#!/usr/bin/env python3
"""
PDF financial extractor — Hybrid: Docling structural + Azure VLM visual
Adapted from the hybrid Docling+GPT-4o extractor to work with Azure OpenAI.

Pipeline per page:
  1. Docling  → structural pass (table detection, reading order, markdown)
  2. Azure VLM (Phi-4 vision) → visual pass on page image (accurate numbers)
  3. Merger   → VLM wins on numbers, Docling wins on labels/text
  4. Fallback → PyMuPDF text → LLM text prompt (original approach)
"""
from __future__ import annotations

import base64, json, re, io
from typing import Dict, List, Optional, Union, Any
from core.config import AZURE_MODEL
from core.openai_client import get_openai_client
from core.logger import setup_logger

logger = setup_logger(__name__)

# Docling disabled ? causes std::bad_alloc on Windows
HAS_DOCLING = False


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _page_to_base64(pdf_bytes: bytes, page_number: int, dpi: int = 150) -> str:
    """Rasterise one PDF page → base64 JPEG."""
    import fitz
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_number]
    mat  = fitz.Matrix(dpi / 72, dpi / 72)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    doc.close()
    return base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")


def _extract_page_text(pdf_bytes: bytes, page_number: int) -> str:
    """Text fallback via PyMuPDF."""
    import fitz
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_number]
    text = page.get_text()
    doc.close()
    return text.strip()


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
      "rows": [{"label": "...", "values": {"col1": "...", "col2": "..."}}]
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
# 1. DOCLING PASS (optionnel)
# ══════════════════════════════════════════════════════════════════

def _docling_extract(pdf_bytes: bytes) -> dict:
    if not HAS_DOCLING:
        return {"markdown": "", "tables": []}
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes); tmp = pathlib.Path(f.name)
    try:
        opts = PdfPipelineOptions(
            do_ocr=False, do_table_structure=True,
            table_structure_options=TableStructureOptions(do_cell_matching=True, mode="fast"),
            do_picture_description=False, generate_picture_images=False,
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        result = converter.convert(tmp)
        doc    = result.document
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as mf:
            md_path = pathlib.Path(mf.name)
        doc.save_as_markdown(md_path, include_annotations=False)
        markdown = md_path.read_text(encoding="utf-8"); md_path.unlink(missing_ok=True)
        tables = []
        for tbl in doc.tables:
            rows = [[cell.text for cell in row] for row in tbl.data.grid]
            tables.append({"caption": getattr(tbl, "caption", ""), "data": rows})
        logger.info(f"Docling: {len(tables)} table(s) detected")
        return {"markdown": markdown, "tables": tables}
    except Exception as e:
        logger.warning(f"Docling failed: {e}")
        return {"markdown": "", "tables": []}
    finally:
        tmp.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════
# 2. VLM VISUAL PASS (image → Azure)
# ══════════════════════════════════════════════════════════════════

def _vlm_page_image(client, pdf_bytes: bytes, page_number: int) -> dict:
    """Send page image to Azure VLM — much more accurate for tables."""
    try:
        b64 = _page_to_base64(pdf_bytes, page_number)
    except Exception as e:
        logger.warning(f"Page {page_number+1} rasterization failed: {e}")
        return None   # triggers text fallback

    try:
        resp = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[
                {"role": "system", "content": VLM_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high"
                    }},
                    {"type": "text", "text": (
                        f"Page {page_number+1} d'un état financier tunisien. "
                        "Extrais TOUS les tableaux et chiffres avec précision."
                    )}
                ]}
            ],
            max_tokens=4096,
            timeout=120,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        if not raw:
            return None
        result = json.loads(raw)
        logger.info(f"  Page {page_number+1}: VLM image OK ({result.get('page_type','?')})")
        return result
    except json.JSONDecodeError:
        logger.warning(f"  Page {page_number+1}: VLM JSON parse error")
        return None
    except Exception as e:
        logger.warning(f"  Page {page_number+1}: VLM image failed ({type(e).__name__}) — text fallback")
        return None


def _vlm_page_text(client, pdf_bytes: bytes, page_number: int) -> dict:
    """Text-based fallback (original approach)."""
    text = _extract_page_text(pdf_bytes, page_number)
    if not text or len(text.strip()) < 20:
        return {"page_type": "empty", "tables": [], "notes": ""}

    prompt = f"""Tu es un expert comptable analysant un document financier tunisien.
Voici le texte de la page {page_number + 1} :

{text[:4000]}

Retourne UNIQUEMENT un JSON valide avec le schéma :
{{"page_type": "bilan_actif|bilan_passif|cpc|tft|etic|other",
  "title": "...", "tables": [{{"caption":"...","headers":[],"rows":[]}}], "notes": "..."}}

Copie chaque chiffre exactement. Cellule vide = null."""

    try:
        resp = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            timeout=120,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        result = json.loads(raw)
        logger.info(f"  Page {page_number+1}: text fallback OK ({result.get('page_type','?')})")
        return result
    except Exception:
        return {"page_type": "parse_error", "tables": [], "notes": text[:300]}


# ══════════════════════════════════════════════════════════════════
# 3. MERGER
# ══════════════════════════════════════════════════════════════════

def _merge(docling_data: dict, vlm_pages: list[dict]) -> dict:
    """VLM wins on numbers; Docling adds structural context."""
    by_type: dict[str, list] = {}
    for page in vlm_pages:
        pt = page.get("page_type", "other")
        by_type.setdefault(pt, []).append(page)

    return {
        "source":               "hybrid_docling_vlm",
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
# NORMALISATION (inchangée)
# ══════════════════════════════════════════════════════════════════

def _normalize_financial(pages: list[dict]) -> dict:
    result = {"bilan_actif": {}, "bilan_passif": {}, "cpc": {}, "tft": {}, "raw_pages": pages}

    def _find(rows, *keywords):
        for row in rows:
            label = (row.get("label") or "").lower()
            if any(k.lower() in label for k in keywords):
                for v in row.get("values", {}).values():
                    if v and v != "null":
                        return str(v)
        return None

    for page in pages:
        pt       = page.get("page_type", "")
        all_rows = [r for t in page.get("tables", []) for r in t.get("rows", []) if isinstance(r, dict)]
        if pt == "bilan_actif":
            result["bilan_actif"] = {
                "total_actif_immobilise": _find(all_rows, "immobilisé", "actif immobilisé"),
                "total_actif_circulant":  _find(all_rows, "circulant", "actif circulant"),
                "disponibilites":         _find(all_rows, "disponibilit"),
                "total_actif":            _find(all_rows, "total actif", "total de l'actif"),
            }
        elif pt == "bilan_passif":
            result["bilan_passif"] = {
                "capital_social":         _find(all_rows, "capital social", "capital"),
                "total_capitaux_propres": _find(all_rows, "capitaux propres"),
                "total_dettes":           _find(all_rows, "dettes", "total dettes"),
                "total_passif":           _find(all_rows, "total passif"),
            }
        elif pt == "cpc":
            result["cpc"] = {
                "chiffre_affaires": _find(all_rows, "chiffre d'affaires", "revenus"),
                "marge_brute":      _find(all_rows, "marge brute"),
                "resultat_net":     _find(all_rows, "résultat net", "resultat net"),
                "charges_total":    _find(all_rows, "total charges", "charges totales"),
            }
        elif pt == "tft":
            result["tft"] = {
                "flux_exploitation":   _find(all_rows, "exploitation", "opérationnel"),
                "flux_investissement": _find(all_rows, "investissement"),
                "flux_financement":    _find(all_rows, "financement"),
                "variation_nette":     _find(all_rows, "variation nette"),
            }
    return result


# ══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def extract_pdf_financial(pdf_bytes: bytes, max_pages: int = None) -> dict:
    """
    Hybrid extraction pipeline:
      1. Docling structural pass (if installed)
      2. Azure VLM per page — image-based (accurate for tables)
      3. Text fallback if VLM image fails
    """
    import fitz
    doc   = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc) if max_pages is None else min(len(doc), max_pages)
    doc.close()

    logger.info(f"PDF extraction (hybrid): {total} pages")
    client = get_openai_client()

    # ── Docling structural pass ────────────────────────────────────
    docling_data = _docling_extract(pdf_bytes)

    # ── VLM pass per page ─────────────────────────────────────────
    pages = []
    n_image = 0; n_text = 0
    for i in range(total):
        logger.info(f"  Page {i+1}/{total}...")
        page_data = _vlm_page_image(client, pdf_bytes, i)
        if page_data is None:
            page_data = _vlm_page_text(client, pdf_bytes, i)
            n_text += 1
        else:
            n_image += 1
        page_data["_page_number"] = i + 1
        pages.append(page_data)

    # ── Merge + normalize ─────────────────────────────────────────
    merged    = _merge(docling_data, pages)
    financial = _normalize_financial(pages)
    financial["_hybrid_meta"] = {
        "pages_via_image": n_image,
        "pages_via_text":  n_text,
        "docling_tables":  len(docling_data.get("tables", [])),
        "has_docling":     HAS_DOCLING,
    }
    financial["_full_extraction"] = merged

    logger.info(f"Hybrid extraction done: {n_image} image / {n_text} text fallback")
    return financial


# ══════════════════════════════════════════════════════════════════
# HELPERS (inchangés)
# ══════════════════════════════════════════════════════════════════

def extract_clean_value(data: Dict, *keys) -> Optional[Union[int, float]]:
    for key in keys:
        if key in data:
            val = data[key]
            if isinstance(val, (int, float)): return val
            if isinstance(val, str):
                try:
                    cleaned = val.replace(" ","").replace(",","").replace("DT","").strip()
                    if not cleaned or cleaned.lower() in ("null","none",""): continue
                    return float(cleaned) if "." in cleaned else int(cleaned)
                except: continue
    return None


def extract_financial_summary(pdf_financial: Dict) -> Dict:
    ba = pdf_financial.get("bilan_actif", {})
    bp = pdf_financial.get("bilan_passif", {})
    cpc= pdf_financial.get("cpc", {})
    tft= pdf_financial.get("tft", {})
    r  = {
        "chiffre_affaires":    extract_clean_value(cpc, "chiffre_affaires"),
        "resultat_net":        extract_clean_value(cpc, "resultat_net"),
        "charges_total":       extract_clean_value(cpc, "charges_total"),
        "marge_brute":         extract_clean_value(cpc, "marge_brute"),
        "total_actif":         extract_clean_value(ba, "total_actif"),
        "actif_courant":       extract_clean_value(ba, "total_actif_circulant"),
        "actif_non_courant":   extract_clean_value(ba, "total_actif_immobilise"),
        "disponibilites":      extract_clean_value(ba, "disponibilites"),
        "capitaux_propres":    extract_clean_value(bp, "total_capitaux_propres"),
        "capital_social":      extract_clean_value(bp, "capital_social"),
        "dettes_total":        extract_clean_value(bp, "total_dettes"),
        "flux_exploitation":   extract_clean_value(tft,"flux_exploitation"),
        "flux_investissement": extract_clean_value(tft,"flux_investissement"),
        "flux_financement":    extract_clean_value(tft,"flux_financement"),
        "tresorerie_finale":   extract_clean_value(tft,"variation_nette"),
    }
    if r["resultat_net"] and r["chiffre_affaires"]:
        r["marge_nette_pct"] = round(r["resultat_net"]/r["chiffre_affaires"]*100,1)
    if r["dettes_total"] and r["capitaux_propres"]:
        r["ratio_endettement_pct"] = round(r["dettes_total"]/r["capitaux_propres"]*100,1)
    if r["capitaux_propres"] and r["total_actif"]:
        r["autonomie_financiere_pct"] = round(r["capitaux_propres"]/r["total_actif"]*100,1)
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
        "bilan_actif_text":  json.dumps(pdf_financial.get("bilan_actif",{}), ensure_ascii=False, indent=2),
        "bilan_passif_text": json.dumps(pdf_financial.get("bilan_passif",{}), ensure_ascii=False, indent=2),
        "cpc_text":          json.dumps(pdf_financial.get("cpc",{}), ensure_ascii=False, indent=2),
        "tft_text":          json.dumps(pdf_financial.get("tft",{}), ensure_ascii=False, indent=2),
    }