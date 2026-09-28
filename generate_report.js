#!/usr/bin/env node
/**
 * generate_report.js - COMPLETE VERSION WITH ALL BENCHMARKS
 * Corporate Credit Report Generator - DOCX Export
 * Usage: node generate_report.js <input.json> <output.docx>
 */

const fs = require('fs');
const {
  Document, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, HeadingLevel
} = require('docx');

// ============================================================================
// COLOR PALETTE
// ============================================================================
const C = {
  white:   "FFFFFF",
  black:   "000000",
  gray50:  "F9FAFB",
  gray100: "F3F4F6",
  gray200: "E5E7EB",
  gray600: "4B5563",
  navy:    "1E3A8A",
  blue:    "3B82F6",
  teal:    "14B8A6",
  amber:   "F59E0B",
  red:     "DC2626",
  green:   "16A34A",
  purple:  "9333EA",
  orange:  "F97316",
};

const VERDICT_COLOR = {
  "Favorable":         C.green,
  "Acceptable":        C.teal,
  "Sous surveillance": C.amber,
  "Défavorable":       C.red,
  "Réservé":           C.gray600,
};

const SEVERITY_COLOR = {
  "Élevé":  { bg: "FEE2E2", text: C.red,    border: C.red },
  "Modéré": { bg: "FEF3C7", text: "92400E", border: C.amber },
  "Faible": { bg: "DCFCE7", text: "166534", border: C.green },
};

const SCORE_COLOR = {
  1: C.red,
  2: C.amber,
  3: "F59E0B",
  4: C.teal,
  5: C.green,
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function safe(val, fallback = "—") {
  if (val === null || val === undefined || val === "" || val === "null" ||
      val === "Non disponible" || val === "Non renseigné") return fallback;
  return String(val);
}

function fmtN(n) {
  if (n === null || n === undefined || n === "" || n === "null" || n === "Non disponible") return "—";
  const num = Number(n);
  if (isNaN(num)) return "—";
  return num.toLocaleString('fr-FR');
}

function sp(size = 12) {
  return new Paragraph({ spacing: { after: size * 20 } });
}

function mkCell(text, opts = {}) {
  const { fill, color, bold, size = 18, width = 2000, center, italic, borderColor } = opts;
  const borders = borderColor ? {
    top:    { style: BorderStyle.SINGLE, size: 1, color: borderColor },
    bottom: { style: BorderStyle.SINGLE, size: 1, color: borderColor },
    left:   { style: BorderStyle.SINGLE, size: 1, color: borderColor },
    right:  { style: BorderStyle.SINGLE, size: 1, color: borderColor },
  } : undefined;
  return new TableCell({
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    width: { size: width, type: WidthType.DXA },
    borders,
    margins: { top: 100, bottom: 100, left: 120, right: 120 },
    children: [new Paragraph({
      alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text || "—"), font: "Arial", size: size * 2,
        bold, italics: italic, color: color || C.black,
      })]
    })]
  });
}

function hCell(text, width = 2000) {
  return mkCell(text, { fill: C.navy, color: C.white, bold: true, size: 18, width, center: true });
}

function allB(color) {
  return {
    top:    { style: BorderStyle.SINGLE, size: 3, color },
    bottom: { style: BorderStyle.SINGLE, size: 3, color },
    left:   { style: BorderStyle.SINGLE, size: 3, color },
    right:  { style: BorderStyle.SINGLE, size: 3, color },
  };
}

function sectionH(title, subtitle = "") {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 480, after: subtitle ? 80 : 240 },
    children: [
      new TextRun({ text: title, font: "Arial", size: 32, bold: true, color: C.navy }),
      ...(subtitle ? [
        new TextRun({ text: "  ", font: "Arial", size: 20 }),
        new TextRun({ text: subtitle, font: "Arial", size: 20, color: C.gray600, italics: true })
      ] : [])
    ]
  });
}

function subH(text) {
  return new Paragraph({
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: C.navy })]
  });
}

function bodyP(text, opts = {}) {
  const { bold, italic, color } = opts;
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({
      text: String(text || ""), font: "Arial", size: 20,
      bold, italics: italic, color: color || C.black
    })]
  });
}

function twoCol(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [4680, 4680],
    rows: rows.map(([label, value]) => new TableRow({
      children: [
        mkCell(label,       { fill: C.gray50, size: 18, width: 4680 }),
        mkCell(safe(value), { bold: true, size: 19, width: 4680 })
      ]
    }))
  });
}

function estimatedBanner(text) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [new TableCell({
      shading: { fill: "FEF3C7", type: ShadingType.CLEAR },
      width: { size: 9360, type: WidthType.DXA },
      margins: { top: 120, bottom: 120, left: 160, right: 160 },
      children: [new Paragraph({ children: [
        new TextRun({ text: "⚠  ", font: "Arial", size: 20, color: C.amber }),
        new TextRun({ text, font: "Arial", size: 18, italics: true, color: "92400E" })
      ]})]
    })]})],
  });
}

function infoBanner(text, icon = "ℹ", bgColor = "DBEAFE") {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [new TableCell({
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      width: { size: 9360, type: WidthType.DXA },
      margins: { top: 120, bottom: 120, left: 160, right: 160 },
      children: [new Paragraph({ children: [
        new TextRun({ text: `${icon}  `, font: "Arial", size: 20, color: C.blue }),
        new TextRun({ text, font: "Arial", size: 18, color: C.navy })
      ]})]
    })]})],
  });
}

function renderJsonSection(obj) {
  if (!obj || typeof obj !== 'object') {
    return [bodyP("Aucune donnée disponible.", { italic: true, color: C.gray600 })];
  }
  const lines = [];
  for (const [key, val] of Object.entries(obj)) {
    if (val && val !== "—" && val !== "null" && val !== "Non disponible" && val !== "Non renseigné") {
      const label = key.replace(/_/g, " ");
      const displayVal = typeof val === 'object' ? JSON.stringify(val, null, 2) : val;
      lines.push(bodyP(`${label} : ${safe(displayVal)}`));
    }
  }
  return lines.length > 0 ? lines : [bodyP("Aucune donnée disponible.", { italic: true, color: C.gray600 })];
}

// ============================================================================
// MAIN GENERATION FUNCTION
// ============================================================================

async function generateReport(jsonPath, outputPath) {
  const raw  = fs.readFileSync(jsonPath, 'utf8');
  const data = JSON.parse(raw);

  const r          = data.rapport    || {};
  const company    = data.company    || {};
  const metaInfo   = data._meta      || data.metaInfo || {};
  const sectionScores = metaInfo.section_scores || data.sectionScores || {};
  const monopoly   = metaInfo.monopoly_detection || {};
  const now        = new Date().toLocaleString('fr-FR');

  // ── DATA EXTRACTION ──────────────────────────────────────────────────────
  const s_id          = r.s_identite               || {};
  const s1_profil     = r.s1_profil_operationnel   || {};
  const s2_fin        = r.s2_analyse_financiere    || {};
  const s3_marche     = r.s3_positionnement_marche || {};
  const s4_risques    = r.s4_facteurs_risque       || {};
  const s5_atouts     = r.s5_facteurs_favorables   || {};
  const s6_gouv       = r.s6_gouvernance_management|| {};
  const s7_bench      = r.s7_benchmark_sectoriel   || {};
  const s8_synthese   = r.s8_synthese_verdict      || {};
  const s_bench_nat   = r.s_benchmark_national     || {};
  const s_bench_leaders  = r.s_benchmark_leaders      || {};
  const s_bench_intl     = r.s_benchmark_international|| {};
  const s_bench_mena     = r.s_benchmark_mena         || {};
  const s_bench_maghreb  = r.s_benchmark_maghreb      || {};
  const s_bench_ca       = r.s_benchmark_ca           || {};
  const s_sources        = Array.isArray(r.s_sources) ? r.s_sources : [];

  const creditRisk = safe(s8_synthese.profil_risque || s8_synthese.verdict_credit, "—");

  // ── COVER PAGE ───────────────────────────────────────────────────────────
  const cover = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 2400, after: 400 },
      children: [
        new TextRun({ text: "Rapport Benchmark Crédit — ", font: "Arial", size: 32, color: C.gray600 }),
        new TextRun({ text: safe(company.denomination, "ENTREPRISE"), font: "Arial", size: 32, bold: true, color: C.navy })
      ]
    }),
    sp(40),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "RAPPORT DE BENCHMARK CRÉDIT", font: "Arial", size: 48, bold: true, color: C.navy })]
    }),
    sp(20),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: safe(company.denomination, "ENTREPRISE").toUpperCase(), font: "Arial", size: 40, bold: true, color: C.black })]
    }),
    sp(80),
    new Table({
      width: { size: 6000, type: WidthType.DXA },
      alignment: AlignmentType.CENTER,
      columnWidths: [3000, 3000],
      rows: [
        new TableRow({ children: [ mkCell("Secteur",     { fill: C.gray50, width: 3000 }), mkCell(safe(company.label_secteur), { bold: true, width: 3000 }) ] }),
        new TableRow({ children: [ mkCell("Gouvernorat", { fill: C.gray50, width: 3000 }), mkCell(safe(company.gouvernorat),   { bold: true, width: 3000 }) ] }),
        new TableRow({ children: [ mkCell("Généré le",   { fill: C.gray50, width: 3000 }), mkCell(now,                         { bold: true, width: 3000 }) ] }),
        new TableRow({ children: [ mkCell("Modèle IA",   { fill: C.gray50, width: 3000 }), mkCell(safe(metaInfo.model, "Phi-4"),{ bold: true, width: 3000 }) ] }),
      ]
    }),
    sp(40),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Source : Annuaire des Entreprises Industrielles — APII Tunisie", font: "Arial", size: 18, italics: true, color: C.gray600 })]
    })
  ];

  // ── SECTIONS ─────────────────────────────────────────────────────────────

  // SECTION 1: Identité
  const sec1 = [
    sectionH("1.  Identité et profil légal", "Données officielles APII"), sp(4),
    twoCol([
      ["Dénomination",      s_id.denomination      || company.denomination],
      ["Secteur",           s_id.secteur           || company.label_secteur],
      ["Gouvernorat",       s_id.gouvernorat       || company.gouvernorat],
      ["Régime",            s_id.regime            || company.regime],
      ["Année de création", s_id.annee_creation    || company.entree_production],
      ["Capital (DT)",      s_id.capital_dt        || company.capital],
      ["Effectif",          s_id.effectif          || company.emploi],
      ["Source officielle", s_id.source_officielle || "APII"],
    ]),
  ];

  // SECTION 2: Synthèse exécutive
  const sec2 = [
    sectionH("2.  Synthèse exécutive"), sp(4),
    ...(typeof s8_synthese === 'string' ? [bodyP(s8_synthese)] : renderJsonSection(s8_synthese)),
  ];

  // SECTION 3: Profil opérationnel
  const sec3 = [
    sectionH("3.  Profil opérationnel et commercial"), sp(4),
    ...renderJsonSection(s1_profil),
  ];

  // SECTION 4: Analyse financière
  const sec4 = [
    sectionH("4.  Analyse financière", "⚠ Données estimées — sources web"), sp(4),
    estimatedBanner("Les données financières sont estimées depuis des sources web. Elles ne constituent pas des données auditées."),
    sp(8),
    ...renderJsonSection(s2_fin),
  ];

  // SECTION 5: Benchmark national — LLM generated
  const sec5 = [
    sectionH("5.  Benchmark national", "Analyse sectorielle IA"), sp(4),
    ...renderJsonSection(s_bench_nat),
  ];

  // SECTION 6: Benchmark sectoriel
  const sec6 = [
    sectionH("6.  Benchmark sectoriel"), sp(4),
    ...renderJsonSection(s7_bench),
  ];

  // SECTION 7: Benchmark Leaders + Monopoly Detection
  const sec7 = [
    sectionH("7.  Benchmark secteur & leaders", "Analyse de la structure de marché"), sp(4),
    ...(monopoly.structure ? [
      infoBanner(
        `Structure de marché détectée : ${monopoly.structure} (Confiance : ${monopoly.confidence || 'Faible'})`,
        "🔍",
        monopoly.structure === "Monopole" ? "FEE2E2" : monopoly.structure === "Oligopole" ? "FEF3C7" : "DCFCE7"
      ),
      sp(8),
    ] : []),
    ...renderJsonSection(s_bench_leaders),
    ...(monopoly.monopoly_signals_found && monopoly.monopoly_signals_found.length > 0 ? [
      sp(8),
      subH("Signaux de monopole détectés"),
      bodyP(`Signaux monopole : ${monopoly.monopoly_signals_found.join(', ')}`,         { italic: true, color: C.gray600 }),
      bodyP(`Signaux concurrence : ${(monopoly.competition_signals_found || []).join(', ') || 'Aucun'}`, { italic: true, color: C.gray600 }),
    ] : []),
  ];

  // SECTION 8: Benchmark International
  const sec8 = [
    sectionH("8.  Benchmark international"), sp(4),
    ...renderJsonSection(s_bench_intl),
  ];

  // SECTION 9: Benchmark MENA
  const sec9 = [
    sectionH("9.  Benchmark MENA", "Moyen-Orient & Afrique du Nord"), sp(4),
    ...renderJsonSection(s_bench_mena),
  ];

  // SECTION 10: Benchmark Maghreb
  const sec10 = [
    sectionH("10. Benchmark Maghreb", "Tunisie, Maroc, Algérie"), sp(4),
    ...renderJsonSection(s_bench_maghreb),
  ];

  // SECTION 11: Benchmark Chiffre d'Affaires
  const sec11 = [
    sectionH("11. Benchmark par chiffre d'affaires"), sp(4),
    ...renderJsonSection(s_bench_ca),
  ];

  // SECTION 12: Analyse des risques
  const risksData = Array.isArray(s4_risques.risques) ? s4_risques.risques : [];
  const sec12 = [
    sectionH("12. Analyse des risques"), sp(4),
    ...(risksData.length > 0 ? [
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3600, 3960, 900, 900],
        rows: [
          new TableRow({ children: [ hCell("Risque", 3600), hCell("Description", 3960), hCell("Sévérité", 900), hCell("Source", 900) ] }),
          ...risksData.map(r => {
            const sev = r.severite || r.Severite || "Modéré";
            const sc  = SEVERITY_COLOR[sev] || SEVERITY_COLOR["Modéré"];
            return new TableRow({ children: [
              mkCell(r.risque      || r.Risque      || "—", { bold: true, size: 17, width: 3600, color: C.navy }),
              mkCell(r.description || r.Description || "—", { size: 17, width: 3960 }),
              mkCell(sev, { size: 17, width: 900, center: true, bold: true, fill: sc.bg, color: sc.text, borderColor: sc.border }),
              mkCell(r.source || "—", { size: 16, width: 900, center: true, color: C.gray600 }),
            ]});
          }),
        ],
      }),
      sp(8),
      bodyP(`Risque global : ${safe(s4_risques.risque_global, "—")}`, { bold: true }),
    ] : [bodyP("Aucun risque identifié.", { italic: true, color: C.gray600 })]),
    ...(s4_risques.note_analyste ? [ sp(4), bodyP(`Note analyste : ${s4_risques.note_analyste}`, { italic: true, color: C.gray600 }) ] : []),
  ];

  // SECTION 13: Facteurs favorables
  const atoutsData = Array.isArray(s5_atouts.atouts) ? s5_atouts.atouts : [];
  const sec13 = [
    sectionH("13. Facteurs favorables"), sp(4),
    ...(atoutsData.length > 0 ? [
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 3760, 2400],
        rows: [
          new TableRow({ children: [ hCell("Atout", 3200), hCell("Description", 3760), hCell("Preuve", 2400) ] }),
          ...atoutsData.map(a => new TableRow({ children: [
            mkCell(a.atout       || "—", { bold: true, size: 17, width: 3200, color: C.teal }),
            mkCell(a.description || "—", { size: 17, width: 3760 }),
            mkCell(a.preuve      || "—", { size: 16, width: 2400, color: C.gray600, italic: true }),
          ]})),
        ],
      }),
    ] : [bodyP("Aucun atout identifié.", { italic: true, color: C.gray600 })]),
    ...(s5_atouts.note_analyste ? [ sp(4), bodyP(`Note analyste : ${s5_atouts.note_analyste}`, { italic: true }) ] : []),
  ];

  // SECTION 14: Gouvernance
  const sec14 = [
    sectionH("14. Gouvernance & management"), sp(4),
    ...renderJsonSection(s6_gouv),
  ];

  // SECTION 15: Verdict crédit
  const verdictText = safe(s8_synthese.verdict_credit, "—");
  const riskText    = safe(s8_synthese.profil_risque, creditRisk);
  const vColor      = VERDICT_COLOR[verdictText] || VERDICT_COLOR[riskText] || C.navy;
  const raisons     = Array.isArray(s8_synthese.raisons_principales) ? s8_synthese.raisons_principales : [];
  const vigilance   = Array.isArray(s8_synthese.points_vigilance)    ? s8_synthese.points_vigilance    : [];

  const sec15 = [
    sectionH("15. Verdict de positionnement crédit"), sp(4),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [9360],
      rows: [new TableRow({ children: [new TableCell({
        borders: allB(vColor),
        shading: { fill: C.gray50, type: ShadingType.CLEAR },
        width: { size: 9360, type: WidthType.DXA },
        margins: { top: 160, bottom: 160, left: 200, right: 200 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
            children: [new TextRun({ text: "PROFIL DE RISQUE CRÉDIT", font: "Arial", size: 20, color: C.gray600 })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 },
            children: [new TextRun({ text: verdictText.toUpperCase(), font: "Arial", size: 44, bold: true, color: vColor })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
            children: [new TextRun({ text: riskText, font: "Arial", size: 20, italics: true, color: vColor })] }),
        ],
      })]})],
    }),
    sp(12),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [1560, 1560, 1560, 1560, 1560, 1560],
      rows: [
        new TableRow({ children: [
          mkCell("Solidité financière",       { fill: C.gray50, size: 16, width: 1560, center: true }),
          mkCell("Maturité & stabilité",      { fill: C.gray50, size: 16, width: 1560, center: true }),
          mkCell("Crédibilité marché",        { fill: C.gray50, size: 16, width: 1560, center: true }),
          mkCell("Exposition internationale", { fill: C.gray50, size: 16, width: 1560, center: true }),
          mkCell("Gouvernance",               { fill: C.gray50, size: 16, width: 1560, center: true }),
          mkCell("Risques",                   { fill: C.gray50, size: 16, width: 1560, center: true }),
        ]}),
        new TableRow({ children: [
          mkCell(safe(s8_synthese.solidite_financiere,       "—"), { bold: true, size: 18, width: 1560, center: true }),
          mkCell(safe(s8_synthese.maturite_stabilite,        "—"), { bold: true, size: 18, width: 1560, center: true }),
          mkCell(safe(s8_synthese.credibilite_marche,        "—"), { bold: true, size: 18, width: 1560, center: true }),
          mkCell(safe(s8_synthese.exposition_internationale, "—"), { bold: true, size: 18, width: 1560, center: true }),
          mkCell(safe(s8_synthese.gouvernance,               "—"), { bold: true, size: 18, width: 1560, center: true }),
          mkCell(
            `${risksData.filter(r => (r.severite||r.Severite) === "Élevé").length} risque(s) élevé(s)  │  ${risksData.filter(r => (r.severite||r.Severite) === "Modéré").length} risque(s) modéré(s)`,
            { size: 16, width: 1560, center: true }
          ),
        ]}),
      ],
    }),
    sp(12),
    ...(raisons.length > 0 ? [
      ...raisons.map(r => new Paragraph({ spacing: { before: 60, after: 60 }, children: [
        new TextRun({ text: "▸  ", font: "Arial", size: 20, bold: true, color: vColor }),
        new TextRun({ text: String(r), font: "Arial", size: 20, color: C.black }),
      ]})),
      sp(8),
    ] : []),
    ...(s8_synthese.recommandation ? [ bodyP(s8_synthese.recommandation), sp(8) ] : []),
    ...(vigilance.length > 0 ? vigilance.map(v => new Paragraph({ spacing: { before: 60, after: 60 }, children: [
      new TextRun({ text: "⚠  ", font: "Arial", size: 20, bold: true, color: C.amber }),
      new TextRun({ text: String(v), font: "Arial", size: 20, color: C.black }),
    ]})) : []),
  ];

  // SECTION 16: Sources et métadonnées
  const sec16 = [
    sectionH("16. Sources et métadonnées"), sp(4),
    subH("Qualité des données"),
    twoCol([
      ["Total questions posées",     String(metaInfo.total_questions || "—")],
      ["Questions avec réponse",     String(metaInfo.questions_answered || "—")],
      ["Niveau de confiance",        metaInfo.data_confidence?.level || "—"],
      ["% questions sans réponse",   ((metaInfo.data_confidence?.pct_low || 0).toFixed(1)) + "%"],
      ["Modèle IA",                  metaInfo.model || "Phi-4"],
      ["Généré le",                  metaInfo.generated_at || now],
    ]),
    ...(Object.keys(sectionScores).length > 0 ? [
      sp(12),
      subH("Scores d'évaluation par section"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [4680, 4680],
        rows: [
          new TableRow({ children: [ hCell("Section", 4680), hCell("Score /5", 4680) ] }),
          ...Object.entries(sectionScores).map(([sid, score]) => new TableRow({ children: [
            mkCell(sid.replace(/_/g, " ").toUpperCase(), { fill: C.gray50, size: 18, width: 4680 }),
            mkCell(String(score) + " / 5", {
              size: 18, width: 4680, bold: true, center: true,
              color: SCORE_COLOR[Math.round(score)] || C.black
            }),
          ]})),
        ],
      }),
    ] : []),
    ...(s_sources.length > 0 ? [
      sp(12),
      subH("Sources web"),
      ...s_sources.slice(0, 20).map(src => bodyP(`• ${src.title || src.url}`, { size: 16 }))
    ] : []),
  ];

  // ── DOCUMENT ASSEMBLY ────────────────────────────────────────────────────
  const doc = new Document({
    sections: [{
      properties: { page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      children: [
        ...cover,
        ...sec1,  sp(12),
        ...sec2,  sp(12),
        ...sec3,  sp(12),
        ...sec4,  sp(12),
        ...sec5,  sp(12),  // Benchmark national — LLM
        ...sec6,  sp(12),  // Benchmark sectoriel
        ...sec7,  sp(12),  // Benchmark leaders
        ...sec8,  sp(12),  // International
        ...sec9,  sp(12),  // MENA
        ...sec10, sp(12),  // Maghreb
        ...sec11, sp(12),  // CA
        ...sec12, sp(12),  // Risques
        ...sec13, sp(12),  // Atouts
        ...sec14, sp(12),  // Gouvernance
        ...sec15, sp(12),  // Verdict
        ...sec16,           // Sources
      ]
    }]
  });

  const Packer = require('docx').Packer;
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`✓ Report generated: ${outputPath}`);
}

// ============================================================================
// CLI EXECUTION
// ============================================================================
if (require.main === module) {
  const [,, jsonPath, outputPath] = process.argv;
  if (!jsonPath || !outputPath) {
    console.error('Usage: node generate_report.js <input.json> <output.docx>');
    process.exit(1);
  }
  generateReport(jsonPath, outputPath).catch(err => {
    console.error('Error:', err);
    process.exit(1);
  });
}

module.exports = { generateReport };