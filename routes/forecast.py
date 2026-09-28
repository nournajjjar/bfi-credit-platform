# backend/routes/forecast.py
"""
API Prévisions financières.
  GET  /api/forecast/load/{report_id}  — périodes depuis rapport caché
  POST /api/forecast/extract-pdf       — upload PDF → extraction rapide sans LLM
  POST /api/forecast/run               — projection financière (OLS + Holt + CAGR)
"""

import re
import io
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from services.mlflow_tracker import log_forecast
from services.financial_forecast import run_forecast

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


# ══════════════════════════════════════════════════════════════════
# Extraction rapide pdfplumber (sans LLM)
# ══════════════════════════════════════════════════════════════════

_DATE_PAT = re.compile(r'\b(\d{2})[/\.](\d{2})[/\.](\d{4})\b')
_NUM_PAT  = re.compile(r'-\s?\d{1,3}(?:\s\d{3})*|\d{1,3}(?:\s\d{3})*')


def _norm_date(s: str) -> str:
    m = _DATE_PAT.search(s)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else s


def _norm_label(s: str) -> str:
    return (s.lower()
             .replace('\u2019', "'").replace('\u2018', "'").replace('\u02bc', "'"))


def _parse_num(s: str) -> Optional[float]:
    s = s.replace(' ', '').replace('\xa0', '').replace(',', '.').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _extract_from_page_text(text: str) -> List[dict]:
    if not text:
        return []
    rows: List[dict] = []
    date_cols: List = []

    for line in text.split('\n'):
        dl = [(m.start(), _norm_date(m.group()), m.end()) for m in _DATE_PAT.finditer(line)]
        if len(dl) >= 2:
            date_cols = dl
            continue
        if not date_cols:
            continue
        label_raw = line[:date_cols[0][0]]
        label = re.sub(r'\s+[A-Z]{1,3}\d{1,3}\s*$', '', label_raw.strip()).strip()
        if not label or len(label) < 2:
            continue
        note_m    = re.search(r'[A-Z]{1,3}\d{2,3}', label_raw)
        val_start = note_m.end() if note_m else max(0, date_cols[0][0] - 3)
        value_region = re.sub(r'\b[A-Z]{1,3}\d{2,3}\b', '', line[val_start:])
        numbers = [v for m in _NUM_PAT.finditer(value_region)
                   if (v := _parse_num(m.group())) is not None]
        n = len(date_cols)
        if len(numbers) < n:
            continue
        if len(numbers) > n:
            numbers = numbers[-n:]
        rows.append({"label": label, "values": {date_cols[i][1]: str(numbers[i]) for i in range(n)}})
    return rows


def _fast_extract_periods_from_pdf(pdf_bytes: bytes) -> dict:
    """Extraction sans LLM via pdfplumber (~2 secondes)."""
    import pdfplumber
    raw_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_rows = []
            try:
                text = page.extract_text(layout=True) or ""
                page_rows = _extract_from_page_text(text)
            except Exception:
                pass
            raw_pages.append({
                "_page_number": i + 1,
                "tables": [{"rows": page_rows}] if page_rows else [],
            })
    return {"raw_pages": raw_pages}


# ══════════════════════════════════════════════════════════════════
# Scanner multi-périodes
# ══════════════════════════════════════════════════════════════════

def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = (str(value).strip()
         .replace('\u202f','').replace(' ','').replace('\xa0','')
         .replace('(', '-').replace(')', '')
         .replace('<', '-').replace('>', '')
         .replace(',', '.'))
    if not s or s in ('-', '—'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_date_col(k: str) -> bool:
    s = str(k).strip()
    # Accepts DD/MM/YYYY, DD.MM.YYYY, or plain YYYY
    return bool(re.match(r'\d{2}[./]\d{2}[./]\d{4}$', s) or re.match(r'^\d{4}$', s))


_TARGET_LABELS: Dict[str, List[str]] = {
    "revenue":             ["revenus", "chiffre d'affaires", "chiffre d affaires",
                            "total produits d'exploitation"],
    "ebit":                ["résultat d'exploitation", "resultat d'exploitation",
                            "résultat d exploitation", "resultat d exploitation"],
    "raw_materials":       ["achats consommés", "achats consommes",
                            "achats d'approvisionnements consommés",
                            "achats d'approvisionnements consommes"],
    "amortization":        ["dotations aux amortissements", "dot aux amortissements",
                            "dotation aux amortissements"],
    "net_result":          ["résultat net de l'exercice", "resultat net de l'exercice",
                            "résultat net", "resultat net",
                            "résultat après modifications", "resultat apres modifications"],
    "equity":              ["total des capitaux propres avant affectation",
                            "total des capitaux propres"],
    "debt_emprunts":       ["total des emprunts"],
    "debt_concours":       ["total des concours bancaires", "concours bancaires"],
    "current_assets":      ["total des actifs courants"],
    "current_liabilities": ["total des passifs courants"],
    "ebit":                ["r?sultat d'exploitation", "resultat d exploitation",
                            "r?sultat d'exploitation", "b?n?fice d'exploitation"],
    "interest":            ["charges financieres nettes", "charges financieres nettes",
                            "interets des emprunts", "charges d'interets",
                            "interets et charges assimilees", "interets", "intérêts"],
    "net_income":          ["r?sultat net de l'exercice", "r?sultat net consolid?",
                            "r?sultat net de l exercice"],
    "total_assets":        ["total des actifs", "total actif"],
    "total_debt":          ["total des dettes", "total dettes financi?res"],
}


def _extract_all_periods(pf: dict) -> List[Dict]:
    by_date: Dict[str, Dict] = {}
    seen:    Dict[str, set]  = {}

    for page in (pf.get("raw_pages", []) or []):
        if not isinstance(page, dict):
            continue
        for table in (page.get("tables", []) or []):
            if not isinstance(table, dict):
                continue
            headers = table.get("headers", []) or []
            date_headers = [h for h in headers if _is_date_col(str(h).replace('/','.'))]
            for row in (table.get("rows", []) or []):
                # Handle list rows: ["LABEL", val1, val2, ...]
                if isinstance(row, list) and len(row) >= 2:
                    label = _norm_label(str(row[0]))
                    vals  = row[1:]
                    # Try to match date headers or use index as date key
                    if date_headers and len(vals) >= len(date_headers):
                        values = {str(date_headers[i]).replace('/','.'): vals[i] for i in range(len(date_headers))}
                    else:
                        # No date headers — skip (can't assign dates)
                        continue
                elif isinstance(row, dict):
                    label  = _norm_label(str(row.get("label", "")))
                    values = row.get("values", {})
                    if not isinstance(values, dict):
                        continue
                else:
                    continue
                for metric_key, subs in _TARGET_LABELS.items():
                    if not any(s in label for s in subs):
                        continue
                    if metric_key in ("debt_emprunts", "debt_concours") and "total" not in label:
                        continue
                    if metric_key == "equity" and "total" not in label:
                        continue
                    for col_key, val in values.items():
                        date_norm = str(col_key).replace('/', '.')
                        if not _is_date_col(date_norm):
                            continue
                        fv = _to_float(val)
                        if fv is None:
                            continue
                        if date_norm not in by_date:
                            by_date[date_norm] = {}
                            seen[date_norm]    = set()
                        if metric_key not in seen[date_norm]:
                            by_date[date_norm][metric_key] = fv
                            seen[date_norm].add(metric_key)

    periods = []
    for date_str, metrics in by_date.items():
        if not metrics.get("revenue"):
            continue
        e = metrics.pop("debt_emprunts", None)
        c = metrics.pop("debt_concours", None)
        if e is not None or c is not None:
            metrics["debt"] = abs(e or 0) + abs(c or 0)
        for k in ("raw_materials", "amortization"):
            if metrics.get(k) is not None:
                metrics[k] = abs(metrics[k])
        periods.append({"date": date_str, **metrics})

    periods.sort(key=lambda p: p["date"])
    return periods


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════

@router.get("/load/{report_id}")
async def load_periods_from_report(report_id: str):
    """
    Charge les périodes depuis le cache du rapport.
    Priorité :
      1. Périodes pré-extraites par pdfplumber (stockées dans pdf_financial["periods"])
      2. Extraction depuis raw_pages (données LLM)
      3. Message explicatif si rien trouvé
    """
    try:
        from services.report_cache import ReportCache
        cache = ReportCache.load_report_context(report_id)
    except Exception as e:
        raise HTTPException(500, detail=f"Erreur cache: {e}")
    if not cache:
        raise HTTPException(404, "Rapport introuvable")

    company = cache.get("company", {}) or {}
    pf      = cache.get("pdf_financial", {}) or {}

    # -- Source 1 : extraction depuis raw_pages du cache ----------
    periods = _extract_all_periods(pf)
    source  = "raw_pages_cache"

    # -- Source 2 : extraction depuis le fichier JSON externe ------
    if not periods or all(len(p) <= 2 for p in periods):
        try:
            import pathlib, json as _j
            safe = company.get("denomination","").replace(" ","_").replace("'","").upper()
            for candidate in [safe, safe.replace("-","_")]:
                json_path = pathlib.Path(f"database/output/{candidate}_extraction.json")
                if json_path.exists():
                    with open(json_path, encoding="utf-8") as _f:
                        extraction = _j.load(_f)
                    extracted = _extract_all_periods(extraction)
                    if extracted:
                        periods = extracted
                        source  = "extraction_json"
                    break
        except Exception:
            pass

    # Filter zero values from each period
    cleaned = []
    for p in periods:
        clean = {k: v for k, v in p.items() if k == "date" or (v is not None and v != 0)}
        cleaned.append(clean)
    periods = cleaned

    # Filter zero values from each period
    cleaned = []
    for p in periods:
        clean = {k: v for k, v in p.items() if k == "date" or (v is not None and v != 0)}
        cleaned.append(clean)
    periods = cleaned

    return {
        "report_id":     report_id,
        "company_name":  company.get("denomination", ""),
        "regime":        company.get("regime", ""),
        "secteur":       company.get("label_secteur", ""),
        "periods":       periods,
        "periods_found": len(periods),
        "source":        source if periods else "none",
        "note": (
            f"{len(periods)} période(s) extraite(s) depuis le cache."
            if periods else
            "Aucune période dans le cache — importez le PDF directement dans l'onglet Prévisions."
        ),
    }


@router.post("/extract-pdf")
async def extract_from_pdf(file: UploadFile = File(...)):
    """Upload un PDF CMF → extraction rapide sans LLM (~2 secondes)."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "PDF trop volumineux (max 50 MB)")
    try:
        pf = await run_in_threadpool(_fast_extract_periods_from_pdf, pdf_bytes)
    except ImportError:
        raise HTTPException(500, "pdfplumber non installé. Exécutez : pip install pdfplumber")
    except Exception as e:
        raise HTTPException(500, f"Erreur d'extraction: {e}")

    periods = _extract_all_periods(pf)
    return {
        "filename":      file.filename,
        "periods":       periods,
        "periods_found": len(periods),
        "note": (
            f"{len(periods)} période(s) extraite(s) depuis {file.filename}."
            if periods else
            "Aucune période trouvée — vérifiez le PDF."
        ),
    }


# ── Schémas + projection ──────────────────────────────────────────

class PeriodInput(BaseModel):
    date:                str
    revenue:             Optional[float] = None
    ebit:                Optional[float] = None
    raw_materials:       Optional[float] = None
    amortization:        Optional[float] = None
    net_result:          Optional[float] = None
    equity:              Optional[float] = None
    debt:                Optional[float] = None
    current_assets:      Optional[float] = None
    current_liabilities: Optional[float] = None


class ForecastRequest(BaseModel):
    company_name: str   = ""
    is_exporter:  bool  = False
    import_share: float = 0.6
    horizon:      int   = 5
    periods:      List[PeriodInput]


@router.post("/run")
async def run_forecast_endpoint(req: ForecastRequest, background_tasks: BackgroundTasks):
    """Lance la projection financière."""
    if len(req.periods) < 2:
        raise HTTPException(422, "Au moins 2 périodes sont requises.")
    horizon = min(max(req.horizon, 1), 10)
    try:
        result = run_forecast(
            periods=[p.dict() for p in req.periods],
            horizon=horizon,
            is_exporter=req.is_exporter,
            import_share=req.import_share,
        )
    except Exception as e:
        raise HTTPException(500, f"Erreur de projection: {e}")
    result["company"] = req.company_name
    background_tasks.add_task(log_forecast, result, req.company_name, horizon, req.is_exporter)
    return {"success": True, "result": result}