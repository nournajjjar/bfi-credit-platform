from openai import OpenAI
import os
from dotenv import load_dotenv

def get_openai_client() -> OpenAI:
    load_dotenv(override=True)
    return OpenAI(
        base_url=os.getenv("AZURE_ENDPOINT", ""),
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )

def clean_response(text: str) -> str:
    """Remove Phi-4 special tokens and clean response."""
    if not text:
        return ""
    text = text.replace("<|im_end|>", "")
    text = text.replace("<|im_start|>", "")
    text = text.replace("<|end|>", "")
    text = text.strip()
    return text