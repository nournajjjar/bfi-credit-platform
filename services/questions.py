# services/questions.py - OPTIMIZED QUESTION GENERATION



from typing import List, Dict


# ══════════════════════════════════════════════════════════════════════════════
# GENERAL QUESTIONS (20 for manufacturing, 10 for services)
# ══════════════════════════════════════════════════════════════════════════════

GENERAL_QUESTIONS = {
    "manufacturing": [
        # Core business (4 questions)
        {"id": "g_01", "question": "Quels sont les principaux produits fabriqués par {company}?", "section": "s1"},
        {"id": "g_02", "question": "Quels sont les marchés cibles de {company} (local, export)?", "section": "s1"},
        {"id": "g_03", "question": "Quelle est la capacité de production de {company}?", "section": "s1"},
        {"id": "g_04", "question": "Combien d'employés travaillent chez {company}?", "section": "s1"},

        # Financial (3 questions)
        {"id": "g_05", "question": "Quel est le chiffre d'affaires de {company}?", "section": "s2"},
        {"id": "g_06", "question": "Est-ce que {company} est rentable?", "section": "s2"},
        {"id": "g_07", "question": "Quel est le niveau d'endettement de {company}?", "section": "s2"},

        # Market position (3 questions)
        {"id": "g_08", "question": "Qui sont les principaux concurrents de {company}?", "section": "s3"},
        {"id": "g_09", "question": "Quelle est la part de marché de {company}?", "section": "s3"},
        {"id": "g_10", "question": "Quels sont les avantages concurrentiels de {company}?", "section": "s5"},

        # Export (2 questions)
        {"id": "g_11", "question": "Est-ce que {company} exporte? Vers quels pays?", "section": "s1"},
        {"id": "g_12", "question": "Quelle est la part de l'export dans le CA de {company}?", "section": "s1"},

        # Quality & clients (2 questions)
        {"id": "g_13", "question": "Quelles certifications possède {company}?", "section": "s1"},
        {"id": "g_14", "question": "Qui sont les principaux clients de {company}?", "section": "s3"},

        # Innovation (2 questions)
        {"id": "g_15", "question": "Est-ce que {company} investit dans l'innovation?", "section": "s5"},
        {"id": "g_16", "question": "Quels sont les projets de développement de {company}?", "section": "s5"},

        # Governance (2 questions)
        {"id": "g_17", "question": "Qui sont les actionnaires de {company}?", "section": "s6"},
        {"id": "g_18", "question": "Qui dirige {company}?", "section": "s6"},

        # Risks (2 questions)
        {"id": "g_19", "question": "Quels sont les principaux risques pour {company}?", "section": "s4"},
        {"id": "g_20", "question": "Y a-t-il des contentieux impliquant {company}?", "section": "s4"},
    ],

    "services": [
        {"id": "g_01", "question": "Quels services offre {company}?", "section": "s1"},
        {"id": "g_02", "question": "Qui sont les clients de {company}?", "section": "s3"},
        {"id": "g_03", "question": "Quel est le chiffre d'affaires de {company}?", "section": "s2"},
        {"id": "g_04", "question": "Est-ce que {company} est rentable?", "section": "s2"},
        {"id": "g_05", "question": "Qui sont les concurrents de {company}?", "section": "s3"},
        {"id": "g_06", "question": "Quelle est la part de marché de {company}?", "section": "s3"},
        {"id": "g_07", "question": "Combien d'employés travaillent chez {company}?", "section": "s1"},
        {"id": "g_08", "question": "Quels sont les atouts de {company}?", "section": "s5"},
        {"id": "g_09", "question": "Quels sont les risques pour {company}?", "section": "s4"},
        {"id": "g_10", "question": "Qui dirige {company}?", "section": "s6"},
    ],
}


def get_general_questions(source_table: str, label_secteur: str) -> List[Dict]:
    """
    Get general questions based on sector type.
    Returns 20 questions for manufacturing, 10 for services.
    """
    # Determine sector type
    is_manufacturing = any(word in label_secteur.lower()
                          for word in ["industrie", "fabrication", "manufacturing", "production"])

    if is_manufacturing:
        questions = GENERAL_QUESTIONS["manufacturing"]
    else:
        questions = GENERAL_QUESTIONS["services"]

    return [q.copy() for q in questions]


# ══════════════════════════════════════════════════════════════════════════════
# SPECIFIC QUESTIONS (5-7 essential questions only)
# ══════════════════════════════════════════════════════════════════════════════

def get_specific_questions(company: Dict, positioning: Dict) -> List[Dict]:
    """
    Generate 5-7 essential company-specific questions.
    """
    company_name = company.get("denomination", "cette entreprise")
    questions = []
    question_id = 1

    # 1. Core positioning question
    questions.append({
        "id": f"sp_{question_id:02d}",
        "question": f"Comment {company_name} se positionne dans son marché?",
        "section": "s3"
    })
    question_id += 1

    # 2. Competitive advantage
    questions.append({
        "id": f"sp_{question_id:02d}",
        "question": f"Quelle est la stratégie de différenciation de {company_name}?",
        "section": "s5"
    })
    question_id += 1

    # 3. Main competitors
    questions.append({
        "id": f"sp_{question_id:02d}",
        "question": f"Qui sont les 3 principaux concurrents de {company_name}?",
        "section": "s3"
    })
    question_id += 1

    # 4. Export markets (if relevant)
    if positioning.get("is_export", False):
        questions.append({
            "id": f"sp_{question_id:02d}",
            "question": f"Quels sont les principaux marchés d'exportation de {company_name}?",
            "section": "s1"
        })
        question_id += 1
    else:
        questions.append({
            "id": f"sp_{question_id:02d}",
            "question": f"Pourquoi {company_name} ne semble pas exporter?",
            "section": "s4"
        })
        question_id += 1

    # 5. Recent developments
    questions.append({
        "id": f"sp_{question_id:02d}",
        "question": f"Quels sont les développements récents de {company_name}?",
        "section": "s5"
    })
    question_id += 1

    # 6. Financial health (conditional)
    questions.append({
        "id": f"sp_{question_id:02d}",
        "question": f"Quelle est la santé financière de {company_name}?",
        "section": "s2"
    })
    question_id += 1

    # 7. Sector-specific question (only if clearly identifiable)
    secteur = company.get("label_secteur", "").lower()
    if "textile" in secteur or "habillement" in secteur:
        questions.append({
            "id": f"sp_{question_id:02d}",
            "question": f"Quelles sont les certifications textiles de {company_name}?",
            "section": "s1"
        })
    elif "agroalimentaire" in secteur or "alimentaire" in secteur:
        questions.append({
            "id": f"sp_{question_id:02d}",
            "question": f"Quelles sont les certifications alimentaires de {company_name}?",
            "section": "s1"
        })
    elif "chimie" in secteur or "pharmaceutique" in secteur:
        questions.append({
            "id": f"sp_{question_id:02d}",
            "question": f"Quelles sont les normes de sécurité respectées par {company_name}?",
            "section": "s1"
        })

    # Return max 7 questions
    return questions[:7]


# ══════════════════════════════════════════════════════════════════════════════
# MONOPOLY DETECTION (Bilingual - French + English)
# ══════════════════════════════════════════════════════════════════════════════

def detect_monopoly_signals(corpus: str) -> Dict:
    """
    NLP-based monopoly detection using bilingual keyword matching.
    Detects market structure: Monopole, Oligopole, or Concurrence.
    """
    if not corpus or len(corpus) < 100:
        return {
            "structure": "Non déterminée",
            "monopoly_score": 0,
            "competition_score": 0,
            "oligopoly_score": 0,
            "confidence": "Faible",
            "total_signals_detected": 0,
        }

    corpus_lower = corpus.lower()

    # ── MONOPOLY KEYWORDS (French + English) ──
    monopoly_keywords = {
        "leader": [
            # French
            "leader du marché", "leader incontesté", "position dominante",
            "acteur principal", "seul acteur", "unique acteur",
            # English
            "market leader", "dominant player", "leading company",
            "sole provider", "only player", "undisputed leader"
        ],
        "dominance": [
            # French
            "domination", "dominer le marché", "monopole", "monopolistique",
            "position monopolistique", "contrôle du marché",
            # English
            "dominance", "dominate", "monopoly", "monopolistic",
            "market control", "dominant position"
        ],
        "exclusivity": [
            # French
            "exclusivité", "exclusif", "seul à proposer", "seul à offrir",
            "unique fournisseur", "sans concurrent",
            # English
            "exclusive", "exclusivity", "sole supplier", "only provider",
            "no competitors", "unique supplier"
        ],
        "barriers": [
            # French
            "barrières à l'entrée", "barrières élevées", "difficile d'entrer",
            "investissement initial important", "licence exclusive",
            # English
            "barriers to entry", "high barriers", "difficult to enter",
            "exclusive license", "significant capital required"
        ],
        "pricing_power": [
            # French
            "fixer les prix", "contrôle des prix", "pouvoir de fixation",
            "déterminer les tarifs",
            # English
            "price setter", "pricing power", "control prices",
            "set prices", "determine prices"
        ],
    }

    # ── OLIGOPOLY KEYWORDS (French + English) ──
    oligopoly_keywords = [
        # French
        "oligopole", "quelques acteurs", "petit nombre d'entreprises",
        "2 ou 3 acteurs", "duopole", "triopole", "acteurs principaux",
        "top 3", "top 5", "principales entreprises",
        # English
        "oligopoly", "few players", "small number of firms",
        "duopoly", "top 3", "top 5", "main players",
        "leading firms", "major players", "key competitors",
        "limited competition", "established players"
    ]

    # ── COMPETITION KEYWORDS (French + English) ──
    competition_keywords = {
        "multiple_players": [
            # French
            "plusieurs acteurs", "nombreux concurrents", "marché fragmenté",
            "dizaines d'entreprises", "centaines d'acteurs",
            # English
            "many players", "numerous competitors", "fragmented market",
            "dozens of companies", "hundreds of players", "crowded market"
        ],
        "competition": [
            # French
            "concurrence", "concurrentiel", "compétitif", "rivalité",
            "guerre des prix", "bataille pour les parts de marché",
            # English
            "competition", "competitive", "rivalry", "compete",
            "price war", "battle for market share", "fierce competition",
            "highly competitive"
        ],
        "market_share": [
            # French
            "part de marché", "perte de parts", "gagner des parts",
            "faible part de marché", "parts fragmentées",
            # English
            "market share", "lose share", "gain share",
            "small market share", "fragmented shares", "share loss"
        ],
        "substitutes": [
            # French
            "produits de substitution", "alternatives", "remplaçants",
            "concurrents directs", "concurrents indirects",
            # English
            "substitutes", "alternatives", "replacement products",
            "direct competitors", "indirect competitors"
        ],
        "price_competition": [
            # French
            "prix compétitifs", "guerre des prix", "alignement des prix",
            "prix similaires", "stratégie de prix",
            # English
            "competitive prices", "price war", "price matching",
            "similar prices", "pricing strategy", "price competition"
        ],
    }

    # ── SCANNING ──
    monopoly_signals_found = []
    monopoly_score = 0

    for category, keywords in monopoly_keywords.items():
        for keyword in keywords:
            if keyword in corpus_lower:
                monopoly_signals_found.append(keyword)
                monopoly_score += 1

    competition_signals_found = []
    competition_score = 0

    for category, keywords in competition_keywords.items():
        for keyword in keywords:
            if keyword in corpus_lower:
                competition_signals_found.append(keyword)
                competition_score += 1

    oligopoly_signals_found = []
    oligopoly_score = 0

    for keyword in oligopoly_keywords:
        if keyword in corpus_lower:
            oligopoly_signals_found.append(keyword)
            oligopoly_score += 1

    # ── CLASSIFICATION ──
    total_signals = monopoly_score + competition_score + oligopoly_score

    if total_signals == 0:
        structure = "Non déterminée"
        confidence = "Faible"
    elif monopoly_score > competition_score and monopoly_score > oligopoly_score:
        structure = "Monopole"
        confidence = "Élevée" if monopoly_score >= 5 else "Modérée"
    elif oligopoly_score >= monopoly_score and oligopoly_score >= competition_score:
        structure = "Oligopole"
        confidence = "Élevée" if oligopoly_score >= 3 else "Modérée"
    elif competition_score > monopoly_score:
        structure = "Concurrence"
        confidence = "Élevée" if competition_score >= 5 else "Modérée"
    else:
        structure = "Non déterminée"
        confidence = "Faible"

    # Contextual adjustments
    if monopoly_score >= 3 and competition_score >= 3:
        structure = "Oligopole"
        confidence = "Modérée"

    return {
        "structure": structure,
        "monopoly_score": monopoly_score,
        "competition_score": competition_score,
        "oligopoly_score": oligopoly_score,
        "monopoly_signals_found": monopoly_signals_found[:5],
        "competition_signals_found": competition_signals_found[:5],
        "oligopoly_signals_found": oligopoly_signals_found[:3],
        "confidence": confidence,
        "total_signals_detected": total_signals,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def format_question_with_company(question_template: str, company_name: str) -> str:
    """Replace {company} placeholder with actual company name"""
    return question_template.replace("{company}", company_name)


def get_all_questions(company: Dict, positioning: Dict) -> List[Dict]:
    """
    Get all questions (general + specific) for a company.
    Returns ~26 questions total (20 general + 6 specific).
    """
    source_table = company.get("source_table", "")
    label_secteur = company.get("label_secteur", "")
    company_name = company.get("denomination", "")

    # Get general questions
    general_q = get_general_questions(source_table, label_secteur)

    # Format with company name
    for q in general_q:
        q["question"] = format_question_with_company(q["question"], company_name)

    # Get specific questions
    specific_q = get_specific_questions(company, positioning)

    # Combine
    all_questions = general_q + specific_q

    return all_questions

# ── MONOPOLY DETECTION (From previous implementation) ─────────────────────────

def detect_monopoly_signals(corpus: str) -> dict:
    """
    NLP-based monopoly detection using keyword matching (French + English).
    """
    corpus_lower = corpus.lower()

    # FRENCH + ENGLISH keywords
    monopoly_keywords = {
        "leader": [
            # French
            "leader du marché", "leader incontesté", "position dominante",
            "acteur principal", "seul acteur", "unique acteur",
            # English
            "market leader", "dominant player", "leading company",
            "sole provider", "only player", "undisputed leader"
        ],
        "dominance": [
            # French
            "domination", "dominer le marché", "monopole", "monopolistique",
            "position monopolistique", "contrôle du marché",
            # English
            "dominance", "dominate", "monopoly", "monopolistic",
            "market control", "dominant position"
        ],
        "exclusivity": [
            # French
            "exclusivité", "exclusif", "seul à proposer", "seul à offrir",
            "unique fournisseur", "sans concurrent",
            # English
            "exclusive", "exclusivity", "sole supplier", "only provider",
            "no competitors", "unique supplier"
        ],
        "barriers": [
            # French
            "barrières à l'entrée", "barrières élevées", "difficile d'entrer",
            "investissement initial important", "licence exclusive",
            # English
            "barriers to entry", "high barriers", "difficult to enter",
            "exclusive license", "significant capital required"
        ],
        "pricing_power": [
            # French
            "fixer les prix", "contrôle des prix", "pouvoir de fixation",
            "déterminer les tarifs",
            # English
            "price setter", "pricing power", "control prices",
            "set prices", "determine prices"
        ],
    }

    oligopoly_keywords = [
        # French
        "oligopole", "quelques acteurs", "petit nombre d'entreprises",
        "2 ou 3 acteurs", "duopole", "triopole", "acteurs principaux",
        "top 3", "top 5", "principales entreprises",
        # English
        "oligopoly", "few players", "small number of firms",
        "duopoly", "top 3", "top 5", "main players",
        "leading firms", "major players", "key competitors"
    ]

    competition_keywords = {
        "multiple_players": [
            # French
            "plusieurs acteurs", "nombreux concurrents", "marché fragmenté",
            "dizaines d'entreprises", "centaines d'acteurs",
            # English
            "many players", "numerous competitors", "fragmented market",
            "dozens of companies", "hundreds of players", "crowded market"
        ],
        "competition": [
            # French
            "concurrence", "concurrentiel", "compétitif", "rivalité",
            "guerre des prix", "bataille pour les parts de marché",
            # English
            "competition", "competitive", "rivalry", "compete",
            "price war", "battle for market share", "fierce competition"
        ],
        "market_share": [
            # French
            "part de marché", "perte de parts", "gagner des parts",
            "faible part de marché", "parts fragmentées",
            # English
            "market share", "lose share", "gain share",
            "small market share", "fragmented shares", "share loss"
        ],
        "substitutes": [
            # French
            "produits de substitution", "alternatives", "remplaçants",
            "concurrents directs", "concurrents indirects",
            # English
            "substitutes", "alternatives", "replacement products",
            "direct competitors", "indirect competitors"
        ],
        "price_competition": [
            # French
            "prix compétitifs", "guerre des prix", "alignement des prix",
            "prix similaires", "stratégie de prix",
            # English
            "competitive prices", "price war", "price matching",
            "similar prices", "pricing strategy", "price competition"
        ],
    }

    # Scanning
    monopoly_signals_found = []
    monopoly_score = 0

    for category, keywords in monopoly_keywords.items():
        for keyword in keywords:
            if keyword in corpus_lower:
                monopoly_signals_found.append(keyword)
                monopoly_score += 1

    competition_signals_found = []
    competition_score = 0

    for category, keywords in competition_keywords.items():
        for keyword in keywords:
            if keyword in corpus_lower:
                competition_signals_found.append(keyword)
                competition_score += 1

    oligopoly_signals_found = []
    oligopoly_score = 0

    for keyword in oligopoly_keywords:
        if keyword in corpus_lower:
            oligopoly_signals_found.append(keyword)
            oligopoly_score += 1

    # Classification
    total_signals = monopoly_score + competition_score + oligopoly_score

    if total_signals == 0:
        structure = "Non déterminée"
        confidence = "Faible"
    elif monopoly_score > competition_score and monopoly_score > oligopoly_score:
        structure = "Monopole"
        confidence = "Élevée" if monopoly_score >= 5 else "Modérée"
    elif oligopoly_score >= monopoly_score and oligopoly_score >= competition_score:
        structure = "Oligopole"
        confidence = "Élevée" if oligopoly_score >= 3 else "Modérée"
    elif competition_score > monopoly_score:
        structure = "Concurrence"
        confidence = "Élevée" if competition_score >= 5 else "Modérée"
    else:
        structure = "Non déterminée"
        confidence = "Faible"

    # Contextual adjustments
    if monopoly_score >= 3 and competition_score >= 3:
        structure = "Oligopole"
        confidence = "Modérée"

    return {
        "structure": structure,
        "monopoly_score": monopoly_score,
        "competition_score": competition_score,
        "oligopoly_score": oligopoly_score,
        "monopoly_signals_found": monopoly_signals_found[:5],
        "competition_signals_found": competition_signals_found[:5],
        "oligopoly_signals_found": oligopoly_signals_found[:3],
        "confidence": confidence,
        "total_signals_detected": total_signals,
    }