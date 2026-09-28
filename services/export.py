#!/usr/bin/env python3
"""
Enhanced DOCX export with professional design and chart embedding
"""
import os, re, json
from datetime import datetime
from colorama import Fore, Style
from core.config import REPORT_OUTPUT_DIR
from core.logger import setup_logger

logger = setup_logger(__name__)


def _safe_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return re.sub(r'\s+', "_", name.strip())[:60]



def generate_docx_report(company, rapport, sector_stats, positioning):
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        print(f"  {Fore.YELLOW}[DOCX] pip install python-docx{Style.RESET_ALL}")
        return None

    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_filename(company.get("denomination", "entreprise"))
    out_path  = os.path.join(REPORT_OUTPUT_DIR, f"rapport_{safe_name}_{ts}.docx")

    doc = Document()

    # ══════════════════════════════════════════════════════════════════════════
    # STYLING HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def add_colored_heading(text, level=1, color_rgb=(30, 58, 138)):  # Navy
        """Add a colored heading"""
        h = doc.add_heading(text, level=level)
        for run in h.runs:
            run.font.color.rgb = RGBColor(*color_rgb)
            run.font.name = 'Arial'
        return h

    def add_info_box(text, bg_color=(219, 234, 254), border_color=(59, 130, 246)):  # Blue
        """Add an info box with colored background"""
        table = doc.add_table(rows=1, cols=1)
        table.style = 'Table Grid'
        cell = table.rows[0].cells[0]

        # Set background color
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:fill'), '%02x%02x%02x' % bg_color)
        cell._element.get_or_add_tcPr().append(shading_elm)

        # Add text
        p = cell.paragraphs[0]
        run = p.add_run(f"ℹ  {text}")
        run.font.size = Pt(10)
        run.font.name = 'Arial'

        return table

    def add_chart_if_exists(chart_path, caption=""):
        """Embed chart if file exists"""
        if chart_path and os.path.exists(chart_path):
            try:
                doc.add_picture(chart_path, width=Inches(6))
                if caption:
                    p = doc.add_paragraph(caption)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in p.runs:
                        run.font.italic = True
                        run.font.size = Pt(9)
                        run.font.color.rgb = RGBColor(75, 85, 99)  # Gray
                doc.add_paragraph()  # Spacing
                return True
            except Exception as e:
                logger.warning(f"Could not embed chart {chart_path}: {e}")
        return False

    def add_verdict_banner(verdict_text, risk_level):
        """Add a colored verdict banner"""
        # Color mapping
        colors = {
            "Favorable": ((22, 163, 74), (220, 252, 231)),      # Green
            "Acceptable": ((20, 184, 166), (204, 251, 241)),    # Teal
            "Sous surveillance": ((245, 158, 11), (254, 243, 199)),  # Amber
            "Défavorable": ((220, 38, 38), (254, 226, 226)),    # Red
            "Réservé": ((75, 85, 99), (243, 244, 246)),         # Gray
        }

        text_color, bg_color = colors.get(verdict_text, colors["Réservé"])

        table = doc.add_table(rows=1, cols=1)
        table.style = 'Table Grid'
        cell = table.rows[0].cells[0]

        # Background
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:fill'), '%02x%02x%02x' % bg_color)
        cell._element.get_or_add_tcPr().append(shading_elm)

        # Text
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        p.add_run("VERDICT DE CRÉDIT\n").font.size = Pt(10)
        run = p.add_run(verdict_text.upper())
        run.font.size = Pt(24)
        run.font.bold = True
        run.font.color.rgb = RGBColor(*text_color)

        p.add_run(f"\n{risk_level}").font.size = Pt(11)

        doc.add_paragraph()  # Spacing

    def add_market_structure_banner(monopoly_data):
        """Add colored market structure banner"""
        structure = monopoly_data.get('structure', 'Non déterminée')
        confidence = monopoly_data.get('confidence', 'Faible')

        # Scores
        mono_score = monopoly_data.get('monopoly_score', 0)
        oligo_score = monopoly_data.get('oligopoly_score', 0)
        comp_score = monopoly_data.get('competition_score', 0)

        # Detected signals
        signals = []
        if structure == "Monopole":
            signals = monopoly_data.get('monopoly_signals_found', [])
        elif structure == "Oligopole":
            signals = monopoly_data.get('oligopoly_signals_found', [])
        else:
            signals = monopoly_data.get('competition_signals_found', [])

        # Color mapping
        colors = {
            "Monopole": ((220, 38, 38), (254, 226, 226)),           # Red
            "Oligopole": ((245, 158, 11), (254, 243, 199)),         # Amber
            "Concurrence": ((22, 163, 74), (220, 252, 231)),        # Green
            "Non déterminée": ((75, 85, 99), (243, 244, 246)),      # Gray
        }

        text_color, bg_color = colors.get(structure, colors["Non déterminée"])

        # Create table
        table = doc.add_table(rows=1, cols=1)
        table.style = 'Table Grid'
        cell = table.rows[0].cells[0]

        # Background color
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:fill'), '%02x%02x%02x' % bg_color)
        cell._element.get_or_add_tcPr().append(shading_elm)

        # Content
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Header
        run = p.add_run("🏛️  STRUCTURE DU MARCHÉ\n\n")
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = RGBColor(75, 85, 99)

        # Structure type
        run = p.add_run(f"{structure.upper()}\n")
        run.font.size = Pt(20)
        run.font.bold = True
        run.font.color.rgb = RGBColor(*text_color)

        # Confidence
        run = p.add_run(f"Confiance: {confidence}\n\n")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(75, 85, 99)

        # Scores
        run = p.add_run(f"Scores: Monopole({mono_score}) | Oligopole({oligo_score}) | Concurrence({comp_score})\n")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(107, 114, 128)

        # Signals detected
        if signals:
            signals_text = ", ".join(signals[:5])
            run = p.add_run(f"\nSignaux détectés: {signals_text}")
            run.font.size = Pt(9)
            run.font.italic = True
            run.font.color.rgb = RGBColor(107, 114, 128)

        doc.add_paragraph()  # Spacing

    # ══════════════════════════════════════════════════════════════════════════
    # COVER PAGE
    # ══════════════════════════════════════════════════════════════════════════

    # Title
    title = doc.add_heading("RAPPORT D'ANALYSE CRÉDIT", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(30, 58, 138)  # Navy
        run.font.size = Pt(28)

    # Company name
    company_para = doc.add_paragraph()
    company_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = company_para.add_run(company.get("denomination", "").upper())
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    doc.add_paragraph()  # Space
    doc.add_paragraph()

    # Info table
    info_table = doc.add_table(rows=4, cols=2)
    info_table.style = 'Light Grid Accent 1'
    info_table.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info_data = [
        ("Secteur", company.get("label_secteur", "—")),
        ("Gouvernorat", company.get("gouvernorat", "—")),
        ("Date de génération", datetime.now().strftime("%d %B %Y")),
        ("Modèle IA", rapport.get("_meta", {}).get("model", "Phi-4")),
    ]

    for i, (label, value) in enumerate(info_data):
        info_table.rows[i].cells[0].text = label
        info_table.rows[i].cells[1].text = str(value)
        # Bold labels
        for run in info_table.rows[i].cells[0].paragraphs[0].runs:
            run.font.bold = True

    doc.add_paragraph()
    doc.add_paragraph()

    # Source
    source_para = doc.add_paragraph("Source : Annuaire des Entreprises Industrielles — APII Tunisie")
    source_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in source_para.runs:
        run.font.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(107, 114, 128)

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════════════
    # HELPER FUNCTION
    # ══════════════════════════════════════════════════════════════════════════

    def write_section(heading, content, chart_path=None, chart_caption=""):
        """Write a section with optional chart"""
        add_colored_heading(heading, level=1)

        # Add chart first if available
        if chart_path:
            add_chart_if_exists(chart_path, chart_caption)

        if content is None:
            doc.add_paragraph("— Données non disponibles —")
            return

        # Try to parse string as JSON
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                doc.add_paragraph(content[:500] if content else "— Données non disponibles —")
                return

        if isinstance(content, dict):
            content_normalized = {k.lower(): v for k, v in content.items()}

            for k, v in content_normalized.items():
                if k in ("analyst_note", "note_analyste"):
                    continue
                if v is None or str(v).strip() in ("", "—", "null", "None"):
                    continue

                if isinstance(v, list):
                    p = doc.add_paragraph()
                    run = p.add_run(f"{k.replace('_', ' ').title()}:")
                    run.bold = True
                    run.font.color.rgb = RGBColor(30, 58, 138)  # Navy

                    for item in v:
                        if isinstance(item, dict):
                            label = (item.get("risque") or item.get("Risque") or
                                    item.get("atout") or item.get("Atout") or
                                    item.get("raison") or item.get("Raison") or
                                    item.get("title") or item.get("Title") or "")
                            desc  = (item.get("description") or item.get("Description") or
                                     item.get("preuve") or item.get("Preuve") or "")
                            sev   = (item.get("severite") or item.get("Severite") or
                                     item.get("Sévérité") or item.get("sévérité") or "")

                            bp = doc.add_paragraph(style="List Bullet")

                            if sev:
                                sev_run = bp.add_run(f"[{sev}] ")
                                sev_run.bold = True
                                # Color by severity
                                if sev.lower() == "élevé":
                                    sev_run.font.color.rgb = RGBColor(220, 38, 38)  # Red
                                elif sev.lower() == "modéré":
                                    sev_run.font.color.rgb = RGBColor(245, 158, 11)  # Amber
                                else:
                                    sev_run.font.color.rgb = RGBColor(22, 163, 74)  # Green

                            bp.add_run(str(label)).bold = True
                            if desc:
                                bp.add_run(f" — {str(desc)[:200]}")
                        else:
                            doc.add_paragraph(f"  • {str(item)[:200]}", style="List Bullet")

                elif isinstance(v, dict):
                    p = doc.add_paragraph()
                    run = p.add_run(f"{k.replace('_', ' ').title()}: ")
                    run.bold = True
                    run.font.color.rgb = RGBColor(30, 58, 138)
                    p.add_run(" | ".join(f"{ek}: {ev}" for ek, ev in v.items() if ev)[:300])
                else:
                    p = doc.add_paragraph()
                    run = p.add_run(f"{k.replace('_', ' ').title()}: ")
                    run.bold = True
                    run.font.color.rgb = RGBColor(30, 58, 138)
                    p.add_run(str(v)[:300])

            # Analyst note at end
            note = content.get("note_analyste") or content.get("analyst_note")
            if note:
                doc.add_paragraph()
                p = doc.add_paragraph()
                run = p.add_run("💡 Note analyste: ")
                run.bold = True
                run.font.color.rgb = RGBColor(59, 130, 246)  # Blue
                p.add_run(str(note)[:500])

        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    label = (item.get("risque") or item.get("atout") or
                             item.get("title") or item.get("url") or "")
                    desc  = item.get("description") or item.get("answer") or ""
                    sev   = item.get("severite") or ""
                    p = doc.add_paragraph(style="List Bullet")
                    if sev:
                        p.add_run(f"[{sev}] ").bold = True
                    p.add_run(str(label)).bold = True
                    if desc:
                        p.add_run(f" — {str(desc)[:200]}")
                else:
                    doc.add_paragraph(f"• {str(item)[:200]}")
        else:
            doc.add_paragraph(str(content)[:500])

    # ══════════════════════════════════════════════════════════════════════════
    # GET CHART PATHS
    # ══════════════════════════════════════════════════════════════════════════

    viz_paths = rapport.get("_viz_paths", {})
    charts_dir = "database/output/charts"

    # Look for charts in the charts directory
    if not viz_paths and os.path.exists(charts_dir):
        # Try to find charts by pattern
        import glob
        chart_files = glob.glob(os.path.join(charts_dir, f"*{safe_name}*.png"))
        if chart_files:
            viz_paths = {
                'financial_summary': next((f for f in chart_files if 'financial' in f), None),
                'risk_severity': next((f for f in chart_files if 'risk' in f), None),
                'positioning_radar': next((f for f in chart_files if 'positioning' in f), None),
                'sector_comparison': next((f for f in chart_files if 'sector' in f), None),
            }

    # ══════════════════════════════════════════════════════════════════════════
    # SECTIONS WITH CHARTS
    # ══════════════════════════════════════════════════════════════════════════

    sections = [
        ("1. Profil Opérationnel", rapport.get("s1_profil_operationnel"), None, ""),
        ("2. Analyse Financière", rapport.get("s2_analyse_financiere"),
         viz_paths.get('financial_summary'), "Indicateurs financiers clés"),
        ("3. Positionnement Marché", rapport.get("s3_positionnement_marche"), None, ""),
        ("4. Facteurs de Risque", rapport.get("s4_facteurs_risque"),
         viz_paths.get('risk_severity'), "Répartition des risques par sévérité"),
        ("5. Facteurs Favorables", rapport.get("s5_facteurs_favorables"), None, ""),
        ("6. Gouvernance & Management", rapport.get("s6_gouvernance_management"), None, ""),
        ("7. Benchmark Sectoriel", rapport.get("s7_benchmark_sectoriel"),
         viz_paths.get('sector_comparison'), "Comparaison avec le secteur"),
        ("8. Benchmark National", rapport.get("s_benchmark_national"), None, ""),
        ("9. Benchmark Leaders", rapport.get("s_benchmark_leaders"), None, ""),
        ("10. Benchmark International", rapport.get("s_benchmark_international"), None, ""),
        ("11. Benchmark MENA", rapport.get("s_benchmark_mena"), None, ""),
        ("12. Benchmark Maghreb", rapport.get("s_benchmark_maghreb"), None, ""),
        ("13. Benchmark CA", rapport.get("s_benchmark_ca"), None, ""),
    ]

    for heading, content, chart_path, chart_caption in sections:
        write_section(heading, content, chart_path, chart_caption)
        doc.add_paragraph()
        # ══════════════════════════════════════════════════════════════════════════
# MARKET STRUCTURE BANNER (after Benchmark Sectoriel)
# ══════════════════════════════════════════════════════════════════════════

    monopoly_data = rapport.get("_meta", {}).get("monopoly_signals", {})
    if monopoly_data and monopoly_data.get('structure') != 'Non déterminée':
        add_colored_heading("Structure du Marché Détectée", level=1)
        add_market_structure_banner(monopoly_data)


    # ══════════════════════════════════════════════════════════════════════════
    # VERDICT SECTION (SPECIAL STYLING)
    # ══════════════════════════════════════════════════════════════════════════

    add_colored_heading("13. Synthèse & Verdict Crédit", level=1)

    s8 = rapport.get("s8_synthese_verdict", {})
    verdict = s8.get("verdict_credit", "Réservé")
    risk = s8.get("profil_risque", "Modéré")

    add_verdict_banner(verdict, risk)

    # Add positioning radar chart
    if viz_paths.get('positioning_radar'):
        add_chart_if_exists(viz_paths.get('positioning_radar'),
                           "Profil de positionnement crédit")

    # Write rest of verdict content
    if isinstance(s8, dict):
        for k, v in s8.items():
            if k in ('verdict_credit', 'profil_risque', 'note_analyste'):
                continue
            if v and str(v).strip() not in ("", "—", "null"):
                p = doc.add_paragraph()
                run = p.add_run(f"{k.replace('_', ' ').title()}: ")
                run.bold = True
                run.font.color.rgb = RGBColor(30, 58, 138)

                if isinstance(v, list):
                    doc.add_paragraph()
                    for item in v:
                        doc.add_paragraph(f"  • {str(item)[:200]}", style="List Bullet")
                else:
                    p.add_run(str(v)[:300])

        if s8.get("note_analyste"):
            doc.add_paragraph()
            add_info_box(f"Note analyste: {s8.get('note_analyste')}")

    doc.add_paragraph()

    # ══════════════════════════════════════════════════════════════════════════
    # SOURCES
    # ══════════════════════════════════════════════════════════════════════════

    add_colored_heading("Sources", level=1)
    sources = rapport.get("s_sources", [])
    if sources:
        for i, src in enumerate(sources[:20], 1):  # Limit to 20
            if isinstance(src, dict):
                p = doc.add_paragraph(f"{i}. {src.get('title', 'Source web')}", style="List Number")
                if src.get('url'):
                    run = p.add_run(f"\n   {src.get('url')}")
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor(107, 114, 128)
    else:
        doc.add_paragraph("Aucune source externe")

    doc.add_paragraph()

    # ══════════════════════════════════════════════════════════════════════════
    # SAVE
    # ══════════════════════════════════════════════════════════════════════════

    doc.save(out_path)
    print(f"  {Fore.GREEN}📄  Rapport professionnel → {out_path}{Style.RESET_ALL}")
    logger.info(f"Enhanced DOCX saved: {out_path}")
    return out_path