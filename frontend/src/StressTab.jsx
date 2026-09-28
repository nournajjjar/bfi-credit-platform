import { useState, useEffect } from 'react'
import { api } from './api'

// ══════════════════════════════════════════════════════════════════
// STRESS TEST TAB
// ══════════════════════════════════════════════════════════════════
const FIELDS = [
  ['revenue',             "Chiffre d'affaires"],
  ['raw_materials',       "Achats consommés (matières)"],
  ['amortization',        "Dotations amortissements"],
  ['interest',            "Intérêts (bruts)"],
  ['equity',              "Capitaux propres"],
  ['debt',                "Dettes financières"],
  ['current_assets',      "Actifs courants"],
  ['current_liabilities', "Passifs courants"],
]

const statusChip = s => ({ ok:'chip-green', warning:'chip-amber', break:'chip-red' }[s] || 'chip-gray')
const fmtNum = n => (n == null ? '—' : Number(n).toLocaleString('fr-FR'))

export default function StressTab() {
  const [reports,   setReports]   = useState([])
  const [reportId,  setReportId]  = useState('')
  const [form,      setForm]      = useState(Object.fromEntries(FIELDS.map(([k]) => [k, ''])))
  const [isExporter,setIsExporter]= useState(false)
  const [custom,    setCustom]    = useState({ revenue_pct:'', cost_pct:'', interest_pct:'', fx_pct:'', receivables_delay_pct:'' })
  const [useCustom, setUseCustom] = useState(false)
  const [result,    setResult]    = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [recs,      setRecs]      = useState(null)
  const [recLoading,setRecLoading]= useState(false)
  const [alert,     setAlert]     = useState(null)

  function showAlert(msg, type='blue') { setAlert({ msg, type }); setTimeout(() => setAlert(null), 6000) }

  useEffect(() => { api.getReports().then(setReports).catch(() => {}) }, [])

  async function prefill() {
    if (!reportId) { showAlert('Sélectionnez un rapport.', 'amber'); return }
    try {
      const d = await api.stressPrefill(reportId)
      const p = d.prefill || {}
      setForm(f => {
        const next = { ...f }
        FIELDS.forEach(([k]) => { if (p[k] != null) next[k] = String(p[k]) })
        return next
      })
      setIsExporter(!!p.is_exporter)
      showAlert(`${d.fields_found}/${d.fields_total} champs trouvés${d.regime ? ` · régime: ${d.regime}` : ''}. Complétez si besoin.`,
        d.fields_found >= 6 ? 'green' : 'amber')
    } catch (e) {
      showAlert('Erreur pré-remplissage: ' + (e.response?.data?.detail || e.message), 'red')
    }
  }

  async function run() {
    const REQUIRED = ['revenue']
    const missing = REQUIRED.filter(k => !form[k] || form[k] === '')
    if (missing.length) { showAlert('Champs requis manquants: ' + missing.join(', '), 'amber'); return }

    for (const [k] of FIELDS) {
      if (!form[k] || form[k] === '') setForm(f => ({ ...f, [k]: '0' }))
    }
    const inputs = { is_exporter: isExporter }
    for (const [k] of FIELDS) inputs[k] = parseFloat(String(form[k]).replace(/\s/g, '').replace(',', '.'))

    let custom_shocks = null
    if (useCustom) {
      custom_shocks = {}
      Object.entries(custom).forEach(([k, v]) => { custom_shocks[k] = v === '' ? 0 : parseFloat(v) })
    }

    setLoading(true); setResult(null); setRecs(null)
    try {
      const d = await api.stressRun({ inputs, custom_shocks, report_id: reportId || null })
      setResult(d.result)
      if (reportId) showAlert('✅ Stress test sauvegardé pour ce rapport.', 'green')
    } catch (e) {
      showAlert('Erreur: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setLoading(false) }
  }

  function buildInputs() {
    const inputs = { is_exporter: isExporter }
    for (const [k] of FIELDS) inputs[k] = parseFloat(String(form[k]).replace(/\s/g, '').replace(',', '.'))
    let custom_shocks = null
    if (useCustom) {
      custom_shocks = {}
      Object.entries(custom).forEach(([k, v]) => { custom_shocks[k] = v === '' ? 0 : parseFloat(v) })
    }
    return { inputs, custom_shocks, report_id: reportId || null }
  }

  async function recommend() {
    setRecLoading(true); setRecs(null)
    try {
      const d = await api.stressRecommend(buildInputs())
      setRecs(d.recommendations)
      if (!d.recommendations?.has_recommendations) {
        showAlert('Aucune vulnérabilité critique — pas de recommandation nécessaire.', 'green')
      }
    } catch (e) {
      showAlert('Erreur recommandations: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setRecLoading(false) }
  }

  const hasBadVerdict = result && (
    result.base_verdict.status !== 'ok' ||
    result.scenarios.some(s => s.verdict.status !== 'ok')
  )

  // Filter out EBIT-related reverse stress metrics
  const REVERSE_EXCLUDED = ['cost_rise_net', 'revenue_drop_ebit']

  return (
    <div className="two-col">
      {/* LEFT: inputs */}
      <div className="left-col" style={{ overflowY:'auto', maxHeight:'calc(100vh - 120px)' }}>
        <div className="section-label">Source des données</div>
        <div style={{ padding:'0 16px 12px' }}>
          <div className="field">
            <label>Pré-remplir depuis un rapport</label>
            <div style={{ display:'flex', gap:8 }}>
              <select value={reportId} onChange={e => setReportId(e.target.value)} style={{ flex:1 }}>
                <option value="">— Choisir —</option>
                {reports.map(r => <option key={r.report_id} value={r.report_id}>{r.company_name}</option>)}
              </select>
              <button className="btn btn-sm" onClick={prefill}>↓ Charger</button>
            </div>
          </div>
        </div>

        <div className="section-label">Chiffres financiers (DT)</div>
        <div style={{ padding:'0 16px 16px' }}>
          {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}
          {FIELDS.map(([k, label]) => (
            <div className="field" key={k}>
              <label>{label}</label>
              <input value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                placeholder="0" inputMode="decimal" />
            </div>
          ))}
          <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:12, color:'#64748b', marginTop:4 }}>
            <input type="checkbox" checked={isExporter} onChange={e => setIsExporter(e.target.checked)} />
            Entreprise totalement exportatrice
          </label>
        </div>

        <div className="section-label">Scénario personnalisé (optionnel)</div>
        <div style={{ padding:'0 16px 16px' }}>
          <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:12, color:'#64748b', marginBottom:8 }}>
            <input type="checkbox" checked={useCustom} onChange={e => setUseCustom(e.target.checked)} />
            Ajouter un scénario sur mesure
          </label>
          {useCustom && (
            <>
              {[
                ['revenue_pct', 'Variation CA (%)'],
                ['cost_pct', 'Hausse coûts intrants (%)'],
                ['interest_pct', 'Hausse intérêts (%)'],
                ['fx_pct', 'Dévaluation dinar (%)'],
                ['receivables_delay_pct', 'Gel actifs courants (%)'],
              ].map(([k, label]) => (
                <div className="field" key={k}>
                  <label>{label}</label>
                  <input value={custom[k]} onChange={e => setCustom(c => ({ ...c, [k]: e.target.value }))}
                    placeholder="0" inputMode="decimal" />
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* RIGHT: results */}
      <div className="right-col" style={{ overflowY:'auto', maxHeight:'calc(100vh - 120px)' }}>
        <button className="btn btn-primary btn-full" style={{ marginBottom:16, padding:12, fontSize:14 }}
          onClick={run} disabled={loading}>
          {loading ? <><span className="spinner" /> Calcul en cours...</> : '⚡ Lancer le stress test'}
        </button>

        {!result ? (
          <div className="empty-hint">
            <div className="icon">⚡</div>
            <h3>Aucun résultat</h3>
            <p>Renseignez les chiffres et lancez le test.</p>
          </div>
        ) : (
          <>
            {/* Base */}
            <div className="card">
              <div className="card-header">
                <h3>Situation de base</h3>
                <span className={`chip ${statusChip(result.base_verdict.status)}`}>{result.base_verdict.label}</span>
              </div>
              <div className="card-body">
                <RatioGrid r={result.base_ratios} />
                <div style={{ fontSize:11, color:'#94a3b8', marginTop:10 }}>
                  Coûts variables: {result.derived.variable_cost_ratio}% du CA ·
                  Coûts fixes: {fmtNum(result.derived.fixed_costs)} DT ·
                  Résultat net: {fmtNum(result.derived.net_result)} DT
                  {result.derived.ebit_note && (
                    <span style={{ marginLeft:8, color:'#f59e0b' }}>
                      · Résultat exploitation {result.derived.ebit_note}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Scenarios */}
            <div className="section-label" style={{ padding:'4px 0 8px' }}>Scénarios</div>
            {result.scenarios.map(sc => (
              <div className="card" key={sc.key}>
                <div className="card-header">
                  <h3>{sc.label}</h3>
                  <span className={`chip ${statusChip(sc.verdict.status)}`}>{sc.verdict.label}</span>
                </div>
                <div className="card-body">
                  <div style={{ fontSize:12, color:'#64748b', marginBottom:10 }}>{sc.description}</div>
                  <RatioGrid r={sc.ratios} base={result.base_ratios} />
                </div>
              </div>
            ))}

            {/* Reverse stress test */}
            {Object.entries(result.reverse).filter(([k]) => !REVERSE_EXCLUDED.includes(k)).length > 0 && (
              <>
                <div className="section-label" style={{ padding:'4px 0 8px' }}>Test de résistance inversé</div>
                <div className="card">
                  <div className="card-body">
                    {Object.entries(result.reverse)
                      .filter(([k]) => !REVERSE_EXCLUDED.includes(k))
                      .map(([k, v]) => (
                        <div key={k} style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                          padding:'8px 0', borderBottom:'1px solid #f1f5f9' }}>
                          <span style={{ fontSize:12, color:'#374151', flex:1 }}>{v.note}</span>
                          <span style={{ fontSize:16, fontWeight:700, color: v.value === 0 ? '#dc2626' : '#0f172a' }}>
                            {v.value == null ? 'N/A' : `${v.value > 0 ? '−' : ''}${v.value}%`}
                          </span>
                        </div>
                      ))}
                    <div style={{ fontSize:11, color:'#94a3b8', marginTop:10 }}>
                      Le point de rupture indique l'ampleur du choc avant franchissement du seuil critique.
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Recommendations */}
            {hasBadVerdict && (
              <>
                <div className="section-label" style={{ padding:'4px 0 8px' }}>
                  Recommandations stratégiques
                </div>
                {!recs ? (
                  <button className="btn btn-primary btn-full" style={{ padding:11 }}
                    onClick={recommend} disabled={recLoading}>
                    {recLoading
                      ? <><span className="spinner" /> Génération des recommandations...</>
                      : '💡 Générer des recommandations'}
                  </button>
                ) : (
                  <div className="card">
                    <div className="card-header">
                      <h3>Plan d'action (côté entreprise)</h3>
                      <span className="chip chip-gray" style={{ fontSize:10 }}>{recs.method}</span>
                    </div>
                    <div className="card-body">
                      {recs.recommendations.length === 0 ? (
                        <div style={{ fontSize:13, color:'#64748b' }}>{recs.note}</div>
                      ) : (
                        recs.recommendations.map((r, i) => {
                          const prio = (r.priorite || '').toLowerCase()
                          const chip = prio === 'élevée' ? 'chip-red'
                            : prio === 'moyenne' ? 'chip-amber' : 'chip-gray'
                          return (
                            <div key={i} style={{ padding:'10px 0', borderBottom:'1px solid #f1f5f9' }}>
                              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:4 }}>
                                <span style={{ fontSize:12, fontWeight:600, color:'#0f172a' }}>{r.categorie}</span>
                                <span className={`chip ${chip}`} style={{ fontSize:10 }}>{r.priorite}</span>
                              </div>
                              <div style={{ fontSize:13, color:'#374151', lineHeight:1.5 }}>{r.recommandation}</div>
                            </div>
                          )
                        })
                      )}
                      {recs.llm_error && (
                        <div style={{ fontSize:11, color:'#94a3b8', marginTop:8 }}>
                          (Reformulation LLM indisponible — recommandations issues des règles)
                        </div>
                      )}
                      <button className="btn btn-sm" style={{ marginTop:10 }} onClick={recommend} disabled={recLoading}>
                        {recLoading ? <span className="spinner" /> : '↻ Régénérer'}
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// Ratio grid with optional comparison to base
function RatioGrid({ r, base }) {
  const items = [
    ['Couverture intérêts', r.interest_coverage, base?.interest_coverage, '×', v => v < 1 ? '#dc2626' : v < 1.5 ? '#92400e' : '#15803d'],
    ['DSCR (approx.)',       r.dscr_approx,        base?.dscr_approx,        '×', v => v < 1 ? '#dc2626' : v < 1.25 ? '#92400e' : '#15803d'],
    ['Marge exploitation',   r.operating_margin,   base?.operating_margin,   '%', v => v < 0 ? '#dc2626' : v < 5 ? '#92400e' : '#15803d'],
    ['Marge nette',          r.net_margin,         base?.net_margin,         '%', v => v < 0 ? '#dc2626' : v < 3 ? '#92400e' : '#15803d'],
    ['Ratio liquidité',      r.current_ratio,      base?.current_ratio,      '×', v => v < 1 ? '#dc2626' : v < 1.2 ? '#92400e' : '#15803d'],
  ]
  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
      {items.map(([label, val, baseVal, unit, color]) => (
        <div key={label} style={{ background:'#f8fafc', border:'1px solid #f1f5f9', borderRadius:8, padding:'8px 10px' }}>
          <div style={{ fontSize:10, color:'#94a3b8', marginBottom:2 }}>{label}</div>
          <div style={{ fontSize:18, fontWeight:700, color: color(val) }}>
            {val}{unit}
          </div>
          {baseVal != null && (
            <div style={{ fontSize:10, color:'#94a3b8' }}>base: {baseVal}{unit}</div>
          )}
        </div>
      ))}
    </div>
  )
}
