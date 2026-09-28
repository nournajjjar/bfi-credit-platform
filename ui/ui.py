#!/usr/bin/env python3
"""
User interface and display module for Deep Research system
"""

from colorama import Fore, Style


# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def print_banner():
    """Print application banner"""
    print(f"\n{Fore.CYAN}{'═'*65}")
    print(f"  🔍  Deep Research — Rapport Benchmark Crédit (Q&A + Autoprompting)")
    print(f"{'═'*65}{Style.RESET_ALL}\n")


def print_verdict(rapport):
    """Print the final credit verdict section"""
    v = rapport.get("s9_verdict", {})
    if not v:
        return

    color = {
        "Faible": Fore.GREEN,
        "Modéré": Fore.YELLOW,
        "Élevé": Fore.RED
    }.get(v.get("profil_risque_credit", ""), Fore.WHITE)

    print(f"\n{Fore.CYAN}{'─'*65}")
    print(f"  🏦  VERDICT FINAL")
    print(f"{'─'*65}{Style.RESET_ALL}")

    for label, key in [
        ("Risque crédit", "profil_risque_credit"),
        ("Solidité fin.", "solidite_financiere"),
        ("Maturité", "maturite_stabilite"),
        ("Exposition intl", "exposition_internationale"),
        ("Justification", "justification"),
    ]:
        val = v.get(key, "")
        if val:
            c = color if key == "profil_risque_credit" else ""
            print(f"  {Fore.WHITE}{label:<16}{Style.RESET_ALL}: {c}{val}{Style.RESET_ALL}")


def print_section_scores(rapport):
    """Print scores for all sections"""
    scores = rapport.get("_meta", {}).get("section_scores", {})
    if not scores:
        return

    print(f"\n  {Fore.WHITE}Scores par section :{Style.RESET_ALL}")
    for sid, score in scores.items():
        c = Fore.GREEN if score >= 4 else Fore.YELLOW if score >= 3 else Fore.RED
        print(f"    {sid}: {c}{score}/5{Style.RESET_ALL}")


def print_fuzzy_matches(matches):
    """Print fuzzy search matches"""
    print(f"\n{Fore.YELLOW}  Entreprises trouvées :{Style.RESET_ALL}")
    for i, (score, c) in enumerate(matches, 1):
        print(
            f"  [{i}] {Fore.WHITE}{c['denomination']}{Style.RESET_ALL} "
            f"({Fore.CYAN}{score:.0f}%{Style.RESET_ALL}) "
            f"{c.get('gouvernorat', '')} — {c.get('label_secteur', '')}"
        )