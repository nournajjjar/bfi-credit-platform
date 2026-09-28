# backend/services/financial_forecast.py
"""
Moteur de prévisions financières — Projection des états financiers.

Méthodologies :
  1) Régression linéaire par moindres carrés ordinaires (OLS)
       y = a + b·t   sur données historiques annualisées
       Intervalle de prévision à 90 % : ŷ ± t₀.₀₅ · σ̂_pred
  2) Taux de Croissance Annuel Composé (CAGR)
       CAGR = (y_N / y_1)^(1/(N-1)) − 1
  3) Lissage exponentiel double de Holt (tendance) — si N ≥ 4
       Niveau: L_t = α·y_t + (1−α)·(L_{t−1} + T_{t−1})
       Tendance: T_t = β·(L_t − L_{t−1}) + (1−β)·T_{t−1}
  4) Projection stressée : les chocs des scénarios nommés (stress test)
       sont appliqués à chaque année projetée — test de résistance
       prospectif (forward-looking stress test).

Hypothèses :
  - Données H1 annualisées (× 2) pour les flux ; stocks non annualisés.
  - Si H1 et FY existent pour la même année, FY est retenu.
  - Coûts variables projetés via le ratio matières/CA historique.
  - Coûts fixes projetés par OLS indépendant.
"""

import re
import numpy as np
from typing import List, Dict, Optional


# ══════════════════════════════════════════════════════════════════
# 1. UTILITAIRES
# ══════════════════════════════════════════════════════════════════

_FLOW_METRICS = {"revenue", "ebit", "raw_materials", "interest", "net_result", "amortization"}
_STOCK_METRICS = {"equity", "debt", "current_assets", "current_liabilities"}


def _parse_date(date_str: str):
    """'30.06.2025' → (year=2025, month=6, is_h1=True, t=2025.5)"""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", str(date_str))
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    t = year + (month - 0.5) / 12.0   # decimal year at period midpoint
    is_h1 = month == 6
    is_fy = month == 12
    return {"year": year, "month": month, "is_h1": is_h1, "is_fy": is_fy, "t": t, "date": date_str}


def _annualize(period: dict) -> dict:
    """Multiplie les flux par 2 pour les états H1 (semi-annuels)."""
    p = dict(period)
    if p.get("is_h1"):
        for k in _FLOW_METRICS:
            if p.get(k) is not None:
                p[k] = p[k] * 2.0
        p["annualized"] = True
        p["label"] = f"{p['year']} (H1 ann.)"
    else:
        p["annualized"] = False
        p["label"] = str(p["year"])
    return p


def _deduplicate(periods: list) -> list:
    """Si H1 et FY coexistent pour la même année, conserver FY."""
    by_year: Dict[int, dict] = {}
    for p in periods:
        y = p["year"]
        if y not in by_year:
            by_year[y] = p
        else:
            # préférer FY
            if p.get("is_fy") or not p.get("is_h1"):
                by_year[y] = p
    return sorted(by_year.values(), key=lambda p: p["t"])


# ══════════════════════════════════════════════════════════════════
# 2. MODÈLES D'AJUSTEMENT
# ══════════════════════════════════════════════════════════════════

def _ols_fit(t: np.ndarray, y: np.ndarray):
    """OLS : y = a + b·t  — renvoie les paramètres et diagnostics."""
    n = len(t)
    t_mean = float(np.mean(t))
    y_mean = float(np.mean(y))
    stt = float(np.sum((t - t_mean) ** 2))
    b = float(np.sum((t - t_mean) * (y - y_mean))) / stt if stt > 0 else 0.0
    a = y_mean - b * t_mean
    y_hat = a + b * t
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    se = float(np.sqrt(ss_res / max(n - 2, 1)))
    return {"a": a, "b": b, "r2": r2, "se": se, "n": n, "t_mean": t_mean, "stt": stt}


def _ols_predict(fit: dict, t_new: float, alpha: float = 0.10):
    """Prédiction OLS + intervalle de prévision à 1−α."""
    a, b = fit["a"], fit["b"]
    se, n = fit["se"], fit["n"]
    t_mean, stt = fit["t_mean"], fit["stt"]
    y_hat = a + b * t_new
    # Intervalle de prévision (pas seulement de confiance)
    se_pred = se * np.sqrt(1.0 + 1.0 / n + (t_new - t_mean) ** 2 / max(stt, 1e-9))
    t_crit = 1.645   # t à 90 % (approximation normale)
    return float(y_hat), float(y_hat - t_crit * se_pred), float(y_hat + t_crit * se_pred)


def _cagr(y_start: float, y_end: float, n_years: float) -> Optional[float]:
    if y_start is None or y_end is None or y_start <= 0 or n_years <= 0:
        return None
    if y_end <= 0:
        return None
    return float((y_end / y_start) ** (1.0 / n_years) - 1.0)


def _holt(y: np.ndarray, horizon: int, alpha: float = 0.3, beta: float = 0.1) -> list:
    """Lissage de Holt (niveau + tendance), requiert N ≥ 4."""
    n = len(y)
    L = np.zeros(n)
    T = np.zeros(n)
    L[0] = y[0]
    T[0] = (y[-1] - y[0]) / max(n - 1, 1)
    for i in range(1, n):
        L[i] = alpha * y[i] + (1 - alpha) * (L[i - 1] + T[i - 1])
        T[i] = beta * (L[i] - L[i - 1]) + (1 - beta) * T[i - 1]
    return [float(L[-1] + k * T[-1]) for k in range(1, horizon + 1)]


# ══════════════════════════════════════════════════════════════════
# 3. PROJECTION D'UNE SÉRIE
# ══════════════════════════════════════════════════════════════════

def _project_series(t_hist: np.ndarray, y_hist: np.ndarray,
                    t_proj: np.ndarray) -> Dict:
    """
    Projette une série (OLS primaire + Holt si N ≥ 4 + CAGR indicatif).
    Renvoie : points + intervalles de confiance pour chaque t_proj.
    """
    n = len(t_hist)
    fit = _ols_fit(t_hist, y_hist)

    cagr_val = _cagr(float(y_hist[0]), float(y_hist[-1]),
                     float(t_hist[-1] - t_hist[0])) if n >= 2 else None

    holt_pts = _holt(y_hist, len(t_proj)) if n >= 4 else None

    results = []
    for i, t_new in enumerate(t_proj):
        pt, lo, hi = _ols_predict(fit, float(t_new))
        # si Holt disponible, on utilise sa prédiction mais les IC de l'OLS
        primary = holt_pts[i] if holt_pts else pt
        # CAGR projection
        cagr_proj = None
        if cagr_val is not None:
            years_ahead = float(t_new - t_hist[-1])
            cagr_proj = float(y_hist[-1]) * (1 + cagr_val) ** years_ahead
        results.append({
            "t": float(t_new),
            "value": round(primary, 0),
            "low": round(lo, 0),
            "high": round(hi, 0),
            "cagr_proj": round(cagr_proj, 0) if cagr_proj else None,
        })

    return {
        "r2": round(fit["r2"], 3),
        "cagr": round(cagr_val * 100, 2) if cagr_val is not None else None,
        "model": "Holt + OLS (IC)" if holt_pts else "OLS",
        "n_points": n,
        "points": results,
    }


# ══════════════════════════════════════════════════════════════════
# 4. PROJECTION STRESSÉE
# ══════════════════════════════════════════════════════════════════

_NAMED_SHOCKS = {
    "recession":  {"revenue_pct": -20, "cost_pct":   0, "interest_pct":  0, "receivables_pct": 15},
    "inflation":  {"revenue_pct":  -5, "cost_pct":  15, "interest_pct": 20, "receivables_pct":  0},
    "fx":         {"revenue_pct":   0, "cost_pct":   0, "interest_pct": 10, "fx_pct":          20},
}


def _stress_projected_year(rev, ebit, interest, net_result,
                           var_cost_ratio, fixed_costs, is_exporter,
                           import_share, shocks) -> dict:
    """
    Applique les chocs à un seul point projeté et renvoie les ratios stressés.
    Réutilise la logique du moteur de stress test.
    """
    r = shocks.get("revenue_pct", 0) / 100
    c = shocks.get("cost_pct", 0) / 100
    i_s = shocks.get("interest_pct", 0) / 100
    fx = shocks.get("fx_pct", 0) / 100

    if rev is None or rev <= 0:
        return {}

    new_rev = rev * (1 + r)
    if is_exporter and fx:
        new_rev *= (1 + fx * 0.5)    # exportateurs gagnent sur dévaluation

    new_var = rev * var_cost_ratio * (1 + r) * (1 + c)
    if fx:
        new_var *= (1 + fx * import_share)

    new_ebit = new_rev - new_var - fixed_costs
    new_interest = interest * (1 + i_s) if interest and interest > 0 else interest or 0
    pretax = new_ebit - new_interest
    new_net = pretax - max(0, pretax * 0.15)

    icr = round(new_ebit / new_interest, 2) if new_interest and new_interest > 0 else None
    net_margin = round(new_net / new_rev * 100, 1) if new_rev else None
    op_margin = round(new_ebit / new_rev * 100, 1) if new_rev else None

    return {
        "revenue": round(new_rev, 0),
        "ebit": round(new_ebit, 0),
        "net_result": round(new_net, 0),
        "icr": icr,
        "net_margin": net_margin,
        "op_margin": op_margin,
    }


# ══════════════════════════════════════════════════════════════════
# 5. POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def run_forecast(periods: List[Dict], horizon: int = 5,
                 is_exporter: bool = False,
                 import_share: float = 0.6) -> Dict:
    """
    periods : liste de dicts avec au moins {date, revenue, ebit, interest}
              + optionnel : raw_materials, net_result, amortization, ...
    horizon : nombre d'années projetées (max 10)
    Retourne : série historique + projetée + stressée
    """
    horizon = min(max(horizon, 1), 10)

    # ── Préparer les données historiques ──────────────────────────
    enriched = []
    for p in periods:
        pd_info = _parse_date(p.get("date", ""))
        if not pd_info:
            continue
        merged = {**pd_info, **p}
        annualized = _annualize(merged)
        enriched.append(annualized)

    if len(enriched) < 2:
        return {"error": "Au moins 2 périodes requises pour la projection."}

    enriched = _deduplicate(enriched)
    n = len(enriched)

    t_hist = np.array([p["t"] for p in enriched])
    last_year = int(t_hist[-1])    # floor → projections commencent à last_year + 1
    t_proj = np.array([float(last_year + k) for k in range(1, horizon + 1)])
    proj_years = [last_year + k for k in range(1, horizon + 1)]
    data_quality = "insuffisant" if n < 3 else "acceptable" if n < 5 else "bon"

    # ── Séries historiques pour affichage ─────────────────────────
    historical = []
    for p in enriched:
        row = {
            "year": p["label"],
            "t": p["t"],
            "revenue": p.get("revenue"),
            "ebit": p.get("ebit"),
            "interest": p.get("interest"),
            "net_result": p.get("net_result"),
            "icr": (round(p["ebit"] / p["interest"], 2)
                    if p.get("ebit") and p.get("interest") and p["interest"] > 0
                    else None),
            "net_margin": (round(p["net_result"] / p["revenue"] * 100, 1)
                           if p.get("net_result") and p.get("revenue") and p["revenue"] > 0
                           else None),
            "op_margin": (round(p["ebit"] / p["revenue"] * 100, 1)
                          if p.get("ebit") and p.get("revenue") and p["revenue"] > 0
                          else None),
            "annualized": p.get("annualized", False),
        }
        historical.append(row)

    # ── Projections par OLS / Holt ─────────────────────────────────
    def _get_series(key):
        vals = [p.get(key) for p in enriched]
        if all(v is None for v in vals):
            return None, None
        t_ok = np.array([t_hist[i] for i, v in enumerate(vals) if v is not None])
        y_ok = np.array([v for v in vals if v is not None], dtype=float)
        return t_ok, y_ok

    projections = {}
    model_stats = {}
    for key in ("revenue", "ebit", "interest", "net_result"):
        t_ok, y_ok = _get_series(key)
        if t_ok is None or len(t_ok) < 2:
            projections[key] = None
        else:
            proj = _project_series(t_ok, y_ok, t_proj)
            projections[key] = proj
            if key == "revenue":
                r2_reported = proj["r2"] if proj["n_points"] >= 3 else None
                model_stats = {
                    "model": proj["model"],
                    "r2": r2_reported,
                    "cagr_pct": proj["cagr"],
                    "n_points": proj["n_points"],
                    "data_quality": data_quality,
                    "warning": ("Seulement 2 points — tendance à interpréter avec précaution."
                                if n < 3 else None),
                }

    # ── Paramètres de structure de coûts (pour projection stressée) ─
    rev_hist = np.array([p.get("revenue") or 0 for p in enriched], dtype=float)
    raw_hist = np.array([p.get("raw_materials") or 0 for p in enriched], dtype=float)
    # ratio coûts variables moyen
    valid_ratios = [raw_hist[i] / rev_hist[i]
                    for i in range(n) if rev_hist[i] > 0 and raw_hist[i] > 0]
    var_cost_ratio = float(np.mean(valid_ratios)) if valid_ratios else 0.54

    # Estimate EBIT if missing: revenue - raw_materials - amortization - 30% gross
    def _est_ebit(p):
        e = p.get("ebit")
        if e and e != 0: return e
        rev = p.get("revenue") or 0
        mat = p.get("raw_materials") or 0
        amo = p.get("amortization") or 0
        gross = rev - mat
        return gross - amo - gross * 0.30 if gross > 0 else 0
    ebit_hist = np.array([_est_ebit(p) for p in enriched], dtype=float)
    # coûts fixes = CA - EBIT - coûts variables (moyenne historique)
    fixed_costs_list = [
        rev_hist[i] - ebit_hist[i] - raw_hist[i]
        for i in range(n) if rev_hist[i] > 0 and ebit_hist[i] != 0
    ]
    avg_fixed_costs = float(np.mean(fixed_costs_list)) if fixed_costs_list else 0

    # ── Construire la série projetée ───────────────────────────────
    projected = []
    for idx, yr in enumerate(proj_years):
        row: Dict = {"year": str(yr), "t": float(yr), "is_projected": True}

        rev_pt  = projections["revenue"]["points"][idx]["value"]  if projections.get("revenue")  else None
        ebit_pt = projections["ebit"]["points"][idx]["value"]     if projections.get("ebit")     else None
        int_pt  = projections["interest"]["points"][idx]["value"] if projections.get("interest") else None
        net_pt  = projections["net_result"]["points"][idx]["value"] if projections.get("net_result") else None

        row["revenue"]    = rev_pt
        row["revenue_low"] = projections["revenue"]["points"][idx]["low"]   if projections.get("revenue") else None
        row["revenue_high"]= projections["revenue"]["points"][idx]["high"]  if projections.get("revenue") else None
        row["ebit"]       = ebit_pt
        row["interest"]   = max(int_pt, 1) if int_pt else None   # évite division par 0
        row["net_result"] = net_pt

        # Ratios projetés
        if ebit_pt and int_pt and int_pt > 0:
            row["icr"] = round(ebit_pt / int_pt, 2)
            row["icr_low"]  = round(projections["ebit"]["points"][idx]["low"]  / int_pt, 2) if projections.get("ebit") else None
            row["icr_high"] = round(projections["ebit"]["points"][idx]["high"] / int_pt, 2) if projections.get("ebit") else None
        if net_pt and rev_pt and rev_pt > 0:
            row["net_margin"] = round(net_pt / rev_pt * 100, 1)
        if ebit_pt and rev_pt and rev_pt > 0:
            row["op_margin"] = round(ebit_pt / rev_pt * 100, 1)

        # ── Projections stressées (#4 forward-looking) ─────────────
        stressed = {}
        for scen_name, shocks in _NAMED_SHOCKS.items():
            s = _stress_projected_year(
                rev=rev_pt, ebit=ebit_pt,
                interest=int_pt or 0,
                net_result=net_pt,
                var_cost_ratio=var_cost_ratio,
                fixed_costs=avg_fixed_costs,
                is_exporter=is_exporter,
                import_share=import_share,
                shocks=shocks,
            )
            stressed[scen_name] = s
        row["stressed"] = stressed

        projected.append(row)

    # ── Résumé de la trajectoire ────────────────────────────────────
    if projected:
        last = projected[-1]
        first = historical[-1]
        summary = {
            "horizon_years": horizon,
            "last_historical_year": first["year"],
            "last_projected_year": str(proj_years[-1]),
            "projected_revenue_last": last.get("revenue"),
            "projected_icr_last": last.get("icr"),
            "projected_net_margin_last": last.get("net_margin"),
        }
    else:
        summary = {}

    return {
        "company": None,   # rempli par le caller
        "model_stats": model_stats,
        "var_cost_ratio_pct": round(var_cost_ratio * 100, 1),
        "historical": historical,
        "projected": projected,
        "scenario_labels": {
            "recession": "Scénario récession",
            "inflation": "Scénario inflation",
            "fx":        "Scénario change",
        },
        "summary": summary,
    }