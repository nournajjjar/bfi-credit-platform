"""Database service — fuzzy search across all sector tables"""
import psycopg2
from psycopg2.extras import RealDictCursor
from rapidfuzz import fuzz, process
from typing import List, Dict, Optional
from core.config import DB_CONFIG, SECTOR_LABELS, CACHE_DAYS
from core.logger import setup_logger
import json, re
from datetime import datetime

logger = setup_logger(__name__)


def _get_conn():
    return psycopg2.connect(**DB_CONFIG)


def _get_table_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
        """, (table,))
        return {r[0].lower().strip(): r[0] for r in cur.fetchall()}


def _resolve_col(cols_map, *candidates):
    def norm(s): return s.lower().strip().replace(" ", "_").replace("-", "_")
    nm = {norm(k): v for k, v in cols_map.items()}
    for c in candidates:
        if norm(c) in nm:
            return nm[norm(c)]
    return None


def _safe_col(cols_map, candidates, alias):
    actual = _resolve_col(cols_map, *candidates)
    return f'"{actual}" AS {alias}' if actual else f"NULL::TEXT AS {alias}"


def load_all_companies() -> List[Dict]:
    conn = _get_conn()
    parts = []
    for t in SECTOR_LABELS:
        cols = _get_table_columns(conn, t)
        parts.append(f"""
            SELECT
                {_safe_col(cols, ["id"], "id")},
                {_safe_col(cols, ["denomination"], "denomination")},
                {_safe_col(cols, ["gouvernorat"], "gouvernorat")},
                {_safe_col(cols, ["activites","activités"], "activites")},
                {_safe_col(cols, ["produits"], "produits")},
                {_safe_col(cols, ["Source URL","source_url","source url"], "source_url")},
                {_safe_col(cols, ["capital_dt","Capital_DT","Capital DT","capital"], "capital")},
                {_safe_col(cols, ["emploi"], "emploi")},
                {_safe_col(cols, ["regime","régime"], "regime")},
                {_safe_col(cols, ["url","URL"], "url")},
                {_safe_col(cols, ["entree_production","entrée production"], "entree_production")},
                '{t}' AS source_table
            FROM {t}
            WHERE denomination IS NOT NULL AND TRIM(denomination::TEXT) <> ''
        """)
    query = " UNION ALL ".join(parts) + " ORDER BY denomination ASC"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        r["label_secteur"] = SECTOR_LABELS.get(r["source_table"], r["source_table"])
    return [dict(r) for r in rows]


def fuzzy_search_companies(query: str, top_n: int = 5) -> List[Dict]:
    companies = load_all_companies()
    names = [c["denomination"] for c in companies]
    matches = process.extract(query, names, scorer=fuzz.WRatio, limit=top_n)
    return [
        {**companies[idx], "match_score": round(score, 1)}
        for _, score, idx in matches
        if score >= 40
    ]


def get_sector_stats(source_table: str) -> Dict:
    if source_table not in SECTOR_LABELS:
        return {}
    conn = _get_conn()
    cols = _get_table_columns(conn, source_table)
    capital_col = _resolve_col(cols, "capital_dt", "Capital_DT", "Capital DT", "capital")
    emploi_col  = _resolve_col(cols, "emploi")
    regime_col  = _resolve_col(cols, "regime", "régime")
    url_col     = _resolve_col(cols, "url", "URL")
    entree_col  = _resolve_col(cols, "entree_production", "entrée production")
    denom_col   = _resolve_col(cols, "denomination")
    gov_col     = _resolve_col(cols, "gouvernorat")

    def _rex(col):
        return (f'NULLIF(REGEXP_REPLACE("{col}", \'[^0-9]\', \'\', \'g\'), \'\')::NUMERIC'
                if col else "NULL::NUMERIC")

    export_expr = (f"CASE WHEN LOWER(COALESCE(\"{regime_col}\",'')) LIKE '%totalement%' THEN 1 ELSE 0 END"
                   if regime_col else "0")
    url_expr = (f"CASE WHEN \"{url_col}\" IS NOT NULL AND TRIM(\"{url_col}\") <> '' AND \"{url_col}\" <> '-' THEN 1 ELSE 0 END"
                if url_col else "0")
    age_expr = (f"CASE WHEN \"{entree_col}\" ~ '^[0-9]{{4}}$' THEN EXTRACT(YEAR FROM NOW())::INT - \"{entree_col}\"::INT ELSE NULL END"
                if entree_col else "NULL::NUMERIC")
    denom_filter  = f'"{denom_col}" IS NOT NULL AND TRIM("{denom_col}") <> \'\'' if denom_col else "TRUE"
    capital_filter = f'"{capital_col}" <> \'-\'' if capital_col else "TRUE"

    query = f"""
        WITH cleaned AS (
            SELECT {_rex(capital_col)} AS capital_num, {_rex(emploi_col)} AS emploi_num,
                   {export_expr} AS is_export, {url_expr} AS has_url,
                   {age_expr} AS age_years, gouvernorat
            FROM {source_table}
            WHERE {denom_filter} AND {capital_filter}
        )
        SELECT
            COUNT(*) AS total_companies,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY capital_num) FILTER (WHERE capital_num IS NOT NULL)) AS median_capital,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY capital_num) FILTER (WHERE capital_num IS NOT NULL)) AS p25_capital,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY capital_num) FILTER (WHERE capital_num IS NOT NULL)) AS p75_capital,
            ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY emploi_num)  FILTER (WHERE emploi_num  IS NOT NULL)) AS median_emploi,
            ROUND(100.0 * SUM(is_export) / NULLIF(COUNT(*),0), 1) AS pct_export,
            ROUND(100.0 * SUM(has_url)   / NULLIF(COUNT(*),0), 1) AS pct_web_presence,
            ROUND(AVG(age_years) FILTER (WHERE age_years IS NOT NULL)) AS avg_age
        FROM cleaned;
    """
    gov_query = (f'SELECT "{gov_col}" AS gouvernorat, COUNT(*) AS cnt FROM {source_table} '
                 f'WHERE "{gov_col}" IS NOT NULL GROUP BY "{gov_col}" ORDER BY cnt DESC LIMIT 5;'
                 if gov_col else "SELECT NULL, 0 WHERE FALSE;")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        row = dict(cur.fetchone() or {})
        cur.execute(gov_query)
        top_govs = [r["gouvernorat"] for r in cur.fetchall()]
    conn.close()

    for k, v in row.items():
        if v is not None:
            try: row[k] = float(v)
            except: pass
    row["top_gouvernorats"] = top_govs
    row["sector_label"]     = SECTOR_LABELS[source_table]
    return row


def compute_positioning(company: Dict, stats: Dict) -> Dict:
    def _num(val):
        cleaned = re.sub(r'[^0-9]', '', str(val or ''))
        return float(cleaned) if cleaned else None

    def _pos(value, median, p25=None, p75=None):
        if value is None or median is None: return "Non disponible"
        if p25 and value < p25: return "Faible (Q1)"
        if p75 and value > p75: return "Élevé (Q4)"
        if value < median * 0.85: return "En dessous de la médiane"
        if value > median * 1.15: return "Au dessus de la médiane"
        return "Dans la médiane"

    capital_val = _num(company.get("capital"))
    emploi_val  = _num(company.get("emploi"))
    ep = str(company.get("entree_production") or "").strip()
    age_val = datetime.now().year - int(ep) if re.match(r'^\d{4}$', ep) else None
    is_export = "totalement" in str(company.get("regime") or "").lower()
    url_val   = str(company.get("url") or "").strip()
    has_web   = bool(url_val and url_val not in ("", "-"))

    return {
        "capital_position": _pos(capital_val, stats.get("median_capital"), stats.get("p25_capital"), stats.get("p75_capital")),
        "emploi_position":  _pos(emploi_val,  stats.get("median_emploi")),
        "age_position":     ("Entreprise jeune (< 10 ans)" if age_val and age_val < 10 else
                             "Entreprise établie (10-25 ans)" if age_val and age_val < 25 else
                             "Entreprise mature (> 25 ans)" if age_val else "Non disponible"),
        "export_vs_sector": (f"Exportatrice — {stats.get('pct_export',0):.1f}% du secteur exportent" if is_export
                             else f"Non exportatrice — {stats.get('pct_export',0):.1f}% du secteur exportent"),
        "web_vs_sector":    (f"Présence web — {stats.get('pct_web_presence',0):.1f}% du secteur en ont une" if has_web
                             else f"Pas de présence web — {stats.get('pct_web_presence',0):.1f}% du secteur en ont une"),
        "is_export": is_export,
        "has_web":   has_web,
        "capital_value": capital_val,
        "emploi_value":  emploi_val,
        "age_years":     age_val,
    }