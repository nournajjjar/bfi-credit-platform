import { useState, useEffect, useRef } from 'react'
import Login from './login'
import { api } from './api'
import './App.css'
import StressTab from './StressTab'
import StrategyTab from './StrategyTab'
import ForecastTab from './ForecastTab'
import DashboardTab from './dashboardTab'

const fmtDate    = d => new Date(d).toLocaleString('fr-FR', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })
const fmtJson    = o => JSON.stringify(o, null, 2).slice(0, 2000)
const scoreClass = s => `sec-score s${Math.min(5, Math.max(1, Math.round(s || 0)))}`

// ── Shared authenticated download helper ────────────────────────────────
// Fetches the file with the JWT Authorization header attached, then
// triggers a browser download via a Blob URL. A plain <a href=...> link
// cannot carry the Authorization header, which is why direct navigation
// to these endpoints returns "Non authentifie".
async function downloadWithAuth(url, filename) {
  const token = localStorage.getItem('bfi_token')
  const res = await fetch(url, {
    headers: { Authorization: 'Bearer ' + token }
  })
  if (!res.ok) {
    throw new Error(`Echec du telechargement (${res.status})`)
  }
  const blob = await res.blob()
  const blobUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(blobUrl)
}

// ======================================================================
// ONGLET 1 - GENERATION DE RAPPORT
// ======================================================================
function GenerateTab({ globalJob, globalJobId, globalPolling, onJobStart }) {
  const [query,     setQuery]     = useState('')
  const [results,   setResults]   = useState([])
  const [searching, setSearching] = useState(false)
  const [selected,  setSelected]  = useState(null)
  const [pdfs,      setPdfs]      = useState([])
  const [form,      setForm]      = useState({
    company_name:'', gouvernorat:'', label_secteur:'', source_table:'',
    activites:'', produits:'', capital:'', emploi:'', regime:'',
    entree_production:'', url:''
  })
  const [alert, setAlert] = useState(null)
  const fileRef = useRef()

  const job     = globalJob
  const jobId   = globalJobId
  const polling = globalPolling

  function showAlert(msg, type='blue') { setAlert({ msg, type }); setTimeout(() => setAlert(null), 6000) }

  async function search() {
    if (!query.trim()) return
    setSearching(true); setResults([])
    try {
      const data = await api.searchCompanies(query)
      setResults(data.companies || [])
      if (!data.companies?.length) showAlert('Aucune entreprise trouvee.', 'amber')
    } catch (e) { showAlert('Erreur recherche : ' + e.message, 'red') }
    finally { setSearching(false) }
  }

  function pick(c) {
    setSelected(c)
    setForm({
      company_name:c.denomination||'', gouvernorat:c.gouvernorat||'',
      label_secteur:c.label_secteur||'', source_table:c.source_table||'',
      activites:c.activites||'', produits:c.produits||'',
      capital:c.capital||'', emploi:c.emploi||'',
      regime:c.regime||'', entree_production:c.entree_production||'', url:c.url||''
    })
  }

  function addPdfs(files) {
    const arr = Array.from(files).filter(f => f.name.endsWith('.pdf'))
    setPdfs(prev => [...prev, ...arr].slice(0, 3))
    if (!form.company_name && arr.length > 0) {
      const name = arr[0].name.replace('.pdf','').replace(/[_-]/g,' ').toUpperCase().trim()
      setForm(f => ({ ...f, company_name: name }))
    }
  }

  function removePdf(i) { setPdfs(prev => prev.filter((_, idx) => idx !== i)) }

  async function generate() {
    if (!form.company_name.trim()) { showAlert("Nom d'entreprise requis.", 'amber'); return }
    try {
      let data
      if (pdfs.length > 0) {
        const fd = new FormData()
        if (pdfs[0]) fd.append('file1', pdfs[0])
        if (pdfs[1]) fd.append('file2', pdfs[1])
        if (pdfs[2]) fd.append('file3', pdfs[2])
        const queryParams = {}
        Object.entries(form).forEach(([k, v]) => { if (v) queryParams[k] = v })
        data = await api.generateReportWithPdf(fd, queryParams)
      } else {
        data = await api.generateReport(form)
      }
      onJobStart(data.job_id, form.company_name)
      showAlert(`Tache demarree : ${data.job_id}`, 'green')
    } catch (e) { showAlert('Erreur : ' + (e.response?.data?.detail || e.message), 'red') }
  }

  async function downloadDocx() {
    if (!jobId) return
    try {
      await downloadWithAuth(
        api.downloadJobDocx(jobId),
        `rapport_${form.company_name.replace(/\s+/g,'_')}.docx`
      )
    } catch (e) {
      showAlert('Erreur telechargement : ' + e.message, 'red')
    }
  }

  const pct=job?.progress||0; const isDone=job?.status==='completed'; const isFail=job?.status==='failed'

  return (
    <div className="two-col">
      <div className="left-col">
        <div className="section-label">Recherche d'entreprise</div>
        <div style={{ padding:'0 16px 12px' }}>
          <div style={{ display:'flex', gap:8 }}>
            <input style={{ flex:1, border:'1px solid #e2e8f0', borderRadius:7, padding:'8px 11px', fontSize:13 }}
              value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==='Enter'&&search()}
              placeholder="Nom de l'entreprise..."/>
            <button className="btn btn-primary" onClick={search} disabled={searching}>
              {searching?<span className="spinner"/>:'\u{1F50D}'}
            </button>
          </div>
        </div>
        {results.length>0&&(
          <>
            <div className="section-label">Resultats ({results.length})</div>
            {results.map((c,i)=>(
              <div key={i} className={`search-result ${selected?.id===c.id?'selected':''}`} onClick={()=>pick(c)}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <div className="sr-name">{c.denomination}</div>
                  <div className="sr-score">{c.match_score}%</div>
                </div>
                <div className="sr-meta">{c.gouvernorat} - {c.label_secteur}</div>
                <div className="sr-meta">{c.activites?.slice(0,60)}...</div>
              </div>
            ))}
          </>
        )}
        <div className="section-label">Informations entreprise</div>
        <div style={{ padding:'0 16px 16px' }}>
          {alert&&<div className={`alert alert-${alert.type}`}>{alert.msg}</div>}
          <div className="field"><label>Denomination *</label><input value={form.company_name} onChange={e=>setForm(f=>({...f,company_name:e.target.value}))} placeholder="Denomination sociale"/></div>
          <div className="field-row">
            <div className="field"><label>Gouvernorat</label><input value={form.gouvernorat} onChange={e=>setForm(f=>({...f,gouvernorat:e.target.value}))}/></div>
            <div className="field"><label>Secteur</label><input value={form.label_secteur} onChange={e=>setForm(f=>({...f,label_secteur:e.target.value}))}/></div>
          </div>
          <div className="field-row">
            <div className="field"><label>Capital (DT)</label><input value={form.capital} onChange={e=>setForm(f=>({...f,capital:e.target.value}))}/></div>
            <div className="field"><label>Effectif</label><input value={form.emploi} onChange={e=>setForm(f=>({...f,emploi:e.target.value}))}/></div>
          </div>
          <div className="field-row">
            <div className="field"><label>Regime</label><input value={form.regime} onChange={e=>setForm(f=>({...f,regime:e.target.value}))}/></div>
            <div className="field"><label>Entree en production</label><input value={form.entree_production} onChange={e=>setForm(f=>({...f,entree_production:e.target.value}))}/></div>
          </div>
          <div className="field"><label>Activites</label><input value={form.activites} onChange={e=>setForm(f=>({...f,activites:e.target.value}))}/></div>
          <div className="field"><label>Produits</label><input value={form.produits} onChange={e=>setForm(f=>({...f,produits:e.target.value}))}/></div>
          <div className="field"><label>Site web</label><input value={form.url} onChange={e=>setForm(f=>({...f,url:e.target.value}))}/></div>
        </div>
      </div>
      <div className="right-col">
        <div className="card">
          <div className="card-header"><h3>Documents PDF (optionnel, max 3)</h3></div>
          <div className="card-body">
            <div className="pdf-zone" onClick={()=>fileRef.current?.click()}
              onDragOver={e=>{e.preventDefault();e.currentTarget.classList.add('drag')}}
              onDragLeave={e=>e.currentTarget.classList.remove('drag')}
              onDrop={e=>{e.preventDefault();e.currentTarget.classList.remove('drag');addPdfs(e.dataTransfer.files)}}>
              <div style={{ fontSize:28 }}>{'\u{1F4CE}'}</div>
              <p>Glisser-deposer ou cliquer pour ajouter des PDFs</p>
              <p style={{ marginTop:4, fontSize:11, color:'#94a3b8' }}>Bilan, CPC, Annexes... (max 3 fichiers, 50 Mo)</p>
            </div>
            <input ref={fileRef} type="file" accept=".pdf" multiple style={{ display:'none' }} onChange={e=>addPdfs(e.target.files)}/>
            {pdfs.map((f,i)=>(
              <div key={i} className="pdf-file">
                <span>{'\u{1F4C4}'}</span>
                <span className="pdf-file-name">{f.name}</span>
                <span style={{ fontSize:11, color:'#94a3b8' }}>{(f.size/1024/1024).toFixed(1)} Mo</span>
                <button className="pdf-remove" onClick={()=>removePdf(i)}>{'\u2715'}</button>
              </div>
            ))}
            {pdfs.length>0&&<div style={{ fontSize:11, color:'#94a3b8', marginTop:6 }}>{pdfs.length}/3 fichier(s)</div>}
          </div>
        </div>
        <button className="btn btn-primary btn-full" style={{ marginBottom:16, padding:12, fontSize:14 }} onClick={generate} disabled={polling}>
          {polling?<><span className="spinner"/> Generation en cours...</>:`Generer le rapport${pdfs.length>0?` (${pdfs.length} PDF)`:''}`}
        </button>
        {(job||jobId)&&(
          <div className="card">
            <div className="card-header">
              <h3>Tache : <code style={{ fontSize:11 }}>{jobId?.slice(0,16)}...</code></h3>
              <span className={`chip ${isDone?'chip-green':isFail?'chip-red':polling?'chip-blue':'chip-gray'}`}>{job?.status||'demarree'}</span>
            </div>
            <div className="card-body">
              {job&&(<>
                <div style={{ fontSize:13, marginBottom:8, color:'#374151' }}>{job.message}</div>
                <div className="progress-wrap"><div className={`progress-bar ${isDone?'done':isFail?'fail':''}`} style={{ width:`${pct}%` }}/></div>
                <div style={{ fontSize:11, color:'#94a3b8', marginBottom:12 }}>{pct}%</div>
              </>)}
              {polling&&!isDone&&!isFail&&<div className="alert alert-blue"><span className="spinner"/> &nbsp;Mise a jour toutes les 2,5 s...</div>}
              {isDone&&(<>
                <div className="alert alert-green">Rapport genere avec succes !</div>
                {job.result?.report_id&&(
                  <div className="alert alert-blue" style={{ marginTop:8 }}>
                    Identifiant du rapport :<br/>
                    <code style={{ fontSize:11, wordBreak:'break-all' }}>{job.result.report_id}</code>
                  </div>
                )}
                <button className="btn btn-green btn-full" style={{ marginTop:12 }} onClick={downloadDocx}>Telecharger le rapport DOCX</button>
                {job.result&&(<div style={{ marginTop:12 }}>
                  <div style={{ fontSize:11, fontWeight:700, color:'#94a3b8', marginBottom:6 }}>DETAILS</div>
                  <pre>{fmtJson({ docx_path:job.result.docx_path, pdf_count:job.result.pdf_count, report_id:job.result.report_id })}</pre>
                </div>)}
              </>)}
              {isFail&&<div className="alert alert-red">{job.error||'Erreur inconnue'}</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ======================================================================
// ONGLET 2 - SUIVI DES TACHES
// ======================================================================
function JobsTab() {
  const [jobs,setJobs]=useState([])
  const [selected,setSelected]=useState(null)
  const [loading,setLoading]=useState(false)
  const [autoRefresh,setAutoRefresh]=useState(false)
  const [alert,setAlert]=useState(null)
  const timerRef=useRef()

  function showAlert(msg,type='blue'){setAlert({msg,type});setTimeout(()=>setAlert(null),4000)}
  async function fetchJobs(){setLoading(true);try{const d=await api.listJobs();setJobs(Array.isArray(d)?d:[])}catch{setJobs([])}finally{setLoading(false)}}
  async function fetchOne(id){try{setSelected(await api.getJob(id))}catch(e){showAlert('Erreur : '+e.message,'red')}}
  useEffect(()=>{fetchJobs()},[])
  useEffect(()=>{if(autoRefresh){timerRef.current=setInterval(fetchJobs,3000)}else{clearInterval(timerRef.current)}return()=>clearInterval(timerRef.current)},[autoRefresh])

  async function downloadDocx(jobId,jobTitle){
    try {
      await downloadWithAuth(
        api.downloadJobDocx(jobId),
        `rapport_${(jobTitle||jobId).replace(/\s+/g,'_')}.docx`
      )
    } catch (e) {
      showAlert('Erreur telechargement : ' + e.message, 'red')
    }
  }
  const statusChip=s=>({completed:'chip-green',failed:'chip-red',running:'chip-blue',pending:'chip-amber'}[s]||'chip-gray')
  const statusLabel=s=>({completed:'termine',failed:'echoue',running:'en cours',pending:'en attente'}[s]||s)

  return (
    <div className="two-col">
      <div className="left-col">
        <div className="section-label" style={{ display:'flex', alignItems:'center', justifyContent:'space-between', paddingRight:16 }}>
          <span>Taches ({jobs.length})</span>
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <label style={{ fontSize:11, color:'#64748b', display:'flex', alignItems:'center', gap:4 }}>
              <input type="checkbox" checked={autoRefresh} onChange={e=>setAutoRefresh(e.target.checked)}/> Auto (3s)
            </label>
            <button className="btn btn-sm" onClick={fetchJobs} disabled={loading}>{loading?<span className="spinner"/>:'\u21BB'}</button>
          </div>
        </div>
        {alert&&<div style={{ padding:'0 16px 8px' }}><div className={`alert alert-${alert.type}`}>{alert.msg}</div></div>}
        {jobs.length===0
          ?<div className="empty-hint"><div className="icon">{'\u{1F4ED}'}</div><h3>Aucune tache</h3><p>Generez un rapport pour commencer.</p></div>
          :jobs.map(j=>{const id=j.job_id||j.id;return(
            <div key={id} className={`job-row ${selected?.job_id===id?'active':''}`} onClick={()=>fetchOne(id)}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:8 }}>
                <div className="job-title" style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{j.title||j.message||id}</div>
                <span className={`chip ${statusChip(j.status)}`}>{statusLabel(j.status)}</span>
              </div>
              <div className="job-meta"><span>{j.progress||0}%</span>{j.created_at&&<span>{fmtDate(j.created_at)}</span>}</div>
              <div className="progress-wrap" style={{ margin:'4px 0 0' }}>
                <div className={`progress-bar ${j.status==='completed'?'done':j.status==='failed'?'fail':''}`} style={{ width:`${j.progress||0}%` }}/>
              </div>
            </div>
          )})
        }
      </div>
      <div className="right-col">
        {!selected
          ?<div className="empty-hint"><div className="icon">{'\u{1F448}'}</div><h3>Selectionnez une tache</h3><p>Cliquez sur une tache pour voir les details.</p></div>
          :<div className="card">
            <div className="card-header">
              <h3 style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:300 }}>{selected.title||selected.job_id}</h3>
              <span className={`chip ${statusChip(selected.status)}`}>{statusLabel(selected.status)}</span>
            </div>
            <div className="card-body">
              <div style={{ fontSize:13, marginBottom:8 }}>{selected.message}</div>
              <div className="progress-wrap">
                <div className={`progress-bar ${selected.status==='completed'?'done':selected.status==='failed'?'fail':''}`} style={{ width:`${selected.progress||0}%` }}/>
              </div>
              <div style={{ fontSize:11, color:'#94a3b8', marginBottom:12 }}>{selected.progress||0}%</div>
              {selected.status==='failed'&&<div className="alert alert-red">{selected.error}</div>}
              {selected.status==='completed'&&(<>
                <div className="alert alert-green">Rapport genere !</div>
                {selected.result?.report_id&&(
                  <div className="alert alert-blue" style={{ marginTop:8 }}>
                    Identifiant : <code style={{ fontSize:11 }}>{selected.result.report_id}</code>
                  </div>
                )}
                <button className="btn btn-green btn-full" style={{ marginTop:10 }} onClick={()=>downloadDocx(selected.job_id||selected.id,selected.title)}>
                  Telecharger DOCX
                </button>
              </>)}
              <button className="btn btn-sm" style={{ marginTop:12 }} onClick={()=>fetchOne(selected.job_id||selected.id)}>Actualiser</button>
              {selected.result&&(<div style={{ marginTop:12 }}>
                <div style={{ fontSize:11, fontWeight:700, color:'#94a3b8', marginBottom:6 }}>RESULTAT</div>
                <pre>{fmtJson(selected.result)}</pre>
              </div>)}
            </div>
          </div>
        }
      </div>
    </div>
  )
}

// ======================================================================
// ONGLET 3 - REVISION / CHATBOT
// ======================================================================
function RefinementTab() {
  const fmtDate2 = d => d ? new Date(d).toLocaleDateString('fr-FR') : ''
  const [reports,    setReports]    = useState([])
  const [report,     setReport]     = useState(null)
  const [sections,   setSections]   = useState([])
  const [section,    setSection]    = useState(null)
  const [messages,   setMessages]   = useState([{role:'bot',text:"Bonjour ! Je suis votre assistant de revision. Selectionnez un rapport puis une section pour commencer, ou posez directement une question sur le rapport.",id:0}])
  const [input,      setInput]      = useState('')
  const [loading,    setLoading]    = useState(false)
  const [comparison, setComparison] = useState(null)
  const [history,    setHistory]    = useState([])
  const [showHist,   setShowHist]   = useState(false)
  const [pending,    setPending]    = useState({})
  const [chatHist,   setChatHist]   = useState([])
  const [generating, setGenerating] = useState(false)
  const [alert,      setAlert]      = useState(null)
  const endRef = useRef()

  function showAlert(msg, type='green') { setAlert({ msg, type }); setTimeout(() => setAlert(null), 5000) }
  function addMsg(role, text) { setMessages(p => [...p, { role, text, id:Date.now() }]) }
  function replaceLastMsg(text) { setMessages(p => [...p.slice(0,-1), { ...p[p.length-1], text }]) }

  useEffect(() => { api.getReports().then(setReports).catch(() => {}) }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  // -- Delete report --------------------------------------------------
  async function deleteReport(reportId) {
    if (!window.confirm('Supprimer ce rapport definitivement ?')) return
    try {
      await api.deleteReport(reportId)
      setReports(rs => rs.filter(r => r.report_id !== reportId))
      if (report?.report_id === reportId) {
        setReport(null); setSection(null); setSections([])
        setMessages([{ role:'bot', text:'Rapport supprime.', id:Date.now() }])
      }
    } catch(e) {
      showAlert('Erreur suppression : ' + (e.response?.data?.detail || e.message), 'red')
    }
  }

  // -- Select report ----------------------------------------------------
  async function selectReport(r) {
    setReport(r); setSection(null); setComparison(null)
    setShowHist(false); setChatHist([]); setPending({})
    setMessages([{ role:'bot', text:`Rapport charge : ${r.company_name}\nSelectionnez une section a reviser ou posez une question sur ce rapport.`, id:Date.now() }])
    try {
      const d = await api.getSections(r.report_id); setSections(d.sections || [])
    } catch(e) { showAlert('Erreur sections : ' + (e.response?.data?.detail || e.message), 'red'); return }
    try {
      const p = await api.getPendingChanges(r.report_id); setPending(p.pending_changes || {})
    } catch { setPending({}) }
  }

  async function selectSection(s) {
    setSection(s); setComparison(null); setShowHist(false); setChatHist([])
    setMessages([{ role:'bot', text:`Section : ${s.title}\nScore actuel : ${s.score??'?'}/5 - Version ${s.current_version}\n\nComment puis-je ameliorer cette section ? Decrivez les modifications souhaitees ou posez une question.`, id:Date.now() }])
    try { const d = await api.getHistory(report.report_id, s.section_id); setHistory(d.versions || []) } catch {}
  }

  async function send() {
    if (!input.trim() || loading) return
    if (!report) { showAlert("Veuillez d'abord selectionner un rapport.", 'amber'); return }
    const instr = input.trim(); setInput('')
    addMsg('user', instr); addMsg('bot', 'Analyse en cours...')
    setLoading(true)
    try {
      const isQ = !section || /[?]$/.test(instr) || /^(qu|comment|pourquoi|quand|quel|est-ce|dis|explique|donne|combien|ou)/i.test(instr)
      if (isQ) {
        const r = await api.askQuestion(report.report_id, instr, section?.section_id)
        replaceLastMsg(r.answer)
      } else {
        const r = await api.refineSection(report.report_id, section.section_id, instr, chatHist)
        setChatHist(p => [...p, { role:'user', content:instr }, { role:'assistant', content:r.changes_summary }])
        replaceLastMsg(`Version ${r.new_version} generee !\nScore : ${r.score_before}/5 -> ${r.score_after}/5\n\n${r.changes_summary}\n\nSouhaitez-vous appliquer cette version ?`)
        setComparison(r)
      }
    } catch(e) { replaceLastMsg(`Erreur: ${e.response?.data?.detail || e.message}`) }
    finally { setLoading(false) }
  }

  async function apply() {
    try {
      await api.applyVersion(report.report_id, section.section_id, comparison.new_version)
      addMsg('bot', `Version ${comparison.new_version} appliquee avec succes !`)
      setComparison(null)
      const [sec, pend] = await Promise.all([api.getSections(report.report_id), api.getPendingChanges(report.report_id)])
      setSections(sec.sections || []); setPending(pend.pending_changes || {})
    } catch(e) { showAlert(e.response?.data?.detail || e.message, 'red') }
  }

  async function revert() {
    if (!window.confirm('Reinitialiser cette section a la version originale ?')) return
    try {
      await api.revertSection(report.report_id, section.section_id)
      addMsg('bot', 'Section reinitialisee a la version originale.')
      setComparison(null)
      const sec = await api.getSections(report.report_id); setSections(sec.sections || [])
    } catch(e) { showAlert(e.message, 'red') }
  }

  async function toggleHist() {
    if (showHist) { setShowHist(false); return }
    try { const d = await api.getHistory(report.report_id, section.section_id); setHistory(d.versions || []); setShowHist(true) }
    catch { showAlert("Erreur lors du chargement de l'historique.", 'red') }
  }

  async function activateVer(v) {
    try {
      await api.applyVersion(report.report_id, section.section_id, v)
      showAlert(`Version ${v} activee.`)
      const [h, s] = await Promise.all([api.getHistory(report.report_id, section.section_id), api.getSections(report.report_id)])
      setHistory(h.versions || []); setSections(s.sections || [])
    } catch { showAlert('Erreur.', 'red') }
  }

  async function generateDocx() {
    setGenerating(true)
    try {
      await api.generateDocx(report.report_id)
      await downloadWithAuth(
        api.downloadRefinedDocx(report.report_id),
        `rapport_${report.company_name.replace(/\s+/g,'_')}_revise.docx`
      )
      showAlert('Rapport DOCX telecharge !')
    } catch(e) { showAlert(e.response?.data?.detail || e.message, 'red') }
    finally { setGenerating(false) }
  }

  const hasPending = Object.keys(pending).length > 0

  return (
    <div className="chat-wrap" style={{ padding:16 }}>
      <div className="chat-sidebar">
        {/* Reports list */}
        <div className="card" style={{ maxHeight:'220px', overflowY:'auto' }}>
          <div className="card-header" style={{ position:'sticky', top:0, background:'#fff', zIndex:1 }}>
            <h3>Rapports ({reports.length})</h3>
            <button className="btn btn-sm btn-ghost" onClick={() => api.getReports().then(setReports)}>{'\u21BB'}</button>
          </div>
          {reports.length === 0
            ? <div style={{ padding:'10px 14px', fontSize:12, color:'#94a3b8' }}>Aucun rapport disponible.</div>
            : reports.map(r => (
              <div key={r.report_id} className={`rep-item ${report?.report_id===r.report_id?'active':''}`}
                onClick={() => selectReport(r)} style={{ position:'relative' }}>
                <div className="rep-name" style={{ fontSize:10, color:'#94a3b8' }}>{r.report_id?.slice(0,8)}...</div>
                <div className="rep-name">{r.company_name}</div>
                <div className="rep-date">{fmtDate2(r.generated_at)} - v{r.version}</div>
                <button
                  onClick={e => { e.stopPropagation(); deleteReport(r.report_id) }}
                  style={{ position:'absolute', top:4, right:4, border:'none', background:'none',
                    cursor:'pointer', color:'#dc2626', fontSize:13, padding:'0 3px', lineHeight:1 }}
                  title="Supprimer ce rapport">{'\u2715'}</button>
              </div>
            ))
          }
        </div>

        {/* Sections list */}
        {sections.length > 0 && (
          <div className="card" style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
            <div className="card-header"><h3>Sections ({sections.length})</h3></div>
            <div style={{ padding:'8px', maxHeight:'400px', overflowY:'auto', paddingBottom:'12px' }}>
              {sections.map(s => (
                <div key={s.section_id} className={`sec-item ${section?.section_id===s.section_id?'active':''}`}
                  onClick={() => selectSection(s)}>
                  <span style={{ fontSize:11, flex:1 }}>{s.title}</span>
                  {s.has_changes && <span className="dot-modified"/>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Pending changes */}
        {hasPending && (
          <div className="card">
            <div className="card-header" style={{ background:'#fffbeb' }}>
              <h3 style={{ color:'#92400e' }}>En attente ({Object.keys(pending).length})</h3>
            </div>
            <div style={{ padding:'8px 12px' }}>
              {Object.entries(pending).map(([sid, c]) => (
                <div key={sid} style={{ display:'flex', gap:6, padding:'4px 0', fontSize:12, borderBottom:'1px solid #fef3c7' }}>
                  <span className="chip chip-green" style={{ fontSize:10 }}>v{c.active_version}</span>
                  <span style={{ flex:1 }}>{c.section_title}</span>
                </div>
              ))}
              <button className="btn btn-green btn-full btn-sm" style={{ marginTop:8 }} onClick={generateDocx} disabled={generating}>
                {generating ? <><span className="spinner"/> Generation...</> : 'Generer le rapport DOCX'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Chat main */}
      <div className="chat-main">
        <div className="chat-topbar">
          <div>
            <div style={{ fontSize:11, color:'#94a3b8' }}>{report?.company_name || 'Aucun rapport selectionne'}</div>
            <h3>{section?.title || 'Assistant de revision'}</h3>
          </div>
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            {section && <>
              <button className="btn btn-sm" onClick={toggleHist}>{showHist ? 'Fermer' : 'Historique'}</button>
              <button className="btn btn-sm" onClick={revert}>Reinitialiser</button>
            </>}
            {alert && <div className={`alert alert-${alert.type}`} style={{ margin:0, padding:'5px 10px', fontSize:12 }}>{alert.msg}</div>}
          </div>
        </div>

        {showHist && (
          <div style={{ padding:'10px 16px', borderBottom:'1px solid #f1f5f9', background:'#f8fafc' }}>
            <div style={{ fontSize:11, fontWeight:700, color:'#94a3b8', marginBottom:6 }}>HISTORIQUE DES VERSIONS</div>
            {history.map(v => (
              <div key={v.version} className="hist-row">
                <span className={`v-badge ${v.is_active?'on':''}`}>v{v.version}</span>
                <span style={{ flex:1, fontSize:12 }}>{v.refinement_instruction || 'Version originale'}</span>
                <span style={{ fontSize:11, color:'#94a3b8' }}>{v.score}/5</span>
                {!v.is_active
                  ? <button className="btn btn-sm" onClick={() => activateVer(v.version)}>Activer</button>
                  : <span className="chip chip-green" style={{ fontSize:10 }}>Active</span>}
              </div>
            ))}
          </div>
        )}

        <div className="chat-messages">
          {messages.map(m => (
            <div key={m.id} className={`msg ${m.role}`}>
              <div className="avatar">{m.role === 'bot' ? '\u{1F916}' : '\u{1F464}'}</div>
              <div className="bubble" style={{ whiteSpace:'pre-wrap' }}>{m.text}</div>
            </div>
          ))}
          {comparison && (
            <div style={{ display:'flex', gap:8, paddingLeft:38, flexWrap:'wrap' }}>
              <button className="btn btn-green" onClick={apply}>Appliquer la version {comparison.new_version}</button>
              <button className="btn" onClick={() => setComparison(null)}>Rejeter</button>
            </div>
          )}
          <div ref={endRef}/>
        </div>

        <div className="chat-input-bar">
          <textarea rows={2} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={loading}
            placeholder={!report ? 'Selectionnez un rapport pour commencer...' : !section ? 'Posez une question sur le rapport (ex : Quel est le CA ?)...' : 'Instruction de revision ou question... (Entree pour envoyer)'}
          />
          <button className="btn btn-primary" onClick={send} disabled={loading || !input.trim()}>
            {loading ? <span className="spinner"/> : 'Envoyer'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ======================================================================
// APPLICATION PRINCIPALE
// ======================================================================
export default function App() {
  const [user, setUser] = useState(() => {
    const t = localStorage.getItem('bfi_token')
    const u = localStorage.getItem('bfi_user')
    return t ? { token:t, username:u } : null
  })

  function handleLogout() {
    localStorage.removeItem('bfi_token')
    localStorage.removeItem('bfi_user')
    localStorage.removeItem('bfi_job_id')
    localStorage.removeItem('bfi_job_company')
    setUser(null)
    window.location.reload()
  }

  const [tab,       setTab]       = useState('dashboard')
  const [backendOk, setBackendOk] = useState(null)
  const [globalJobId,   setGlobalJobId]   = useState(() => localStorage.getItem('bfi_job_id') || null)
  const [globalJob,     setGlobalJob]     = useState(null)
  const [globalPolling, setGlobalPolling] = useState(false)
  const [globalCompany, setGlobalCompany] = useState(() => localStorage.getItem('bfi_job_company') || '')
  const pollRef = useRef()

  useEffect(() => {
    fetch('http://localhost:8000/health').then(() => setBackendOk(true)).catch(() => setBackendOk(false))
  }, [])

  useEffect(() => {
    const savedId = localStorage.getItem('bfi_job_id')
    if (savedId) startPolling(savedId)
  }, [])

  function startPolling(id) {
    setGlobalPolling(true)
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const j = await api.getJob(id)
        setGlobalJob(j)
        if (j.status === 'completed' || j.status === 'failed') {
          clearInterval(pollRef.current)
          setGlobalPolling(false)
          localStorage.removeItem('bfi_job_id')
          localStorage.removeItem('bfi_job_company')
        }
      } catch {
        clearInterval(pollRef.current)
        setGlobalPolling(false)
        setGlobalJobId(null)
        setGlobalJob(null)
        localStorage.removeItem('bfi_job_id')
        localStorage.removeItem('bfi_job_company')
      }
    }, 2500)
  }

  function handleJobStart(jobId, companyName) {
    setGlobalJobId(jobId)
    setGlobalJob(null)
    setGlobalCompany(companyName)
    localStorage.setItem('bfi_job_id', jobId)
    localStorage.setItem('bfi_job_company', companyName)
    startPolling(jobId)
  }

  useEffect(() => () => clearInterval(pollRef.current), [])

  const pct     = globalJob?.progress || 0
  const isDone  = globalJob?.status === 'completed'
  const isFail  = globalJob?.status === 'failed'
  const showBar = globalJobId && (globalPolling || isDone || isFail)

  if (!user) return <Login onLogin={setUser}/>

  return (
    <div className="app">
      <nav className="nav">
        <div className="nav-brand" style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:2 }}>
          <span style={{ fontSize:12, fontWeight:700, letterSpacing:2, color:'#ffffff' }}>
            <span style={{ color:'#378ADD' }}>BFI</span> <span style={{ color:'#ffffff' }}>Credit</span>
          </span>
        </div>
        {[
          ['generate',  '🔍 Génération de rapport'],
          ['jobs',      '⚙️ Suivi des tâches'],
          ['refine',    '🤖 Chatbot'],
          ['stress',    '⚡ Test de résistance'],
          ['strategy',  '💡 Stratégies'],
          ['forecast',  '📈 Prévisions'],
          ['dashboard', '📊 Dashboard'],

        ].map(([key, label]) => (
          <button key={key} className={`nav-tab ${tab===key?'active':''}`} onClick={() => setTab(key)}>{label}</button>
        ))}
        <span style={{ fontSize:12, color:'#94a3b8', marginRight:8 }}>{user?.username}</span>
        <button onClick={handleLogout} style={{ fontSize:11, padding:'4px 10px', background:'#ef4444', color:'#fff', border:'none', borderRadius:6, cursor:'pointer', marginRight:8 }}>
          Deconnexion
        </button>
        <div className={`nav-status ${backendOk===true?'ok':''}`}>
          {backendOk===null ? 'Connexion...' : backendOk ? 'Serveur actif' : 'Serveur hors ligne'}
        </div>
      </nav>

      {showBar && (
        <div style={{
          background: isDone ? '#f0fdf4' : isFail ? '#fef2f2' : '#eff6ff',
          borderBottom: `2px solid ${isDone ? '#16a34a' : isFail ? '#dc2626' : '#378ADD'}`,
          padding: '6px 20px', display:'flex', alignItems:'center', gap:12,
        }}>
          <span style={{ fontSize:13, fontWeight:500, color: isDone ? '#16a34a' : isFail ? '#dc2626' : '#1e40af' }}>
            {isDone ? 'OK' : isFail ? 'X' : <span className="spinner" style={{ display:'inline-block' }}/>}
            &nbsp;{isDone ? 'Rapport genere' : isFail ? 'Echec' : 'Generation en cours'}
            {globalCompany ? ` - ${globalCompany}` : ''}
          </span>
          <div style={{ flex:1, height:5, background:'#e2e8f0', borderRadius:3 }}>
            <div style={{ width:`${pct}%`, height:'100%', borderRadius:3,
              background: isDone ? '#16a34a' : isFail ? '#dc2626' : '#378ADD',
              transition:'width 0.5s ease' }}/>
          </div>
          <span style={{ fontSize:12, color:'#64748b', minWidth:32 }}>{pct}%</span>
          <span style={{ fontSize:11, color:'#94a3b8', maxWidth:300, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {globalJob?.message || ''}
          </span>
          {(isDone || isFail) && (
            <button style={{ fontSize:11, background:'none', border:'none', cursor:'pointer', color:'#94a3b8' }}
              onClick={() => { setGlobalJobId(null); setGlobalJob(null); localStorage.removeItem('bfi_job_id') }}>
              {'\u2715'}
            </button>
          )}
        </div>
      )}

      <div className="page">
        {tab==='generate' && <GenerateTab globalJob={globalJob} globalJobId={globalJobId} globalPolling={globalPolling} onJobStart={handleJobStart}/>}
        {tab==='jobs'     && <JobsTab/>}
        {tab==='refine'   && <RefinementTab/>}
        {tab==='stress'   && <StressTab/>}
        {tab==='strategy' && <StrategyTab/>}
        {tab==='forecast' && <ForecastTab/>}
        {tab==='dashboard' && <DashboardTab/>}

      </div>
    </div>
  )
}
