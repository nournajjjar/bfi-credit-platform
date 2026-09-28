"""
prompt_export.py — Exporteur de prompts pour audit et amélioration
"""
import json, os, re
from datetime import datetime
from pathlib import Path

REPORT_OUTPUT_DIR = os.getenv("REPORT_OUTPUT_DIR", ".")


class PromptTracker:
    def __init__(self, company_name: str, sector: str):
        self.company_name = company_name
        self.sector       = sector
        self.started_at   = datetime.now().isoformat()
        self.sections: dict = {}
        self.qa_metadata: dict = {}
        self._current: str = None

    def start_section(self, section_id, section_title, initial_prompt):
        self._current = section_id
        self.sections[section_id] = {
            "section_id": section_id, "section_title": section_title,
            "initial_prompt": initial_prompt, "attempts": [],
            "final_prompt": None, "final_output": None,
            "final_score": None, "accepted_at_attempt": None, "human_accepted": False,
        }

    def record_attempt(self, attempt_number, prompt_used, output,
                       eval_result, human_feedback="", prompt_was_rewritten=False):
        if self._current not in self.sections:
            return
        self.sections[self._current]["attempts"].append({
            "attempt": attempt_number, "prompt_used": prompt_used,
            "prompt_rewritten": prompt_was_rewritten, "output": output,
            "eval_score": eval_result.get("score"), "eval_pass": eval_result.get("pass"),
            "eval_reasons": eval_result.get("reasons", []),
            "eval_suggestions": eval_result.get("suggestions", []),
            "human_feedback": human_feedback, "timestamp": datetime.now().isoformat(),
        })

    def finalize_section(self, final_output, final_score, final_prompt, human_accepted=True):
        if self._current not in self.sections:
            return
        sec = self.sections[self._current]
        sec.update({
            "final_output": final_output, "final_score": final_score,
            "final_prompt": final_prompt, "human_accepted": human_accepted,
            "accepted_at_attempt": len(sec["attempts"]),
        })
        self._current = None

    def record_qa_metadata(self, all_questions, answers, confidence):
        self.qa_metadata = {
            "total_questions": len(all_questions), "total_answers": len(answers),
            "confidence_level": confidence.get("level"),
            "pct_low_confidence": confidence.get("pct_low"),
            "questions": [
                {"id": q.get("id"), "theme": q.get("theme"), "question": q.get("question"),
                 "section_cible": q.get("section_cible"),
                 "type": "general" if str(q.get("id","")).startswith("G") else "specific"}
                for q in all_questions
            ],
            "answers": [
                {"id": a.get("id"), "question": a.get("question"), "answer": a.get("answer"),
                 "confidence": a.get("confidence"), "source_url": a.get("source_url")}
                for a in answers
            ],
        }

    def export(self, report_meta=None):
        safe_name = re.sub(r'[\\/*?:"<>|\s]+', "_", self.company_name)[:50]
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath  = Path(REPORT_OUTPUT_DIR) / f"{safe_name}_{ts}_prompts.json"

        total_attempts  = sum(len(s["attempts"]) for s in self.sections.values())
        rewritten       = sum(1 for s in self.sections.values()
                              for a in s["attempts"] if a.get("prompt_rewritten"))
        scores = [s["final_score"] for s in self.sections.values() if s["final_score"] is not None]
        avg    = round(sum(scores)/len(scores), 2) if scores else None

        payload = {
            "meta": {
                "company_name": self.company_name, "sector": self.sector,
                "started_at": self.started_at, "exported_at": datetime.now().isoformat(),
                "total_sections": len(self.sections), "total_attempts": total_attempts,
                "prompts_rewritten": rewritten, "average_section_score": avg,
                "report_meta": report_meta or {},
            },
            "qa_metadata": self.qa_metadata,
            "sections": self.sections,
            "summary": {
                "section_scores": {sid: s["final_score"] for sid, s in self.sections.items()},
                "sections_accepted_first_try": sum(
                    1 for s in self.sections.values()
                    if len(s["attempts"]) == 1 and s["human_accepted"]),
                "sections_needing_prompt_rewrite": rewritten,
                "sections_exhausted_retries": sum(
                    1 for s in self.sections.values() if not s["human_accepted"]),
            },
        }
        filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)


def make_tracked_generate_llm_section(
    tracker, original_fn=None,
    evaluate_section_fn=None, improve_prompt_fn=None, MIN_SECTION_SCORE=3
):
    import re, json
    from openai import OpenAI
    from colorama import Fore, Style

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
    MAX_RETRIES    = int(os.getenv("MAX_SECTION_RETRIES", "3"))

    def tracked_generate(section_id, section_title, prompt_template, context, max_retries=MAX_RETRIES):
        tracker.start_section(section_id, section_title, prompt_template)
        client = OpenAI(api_key=OPENAI_API_KEY)
        current_prompt = prompt_template
        last_output = last_eval = None
        human_feedback = ""
        prompt_was_rewritten = False

        for attempt in range(1, max_retries + 2):
            print(f"\n  {Fore.CYAN}[{section_id}] Tentative {attempt}…{Style.RESET_ALL}")
            try:
                filled = current_prompt.format(**context)
            except KeyError:
                filled = current_prompt

            try:
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content":
                         "Tu es un analyste crédit senior. Réponds en JSON uniquement quand demandé. Français professionnel bancaire."},
                        {"role": "user", "content": filled},
                    ],
                    temperature=0.2, max_tokens=2000,
                )
                raw = resp.choices[0].message.content.strip()
                raw = re.sub(r'^```json\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
                try:
                    output = json.loads(raw)
                except json.JSONDecodeError:
                    output = raw
            except Exception as e:
                print(f"  {Fore.RED}[LLM ERROR] {e}{Style.RESET_ALL}")
                output = None
            last_output = output

            eval_result = evaluate_section_fn(section_id, section_title, output) if evaluate_section_fn \
                          else {"score": 3, "pass": True, "reasons": [], "suggestions": []}
            last_eval = eval_result
            score  = eval_result.get("score", 3)
            passed = eval_result.get("pass", True)

            sc = Fore.GREEN if score >= 4 else Fore.YELLOW if score >= 3 else Fore.RED
            print(f"  {sc}Score {score}/5 {'✓ ACCEPTÉ' if passed else '✗ REJETÉ'}{Style.RESET_ALL}")
            for r in eval_result.get("reasons", [])[:3]:
                print(f"    • {r}")

            tracker.record_attempt(attempt, filled, output, eval_result, "", prompt_was_rewritten)

            if passed:
                preview = (output[:300] if isinstance(output, str)
                           else json.dumps(output, ensure_ascii=False)[:300])
                print(f"\n  {Fore.WHITE}── Aperçu {section_title} ──{Style.RESET_ALL}")
                print(f"  {preview}…\n")
                human_input = input(
                    f"  {Fore.CYAN}Accepter ? [Entrée=oui | tapez une correction] : {Style.RESET_ALL}"
                ).strip()
                tracker.sections[section_id]["attempts"][-1]["human_feedback"] = human_input
                if not human_input:
                    print(f"  {Fore.GREEN}✓ {section_title} acceptée{Style.RESET_ALL}")
                    tracker.finalize_section(output, score, current_prompt, True)
                    return output, score, current_prompt
                human_feedback = human_input
                print(f"  {Fore.YELLOW}Feedback enregistré, amélioration…{Style.RESET_ALL}")

            reasons = eval_result.get("reasons", []) + (
                [f"Feedback humain: {human_feedback}"] if human_feedback else [])
            if attempt <= max_retries:
                if attempt >= 2 and improve_prompt_fn:
                    current_prompt = improve_prompt_fn(
                        section_id, section_title, current_prompt,
                        last_output, reasons, human_feedback, attempt)
                    prompt_was_rewritten = True
                else:
                    hints = "\n".join(f"- {r}" for r in reasons[:3])
                    current_prompt = current_prompt + f"\n\nATTENTION — Corriger :\n{hints}"
                    prompt_was_rewritten = False

        print(f"  {Fore.YELLOW}⚠ {section_title} : max tentatives atteint{Style.RESET_ALL}")
        tracker.finalize_section(last_output,
                                 last_eval.get("score", 2) if last_eval else 2,
                                 current_prompt, False)
        return last_output, last_eval.get("score", 2) if last_eval else 2, current_prompt

    return tracked_generate