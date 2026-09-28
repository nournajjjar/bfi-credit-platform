#!/usr/bin/env python3
"""
PDF financial extractor — Optimized version (text-only, Phi-4 compatible)

Phi-4 is a text-only model — VLM image calls removed entirely.

Optimizations applied:
  1. Parallel text extraction (ThreadPoolExecutor, max_workers=2)
  2. Pre-filter non-financial pages (skip cover, signatures, etc.)
  3. max_tokens reduced 4096 → 1500
  4. PDF extraction result cached to JSON (skip on re-run)
  5. FIXED: _find() handles both list rows AND dict rows
"""
from __future__ import annotations

import base64, json, re, pathlib
from typing import Dict, List, Optional, Union, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import AZURE_MODEL
from core.openai_client import get_openai_client
from core.logger import setup_logger

logger = setup_logger(__name__)

HAS_DOCLING = False

_FINANCIAL_KEYWORDS = [
    "total", "actif", "passif", "chiffre", "résultat", "resultat",
    "capitaux", "dettes", "exercice", "tnd", "dt", "bilan", "cpc",
    "produits", "charges", "marge", "flux", "trésorerie", "tresorerie",
    "immobilisé", "circulant", "amortissement", "provision",
]

_MIN_KEYWORD_HITS = 3
_MAX_WORKERS      = 2


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _extract_page_text(pdf_bytes: bytes, page_number: int) -> str:
    """Extract text from a PDF page via PyMuPDF."""
    import fitz
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_number]
    text = page.get_text()
    doc.close()
    return text.strip()


def _is_financial_page(pdf_bytes: bytes, page_number: int) -> bool:
    """
    Quick pre-filter — checks if page has enough financial keywords.
    Skips cover pages, table of contents, audit signatures, etc.
    Zero API cost.
    """
    try:
        text = _extract_page_text(pdf_bytes, page_number).lower()
        hits = sum(1 for kw in _FINANCIAL_KEYWORDS if kw in text)
        return hits >= _MIN_KEYWORD_HITS
    except Exception:
        return True  # if check fails, process the page anyway


VLM_SYSTEM_PROMPT = """\
Tu es un moteur OCR financier de précision pour des états financiers tunisiens (CMF).
Retourne UNIQUEMENT du JSON valide — sans balises markdown, sans préambule.

Schéma attendu :
{
  "page_type": "bilan_actif | bilan_passif | cpc | tft | etic | other",
  "title": "<titre de la section tel qu'imprimé>",
  "tables": [
    {
      "caption": "<titre du tableau>",
      "headers": ["col1", "col2"],
      "rows": [["label", "val1", "val2"]]
    }
  ],
  "notes": "<texte libre de la page>"
}

Règles CRITIQUES :
- Copie chaque chiffre EXACTEMENT tel qu'imprimé (sans arrondi, sans formatage).
- Parenthèses = valeur négative, ex : (1 234 567) → conserver telles quelles.
- Cellule vide → null.
- Si plusieurs tableaux sur la page, tous les inclure dans "tables".
"""


# ══════════════════════════════════════════════════════════════════
# 1. DOCLING PASS (disabled on Windows)
# ══════════════════════════════════════════════════════════════════

def _docling_extract(pdf_bytes: bytes) -> dict:
    if not HAS_DOCLING:
        return {"markdown": "", "tables": []}
    return {"markdown": "", "tables": []}


# ══════════════════════════════════════════════════════════════════
# 2. TEXT EXTRACTION (Phi-4 compatible — no image)
# ══════════════════════════════════════════════════════════════════

def _vlm_page_text(client, pdf_bytes: bytes, page_number: int) -> dict:
    """
    Text-based extraction using Phi-4.
    Phi-4 is text-only — no image_url calls.
    """
    text = _extract_page_text(pdf_bytes, page_number)
    if not text or len(text.strip()) < 20:
        return {"page_type": "empty", "tables": [], "notes": ""}

    prompt = f"""Tu es un expert comptable analysant un document financier tunisien (CMF).
Voici le texte de la page {page_number + 1} :

{text[:4000]}

Retourne UNIQUEMENT un JSON valide avec ce schéma exact :
{{
  "page_type": "bilan_actif|bilan_passif|cpc|tft|etic|other",
  "title": "...",
  "tables": [
    {{
      "caption": "...",
      "headers": ["Libellé", "date1", "date2"],
      "rows": [["nom de la ligne", "valeur1", "valeur2"]]
    }}
  ],
  "notes": "..."
}}

Règles :
- Copie chaque chiffre EXACTEMENT tel qu'imprimé.
- Cellule vide = null.
- page_type = "bilan_actif" si la page contient l'actif du bilan.
- page_type = "bilan_passif" si la page contient le passif et capitaux propres.
- page_type = "cpc" si la page contient les produits et charges (compte de résultat).
- page_type = "tft" si la page contient les flux de trésorerie.
- page_type = "other" pour tout le reste."""

    try:
        resp = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[
                {"role": "system", "content": "Tu es un expert comptable. Réponds uniquement en JSON valide."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            timeout=60,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        result = json.loads(raw)
        logger.info(f"  Page {page_number+1}: OK ({result.get('page_type','?')})")
        return result
    except json.JSONDecodeError:
        logger.warning(f"  Page {page_number+1}: JSON parse error")
        text_short = _extract_page_text(pdf_bytes, page_number)
        return {"page_type": "parse_error", "tables": [], "notes": text_short[:300]}
    except Exception as e:
        logger.warning(f"  Page {page_number+1}: failed ({type(e).__name__})")
        return {"page_type": "parse_error", "tables": [], "notes": ""}


def _process_single_page(args) -> tuple:
    """Worker function — text only (Phi-4 does not support vision)."""
    client, pdf_bytes, i, is_financial = args
    if not is_financial:
        return i, {"page_type": "other", "tables": [], "notes": "",
                   "_page_number": i + 1, "_skipped": True}
    page_data = _vlm_page_text(client, pdf_bytes, i)
    page_data["_page_number"] = i + 1
    return i, page_data


# ══════════════════════════════════════════════════════════════════
# 3. MERGER
# ══════════════════════════════════════════════════════════════════

def _merge(docling_data: dict, vlm_pages: list) -> dict:
    by_type: dict = {}
    for page in vlm_pages:
        pt = page.get("page_type", "other")
        by_type.setdefault(pt, []).append(page)

    return {
        "source":               "text_phi4",
        "pages":                vlm_pages,
        "financial_statements": {
            pt: {
                "title":  pages[0].get("title", pt),
                "tables": [{"page": p.get("_page_number"), **t}
                           for p in pages for t in p.get("tables", [])],
                "notes":  " | ".join(str(p.get("notes","")) for p in pages if p.get("notes")),
            }
            for pt, pages in by_type.items()
        },
        "docling_markdown": docling_data.get("markdown", ""),
    }


# ══════════════════════════════════════════════════════════════════
# 4. NORMALISATION — handles both list rows AND dict rows
# ══════════════════════════════════════════════════════════════════

def _normalize_financial(pages: list) -> dict:
    result = {"bilan_actif": {}, "bilan_passif": {}, "cpc": {}, "tft": {}, "raw_pages": pages}

    def _find(rows, *keywords):
        for row in rows:
            # Format A: list ["label", val1, val2, ...]
            if isinstance(row, list) and len(row) >= 2:
                label = str(row[0]).lower()
                if any(k.lower() in label for k in keywords):
                    for v in row[1:]:
                        if v is None:
                            continue
                        s = str(v).strip()
                        if s and s not in ("null", "None", ""):
                            return s
            # Format B: dict {"label": "...", "values": {...}}
            elif isinstance(row, dict):
                label = (row.get("label") or "").lower()
                if any(k.lower() in label for k in keywords):
                    for v in row.get("values", {}).values():
                        if v and str(v) not in ("null", "None", ""):
                            return str(v)
        return None

    for page in pages:
        pt = page.get("page_type", "")
        all_rows = []
        for t in page.get("tables", []):
            for r in t.get("rows", []):
                all_rows.append(r)

        if pt == "bilan_actif":
            result["bilan_actif"] = {
                "total_actif_immobilise": _find(all_rows,
                    "immobilisé", "actif immobilise", "immobilisations nettes",
                    "total actif non courant", "actif non courant"),
                "total_actif_circulant": _find(all_rows,
                    "circulant", "actif circulant", "total actif courant",
                    "actifs courants"),
                "disponibilites": _find(all_rows,
                    "disponibilit", "liquidit", "trésorerie et équivalents",
                    "caisse", "banque"),
                "total_actif": _find(all_rows,
                    "total actif", "total de l'actif", "total des actifs",
                    "total général"),
            }

        elif pt == "bilan_passif":
            result["bilan_passif"] = {
                "capital_social": _find(all_rows,
                    "capital social", "capital souscrit"),
                "total_capitaux_propres": _find(all_rows,
                    "total des capitaux propres", "total capitaux propres",
                    "capitaux propres", "total cp"),
                "total_dettes": _find(all_rows,
                    "total des dettes", "total dettes", "dettes financières",
                    "total passif non courant", "emprunts"),
                "total_passif": _find(all_rows,
                    "total passif", "total du passif", "total des passifs",
                    "total général"),
            }

        elif pt == "cpc":
            result["cpc"] = {
                "chiffre_affaires": _find(all_rows,
                    "chiffre d'affaires", "chiffre d affaires", "revenus",
                    "produits d'exploitation", "total produits", "ventes"),
                "marge_brute": _find(all_rows,
                    "marge brute", "marge commerciale"),
                "resultat_exploitation": _find(all_rows,
                    "résultat d'exploitation", "resultat d exploitation",
                    "résultat opérationnel", "bénéfice d'exploitation"),
                "resultat_net": _find(all_rows,
                    "résultat net", "resultat net", "bénéfice net",
                    "résultat de l'exercice", "résultat après impôt"),
                "charges_total": _find(all_rows,
                    "total charges", "charges totales", "total des charges"),
                "achats_consommes": _find(all_rows,
                    "achats consommés", "achats consommes",
                    "matières consommées", "consommation"),
            }

        elif pt == "tft":
            result["tft"] = {
                "flux_exploitation": _find(all_rows,
                    "exploitation", "opérationnel", "activités opérationnelles"),
                "flux_investissement": _find(all_rows,
                    "investissement", "activités d'investissement"),
                "flux_financement": _find(all_rows,
                    "financement", "activités de financement"),
                "variation_nette": _find(all_rows,
                    "variation nette", "variation de trésorerie",
                    "augmentation", "diminution de trésorerie"),
            }

    return result


# ══════════════════════════════════════════════════════════════════
# 5. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def extract_pdf_financial(pdf_bytes: bytes, max_pages: int = None,
                          cache_key: str = None) -> dict:
    """
    Optimized text-only extraction pipeline (Phi-4 compatible).
      1. Check JSON cache (skip if already extracted)
      2. Pre-filter non-financial pages
      3. Parallel text extraction (2 workers)
      4. Normalize extracted data
    """
    import fitz

    # ── Check cache ────────────────────────────────────────────────
    if cache_key:
        cache_path = pathlib.Path(f"database/output/{cache_key}_extraction.json")
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                logger.info(f"PDF extraction: using cache ({cache_path})")
                return cached
            except Exception:
                pass

    doc   = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc) if max_pages is None else min(len(doc), max_pages)
    doc.close()

    logger.info(f"PDF extraction (text-only, Phi-4): {total} pages")
    client = get_openai_client()

    docling_data = _docling_extract(pdf_bytes)

    # ── Pre-filter pages ───────────────────────────────────────────
    financial_flags = []
    n_skipped = 0
    for i in range(total):
        is_fin = _is_financial_page(pdf_bytes, i)
        financial_flags.append(is_fin)
        if not is_fin:
            n_skipped += 1
    logger.info(f"  Page filter: {total - n_skipped} financial / {n_skipped} skipped")

    # ── Parallel text extraction ───────────────────────────────────
    pages = [None] * total
    n_ok = 0; n_error = 0; n_filtered = 0

    args_list = [(client, pdf_bytes, i, financial_flags[i]) for i in range(total)]

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(_process_single_page, args): args[2]
                   for args in args_list}
        for future in as_completed(futures):
            i, page_data = future.result()
            pages[i] = page_data
            if page_data.get("_skipped"):
                n_filtered += 1
            elif page_data.get("page_type") in ("parse_error", "empty"):
                n_error += 1
            else:
                n_ok += 1

    # ── Merge + normalize ─────────────────────────────────────────
    merged    = _merge(docling_data, pages)
    financial = _normalize_financial(pages)
    financial["_hybrid_meta"] = {
        "pages_total":    total,
        "pages_ok":       n_ok,
        "pages_error":    n_error,
        "pages_filtered": n_filtered,
        "has_docling":    HAS_DOCLING,
        "optimized":      True,
        "mode":           "text_only_phi4",
    }
    financial["_full_extraction"] = merged

    logger.info(f"Extraction done: {n_ok} ok / {n_error} error / {n_filtered} filtered")
    return financial


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def extract_clean_value(data: Dict, *keys) -> Optional[Union[int, float]]:
    for key in keys:
        if key in data:
            val = data[key]
            if isinstance(val, (int, float)): return val
            if isinstance(val, str):
                try:
                    cleaned = (val.replace(" ","").replace(",","")
                                  .replace("DT","").replace("\xa0","")
                                  .replace("(","").replace(")","")
                                  .replace("<","").replace(">","").strip())
                    if not cleaned or cleaned.lower() in ("null","none",""): continue
                    return float(cleaned) if "." in cleaned else int(cleaned)
                except: continue
    return None


def extract_financial_summary(pdf_financial: Dict) -> Dict:
    ba  = pdf_financial.get("bilan_actif", {})
    bp  = pdf_financial.get("bilan_passif", {})
    cpc = pdf_financial.get("cpc", {})
    tft = pdf_financial.get("tft", {})
    r = {
        "chiffre_affaires":     extract_clean_value(cpc, "chiffre_affaires"),
        "resultat_net":         extract_clean_value(cpc, "resultat_net"),
        "resultat_exploitation":extract_clean_value(cpc, "resultat_exploitation"),
        "charges_total":        extract_clean_value(cpc, "charges_total"),
        "achats_consommes":     extract_clean_value(cpc, "achats_consommes"),
        "marge_brute":          extract_clean_value(cpc, "marge_brute"),
        "total_actif":          extract_clean_value(ba,  "total_actif"),
        "actif_courant":        extract_clean_value(ba,  "total_actif_circulant"),
        "actif_non_courant":    extract_clean_value(ba,  "total_actif_immobilise"),
        "disponibilites":       extract_clean_value(ba,  "disponibilites"),
        "capitaux_propres":     extract_clean_value(bp,  "total_capitaux_propres"),
        "capital_social":       extract_clean_value(bp,  "capital_social"),
        "dettes_total":         extract_clean_value(bp,  "total_dettes"),
        "flux_exploitation":    extract_clean_value(tft, "flux_exploitation"),
        "flux_investissement":  extract_clean_value(tft, "flux_investissement"),
        "flux_financement":     extract_clean_value(tft, "flux_financement"),
        "tresorerie_finale":    extract_clean_value(tft, "variation_nette"),
    }
    if r["resultat_net"] and r["chiffre_affaires"]:
        r["marge_nette_pct"] = round(r["resultat_net"] / r["chiffre_affaires"] * 100, 1)
    if r["dettes_total"] and r["capitaux_propres"]:
        r["ratio_endettement_pct"] = round(r["dettes_total"] / r["capitaux_propres"] * 100, 1)
    if r["capitaux_propres"] and r["total_actif"]:
        r["autonomie_financiere_pct"] = round(r["capitaux_propres"] / r["total_actif"] * 100, 1)
    return r


def format_financial_for_prompt(fs: Dict) -> str:
    def fmt(v):
        if v is None: return "Non disponible"
        if isinstance(v, float): return f"{v:,.0f}" if v > 1000 else f"{v:.1f}"
        return f"{v:,}"
    return f"""DONNÉES FINANCIÈRES:
CA: {fmt(fs.get('chiffre_affaires'))} DT | Résultat net: {fmt(fs.get('resultat_net'))} DT
Total actif: {fmt(fs.get('total_actif'))} DT | Capitaux propres: {fmt(fs.get('capitaux_propres'))} DT
Dettes: {fmt(fs.get('dettes_total'))} DT | Marge nette: {fmt(fs.get('marge_nette_pct'))}%"""


def get_simplified_pdf_context(pdf_financial: Dict) -> Dict[str, str]:
    fs = extract_financial_summary(pdf_financial)
    return {
        "financial_summary_text": format_financial_for_prompt(fs),
        "financial_summary_dict": fs,
        "bilan_actif_text":  json.dumps(pdf_financial.get("bilan_actif",{}),  ensure_ascii=False, indent=2),
        "bilan_passif_text": json.dumps(pdf_financial.get("bilan_passif",{}), ensure_ascii=False, indent=2),
        "cpc_text":          json.dumps(pdf_financial.get("cpc",{}),           ensure_ascii=False, indent=2),
        "tft_text":          json.dumps(pdf_financial.get("tft",{}),           ensure_ascii=False, indent=2),
    }