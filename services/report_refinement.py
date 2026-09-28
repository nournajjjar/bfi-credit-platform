# backend/services/report_refinement.py

"""
Report Refinement Service
Core logic for refining report sections based on user instructions
"""

import json
import re
from typing import Dict, List, Tuple
from services.report_cache import ReportCache
from services.section_versioning import SectionVersioning
from services.qa_answering import format_qa_for_prompt


REFINEMENT_PROMPT = """
Tu es un analyste financier expert qui améliore des sections de rapports de crédit.

═══════════════════════════════════════════════════════════════════
SECTION ORIGINALE À AMÉLIORER
═══════════════════════════════════════════════════════════════════

Section: {section_title}

Contenu actuel (JSON):
{original_section}

Score actuel: {current_score}/5

═══════════════════════════════════════════════════════════════════
DONNÉES CONTEXTUELLES DISPONIBLES
═══════════════════════════════════════════════════════════════════

Informations entreprise:
{company_info}

Données Q&A web:
{qa_data}

Données financières PDF:
{financial_data}

Données RAG (sources officielles):
{rag_data}

═══════════════════════════════════════════════════════════════════
INSTRUCTION DE REFINEMENT
═══════════════════════════════════════════════════════════════════

{user_instruction}

═══════════════════════════════════════════════════════════════════
HISTORIQUE DE CONVERSATION (si applicable)
═══════════════════════════════════════════════════════════════════

{conversation_history}

═══════════════════════════════════════════════════════════════════
CONSIGNES STRICTES
═══════════════════════════════════════════════════════════════════

1. STRUCTURE: Conserve EXACTEMENT la structure JSON de la section originale
2. CHANGEMENTS: Applique UNIQUEMENT les modifications demandées
3. STYLE: Maintiens le même niveau professionnel et analytique
4. DONNÉES: Utilise les données contextuelles pour enrichir
5. AMÉLIORATION: Vise un score supérieur à {current_score}/5

═══════════════════════════════════════════════════════════════════
FORMAT DE RÉPONSE
═══════════════════════════════════════════════════════════════════

Retourne UNIQUEMENT un objet JSON avec:

{{
  "refined_section": {{
    // La section améliorée avec structure identique à l'original
  }},
  "changes_summary": "Description concise des changements effectués (2-3 phrases)",
  "estimated_score": 4
}}

NE PAS inclure de texte avant ou après le JSON.
"""


class ReportRefinement:
    """Service for refining report sections with LLM"""

    @staticmethod
    async def refine_section(
        report_id: str,
        section_id: str,
        instruction: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        print(f"\n{'='*60}")
        print(f"REFINEMENT REQUEST — {section_id}")
        print(f"Instruction: {instruction}")
        print(f"{'='*60}\n")

        # 1. Load report context
        context = ReportCache.get_section_context(report_id, section_id)
        if not context:
            raise ValueError(f"Report {report_id} not found")

        original_section = context["original_content"]
        section_title = context["section_metadata"].get("title", section_id)
        current_score = context["section_metadata"].get("score", 0)
        company = context.get("company", {})

        # 2. Prepare context data
        company_info = ReportRefinement._format_company_info(company)
        qa_data      = format_qa_for_prompt(context.get("qa_answers", []))
        financial_data = ReportRefinement._format_financial_data(
            context.get("pdf_financial", {})
        )

        # 3. RAG embeddings
        rag_data = ""
        try:
            from services.embeddings_service import retrieve_relevant_chunks
            chunks = retrieve_relevant_chunks(
                company.get("denomination", ""), section_id, top_k=5
            )
            if chunks:
                rag_data = "\n".join(chunks)
        except Exception:
            rag_data = "RAG non disponible"

        # 4. Format conversation history
        history_text = ReportRefinement._format_conversation(
            conversation_history or []
        )

        # 5. Build refinement prompt
        prompt = REFINEMENT_PROMPT.format(
            section_title=section_title,
            original_section=json.dumps(original_section, indent=2, ensure_ascii=False),
            current_score=current_score,
            company_info=company_info,
            qa_data=qa_data,
            financial_data=financial_data,
            rag_data=rag_data[:1000],
            user_instruction=instruction,
            conversation_history=history_text
        )

        # 6. Call LLM
        try:
            from core.openai_client import get_openai_client
            from core.config import OPENAI_MODEL
            client = get_openai_client()
            model = OPENAI_MODEL
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=3000,
                timeout=90
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

            result = json.loads(raw)
            refined_section = result.get("refined_section", {})
            changes_summary = result.get("changes_summary", "Section refined")
            estimated_score = result.get("estimated_score", current_score)

        except Exception as e:
            print(f"LLM refinement failed: {e}")
            raise

        # 7. Save new version
        new_version = SectionVersioning.save_version(
            report_id=report_id,
            section_id=section_id,
            content=refined_section,
            refinement_instruction=instruction,
            changes_summary=changes_summary,
            score=estimated_score,
            set_active=False
        )

        print(f"Refinement complete — Version {new_version}")

        return {
            "original":      original_section,
            "refined":       refined_section,
            "changes_summary": changes_summary,
            "new_version":   new_version,
            "score_after":   estimated_score,
            "score_before":  current_score
        }

    @staticmethod
    def _format_company_info(company: Dict) -> str:
        return (
            f"Denomination: {company.get('denomination', '')}\n"
            f"Secteur: {company.get('label_secteur', '')}\n"
            f"Gouvernorat: {company.get('gouvernorat', '')}\n"
            f"Activites: {company.get('activites', '')}\n"
            f"Produits: {company.get('produits', '')}\n"
            f"Capital: {company.get('capital', '')} DT\n"
            f"Emploi: {company.get('emploi', '')} personnes\n"
            f"Regime: {company.get('regime', '')}\n"
            f"Creation: {company.get('entree_production', '')}\n"
            f"Site web: {company.get('url', 'Non disponible')}"
        )

    @staticmethod
    def _format_financial_data(pdf_financial: Dict) -> str:
        if not pdf_financial:
            return "Aucune donnee financiere PDF disponible"
        lines = []
        if cpc := pdf_financial.get("cpc", {}):
            lines.append("Compte de Produits et Charges:")
            for k, v in cpc.items():
                if v: lines.append(f"  {k}: {v}")
        if actif := pdf_financial.get("bilan_actif", {}):
            lines.append("\nBilan Actif:")
            for k, v in actif.items():
                if v: lines.append(f"  {k}: {v}")
        if passif := pdf_financial.get("bilan_passif", {}):
            lines.append("\nBilan Passif:")
            for k, v in passif.items():
                if v: lines.append(f"  {k}: {v}")
        return "\n".join(lines) if lines else "Donnees financieres partielles"

    @staticmethod
    def _format_conversation(history: List[Dict]) -> str:
        if not history:
            return "Aucun historique (premiere demande)"
        lines = []
        for i, msg in enumerate(history, 1):
            role = "Utilisateur" if msg.get("role") == "user" else "Assistant"
            lines.append(f"{i}. {role}: {msg.get('content', '')}")
        return "\n".join(lines)

    @staticmethod
    def save_conversation(
        report_id: str,
        section_id: str,
        user_message: str,
        bot_response: str,
        refinement_applied: bool = False
    ):
        from Database import get_conn
        conn = get_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO refinement_conversations
                (report_id, section_id, user_message, bot_response, refinement_applied)
                VALUES (%s, %s, %s, %s, %s)
            """, (report_id, section_id, user_message, bot_response, refinement_applied))
            conn.commit()
        finally:
            cur.close(); conn.close()

    @staticmethod
    def get_conversation_history(report_id: str, section_id: str) -> List[Dict]:
        from Database import get_conn
        conn = get_conn()
        cur  = conn.cursor()
        try:
            cur.execute("""
                SELECT user_message, bot_response, refinement_applied, created_at
                FROM refinement_conversations
                WHERE report_id = %s AND section_id = %s
                ORDER BY created_at ASC
            """, (report_id, section_id))
            history = []
            for row in cur.fetchall():
                history.append({"role": "user",      "content": row[0], "timestamp": row[3].isoformat()})
                if row[1]:
                    history.append({"role": "assistant", "content": row[1], "applied": row[2], "timestamp": row[3].isoformat()})
            return history
        finally:
            cur.close(); conn.close()