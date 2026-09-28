import { useState, useEffect } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

const COLORS = ['#1E3A8A','#1D4ED8','#2563EB','#3B82F6','#60A5FA','#93C5FD','#1E40AF','#1d5296','#4B7BE8','#2979D4']

const VERDICT_COLORS = {
  'Favorable':         '#1E3A8A',
  'Acceptable':        '#2563EB',
  'Sous surveillance': '#60A5FA',
  'Défavorable':       '#93C5FD',
  'Réservé':           '#BFDBFE',
  'Inconnu':           '#DBEAFE',
}

const fmtDate = d => new Date(d).toLocaleDateString('fr-FR', { day:'2-digit', month:'short', year:'2-digit' })

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background:'#fff', border:'1px solid #e2e8f0', borderRadius:8, padding:'8px 12px', fontSize:12 }}>
      <div style={{ fontWeight:600, marginBottom:4 }}>{label}</div>
      {payload.map((e, i) => (
        <div key={i} style={{ color: e.color }}>{e.name}: <b>{e.value}</b></div>
      ))}
    </div>
  )
}

function KpiCard({ label, value, color='#1E3A8A', sub }) {
  return (
    <div style={{ background:'#fff', border:'1px solid #e2e8f0', borderRadius:10,
      padding:'16px 20px', flex:1, minWidth:140 }}>
      <div style={{ fontSize:11, color:'#94a3b8', marginBottom:4 }}>{label}</div>
      <div style={{ fontSize:28, fontWeight:800, color }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>{sub}</div>}
    </div>
  )
}

export default function DashboardTab() {
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [search,  setSearch]  = useState('')

  const loadStats = () => {
    setLoading(true)
    fetch('http://localhost:8000/api/dashboard/stats', {
      headers: { Authorization: 'Bearer ' + localStorage.getItem('bfi_token') }
    })
      .then(r => r.json())
      .then(d => { setStats(d); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { setTimeout(loadStats, 300) }, [])

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
      height:'60vh', flexDirection:'column', gap:12 }}>
      <span className="spinner" style={{ width:32, height:32 }}/>
      <div style={{ color:'#64748b' }}>Chargement du tableau de bord...</div>
    </div>
  )

  if (!stats) return (
    <div className="empty-hint">
      <div className="icon">📊</div>
      <h3>Données indisponibles</h3>
      <button className="btn btn-primary" onClick={loadStats} style={{ marginTop:12 }}>↻ Réessayer</button>
    </div>
  )

  const filtered = (stats.companies || []).filter(c =>
    !search ||
    c.company_name?.toLowerCase().includes(search.toLowerCase()) ||
    c.gouvernorat?.toLowerCase().includes(search.toLowerCase()) ||
    c.secteur?.toLowerCase().includes(search.toLowerCase())
  )

  // Sectors from APII database
  const secteursDb = (stats.secteurs_db || []).slice(0, 10)

  return (
    <div style={{ padding:20, overflowY:'auto', height:'calc(100vh - 80px)' }}>

      {/* KPIs */}
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <KpiCard label="Rapports générés"      value={stats.total_reports}           color="#1E3A8A" />
        <KpiCard label="Révisions chatbot"     value={stats.total_revisions}         color="#3B82F6" sub="sections modifiées" />
        <KpiCard label="Gouvernorats couverts" value={stats.gouvernorats?.length||0} color="#16A34A" />
        <KpiCard label="Secteurs APII"         value={secteursDb.length}             color="#F59E0B" />
      </div>

      {/* Row 1: Gouvernorats + Verdicts */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>

        {/* Gouvernorats */}
        <div className="card">
          <div className="card-header">
            <h3>📍 Répartition par gouvernorat </h3>
          </div>
          <div className="card-body" style={{ height:280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.gouvernorats?.slice(0,10)} layout="vertical"
                margin={{ left:80, right:30, top:5, bottom:5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false}/>
                <XAxis type="number" tick={{ fontSize:11 }} allowDecimals={false}/>
                <YAxis type="category" dataKey="name" tick={{ fontSize:11 }} width={80}/>
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Entreprises" radius={[0,4,4,0]}>
                  {stats.gouvernorats?.slice(0,10).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Verdicts */}
        <div className="card">
          <div className="card-header"><h3>⚖️ Distribution des verdicts crédit</h3></div>
          <div className="card-body" style={{ height:280, display:'flex', flexDirection:'column', gap:12 }}>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={stats.verdicts}
                  dataKey="count"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  innerRadius={30}
                  paddingAngle={3}
                  labelLine={false}
                  label={({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
                    if (percent < 0.05) return null
                    const RADIAN = Math.PI / 180
                    const r = innerRadius + (outerRadius - innerRadius) * 0.5
                    const x = cx + r * Math.cos(-midAngle * RADIAN)
                    const y = cy + r * Math.sin(-midAngle * RADIAN)
                    return (
                      <text x={x} y={y} fill="white" textAnchor="middle"
                        dominantBaseline="central" fontSize={11} fontWeight={700}>
                        {`${Math.round(percent * 100)}%`}
                      </text>
                    )
                  }}>
                  {stats.verdicts?.map((entry, i) => (
                    <Cell key={i} fill={VERDICT_COLORS[entry.name] || COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v, n) => [v, n]}/>
              </PieChart>
            </ResponsiveContainer>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, justifyContent:'center' }}>
              {stats.verdicts?.map((v, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <div style={{ width:10, height:10, borderRadius:2, flexShrink:0,
                    background: VERDICT_COLORS[v.name] || COLORS[i % COLORS.length] }}/>
                  <span style={{ fontSize:11 }}>
                    {v.name} — {v.count} ({Math.round(v.count / stats.total_reports * 100)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Top secteurs (APII database) + Timeline */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>

        {/* Top secteurs from APII database */}
        <div className="card">
          <div className="card-header">
            <h3>🏆 Top secteurs des entreprises </h3>
          </div>
          <div className="card-body" style={{ height:280 }}>
            {secteursDb.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={secteursDb} layout="vertical"
                  margin={{ left:150, right:40, top:5, bottom:5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false}/>
                  <XAxis type="number" tick={{ fontSize:11 }} allowDecimals={false}/>
                  <YAxis type="category" dataKey="name" tick={{ fontSize:10 }} width={150}/>
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" name="Entreprises" radius={[0,4,4,0]}>
                    {secteursDb.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
                height:'100%', color:'#94a3b8', fontSize:13 }}>
                Aucune donnée disponible
              </div>
            )}
          </div>
        </div>

        {/* Timeline */}
        <div className="card">
          <div className="card-header"><h3>📅 Activité — rapports générés</h3></div>
          <div className="card-body" style={{ height:280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats.timeline} margin={{ left:0, right:20, top:5, bottom:30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9"/>
                <XAxis dataKey="date" tick={{ fontSize:10 }} angle={-35} textAnchor="end"/>
                <YAxis tick={{ fontSize:11 }} allowDecimals={false}/>
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="count" name="Rapports"
                  stroke="#1E3A8A" strokeWidth={2} dot={{ r:5, fill:'#1E3A8A' }}/>
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Companies table */}
      <div className="card">
        <div className="card-header">
          <h3>📋 Entreprises analysées ({filtered.length})</h3>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filtrer..."
            style={{ border:'1px solid #e2e8f0', borderRadius:6,
              padding:'4px 10px', fontSize:12, width:160 }}/>
        </div>
        <div style={{ overflowX:'auto' }}>
          <table style={{ width:'100%', fontSize:12, borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ background:'#f8fafc', borderBottom:'2px solid #e2e8f0' }}>
                {['Entreprise','Gouvernorat','Secteur','Régime','Verdict','Date'].map(h => (
                  <th key={h} style={{ padding:'8px 12px', textAlign:'left', fontSize:11,
                    fontWeight:700, color:'#64748b', whiteSpace:'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr key={i} style={{ borderBottom:'1px solid #f1f5f9',
                  background: i%2===0 ? '#fff' : '#f8fafc' }}>
                  <td style={{ padding:'8px 12px', fontWeight:600, color:'#1E3A8A' }}>
                    {c.denomination || c.company_name}
                  </td>
                  <td style={{ padding:'8px 12px', color:'#374151' }}>{c.gouvernorat || '—'}</td>
                  <td style={{ padding:'8px 12px', color:'#374151', maxWidth:180,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {c.secteur || '—'}
                  </td>
                  <td style={{ padding:'8px 12px', color:'#64748b', fontSize:11 }}>
                    {c.regime || '—'}
                  </td>
                  <td style={{ padding:'8px 12px' }}>
                    <span style={{
                      padding:'2px 8px', borderRadius:12, fontSize:11, fontWeight:600,
                      background: (VERDICT_COLORS[c.verdict] || '#94a3b8') + '22',
                      color: VERDICT_COLORS[c.verdict] || '#64748b'
                    }}>{c.verdict || '—'}</span>
                  </td>
                  <td style={{ padding:'8px 12px', color:'#94a3b8', whiteSpace:'nowrap' }}>
                    {c.generated_at ? fmtDate(c.generated_at) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
