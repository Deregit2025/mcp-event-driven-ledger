import { useState } from "react"
import { api } from "../hooks/api"
import { Card, Err } from "../components/Card"
import { Play, Database, Table as TableIcon, TerminalSquare } from "lucide-react"

export default function LiveQuery() {
  const [query, setQuery] = useState("SELECT * FROM application_summary\\nORDER BY updated_at DESC\\nLIMIT 5;")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)

  const runQuery = async () => {
    setLoading(true)
    setErr(null)
    setResult(null)
    try {
      const res = await api.runLiveQuery({ query })
      if (res.error) setErr(res.error)
      else setResult(res)
    } catch (e) {
      setErr(e.message)
    }
    setLoading(false)
  }

  // Helper to render table
  const renderTable = (rows) => {
    if (!rows || rows.length === 0) return <div style={{padding:20,color:"var(--muted)",textAlign:"center"}}>0 rows returned</div>
    const keys = Object.keys(rows[0])
    return (
      <div style={{overflowX:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
          <thead>
            <tr style={{borderBottom:"1px solid var(--border)",background:"rgba(255,255,255,0.02)"}}>
              {keys.map(k => <th key={k} style={{padding:"10px 14px",textAlign:"left",color:"var(--purple)",fontWeight:500}}>{k}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{borderBottom:"1px solid var(--border)"}}>
                {keys.map(k => (
                  <td key={k} style={{padding:"10px 14px",color:"#e2e2e2",maxWidth:300,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                    {String(row[k])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="animate-in">
      <div style={{marginBottom:24}}>
        <h1 className="brand-font" style={{fontSize:28,fontWeight:700,color:"#fff",letterSpacing:"-0.02em"}}>Live CQRS Query</h1>
        <p style={{fontSize:14,color:"var(--muted)",marginTop:6}}>Execute Read-Only SQL queries against the Read Models (Projections)</p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 300px",gap:20,alignItems:"start"}}>
        <div>
          <Card title="Query Editor" className="p-0">
            <div style={{display:"flex",gap:10,alignItems:"center",padding:"12px 20px",borderBottom:"1px solid var(--border)",background:"rgba(0,0,0,0.2)"}}>
              <TerminalSquare size={16} color="var(--purple)" />
              <span style={{fontSize:13,color:"var(--muted)",fontWeight:500}}>PostgreSQL</span>
            </div>
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{
                width:"100%", height: 160, background:"rgba(5, 6, 15, 0.5)", border:"none", 
                padding:"20px", color:"#e2e2e2", fontSize:14, fontFamily:"monospace", resize:"vertical", outline:"none"
              }}
              spellCheck={false}
            />
            <div style={{padding:"16px 20px",borderTop:"1px solid var(--border)",display:"flex",justifyContent:"flex-end",background:"rgba(0,0,0,0.2)"}}>
              <button onClick={runQuery} disabled={loading} className="btn-primary" style={{display:"flex",alignItems:"center",gap:8}}>
                {loading ? <div style={{width:16,height:16,border:"2px solid #fff",borderTopColor:"transparent",borderRadius:"50%",animation:"spin 1s linear infinite"}}/> : <Play size={16} fill="currentColor" />}
                {loading ? "Executing..." : "Execute Query"}
              </button>
            </div>
          </Card>

          {err && <Err msg={err} />}
          
          {result && (
            <Card title="Query Results" subtitle={`${result.count} rows returned`}>
              {renderTable(result.rows)}
            </Card>
          )}
        </div>

        <div style={{display:"flex",flexDirection:"column",gap:16}}>
          <Card title="Available Read Models" style={{marginBottom:0}}>
            {[
              { name: "application_summary", desc: "Rolled up metrics per application" },
              { name: "agent_performance_ledger", desc: "Agent LLM cost, tokens and latency" },
              { name: "compliance_audit_view", desc: "Denormalized compliance state" }
            ].map(rm => (
              <div key={rm.name} style={{padding:"12px 0",borderBottom:"1px solid var(--border)"}}>
                <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}>
                  <Database size={12} color="var(--blue)" />
                  <span style={{fontSize:13,color:"#fff",fontWeight:500}}>{rm.name}</span>
                </div>
                <div style={{fontSize:11,color:"var(--muted)",lineHeight:1.4}}>{rm.desc}</div>
              </div>
            ))}
          </Card>
        </div>
      </div>
      <style>{`
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
