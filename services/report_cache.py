# backend/services/report_cache.py

import json
import uuid
from datetime import datetime
from typing import Dict, Optional
from Database import get_conn
import os


class ReportCache:
    """
    Service for caching report generation context to enable refinement.
    """

    @staticmethod
    def save_report_context(
        company: Dict,
        stats: Dict,
        pos: Dict,
        web_pages: list,
        pdf_financial: Dict,
        corpus: str,
        generated_report: Dict,
        sections_metadata: Dict,
        qa_answers: list = None
    ) -> str:
        report_id = str(uuid.uuid4())
        cache_data = {
            "report_id": report_id,
            "company": company,
            "stats": stats,
            "pos": pos,
            "web_pages": web_pages,
            "pdf_financial": pdf_financial,
            "corpus": corpus,
            "generated_report": generated_report,
            "sections_metadata": sections_metadata,
            "qa_answers": qa_answers or [],
            "created_at": datetime.now().isoformat()
        }
        conn = get_conn()   # ← fixed
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO reports (id, company_name, denomination, generated_at, original_data)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                report_id,
                company.get("denomination", ""),
                company.get("denomination", ""),
                datetime.now(),
                json.dumps(cache_data, ensure_ascii=False, default=str).replace('\u0000', '')
            ))
            conn.commit()
            print(f"✓ Report context cached: {report_id}")
            return report_id
        except Exception as e:
            conn.rollback()
            print(f"✗ Failed to cache report: {e}")
            raise
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def load_report_context(report_id: str) -> Optional[Dict]:
        conn = get_conn()   # ← fixed
        cur = conn.cursor()
        try:
            cur.execute("SELECT original_data FROM reports WHERE id = %s", (report_id,))
            result = cur.fetchone()
            if result:
                r = result[0]; return r if isinstance(r, dict) else json.loads(r)
            return None
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_section_context(report_id: str, section_id: str) -> Dict:
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise ValueError(f"Report {report_id} not found")
        section_meta = cache["sections_metadata"].get(section_id, {})
        return {
            "company":          cache["company"],
            "stats":            cache["stats"],
            "pos":              cache["pos"],
            "corpus":           cache["corpus"],
            "pdf_financial":    cache["pdf_financial"],
            "qa_answers":       cache.get("qa_answers", []),
            "section_metadata": section_meta,
            "original_content": cache["generated_report"].get(section_id, {}),
            "context_used":     section_meta.get("context_used", {})
        }

    @staticmethod
    def update_section_in_cache(report_id: str, section_id: str, new_content: Dict):
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise ValueError(f"Report {report_id} not found")
        cache["generated_report"][section_id] = new_content
        conn = get_conn()   # ← fixed
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE reports
                SET original_data = %s, current_version = current_version + 1
                WHERE id = %s
                 """, (json.dumps(cache, ensure_ascii=False, default=str).replace('\u0000', ''), report_id))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def list_reports(limit: int = 50) -> list:
        conn = get_conn()   # ← fixed
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, company_name, generated_at, current_version
                FROM reports
                ORDER BY generated_at DESC
                LIMIT %s
            """, (limit,))
            return [
                {
                    "report_id":    str(row[0]),
                    "company_name": row[1],
                    "generated_at": row[2].isoformat(),
                    "version":      row[3]
                }
                for row in cur.fetchall()
            ]
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def delete_report_cache(report_id: str):
        conn = get_conn()   # ← fixed
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
            cur.execute("DELETE FROM section_versions WHERE report_id = %s", (report_id,))
            cur.execute("DELETE FROM refinement_conversations WHERE report_id = %s", (report_id,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
