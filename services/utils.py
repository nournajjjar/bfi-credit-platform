import re
from datetime import datetime

def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/\*\?:"<>|]', "", name)
    name = re.sub(r'\s+', "_", name.strip())
    return name[:60]

def timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")