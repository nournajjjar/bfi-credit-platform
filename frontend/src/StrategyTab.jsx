import { useState, useEffect } from 'react'
import { api } from './api'

// ══════════════════════════════════════════════════════════════════
// STRATÉGIES — page dédiée aux recommandations
// Flux : choisir un rapport → verdict (rapport + stress test déjà fait)
//        → générer des stratégies
// ══════════════════════════════════════════════════════════════════

const statusChip = s => ({ ok:'chip-green', warning:'chip-amber', break:'chip-red' }[s] || 'chip-gray')
const prioChip   = p => ({ 'élevée':'chip-red', 'moyenne':'chip-amber', 'faible':'chip-gray' }[(p||'').toLowerCase()] || 'chip-gray')
const effortChip = e => ({ 'faible':'chip-green', 'moyen':'chip-amber', 'élevé':'chip-red' }[(e||'').toLowerCase()] || 'chip-gray')
const impactChip = i => ({ 'élevé':'chip-green', 'moyen':'chip-amber', 'faible':'chip-gray', 'structurel':'chip-blue' }[(i||'').toLowerCase()] || 'chip-gray')
const fmtDate    = d => d ? new Date(d).toLocaleString('fr-FR', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : ''

export default function StrategyTab() {
  const [reports,  setReports]  = useState([])
  const [reportId, setReportId] = useState('')
  const [overview, setOverview] = useState(null)
  const [stress,   setStress]   = useState(null)
  const [recs,     setRecs]     = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [recLoading, setRecLoading] = useState(false)
  const [alert,    setAlert]    = useState(null)

  function showAlert(msg, type='blue') { setAlert({ msg, type }); setTimeout(() => setAlert(null), 6000) }

  useEffect(() => { api.getReports().then(setReports).catch(() => {}) }, [])

  async function loadReport(id) {
    setReportId(id); setOverview(null); setStress(null); setRecs(null)
    if (!id) return
    setLoading(true)
    try {
      const [ov, st] = await Promise.all([
        api.stressOverview(id),
        api.stressSaved(id),
      ])
      setOverview(ov)
      setStress(st)
    } catch (e) {
      showAlert('Erreur: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setLoading(false) }
  }

  async function recommend() {
    setRecLoading(true); setRecs(null)
    try {
      const d = await api.stressRecommendSaved(reportId)
      setRecs(d.recommendations)
    } catch (e) {
      showAlert('Erreur recommandations: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setRecLoading(false) }
  }

  const sr = stress?.saved ? stress.result : null

  return (
    <div className="two-col">
      {/* LEFT: pick report + verdicts */}
      <div className="left-col">
        <div className="section-label">Rapport généré</div>
        <div style={{ padding:'0 16px 12px' }}>
          <select value={reportId} onChange={e => loadReport(e.target.value)} style={{ width:'100%' }}>
            <option value="">— Choisir un rapport —</option>
            {reports.map(r => <option key={r.report_id} value={r.report_id}>{r.company_name}</option>)}
          </select>
        </div>

        {alert && <div style={{ padding:'0 16px 8px' }}><div className={`alert alert-${alert.type}`}>{alert.msg}</div></div>}

        {loading && <div style={{ padding:'20px 16px', fontSize:13, color:'#94a3b8' }}><span className="spinner" /> Chargement...</div>}

        {overview && (
          <div style={{ padding:'0 16px 16px' }}>
            {/* Company + report verdict */}
            <div className="card">
              <div className="card-header"><h3>{overview.company_name}</h3></div>
              <div className="card-body">
                <div style={{ fontSize:12, color:'#64748b', marginBottom:8 }}>
                  {overview.secteur} · {overview.gouvernorat} · {overview.regime}
                </div>
                {overview.report_verdict ? (
                  <>
                    <div style={{ fontSize:10, fontWeight:700, color:'#94a3b8', textTransform:'uppercase', marginBottom:4 }}>
                      Verdict du rapport
                    </div>
                    <div style={{ fontSize:12, color:'#374151', lineHeight:1.5, maxHeight:160, overflowY:'auto' }}>
                      {overview.report_verdict.text}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize:12, color:'#94a3b8' }}>Pas de section verdict détectée dans le rapport.</div>
                )}
              </div>
            </div>

            {/* Stress test status */}
            <div className="card" style={{ marginTop:12 }}>
              <div className="card-header">
                <h3>Stress test</h3>
                {sr
                  ? <span className={`chip ${statusChip(sr.base_verdict.status)}`}>{sr.base_verdict.label}</span>
                  : <span className="chip chip-gray">Non effectué</span>}
              </div>
              <div className="card-body">
                {sr ? (
                  <>
                    {sr.scenarios.map(s => (
                      <div key={s.key} style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                        padding:'6px 0', borderBottom:'1px solid #f1f5f9' }}>
                        <span style={{ fontSize:12, color:'#374151', flex:1 }}>{s.label}</span>
                        <span className={`chip ${statusChip(s.verdict.status)}`} style={{ fontSize:10 }}>{s.verdict.label}</span>
                      </div>
                    ))}
                    {sr.reverse?.revenue_drop_icr?.value != null && (
                      <div style={{ fontSize:12, color:'#64748b', marginTop:8 }}>
                        Rupture à <b>&minus;{sr.reverse.revenue_drop_icr.value}%</b> de CA (couverture intérêts &lt; 1.0&times;).
                      </div>
                    )}
                    <div style={{ fontSize:11, color:'#94a3b8', marginTop:8 }}>
                      Effectué le {fmtDate(stress.updated_at)}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize:12, color:'#92400e' }}>
                    Aucun stress test sauvegardé pour ce rapport.
                    <br /><span style={{ color:'#64748b' }}>Lancez-en un dans l'onglet ⚡ Stress Test (en sélectionnant ce rapport), puis revenez ici.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* RIGHT: recommendations */}
      <div className="right-col">
        {!overview ? (
          <div className="empty-hint">
            <div className="icon">💡</div>
            <h3>Choisir un rapport</h3>
            <p>Sélectionnez un rapport pour voir son verdict et générer des stratégies.</p>
          </div>
        ) : !sr ? (
          <div className="empty-hint">
            <div className="icon">⚡</div>
            <h3>Stress test requis</h3>
            <p>Les recommandations s'appuient sur un stress test. Lancez-en un dans l'onglet ⚡ Stress Test pour ce rapport.</p>
          </div>
        ) : (
          <>
            <button className="btn btn-primary btn-full" style={{ marginBottom:16, padding:12, fontSize:14 }}
              onClick={recommend} disabled={recLoading}>
              {recLoading ? <><span className="spinner" /> Génération des stratégies...</> : '💡 Générer les stratégies'}
            </button>

            {!recs ? (
              <div className="empty-hint" style={{ paddingTop:20 }}>
                <p>Cliquez ci-dessus pour obtenir un plan d'action fondé sur le verdict et le stress test.</p>
              </div>
            ) : !recs.has_recommendations ? (
              <div className="card"><div className="card-body">
                <div style={{ fontSize:13, color:'#15803d' }}>✅ {recs.note || "Aucune vulnérabilité critique détectée."}</div>
              </div></div>
            ) : (
              <>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
                  <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8', textTransform:'uppercase' }}>
                    Plan d'action — {recs.recommendations.length} levier(s)
                  </span>
                  {recs.method && <span className="chip chip-gray" style={{ fontSize:10 }}>{recs.method}</span>}
                </div>

                {['court', 'moyen', 'long'].map(h => {
                  const items = recs.by_horizon?.[h] || []
                  if (!items.length) return null
                  return (
                    <div key={h} style={{ marginBottom:14 }}>
                      <div className="section-label" style={{ padding:'2px 0 6px' }}>
                        {recs.horizon_labels?.[h] || h}
                      </div>
                      {items.map((r, i) => <RecCard key={i} r={r} />)}
                    </div>
                  )
                })}

                {recs.recommendations.some(r => r.recommandation === undefined) && (
                  <div style={{ fontSize:11, color:'#94a3b8' }}>
                    (Reformulation LLM indisponible — texte issu des règles)
                  </div>
                )}
                <button className="btn btn-sm" onClick={recommend} disabled={recLoading}>
                  {recLoading ? <span className="spinner" /> : '↻ Régénérer'}
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// Carte de recommandation enrichie (horizon / effort / impact / what-if)
function RecCard({ r }) {
  const wi = r.impact || {}
  return (
    <div className="card" style={{ marginBottom:8 }}>
      <div className="card-body" style={{ padding:'12px 14px' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:6, gap:6, flexWrap:'wrap' }}>
          <span style={{ fontSize:12, fontWeight:600, color:'#0f172a' }}>{r.categorie}</span>
          <div style={{ display:'flex', gap:5, flexWrap:'wrap' }}>
            <span className={`chip ${prioChip(r.priorite)}`} style={{ fontSize:10 }}>priorité {r.priorite}</span>
            <span className={`chip ${effortChip(r.effort)}`} style={{ fontSize:10 }}>effort {r.effort}</span>
            <span className={`chip ${impactChip(wi.impact_level)}`} style={{ fontSize:10 }}>impact {wi.impact_level}</span>
          </div>
        </div>

        <div style={{ fontSize:13, color:'#374151', lineHeight:1.5, marginBottom:8 }}>{r.recommandation}</div>

        {/* What-if simulation (#2) */}
        {wi.applicable ? (
          <div style={{ fontSize:11, color:'#475569', background:'#f8fafc', border:'1px solid #f1f5f9',
            borderRadius:7, padding:'7px 10px' }}>
            <b>Simulation :</b> couverture intérêts {wi.interest_coverage_before}× → <b style={{ color:'#15803d' }}>{wi.interest_coverage_after}×</b>
            {' · '}verdict {wi.verdict_before} → <b style={{ color:'#15803d' }}>{wi.verdict_after}</b>
            {wi.scenarios_improved > 0 && <> · {wi.scenarios_improved} scénario(s) amélioré(s)</>}
          </div>
        ) : (
          <div style={{ fontSize:11, color:'#94a3b8', fontStyle:'italic' }}>{wi.note}</div>
        )}
      </div>
    </div>
  )
}
