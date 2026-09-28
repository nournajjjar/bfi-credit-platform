# backend/routes/research.py
"""Research routes — full pipeline with job tracking"""
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, File, UploadFile, Query
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional
from schemas.report_schema import ReportRequest
from schemas.job_schema import JobStatus, JobType
from services.job_service import job_service
from services.database_service import fuzzy_search_companies, get_sector_stats, compute_positioning
from services.report import build_report
from services.export import generate_docx_report
from services.search import tavily_search, collect_web_content, THEMED_QUERIES_TEMPLATES, build_web_corpus
from services.embeddings_service import process_and_store
from core.logger import setup_logger
from services.report_cache import ReportCache
from services.section_versioning import SectionVersioning
from services.mlflow_tracker import log_report_generation, compute_faithfulness_heuristic

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/research", tags=["Research"])


@router.get("/search")
async def search_companies(q: str, top_n: int = 5):
    if not q:
        raise HTTPException(400, "Query parameter 'q' is required")
    results = await run_in_threadpool(fuzzy_search_companies, q, top_n)
    return {"success": True, "count": len(results), "companies": results}


@router.post("/deep-research")
async def deep_research(
    background_tasks: BackgroundTasks,
    company_name: str,
    gouvernorat:  str = "Tunisie",
    label_secteur:str = "",
):
    if not company_name:
        raise HTTPException(400, "company_name is required")
    job_id = job_service.create_job(
        JobType.REPORT_GENERATION,
        f"Deep Research: {company_name}",
        {"company_name": company_name}
    )
    background_tasks.add_task(_run_deep_research, job_id, company_name, gouvernorat, label_secteur)
    return {"success": True, "job_id": job_id, "message": "Deep research started"}


@router.post("/generate-report")
async def generate_report(background_tasks: BackgroundTasks, request: ReportRequest):
    job_id = job_service.create_job(
        JobType.REPORT_GENERATION,
        f"Rapport: {request.company_name}",
        {"company_name": request.company_name, "source_table": request.source_table}
    )
    background_tasks.add_task(_run_pipeline, job_id, request, [])
    return {"success": True, "job_id": job_id, "message": "Pipeline started"}


@router.post("/generate-report-with-pdf")
async def generate_report_with_pdf(
    background_tasks:  BackgroundTasks,
    file1:             UploadFile           = File(...),
    file2:             Optional[UploadFile] = File(None),
    file3:             Optional[UploadFile] = File(None),
    company_name:      str = Query(default=""),
    source_table:      str = Query(default=""),
    gouvernorat:       str = Query(default=""),
    label_secteur:     str = Query(default=""),
    activites:         str = Query(default=""),
    produits:          str = Query(default=""),
    capital:           str = Query(default=""),
    emploi:            str = Query(default=""),
    regime:            str = Query(default=""),
    entree_production: str = Query(default=""),
    url:               str = Query(default=""),
):
    raw_files = [f for f in [file1, file2, file3] if f is not None]
    for f in raw_files:
        if f.filename and not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"'{f.filename}' n'est pas un PDF")

    all_pdf_bytes = []
    total_size = 0
    for f in raw_files:
        data = await f.read()
        if not data:
            continue
        total_size += len(data)
        if total_size > 50 * 1024 * 1024:
            raise HTTPException(400, "Taille totale trop grande (max 50 Mo)")
        all_pdf_bytes.append({"filename": f.filename or "document.pdf", "bytes": data})

    if not all_pdf_bytes:
        raise HTTPException(400, "Au moins un PDF est requis")

    request = ReportRequest(
        company_name=company_name, source_table=source_table,
        gouvernorat=gouvernorat, label_secteur=label_secteur,
        activites=activites, produits=produits, capital=capital,
        emploi=emploi, regime=regime, entree_production=entree_production, url=url,
    )
    job_id = job_service.create_job(
        JobType.REPORT_GENERATION,
        f"Rapport + PDF(s): {company_name}",
        {"company_name": company_name, "pdf_count": len(all_pdf_bytes)}
    )
    background_tasks.add_task(_run_pipeline, job_id, request, all_pdf_bytes)
    return {"success": True, "job_id": job_id, "pdf_count": len(all_pdf_bytes)}


# ── Helpers ───────────────────────────────────────────────────────

def _step(job_id: str, pct: int, msg: str):
    job_service.update_job(job_id, status=JobStatus.RUNNING, progress=pct, message=msg)
    logger.info(f"[{job_id}] {pct}% — {msg}")


def _merge_pdf_financial(results: list) -> dict:
    merged = {}
    all_pages = []
    for result in results:
        pages = result.pop("raw_pages", [])
        all_pages.extend(pages)
        for key, value in result.items():
            if key not in merged:
                merged[key] = value
            else:
                if isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key].update(value)
                elif isinstance(merged[key], list) and isinstance(value, list):
                    merged[key].extend(value)
                elif value and str(value).strip() not in ("", "null", "None"):
                    merged[key] = value
    merged["raw_pages"] = all_pages
    return merged


def _run_deep_research(job_id: str, company_name: str, gouvernorat: str, label_secteur: str):
    try:
        _step(job_id, 30, "Recherche Tavily...")
        search_results = tavily_search(company_name, gouvernorat, label_secteur)
        _step(job_id, 70, "Structuration des resultats...")
        findings = _structure_tavily_results(search_results)
        _step(job_id, 90, "Indexation (embeddings)...")
        process_and_store(
            company=company_name, source="deep_research",
            data={"findings": findings},
            metadata={"gouvernorat": gouvernorat, "label_secteur": label_secteur}
        )
        job_service.update_job(job_id, status=JobStatus.COMPLETED, progress=100,
            message="Deep research terminee",
            result={"company_name": company_name, "findings": findings,
                    "sources": [{"title": r.get("title"), "url": r.get("url")} for r in search_results]})
    except Exception as e:
        logger.error(f"[{job_id}] Deep research failed: {e}", exc_info=True)
        job_service.update_job(job_id, status=JobStatus.FAILED, error=str(e))


def _structure_tavily_results(search_results: list) -> dict:
    by_theme = {key: [] for key, _label, _tmpl in THEMED_QUERIES_TEMPLATES}
    findings = {"high_relevance": [], "medium_relevance": [], "low_relevance": [],
                "all_content": [], "by_theme": by_theme}
    for r in search_results:
        score = r.get("score", 0)
        item  = {"title": r.get("title",""), "url": r.get("url",""),
                 "snippet": r.get("snippet",""), "raw_content": r.get("raw_content",""),
                 "score": score, "theme": r.get("theme")}
        if score >= 0.7:   findings["high_relevance"].append(item)
        elif score >= 0.4: findings["medium_relevance"].append(item)
        else:              findings["low_relevance"].append(item)
        findings["all_content"].append(item)
        theme_key = r.get("theme")
        if theme_key and theme_key in by_theme:
            by_theme[theme_key].append(item)
    return findings


# ── Pipeline principal ────────────────────────────────────────────

def _run_pipeline(job_id: str, request: ReportRequest, all_pdf_bytes: list):
    try:
        company = {
            "denomination":      request.company_name,
            "gouvernorat":       request.gouvernorat or "",
            "label_secteur":     request.label_secteur or "",
            "source_table":      request.source_table or "",
            "activites":         request.activites or "",
            "produits":          request.produits or "",
            "capital":           request.capital or "",
            "emploi":            request.emploi or "",
            "regime":            request.regime or "",
            "entree_production": request.entree_production or "",
            "url":               request.url or "",
            "source_url":        getattr(request, "source_url", "") or "",
        }

        # ── Etape 1 — Extraction PDF ──────────────────────────────
        pdf_financial = getattr(request, "pdf_financial_data", None) or {}
        if all_pdf_bytes:
            total = len(all_pdf_bytes)
            _step(job_id, 5, f"Extraction de {total} PDF(s)...")
            try:
                from services.pdf_extractor_optimized import extract_pdf_financial
            except ImportError:
                from services.pdf_extractor import extract_pdf_financial
            extraction_results = []
            for i, pdf in enumerate(all_pdf_bytes):
                pct = 5 + int(12 * (i + 1) / total)
                _step(job_id, pct, f"Extraction PDF {i+1}/{total} : {pdf['filename']}...")
                safe_name = request.company_name.replace(' ', '_').replace("'", "").upper()
                result = extract_pdf_financial(pdf["bytes"], cache_key=safe_name)
                extraction_results.append(result)
            pdf_financial = _merge_pdf_financial(extraction_results) if total > 1 else extraction_results[0]
            _step(job_id, 18, f"PDFs extraits — {len(pdf_financial.get('raw_pages', []))} pages")

            # ── Extract forecast periods with pdfplumber (fast, no LLM) ──
            try:
                from routes.forecast import _fast_extract_periods_from_pdf, _extract_all_periods
                for pdf in all_pdf_bytes:
                    pf_forecast = _fast_extract_periods_from_pdf(pdf["bytes"])
                    periods     = _extract_all_periods(pf_forecast)
                    if periods:
                        pdf_financial["periods"] = periods
                        logger.info(f"[{job_id}] {len(periods)} periodes extraites (pdfplumber)")
                        break
            except Exception as _pe:
                logger.warning(f"[{job_id}] Period extraction ignoree: {_pe}")

            # ── Save extraction JSON ──────────────────────────────
            try:
                import pathlib, json as _json
                out_dir   = pathlib.Path("database/output")
                out_dir.mkdir(parents=True, exist_ok=True)
                safe_name = request.company_name.replace(' ', '_').replace("'", "")
                json_path = out_dir / f"{safe_name}_extraction.json"
                with open(json_path, "w", encoding="utf-8") as _f:
                    _json.dump(pdf_financial, _f, ensure_ascii=False, indent=2, default=str)
                logger.info(f"[{job_id}] Extraction JSON saved: {json_path}")
            except Exception as _je:
                logger.warning(f"[{job_id}] JSON save ignore: {_je}")

        # ── Etape 2 — Base de donnees ─────────────────────────────
        _step(job_id, 20, "Recherche entreprise en base de donnees...")
        if not company.get("source_table"):
            try:
                results = fuzzy_search_companies(company["denomination"], top_n=1)
                if results:
                    best = results[0]
                    for k in ["source_table","label_secteur","gouvernorat","activites","produits",
                               "capital","emploi","regime","entree_production","url","source_url"]:
                        company[k] = best.get(k, "")
            except Exception as e:
                logger.warning(f"[{job_id}] DB lookup failed: {e}")

        # ── Etape 3 — Stats sectorielles ──────────────────────────
        _step(job_id, 25, "Statistiques sectorielles...")
        stats       = get_sector_stats(company.get("source_table","")) if company.get("source_table") else {}
        positioning = compute_positioning(company, stats)

        # ── Etape 4 — Tavily ──────────────────────────────────────
        _step(job_id, 30, "Recherche Tavily...")
        search_results = tavily_search(
            company["denomination"],
            company.get("gouvernorat","Tunisie"),
            company.get("label_secteur","")
        )

        # ── Etape 5 — Web content ─────────────────────────────────
        _step(job_id, 42, f"Collecte contenu web ({len(search_results)} resultats)...")
        web_pages = collect_web_content(search_results)
        corpus    = build_web_corpus(web_pages)

        # ── Etape 6 — Generation rapport ──────────────────────────
        _step(job_id, 55, "Generation du rapport (Q&A + sections LLM)...")
        rapport, qa_layer, tracker = build_report(
            company, stats, positioning, web_pages, search_results, pdf_financial
        )

        # ── Etape 7 — Embeddings PDF ──────────────────────────────
        n_chunks = 0
        if all_pdf_bytes:
            _step(job_id, 85, "Indexation PDF (embeddings)...")
            try:
                n_chunks = process_and_store(
                    company=company["denomination"], source="pdf",
                    data=pdf_financial,
                    metadata={"source_table": company.get("source_table",""), "pdf_count": len(all_pdf_bytes)}
                ) or 0
            except Exception as emb_err:
                logger.warning(f"[{job_id}] Embedding ignore: {emb_err}")

        # ── Etape 8 — Export DOCX ─────────────────────────────────
        _step(job_id, 92, "Export DOCX...")
        docx_path = generate_docx_report(company, rapport, stats, positioning)

        # ── Node.js DOCX (generate_report.js — better formatting) ─
        js_docx_path = None
        try:
            import subprocess, json as _json, re as _re
            from datetime import datetime as _dt
            _safe = _re.sub(r"[^a-zA-Z0-9_]", "_", company.get("denomination", "rapport"))
            _ts   = _dt.now().strftime("%Y%m%d_%H%M%S")
            _jin  = f"database/output/{_safe}_{_ts}_input.json"
            _jdocx= f"database/output/rapport_{_safe}_{_ts}_full.docx"
            _pl   = {
                "rapport": rapport, "company": company,
                "stats": stats, "positioning": positioning,
                "_meta": rapport.get("_meta", {})
            }
            with open(_jin, "w", encoding="utf-8") as _f:
                _json.dump(_pl, _f, ensure_ascii=False, default=str)
            _r = subprocess.run(
                ["node", "generate_report.js", _jin, _jdocx],
                capture_output=True, text=True, timeout=60
            )
            if _r.returncode == 0 and os.path.exists(_jdocx):
                js_docx_path = _jdocx
                docx_path    = _jdocx   # use the JS-generated DOCX as the primary download
                logger.info(f"[{job_id}] JS DOCX -> {_jdocx}")
            else:
                logger.warning(f"[{job_id}] JS DOCX failed: {_r.stderr[:200]}")
        except Exception as _e:
            logger.warning(f"[{job_id}] JS DOCX error: {_e}")

        # ── Etape 9 — Cache + versions ────────────────────────────
        _step(job_id, 96, "Sauvegarde pour revision...")
        report_id = None
        try:
            section_scores    = rapport.get("_meta", {}).get("section_scores", {})
            sections_metadata = {
                sid: {
                    "title":   _section_title(sid),
                    "version": 1,
                    "content": content,
                    "score":   section_scores.get(sid, 0)
                }
                for sid, content in rapport.items() if not sid.startswith("_")
            }
            report_id = ReportCache.save_report_context(
                company=company, stats=stats, pos=positioning,
                web_pages=web_pages, pdf_financial=pdf_financial,
                corpus=corpus, generated_report=rapport,
                sections_metadata=sections_metadata,
                qa_answers=qa_layer if isinstance(qa_layer, list) else []
            )
            for sid, metadata in sections_metadata.items():
                try:
                    SectionVersioning.save_version(
                        report_id=report_id, section_id=sid,
                        content=metadata["content"],
                        refinement_instruction="Version originale",
                        score=metadata["score"], set_active=True
                    )
                except Exception as sv_err:
                    logger.warning(f"[{job_id}] Section version save failed {sid}: {sv_err}")
        except Exception as cache_err:
            logger.warning(f"[{job_id}] Cache failed: {cache_err}")
            report_id = None

        # ── Etape 10 — MLflow ─────────────────────────────────────
        try:
            from core.config import OPENAI_MODEL
            context_for_faith   = str(corpus)[:4000] if corpus else ""
            prompts_log         = []
            faithfulness_scores = []
            for sid, content in rapport.items():
                if sid.startswith("_"):
                    continue
                text = content if isinstance(content, str) else \
                       " ".join(str(v) for v in content.values() if isinstance(v, str)) \
                       if isinstance(content, dict) else ""
                if text and context_for_faith:
                    faithfulness_scores.append(compute_faithfulness_heuristic(context_for_faith, text))
                    prompts_log.append({"section": sid, "prompt": f"[section {sid}]", "response": text[:800]})
            log_report_generation(
                company_name        = request.company_name,
                report_id           = report_id or "",
                model_name          = OPENAI_MODEL,
                n_pdfs              = len(all_pdf_bytes),
                n_sections          = len([k for k in rapport if not k.startswith("_")]),
                source_table        = request.source_table or "",
                n_rag_chunks        = n_chunks,
                regime              = request.regime or "",
                qa_answers          = {"answers": qa_layer} if isinstance(qa_layer, list) else qa_layer,
                prompts             = prompts_log,
                faithfulness_scores = faithfulness_scores,
            )
        except Exception as mlf_err:
            logger.warning(f"[{job_id}] MLflow ignore: {mlf_err}")

        # ── Termine ───────────────────────────────────────────────
        job_service.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message=f"Rapport genere ({len(all_pdf_bytes)} PDF(s))" if all_pdf_bytes else "Rapport genere",
            result={
                "rapport":       rapport,
                "docx_path":     docx_path,
                "pdf_financial": pdf_financial,
                "stats":         stats,
                "positioning":   positioning,
                "pdf_count":     len(all_pdf_bytes),
                "report_id":     report_id,
            }
        )

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        job_service.update_job(job_id, status=JobStatus.FAILED, error=str(e),
                               message=f"Erreur : {str(e)[:200]}")


def _section_title(section_id: str) -> str:
    titles = {
        "s_identite":                "Fiche d'Identite",
        "s1_profil_operationnel":    "Profil Operationnel",
        "s2_analyse_financiere":     "Analyse Financiere",
        "s3_positionnement_marche":  "Positionnement Marche",
        "s4_facteurs_risque":        "Facteurs de Risque",
        "s5_facteurs_favorables":    "Facteurs Favorables",
        "s6_gouvernance_management": "Gouvernance & Management",
        "s7_benchmark_sectoriel":    "Benchmark Sectoriel",
        "s8_synthese_verdict":       "Synthese & Verdict",
        "s_benchmark_national":      "Benchmark National",
        "s_benchmark_leaders":       "Benchmark Leaders",
        "s_benchmark_international": "Benchmark International",
        "s_benchmark_mena":          "Benchmark MENA",
        "s_benchmark_maghreb":       "Benchmark Maghreb",
        "s_benchmark_ca":            "Benchmark Chiffre d'Affaires",
        "s_sources":                 "Sources",
    }
    return titles.get(section_id, section_id.replace("_", " ").title())
