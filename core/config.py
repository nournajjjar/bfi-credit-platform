#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _require(var):
    val = os.getenv(var)
    if not val:
        print(f"\n❌  Variable manquante : {var}\n    set {var}=<valeur>\n")
        sys.exit(1)
    return val

DB_HOST     = os.getenv("PG_HOST", "localhost")
DB_PORT     = os.getenv("PG_PORT", "5432")
DB_NAME     = os.getenv("PG_DB", "tunisie_industrie")
DB_USER     = os.getenv("PG_USER", "postgres")
DB_PASSWORD = _require("PG_PASSWORD")

OPENAI_API_KEY = _require("OPENAI_API_KEY")

OPENAI_MODEL      = "gpt-4o"
REPORT_OUTPUT_DIR = os.getenv("REPORT_OUTPUT_DIR", ".")
SCRIPT_DIR        = Path(__file__).parent
REPORT_GENERATOR  = SCRIPT_DIR.parent / "scripts" / "generate_report.js"
CACHE_DIR  = SCRIPT_DIR / "cache" / "sector_questions"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DAYS = 30
TAVILY_API_KEY = _require("TAVILY_API_KEY")
MAX_PAGES           = 20
MAX_TAVILY_RESULTS  = 15
MAX_PAGE_CHARS      = 8000


MAX_SECTION_RETRIES = 5
MIN_SECTION_SCORE   = 3

SECTOR_LABELS = {
    "secteur_ind_m_caniques":         "Industries mécaniques et métallurgiques",
    "secteur_ind_textile":            "Industries textiles et habillement",
    "secteur_mat_riaux_construction": "Industries des matériaux de construction",
    "secteur_ind_chimiques":          "Industries chimiques",
    "secteur_agro_alimentaires":      "Industries agro-alimentaires",
    "secteur_ind_cuir_chaussures":    "Industries du cuir et de la chaussure",
    "secteur_ind_bois_li_ge":         "Industries du bois, du liège et ameublement",
    "secteur_ind_lectriques":         "Industries électriques et électroniques",
    "secteur_ind_diverses":           "Industries diverses",
}

SECTIONS = [
    ("s1_portfolio_overview",      "Portfolio Performance Overview",        True),
    ("s2_credit_quality",          "Credit Quality & Risk Metrics",         True),
    ("s3_pricing_yield",           "Pricing & Yield Analysis",              True),
    ("s4_deal_structuring",        "Deal Structuring & Covenant Trends",    True),
    ("s5_origination_pipeline",    "Origination & Pipeline Activity",       True),
    ("s6_sector_concentration",    "Sector & Industry Concentration",       True),
    ("s7_relationship_wallet",     "Relationship & Wallet Share",           True),
    ("s8_regulatory_capital",      "Regulatory & Capital Efficiency",       True),
    ("s9_operational_process",     "Operational & Process Benchmarks",      True),
    ("s10_client_retention",       "Client Retention & Attrition",         True),
]

# ── FastAPI metadata ──────────────────────────────────────────────────────────
API_TITLE       = "backend"
API_VERSION     = "1.0.0"
API_DESCRIPTION = "Benchmark & credit report generator for Tunisian industrial companies"
APP_ENV         = os.getenv("APP_ENV", "development")
MODEL_NAME      = OPENAI_MODEL

# ── DB_CONFIG dict for psycopg2 ───────────────────────────────────────────────
DB_CONFIG = {
    "host":     DB_HOST,
    "port":     int(DB_PORT),
    "dbname":   DB_NAME,
    "user":     DB_USER,
    "password": DB_PASSWORD,
    "options":  "-c client_encoding=UTF8",
}

AZURE_ENDPOINT   = os.getenv("AZURE_ENDPOINT", "")
AZURE_MODEL      = os.getenv("AZURE_MODEL", "Phi-4")
OPENAI_MODEL     = AZURE_MODEL

AZURE_EMBED_DEPLOYMENT = os.getenv("AZURE_EMBED_DEPLOYMENT", "text-embedding-3-small")