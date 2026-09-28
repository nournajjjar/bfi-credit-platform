#!/usr/bin/env python3
"""
Database operations module for Deep Research system
"""

import json
import re
from datetime import datetime
import pg8000 as psycopg2
from rapidfuzz import fuzz, process

from core.config import (
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    SECTOR_LABELS, CACHE_DAYS
)


# ══════════════════════════════════════════════════════════════════════════════
#  CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_conn():
    """Create and return a database connection"""
    return psycopg2.connect(
        host=DB_HOST, port=int(DB_PORT), database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SCHEMA MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def init_enrichment_table(conn):
    """Initialize the enrichment table if it doesn't exist"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entreprises_enrichies (
                id               SERIAL PRIMARY KEY,
                entreprise_id    INTEGER,
                source_url       TEXT UNIQUE,
                denomination     TEXT,
                source_table     TEXT,
                rapport_json     JSONB,
                sector_stats     JSONB,
                positioning      JSONB,
                qa_layer         JSONB,
                enriched_at      TIMESTAMP DEFAULT NOW(),
                raw_sections     JSONB
            );
        """)
        cur.execute("""
            ALTER TABLE entreprises_enrichies
            ADD COLUMN IF NOT EXISTS qa_layer JSONB;
        """)
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  COLUMN RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def get_table_columns(conn, table):
    """Get all column names for a table"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
        """, (table,))
        rows = cur.fetchall()
    return {row[0].lower().strip(): row[0] for row in rows}


def resolve_col(cols_map, *candidates):
    """Resolve a column name from candidates"""
    def normalize(s):
        return s.lower().strip().replace(" ", "_").replace("-", "_")
    nm = {normalize(k): v for k, v in cols_map.items()}
    for c in candidates:
        if normalize(c) in nm:
            return nm[normalize(c)]
    return None


def safe_col_expr(cols_map, candidates, alias):
    """Generate a safe column expression with alias"""
    actual = resolve_col(cols_map, *candidates)
    if actual:
        return f'"{actual}" AS {alias}'
    return f"NULL::TEXT AS {alias}"


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_all_names(conn):
    """Load all company names from all sector tables"""
    tables = list(SECTOR_LABELS.keys())
    parts = []

    for t in tables:
        cols = get_table_columns(conn, t)
        parts.append(f"""
            SELECT
                {safe_col_expr(cols, ["id"], "id")},
                {safe_col_expr(cols, ["denomination"], "denomination")},
                {safe_col_expr(cols, ["raison_sociale","raison sociale"], "raison_sociale")},
                {safe_col_expr(cols, ["gouvernorat"], "gouvernorat")},
                {safe_col_expr(cols, ["activites","activités"], "activites")},
                {safe_col_expr(cols, ["produits"], "produits")},
                {safe_col_expr(cols, ["Source URL","source_url","source url"], "source_url")},
                {safe_col_expr(cols, ["capital_dt","Capital_DT","Capital DT","capital"], "capital")},
                {safe_col_expr(cols, ["emploi"], "emploi")},
                {safe_col_expr(cols, ["regime","régime"], "regime")},
                {safe_col_expr(cols, ["url","URL"], "url")},
                {safe_col_expr(cols, ["entree_production","entrée production","entree production"], "entree_production")},
                '{t}' AS source_table
            FROM {t}
            WHERE denomination IS NOT NULL AND TRIM(denomination::TEXT) <> ''
        """)

    query = " UNION ALL ".join(parts) + " ORDER BY denomination ASC"

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        rows = cur.fetchall()

    for r in rows:
        r["label_secteur"] = SECTOR_LABELS.get(r["source_table"], r["source_table"])

    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  FUZZY SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def fuzzy_search(query, companies, top_n=5, threshold=40):
    """Perform fuzzy search on company names"""
    names = [c["denomination"] for c in companies]
    matches = process.extract(query, names, scorer=fuzz.WRatio, limit=top_n)
    return sorted(
        [(score, companies[idx]) for _, score, idx in matches if score >= threshold],
        key=lambda x: -x[0]
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTOR STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

def get_sector_stats(conn, source_table):
    """Calculate sector statistics"""
    if source_table not in SECTOR_LABELS:
        return {}

    cols = get_table_columns(conn, source_table)
    capital_col = resolve_col(cols, "capital_dt", "Capital_DT", "Capital DT", "capital")
    emploi_col = resolve_col(cols, "emploi")
    regime_col = resolve_col(cols, "regime", "régime")
    url_col = resolve_col(cols, "url", "URL")
    entree_col = resolve_col(cols, "entree_production", "entrée production", "entree production")
    denom_col = resolve_col(cols, "denomination")
    gov_col = resolve_col(cols, "gouvernorat")

    def _rex(col):
        return (
            f'NULLIF(REGEXP_REPLACE("{col}", \'[^0-9]\', \'\', \'g\'), \'\')::NUMERIC'
            if col else "NULL::NUMERIC"
        )

    capital_expr = _rex(capital_col)
    emploi_expr = _rex(emploi_col)
    export_expr = (
        f"CASE WHEN LOWER(COALESCE(\"{regime_col}\",'')) LIKE '%totalement%' THEN 1 ELSE 0 END"
        if regime_col else "0"
    )
    url_expr = (
        f"CASE WHEN \"{url_col}\" IS NOT NULL AND TRIM(\"{url_col}\") <> '' "
        f"AND \"{url_col}\" <> '-' THEN 1 ELSE 0 END"
        if url_col else "0"
    )
    age_expr = (
        f"CASE WHEN \"{entree_col}\" ~ '^[0-9]{{4}}$' "
        f"THEN EXTRACT(YEAR FROM NOW())::INT - \"{entree_col}\"::INT ELSE NULL END"
        if entree_col else "NULL::NUMERIC"
    )
    denom_filter = f'"{denom_col}" IS NOT NULL AND TRIM("{denom_col}") <> \'\'' if denom_col else "TRUE"
    capital_filter = f'"{capital_col}" <> \'-\'' if capital_col else "TRUE"

    query = f"""
        WITH cleaned AS (
            SELECT {capital_expr} AS capital_num, {emploi_expr} AS emploi_num,
                   {export_expr} AS is_export, {url_expr} AS has_url,
                   {age_expr} AS age_years, gouvernorat
            FROM {source_table}
            WHERE {denom_filter} AND {capital_filter}
        )
        SELECT
            COUNT(*) AS total_companies,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY capital_num)
                  FILTER (WHERE capital_num IS NOT NULL)) AS median_capital,
            ROUND(AVG(capital_num)      FILTER (WHERE capital_num IS NOT NULL)) AS avg_capital,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY capital_num)
                  FILTER (WHERE capital_num IS NOT NULL)) AS p25_capital,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY capital_num)
                  FILTER (WHERE capital_num IS NOT NULL)) AS p75_capital,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY emploi_num)
                  FILTER (WHERE emploi_num IS NOT NULL)) AS median_emploi,
            ROUND(AVG(emploi_num)       FILTER (WHERE emploi_num IS NOT NULL)) AS avg_emploi,
            ROUND(100.0 * SUM(is_export) / NULLIF(COUNT(*),0), 1) AS pct_export,
            ROUND(100.0 * SUM(has_url)   / NULLIF(COUNT(*),0), 1) AS pct_web_presence,
            ROUND(AVG(age_years)         FILTER (WHERE age_years IS NOT NULL)) AS avg_age,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY age_years)
                  FILTER (WHERE age_years IS NOT NULL)) AS median_age
        FROM cleaned;
    """

    gov_query = (
        f'SELECT "{gov_col}" AS gouvernorat, COUNT(*) AS cnt FROM {source_table} '
        f'WHERE "{gov_col}" IS NOT NULL AND TRIM("{gov_col}") <> \'\' '
        f'GROUP BY "{gov_col}" ORDER BY cnt DESC LIMIT 5;'
        if gov_col else "SELECT NULL AS gouvernorat, 0 AS cnt WHERE FALSE;"
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        row = cur.fetchone()
        cur.execute(gov_query)
        top_govs = [r["gouvernorat"] for r in cur.fetchall()]

    stats = dict(row) if row else {}
    for k, v in stats.items():
        if v is not None:
            try:
                stats[k] = float(v)
            except:
                pass

    stats["top_gouvernorats"] = top_govs
    stats["sector_label"] = SECTOR_LABELS.get(source_table, source_table)
    stats["source_table"] = source_table
    return stats


# ══════════════════════════════════════════════════════════════════════════════
#  POSITIONING
# ══════════════════════════════════════════════════════════════════════════════

def _parse_num(val):
    """Parse a numeric value from string"""
    if val is None:
        return None
    cleaned = re.sub(r'[^0-9]', '', str(val))
    return float(cleaned) if cleaned else None


def _position_label(value, median, p25=None, p75=None):
    """Generate positioning label based on value and quartiles"""
    if value is None or median is None:
        return "Non disponible"
    if p25 and value < p25:
        return "Faible (Q1 — bas du secteur)"
    if p75 and value > p75:
        return "Élevé (Q4 — haut du secteur)"
    if value < median * 0.85:
        return "En dessous de la médiane"
    if value > median * 1.15:
        return "Au dessus de la médiane"
    return "Dans la médiane"


def compute_positioning(company, stats):
    """Compute company positioning within sector"""
    capital_val = _parse_num(company.get("capital"))
    emploi_val = _parse_num(company.get("emploi"))

    ep = str(company.get("entree_production") or "").strip()
    age_val = datetime.now().year - int(ep) if re.match(r'^\d{4}$', ep) else None

    regime = str(company.get("regime") or "").lower()
    is_export = "totalement" in regime

    url_val = str(company.get("url") or "").strip()
    has_web = bool(url_val and url_val not in ("", "-"))

    return {
        "capital_value": capital_val,
        "emploi_value": emploi_val,
        "age_years": age_val,
        "is_export": is_export,
        "has_web": has_web,
        "capital_position": _position_label(
            capital_val, stats.get("median_capital"),
            stats.get("p25_capital"), stats.get("p75_capital")
        ),
        "emploi_position": _position_label(
            emploi_val, stats.get("median_emploi")
        ),
        "age_position": (
            "Entreprise jeune (< 10 ans)" if age_val and age_val < 10 else
            "Entreprise établie (10-25 ans)" if age_val and age_val < 25 else
            "Entreprise mature (> 25 ans)" if age_val else "Non disponible"
        ),
        "export_vs_sector": (
            f"Exportatrice — {stats.get('pct_export', 0):.1f}% du secteur exportent"
            if is_export else
            f"Non exportatrice — {stats.get('pct_export', 0):.1f}% du secteur exportent"
        ),
        "web_vs_sector": (
            f"Présence web confirmée — {stats.get('pct_web_presence', 0):.1f}% du secteur en ont une"
            if has_web else
            f"Pas de présence web — {stats.get('pct_web_presence', 0):.1f}% du secteur en ont une"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CACHE OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_cached_enrichment(conn, source_url):
    """Get cached enrichment data if available"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM entreprises_enrichies
            WHERE source_url = %s
              AND enriched_at > NOW() - INTERVAL '%s days'
        """, (source_url, CACHE_DAYS))
        return cur.fetchone()


def save_enrichment(conn, company, rapport, sector_stats, positioning, qa_layer):
    """Save enrichment data to database"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO entreprises_enrichies
              (entreprise_id, source_url, denomination, source_table,
               rapport_json, sector_stats, positioning, qa_layer, enriched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (source_url) DO UPDATE SET
              rapport_json = EXCLUDED.rapport_json,
              sector_stats = EXCLUDED.sector_stats,
              positioning  = EXCLUDED.positioning,
              qa_layer     = EXCLUDED.qa_layer,
              enriched_at  = NOW()
        """, (
            company.get("id"), company.get("source_url"),
            company.get("denomination"), company.get("source_table"),
            json.dumps(rapport, ensure_ascii=False),
            json.dumps(sector_stats, ensure_ascii=False),
            json.dumps(positioning, ensure_ascii=False),
            json.dumps(qa_layer, ensure_ascii=False),
        ))
        conn.commit()