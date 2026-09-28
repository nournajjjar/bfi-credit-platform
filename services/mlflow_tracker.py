# backend/services/mlflow_tracker.py
"""
Service de tracking MLflow centralisé — v2.
Ajoute :
  - Journalisation des prompts (artifacts texte)
  - Métriques de fidélité / hallucination (faithfulness)
    • Heuristique simple  : chevauchement lexical (instantané)
    • Juge LLM (optionnel) : second appel LLM pour scorer la réponse

Expériences :
  BFI · Prévisions Financières
  BFI · Stress Test
  BFI · Recommandations
  BFI · Génération Rapport
  BFI · Qualité des Réponses   ← nouveau (prompts + hallucination)
"""

import json
import re
import tempfile
import os
from datetime import datetime
from typing import Optional, List

from core.logger import setup_logger as get_logger

logger = get_logger(__name__)

MLFLOW_URI = "http://mlflow:5000"
EXP_FORECAST = "BFI · Prévisions Financières"
EXP_STRESS   = "BFI · Stress Test"
EXP_RECOMMEND= "BFI · Recommandations"
EXP_REPORT   = "BFI · Génération Rapport"
EXP_QUALITY  = "BFI · Qualité des Réponses"   # prompts + hallucination

_STOP_WORDS_FR = {
    'le','la','les','de','du','des','un','une','et','ou','en','est','sont',
    'a','au','aux','ce','se','sa','son','ses','par','sur','dans','qui','que',
    'il','elle','ils','elles','nous','vous','on','y','à','être','avoir','pas',
    'plus','très','bien','tout','même','aussi','comme','mais','car','si','donc'
}


# ══════════════════════════════════════════════════════════════════
# Utilitaires internes
# ══════════════════════════════════════════════════════════════════

def _get_or_create_experiment(mlflow, name: str) -> str:
    exp = mlflow.get_experiment_by_name(name)
    return exp.experiment_id if exp else mlflow.create_experiment(name)


def _safe_float(v, default=0.0):
    try: return float(v) if v is not None else default
    except: return default


def _log_artifact_dict(mlflow, data: dict, filename: str):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        tmp = f.name
    try: mlflow.log_artifact(tmp, artifact_path='results')
    finally: os.unlink(tmp)


def _log_artifact_text(mlflow, text: str, filename: str, folder: str = 'prompts'):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text); tmp = f.name
    try: mlflow.log_artifact(tmp, artifact_path=folder)
    finally: os.unlink(tmp)


# ══════════════════════════════════════════════════════════════════
# MÉTRIQUES DE FIDÉLITÉ (hallucination)
# ══════════════════════════════════════════════════════════════════

def compute_faithfulness_heuristic(context: str, response: str) -> float:
    """
    Heuristique rapide (sans LLM) :
    Ratio de phrases de la réponse dont les mots-clés proviennent du contexte.
    Score : 0.0 = tout halluciné · 1.0 = entièrement fondé
    """
    if not context or not response:
        return 0.0

    ctx_words = set(re.findall(r'\b\w{4,}\b', context.lower())) - _STOP_WORDS_FR
    sentences  = [s.strip() for s in re.split(r'[.!?]', response) if len(s.strip()) > 10]

    if not sentences:
        return 0.0

    grounded = 0
    for sent in sentences:
        sent_words = set(re.findall(r'\b\w{4,}\b', sent.lower())) - _STOP_WORDS_FR
        overlap    = sent_words & ctx_words
        if len(overlap) >= 2:   # au moins 2 mots-clés communs → fondé
            grounded += 1

    return round(grounded / len(sentences), 3)


def compute_faithfulness_llm(context: str, response: str,
                              client=None, model: str = "") -> dict:
    """
    Juge LLM : évalue la fidélité de la réponse par rapport au contexte.
    Retourne {"score": 0.X, "hallucinations": ["phrase..."], "verdict": "..."}
    """
    if client is None or not model:
        return {"score": None, "hallucinations": [], "verdict": "juge LLM non disponible"}

    prompt = f"""Tu es un évaluateur de qualité de réponses IA. Évalue si la réponse suivante est fidèle au contexte fourni (sans hallucination).

CONTEXTE (source de vérité) :
{context[:2500]}

RÉPONSE À ÉVALUER :
{response}

Réponds UNIQUEMENT en JSON :
{{
  "score": <0.0 à 1.0>,
  "hallucinations": ["<phrase ou affirmation non fondée>", ...],
  "verdict": "<Fidèle|Partiellement fidèle|Hallucination>"
}}

Score : 1.0 = entièrement fondé · 0.0 = entièrement halluciné"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=300, timeout=20
        )
        text = resp.choices[0].message.content
        m    = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        logger.warning(f"[mlflow] Juge LLM échoué : {e}")

    return {"score": None, "hallucinations": [], "verdict": "erreur juge"}


# ══════════════════════════════════════════════════════════════════
# LOG D'UN APPEL LLM (prompt + réponse + fidélité)
# ══════════════════════════════════════════════════════════════════

def log_llm_call(run_name: str, prompt: str, response: str,
                 context: str = "", metadata: dict = None,
                 use_llm_judge: bool = False):
    """
    Enregistre un appel LLM individuel :
      - Prompt et réponse comme artifacts texte
      - Score de fidélité (heuristique + optionnellement juge LLM)
    Utiliser via BackgroundTasks pour ne pas bloquer la réponse API.
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp_id = _get_or_create_experiment(mlflow, EXP_QUALITY)

        with mlflow.start_run(experiment_id=exp_id, run_name=run_name):
            # ── Artefacts texte ────────────────────────────────────
            ts = datetime.now().strftime('%H%M%S')
            _log_artifact_text(mlflow,
                f"=== PROMPT ===\n{prompt}\n\n=== RÉPONSE ===\n{response}",
                f"llm_call_{ts}.txt", folder='prompts')

            if context:
                _log_artifact_text(mlflow, context, f"context_{ts}.txt", folder='contexts')

            # ── Fidélité heuristique ───────────────────────────────
            faith_h = compute_faithfulness_heuristic(context, response) if context else None

            # ── Juge LLM (optionnel) ───────────────────────────────
            faith_llm = None
            hallucinations = []
            verdict = "—"
            if use_llm_judge and context:
                try:
                    from core.openai_client import get_openai_client
                    from core.config import OPENAI_MODEL
                    result = compute_faithfulness_llm(context, response, get_openai_client(), OPENAI_MODEL)
                    faith_llm     = result.get("score")
                    hallucinations= result.get("hallucinations", [])
                    verdict       = result.get("verdict", "—")
                except Exception as e:
                    logger.warning(f"[mlflow] Juge LLM indisponible : {e}")

            # ── Métriques ──────────────────────────────────────────
            metrics = {}
            if faith_h is not None:  metrics["faithfulness_heuristic"] = faith_h
            if faith_llm is not None: metrics["faithfulness_llm_judge"] = _safe_float(faith_llm)
            metrics["prompt_length"]   = len(prompt)
            metrics["response_length"] = len(response)
            metrics["n_hallucinations"]= len(hallucinations)
            mlflow.log_metrics(metrics)

            # ── Paramètres ─────────────────────────────────────────
            params = {"run_name": run_name, "verdict": verdict}
            if metadata: params.update({k: str(v)[:250] for k, v in metadata.items()})
            mlflow.log_params(params)

            # ── Tags ───────────────────────────────────────────────
            mlflow.set_tags({
                "verdict":  verdict,
                "module":   metadata.get("module", "llm") if metadata else "llm",
            })

        logger.info(f"[mlflow] LLM call logged — faithfulness={faith_h}")

    except Exception as e:
        logger.warning(f"[mlflow] log_llm_call ignoré : {e}")


# ══════════════════════════════════════════════════════════════════
# FONCTIONS EXISTANTES — enrichies avec prompts + fidélité
# ══════════════════════════════════════════════════════════════════

def log_forecast(forecast_result: dict, company_name: str = "",
                 horizon: int = 5, is_exporter: bool = False):
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp_id  = _get_or_create_experiment(mlflow, EXP_FORECAST)
        stats   = forecast_result.get("model_stats", {})
        summary = forecast_result.get("summary", {})
        hist    = forecast_result.get("historical", [])
        proj    = forecast_result.get("projected", [])
        run_name= f"{company_name or 'Inconnu'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        with mlflow.start_run(experiment_id=exp_id, run_name=run_name):
            mlflow.log_params({
                "company":           company_name or "—",
                "horizon_years":     horizon,
                "n_periods":         stats.get("n_points", len(hist)),
                "model":             stats.get("model", "OLS"),
                "data_quality":      stats.get("data_quality", "—"),
                "is_exporter":       str(is_exporter),
                "last_hist_year":    summary.get("last_historical_year", "—"),
                "last_proj_year":    summary.get("last_projected_year", "—"),
                "var_cost_ratio_pct":forecast_result.get("var_cost_ratio_pct", 0),
            })
            metrics = {}
            if stats.get("r2") is not None: metrics["r_squared"] = _safe_float(stats["r2"])
            if stats.get("cagr_pct") is not None: metrics["cagr_pct"] = _safe_float(stats["cagr_pct"])
            metrics["n_data_points"] = int(stats.get("n_points", 0))
            if proj:
                y1 = proj[0]; last = proj[-1]
                metrics.update({
                    "proj_y1_revenue_M":  _safe_float(y1.get("revenue",0))/1e6,
                    "proj_y1_icr":        _safe_float(y1.get("icr"), 0),
                    "proj_y1_net_margin": _safe_float(y1.get("net_margin"), 0),
                    "proj_last_revenue_M":_safe_float(last.get("revenue",0))/1e6,
                    "proj_last_icr":      _safe_float(last.get("icr"), 0),
                })
                rec = last.get("stressed",{}).get("recession",{})
                inf = last.get("stressed",{}).get("inflation",{})
                if rec.get("icr") is not None: metrics["proj_last_icr_recession"] = _safe_float(rec["icr"])
                if inf.get("icr") is not None: metrics["proj_last_icr_inflation"] = _safe_float(inf["icr"])
            mlflow.log_metrics({k:v for k,v in metrics.items() if v is not None})
            mlflow.set_tags({"warning": stats.get("warning") or "aucun", "module": "forecasting"})
            _log_artifact_dict(mlflow, forecast_result, "forecast_result.json")
        logger.info(f"[mlflow] Forecast logged — {company_name}")
    except Exception as e:
        logger.warning(f"[mlflow] Forecast tracking ignoré : {e}")


def log_stress_test(stress_result: dict, inputs: dict,
                    company_name: str = "", report_id: str = ""):
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp_id  = _get_or_create_experiment(mlflow, EXP_STRESS)
        base    = stress_result.get("base_ratios", {})
        rev     = stress_result.get("reverse", {})
        scens   = stress_result.get("scenarios", [])
        verdict = stress_result.get("base_verdict", {})
        run_name= f"{company_name or 'Inconnu'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        with mlflow.start_run(experiment_id=exp_id, run_name=run_name):
            rev_m = lambda k: round(_safe_float(inputs.get(k),0)/1e6, 2)
            mlflow.log_params({
                "company":      company_name or "—", "report_id": report_id or "—",
                "revenue_M":    rev_m("revenue"), "ebit_M":     rev_m("ebit"),
                "interest_M":   rev_m("interest"), "equity_M":   rev_m("equity"),
                "debt_M":       rev_m("debt"), "is_exporter": str(inputs.get("is_exporter",False)),
                "import_share": inputs.get("import_share",0.6),
            })
            metrics = {
                "base_icr":           _safe_float(base.get("interest_coverage")),
                "base_net_margin":    _safe_float(base.get("net_margin")),
                "base_current_ratio": _safe_float(base.get("current_ratio")),
                "base_dscr":          _safe_float(base.get("dscr_approx")),
            }
            bp = rev.get("revenue_drop_icr",{}).get("value")
            if bp is not None: metrics["reverse_breakpoint_pct"] = _safe_float(bp)
            for s in scens:
                icr = s.get("ratios",{}).get("interest_coverage")
                if icr is not None: metrics[f"icr_{s.get('key','')}"] = _safe_float(icr)
            mlflow.log_metrics({k:v for k,v in metrics.items() if v is not None})
            tags = {"base_verdict": verdict.get("status","—"), "module": "stress_test"}
            for s in scens: tags[f"verdict_{s.get('key','')}"] = s.get("verdict",{}).get("status","—")
            mlflow.set_tags(tags)
            _log_artifact_dict(mlflow, stress_result, "stress_result.json")
        logger.info(f"[mlflow] Stress test logged — {company_name}")
    except Exception as e:
        logger.warning(f"[mlflow] Stress test tracking ignoré : {e}")


def log_recommendations(recs: dict, company_name: str = "", report_id: str = ""):
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp_id    = _get_or_create_experiment(mlflow, EXP_RECOMMEND)
        recs_list = recs.get("recommendations", [])
        run_name  = f"{company_name or 'Inconnu'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        with mlflow.start_run(experiment_id=exp_id, run_name=run_name):
            mlflow.log_params({"company": company_name or "—", "report_id": report_id or "—", "method": recs.get("method","—")})
            mlflow.log_metrics({
                "n_recommendations": len(recs_list),
                "n_high_priority":   sum(1 for r in recs_list if str(r.get("priorite","")).lower()=="élevée"),
                "n_medium_priority": sum(1 for r in recs_list if str(r.get("priorite","")).lower()=="moyenne"),
                "n_low_priority":    sum(1 for r in recs_list if str(r.get("priorite","")).lower()=="faible"),
                "has_recommendations": int(recs.get("has_recommendations",False)),
            })
            categories = list({r.get("categorie","") for r in recs_list if r.get("categorie")})
            mlflow.set_tags({"levers": ", ".join(categories) or "aucun", "module": "recommendations"})
            _log_artifact_dict(mlflow, recs, "recommendations.json")
        logger.info(f"[mlflow] Recommandations logged — {company_name}")
    except Exception as e:
        logger.warning(f"[mlflow] Recommandations tracking ignoré : {e}")


def log_report_generation(company_name: str, report_id: str,
                          model_name: str, n_pdfs: int, n_sections: int,
                          source_table: str, n_rag_chunks: int, regime: str,
                          qa_answers: Optional[dict] = None,
                          prompts: Optional[List[dict]] = None,
                          faithfulness_scores: Optional[List[float]] = None):
    """
    prompts          : liste de {"section": str, "prompt": str, "response": str}
    faithfulness_scores : liste de scores (un par section générée)
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp_id   = _get_or_create_experiment(mlflow, EXP_REPORT)
        run_name = f"{company_name or 'Inconnu'} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        with mlflow.start_run(experiment_id=exp_id, run_name=run_name):
            mlflow.log_params({
                "company":      company_name or "—", "report_id": report_id or "—",
                "llm_model":    model_name or "—",  "n_pdfs":    n_pdfs,
                "n_sections":   n_sections,          "source_table": source_table or "—",
                "regime":       regime or "—",
            })
            metrics = {"n_rag_chunks": n_rag_chunks}
            if qa_answers and isinstance(qa_answers, dict):
                answers = qa_answers.get("answers", []) or []
                metrics.update({
                    "qa_n_high":   sum(1 for a in answers if a.get("confidence")=="élevé"),
                    "qa_n_medium": sum(1 for a in answers if a.get("confidence")=="moyen"),
                    "qa_n_low":    sum(1 for a in answers if a.get("confidence")=="faible"),
                    "qa_total":    len(answers),
                 })

            # ── Métriques de fidélité ──────────────────────────────
            if faithfulness_scores:
                valid = [s for s in faithfulness_scores if s is not None]
                if valid:
                    metrics["faithfulness_mean"] = round(sum(valid)/len(valid), 3)
                    metrics["faithfulness_min"]  = round(min(valid), 3)
                    metrics["faithfulness_max"]  = round(max(valid), 3)
                    metrics["n_sections_scored"] = len(valid)
            mlflow.log_metrics(metrics)
            mlflow.set_tags({"has_pdf": str(n_pdfs>0), "module": "report_generation"})

            # ── Journalisation des prompts ─────────────────────────
            if prompts:
                for i, p in enumerate(prompts):
                    section = p.get("section", f"section_{i}")
                    text = (
                        f"=== SECTION : {section} ===\n\n"
                        f"--- PROMPT ---\n{p.get('prompt','')}\n\n"
                        f"--- RÉPONSE ---\n{p.get('response','')}\n"
                    )
                    _log_artifact_text(mlflow, text, f"prompt_{i:02d}_{section}.txt", folder='prompts')

        logger.info(f"[mlflow] Rapport logged — {company_name} | fidélité={metrics.get('faithfulness_mean','—')}")
    except Exception as e:
        logger.warning(f"[mlflow] Rapport tracking ignoré : {e}")


def log_qa_interaction(report_id: str, company_name: str,
                       question: str, answer: str, context: str,
                       section_id: Optional[str] = None,
                       use_llm_judge: bool = False):
    """
    Log une interaction Q&A (chatbot de révision) avec métriques de fidélité.
    """
    run_name = f"Q&A · {company_name or report_id[:8]} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    log_llm_call(
        run_name=run_name,
        prompt=question,
        response=answer,
        context=context,
        metadata={
            "module":     "chatbot_qa",
            "report_id":  report_id,
            "company":    company_name,
            "section_id": section_id or "—",
        },
        use_llm_judge=use_llm_judge,
    )
