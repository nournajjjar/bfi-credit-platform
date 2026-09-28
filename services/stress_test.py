# backend/services/stress_test.py
"""
Moteur de Stress Testing pour l'évaluation du risque de crédit corporate.

Méthodologies implémentées :
  - Analyse de scénarios déterministe multi-facteurs
  - Test de résistance inversé par dichotomie
  - Modèle de comportement des coûts / levier d'exploitation
  - Hypothèse de bilan statique
  - Approche bottom-up au niveau de la firme

EBIT est estimé automatiquement si non fourni :
  EBIT_estimé = Revenus - Coûts variables - Amortissements
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Callable


# ══════════════════════════════════════════════════════════════════
# 1. ENTRÉES FINANCIÈRES
# ══════════════════════════════════════════════════════════════════

@dataclass
class FinancialInputs:
    """
    Chiffres de base extraits des états financiers de l'entreprise.
    """
    revenue: float              # Chiffre d'affaires
    raw_materials: float = 0    # Achats consommés (driver variable)
    amortization: float = 0     # Dotations aux amortissements
    interest: float = 0         # Intérêts bruts
    equity: float = 0           # Capitaux propres
    debt: float = 0             # Dettes financières
    current_assets: float = 0   # Total actifs courants
    current_liabilities: float = 0  # Total passifs courants
    ebit: Optional[float] = None    # Résultat d'exploitation (optionnel)

    is_exporter: bool = False
    tax_rate: float = 0.15
    import_share: float = 0.60
    export_share: float = 0.50
    principal_ratio: float = 0.10

    def __post_init__(self):
        # Estimate EBIT if not provided
        if self.ebit is None or self.ebit == 0:
            # EBIT ≈ Revenue - VariableCosts - Amortization
            # Use 30% of (Revenue - RawMaterials) as fixed cost estimate
            gross = self.revenue - self.raw_materials
            estimated_fixed = gross * 0.30
            self.ebit = gross - self.amortization - estimated_fixed
            self._ebit_estimated = True
        else:
            self._ebit_estimated = False

    @property
    def variable_cost_ratio(self) -> float:
        return self.raw_materials / self.revenue if self.revenue else 0.0

    @property
    def fixed_costs(self) -> float:
        return max(0, self.revenue - self.ebit - self.raw_materials)

    @property
    def net_result(self) -> float:
        pretax = self.ebit - self.interest
        tax = max(0.0, pretax * self.tax_rate)
        return pretax - tax


# ══════════════════════════════════════════════════════════════════
# 2. CHOCS
# ══════════════════════════════════════════════════════════════════

@dataclass
class Shocks:
    revenue_pct: float = 0.0
    cost_pct: float = 0.0
    interest_pct: float = 0.0
    fx_pct: float = 0.0
    receivables_delay_pct: float = 0.0


# ══════════════════════════════════════════════════════════════════
# 3. APPLICATION DES CHOCS
# ══════════════════════════════════════════════════════════════════

def apply_shocks(base: FinancialInputs, shocks: Shocks) -> Dict[str, float]:
    rev_factor = 1.0 + shocks.revenue_pct / 100.0

    new_revenue = base.revenue * rev_factor
    if base.is_exporter and shocks.fx_pct:
        new_revenue *= (1.0 + (shocks.fx_pct / 100.0) * base.export_share)

    new_variable = base.raw_materials * rev_factor
    new_variable *= (1.0 + shocks.cost_pct / 100.0)
    if shocks.fx_pct:
        new_variable *= (1.0 + (shocks.fx_pct / 100.0) * base.import_share)

    fixed = base.fixed_costs
    new_ebit = new_revenue - new_variable - fixed
    new_interest = base.interest * (1.0 + shocks.interest_pct / 100.0)

    pretax = new_ebit - new_interest
    tax = max(0.0, pretax * base.tax_rate)
    new_net = pretax - tax

    new_current_assets = base.current_assets * (1.0 - shocks.receivables_delay_pct / 100.0)

    return {
        "revenue": new_revenue,
        "variable_costs": new_variable,
        "fixed_costs": fixed,
        "ebit": new_ebit,
        "interest": new_interest,
        "net_result": new_net,
        "current_assets": new_current_assets,
        "current_liabilities": base.current_liabilities,
        "amortization": base.amortization,
        "debt": base.debt,
    }


# ══════════════════════════════════════════════════════════════════
# 4. RATIOS DE SANTÉ
# ══════════════════════════════════════════════════════════════════

def compute_ratios(f: Dict[str, float], principal_ratio: float = 0.10) -> Dict[str, float]:
    revenue = f["revenue"]
    ebit    = f["ebit"]
    interest = f["interest"]
    net     = f["net_result"]
    ca      = f["current_assets"]
    pa      = f["current_liabilities"]
    amort   = f["amortization"]
    debt    = f["debt"]

    icr           = ebit / interest if interest else float("inf")
    op_margin     = ebit / revenue if revenue else 0.0
    net_margin    = net / revenue if revenue else 0.0
    current_ratio = ca / pa if pa else float("inf")

    est_principal = principal_ratio * debt
    debt_service  = interest + est_principal
    dscr          = (ebit + amort) / debt_service if debt_service else float("inf")

    return {
        "interest_coverage": round(icr, 2),
        "operating_margin":  round(op_margin * 100, 1),
        "net_margin":        round(net_margin * 100, 1),
        "current_ratio":     round(current_ratio, 2),
        "dscr_approx":       round(dscr, 2),
    }


def _verdict(ratios: Dict[str, float]) -> Dict:
    icr        = ratios["interest_coverage"]
    net_margin = ratios["net_margin"]
    current    = ratios["current_ratio"]

    breaks  = (icr < 1.0) or (net_margin < 0)
    stressed = (1.0 <= icr < 1.5) or (0 <= net_margin < 3) or (current < 1.0)

    if breaks:
        status, label = "break",   "Rupture"
    elif stressed:
        status, label = "warning", "Sous tension"
    else:
        status, label = "ok",      "Résiste"

    return {"status": status, "label": label}


# ══════════════════════════════════════════════════════════════════
# 5. SCÉNARIOS NOMMÉS
# ══════════════════════════════════════════════════════════════════

NAMED_SCENARIOS = {
    "inflation": {
        "label": "Choc inflationniste",
        "description": "Hausse du prix des intrants (+15%), hausse des taux (+20%), légère contraction de la demande (-5%).",
        "shocks": Shocks(revenue_pct=-5, cost_pct=15, interest_pct=20),
    },
    "recession": {
        "label": "Récession (contraction de la demande)",
        "description": "Chute des ventes (-20%), allongement des délais clients (15% des actifs courants gelés).",
        "shocks": Shocks(revenue_pct=-20, receivables_delay_pct=15),
    },
    "fx": {
        "label": "Choc de change (dévaluation du dinar)",
        "description": "Dévaluation du dinar de 20%. Renchérit les importations, soutient le CA des exportateurs.",
        "shocks": Shocks(fx_pct=20, interest_pct=10),
    },
}


# ══════════════════════════════════════════════════════════════════
# 6. TEST DE RÉSISTANCE INVERSÉ
# ══════════════════════════════════════════════════════════════════

def _bisect(func: Callable[[float], float], lo: float, hi: float,
            target: float, tol: float = 0.001, max_iter: int = 200) -> Optional[float]:
    f_lo = func(lo) - target
    f_hi = func(hi) - target
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid   = (lo + hi) / 2.0
        f_mid = func(mid) - target
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def reverse_stress_test(base: FinancialInputs) -> Dict:
    results = {}

    def icr_at(rev_pct: float) -> float:
        s = apply_shocks(base, Shocks(revenue_pct=rev_pct))
        return s["ebit"] / s["interest"] if s["interest"] else float("inf")

    if icr_at(0) <= 1.0:
        results["revenue_drop_icr"] = {"value": 0.0, "note": "Déjà sous le seuil"}
    else:
        x = _bisect(icr_at, -99, 0, target=1.0)
        results["revenue_drop_icr"] = {
            "value": round(abs(x), 1) if x is not None else None,
            "note": "Baisse de CA avant couverture intérêts < 1.0×"
        }

    def net_at(cost_pct: float) -> float:
        return apply_shocks(base, Shocks(cost_pct=cost_pct))["net_result"]

    if net_at(0) <= 0:
        results["cost_rise_net"] = {"value": 0.0, "note": "Déjà déficitaire"}
    else:
        x = _bisect(net_at, 0, 300, target=0.0)
        results["cost_rise_net"] = {
            "value": round(x, 1) if x is not None else None,
            "note": "Hausse des coûts intrants avant résultat net = 0"
        }

    return results


# ══════════════════════════════════════════════════════════════════
# 7. POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def run_full_stress_test(base: FinancialInputs,
                         custom_shocks: Optional[dict] = None) -> Dict:
    base_financials = apply_shocks(base, Shocks())
    base_ratios     = compute_ratios(base_financials, base.principal_ratio)

    scen_defs = dict(NAMED_SCENARIOS)
    if custom_shocks:
        scen_defs["custom"] = {
            "label":       "Scénario personnalisé",
            "description": "Chocs définis par l'analyste.",
            "shocks":      Shocks(**custom_shocks),
        }

    scenarios_out: List[Dict] = []
    for key, sc in scen_defs.items():
        stressed = apply_shocks(base, sc["shocks"])
        ratios   = compute_ratios(stressed, base.principal_ratio)
        verdict  = _verdict(ratios)
        scenarios_out.append({
            "key":                 key,
            "label":               sc["label"],
            "description":         sc["description"],
            "shocks":              asdict(sc["shocks"]),
            "stressed_financials": {k: round(v, 0) for k, v in stressed.items()},
            "ratios":              ratios,
            "verdict":             verdict,
        })

    reverse = reverse_stress_test(base)

    ebit_note = "(estimé automatiquement)" if getattr(base, '_ebit_estimated', False) else "(fourni)"

    return {
        "inputs":       asdict(base),
        "derived": {
            "variable_cost_ratio": round(base.variable_cost_ratio * 100, 1),
            "fixed_costs":         round(base.fixed_costs, 0),
            "net_result":          round(base.net_result, 0),
            "ebit_used":           round(base.ebit, 0),
            "ebit_note":           ebit_note,
        },
        "base_ratios":  base_ratios,
        "base_verdict": _verdict(base_ratios),
        "scenarios":    scenarios_out,
        "reverse":      reverse,
    }


# ══════════════════════════════════════════════════════════════════
# 8. AUTO-TEST
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    sah = FinancialInputs(
        revenue=462_125_938,
        raw_materials=249_338_735,
        amortization=23_789_544,
        interest=26_402_044,
        equity=448_869_472,
        debt=126_128_651,
        current_assets=845_131_718,
        current_liabilities=813_064_562,
        is_exporter=False,
    )
    result = run_full_stress_test(sah)
    print(json.dumps(result, indent=2, ensure_ascii=False))