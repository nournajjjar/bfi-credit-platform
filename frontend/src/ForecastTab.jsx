import { useState, useEffect, useRef } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer
} from 'recharts'
import { api } from './api'

const ALL_PERIOD_FIELDS = [
  ['revenue',       "Chiffre d'affaires"],
  ['ebit',          "EBIT"],
  ['raw_materials', "Achats consommes"],
  ['interest',      "Interets (bruts)"],
  ['net_result',    "Resultat net"],
]

const METRICS = {
  revenue:    { label: "Chiffre d'affaires", unit: "M DT", scale: 1e6, color: "#2563eb", dp: 1 },
  ebit:       { label: "EBIT",               unit: "M DT", scale: 1e6, color: "#16a34a", dp: 1 },
  icr:        { label: "Couverture interets", unit: "x",    scale: 1,   color: "#7c3aed", dp: 2 },
  net_margin: { label: "Marge nette",        unit: "%",    scale: 1,   color: "#ea580c", dp: 1 },
}

const SCENARIO_COLORS = { recession: "#dc2626", inflation: "#f59e0b", fx: "#8b5cf6" }
const SCENARIO_LABELS = { recession: "Recession", inflation: "Inflation", fx: "Change" }

const emptyPeriod = () => ({
  id: Date.now() + Math.random(),
  date: '', revenue: '', ebit: '', raw_materials: '', interest: '', net_result: ''
})

function fmtVal(v, scale, dp) {
  if (v == null) return '-'
  return (v / scale).toFixed(dp)
}

function getActiveFields(periods) {
  return ALL_PERIOD_FIELDS.filter(([k]) =>
    k === 'revenue' || periods.some(p => {
      const v = parseFloat(p[k])
      return !isNaN(v) && v !== 0
    })
  )
}

function getVal(point, metric, source) {
  const m = METRICS[metric]
  const scale = m.scale
  if (source === 'base') return point[metric] != null ? point[metric] / scale : null
  if (source === 'low')  return metric === 'icr' ? point.icr_low : metric === 'revenue' ? (point.revenue_low ? point.revenue_low / scale : null) : null
  if (source === 'high') return metric === 'icr' ? point.icr_high : metric === 'revenue' ? (point.revenue_high ? point.revenue_high / scale : null) : null
  if (['recession', 'inflation', 'fx'].includes(source)) {
    const s = point.stressed?.[source]
    if (!s) return null
    if (metric === 'revenue')    return s.revenue != null ? s.revenue / scale : null
    if (metric === 'ebit')       return s.ebit    != null ? s.ebit    / scale : null
    if (metric === 'icr')        return s.icr
    if (metric === 'net_margin') return s.net_margin
  }
  return null
}

export default function ForecastTab() {
  const [reports,    setReports]    = useState([])
  const [periods,    setPeriods]    = useState([emptyPeriod(), emptyPeriod()])
  const [companyName,setCompanyName]= useState('')
  const [isExporter, setIsExporter] = useState(false)
  const [horizon,    setHorizon]    = useState(5)
  const [metric,     setMetric]     = useState('revenue')
  const [result,     setResult]     = useState(null)
  const [loading,    setLoading]    = useState(false)
  const [alert,      setAlert]      = useState(null)
  const [uploading,  setUploading]  = useState(false)
  const fileRef = useRef()

  function showAlert(msg, type='blue') { setAlert({ msg, type }); setTimeout(() => setAlert(null), 6000) }

  useEffect(() => { api.getReports().then(setReports).catch(() => {}) }, [])

  const activeFields = getActiveFields(periods)

  // Check if result is valid (has historical/projected) or just an error
  const resultOk = result && !result.error && result.historical && result.projected

  async function loadFromReport(reportId) {
    if (!reportId) return
    try {
      const d = await api.forecastLoad(reportId)
      setCompanyName(d.company_name || '')
      setIsExporter(d.regime?.toLowerCase().includes('totalement exportatrice') &&
                    !d.regime?.toLowerCase().includes('non totalement'))
      if (d.periods && d.periods.length > 0) {
        setPeriods(d.periods.map(p => ({ id: Date.now() + Math.random(), ...p,
          revenue:       p.revenue       != null ? String(Math.round(p.revenue))       : '',
          ebit:          p.ebit          != null ? String(Math.round(p.ebit))          : '',
          raw_materials: p.raw_materials != null ? String(Math.round(p.raw_materials)) : '',
          interest:      p.interest      != null ? String(Math.round(p.interest))      : '',
          net_result:    p.net_result    != null ? String(Math.round(p.net_result))    : '',
        })))
        showAlert(`${d.periods.length} periode(s) chargee(s) depuis le rapport.`, 'green')
      } else {
        showAlert(d.note || 'Aucune periode extraite - saisir manuellement.', 'amber')
      }
    } catch (e) {
      showAlert('Erreur chargement: ' + (e.response?.data?.detail || e.message), 'red')
    }
  }

  async function uploadPdf(file) {
    setUploading(true)
    try {
      const fd = new FormData(); fd.append('file', file)
      const d = await api.forecastExtractPdf(fd)
      if (d.periods && d.periods.length > 0) {
        const newPeriods = d.periods.map(p => ({ id: Date.now() + Math.random(), ...p,
          revenue:       p.revenue       != null ? String(Math.round(p.revenue))       : '',
          ebit:          p.ebit          != null ? String(Math.round(p.ebit))          : '',
          raw_materials: p.raw_materials != null ? String(Math.round(p.raw_materials)) : '',
          interest:      p.interest      != null ? String(Math.round(p.interest))      : '',
          net_result:    p.net_result    != null ? String(Math.round(p.net_result))    : '',
        }))
        const newDates = new Set(newPeriods.map(p => p.date))
        const kept = periods.filter(p => p.date && !newDates.has(p.date))
        const merged = [...kept, ...newPeriods].sort((a, b) => (a.date || '').localeCompare(b.date || ''))
        setPeriods(merged.length > 0 ? merged : [emptyPeriod()])
        showAlert(`${d.periods.length} periode(s) extraite(s) depuis ${file.name}.`, 'green')
      } else {
        showAlert(d.note || 'Aucune periode extraite - saisir manuellement.', 'amber')
      }
    } catch (e) {
      showAlert('Erreur extraction: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setUploading(false) }
  }

  function updatePeriod(id, key, val) { setPeriods(p => p.map(r => r.id === id ? { ...r, [key]: val } : r)) }
  function addPeriod()  { setPeriods(p => [...p, emptyPeriod()]) }
  function removePeriod(id) { if (periods.length > 1) setPeriods(p => p.filter(r => r.id !== id)) }
  function clearAll()   { setPeriods([emptyPeriod(), emptyPeriod()]); setResult(null) }

  async function runForecast() {
    const valid = periods.filter(p => p.date && p.revenue)
    if (valid.length < 2) { showAlert('Au moins 2 periodes avec date et CA requis.', 'amber'); return }
    const periodPayload = valid.map(p => {
      const row = { date: p.date }
      for (const [k] of activeFields) {
        const v = parseFloat(p[k])
        if (!isNaN(v) && v !== 0) row[k] = v
      }
      return row
    })
    setLoading(true); setResult(null)
    try {
      const d = await api.forecastRun({ company_name: companyName, is_exporter: isExporter, horizon, periods: periodPayload })
      setResult(d.result)
    } catch (e) {
      showAlert('Erreur: ' + (e.response?.data?.detail || e.message), 'red')
    } finally { setLoading(false) }
  }

  function buildChartData() {
    if (!resultOk) return []
    const m = METRICS[metric]
    const hist = result.historical.map(h => ({
      year: h.year,
      base_hist: h[metric] != null ? h[metric] / m.scale : null,
      base_proj: null, low: null, high: null,
      recession: null, inflation: null, fx: null,
    }))
    const lastHist = hist[hist.length - 1]
    if (lastHist) lastHist.base_proj = lastHist.base_hist
    const proj = result.projected.map(p => ({
      year: p.year, base_hist: null,
      base_proj: getVal(p, metric, 'base'),
      low:  getVal(p, metric, 'low'),
      high: getVal(p, metric, 'high'),
      recession: getVal(p, metric, 'recession'),
      inflation: getVal(p, metric, 'inflation'),
      fx:        getVal(p, metric, 'fx'),
    }))
    return [...hist, ...proj]
  }

  const chartData  = buildChartData()
  const m          = METRICS[metric]
  const bridgeYear = resultOk ? result.historical?.[result.historical.length - 1]?.year : null

  const hasEbit      = resultOk && result.historical?.some(h => h.ebit != null && h.ebit !== 0)
  const hasIcr       = resultOk && result.projected?.some(p => p.icr != null && p.icr !== 0 && isFinite(p.icr))
  const hasNetMargin = resultOk && result.projected?.some(p => p.net_margin != null && p.net_margin !== 0)

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null
    return (
      <div style={{ background:'#fff', border:'1px solid #e2e8f0', borderRadius:8, padding:'8px 12px', fontSize:12 }}>
        <div style={{ fontWeight:600, marginBottom:4 }}>{label}</div>
        {payload.map((entry, i) => (
          <div key={i} style={{ color: entry.color, display:'flex', gap:8 }}>
            <span>{entry.name}:</span>
            <span>{entry.value != null ? `${entry.value.toFixed(m.dp)} ${m.unit}` : '-'}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="two-col">
      {/* LEFT */}
      <div className="left-col" style={{ overflowY:'auto', maxHeight:'calc(100vh - 120px)' }}>
        <div className="section-label">Source des donnees</div>
        <div style={{ padding:'0 16px 8px' }}>
          <div className="field">
            <label>Depuis un rapport existant</label>
            <select onChange={e => loadFromReport(e.target.value)} style={{ width:'100%' }}>
              <option value="">-- Choisir --</option>
              {reports.map(r => <option key={r.report_id} value={r.report_id}>{r.company_name}</option>)}
            </select>
          </div>
          <div style={{ display:'flex', gap:8, marginBottom:8 }}>
            <button className="btn" style={{ flex:1 }} onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? <><span className="spinner" /> Extraction...</> : 'Ajouter un PDF CMF'}
            </button>
            <input ref={fileRef} type="file" accept=".pdf" style={{ display:'none' }}
              onChange={e => e.target.files[0] && uploadPdf(e.target.files[0])} />
          </div>
          {alert && <div className={`alert alert-${alert.type}`} style={{ marginBottom:8 }}>{alert.msg}</div>}
          <div className="field">
            <label>Nom de l'entreprise</label>
            <input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="SAH..." />
          </div>
          <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:12, color:'#64748b', marginBottom:12 }}>
            <input type="checkbox" checked={isExporter} onChange={e => setIsExporter(e.target.checked)} />
            Totalement exportatrice
          </label>
        </div>

        <div className="section-label">Periodes financieres (DT)</div>
        <div style={{ overflowX:'auto', padding:'0 8px 8px' }}>
          <table style={{ width:'100%', fontSize:11, borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ background:'#f8fafc' }}>
                <th style={thStyle}>Date (JJ.MM.AAAA)</th>
                {activeFields.map(([k, l]) => <th key={k} style={thStyle}>{l}</th>)}
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {periods.map(p => (
                <tr key={p.id}>
                  <td style={tdStyle}>
                    <input value={p.date} onChange={e => updatePeriod(p.id, 'date', e.target.value)}
                      placeholder="31.12.2023" style={inputStyle} />
                  </td>
                  {activeFields.map(([k]) => (
                    <td key={k} style={tdStyle}>
                      <input value={p[k] || ''} onChange={e => updatePeriod(p.id, k, e.target.value)}
                        placeholder="0" style={inputStyle} inputMode="numeric" />
                    </td>
                  ))}
                  <td style={tdStyle}>
                    <button onClick={() => removePeriod(p.id)}
                      style={{ border:'none', background:'none', cursor:'pointer', color:'#dc2626', fontSize:13 }}>{'\u2715'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display:'flex', gap:8, marginTop:6 }}>
            <button className="btn btn-sm" onClick={addPeriod}>+ Periode</button>
            <button className="btn btn-sm" onClick={clearAll}>Vider</button>
          </div>
        </div>

        <div style={{ padding:'8px 16px' }}>
          <div className="field">
            <label>Horizon de projection : <b>{horizon} ans</b></label>
            <input type="range" min={1} max={10} value={horizon} onChange={e => setHorizon(Number(e.target.value))}
              style={{ width:'100%' }} />
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'#94a3b8' }}>
              <span>1 an</span><span>5 ans</span><span>10 ans</span>
            </div>
          </div>
        </div>
        <div style={{ padding:'0 16px 16px' }}>
          <button className="btn btn-primary btn-full" style={{ padding:11 }} onClick={runForecast} disabled={loading}>
            {loading ? <><span className="spinner" /> Projection en cours...</> : 'Lancer la projection'}
          </button>
        </div>
      </div>

      {/* RIGHT */}
      <div className="right-col" style={{ overflowY:'auto', maxHeight:'calc(100vh - 120px)' }}>
        {!result ? (
          <div className="empty-hint">
            <div className="icon">{'\u{1F4C8}'}</div>
            <h3>Previsions financieres</h3>
            <p>Chargez un rapport ou saisissez les donnees historiques, puis lancez la projection.</p>
          </div>
        ) : result.error ? (
          <div style={{ padding:24 }}>
            <div className="alert alert-red">
              <b>Erreur de projection :</b> {result.error}
            </div>
            <div style={{ marginTop:12, fontSize:12, color:'#64748b' }}>
              Verifiez que vous avez au moins 2 periodes avec une date et un chiffre d'affaires valides.
            </div>
          </div>
        ) : !resultOk ? (
          <div style={{ padding:24 }}>
            <div className="alert alert-amber">Resultat invalide ou incomplet.</div>
          </div>
        ) : (
          <>
            {/* Model stats */}
            <div className="card" style={{ marginBottom:12 }}>
              <div className="card-body" style={{ display:'flex', gap:16, flexWrap:'wrap', alignItems:'center', padding:'10px 14px' }}>
                <div><span style={{ fontSize:10, color:'#94a3b8' }}>Modele</span><br/><b style={{ fontSize:13 }}>{result.model_stats.model}</b></div>
                {result.model_stats.r2 != null && <div><span style={{ fontSize:10, color:'#94a3b8' }}>R2</span><br/><b style={{ fontSize:13 }}>{result.model_stats.r2}</b></div>}
                {result.model_stats.cagr_pct != null && <div><span style={{ fontSize:10, color:'#94a3b8' }}>CAGR historique</span><br/><b style={{ fontSize:13 }}>{result.model_stats.cagr_pct}%/an</b></div>}
                <div><span style={{ fontSize:10, color:'#94a3b8' }}>Donnees</span><br/><b style={{ fontSize:13 }}>{result.model_stats.n_points} point(s)</b></div>
                <div><span style={{ fontSize:10, color:'#94a3b8' }}>Couts variables</span><br/><b style={{ fontSize:13 }}>{result.var_cost_ratio_pct}% du CA</b></div>
                {result.model_stats.warning && (
                  <div className="alert alert-amber" style={{ flex:'1 1 100%', padding:'4px 8px', fontSize:11, marginBottom:0 }}>
                    {result.model_stats.warning}
                  </div>
                )}
              </div>
            </div>

            {/* Metric selector */}
            <div style={{ display:'flex', gap:6, marginBottom:10 }}>
              {Object.entries(METRICS)
                .filter(([k]) =>
                  k === 'revenue' ||
                  (k === 'ebit' && hasEbit) ||
                  (k === 'icr' && hasIcr) ||
                  (k === 'net_margin' && hasNetMargin)
                )
                .map(([k, v]) => (
                  <button key={k} className={`btn btn-sm ${metric===k?'btn-primary':''}`} onClick={() => setMetric(k)}>
                    {v.label}
                  </button>
                ))}
            </div>

            {/* Chart */}
            <div className="card" style={{ marginBottom:12 }}>
              <div className="card-header">
                <h3>{m.label} -- {companyName || 'Projection'}</h3>
                <span style={{ fontSize:11, color:'#94a3b8' }}>en {m.unit}</span>
              </div>
              <div style={{ padding:'8px 4px', height:300, minHeight:300, width:'100%', display:'block' }}>
                <ResponsiveContainer width="99%" height={280}>
                  <ComposedChart data={chartData} margin={{ top:10, right:20, bottom:0, left:10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="year" tick={{ fontSize:11 }} />
                    <YAxis tick={{ fontSize:10 }} tickFormatter={v => `${v.toFixed(m.dp)}`}
                      label={{ value: m.unit, angle:-90, position:'insideLeft', fontSize:10 }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend wrapperStyle={{ fontSize:11 }} />
                    {bridgeYear && <ReferenceLine x={bridgeYear} stroke="#94a3b8" strokeDasharray="4 2"
                      label={{ value:'projete', position:'top', fontSize:9, fill:'#94a3b8' }} />}
                    <Line type="monotone" dataKey="base_hist" name="Historique" stroke={m.color}
                      strokeWidth={2.5} dot={{ r:4 }} connectNulls={false} />
                    <Line type="monotone" dataKey="base_proj" name="Projection (base)"
                      stroke={m.color} strokeWidth={2} strokeDasharray="6 3" dot={{ r:3 }} connectNulls={false} />
                    <Line type="monotone" dataKey="high" name="IC superieur (90%)"
                      stroke={m.color} strokeWidth={1} strokeDasharray="2 3" strokeOpacity={0.4} dot={false} connectNulls={false} />
                    <Line type="monotone" dataKey="low" name="IC inferieur (90%)"
                      stroke={m.color} strokeWidth={1} strokeDasharray="2 3" strokeOpacity={0.4} dot={false} connectNulls={false} />
                    {Object.entries(SCENARIO_COLORS).map(([scen, color]) => (
                      <Line key={scen} type="monotone" dataKey={scen}
                        name={SCENARIO_LABELS[scen]} stroke={color}
                        strokeWidth={1.5} strokeDasharray="3 3" dot={false} connectNulls={false} />
                    ))}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Summary table */}
            <div className="card">
              <div className="card-header"><h3>Tableau de projection</h3></div>
              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', fontSize:11, borderCollapse:'collapse' }}>
                  <thead>
                    <tr style={{ background:'#f8fafc', borderBottom:'2px solid #e2e8f0' }}>
                      <th style={thStyle}>Annee</th>
                      <th style={thStyle}>CA (M DT)</th>
                      {hasEbit      && <th style={thStyle}>EBIT (M DT)</th>}
                      {hasIcr       && <th style={thStyle}>ICR</th>}
                      {hasNetMargin && <th style={thStyle}>Marge nette</th>}
                      {hasIcr       && <th style={{ ...thStyle, color:'#dc2626' }}>ICR (recession)</th>}
                      {hasIcr       && <th style={{ ...thStyle, color:'#f59e0b' }}>ICR (inflation)</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {result.historical.map((h, i) => (
                      <tr key={i} style={{ background:'#eff6ff' }}>
                        <td style={tdStyle}><b>{h.year}</b></td>
                        <td style={tdStyle}>{fmtVal(h.revenue, 1e6, 1)}</td>
                        {hasEbit      && <td style={tdStyle}>{h.ebit != null && h.ebit !== 0 ? fmtVal(h.ebit, 1e6, 1) : '-'}</td>}
                        {hasIcr       && <td style={tdStyle}>{h.icr != null && isFinite(h.icr) ? h.icr : '-'}</td>}
                        {hasNetMargin && <td style={tdStyle}>{h.net_margin != null ? `${h.net_margin}%` : '-'}</td>}
                        {hasIcr       && <td style={tdStyle}>-</td>}
                        {hasIcr       && <td style={tdStyle}>-</td>}
                      </tr>
                    ))}
                    {result.projected.map((p, i) => (
                      <tr key={i} style={{ borderBottom:'1px solid #f1f5f9' }}>
                        <td style={tdStyle}><span style={{ color:'#64748b' }}>{p.year}</span></td>
                        <td style={tdStyle}>{fmtVal(p.revenue, 1e6, 1)}</td>
                        {hasEbit      && <td style={tdStyle}>{p.ebit != null && p.ebit !== 0 ? fmtVal(p.ebit, 1e6, 1) : '-'}</td>}
                        {hasIcr       && <td style={{ ...tdStyle, fontWeight:600, color: p.icr < 1 ? '#dc2626' : p.icr < 1.5 ? '#92400e' : '#15803d' }}>
                          {p.icr != null && isFinite(p.icr) ? p.icr : '-'}
                        </td>}
                        {hasNetMargin && <td style={{ ...tdStyle, color: p.net_margin < 0 ? '#dc2626' : '#374151' }}>
                          {p.net_margin != null ? `${p.net_margin}%` : '-'}
                        </td>}
                        {hasIcr       && <td style={{ ...tdStyle, color:'#dc2626' }}>{p.stressed?.recession?.icr ?? '-'}</td>}
                        {hasIcr       && <td style={{ ...tdStyle, color:'#f59e0b' }}>{p.stressed?.inflation?.icr ?? '-'}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize:10, color:'#94a3b8', padding:'6px 12px' }}>
                Lignes bleues = historique · Lignes blanches = projection · ICR inferieur a 1.0 = rupture
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const thStyle    = { padding:'6px 8px', textAlign:'left', fontSize:10, fontWeight:700, color:'#64748b', borderBottom:'1px solid #e2e8f0', whiteSpace:'nowrap' }
const tdStyle    = { padding:'5px 8px', fontSize:11, borderBottom:'1px solid #f8fafc' }
const inputStyle = { width:'100%', border:'1px solid #e2e8f0', borderRadius:4, padding:'3px 5px', fontSize:11 }
