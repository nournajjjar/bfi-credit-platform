import { useState } from "react"

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleLogin() {
    if (!username || !password) { setError("Veuillez remplir tous les champs."); return }
    setLoading(true); setError(null)
    try {
      const resp = await fetch("http://localhost:8000/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      })
      const data = await resp.json()
      if (!resp.ok) { setError(data.detail || "Identifiants incorrects"); return }
      localStorage.setItem("bfi_token", data.access_token)
      localStorage.setItem("bfi_user", data.username)
      onLogin(data)
    } catch { setError("Impossible de contacter le serveur.") }
    finally { setLoading(false) }
  }

  return (
    <div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center",background:"linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%)"}}>
      <div style={{background:"#fff",borderRadius:16,padding:"40px 36px",width:360,boxShadow:"0 20px 60px rgba(0,0,0,0.3)"}}>
        <div style={{textAlign:"center",marginBottom:28}}>
          <div style={{fontSize:20,fontWeight:700,color:"#1e3a5f"}}>BFI <span style={{color:"#378ADD"}}>Credit</span></div>
          <div style={{fontSize:12,color:"#94a3b8",marginTop:4}}>Plateforme d analyse credit IA</div>
        </div>
        <div style={{marginBottom:16}}>
          <label style={{fontSize:12,fontWeight:600,color:"#374151",display:"block",marginBottom:6}}>Nom d utilisateur</label>
          <input value={username} onChange={e=>setUsername(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleLogin()} placeholder="admin"
            style={{width:"100%",padding:"10px 12px",border:"1px solid #e2e8f0",borderRadius:8,fontSize:14,boxSizing:"border-box"}}/>
        </div>
        <div style={{marginBottom:20}}>
          <label style={{fontSize:12,fontWeight:600,color:"#374151",display:"block",marginBottom:6}}>Mot de passe</label>
          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleLogin()} placeholder="..."
            style={{width:"100%",padding:"10px 12px",border:"1px solid #e2e8f0",borderRadius:8,fontSize:14,boxSizing:"border-box"}}/>
        </div>
        {error&&<div style={{background:"#fef2f2",border:"1px solid #fecaca",borderRadius:8,padding:"8px 12px",fontSize:13,color:"#dc2626",marginBottom:16}}>{error}</div>}
        <button onClick={handleLogin} disabled={loading}
          style={{width:"100%",padding:11,background:loading?"#94a3b8":"#378ADD",color:"#fff",border:"none",borderRadius:8,fontSize:14,fontWeight:600,cursor:"pointer"}}>
          {loading?"Connexion...":"Se connecter"}
        </button>
        <div style={{textAlign:"center",marginTop:16,fontSize:11,color:"#94a3b8"}}>Banque de Financement des Investissements</div>
      </div>
    </div>
  )
}