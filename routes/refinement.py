# backend/routes/refinement.py
"""
API Routes for Report Refinement
Interactive report editing via chat interface
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import os

from services.report_cache import ReportCache
from services.report_refinement import ReportRefinement
from services.section_versioning import SectionVersioning
from services.docx_updater import DocxUpdater

router = APIRouter(prefix="/api/refinement", tags=["refinement"])


# ══════════════════════════════════════════════════════════════════
# MODÈLES
# ══════════════════════════════════════════════════════════════════

class RefineRequest(BaseModel):
    instruction: str
    conversation_history: Optional[List[Dict]] = None

class ApplyChangesRequest(BaseModel):
    section_changes: Dict[str, int]

class SectionSelector(BaseModel):
    section_id: str
    version: int

class AskRequest(BaseModel):
    question: str
    section_id: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════

@router.get("/reports")
async def list_reports(limit: int = 50):
    try:
        reports = ReportCache.list_reports(limit=limit)
        return {"success": True, "reports": reports, "count": len(reports)}
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/sections")
async def list_sections(report_id: str):
    try:
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise HTTPException(status_code=404, detail="Rapport introuvable")
        sections = []
        for section_id, metadata in cache["sections_metadata"].items():
            active = SectionVersioning.get_active_version(report_id, section_id)
            sections.append({
                "section_id":      section_id,
                "title":           metadata.get("title", section_id),
                "current_version": active["version"] if active else 1,
                "score":           active["score"] if active else metadata.get("score", 0),
                "word_count":      len(str(metadata.get("content", "")).split()),
                "can_refine":      True,
                "has_changes":     bool(active and active["version"] > 1)
            })
        return {
            "success":      True,
            "report_id":    report_id,
            "company_name": cache["company"].get("denomination", ""),
            "sections":     sections
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/sections/{section_id}/refine")
async def refine_section(report_id: str, section_id: str, request: RefineRequest):
    try:
        result = await ReportRefinement.refine_section(
            report_id=report_id,
            section_id=section_id,
            instruction=request.instruction,
            conversation_history=request.conversation_history
        )
        ReportRefinement.save_conversation(
            report_id=report_id,
            section_id=section_id,
            user_message=request.instruction,
            bot_response=result["changes_summary"],
            refinement_applied=False
        )
        return {
            "success":          True,
            "report_id":        report_id,
            "section_id":       section_id,
            "original_content": result["original"],
            "refined_content":  result["refined"],
            "changes_summary":  result["changes_summary"],
            "new_version":      result["new_version"],
            "score_before":     result["score_before"],
            "score_after":      result["score_after"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/sections/{section_id}/history")
async def get_section_history(report_id: str, section_id: str):
    try:
        history = SectionVersioning.get_version_history(report_id, section_id)
        return {"success": True, "report_id": report_id, "section_id": section_id, "versions": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/sections/{section_id}/versions/{version}")
async def get_section_version(report_id: str, section_id: str, version: int):
    try:
        version_data = SectionVersioning.get_version(report_id, section_id, version)
        if not version_data:
            raise HTTPException(status_code=404, detail=f"Version {version} introuvable")
        return {
            "success":                True,
            "report_id":              report_id,
            "section_id":             section_id,
            "version":                version,
            "content":                version_data["content"],
            "score":                  version_data["score"],
            "refinement_instruction": version_data.get("refinement_instruction"),
            "changes_summary":        version_data.get("changes_summary"),
            "created_at":             version_data["created_at"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/sections/{section_id}/apply/{version}")
async def apply_section_version(report_id: str, section_id: str, version: int):
    try:
        DocxUpdater.apply_section_change(report_id, section_id, version)
        ReportRefinement.save_conversation(
            report_id=report_id, section_id=section_id,
            user_message=f"Applied version {version}",
            bot_response=f"Version {version} is now active",
            refinement_applied=True
        )
        return {"success": True, "message": f"Version {version} appliquée", "active_version": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/sections/{section_id}/revert")
async def revert_section(report_id: str, section_id: str):
    try:
        DocxUpdater.revert_section(report_id, section_id)
        return {"success": True, "message": f"{section_id} réinitialisée à v1", "active_version": 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/pending-changes")
async def get_pending_changes(report_id: str):
    try:
        pending = DocxUpdater.get_pending_changes(report_id)
        return {"success": True, "report_id": report_id, "pending_changes": pending, "count": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/preview-changes")
async def preview_changes(report_id: str, request: ApplyChangesRequest):
    try:
        preview = DocxUpdater.preview_changes(report_id, request.section_changes)
        return {"success": True, "report_id": report_id, "changes": preview}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/generate")
async def generate_updated_report(
    report_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[ApplyChangesRequest] = None
):
    try:
        section_changes = request.section_changes if request else None
        docx_path = DocxUpdater.generate_updated_report(
            report_id=report_id, section_changes=section_changes
        )
        if not os.path.exists(docx_path):
            raise HTTPException(status_code=500, detail="Génération DOCX échouée")
        return {
            "success":         True,
            "message":         "Rapport mis à jour généré",
            "report_id":       report_id,
            "download_url":    f"/api/refinement/reports/{report_id}/download",
            "changes_applied": len(section_changes) if section_changes else "toutes actives"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str):
    try:
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise HTTPException(status_code=404, detail="Rapport introuvable")
        company_name = cache["company"].get("denomination", "rapport")
        safe_name    = "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in company_name).strip()
        output_dir   = "database/output"
        import glob
        patterns  = [
            f"{output_dir}/rapport_{safe_name}_updated.docx",
            f"{output_dir}/rapport_{safe_name}_*.docx",
            f"{output_dir}/rapport_{safe_name.replace(' ', '_')}*.docx",
        ]
        docx_path = None
        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                docx_path = max(matches, key=os.path.getmtime)
                break
        if not docx_path or not os.path.exists(docx_path):
            raise HTTPException(status_code=404, detail="Fichier DOCX introuvable. Générez d'abord le rapport.")
        return FileResponse(
            path=docx_path,
            filename=f"rapport_{safe_name}_updated.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}/conversation/{section_id}")
async def get_conversation(report_id: str, section_id: str):
    try:
        history = ReportRefinement.get_conversation_history(report_id, section_id)
        return {"success": True, "report_id": report_id, "section_id": section_id, "conversation": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    try:
        ReportCache.delete_report_cache(report_id)
        return {"success": True, "message": f"Rapport {report_id} supprimé"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-db")
async def test_db():
    try:
        from Database import get_conn
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('reports','section_versions','refinement_conversations')")
        tables = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"tables_found": tables, "missing": [t for t in ['reports','section_versions','refinement_conversations'] if t not in tables]}
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug")
async def debug():
    import traceback
    try:
        from Database import get_conn
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT current_database()")
        db_name = cur.fetchone()[0]
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"database": db_name, "tables": tables}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


# ══════════════════════════════════════════════════════════════════
# Q&A CHATBOT — accès à toutes les données du rapport
# ══════════════════════════════════════════════════════════════════

@router.post("/reports/{report_id}/ask")
async def ask_question(
    report_id: str,
    request: AskRequest,
    background_tasks: BackgroundTasks
):
    """Répond à une question en utilisant TOUTES les données disponibles."""
    try:
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise HTTPException(404, "Rapport introuvable")

        company  = (cache.get("company", {}) or {}).get("denomination", "l'entreprise")
        question = request.question
        parts    = []

        # 1 — QA answers (26 questions collectées)
        qa_answers = cache.get("qa_answers", []) or []
        if isinstance(qa_answers, dict):
            qa_answers = qa_answers.get("answers", [])
        if qa_answers:
            qa_text = "\n".join(
                f"Q: {a.get('question','')}\nR: {a.get('answer','')}"
                for a in qa_answers
                if a.get("answer") and "non disponible" not in (a.get("answer") or "").lower()
            )
            if qa_text:
                parts.append(f"REPONSES COLLECTEES SUR L'ENTREPRISE:\n{qa_text[:4000]}")

        # 2 — Corpus web
        corpus = cache.get("corpus", "") or ""
        if isinstance(corpus, list):
            corpus = "\n".join(str(c) for c in corpus)
        if corpus:
            parts.append(f"CORPUS WEB:\n{str(corpus)[:2000]}")

        # 3 — PDF financial pages
        pf = cache.get("pdf_financial", {}) or {}
        for page in (pf.get("raw_pages", []) or [])[:10]:
            if isinstance(page, dict):
                notes = page.get("notes", "")
                if notes and isinstance(notes, str) and len(notes) > 20:
                    parts.append(notes[:500])

        # 4 — Generated report sections
        report_data = cache.get("generated_report", {}) or {}
        for key, section in list(report_data.items())[:10]:
            if key.startswith("_"):
                continue
            text = ""
            if isinstance(section, str):
                text = section
            elif isinstance(section, dict):
                text = " ".join(str(v) for v in section.values() if isinstance(v, str))
            if text:
                parts.append(f"{key.upper()}:\n{text[:500]}")

        # 5 — RAG embeddings
        try:
            from services.embeddings_service import retrieve_relevant_chunks
            chunks = retrieve_relevant_chunks(company, question, top_k=5)
            if chunks:
                parts.append(f"DONNEES OFFICIELLES (RAG):\n" + "\n".join(chunks))
        except Exception:
            pass

        full_context = "\n\n---\n\n".join(parts)[:8000]

        prompt = f"""Tu es un analyste credit expert specialise dans les entreprises tunisiennes.
Reponds precisement a la question suivante en te basant UNIQUEMENT sur les informations disponibles dans le contexte.

ENTREPRISE: {company}

CONTEXTE COMPLET:
{full_context}

QUESTION: {question}

Instructions:
- Reponds en francais de facon precise et professionnelle
- Si l'information est dans le contexte, cite-la explicitement avec des chiffres precis
- Ne dis JAMAIS que l'information n'est pas disponible si elle est dans le contexte
- Reponse concise et directe (3-6 phrases)"""

        from core.openai_client import get_openai_client
        from core.config import OPENAI_MODEL
        client = get_openai_client()
        model = OPENAI_MODEL
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=600,
            timeout=45
        )
        answer = response.choices[0].message.content.strip()

        # MLflow logging (non-bloquant)
        try:
            from services.mlflow_tracker import log_qa_interaction
            background_tasks.add_task(
                log_qa_interaction,
                report_id, company, question, answer,
                full_context, request.section_id, False
            )
        except Exception:
            pass

        return {"success": True, "answer": answer, "type": "question"}

    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, detail=str(e))