# backend/routes/stress_test.py
"""
API de Stress Testing.

Endpoints :
  GET  /api/stress-test/prefill/{report_id}  → pré-remplit les chiffres depuis un rapport caché
  POST /api/stress-test/run                  → lance le stress test complet
"""

import re
from pydantic import BaseModel
from typing import Optional, Dict, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from services.mlflow_tracker import log_stress_test, log_recommendations
from services.stress_test import FinancialInputs, run_full_stress_test

router = APIRouter(prefix="/api/stress-test", tags=["stress-test"])


# ══════════════════════════════════════════════════════════════════
# Schémas
# ══════════════════════════════════════════════════════════════════

class StressInputs(BaseModel):
    revenue: float
    ebit: Optional[float] = None  # Removed from UI
    raw_materials: Optional[float] = 0.0
    amortization: Optional[float] = 0.0
    interest: Optional[float] = 0.0
    equity: Optional[float] = 0.0
    debt: Optional[float] = 0.0
    current_assets: Optional[float] = 0.0
    current_liabilities: Optional[float] = 0.0
    is_exporter: bool = False
    tax_rate: float = 0.15
    import_share: float = 0.60
    export_share: float = 0.50
    principal_ratio: float = 0.10

    def dict(self, **kwargs):
        d = super().dict(**kwargs)
        for k, v in d.items():
            if v is None:
                d[k] = 0.0
        return d


class CustomShocks(BaseModel):
    revenue_pct: float = 0.0
    cost_pct: float = 0.0
    interest_pct: float = 0.0
    fx_pct: float = 0.0
    receivables_delay_pct: float = 0.0


class StressRunRequest(BaseModel):
    inputs: StressInputs
    custom_shocks: Optional[CustomShocks] = None
    report_id: Optional[str] = None   # si fourni, le résultat est sauvegardé


class RecommendRequest(BaseModel):
    inputs: StressInputs
    custom_shocks: Optional[CustomShocks] = None
    report_id: Optional[str] = None   # pour adapter les recommandations au cas


# ══════════════════════════════════════════════════════════════════
# Outils d'extraction
# ══════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode('ascii').lower().strip()

def _to_float(value) -> Optional[float]:
    """'84 015 979' / '(14 651 353)' / '<6 431 904>' / '-' → float ou None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("-", "—", "N/A", "n/a"):
        return None
    s = s.replace("\u202f", "").replace(" ", "").replace("\xa0", "")
    s = s.replace("(", "-").replace(")", "")     # négatifs entre parenthèses
    s = s.replace("<", "-").replace(">", "")      # négatifs entre chevrons
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date_key(k) -> Optional[tuple]:
    """'30.06.2025' → (2025, 6, 30) pour le tri."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", str(k))
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _latest_value(values: dict):
    """Choisit la valeur de la colonne de date la plus récente."""
    dated = []
    for k, v in values.items():
        dk = _parse_date_key(k)
        if dk and v is not None:
            dated.append((dk, v))
    if dated:
        dated.sort(reverse=True)
        return dated[0][1]
    for v in values.values():       # pas de date → première valeur non nulle
        if v is not None:
            return v
    return None


def _scan_rows(pf: dict) -> Dict[str, float]:
    """
    Parcourt raw_pages[].tables[].rows[] et construit
    {label_minuscule: valeur_la_plus_recente_en_float}.
    Gere Format A : {"label":"..","values":{}} ET Format B : {"Label":[val1,val2]}
    """
    lookup: Dict[str, float] = {}
    if not isinstance(pf, dict):
        return lookup

    def _first_num(arr):
        if isinstance(arr, (int, float)):
            return _to_float(arr)
        if isinstance(arr, list):
            for v in arr:
                if isinstance(v, (int, float)):
                    return _to_float(v)
                if isinstance(v, str):
                    f = _to_float(v)
                    if f is not None and abs(f) >= 100:
                        return f
        return None

    for page in (pf.get("raw_pages", []) or []):
        if not isinstance(page, dict): continue
        for table in (page.get("tables", []) or []):
            if not isinstance(table, dict): continue
            headers = table.get("headers", []) or []
            for row in (table.get("rows", []) or []):
                # Handle list rows: ["LABEL", val1, val2, ...]
                if isinstance(row, list) and len(row) >= 2:
                    label = _norm(str(row[0]))
                    if label and len(label) > 2:
                        for v in row[1:]:
                            val = _to_float(str(v).replace(" ", "").replace(",", ".")) if isinstance(v, str) else _to_float(v)
                            if val is not None and abs(val) >= 100:
                                if label not in lookup:
                                    lookup[label] = val
                                break
                    continue
                if not isinstance(row, dict): continue
                if "label" in row and "values" in row:
                    label = _norm(row.get("label",""))
                    values = row.get("values", {})
                    if label and isinstance(values, dict):
                        val = _to_float(_latest_value(values))
                        if val is not None and label not in lookup:
                            lookup[label] = val
                else:
                    for key, arr in row.items():
                        label = _norm(key)
                        if not label: continue
                        val = _first_num(arr)
                        if val is not None and label not in lookup:
                            lookup[label] = val
    for page in (pf.get("raw_pages", []) or []):
        if not isinstance(page, dict): continue
        if page.get("page_type") not in ("parse_error", "other"): continue
        notes = str(page.get("notes", "") or "")
        if not notes: continue
        note_lines = [l.strip() for l in notes.split("\n") if l.strip()]
        for idx, nline in enumerate(note_lines):
            lbl = _norm(nline)
            if not lbl or len(lbl) < 3: continue
            for jdx in range(idx+1, min(idx+4, len(note_lines))):
                val = _to_float(note_lines[jdx].replace(" ", "").replace(",", "."))
                if val is not None and abs(val) >= 100:
                    if lbl not in lookup:
                        lookup[lbl] = val
                    break
    return lookup


def _match(lookup: Dict[str, float], *subs: str, prefer_total: bool = True) -> Optional[float]:
    """
    Renvoie la valeur de la premiere ligne dont le label contient un des fragments.
    Ignore les valeurs < 100 (references de notes comptables ex: 5.1, 5.7).
    """
    cands: List = []
    for sub in subs:
        sub = _norm(sub)
        for label, val in lookup.items():
            if sub in label and abs(val) >= 100:
                cands.append((label, val))
    if not cands:
        return None
    if prefer_total:
        totals = [(l, v) for l, v in cands if "total" in l]
        if totals:
            return totals[0][1]
    return cands[0][1]

def _extract_financials(cache: dict) -> dict:
    """
    Extraction partagée des chiffres financiers depuis un rapport caché.
    Utilisée par /prefill ET /overview.
    """
    company = cache.get("company", {}) or {}
    pf = cache.get("pdf_financial", {}) or {}

    cpc = pf.get("cpc", {}) if isinstance(pf, dict) else {}
    struct = {
        "revenue":       _to_float(cpc.get("chiffre_affaires")),
        "ebit":          _to_float(cpc.get("resultat_exploitation")),
        "raw_materials": _to_float(cpc.get("achats_consommes")),
    }

    try:
        lookup = _scan_rows(pf)
    except Exception:
        lookup = {}

    revenue            = struct["revenue"]       or _match(lookup, "chiffre d'affaires", "chiffre d affaires", "revenus", "produits d'exploitation", "total produits")
    raw_materials      = struct["raw_materials"] or _match(lookup, "achats consommés", "achats consommes")
    amortization       = _match(lookup, "dot aux amortissements", "dotations aux amortissements", "dotation aux amortissements", "amortissements")
    interest           = _match(lookup, "intérêts", "interets", "charges financières nettes", "charges financieres nettes")
    equity             = _match(lookup, "total des capitaux propres - part du groupe", "total des capitaux propres", "capitaux propres")
    emprunts           = _match(lookup, "total des emprunts", "emprunts")
    concours           = _match(lookup, "total des concours bancaires", "concours bancaires")
    current_assets     = _match(lookup, "total des actifs courants", "actifs courants")
    current_liabilities= _match(lookup, "total des passifs courants", "passifs courants")

    if raw_materials is not None: raw_materials = abs(raw_materials)
    if amortization  is not None: amortization  = abs(amortization)
    if interest      is not None: interest      = abs(interest)

    debt = None
    if emprunts is not None or concours is not None:
        debt = abs(emprunts or 0.0) + abs(concours or 0.0)

    regime = str(company.get("regime", "")).lower()
    is_exporter = ("totalement exportatrice" in regime) and ("non totalement" not in regime)

    prefill = {
        "revenue": revenue, "raw_materials": raw_materials,
        "amortization": amortization, "interest": interest, "equity": equity,
        "debt": debt, "current_assets": current_assets,
        "current_liabilities": current_liabilities, "is_exporter": is_exporter,
    }
    fields_found = sum(1 for v in prefill.values() if v is not None and v is not False)
    return {"prefill": prefill, "fields_found": fields_found, "rows_scanned": len(lookup)}


def _stringify(section) -> str:
    if isinstance(section, str):
        return section
    if isinstance(section, dict):
        out = []
        for v in section.values():
            if isinstance(v, str):
                out.append(v)
        return " ".join(out)
    return ""


def _extract_report_verdict(cache: dict) -> Optional[dict]:
    """
    Cherche une section de synthèse / conclusion / avis / facteurs de risque
    dans le rapport généré, pour afficher le « verdict » qualitatif.
    """
    report = cache.get("generated_report", {}) or {}
    # priorité aux sections de synthèse/avis
    for key in report:
        kl = str(key).lower()
        if any(t in kl for t in ("synth", "conclu", "avis", "verdict")):
            txt = _stringify(report[key]).strip()
            if txt:
                return {"section": key, "text": txt[:800]}
    # repli : facteurs de risque
    for key in report:
        if "risque" in str(key).lower():
            txt = _stringify(report[key]).strip()
            if txt:
                return {"section": key, "text": txt[:800]}
    return None


# ══════════════════════════════════════════════════════════════════
# Persistance des stress tests (table stress_tests)
# ══════════════════════════════════════════════════════════════════

def _save_stress(report_id: str, inputs_dict: dict, result: dict):
    import json
    from Database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO stress_tests (report_id, result, inputs, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (report_id) DO UPDATE
              SET result = EXCLUDED.result,
                  inputs = EXCLUDED.inputs,
                  updated_at = NOW()
        """, (report_id, json.dumps(result), json.dumps(inputs_dict)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        # on n'échoue pas le run pour un problème de sauvegarde
        print(f"[stress] sauvegarde échouée: {e}")
    finally:
        cur.close()
        conn.close()


def _load_stress(report_id: str) -> Optional[dict]:
    import json
    from Database import get_conn
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT result, inputs, updated_at FROM stress_tests WHERE report_id = %s", (report_id,))
        row = cur.fetchone()
        if not row:
            return None
        result = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        inputs = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        return {
            "result": result,
            "inputs": inputs,
            "updated_at": row[2].isoformat() if row[2] else None,
        }
    finally:
        cur.close()
        conn.close()


# ══════════════════════════════════════════════════════════════════
# Pré-remplissage depuis un rapport caché
# ══════════════════════════════════════════════════════════════════

@router.get("/prefill/{report_id}")
async def prefill_from_report(report_id: str):
    """
    Extrait au mieux les chiffres financiers :
      1) d'abord depuis le résumé structuré (cpc) s'il est rempli,
      2) sinon en scannant les tableaux bruts (raw_pages).
    Ne échoue jamais en dur ; le frontend laisse compléter/corriger.
    """
    try:
        from services.report_cache import ReportCache
        cache = ReportCache.load_report_context(report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chargement rapport : {e}")

    if not cache:
        raise HTTPException(status_code=404, detail="Rapport introuvable")

    company = cache.get("company", {}) or {}
    pf = cache.get("pdf_financial", {}) or {}

    # ── 1) résumé structuré (souvent null, mais on essaie) ────────
    cpc = pf.get("cpc", {}) if isinstance(pf, dict) else {}
    struct = {
        "revenue":       _to_float(cpc.get("chiffre_affaires")),
        "ebit":          _to_float(cpc.get("resultat_exploitation")),
        "raw_materials": _to_float(cpc.get("achats_consommes")),
        "resultat_net":  _to_float(cpc.get("resultat_net")),
    }

    # ── 2) scan des tableaux bruts ────────────────────────────────
    try:
        lookup = _scan_rows(pf)
    except Exception:
        lookup = {}

    revenue            = struct["revenue"]       or _match(lookup, "chiffre d'affaires", "chiffre d affaires", "revenus", "produits d'exploitation", "total produits")
    raw_materials      = struct["raw_materials"] or _match(lookup, "achats consommés", "achats consommes")
    amortization       = _match(lookup, "dot aux amortissements", "dotations aux amortissements", "dotation aux amortissements", "amortissements")
    interest           = _match(lookup, "intérêts", "interets", "charges financières nettes", "charges financieres nettes")
    equity             = _match(lookup, "total des capitaux propres - part du groupe", "total des capitaux propres", "capitaux propres")
    emprunts           = _match(lookup, "total des emprunts", "emprunts")
    concours           = _match(lookup, "total des concours bancaires", "concours bancaires")
    current_assets     = _match(lookup, "total des actifs courants", "actifs courants")
    current_liabilities= _match(lookup, "total des passifs courants", "passifs courants")

    # Les charges sont souvent stockées en négatif (<...> ou (...)).
    # Le moteur attend des magnitudes POSITIVES pour ces postes de coûts.
    for _name in ("raw_materials", "amortization", "interest"):
        _v = locals()[_name]
        if _v is not None:
            if _name == "raw_materials":
                raw_materials = abs(_v)
            elif _name == "amortization":
                amortization = abs(_v)
            elif _name == "interest":
                interest = abs(_v)

    # dette financière = emprunts + concours bancaires (si trouvés)
    debt = None
    if emprunts is not None or concours is not None:
        debt = abs(emprunts or 0.0) + abs(concours or 0.0)

    # Régime : « totalement exportatrice » est un sous-texte de
    # « non totalement exportatrice » → exclure explicitement le « non ».
    regime = str(company.get("regime", "")).lower()
    is_exporter = ("totalement exportatrice" in regime) and ("non totalement" not in regime)

    prefill = {
        "revenue": revenue,

        "raw_materials": raw_materials,
        "amortization": amortization,
        "interest": interest,
        "equity": equity,
        "debt": debt,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "is_exporter": is_exporter,
    }

    found = sum(1 for k, v in prefill.items() if k != "is_exporter" and v is not None)

    # ── Fallback: extraction JSON (raw_pages scan) ────────────────
    try:
        import pathlib, json as _j
        safe_name = company.get("denomination","").replace(" ","_").replace("'","").upper()
        for candidate in [safe_name, safe_name.replace("-","_"), safe_name.replace(" ","_")]:
            json_path = pathlib.Path(f"database/output/{candidate}_extraction.json")
            if json_path.exists():
                with open(json_path, encoding="utf-8") as _f:
                    extraction = _j.load(_f)
                # Scan raw_pages from extraction JSON
                ext_lookup = _scan_rows(extraction)
                # Fill missing fields from extraction JSON
                if not prefill["revenue"]:
                    prefill["revenue"] = _match(ext_lookup, "chiffre d affaires", "revenus", "produits d exploitation", "total produits")
                if not prefill["equity"]:
                    prefill["equity"] = _match(ext_lookup, "total des capitaux propres", "capitaux propres")
                if not prefill["current_assets"]:
                    prefill["current_assets"] = _match(ext_lookup, "total des actifs courants", "actifs courants")
                if not prefill["current_liabilities"]:
                    prefill["current_liabilities"] = _match(ext_lookup, "total des passifs courants", "passifs courants")
                if not prefill["amortization"]:
                    prefill["amortization"] = _match(ext_lookup, "dotations aux amortissements", "amortissements")
                    if prefill["amortization"]: prefill["amortization"] = abs(prefill["amortization"])
                if not prefill["interest"]:
                    prefill["interest"] = _match(ext_lookup, "interets", "charges financieres", "charges d interets")
                    if prefill["interest"]: prefill["interest"] = abs(prefill["interest"])
                if not prefill["raw_materials"]:
                    prefill["raw_materials"] = _match(ext_lookup, "achats consommes", "matieres premieres", "matieres consommees")
                if not prefill["debt"]:
                    emp = _match(ext_lookup, "emprunts")
                    con = _match(ext_lookup, "concours bancaires")
                    if emp or con:
                        prefill["debt"] = abs(emp or 0) + abs(con or 0)
                # Also try periods
                periods = extraction.get("periods", [])
                if periods:
                    latest = sorted(periods, key=lambda p: p.get("date",""))[-1]
                    for field in ["revenue","equity","current_assets","current_liabilities","amortization","interest"]:
                        if not prefill[field]: prefill[field] = latest.get(field)
                    if not prefill["debt"] and latest.get("total_debt"):
                        prefill["debt"] = latest.get("total_debt")
                found = sum(1 for k,v in prefill.items() if k != "is_exporter" and v is not None)
                break
    except Exception:
        pass
    return {
        "report_id": report_id,
        "company_name": company.get("denomination", ""),
        "regime": company.get("regime", ""),
        "prefill": prefill,
        "fields_found": found,
        "fields_total": 8,
        "rows_scanned": len(lookup),
        "note": "Vérifiez et complétez les champs manquants avant de lancer le test."
    }


# ══════════════════════════════════════════════════════════════════
# Lancement du stress test
# ══════════════════════════════════════════════════════════════════
@router.post("/run")
async def run_stress_test(req: StressRunRequest, background_tasks: BackgroundTasks):
    """Lance le stress test complet : base + 3 scénarios nommés + test inversé."""
    try:
        base = FinancialInputs(**req.inputs.dict())
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Entrées invalides : {e}")

    if base.revenue <= 0:
        raise HTTPException(status_code=422, detail="Le chiffre d'affaires doit être positif.")
    if base.interest < 0:
        raise HTTPException(status_code=422, detail="Les intérêts ne peuvent être négatifs.")

    custom = req.custom_shocks.dict() if req.custom_shocks else None
    if custom and not any(abs(v) > 0 for v in custom.values()):
        custom = None

    try:
        result = run_full_stress_test(base, custom_shocks=custom)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul : {e}")

    if req.report_id:
        _save_stress(req.report_id, req.inputs.dict(), result)

    # ── MLflow tracking (non-bloquant) ────────────────────────────
    company_name = ""
    if req.report_id:
        try:
            from services.report_cache import ReportCache
            cache = ReportCache.load_report_context(req.report_id)
            company_name = (cache.get("company", {}) or {}).get("denomination", "")
        except Exception:
            pass

    background_tasks.add_task(
        log_stress_test,
        result,
        req.inputs.dict(),
        company_name,
        req.report_id or ""
    )
    # ─────────────────────────────────────────────────────────────

    import math, json as _json
    def _sanitize(obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj
    result = _sanitize(result)
    return {"success": True, "result": result, "saved": bool(req.report_id)}

# ══════════════════════════════════════════════════════════════════
# Recommandations (stress test + rapport)
# ══════════════════════════════════════════════════════════════════

@router.post("/recommend")
async def recommend(req: RecommendRequest):
    """
    Lance le stress test puis génère des recommandations stratégiques
    (côté entreprise), adaptées via le contexte du rapport si report_id fourni.
    """
    from services.recommendations import build_recommendations, build_report_context

    try:
        base = FinancialInputs(**req.inputs.dict())
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Entrées invalides : {e}")

    if base.revenue <= 0:
        raise HTTPException(status_code=422, detail="Le chiffre d'affaires doit être positif.")

    custom = req.custom_shocks.dict() if req.custom_shocks else None
    if custom and not any(abs(v) > 0 for v in custom.values()):
        custom = None

    try:
        result = run_full_stress_test(base, custom_shocks=custom)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul : {e}")

    # Contexte du rapport (optionnel) pour adapter les recommandations
    report_context = None
    if req.report_id:
        try:
            from services.report_cache import ReportCache
            cache = ReportCache.load_report_context(req.report_id)
            if cache:
                report_context = build_report_context(cache)
        except Exception:
            report_context = None  # on continue en mode règles

    recs = build_recommendations(result, report_context, use_llm=True)

    return {
        "success": True,
        "stress_result": result,
        "recommendations": recs,
    }


# ══════════════════════════════════════════════════════════════════
# Vue d'ensemble d'un rapport (pour la page Stratégies)
# ══════════════════════════════════════════════════════════════════

@router.get("/overview/{report_id}")
async def report_overview(report_id: str):
    """
    Renvoie tout ce dont la page Stratégies a besoin pour un rapport :
      - infos entreprise + régime
      - verdict qualitatif extrait du rapport
      - chiffres financiers pré-remplis (éditables côté frontend)
    """
    try:
        from services.report_cache import ReportCache
        cache = ReportCache.load_report_context(report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chargement rapport : {e}")
    if not cache:
        raise HTTPException(status_code=404, detail="Rapport introuvable")

    company = cache.get("company", {}) or {}
    try:
        fin = _extract_financials(cache) or {"prefill": {}, "fields_found": 0, "rows_scanned": 0}
    except Exception:
        fin = {"prefill": {}, "fields_found": 0, "rows_scanned": 0}

    verdict = _extract_report_verdict(cache)

    return {
        "report_id": report_id,
        "company_name": company.get("denomination", ""),
        "regime": company.get("regime", ""),
        "secteur": company.get("label_secteur", ""),
        "gouvernorat": company.get("gouvernorat", ""),
        "report_verdict": verdict,            # peut être null
        "prefill": fin["prefill"],
        "fields_found": fin["fields_found"],
        "fields_total": 8,
        "rows_scanned": fin["rows_scanned"],
    }


# ══════════════════════════════════════════════════════════════════
# Stress test sauvegardé + recommandations à partir du sauvegardé
# ══════════════════════════════════════════════════════════════════

@router.get("/saved/{report_id}")
async def get_saved_stress(report_id: str):
    """Renvoie le dernier stress test sauvegardé pour ce rapport (ou saved=false)."""
    try:
        saved = _load_stress(report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture: {e}")
    if not saved:
        return {"saved": False}
    return {
        "saved": True,
        "result": saved["result"],
        "updated_at": saved["updated_at"],
    }


@router.post("/recommend-saved/{report_id}")
async def recommend_from_saved(report_id: str):
    """
    Génère des recommandations à partir du stress test DÉJÀ sauvegardé
    pour ce rapport + le contexte du rapport. Ne recalcule rien.
    """
    from services.recommendations import build_recommendations, build_report_context

    saved = _load_stress(report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Aucun stress test sauvegardé pour ce rapport.")

    report_context = None
    try:
        from services.report_cache import ReportCache
        cache = ReportCache.load_report_context(report_id)
        if cache:
            report_context = build_report_context(cache)
    except Exception:
        report_context = None

    recs = build_recommendations(saved["result"], report_context, use_llm=True)
    return {
        "success": True,
        "stress_result": saved["result"],
        "recommendations": recs,
        "updated_at": saved["updated_at"],
    }