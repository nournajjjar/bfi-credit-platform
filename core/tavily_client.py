"""
Tavily Client - Singleton pattern
"""
from tavily import TavilyClient
from typing import Optional
from .config import TAVILY_API_KEY
from .logger import setup_logger

logger = setup_logger(__name__)

_tavily_client: Optional[TavilyClient] = None

def get_tavily_client() -> TavilyClient:
    """Get or create Tavily client (singleton)"""
    global _tavily_client

    if _tavily_client is None:
        if not TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY not configured")

        _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        logger.info("Tavily client initialized")

    return _tavily_client

def reset_tavily_client():
    """Reset client (for testing)"""
    global _tavily_client
    _tavily_client = None
