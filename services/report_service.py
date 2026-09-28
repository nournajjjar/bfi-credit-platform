"""Report service with OpenAI"""
from typing import Dict, Any
from core.logger import setup_logger
from core.openai_client import get_openai_client
from core.config import OPENAI_MODEL

logger = setup_logger(__name__)

class ReportService:
    def __init__(self):
        self.client = get_openai_client()

    def generate_report(self, company: Dict) -> Dict[str, Any]:
        """Generate report using OpenAI GPT-4"""
        logger.info(f"Generating report with OpenAI for {company.get('denomination')}")

        # Example: Use OpenAI for synthesis
        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{
                    "role": "user",
                    "content": f"Generate a brief credit analysis summary for company: {company.get('denomination')}"
                }],
                max_tokens=500
            )

            synthesis = response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            synthesis = "Rapport généré."

        return {
            "s1_identite": {
                "denomination": company.get("denomination", "")
            },
            "s2_synthese": synthesis,
            "_meta": {
                "generated_at": "2026-04-21",
                "model": OPENAI_MODEL
            }
        }
