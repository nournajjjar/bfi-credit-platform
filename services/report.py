#!/usr/bin/env python3
import json
from datetime import datetime
from core.config import OPENAI_MODEL
from services.search import build_web_corpus
from services.questions import (
    get_general_questions,
    get_specific_questions,
    detect_monopoly_signals
)
from services.report_vis import generate_all_visualizations
from services.qa_answering import (
    answer_questions, compute_data_confidence,
    filter_answers_for_section, format_qa_for_prompt
)
from services.sections import (
    SECTION_PROMPTS,
    generate_s1_identite, generate_s5_benchmark_national,
    generate_s9_verdict, generate_s10_sources
)
from services.llm_sections import generate_llm_section
from prompt_export import PromptTracker
from services.pipeline_logger import PipelineLogger


def build_report(company, stats, pos, web_pages, search_results, pdf_financial=None):
    from services.pipeline_logger import PipelineLogger
    _plog = PipelineLogger(company.get("denomination", "unknown"))

    corpus        = build_web_corpus(web_pages)
    monopoly_signals = detect_monopoly_signals(corpus)

    pdf_financial = pdf_financial or {}
    report        = {}
    section_scores = {}
    tracker = PromptTracker(
        company.get("denomination", ""),
        company.get("label_secteur", "")
    )

    # Layer 1 - questions
    general_qs    = get_general_questions(
        company.get("source_table", ""),
        company.get("label_secteur", "")
    )
    specific_qs   = get_specific_questions(company, pos)
    all_questions = general_qs + specific_qs

    # Layer 2 - Q&A (runs ONCE)
    answers    = answer_questions(all_questions, corpus, pipeline_logger=_plog)
    confidence = compute_data_confidence(answers)
    tracker.record_qa_metadata(all_questions, answers, confidence)

    q_section_map = {q["id"]: q.get("section_cible", "") for q in all_questions}
    for a in answers:
        if not a.get("section_cible"):
            a["section_cible"] = q_section_map.get(a.get("id", ""), "")

    # Static sections
    report["s_identite"] = generate_s1_identite(company)

    # Shared context strings
    apii_summary = (
        f"Nom: {company.get('denomination', '')}\n"
        f"Secteur: {company.get('label_secteur', '')}\n"
        f"Gouvernorat: {company.get('gouvernorat', '')}\n"
        f"Activites: {company.get('activites', '')}\n"
        f"Produits: {company.get('produits', '')}\n"
        f"Capital: {company.get('capital', '')} DT | Emploi: {company.get('emploi', '')}\n"
        f"Regime: {company.get('regime', '')} | Creation: {company.get('entree_production', '')}"
    )
    pos_summary = "\n".join(f"{k}: {v}" for k, v in pos.items() if isinstance(v, str))
    sector_stats_summary = (
        f"Total entreprises: {stats.get('total_companies', 'N/A')}\n"
        f"Capital median: {stats.get('median_capital', 'N/A')} DT\n"
        f"Emploi median: {stats.get('median_emploi', 'N/A')}\n"
        f"% exportatrices: {stats.get('pct_export', 'N/A')}%\n"
        f"% presence web: {stats.get('pct_web_presence', 'N/A')}%\n"
        f"Age moyen: {stats.get('avg_age', 'N/A')} ans\n"
        f"Top gouvernorats: {', '.join(str(g) for g in stats.get('top_gouvernorats', []))}"
    )
    label_secteur = company.get("label_secteur", "")

    # Financial data from PDF for benchmark CA
    chiffre_affaires = (
        pdf_financial.get("cpc", {}).get("chiffre_affaires") or
        "Non disponible"
    )
    resultat_net = (
        pdf_financial.get("cpc", {}).get("resultat_net") or
        "Non disponible"
    )

    # _qa helper - embeddings first, web Q&A fallback
    def _qa(section_id):
        embedded_chunks = []
        try:
            from services.embeddings_service import retrieve_relevant_chunks
            embedded_chunks = retrieve_relevant_chunks(
                company.get("denomination", ""), section_id, top_k=5
            )
        except Exception:
            pass
        relevant = filter_answers_for_section(answers, section_id)
        qa_text  = format_qa_for_prompt(relevant if relevant else answers)
        if embedded_chunks:
            return (
                f"DONNEES OFFICIELLES :\n{chr(10).join(embedded_chunks)}"
                f"\n\n---\nDONNEES WEB :\n{qa_text}"
            )
        return qa_text

    # Benchmark national (LLM)
    out, score, _ = generate_llm_section(
        "s_benchmark_national", "Benchmark National",
        SECTION_PROMPTS["s_benchmark_national"],
        {"apii_data": apii_summary, "sector_stats": sector_stats_summary,
         "positioning": pos_summary, "qa": _qa("s7")},
        tracker=tracker, pipeline_logger=_plog
    )
    report["s_benchmark_national"]         = out
    section_scores["s_benchmark_national"] = score

    # Layer 3 - LLM sections (runs ONCE)
    existing_sections = [
        ("s1_profil_operationnel", "Profil Operationnel", {
            "apii_data": apii_summary,
            "qa":        _qa("s1"),
        }),
        ("s2_analyse_financiere", "Analyse Financiere", {
            "apii_data":        apii_summary,
            "pdf_bilan_actif":  json.dumps(pdf_financial.get("bilan_actif",  {}), ensure_ascii=False),
            "pdf_bilan_passif": json.dumps(pdf_financial.get("bilan_passif", {}), ensure_ascii=False),
            "pdf_cpc":          json.dumps(pdf_financial.get("cpc",          {}), ensure_ascii=False),
            "pdf_tft":          json.dumps(pdf_financial.get("tft",          {}), ensure_ascii=False),
            "qa":               _qa("s2"),
        }),
        ("s3_positionnement_marche", "Positionnement Marche", {
            "apii_data": apii_summary,
            "qa":        _qa("s3"),
        }),
        ("s4_facteurs_risque", "Facteurs de Risque", {
            "apii_data":   apii_summary,
            "positioning": pos_summary,
            "qa":          _qa("s4"),
        }),
        ("s5_facteurs_favorables", "Facteurs Favorables", {
            "apii_data":   apii_summary,
            "positioning": pos_summary,
            "qa":          _qa("s5"),
        }),
        ("s6_gouvernance_management", "Gouvernance & Management", {
            "apii_data": apii_summary,
            "qa":        _qa("s6"),
        }),
        ("s7_benchmark_sectoriel", "Benchmark Sectoriel", {
            "sector_stats": sector_stats_summary,
            "positioning":  pos_summary,
            "qa":           _qa("s7"),
        }),
    ]

    for sid, title, ctx in existing_sections:
        out, score, _ = generate_llm_section(
            sid, title, SECTION_PROMPTS[sid], ctx, tracker=tracker
        )
        report[sid]         = out
        section_scores[sid] = score

    # NEW benchmark sections
    monopoly_summary = (
        f"Structure detectee: {monopoly_signals.get('structure', 'Non determinee')}\n"
        f"Score monopole: {monopoly_signals.get('monopoly_score', 0)}\n"
        f"Score concurrence: {monopoly_signals.get('competition_score', 0)}\n"
        f"Signaux monopole: {', '.join(monopoly_signals.get('monopoly_signals_found', []))}\n"
        f"Signaux concurrence: {', '.join(monopoly_signals.get('competition_signals_found', []))}"
    )

    # 1. Benchmark Leaders
    out, score, _ = generate_llm_section(
        "s_benchmark_leaders",
        "Benchmark Secteur & Leaders",
        SECTION_PROMPTS["s_benchmark_leaders"],
        {
            "sector_stats": sector_stats_summary,
            "apii_data":    apii_summary,
            "qa":           _qa("benchmark_leaders"),
        },
        tracker=tracker,
    )
    if isinstance(out, dict):
        out["nlp_monopoly_detection"] = monopoly_signals
    report["s_benchmark_leaders"] = out
    section_scores["s_benchmark_leaders"] = score

    # 2. Benchmark International
    out, score, _ = generate_llm_section(
        "s_benchmark_international",
        "Benchmark International",
        SECTION_PROMPTS["s_benchmark_international"],
        {
            "apii_data":     apii_summary,
            "label_secteur": label_secteur,
            "qa":            _qa("benchmark_international"),
        },
        tracker=tracker,
    )
    report["s_benchmark_international"] = out
    section_scores["s_benchmark_international"] = score

    # 3. Benchmark MENA
    out, score, _ = generate_llm_section(
        "s_benchmark_mena",
        "Benchmark MENA",
        SECTION_PROMPTS["s_benchmark_mena"],
        {
            "apii_data":     apii_summary,
            "label_secteur": label_secteur,
            "qa":            _qa("benchmark_mena"),
        },
        tracker=tracker,
    )
    report["s_benchmark_mena"] = out
    section_scores["s_benchmark_mena"] = score

    # 4. Benchmark Maghreb
    out, score, _ = generate_llm_section(
        "s_benchmark_maghreb",
        "Benchmark Maghreb",
        SECTION_PROMPTS["s_benchmark_maghreb"],
        {
            "apii_data":     apii_summary,
            "label_secteur": label_secteur,
            "qa":            _qa("benchmark_maghreb"),
        },
        tracker=tracker,
    )
    report["s_benchmark_maghreb"] = out
    section_scores["s_benchmark_maghreb"] = score

    # 5. Benchmark Chiffre d'Affaires
    out, score, _ = generate_llm_section(
        "s_benchmark_ca",
        "Benchmark par Chiffre d'Affaires",
        SECTION_PROMPTS["s_benchmark_ca"],
        {
            "apii_data":        apii_summary,
            "chiffre_affaires": chiffre_affaires,
            "resultat_net":     resultat_net,
            "sector_stats":     sector_stats_summary,
            "qa":               _qa("benchmark_ca"),
        },
        tracker=tracker,
    )
    report["s_benchmark_ca"] = out
    section_scores["s_benchmark_ca"] = score

    # s8 synthese - needs all sections done first
    risks_summary     = json.dumps(report.get("s4_facteurs_risque",     {}), ensure_ascii=False)
    strengths_summary = json.dumps(report.get("s5_facteurs_favorables", {}), ensure_ascii=False)
    financial_summary = json.dumps(report.get("s2_analyse_financiere",  {}), ensure_ascii=False)

    s8_out, s8_score, _ = generate_llm_section(
        "s8_synthese_verdict",
        "Synthese & Verdict Credit",
        SECTION_PROMPTS["s8_synthese_verdict"],
        {
            "apii_data":         apii_summary,
            "financial_summary": financial_summary,
            "risks_summary":     risks_summary,
            "strengths_summary": strengths_summary,
            "qa":                _qa("s8"),
        },
        tracker=tracker,
    )
    report["s8_synthese_verdict"] = s8_out
    section_scores["s8"]          = s8_score

    # Generate visualizations
    viz_paths = generate_all_visualizations(
        report, company, stats, pos,
        output_dir="database/output/charts"
    )
    report["_viz_paths"] = viz_paths

    # Sources
    report["s_sources"] = generate_s10_sources(web_pages)

    # Metadata
    report["_meta"] = {
        "generated_at":       datetime.now().isoformat(),
        "model":              OPENAI_MODEL,
        "data_confidence":    confidence,
        "section_scores":     section_scores,
        "total_questions":    len(all_questions),
        "questions_answered": len([a for a in answers if a.get("answer") and a.get("answer") != "Information non disponible dans les sources"]),
        "monopoly_signals":   monopoly_signals,
    }

    return report, answers, tracker