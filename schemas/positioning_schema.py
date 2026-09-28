from pydantic import BaseModel
from typing import Optional

class PositioningResult(BaseModel):
    capital_position: Optional[str] = None
    emploi_position: Optional[str] = None
    age_position: Optional[str] = None
    is_export: bool = False
    has_web: bool = False
    export_vs_sector: Optional[str] = None
    web_vs_sector: Optional[str] = None