from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from core.config import APP_ENV, MODEL_NAME

router = APIRouter(tags=["Health"])


@router.get("/", summary="Index")
async def index():
    return {
        "service": "backend",
        "version": "1.0.0",
        "env": APP_ENV,
        "model": MODEL_NAME,
    }


@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok"}


@router.get("/ui", include_in_schema=False)
async def ui():
    return HTMLResponse(content=_UI_HTML)


# ─────────────────────────────────────────────────────────────────────────────
_UI_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deep Research — Rapport Crédit Corporate</title>
<style>
:root{--navy:#1A3A5C;--blue:#2563A8;--teal:#0F766E;--amber:#B45309;--green:#166534;--red:#991B1B;--gray50:#F8FAFC;--gray100:#F1F5F9;--gray200:#E2E8F0;--gray600:#475569;--white:#FFFFFF}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:var(--gray50);color:#1e293b;min-height:100vh}
header{background:var(--navy);color:#fff;padding:18px 32px;display:flex;align-items:center;gap:12px}
header h1{font-size:1.25rem;font-weight:700}
header p{font-size:.8rem;opacity:.65;margin-top:2px}
.container{max-width:900px;margin:0 auto;padding:28px 16px}
.card{background:#fff;border-radius:8px;border:1px solid var(--gray200);padding:22px;margin-bottom:18px}
.card-title{font-size:.95rem;font-weight:700;color:var(--navy);margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--navy);display:flex;align-items:center;gap:8px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.field{display:flex;flex-direction:column;gap:4px}
.field.full{grid-column:1/-1}
label{font-size:.72rem;font-weight:600;color:var(--gray600);text-transform:uppercase;letter-spacing:.04em}
input[type=text],select,textarea{padding:8px 10px;border:1px solid var(--gray200);border-radius:5px;font-size:.88rem;outline:none;transition:border-color .15s;background:#fff;width:100%}
input:focus,select:focus{border-color:var(--blue);box-shadow:0 0 0 2px rgba(37,99,168,.12)}
.file-pick{display:flex;align-items:center;gap:10px;border:1px solid var(--gray200);border-radius:6px;padding:9px 12px;cursor:pointer;background:var(--gray50);transition:border-color .15s}
.file-pick:hover{border-color:var(--blue);background:#EFF6FF}
.file-pick.has-file{border-color:var(--teal);background:#F0FDF4}
.fp-icon{font-size:1.2rem;flex-shrink:0}
.fp-lbl{font-size:.84rem;color:var(--gray600);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-pick.has-file .fp-lbl{color:var(--teal);font-weight:600}
.btn-submit{width:100%;padding:12px;background:var(--teal);color:#fff;border:none;border-radius:6px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:4px;transition:background .15s;letter-spacing:.01em}
.btn-submit:hover:not(:disabled){background:#0c6060}
.btn-submit:disabled{opacity:.55;cursor:not-allowed}
.progress-bar{height:8px;background:var(--gray200);border-radius:4px;overflow:hidden;margin:10px 0}
.progress-fill{height:100%;background:var(--teal);border-radius:4px;transition:width .4s ease}
.progress-msg{font-size:.84rem;color:var(--gray600)}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:700;text-transform:uppercase;margin-left:8px}
.badge.running{background:#FEF3C7;color:var(--amber)}
.badge.done{background:#DCFCE7;color:var(--green)}
.badge.failed{background:#FEE2E2;color:var(--red)}
.result-box{background:#F0FDF4;border:1px solid #86EFAC;border-radius:8px;padding:22px;text-align:center}
.result-box h3{color:var(--green);margin-bottom:6px;font-size:1.1rem}
.btn-dl{display:inline-block;padding:10px 26px;background:var(--navy);color:#fff;border-radius:6px;text-decoration:none;font-weight:700;margin-top:10px}
.btn-dl:hover{background:var(--blue)}
.error-box{background:#FEF2F2;border:1px solid #FCA5A5;border-radius:8px;padding:16px;color:var(--red);font-size:.88rem}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}}
</style>
</head>
<body>

<header>
  <div>
    <h1>🔍 Deep Research — Rapport Analyse Crédit Corporate</h1>
    <p>APII Tunisie &nbsp;·&nbsp; Benchmark sectoriel &nbsp;·&nbsp; Analyse financière &nbsp;·&nbsp; Tavily Web Research</p>
  </div>
</header>

<div class="container">

  <form id="form">

    <!-- Company info -->
    <div class="card">
      <div class="card-title">🏢 Informations de l'entreprise</div>
      <div class="form-grid">
        <div class="field full">
          <label>Dénomination *</label>
          <input type="text" id="company_name" placeholder="Ex : SOTUMAG" required>
        </div>
        <div class="field">
          <label>Gouvernorat</label>
          <input type="text" id="gouvernorat" placeholder="Ex : Tunis">
        </div>
        <div class="field">
          <label>Secteur (table DB)</label>
          <select id="source_table">
            <option value="">— Sélectionner —</option>
            <option value="secteur_ind_m_caniques">Industries mécaniques et métallurgiques</option>
            <option value="secteur_ind_textile">Industries textiles et habillement</option>
            <option value="secteur_mat_riaux_construction">Industries des matériaux de construction</option>
            <option value="secteur_ind_chimiques">Industries chimiques</option>
            <option value="secteur_agro_alimentaires">Industries agro-alimentaires</option>
            <option value="secteur_ind_cuir_chaussures">Industries du cuir et de la chaussure</option>
            <option value="secteur_ind_bois_li_ge">Industries du bois, du liège et ameublement</option>
            <option value="secteur_ind_lectriques">Industries électriques et électroniques</option>
            <option value="secteur_ind_diverses">Industries diverses</option>
          </select>
        </div>
        <div class="field">
          <label>Label secteur</label>
          <input type="text" id="label_secteur" placeholder="Auto-rempli depuis le secteur">
        </div>
        <div class="field">
          <label>Capital (DT)</label>
          <input type="text" id="capital" placeholder="Ex : 500 000">
        </div>
        <div class="field">
          <label>Effectif</label>
          <input type="text" id="emploi" placeholder="Ex : 120">
        </div>
        <div class="field">
          <label>Régime</label>
          <input type="text" id="regime" placeholder="Ex : Totalement exportatrice">
        </div>
        <div class="field">
          <label>Entrée en production</label>
          <input type="text" id="entree_production" placeholder="Ex : 2005">
        </div>
        <div class="field full">
          <label>Activités</label>
          <input type="text" id="activites" placeholder="Ex : Fabrication de conserves alimentaires…">
        </div>
        <div class="field full">
          <label>Produits</label>
          <input type="text" id="produits" placeholder="Ex : Conserves, huiles, épices…">
        </div>
        <div class="field full">
          <label>Site web</label>
          <input type="text" id="url" placeholder="Ex : https://www.entreprise.tn">
        </div>
      </div>
    </div>

    <!-- PDF upload -->
    <div class="card">
      <div class="card-title">
        📄 Documents CMF (PDF)
        <span style="font-weight:400;font-size:.78rem;color:#64748b">— max 50 MB total</span>
      </div>
      <div class="form-grid">
        <div class="field full">
          <label>PDF 1 — Bilan <span style="color:var(--red)">*</span></label>
          <div class="file-pick" id="pick1" onclick="document.getElementById('file1').click()">
            <span class="fp-icon">📄</span>
            <span id="lbl1" class="fp-lbl">Choisir un fichier PDF…</span>
            <input type="file" id="file1" accept=".pdf" style="display:none" onchange="setLabel('lbl1',this,'pick1')">
          </div>
        </div>
        <div class="field">
          <label>PDF 2 — CPC <span style="color:var(--gray600);font-weight:400">(optionnel)</span></label>
          <div class="file-pick" id="pick2" onclick="document.getElementById('file2').click()">
            <span class="fp-icon">📄</span>
            <span id="lbl2" class="fp-lbl">Choisir un fichier PDF…</span>
            <input type="file" id="file2" accept=".pdf" style="display:none" onchange="setLabel('lbl2',this,'pick2')">
          </div>
        </div>
        <div class="field">
          <label>PDF 3 — Annexes <span style="color:var(--gray600);font-weight:400">(optionnel)</span></label>
          <div class="file-pick" id="pick3" onclick="document.getElementById('file3').click()">
            <span class="fp-icon">📄</span>
            <span id="lbl3" class="fp-lbl">Choisir un fichier PDF…</span>
            <input type="file" id="file3" accept=".pdf" style="display:none" onchange="setLabel('lbl3',this,'pick3')">
          </div>
        </div>
      </div>
    </div>

    <button type="submit" class="btn-submit" id="submitBtn">⚡ Générer le rapport</button>
  </form>

  <!-- Progress -->
  <div class="card" id="progressCard" style="display:none;margin-top:18px">
    <div class="card-title">
      Traitement en cours
      <span class="badge running" id="statusBadge">En cours</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
    <p class="progress-msg" id="progressMsg">Démarrage…</p>
  </div>

  <!-- Result -->
  <div id="resultCard" style="display:none;margin-top:18px">
    <div class="result-box">
      <h3>✅ Rapport généré avec succès</h3>
      <p id="resultMeta" style="color:#475569;font-size:.84rem;margin-top:4px"></p>
      <a id="downloadBtn" href="#" class="btn-dl">⬇ Télécharger le rapport DOCX</a>
    </div>
  </div>

  <!-- Error -->
  <div class="error-box" id="errorCard" style="display:none;margin-top:18px"></div>

</div>

<script>
const SECTOR_LABELS = {
  'secteur_ind_m_caniques':         'Industries mécaniques et métallurgiques',
  'secteur_ind_textile':            'Industries textiles et habillement',
  'secteur_mat_riaux_construction': 'Industries des matériaux de construction',
  'secteur_ind_chimiques':          'Industries chimiques',
  'secteur_agro_alimentaires':      'Industries agro-alimentaires',
  'secteur_ind_cuir_chaussures':    'Industries du cuir et de la chaussure',
  'secteur_ind_bois_li_ge':         'Industries du bois, du liège et ameublement',
  'secteur_ind_lectriques':         'Industries électriques et électroniques',
  'secteur_ind_diverses':           'Industries diverses',
};

// ── File label helper ─────────────────────────────────────────────────────────
function setLabel(lblId, input, pickId) {
  const lbl  = document.getElementById(lblId);
  const pick = document.getElementById(pickId);
  if (input.files && input.files[0]) {
    lbl.textContent = input.files[0].name;
    pick.classList.add('has-file');
  } else {
    lbl.textContent = 'Choisir un fichier PDF…';
    pick.classList.remove('has-file');
  }
}

// ── Sector → label sync ───────────────────────────────────────────────────────
document.getElementById('source_table').addEventListener('change', function() {
  document.getElementById('label_secteur').value = SECTOR_LABELS[this.value] || '';
});

// ── Helpers ───────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function setLoading(on) {
  $('submitBtn').disabled    = on;
  $('submitBtn').textContent = on ? '⏳ Traitement en cours…' : '⚡ Générer le rapport';
}

function showError(msg) {
  $('progressCard').style.display = 'none';
  $('resultCard').style.display   = 'none';
  const el = $('errorCard');
  el.style.display = 'block';
  el.innerHTML = `<strong>❌ Erreur</strong><br>${msg}`;
}

function startPolling(jobId) {
  $('progressCard').style.display = 'block';
  $('resultCard').style.display   = 'none';
  $('errorCard').style.display    = 'none';
  const iv = setInterval(async () => {
    try {
      const job = await fetch(`/api/jobs/${jobId}`).then(r => r.json());
      const pct = job.progress ?? 0;
      $('progressFill').style.width    = pct + '%';
      $('progressMsg').textContent     = `${pct}% — ${job.message || ''}`;
      if (job.status === 'completed') {
        clearInterval(iv);
        $('progressCard').style.display = 'none';
        $('resultCard').style.display   = 'block';
        $('resultMeta').textContent     = (job.result?.pdf_count > 0)
          ? `${job.result.pdf_count} PDF(s) analysé(s)`
          : 'Analyse web uniquement';
        $('downloadBtn').href = `/api/jobs/${jobId}/download`;
        setLoading(false);
      } else if (job.status === 'failed') {
        clearInterval(iv);
        showError(job.error || 'Pipeline échoué.');
        setLoading(false);
      }
    } catch(_) {}
  }, 2000);
}

// ── Submit ────────────────────────────────────────────────────────────────────
document.getElementById('form').addEventListener('submit', async e => {
  e.preventDefault();
  const company = $('company_name').value.trim();
  if (!company) { alert('La dénomination est obligatoire.'); return; }

  const qs = new URLSearchParams({
    company_name:      company,
    gouvernorat:       $('gouvernorat').value,
    source_table:      $('source_table').value,
    label_secteur:     $('label_secteur').value,
    capital:           $('capital').value,
    emploi:            $('emploi').value,
    regime:            $('regime').value,
    entree_production: $('entree_production').value,
    activites:         $('activites').value,
    produits:          $('produits').value,
    url:               $('url').value,
  });

  setLoading(true);
  $('errorCard').style.display  = 'none';
  $('resultCard').style.display = 'none';

  try {
    const f1 = document.getElementById('file1').files[0];
    const f2 = document.getElementById('file2').files[0];
    const f3 = document.getElementById('file3').files[0];

    if (!f1) { showError('Le PDF 1 (Bilan) est obligatoire.'); setLoading(false); return; }

    // Use /api/pdf/extract-and-report with named file fields + query params
    const fd = new FormData();
    fd.append('file1', f1);
    if (f2) fd.append('file2', f2);
    if (f3) fd.append('file3', f3);

    const res  = await fetch(`/api/pdf/extract-and-report?${qs}`, { method:'POST', body:fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    startPolling(data.job_id);
  } catch(err) { showError(err.message); setLoading(false); }
});
</script>
</body>
</html>"""
