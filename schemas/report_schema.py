from pydantic import BaseModel
from typing import Optional, Dict, Any

class ReportRequest(BaseModel):
    company_name:       str
    source_table:       Optional[str] = ""
    gouvernorat:        Optional[str] = ""
    label_secteur:      Optional[str] = ""
    activites:          Optional[str] = ""
    produits:           Optional[str] = ""
    capital:            Optional[str] = ""
    emploi:             Optional[str] = ""
    regime:             Optional[str] = ""
    entree_production:  Optional[str] = ""
    url:                Optional[str] = ""
    source_url:         Optional[str] = ""
    pdf_financial_data: Optional[Dict[str, Any]] = None

class ReportResponse(BaseModel):
    job_id:   str
    success:  bool
    message:  str