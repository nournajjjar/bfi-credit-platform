# services/sections.py - COMPLETE MERGED VERSION

"""
Section prompt templates and helper functions for report generation.
MERGED VERSION: Contains improved prompts + all required helper functions.
"""

# ══════════════════════════════════════════════════════════════════════════════
# IMPROVED SECTION PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

SECTION_PROMPTS = {
    # ── SECTION 1: Profil Opérationnel ──────────────────────────────────────
    "s1_profil_operationnel": """
Tu es un analyste financier tunisien expert. Génère un profil opérationnel structuré.

**DONNÉES APII:**
{apii_data}

**DONNÉES WEB & RECHERCHE:**
{qa}

**INSTRUCTIONS:**
1. Extrais les informations RÉELLES des données APII (pas de "Non renseigné")
2. Complète avec les données web
3. Format JSON strict avec ces champs:
   - activite_principale (string)
   - produits_services (string)
   - marches_servis (string)
   - regime_export (string: "Totalement exportateur" | "Partiellement exportateur" | "Non exportateur")
   - effectif (number ou null)
   - annee_creation (number ou null)
   - sites_production (string ou null)
   - certifications (string ou null)
   - presence_internationale (string ou null)
   - note_analyste (string)

**RÈGLES CRITIQUES:**
- Si une donnée n'existe pas → utilise null (pas "Non renseigné")
- Les nombres doivent être des numbers JSON, pas des strings
- La note_analyste doit être un paragraphe analytique de 2-3 phrases

**EXEMPLE DE SORTIE:**
{{
  "activite_principale": "Fabrication d'articles sans couture (lingerie, shapewear, sportswear)",
  "produits_services": "Lingerie sans couture, shapewear, sportswear, outwear",
  "marches_servis": "Tunisie, France, Italie, Allemagne, Belgique",
  "regime_export": "Partiellement exportateur",
  "effectif": 250,
  "annee_creation": 2009,
  "sites_production": "Usine principale à Nabeul",
  "certifications": null,
  "presence_internationale": "Exportation vers Europe",
  "note_analyste": "L'entreprise se distingue par son intégration verticale et sa maîtrise de la chaîne de production. La diversification géographique vers l'Europe démontre une stratégie d'internationalisation réussie."
}}

Génère UNIQUEMENT le JSON valide, sans markdown ni explications.
""",

    # ── SECTION 2: Analyse Financière ─────────────────────────────────────
    "s2_analyse_financiere": """
Tu es un analyste financier expert. Génère une analyse financière COMPLÈTE avec les VRAIES VALEURS des PDFs.

**DONNÉES APII:**
{apii_data}

**PDF BILAN ACTIF (JSON):**
{pdf_bilan_actif}

**PDF BILAN PASSIF (JSON):**
{pdf_bilan_passif}

**PDF COMPTE DE RÉSULTAT (CPC) (JSON):**
{pdf_cpc}

**PDF TABLEAU FLUX TRÉSORERIE (TFT) (JSON):**
{pdf_tft}

**DONNÉES WEB & RECHERCHE:**
{qa}

**INSTRUCTIONS CRITIQUES:**
1. **PARSE LES JSON PDF** - Extrais les valeurs NUMÉRIQUES réelles
2. **NE GÉNÈRE PAS de placeholders** comme "Valeur du résultat net (pdf_cpc)"
3. **Utilise les vraies valeurs** des PDFs ou null si manquant
4. **Calcule les ratios** si possible

**EXTRACTION DES VALEURS:**
- chiffre_affaires: Cherche dans pdf_cpc → "chiffre_affaires" ou "R01" ou "ventes"
- resultat_net: Cherche dans pdf_cpc → "resultat_net" ou "RN" ou "bénéfice net"
- total_actif: Cherche dans pdf_bilan_actif → "total_actif" ou "total"
- capitaux_propres: Cherche dans pdf_bilan_passif → "capitaux_propres" ou "CP01" ou "capital_social"
- tresorerie: Cherche dans pdf_tft → "tresorerie" ou "flux_exploitation"

**FORMAT DE SORTIE (JSON STRICT):**
{{
  "chiffre_affaires": 4250000,
  "evolution_ca": "+12.5% vs N-1",
  "marge_brute": 35.2,
  "resultat_net": 594371,
  "total_actif": 8500000,
  "capitaux_propres": 4250400,
  "endettement_net": 1200000,
  "ratio_endettement": 28.2,
  "capacite_remboursement": 2.3,
  "tresorerie": 884721,
  "fiabilite_donnees": "Données extraites des états financiers 2024",
  "note_analyste": "L'entreprise présente une structure financière solide avec des capitaux propres significatifs et une trésorerie positive. Le résultat net de 594k DT témoigne d'une rentabilité satisfaisante."
}}

**SI UNE VALEUR MANQUE:**
- Utilise null (pas "Non disponible")
- NE GÉNÈRE JAMAIS "Valeur du..." ou autres placeholders
- Mentionne dans note_analyste les données manquantes

**EXEMPLES DE CE QU'IL NE FAUT PAS FAIRE:**
❌ "resultat_net": "Valeur du résultat net (pdf_cpc)"
❌ "total_actif": "Valeur du total de l'actif"
❌ "chiffre_affaires": "Non disponible"

**EXEMPLES DE CE QU'IL FAUT FAIRE:**
✅ "resultat_net": 594371
✅ "total_actif": null
✅ "chiffre_affaires": 4250000

Génère UNIQUEMENT le JSON valide avec les VRAIES VALEURS NUMÉRIQUES.
""",

    # ── SECTION 3: Positionnement Marché ───────────────────────────────────
    "s3_positionnement_marche": """
Tu es un analyste de marché expert. Génère une analyse du positionnement concurrentiel.

**DONNÉES APII:**
{apii_data}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "position_concurrentielle": "Leader" | "Challenger" | "Suiveur" | "Niche",
  "principaux_concurrents": ["Concurrent A", "Concurrent B"],
  "avantages_competitifs": ["Avantage 1", "Avantage 2"],
  "part_marche_estimee": "15%" ou null,
  "clients_principaux": "Description" ou null,
  "fournisseurs_principaux": "Description" ou null,
  "dependances_strategiques": "Description" ou null,
  "dynamique_sectorielle": "Description de la dynamique du secteur",
  "note_analyste": "Analyse en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 4: Facteurs de Risque ──────────────────────────────────────
    "s4_facteurs_risque": """
Tu es un analyste de risque expert. Identifie les risques de crédit CONCRETS et MESURABLES.

**DONNÉES APII:**
{apii_data}

**POSITIONNEMENT:**
{positioning}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "risques": [
    {{
      "risque": "Titre court du risque",
      "description": "Description détaillée",
      "severite": "Élevé" | "Modéré" | "Faible",
      "source": "APII" | "Web" | "Analyse"
    }}
  ],
  "risque_global": "Élevé" | "Modéré" | "Faible",
  "note_analyste": "Synthèse en 2-3 phrases"
}}

**TYPES DE RISQUES À IDENTIFIER:**
1. Risques financiers (endettement, trésorerie, rentabilité)
2. Risques opérationnels (concentration clients, fournisseurs)
3. Risques de marché (concurrence, substitution)
4. Risques réglementaires
5. Risques de gouvernance

Génère UNIQUEMENT le JSON valide avec au moins 3 risques.
""",

    # ── SECTION 5: Facteurs Favorables ─────────────────────────────────────
    "s5_facteurs_favorables": """
Tu es un analyste crédit. Identifie les forces et atouts CONCRETS de l'entreprise.

**DONNÉES APII:**
{apii_data}

**POSITIONNEMENT:**
{positioning}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "atouts": [
    {{
      "atout": "Titre court",
      "description": "Description détaillée",
      "preuve": "Source de la preuve"
    }}
  ],
  "note_analyste": "Synthèse en 2-3 phrases"
}}

**TYPES D'ATOUTS À IDENTIFIER:**
1. Solidité financière (fonds propres, trésorerie positive)
2. Position de marché (leader, exportateur)
3. Qualité de la gouvernance
4. Innovation et certifications
5. Diversification (produits, marchés, clients)

Génère UNIQUEMENT le JSON valide avec au moins 3 atouts.
""",

    # ── SECTION 6: Gouvernance ─────────────────────────────────────────────
    "s6_gouvernance_management": """
Tu es un analyste gouvernance. Évalue la qualité de la gouvernance et du management.

**DONNÉES APII:**
{apii_data}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "structure_actionnariat": "Description de l'actionnariat",
  "dirigeants_cles": "Noms et fonctions" ou null,
  "appartenance_groupe": "Nom du groupe" ou null,
  "filiales": "Liste des filiales" ou null,
  "transparence_financiere": "Élevée" | "Moyenne" | "Faible",
  "notation_gouvernance": "Excellente" | "Solide" | "Acceptable" | "Faible",
  "note_analyste": "Analyse en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 7: Benchmark Sectoriel ─────────────────────────────────────
    "s7_benchmark_sectoriel": """
Tu es un analyste sectoriel. Compare l'entreprise avec son secteur en Tunisie.

**STATISTIQUES SECTEUR:**
{sector_stats}

**POSITIONNEMENT:**
{positioning}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "position_capital": "Au-dessus de la médiane" | "Dans la médiane" | "En-dessous de la médiane",
  "position_effectif": "Au-dessus de la médiane" | "Dans la médiane" | "En-dessous de la médiane",
  "position_age": "Plus ancien que la moyenne" | "Âge moyen" | "Plus récent que la moyenne",
  "comparaison_export": "Plus exportateur que la moyenne" | "Dans la moyenne" | "Moins exportateur",
  "comparaison_web": "Meilleure présence web" | "Présence moyenne" | "Faible présence web",
  "note_analyste": "Analyse comparative en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 8: Benchmark Leaders ───────────────────────────────────────
    "s_benchmark_leaders": """
Tu es un analyste concurrentiel. Identifie les leaders du secteur et compare.

**STATISTIQUES SECTEUR:**
{sector_stats}

**DONNÉES APII:**
{apii_data}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "leaders_secteur": ["Leader 1", "Leader 2", "Leader 3"],
  "parts_marche_estimees": {{
    "Leader 1": "30%",
    "Leader 2": "25%",
    "Entreprise": "5%"
  }},
  "avantages_leaders": ["Avantage 1", "Avantage 2"],
  "points_differenciation": ["Point 1", "Point 2"],
  "note_analyste": "Analyse comparative avec leaders en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 9: Benchmark International ─────────────────────────────────
    "s_benchmark_international": """
Tu es un analyste international. Compare avec des entreprises similaires à l'étranger.

**DONNÉES APII:**
{apii_data}

**SECTEUR:**
{label_secteur}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "pays_comparables": ["Pays 1", "Pays 2"],
  "entreprises_reference": ["Entreprise 1 (Pays)", "Entreprise 2 (Pays)"],
  "ecarts_competitivite": "Description des écarts",
  "opportunites_export": ["Marché 1", "Marché 2"],
  "menaces_importation": ["Menace 1", "Menace 2"],
  "note_analyste": "Analyse internationale en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 10: Benchmark MENA ─────────────────────────────────────────
    "s_benchmark_mena": """
Tu es un analyste MENA (Middle East & North Africa). Compare avec la région.

**DONNÉES APII:**
{apii_data}

**SECTEUR:**
{label_secteur}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "position_regionale": "Leader régional" | "Acteur établi" | "Challenger" | "Emergent",
  "principaux_marches_mena": ["Marché 1", "Marché 2"],
  "concurrents_mena": ["Concurrent 1 (Pays)", "Concurrent 2 (Pays)"],
  "avantages_tunisie": ["Avantage 1", "Avantage 2"],
  "defis_region": ["Défi 1", "Défi 2"],
  "note_analyste": "Analyse MENA en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",
"s_benchmark_national": """
Tu es un analyste sectoriel tunisien. Génère un benchmark national comparant l'entreprise à son secteur.

**DONNÉES APII:**
{apii_data}

**STATISTIQUES SECTEUR:**
{sector_stats}

**POSITIONNEMENT:**
{positioning}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "total_entreprises_secteur": 120,
  "position_capital": "Au-dessus de la médiane",
  "position_effectif": "Dans la médiane",
  "position_age": "Plus ancien que la moyenne",
  "comparaison_export": "Plus exportateur que la moyenne",
  "top_gouvernorats": ["Tunis", "Sfax", "Sousse"],
  "note_analyste": "Analyse comparative nationale en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",
    # ── SECTION 11: Benchmark Maghreb ──────────────────────────────────────
    "s_benchmark_maghreb": """
Tu es un analyste Maghreb. Compare avec Tunisie, Maroc, Algérie.

**DONNÉES APII:**
{apii_data}

**SECTEUR:**
{label_secteur}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "position_maghreb": "Leader maghrébin" | "Acteur majeur" | "Présence modérée" | "Faible présence",
  "comparaison_maroc": "Description vs Maroc",
  "comparaison_algerie": "Description vs Algérie",
  "integration_regionale": "Forte" | "Moyenne" | "Faible",
  "opportunites_maghreb": ["Opportunité 1", "Opportunité 2"],
  "note_analyste": "Analyse Maghreb en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 12: Benchmark CA ───────────────────────────────────────────
    "s_benchmark_ca": """
Tu es un analyste financier. Compare le chiffre d'affaires avec le secteur.

**DONNÉES APII:**
{apii_data}

**CHIFFRE D'AFFAIRES ENTREPRISE:**
{chiffre_affaires} DT

**RÉSULTAT NET:**
{resultat_net} DT

**STATISTIQUES SECTEUR:**
{sector_stats}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "ca_entreprise": 4250000,
  "ca_median_secteur": 2000000,
  "position_ca": "Top 10%" | "Top 25%" | "Médiane" | "En-dessous médiane",
  "croissance_ca": "+12.5% vs N-1" ou null,
  "rentabilite": "Marge nette: 14%" ou null,
  "comparaison_peers": "Description comparative",
  "note_analyste": "Analyse CA en 2-3 phrases"
}}

**IMPORTANT:** Utilise les VRAIES VALEURS numériques, pas des placeholders!

Génère UNIQUEMENT le JSON valide.
""",

    # ── SECTION 13: Synthèse & Verdict ─────────────────────────────────────
    "s8_synthese_verdict": """
Tu es un analyste crédit senior. Génère le verdict final de crédit.

**DONNÉES APII:**
{apii_data}

**SYNTHÈSE FINANCIÈRE:**
{financial_summary}

**SYNTHÈSE RISQUES:**
{risks_summary}

**SYNTHÈSE ATOUTS:**
{strengths_summary}

**DONNÉES WEB & RECHERCHE:**
{qa}

**FORMAT DE SORTIE (JSON):**
{{
  "verdict_credit": "Favorable" | "Acceptable" | "Sous surveillance" | "Défavorable" | "Réservé",
  "profil_risque": "Faible" | "Modéré" | "Élevé",
  "solidite_financiere": "Forte" | "Moyenne" | "Faible",
  "maturite_stabilite": "Forte" | "Moyenne" | "Faible",
  "credibilite_marche": "Forte" | "Moyenne" | "Faible",
  "exposition_internationale": "Forte" | "Moyenne" | "Faible",
  "gouvernance": "Excellente" | "Solide" | "Acceptable" | "Faible",
  "raisons_principales": [
    "Raison 1 du verdict",
    "Raison 2 du verdict",
    "Raison 3 du verdict"
  ],
  "recommandation": "Recommandation crédit en 1 phrase",
  "conditions_credit_suggerees": "Conditions suggérées",
  "points_vigilance": [
    "Point de vigilance 1",
    "Point de vigilance 2"
  ],
  "note_finale": "Note synthétique finale en 2-3 phrases"
}}

Génère UNIQUEMENT le JSON valide.
"""
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - REQUIRED BY report.py
# ══════════════════════════════════════════════════════════════════════════════

def generate_s1_identite(company):
    """Generate static identity section from APII data"""
    return {
        "denomination": company.get("denomination", "—"),
        "secteur": company.get("label_secteur", "—"),
        "gouvernorat": company.get("gouvernorat", "—"),
        "regime": company.get("regime", "—"),
        "annee_creation": company.get("entree_production", "—"),
        "capital_dt": company.get("capital", "—"),
        "effectif": company.get("emploi", "—"),
        "source_officielle": "APII - Agence de Promotion de l'Industrie et de l'Innovation"
    }


def generate_s5_benchmark_national(stats, positioning):
    """Generate national benchmark section from statistics"""
    return {
        "total_entreprises_secteur": stats.get("total_companies", "—"),
        "capital_mediane": stats.get("median_capital", "—"),
        "emploi_mediane": stats.get("median_emploi", "—"),
        "pct_exportatrices": stats.get("pct_export", "—"),
        "pct_presence_web": stats.get("pct_web_presence", "—"),
        "age_moyen": stats.get("avg_age", "—"),
        "top_gouvernorats": stats.get("top_gouvernorats", []),
        "position_capital": positioning.get("capital_position", "—"),
        "position_emploi": positioning.get("emploi_position", "—"),
        "position_age": positioning.get("age_position", "—"),
        "export_vs_secteur": positioning.get("export_comparison", "—"),
        "web_vs_secteur": positioning.get("web_comparison", "—"),
    }


def generate_s9_verdict(report_sections):
    """
    Generate verdict section based on all other sections.
    This is typically called after all LLM sections are complete.

    Args:
        report_sections: Dict containing all generated sections

    Returns:
        Dict with verdict information
    """
    # Extract key information from other sections
    financial = report_sections.get("s2_analyse_financiere", {})
    risks = report_sections.get("s4_facteurs_risque", {})
    strengths = report_sections.get("s5_facteurs_favorables", {})
    governance = report_sections.get("s6_gouvernance_management", {})

    # Determine verdict based on sections
    risk_level = risks.get("risque_global", "Modéré")

    if risk_level == "Faible" and len(strengths.get("atouts", [])) >= 3:
        verdict = "Favorable"
    elif risk_level == "Élevé" or len(risks.get("risques", [])) > 5:
        verdict = "Défavorable"
    elif risk_level == "Modéré":
        verdict = "Acceptable"
    else:
        verdict = "Sous surveillance"

    return {
        "verdict_credit": verdict,
        "profil_risque": risk_level,
        "note_finale": f"Verdict {verdict} basé sur l'analyse complète de l'entreprise."
    }


def generate_s10_sources(web_pages):
    """Generate sources section from web search results"""
    return [
        {
            "url": page.get("url", ""),
            "title": page.get("title", "Source web")
        }
        for page in web_pages[:30]  # Top 30 sources
    ]