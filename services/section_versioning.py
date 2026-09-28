# backend/services/section_versioning.py

"""
Section Versioning Service
Tracks version history of refined report sections
"""

import json

def _safe_json(val):
    if not val: return None
    if isinstance(val, (dict, list)): return val
    try:
        s = val.decode("utf-8") if isinstance(val, (bytes, memoryview)) else str(val)
        return json.loads(s) if s.strip() else None
    except Exception:
        return None

from typing import Dict, List, Optional
from datetime import datetime
from Database import get_conn



class SectionVersioning:
    """Manage section version history and refinements"""

    @staticmethod
    def save_version(
        report_id: str,
        section_id: str,
        content: Dict,
        refinement_instruction: str = None,
        changes_summary: str = None,
        score: int = None,
        set_active: bool = False
    ) -> int:
        """
        Save a new version of a section.
        Returns the version number.
        """
        conn = get_conn()
        cur = conn.cursor()

        try:
            # Get next version number
            cur.execute("""
                SELECT COALESCE(MAX(version), 0) + 1
                FROM section_versions
                WHERE report_id = %s AND section_key = %s
            """, (report_id, section_id))

            next_version = cur.fetchone()[0]

            # If setting active, deactivate all other versions first
            if set_active:
                cur.execute("""
                    UPDATE section_versions
                    SET is_active = FALSE
                    WHERE report_id = %s AND section_key = %s
                """, (report_id, section_id))

            # Insert new version
            cur.execute("""
                INSERT INTO section_versions (
                    report_id, section_key, version, content, score,
                    refinement_instruction, changes_summary, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                report_id,
                section_id,
                next_version,
                json.dumps(content),
                score,
                refinement_instruction,
                changes_summary,
                set_active
            ))

            version_id = cur.fetchone()[0]
            conn.commit()

            print(f"✓ Saved section version {next_version} for {section_id}")
            return next_version

        except Exception as e:
            conn.rollback()
            print(f"✗ Failed to save version: {e}")
            raise
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_version(report_id: str, section_id: str, version: int) -> Optional[Dict]:
        """Get a specific version of a section"""
        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT content, score, refinement_instruction, changes_summary, created_at
                FROM section_versions
                WHERE report_id = %s AND section_key = %s AND version = %s
            """, (report_id, section_id, version))

            row = cur.fetchone()
            if row:
                return {
                    "content": (row[0] if isinstance(row[0], (dict, list)) else (None if not row[0] else json.loads(row[0]))),
                    "score": row[1],
                    "refinement_instruction": row[2],
                    "changes_summary": row[3],
                    "created_at": row[4].isoformat()
                }
            return None

        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_active_version(report_id: str, section_id: str) -> Optional[Dict]:
        """Get the currently active version of a section"""
        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT version, content, score, refinement_instruction, created_at
                FROM section_versions
                WHERE report_id = %s AND section_key = %s AND is_active = TRUE
                ORDER BY version DESC
                LIMIT 1
            """, (report_id, section_id))

            row = cur.fetchone()
            if row:
                return {
                    "version": row[0],
                    "content": (row[1] if isinstance(row[1], (dict, list)) else _safe_json(row[1])),
                    "score": row[2],
                    "refinement_instruction": row[3],
                    "created_at": row[4].isoformat()
                }
            return None

        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_version_history(report_id: str, section_id: str) -> List[Dict]:
        """Get all versions of a section"""
        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT version, score, refinement_instruction,
                       changes_summary, is_active, created_at
                FROM section_versions
                WHERE report_id = %s AND section_key = %s
                ORDER BY version ASC
            """, (report_id, section_id))

            return [
                {
                    "version": row[0],
                    "score": row[1],
                    "refinement_instruction": row[2] or "Original generation",
                    "changes_summary": row[3],
                    "is_active": row[4],
                    "created_at": row[5].isoformat()
                }
                for row in cur.fetchall()
            ]

        finally:
            cur.close()
            conn.close()

    @staticmethod
    def set_active_version(report_id: str, section_id: str, version: int):
        """Set a specific version as active"""
        conn = get_conn()
        cur = conn.cursor()

        try:
            # Deactivate all versions
            cur.execute("""
                UPDATE section_versions
                SET is_active = FALSE
                WHERE report_id = %s AND section_key = %s
            """, (report_id, section_id))

            # Activate specified version
            cur.execute("""
                UPDATE section_versions
                SET is_active = TRUE
                WHERE report_id = %s AND section_key = %s AND version = %s
            """, (report_id, section_id, version))

            conn.commit()
            print(f"✓ Activated version {version} for {section_id}")

        except Exception as e:
            conn.rollback()
            print(f"✗ Failed to set active version: {e}")
            raise
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_all_active_versions(report_id: str) -> Dict[str, Dict]:
        """Get all active section versions for a report"""
        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT section_key, version, content, score
                FROM section_versions
                WHERE report_id = %s AND is_active = TRUE
            """, (report_id,))

            return {
                row[0]: {
                    "version": row[1],
                    "content": _safe_json(row[2]),
                    "score": row[3]
                }
                for row in cur.fetchall()
            }

        finally:
            cur.close()
            conn.close()

    @staticmethod
    def compare_versions(
        report_id: str,
        section_id: str,
        version1: int,
        version2: int
    ) -> Dict:
        """Compare two versions of a section"""
        v1 = SectionVersioning.get_version(report_id, section_id, version1)
        v2 = SectionVersioning.get_version(report_id, section_id, version2)

        if not v1 or not v2:
            raise ValueError("One or both versions not found")

        return {
            "version1": {
                "version": version1,
                "content": v1["content"],
                "score": v1["score"]
            },
            "version2": {
                "version": version2,
                "content": v2["content"],
                "score": v2["score"]
            },
            "changes": {
                "score_delta": (v2["score"] or 0) - (v1["score"] or 0),
                "refinement": v2.get("refinement_instruction", "")
            }
        }
