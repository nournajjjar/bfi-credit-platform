"""
Layer 3 (LLM) — Génération de sections avec boucle évaluation + tracking.

NOTE: Le feedback humain interactif (input()) a été SUPPRIMÉ pour la compatibilité API.
      En mode API, chaque section est acceptée automatiquement dès que le score >= MIN_SECTION_SCORE.
      Le tracker enregistre quand même tous les essais pour audit.
"""

import json
import re

from core.config import OPENAI_MODEL, MAX_SECTION_RETRIES
from core.openai_client import get_openai_client, clean_response
from core.logger import setup_logger as get_logger
from services.evaluation import evaluate_section, improve_prompt

logger = get_logger(__name__)

# ── Timeout config ─────────────────────────────────────────────
LLM_TIMEOUT_SECONDS = 90   # Max 90s per LLM call — never hang forever


def generate_llm_section(
    section_id: str,
    section_title: str,
    prompt_template: str,
    context: dict,
    tracker=None,
    max_retries: int = MAX_SECTION_RETRIES,
    pipeline_logger=None,
) -> tuple:
    """
    Generate one report section with:
      - LLM generation with timeout (no more infinite hangs)
      - Automatic evaluation (LLM-as-judge)
      - Auto-accept when score >= 3  (no blocking input() in API mode)
      - Prompt auto-improvement on repeated failure
      - PromptTracker recording for audit

    Returns: (output, final_score, final_prompt)
    """
    if tracker:
        tracker.start_section(section_id, section_title, prompt_template)

    client           = get_openai_client()
    current_prompt   = prompt_template
    last_output      = None
    last_eval        = None
    prompt_rewritten = False

    for attempt in range(1, max_retries + 2):   # +1 for prompt-engineer retry
        logger.info(f"[{section_id}] Tentative {attempt}/{max_retries + 1}")

        # ── Format prompt ──────────────────────────────────────────────
        try:
            filled_prompt = current_prompt.format(**context)
        except (KeyError, AttributeError):
            # Improved prompt may have broken placeholders — use raw prompt
            filled_prompt = current_prompt

        # ── Generate ───────────────────────────────────────────────────
        output = None
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un analyste crédit senior. Réponds en JSON uniquement "
                            "quand demandé. Français professionnel bancaire."
                        ),
                    },
                    {"role": "user", "content": filled_prompt},
                ],
                temperature=0.2,
                max_tokens=2000,
                timeout=LLM_TIMEOUT_SECONDS,  
            )
            raw = clean_response(resp.choices[0].message.content)
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$',     '', raw)

            try:
                output = json.loads(raw)
            except json.JSONDecodeError:
                output = raw   # some sections return plain text

        except Exception as e:
            err_type = type(e).__name__
            if "timeout" in str(e).lower() or "Timeout" in err_type:
                logger.warning(f"[{section_id}] Tentative {attempt} — TIMEOUT ({LLM_TIMEOUT_SECONDS}s), passage à la suivante")
            else:
                logger.error(f"[LLM ERROR] {section_id} tentative {attempt}: {err_type}: {e}")
            output = None

        last_output = output

        # ── If output is None (timeout/error) skip evaluation ──────────
        if output is None:
            if attempt <= max_retries:
                logger.info(f"[{section_id}] Output vide — nouvelle tentative...")
                continue
            else:
                logger.warning(f"[{section_id}] Toutes les tentatives ont échoué")
                break

        # ── Evaluate ───────────────────────────────────────────────────
        eval_result = evaluate_section(section_id, section_title, output)
        last_eval   = eval_result
        score       = eval_result.get("score", 3)
        passed      = eval_result.get("pass", True)

        logger.info(f"[{section_id}] Score {score}/5 — {'ACCEPTÉ' if passed else 'REJETÉ'}")
        for reason in eval_result.get("reasons", [])[:2]:
            logger.debug(f"[{section_id}]   • {reason}")

        # ── Record attempt ─────────────────────────────────────────────
        if tracker:
            tracker.record_attempt(
                attempt, filled_prompt, output, eval_result,
                "", prompt_rewritten
            )

        # ── Auto-accept if passed ──────────────────────────────────────
        if passed:
            logger.info(f"[{section_id}] Section acceptée automatiquement (score {score}/5)")
            if tracker:
                tracker.finalize_section(output, score, current_prompt, True)
            if pipeline_logger: pipeline_logger.log_section(section_id, section_title, filled_prompt, output, score, attempt)
            return output, score, current_prompt

        # ── Improve prompt for next retry ──────────────────────────────
        if attempt <= max_retries:
            reasons = eval_result.get("reasons", [])
            if attempt >= 2:
                current_prompt = improve_prompt(
                    section_id, section_title, current_prompt,
                    last_output, reasons, "", attempt
                )
                prompt_rewritten = True
            else:
                current_prompt = (
                    current_prompt
                    + "\n\nATTENTION — Corriger ces points :\n"
                    + "\n".join(f"- {r}" for r in reasons[:3])
                )
                prompt_rewritten = False

    # ── Max retries exhausted — return best effort ─────────────────────
    logger.warning(f"[{section_id}] Max retries atteint — meilleur résultat utilisé")
    if tracker:
        tracker.finalize_section(
            last_output,
            last_eval.get("score", 2) if last_eval else 2,
            current_prompt,
            False,
        )
    return last_output, last_eval.get("score", 2) if last_eval else 2, current_prompt