#!/usr/bin/env python3
import json, re
from colorama import Fore, Style
from core.config import  OPENAI_MODEL
from core.openai_client import get_openai_client , clean_response

# services/evaluation.py - ENHANCED WITH SCORING CRITERIA

"""
Enhanced evaluation module with detailed section scoring criteria.
Compatible with existing llm_sections.py architecture.
"""

import json
from typing import Dict, Tuple, List


# ══════════════════════════════════════════════════════════════════════════════
# SCORING CRITERIA - NEW ADDITION
# ══════════════════════════════════════════════════════════════════════════════

SECTION_SCORING_CRITERIA = {
    "s1_profil_operationnel": {
        "required_fields": [
            "activite_principale", "produits_services", "marches_servis",
            "regime_export", "note_analyste"
        ],
        "optional_fields": ["effectif", "annee_creation", "sites_production", "certifications"],
        "min_note_length": 100,
        "max_score": 5
    },

    "s2_analyse_financiere": {
        "required_fields": [
            "chiffre_affaires", "resultat_net", "total_actif",
            "capitaux_propres", "note_analyste"
        ],
        "numeric_fields": ["chiffre_affaires", "resultat_net", "total_actif", "capitaux_propres"],
        "optional_fields": ["marge_brute", "ratio_endettement", "tresorerie"],
        "min_note_length": 120,
        "max_score": 5
    },

    "s3_positionnement_marche": {
        "required_fields": [
            "position_concurrentielle", "principaux_concurrents",
            "avantages_competitifs", "dynamique_sectorielle", "note_analyste"
        ],
        "list_fields": ["principaux_concurrents", "avantages_competitifs"],
        "min_list_length": 2,
        "min_note_length": 100,
        "max_score": 5
    },

    "s4_facteurs_risque": {
        "required_fields": ["risques", "risque_global", "note_analyste"],
        "list_fields": ["risques"],
        "min_list_length": 3,
        "risk_required_fields": ["risque", "description", "severite"],
        "min_note_length": 100,
        "max_score": 5
    },

    "s5_facteurs_favorables": {
        "required_fields": ["atouts", "note_analyste"],
        "list_fields": ["atouts"],
        "min_list_length": 3,
        "atout_required_fields": ["atout", "description"],
        "min_note_length": 100,
        "max_score": 5
    },

    "s6_gouvernance_management": {
        "required_fields": [
            "structure_actionnariat", "transparence_financiere",
            "notation_gouvernance", "note_analyste"
        ],
        "min_note_length": 100,
        "max_score": 5
    },

    "s7_benchmark_sectoriel": {
        "required_fields": [
            "position_capital", "position_effectif", "position_age",
            "comparaison_export", "note_analyste"
        ],
        "min_note_length": 100,
        "max_score": 5
    },

    "s_benchmark_leaders": {
        "required_fields": ["leaders_secteur", "note_analyste"],
        "list_fields": ["leaders_secteur"],
        "min_list_length": 2,
        "min_note_length": 100,
        "max_score": 5
    },

    "s_benchmark_international": {
        "required_fields": ["pays_comparables", "entreprises_reference", "note_analyste"],
        "list_fields": ["pays_comparables", "entreprises_reference"],
        "min_list_length": 2,
        "min_note_length": 100,
        "max_score": 5
    },

    "s_benchmark_mena": {
        "required_fields": ["position_regionale", "principaux_marches_mena", "note_analyste"],
        "list_fields": ["principaux_marches_mena"],
        "min_list_length": 2,
        "min_note_length": 100,
        "max_score": 5
    },

    "s_benchmark_maghreb": {
        "required_fields": ["position_maghreb", "integration_regionale", "note_analyste"],
        "min_note_length": 100,
        "max_score": 5
    },

    "s_benchmark_ca": {
        "required_fields": ["ca_entreprise", "position_ca", "note_analyste"],
        "numeric_fields": ["ca_entreprise"],
        "min_note_length": 100,
        "max_score": 5
    },

    "s8_synthese_verdict": {
        "required_fields": [
            "verdict_credit", "profil_risque", "raisons_principales",
            "recommandation", "note_finale"
        ],
        "list_fields": ["raisons_principales"],
        "min_list_length": 3,
        "min_note_length": 150,
        "max_score": 5
    },
}


MIN_SECTION_SCORE = 2  # Minimum score to auto-accept


# ══════════════════════════════════════════════════════════════════════════════
# DETAILED SCORING FUNCTION - NEW ADDITION
# ══════════════════════════════════════════════════════════════════════════════

def score_section_detailed(section_id: str, output: Dict) -> Tuple[int, List[str]]:
    """
    Score a section output based on detailed criteria.

    Returns:
        (score, list_of_reasons)
    """
    if not isinstance(output, dict):
        return 1, ["Output n'est pas un dictionnaire JSON valide"]

    if section_id not in SECTION_SCORING_CRITERIA:
        # No criteria defined, use basic validation
        if "note_analyste" not in output:
            return 2, ["Champ 'note_analyste' manquant"]
        return 3, ["Section sans critères spécifiques"]

    criteria = SECTION_SCORING_CRITERIA[section_id]
    score = criteria["max_score"]
    reasons = []

    # Check required fields
    required = criteria.get("required_fields", [])
    missing_required = []
    for field in required:
        if field not in output or not output[field]:
            missing_required.append(field)
            score -= 1

    if missing_required:
        reasons.append(f"Champs requis manquants: {', '.join(missing_required)}")

    # Check numeric fields (should be numbers, not strings)
    numeric_fields = criteria.get("numeric_fields", [])
    for field in numeric_fields:
        if field in output:
            val = output[field]
            if val is not None and not isinstance(val, (int, float)):
                score -= 0.5
                reasons.append(f"Le champ '{field}' doit être un nombre, pas une string")

    # Check list fields (should have minimum items)
    list_fields = criteria.get("list_fields", [])
    min_list_len = criteria.get("min_list_length", 1)
    for field in list_fields:
        if field in output:
            if not isinstance(output[field], list):
                score -= 1
                reasons.append(f"Le champ '{field}' doit être une liste")
            elif len(output[field]) < min_list_len:
                score -= 0.5
                reasons.append(f"Le champ '{field}' doit avoir au moins {min_list_len} éléments")

    # Check nested object fields (e.g., risques array)
    if "risk_required_fields" in criteria and "risques" in output:
        for i, risk in enumerate(output.get("risques", [])):
            missing_risk_fields = []
            for req_field in criteria["risk_required_fields"]:
                if req_field not in risk or not risk[req_field]:
                    missing_risk_fields.append(req_field)
            if missing_risk_fields:
                score -= 0.3
                reasons.append(f"Risque {i+1}: champs manquants ({', '.join(missing_risk_fields)})")

    if "atout_required_fields" in criteria and "atouts" in output:
        for i, atout in enumerate(output.get("atouts", [])):
            missing_atout_fields = []
            for req_field in criteria["atout_required_fields"]:
                if req_field not in atout or not atout[req_field]:
                    missing_atout_fields.append(req_field)
            if missing_atout_fields:
                score -= 0.3
                reasons.append(f"Atout {i+1}: champs manquants ({', '.join(missing_atout_fields)})")

    # Check note_analyste length
    min_note_len = criteria.get("min_note_length", 0)
    if "note_analyste" in output:
        note = output["note_analyste"]
        if isinstance(note, str) and len(note) < min_note_len:
            score -= 0.5
            reasons.append(f"Note analyste trop courte (min {min_note_len} caractères, actuel: {len(note)})")

    # Cap score at 1 minimum and max_score maximum
    score = max(1, min(criteria["max_score"], score))

    return int(score), reasons


# ══════════════════════════════════════════════════════════════════════════════
# ENHANCED EVALUATE_SECTION - REPLACES YOUR EXISTING ONE
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_section(section_id: str, section_title: str, output) -> dict:
    """
    Enhanced evaluation that uses detailed scoring criteria.

    Returns:
        {
            "score": int (1-5),
            "pass": bool (score >= MIN_SECTION_SCORE),
            "reasons": [list of issues],
            "feedback": str
        }
    """
    # Use detailed scoring
    score, reasons = score_section_detailed(section_id, output)

    # Determine if passed
    passed = score >= MIN_SECTION_SCORE

    # Generate feedback
    if passed:
        if score == 5:
            feedback = "✓ Section excellente - tous les critères respectés"
        elif score == 4:
            feedback = "✓ Section de bonne qualité avec quelques améliorations mineures possibles"
        else:
            feedback = "✓ Section acceptable - critères de base respectés"
    else:
        feedback = f"✗ Section rejetée (score {score}/{MIN_SECTION_SCORE}) - corrections nécessaires"

    return {
        "score": score,
        "pass": passed,
        "reasons": reasons,
        "feedback": feedback
    }


# ══════════════════════════════════════════════════════════════════════════════
# IMPROVE_PROMPT - KEEP YOUR EXISTING IMPLEMENTATION
# ══════════════════════════════════════════════════════════════════════════════

def improve_prompt(
    section_id: str,
    section_title: str,
    current_prompt: str,
    last_output,
    reasons: List[str],
    human_feedback: str,
    attempt: int
) -> str:
    """
    Improve prompt based on evaluation reasons.

    You can keep your existing implementation or use this enhanced version.
    """
    # Build improvement instructions
    improvements = []

    if "manquants" in " ".join(reasons):
        improvements.append("AJOUTE tous les champs requis dans le JSON")

    if "nombre" in " ".join(reasons):
        improvements.append("Les champs numériques doivent être des NOMBRES (int/float), pas des strings")

    if "liste" in " ".join(reasons):
        improvements.append("Les champs de type liste doivent contenir plusieurs éléments")

    if "courte" in " ".join(reasons):
        improvements.append("La note_analyste doit être plus détaillée et substantielle")

    # Add specific reasons
    for reason in reasons[:3]:
        improvements.append(f"- {reason}")

    # Enhanced prompt with corrections
    enhanced_prompt = f"""{current_prompt}

═══════════════════════════════════════════════════════════════
⚠️ CORRECTIONS REQUISES (Tentative {attempt}):
═══════════════════════════════════════════════════════════════

PROBLÈMES IDENTIFIÉS:
{chr(10).join(f"  ✗ {imp}" for imp in improvements)}

INSTRUCTIONS STRICTES:
1. Génère UNIQUEMENT du JSON valide
2. Inclus TOUS les champs requis
3. Les valeurs numériques doivent être des numbers (pas des strings)
4. Les listes doivent avoir le nombre minimum d'éléments
5. La note_analyste doit être substantielle et analytique

EXEMPLE DE STRUCTURE ATTENDUE:
{{
  "champ_texte": "valeur en string",
  "champ_numerique": 12345,  // PAS "12345"
  "champ_liste": ["item1", "item2", "item3"],
  "note_analyste": "Analyse détaillée de minimum 100 caractères..."
}}
"""

    return enhanced_prompt


# ══════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY
# ══════════════════════════════════════════════════════════════════════════════

# If you had other functions in your old evaluation.py, keep them here
# Just add them after this comment

###def evaluate_section(section_id: str, section_title: str, content) -> dict:
    rubric      = SECTION_RUBRICS.get(section_id, "Évalue la qualité générale (1-5).")
    content_str = (json.dumps(content, ensure_ascii=False, indent=2)
                   if isinstance(content, (dict, list)) else str(content))
    client = get_openai_client()
    prompt = EVALUATOR_PROMPT.format(section_title=section_title, rubric=rubric, content=content_str[:3000])
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=500,
        )
        raw = clean_response(resp.choices[0].message.content)
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except:
        return {"score": 3, "pass": True, "reasons": [], "suggestions": []}

###def improve_prompt(section_id, section_title, original_prompt, failed_output,
                  ### failure_reasons, human_feedback, n_tries) -> str:
    print(f"  {Fore.YELLOW}[PE] Amélioration du prompt pour {section_title}…{Style.RESET_ALL}")
    client = get_openai_client()
    prompt = PROMPT_ENGINEER_PROMPT.format(
        section_title=section_title, n_tries=n_tries,
        original_prompt=original_prompt[:1500],
        failed_output=(json.dumps(failed_output, ensure_ascii=False)[:1000] if failed_output else "N/A"),
        failure_reasons="\n".join(f"- {r}" for r in failure_reasons),
        human_feedback=human_feedback or "Aucun feedback humain fourni.",
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4, max_tokens=1500,
        )
        improved = resp.choices[0].message.content.strip()
        print(f"  {Fore.GREEN}✓ Prompt amélioré{Style.RESET_ALL}")
        return improved
    except Exception as e:
        print(f"  {Fore.RED}[PE ERROR] {e}{Style.RESET_ALL}")
        return original_prompt######