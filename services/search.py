#!/usr/bin/env python3
"""
Web search and content collection module for Deep Research system
"""

import re
import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style

from core.config import MAX_TAVILY_RESULTS, MAX_PAGES, MAX_PAGE_CHARS
from core.tavily_client import get_tavily_client


# ══════════════════════════════════════════════════════════════════════════════
#  THEMED QUERY TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

# (theme_key, label, query_template) — supplementary, never replace the main queries
THEMED_QUERIES_TEMPLATES = [
    ("donnees_financieres",  "Données financières",
     '{company} Tunisie chiffre affaires résultat net bilan comptable dividendes rapport financier'),
    ("actualites_recentes",  "Actualités récentes",
     '{company} Tunisie actualités communiqué CMF presse annonce récente 2024 2025'),
    ("secteur_marche",       "Secteur et marché tunisien",
     '{company} Tunisie secteur concurrents marché part tendances positionnement'),
    ("gouvernance",          "Gouvernance",
     '{company} Tunisie dirigeants actionnaires conseil administration PDG structure gouvernance'),
    ("cotation_bvmt",        "Cotation BVMT",
     '{company} BVMT cotation bourse cours action volume historique capitalisation'),
    ("export_international", "Export et international",
     '{company} Tunisie export international pays clients étrangers filiales implantation'),
    ("risques_litiges",      "Risques et litiges",
     '{company} Tunisie risques litiges contentieux réglementaire juridique compliance'),
]


# ══════════════════════════════════════════════════════════════════════════════
#  TAVILY SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def tavily_search(company_name, gouvernorat="Tunisie", secteur=""):
    """Search for company information using Tavily"""
    client = get_tavily_client()

    # Main queries — always run first, results tagged theme=None
    main_queries = [
        (None, f'"{company_name}" Tunisie entreprise industrielle'),
        (None, f'{company_name} {gouvernorat} {secteur}'),
        (None, f'{company_name} Tunisie site:linkedin.com OR site:kompass.com OR site:manageo.com'),
    ]

    # Supplementary themed queries — appended, results tagged with their theme key
    themed_queries = [
        (theme_key, tmpl.format(company=company_name))
        for theme_key, _label, tmpl in THEMED_QUERIES_TEMPLATES
    ]

    seen_urls, results = set(), []

    for theme_tag, q in main_queries + themed_queries:
        try:
            resp = client.search(
                query=q,
                search_depth="advanced",
                max_results=MAX_TAVILY_RESULTS,
                include_answer=False,
                include_raw_content=True
            )
            for r in resp.get("results", []):
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append({
                        "title":       r.get("title", ""),
                        "url":         url,
                        "snippet":     r.get("content", ""),
                        "raw_content": r.get("raw_content") or "",
                        "score":       r.get("score", 0),
                        "theme":       theme_tag,  # None for main queries
                    })
        except Exception as e:
            print(f"  {Fore.YELLOW}[TAVILY]{Style.RESET_ALL} {e}")

    results.sort(key=lambda x: -x.get("score", 0))
    return results[:MAX_TAVILY_RESULTS * 2]


# ══════════════════════════════════════════════════════════════════════════════
#  WEB CONTENT COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

def collect_web_content(search_results):
    """Collect and clean web content from search results"""
    collected, fetched = [], 0

    for r in search_results:
        if fetched >= MAX_PAGES:
            break

        url = r["url"]
        text = r.get("raw_content", "").strip()

        if not text:
            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": "ResearchBot/1.0"},
                    timeout=10
                )
                soup = BeautifulSoup(resp.text, "html.parser")

                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                    tag.decompose()

                text = re.sub(r'\s+', ' ', soup.get_text(separator=" ", strip=True))
            except:
                pass

        text = re.sub(r'\s+', ' ', text)[:MAX_PAGE_CHARS] if text else ""

        if text and len(text) > 200:
            collected.append({
                "url":   url,
                "title": r["title"],
                "text":  text
            })
            fetched += 1

    return collected


# ══════════════════════════════════════════════════════════════════════════════
#  CORPUS BUILDING
# ══════════════════════════════════════════════════════════════════════════════

def build_web_corpus(web_pages):
    """Concatenate all web content into one string for Q&A answering"""
    corpus = ""
    for i, p in enumerate(web_pages, 1):
        corpus += f"\n--- Source {i}: {p['title']} ({p['url']}) ---\n{p['text']}\n"
    return corpus
