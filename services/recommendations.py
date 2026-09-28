# backend/services/recommendations.py
"""
Moteur de recommandations stratégiques (côté entreprise) — version enrichie.
"""

import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from core.logger import setup_logger as get_logger

logger = get_logger(__name__)

LLM_TIMEOUT_SECONDS = 60

_STATUS_RANK  = {"break": 0, "warning": 1, "ok": 2}
_PRIORITY_LABEL = {1: "élevée", 2: "moyenne", 3: "faible"}


# ══════════════════════════════════════════════════════════════════
# 1. LEVIERS
# ══════════════════════════════════════════════════════════════════

@dataclass
class Lever:
    category:   str
    trigger:    str
    base_text:  str
    priority:   int
    horizon:    str
    effort:     str
    mitigation: Dict = field(default_factory=dict)


def _urgency(stress_result: dict) -> int:
    rev      = stress_result.get("reverse", {})
    icr_drop = rev.get("revenue_drop_icr", {}).get("value")
    if icr_drop is None: return 2
    if icr_drop <= 15:   return 1
    if icr_drop <= 30:   return 2
    return 3


def select_levers(stress_result: dict) -> List[Lever]:
    base      = stress_result.get("base_ratios", {})
    scenarios = stress_result.get("scenarios", [])
    urgency   = _urgency(stress_result)

    def fails(metric: str, threshold: float) -> bool:
        vals = [base.get(metric)] + [s["ratios"].get(metric) for s in scenarios]
        return any(v is not None and v < threshold for v in vals)

    by_key = {s["key"]: s for s in scenarios}

    def scenario_breaks(key: str) -> bool:
        return by_key.get(key, {}).get("verdict", {}).get("status") == "break"

    levers: List[Lever] = []

    if fails("interest_coverage", 1.5):
        levers.append(Lever(
            "Endettement", "Couverture des intérêts insuffisante (< 1.5×)",
            "Rééchelonner et refinancer la dette : allonger les maturités, "
            "renégocier les taux et réduire le levier financier.",
            urgency, horizon="moyen", effort="élevé",
            mitigation={"debt_reduction_pct": 20, "interest_reduction_pct": 20},
        ))
    if fails("dscr_approx", 1.25):
        levers.append(Lever(
            "Service de la dette", "DSCR approximatif insuffisant (< 1.25)",
            "Restructurer l'échéancier de la dette et différer les investissements "
            "non essentiels pour préserver la capacité de remboursement.",
            min(urgency, 2), horizon="moyen", effort="élevé",
            mitigation={"interest_reduction_pct": 15},
        ))
    if fails("net_margin", 3):
        levers.append(Lever(
            "Rentabilité", "Marge nette faible ou négative sous stress",
            "Lancer un plan de réduction des coûts et une revue tarifaire afin de "
            "restaurer la marge nette.",
            urgency, horizon="court", effort="moyen",
            mitigation={"cost_reduction_pct": 5},
        ))
    if fails("current_ratio", 1.2):
        levers.append(Lever(
            "Liquidité", "Ratio de liquidité tendu (< 1.2)",
            "Optimiser le besoin en fonds de roulement (accélérer le recouvrement "
            "clients, négocier les délais fournisseurs) et sécuriser des lignes de "
            "crédit confirmées.",
            urgency, horizon="court", effort="moyen",
            mitigation={"working_capital_pct": 15},
        ))
    if scenario_breaks("fx"):
        levers.append(Lever(
            "Risque de change", "Rupture sous le choc de dévaluation du dinar",
            "Couvrir l'exposition de change, diversifier les sources "
            "d'approvisionnement et augmenter la part de contenu local.",
            urgency, horizon="moyen", effort="moyen",
            mitigation={"import_share_reduction_pct": 50},
        ))
    if scenario_breaks("inflation"):
        levers.append(Lever(
            "Coûts des intrants", "Rupture sous le choc inflationniste",
            "Sécuriser des contrats d'approvisionnement à long terme et introduire "
            "des clauses d'indexation dans les contrats de vente.",
            urgency, horizon="moyen", effort="moyen",
            mitigation={"cost_reduction_pct": 3},
        ))
    if scenario_breaks("recession"):
        levers.append(Lever(
            "Diversification", "Rupture sous le scénario de récession",
            "Diversifier le portefeuille clients et les marchés, et constituer un "
            "coussin de trésorerie de précaution.",
            urgency, horizon="long", effort="élevé",
            mitigation={},
        ))

    levers.sort(key=lambda l: l.priority)
    return levers


# ══════════════════════════════════════════════════════════════════
# 2. ANALYSE WHAT-IF
# ══════════════════════════════════════════════════════════════════

def _apply_mitigation(inp: dict, mit: dict) -> dict:
    d = dict(inp)
    if mit.get("debt_reduction_pct"):
        d["debt"] = d["debt"] * (1 - mit["debt_reduction_pct"] / 100.0)
    if mit.get("interest_reduction_pct"):
        d["interest"] = d["interest"] * (1 - mit["interest_reduction_pct"] / 100.0)
    if mit.get("cost_reduction_pct"):
        saving = d["raw_materials"] * (mit["cost_reduction_pct"] / 100.0)
        d["raw_materials"] = d["raw_materials"] - saving
        d["ebit"] = d.get("ebit", 0) + saving
    if mit.get("working_capital_pct"):
        d["current_assets"] = d["current_assets"] * (1 + mit["working_capital_pct"] / 100.0)
    if mit.get("import_share_reduction_pct"):
        d["import_share"] = d.get("import_share", 0.6) * (1 - mit["import_share_reduction_pct"] / 100.0)
    return d


def _compute_impact(stress_inputs: dict, lever: Lever) -> dict:
    from services.stress_test import FinancialInputs, run_full_stress_test

    if not lever.mitigation:
        return {
            "applicable": False,
            "impact_level": "structurel",
            "note": "Mesure structurelle — effet sur la résilience non quantifiable par un ratio unique.",
        }

    try:
        before       = run_full_stress_test(FinancialInputs(**stress_inputs))
        after_inputs = _apply_mitigation(stress_inputs, lever.mitigation)
        after        = run_full_stress_test(FinancialInputs(**after_inputs))
    except Exception as e:
        return {"applicable": False, "impact_level": "n/d", "note": f"Simulation indisponible: {e}"}

    icr_b = before["base_ratios"]["interest_coverage"]
    icr_a = after["base_ratios"]["interest_coverage"]
    vb, va = before["base_verdict"], after["base_verdict"]

    improved = sum(
        1 for sb, sa in zip(before["scenarios"], after["scenarios"])
        if _STATUS_RANK.get(sa["verdict"]["status"], 0) > _STATUS_RANK.get(sb["verdict"]["status"], 0)
    )

    rank_gain = _STATUS_RANK.get(va["status"], 0) - _STATUS_RANK.get(vb["status"], 0)
    if rank_gain >= 2 or improved >= 2:
        impact_level = "élevé"
    elif rank_gain == 1 or improved == 1:
        impact_level = "moyen"
    else:
        impact_level = "faible"

    return {
        "applicable": True,
        "impact_level": impact_level,
        "interest_coverage_before": icr_b,
        "interest_coverage_after":  icr_a,
        "verdict_before": vb["label"],
        "verdict_after":  va["label"],
        "scenarios_improved": improved,
    }


# ══════════════════════════════════════════════════════════════════
# 3. CONTEXTE DU RAPPORT
# ══════════════════════════════════════════════════════════════════

def _stringify_section(section) -> str:
    if isinstance(section, str):  return section
    if isinstance(section, dict): return " ".join(v for v in section.values() if isinstance(v, str))
    return ""


def build_report_context(cache: dict) -> dict:
    company = cache.get("company", {}) or {}
    report  = cache.get("generated_report", {}) or {}
    fin_section = (report.get("s2_analyse_financiere")
                   or report.get("s_analyse_financiere")
                   or report.get("s2") or {})
    return {
        "denomination":     company.get("denomination", ""),
        "secteur":          company.get("label_secteur", ""),
        "activites":        company.get("activites", ""),
        "produits":         company.get("produits", ""),
        "regime":           company.get("regime", ""),
        "gouvernorat":      company.get("gouvernorat", ""),
        "financial_excerpt": _stringify_section(fin_section)[:800],
    }


# ══════════════════════════════════════════════════════════════════
# 4. REFORMULATION PAR LLM
# ══════════════════════════════════════════════════════════════════

def _summarize_stress(stress_result: dict) -> str:
    base = stress_result.get("base_ratios", {})
    rev  = stress_result.get("reverse", {})
    lines = [
        f"Couverture intérêts (base): {base.get('interest_coverage')}×",
        f"Marge nette (base): {base.get('net_margin')}%",
        f"Ratio liquidité (base): {base.get('current_ratio')}",
    ]
    for s in stress_result.get("scenarios", []):
        lines.append(f"Scénario « {s['label']} » → {s['verdict']['label']}")
    if rev.get("revenue_drop_icr", {}).get("value") is not None:
        lines.append(f"Rupture à -{rev['revenue_drop_icr']['value']}% de CA (couverture < 1.0×)")
    return "\n".join(lines)


def _llm_phrase(enriched: List[dict], ctx: dict, stress_result: dict) -> List[Dict]:
    from core.openai_client import get_openai_client, clean_response
    from core.config import OPENAI_MODEL

    # Use Azure client if available, fallback to standard OpenAI
    try:
        from services.azure_client import get_azure_client
        client, model = get_azure_client()
    except Exception:
        client = get_openai_client()
        model  = OPENAI_MODEL

    lines = []
    for e in enriched:
        wi     = e["impact"]
        whatif = ""
        if wi.get("applicable"):
            whatif = (f" (simulation: couverture {wi['interest_coverage_before']}× → "
                      f"{wi['interest_coverage_after']}×, verdict {wi['verdict_before']} → {wi['verdict_after']})")
        lines.append(f"- [{e['categorie']}] {e['base_text']}{whatif}")
    levers_text = "\n".join(lines)

    profile = (f"Dénomination: {ctx.get('denomination')}\nSecteur: {ctx.get('secteur')}\n"
               f"Activités: {ctx.get('activites')}\nProduits: {ctx.get('produits')}\n"
               f"Régime: {ctx.get('regime')}\nGouvernorat: {ctx.get('gouvernorat')}")

    prompt = f"""Tu es un analyste crédit senior dans une banque tunisienne. À partir du profil de l'entreprise, de l'extrait d'analyse financière et des résultats du stress test (avec simulations what-if), reformule chaque axe en recommandation CONCRÈTE, ACTIONNABLE et ADAPTÉE à cette entreprise. Quand une simulation est fournie, intègre le résultat chiffré dans la recommandation.

PROFIL ENTREPRISE:
{profile}

EXTRAIT ANALYSE FINANCIÈRE:
{ctx.get('financial_excerpt')}

RÉSULTATS STRESS TEST:
{_summarize_stress(stress_result)}

AXES À REFORMULER (avec simulation what-if):
{levers_text}

Consignes:
- Recommandations spécifiques (pas génériques), français bancaire.
- Intègre les chiffres de simulation quand ils existent.
- Réponds UNIQUEMENT en JSON: [{{"categorie": "...", "recommandation": "..."}}]
- Même ordre et mêmes catégories que les axes fournis. Aucun texte hors JSON."""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Analyste crédit senior. JSON uniquement."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1400,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    raw  = clean_response(resp.choices[0].message.content)
    raw  = re.sub(r"^```json\s*", "", raw)
    raw  = re.sub(r"\s*```$",     "", raw)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Réponse LLM non conforme")
    return data


# ══════════════════════════════════════════════════════════════════
# 5. POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════

def build_recommendations(stress_result: dict,
                          report_context: Optional[dict] = None,
                          use_llm: bool = True) -> dict:
    levers = select_levers(stress_result)
    if not levers:
        return {
            "has_recommendations": False,
            "method": "règles",
            "recommendations": [],
            "note": "Aucune vulnérabilité critique détectée par le stress test.",
        }

    stress_inputs = stress_result.get("inputs", {})

    enriched = []
    for l in levers:
        impact = _compute_impact(stress_inputs, l) if stress_inputs else {"applicable": False, "impact_level": "n/d"}
        enriched.append({
            "categorie": l.category,
            "base_text": l.base_text,
            "priorite":  _PRIORITY_LABEL[l.priority],
            "horizon":   l.horizon,
            "effort":    l.effort,
            "impact":    impact,
        })

    method = "règles"
    if use_llm and report_context:
        try:
            phrased = _llm_phrase(enriched, report_context, stress_result)
            by_cat  = {p.get("categorie", "").strip().lower(): p.get("recommandation", "") for p in phrased}
            for e in enriched:
                txt = by_cat.get(e["categorie"].strip().lower())
                e["recommandation"] = txt or e["base_text"]
            method = "hybride (règles + LLM)"
            logger.info("[recommendations] LLM OK — recommandations hybrides générées")
        except Exception as ex:
            logger.warning(f"[recommendations] LLM indisponible ({ex}) — fallback règles")
            for e in enriched:
                e["recommandation"] = e["base_text"]
            method = "règles (LLM indisponible)"
            logger.warning(f"[recommendations] FALLBACK règles — LLM indisponible: {ex}")
    else:
        for e in enriched:
            e["recommandation"] = e["base_text"]

    for e in enriched:
        e.pop("base_text", None)

    grouped = {"court": [], "moyen": [], "long": []}
    for e in enriched:
        grouped.get(e["horizon"], grouped["moyen"]).append(e)

    return {
        "has_recommendations": True,
        "method": method,
        "recommendations": enriched,
        "by_horizon": grouped,
        "horizon_labels": {
            "court": "Court terme (0–6 mois)",
            "moyen": "Moyen terme (6–18 mois)",
            "long":  "Long terme (>18 mois)",
        },
    }