from pydantic import BaseModel
from typing import Optional

class QAAnswer(BaseModel):
    id: str
    question: str
    answer: str
    confidence: str  # "élevé", "moyen", "faible"
    source_url: Optional[str] = None