"""
PDF extraction routes — standalone + full pipeline (supports up to 3 PDFs)
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from schemas.job_schema import JobStatus, JobType
from services.job_service import job_service
from services.pdf_extractor import extract_pdf_financial
from services.database_service import get_sector_stats, compute_positioning
from services.export import generate_docx_report
from services.search import tavily_search, collect_web_content
from core.logger import setup_logger
from services.database_service import fuzzy_search_companies

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/pdf", tags=["PDF"])


# ── 1. Standalone extraction (single PDF) ────────────────────────────────────
@router.post("/extract")
async def extract_pdf(file: UploadFile = File(...)):
    """
    Upload a single CMF PDF → returns structured financial data immediately.
    Use this to test PDF extraction before the full pipeline.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "PDF too large (max 20MB)")

    job_id = job_service.create_job(
        JobType.REPORT_GENERATION,
        f"PDF extraction: {file.filename}",
        {"filename": file.filename}
    )
    job_service.update_job(job_id, status=JobStatus.RUNNING, progress=10, message="Extracting PDF...")

    try:
        result = await run_in_threadpool(extract_pdf_financial, pdf_bytes)
        job_service.update_job(
            job_id, status=JobStatus.COMPLETED, progress=100,
            message="Extraction complete", result=result
        )
        return {
            "success":         True,
            "job_id":          job_id,
            "pages_processed": len(result.get("raw_pages", [])),
            "financial_data":  result,
        }
    except Exception as e:
        job_service.update_job(job_id, status=JobStatus.FAILED, error=str(e))
        logger.error(f"PDF extraction failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))


# ── 2. Extract + full pipeline (up to 3 PDFs as separate fields) ─────────────
@router.post("/extract-and-report")
async def extract_and_report(
    background_tasks:  BackgroundTasks,
    # ── PDF files (each is an optional separate field — Swagger shows 3 pickers)
    file1:             UploadFile       = File(...,       description="PDF file 1 (required) — e.g. Bilan"),
    file2:             Optional[UploadFile] = File(None,  description="PDF file 2 (optional) — e.g. CPC"),
    file3:             Optional[UploadFile] = File(None,  description="PDF file 3 (optional) — e.g. Annexes"),
    # ── Company info as query params
    company_name:      str = Query(...,        description="Company name (required)"),
    source_table:      str = Query(default="", description="DB table name (auto-detected if empty)"),
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
    """
    Upload 1, 2 or 3 CMF PDFs + company info → full report pipeline.
    - file1 is required (e.g. Bilan)
    - file2 and file3 are optional (e.g. CPC, Annexes)
    - Multiple PDFs are merged before analysis
    - Returns job_id immediately — poll /api/jobs/{job_id} for progress
    """
    # Collect whichever files were provided
    raw_files = [f for f in [file1, file2, file3] if f is not None]

    # Validate all provided files
    for f in raw_files:
        if f.filename and not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"'{f.filename}' is not a PDF")

    # Read bytes
    all_pdf_bytes = []
    total_size    = 0
    for f in raw_files:
        data        = await f.read()
        if not data:          # empty optional field sent by Swagger
            continue
        total_size += len(data)
        if total_size > 50 * 1024 * 1024:
            raise HTTPException(400, "Total PDF size exceeds 50MB")
        all_pdf_bytes.append({"filename": f.filename or "document.pdf", "bytes": data})

    if not all_pdf_bytes:
        raise HTTPException(400, "At least one PDF file is required")

    filenames = [f["filename"] for f in all_pdf_bytes]
    company   = {
        "denomination":      company_name,
        "source_table":      source_table,
        "gouvernorat":       gouvernorat,
        "label_secteur":     label_secteur,
        "activites":         activites,
        "produits":          produits,
        "capital":           capital,
        "emploi":            emploi,
        "regime":            regime,
        "entree_production": entree_production,
        "url":               url,
        "source_url":        "",
    }

    job_id = job_service.create_job(
        JobType.REPORT_GENERATION,
        f"PDF + Report: {company_name}",
        {"company_name": company_name, "filenames": filenames, "pdf_count": len(filenames)}
    )

    background_tasks.add_task(_run_pdf_pipeline, job_id, all_pdf_bytes, company)
    return {
        "success":   True,
        "job_id":    job_id,
        "pdf_count": len(all_pdf_bytes),
        "filenames": filenames,
        "message":   "Pipeline started — poll /api/jobs/{job_id}",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _step(job_id: str, pct: int, msg: str):
    job_service.update_job(job_id, status=JobStatus.RUNNING, progress=pct, message=msg)
    logger.info(f"[{job_id}] {pct}% — {msg}")


def _merge_pdf_financial(results: list) -> dict:
    """Merge multiple PDF extraction results into one combined dict."""
    merged    = {}
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
                else:
                    if value and str(value).strip() not in ("", "null", "None"):
                        merged[key] = value
    merged["raw_pages"] = all_pages
    return merged


def _run_pdf_pipeline(job_id: str, all_pdf_bytes: list, company: dict):
    logger.info(f"[{job_id}] Company after DB lookup: {company}")
    try:
        total = len(all_pdf_bytes)

        # Step 1 — extract all PDFs
        _step(job_id, 5, f"Extraction de {total} PDF(s)...")
        extraction_results = []
        for i, pdf in enumerate(all_pdf_bytes):
            pct = 5 + int(15 * (i + 1) / total)
            _step(job_id, pct, f"Extraction PDF {i+1}/{total} : {pdf['filename']}...")
            result = extract_pdf_financial(pdf["bytes"])
            pages  = len(result.get("raw_pages", []))
            logger.info(f"[{job_id}] '{pdf['filename']}' → {pages} pages extraites")
            extraction_results.append(result)

        pdf_financial = _merge_pdf_financial(extraction_results) if total > 1 else extraction_results[0]
        total_pages   = len(pdf_financial.get("raw_pages", []))
        _step(job_id, 22, f"PDFs extraits — {total_pages} pages au total")

        # Step 2 — auto DB lookup
        _step(job_id, 25, "Recherche entreprise en base de données...")
        if not company.get("source_table"):
            try:

                results = fuzzy_search_companies(company["denomination"], top_n=1)
                if results:
                    best = results[0]
                    company["source_table"]      = best.get("source_table", "")
                    company["label_secteur"]     = best.get("label_secteur", "")
                    company["gouvernorat"]       = company["gouvernorat"] or best.get("gouvernorat", "")
                    company["activites"]         = best.get("activites", "")
                    company["produits"]          = best.get("produits", "")
                    company["capital"]           = best.get("capital", "")
                    company["emploi"]            = best.get("emploi", "")
                    company["regime"]            = best.get("regime", "")
                    company["entree_production"] = best.get("entree_production", "")
                    company["url"]               = best.get("url", "")
                    company["source_url"]        = best.get("source_url", "")
                    logger.info(f"[{job_id}] DB match: {best.get('denomination')}")
            except Exception as e:
                logger.warning(f"[{job_id}] DB lookup failed: {e}")

        # Step 3 — sector stats
        _step(job_id, 30, "Statistiques sectorielles...")
        stats       = get_sector_stats(company["source_table"]) if company["source_table"] else {}
        positioning = compute_positioning(company, stats)

        # Step 4 — Tavily search
        _step(job_id, 38, "Recherche Tavily...")
        search_results = tavily_search(
            company["denomination"],
            company.get("gouvernorat", "Tunisie"),
            company.get("label_secteur", "")
        )

        # Step 5 — collect web content
        _step(job_id, 48, f"Collecte web ({len(search_results)} résultats)...")
        web_pages = collect_web_content(search_results)

        # Step 6 — deep research
        _step(job_id, 58, "Deep research (Q&A web)...")
        from services.questions import get_specific_questions
        from services.qa_answering import answer_questions
        from services.search import build_web_corpus
        deep_corpus    = build_web_corpus(web_pages)
        deep_questions = get_specific_questions(company, positioning)
        deep_answers   = answer_questions(deep_questions, deep_corpus)
        logger.info(f"[{job_id}] Deep research: {len(deep_answers)} réponses")

        try:
            from services.embeddings_service import process_and_store
            process_and_store(
                company=company["denomination"],
                source="deep_research",
                data={"findings": {a.get("theme", "general"): [a] for a in deep_answers}},
                metadata={"source_table": company.get("source_table", "")}
            )
        except Exception as emb_err:
            logger.warning(f"[{job_id}] Embedding deep research ignoré: {emb_err}")

        # Step 7 — full report
        _step(job_id, 68, "Génération rapport (Q&A + sections LLM)...")
        from services.report import build_report
        rapport, qa_layer, tracker = build_report(
            company, stats, positioning, web_pages, search_results, pdf_financial
        )

        # Step 8 — store PDF embeddings
        _step(job_id, 85, "Indexation PDF (embeddings)...")
        try:
            from services.embeddings_service import process_and_store
            process_and_store(
                company=company["denomination"],
                source="pdf",
                data=pdf_financial,
                metadata={"source_table": company.get("source_table", ""), "pdf_count": total}
            )
        except Exception as emb_err:
            logger.warning(f"[{job_id}] Embedding PDF ignoré: {emb_err}")

        # Step 9 — export DOCX
        _step(job_id, 92, "Export DOCX...")
        docx_path = generate_docx_report(company, rapport, stats, positioning)

        job_service.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message=f"Rapport généré ({total} PDF(s) analysé(s))",
            result={
                "rapport":       rapport,
                "docx_path":     docx_path,
                "pdf_financial": pdf_financial,
                "stats":         stats,
                "positioning":   positioning,
                "pdf_count":     total,
            }
        )

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        job_service.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
            message=f"Erreur pipeline : {str(e)[:200]}",
        )