# backend/services/docx_updater.py

"""
DOCX Updater Service
Merges refined sections back into DOCX reports
"""

import os
from typing import Dict
from services.export import generate_docx_report
from services.report_cache import ReportCache
from services.section_versioning import SectionVersioning
from Database import get_conn

class DocxUpdater:
    """Update DOCX reports with refined sections"""

    @staticmethod
    def generate_updated_report(
        report_id: str,
        section_changes: Dict[str, int] = None,
        output_path: str = None
    ) -> str:
        """
        Generate new DOCX with refined sections.

        Args:
            report_id: UUID of cached report
            section_changes: Dict of {section_id: version} to apply
                           If None, uses all active versions
            output_path: Where to save DOCX (auto-generated if None)

        Returns:
            Path to generated DOCX file
        """
        print(f"\n{'='*60}")
        print(f"GENERATING UPDATED DOCX")
        print(f"{'='*60}")
        print(f"Report ID: {report_id}")

        # 1. Load original report context
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise ValueError(f"Report {report_id} not found")

        # 2. Get base report
        report = cache["generated_report"].copy()
        company = cache["company"]

        # 3. Determine which sections to update
        if section_changes:
            # Use specified versions
            print(f"Applying {len(section_changes)} section changes")
            for section_id, version in section_changes.items():
                version_data = SectionVersioning.get_version(
                    report_id, section_id, version
                )
                if version_data:
                    report[section_id] = version_data["content"]
                    print(f"  ✓ {section_id}: version {version}")
        else:
            # Use all active versions
            active_versions = SectionVersioning.get_all_active_versions(report_id)
            print(f"Applying {len(active_versions)} active versions")
            for section_id, version_data in active_versions.items():
                report[section_id] = version_data["content"]
                print(f"  ✓ {section_id}: version {version_data['version']}")

        # 4. Generate output path if not provided
        if not output_path:
            company_name = company.get("denomination", "report")
            safe_name = "".join(
                c if c.isalnum() or c in (' ', '_') else '_'
                for c in company_name
            )
            output_path = f"database/output/rapport_{safe_name}_updated.docx"

        # 5. Generate DOCX using existing export service
        print(f"Generating DOCX: {output_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Generate DOCX
        stats = cache.get('stats', {})
        pos   = cache.get('pos', {})
        docx_path = generate_docx_report(company, report, stats, pos)

        print(f"✓ DOCX generated: {docx_path}")
        print(f"{'='*60}\n")

        return docx_path

    @staticmethod
    def preview_changes(report_id: str, section_changes: Dict[str, int]) -> Dict:
        """
        Preview what sections will be changed without generating DOCX.

        Returns summary of changes.
        """
        cache = ReportCache.load_report_context(report_id)
        if not cache:
            raise ValueError(f"Report {report_id} not found")

        changes_preview = {}

        for section_id, version in section_changes.items():
            # Get original
            original = cache["generated_report"].get(section_id, {})

            # Get refined version
            version_data = SectionVersioning.get_version(
                report_id, section_id, version
            )

            if version_data:
                changes_preview[section_id] = {
                    "section_title": cache["sections_metadata"]
                        .get(section_id, {})
                        .get("title", section_id),
                    "version": version,
                    "original_score": cache["sections_metadata"]
                        .get(section_id, {})
                        .get("score", 0),
                    "new_score": version_data.get("score", 0),
                    "changes_summary": version_data.get("changes_summary", ""),
                    "refinement_instruction": version_data.get(
                        "refinement_instruction", ""
                    )
                }

        return changes_preview

    @staticmethod
    def apply_section_change(report_id: str, section_id: str, version: int):
        """
        Apply a specific section version (set as active).
        This doesn't generate DOCX yet, just marks the version.
        """
        SectionVersioning.set_active_version(report_id, section_id, version)
        print(f"✓ Applied {section_id} version {version}")

    @staticmethod
    def revert_section(report_id: str, section_id: str):
        """
        Revert section to version 1 (original).
        """
        SectionVersioning.set_active_version(report_id, section_id, 1)
        print(f"✓ Reverted {section_id} to original")

    @staticmethod
    def get_pending_changes(report_id: str) -> Dict:
        """
        Get summary of sections with pending changes (active version > 1).
        """
        active_versions = SectionVersioning.get_all_active_versions(report_id)
        cache = ReportCache.load_report_context(report_id)

        pending = {}
        for section_id, version_data in active_versions.items():
            if version_data["version"] > 1:  # Changed from original
                pending[section_id] = {
                    "section_title": cache["sections_metadata"]
                        .get(section_id, {})
                        .get("title", section_id),
                    "active_version": version_data["version"],
                    "score": version_data.get("score", 0)
                }

        return pending