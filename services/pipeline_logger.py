"""
services/pipeline_logger.py
Logs generated prompts, questions and answers to a JSON file per report.
Output: backend/logs/pipeline_{company}_{timestamp}.json
"""
import json, os, re
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class PipelineLogger:
    def __init__(self, company_name: str):
        safe = re.sub(r'[^\w]', '_', company_name)[:30]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = LOG_DIR / f"pipeline_{safe}_{ts}.json"
        self.data = {
            "company":   company_name,
            "started_at": datetime.now().isoformat(),
            "questions": [],
            "answers":   [],
            "sections":  [],
        }
        self._save()

    # ── Questions ─────────────────────────────────────────────────
    def log_questions(self, questions: list):
        self.data["questions"] = [
            {"id": q.get("id"), "question": q.get("question"), "section": q.get("section")}
            for q in questions
        ]
        self._save()

    # ── Q&A answers ───────────────────────────────────────────────
    def log_answers(self, answers: list):
        self.data["answers"] = [
            {
                "id":         a.get("id"),
                "question":   a.get("question"),
                "answer":     a.get("answer"),
                "confidence": a.get("confidence"),
            }
            for a in answers
        ]
        self._save()

    # ── Section prompt + output ───────────────────────────────────
    def log_section(self, section_id: str, title: str, prompt: str, output, score: int, attempt: int):
        self.data["sections"].append({
            "section_id": section_id,
            "title":      title,
            "score":      score,
            "attempt":    attempt,
            "prompt":     prompt[:3000],          # truncate for readability
            "output":     output if isinstance(output, dict) else str(output)[:2000],
            "logged_at":  datetime.now().isoformat(),
        })
        self._save()

    def finish(self):
        self.data["finished_at"] = datetime.now().isoformat()
        self._save()
        return str(self.path)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)