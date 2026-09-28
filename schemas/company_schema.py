"""Company schemas"""
from pydantic import BaseModel
from typing import Optional

class CompanySearchRequest(BaseModel):
    query: str
    top_n: int = 5

class CompanyResponse(BaseModel):
    denomination:  str
    gouvernorat:   Optional[str] = None
    source_table:  Optional[str] = None
    label_secteur: Optional[str] = None
    match_score:   Optional[float] = None
