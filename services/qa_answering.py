#!/usr/bin/env python3
import json, re
from colorama import Fore, Style
from core.config import  OPENAI_MODEL
from core.openai_client import get_openai_client , clean_response
QA_ANSWER_PROMPT = """
Tu es un analyste disposant du contenu web suivant sur une entreprise tunisienne.
Réponds à chaque question avec :
  - Une réponse précise basée UNIQUEMENT sur le contenu fourni
  -- Un niveau de confiance :
    * "élevé" (trouvé directement avec détails)
    * "moyen" (trouvé partiellement OU inféré de façon raisonnable)  ← MORE LENIENT
    * "faible" (aucune information pertinente)
  - Si non trouvé : répondre exactement "Information non disponible dans les sources"

CONTENU WEB DISPONIBLE :
{corpus}

QUESTIONS À RÉPONDRE :
{questions_text}

Retourne UNIQUEMENT un JSON :
{{
  "answers": [
    {{
      "id": "G01",
      "question": "...",
      "answer": "...",
      "confidence": "élevé|moyen|faible",
      "source_url": "url ou null"
    }},
    ...
  ]
}}
"""

def answer_questions(questions: list, corpus: str, pipeline_logger=None) -> list:
    if not questions:
        return []
    print(f"  {Fore.CYAN}[QA] Réponse aux {len(questions)} questions…{Style.RESET_ALL}")
    questions_text = "\n".join(f"[{q['id']}] {q['question']}" for q in questions)
    client = get_openai_client()
    prompt = QA_ANSWER_PROMPT.format(corpus=corpus[:12000], questions_text=questions_text)
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=4000,
        )
        raw = clean_response(resp.choices[0].message.content)
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        answers = json.loads(raw).get("answers", [])
        high   = sum(1 for a in answers if a.get("confidence") == "élevé")
        medium = sum(1 for a in answers if a.get("confidence") == "moyen")
        low    = sum(1 for a in answers if a.get("confidence") == "faible")
        print(f"  {Fore.GREEN}✓ Confiance : {high} élevé / {medium} moyen / {Fore.YELLOW}{low} faible{Style.RESET_ALL}")
        if pipeline_logger: pipeline_logger.log_answers(answers)
        return answers
    except Exception as e:
        print(f"  {Fore.RED}[QA ERROR] {e}{Style.RESET_ALL}")
        return []

def compute_data_confidence(answers: list) -> dict:
    if not answers:
        return {"level": "insuffisant", "flag": True, "pct_low": 100}
    total   = len(answers)
    low     = sum(1 for a in answers if a.get("confidence") == "faible")
    pct_low = round(100 * low / total, 1)
    level = "insuffisant" if pct_low > 60 else "partiel" if pct_low > 50 else "satisfaisant"

    return {"level": level, "flag": pct_low > 60, "pct_low": pct_low, "total": total, "low": low}

def filter_answers_for_section(answers: list, section_id: str) -> list:
    return [a for a in answers if section_id in (a.get("section_cible", ""))]

def format_qa_for_prompt(answers: list) -> str:
    if not answers:
        return "Aucune information disponible."
    lines = []
    for a in answers:
        conf  = a.get("confidence", "")
        label = {"élevé": "✓", "moyen": "~", "faible": "?"}.get(conf, "?")
        lines.append(f"[{label}] Q: {a.get('question', '')}\n    R: {a.get('answer', '')}")
    return "\n\n".join(lines)