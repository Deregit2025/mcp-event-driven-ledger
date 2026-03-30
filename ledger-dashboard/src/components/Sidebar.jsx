import { LayoutDashboard, FileText, Shield, BarChart3, RefreshCw, Database, Play, Wrench, Lock, Activity, TerminalSquare } from "lucide-react"

const links = [
  { id:"architecture", icon:TerminalSquare, label:"System Story" },
  { id:"overview", icon:LayoutDashboard, label:"Overview" },
  { id:"flow", icon:Activity, label:"Submit Application" },
  { id:"audit", icon:FileText, label:"Audit Trail" },
  { id:"compliance", icon:Shield, label:"Compliance" },
  { id:"projections", icon:BarChart3, label:"Projections" },
  { id:"query", icon:TerminalSquare, label:"Live Query" },
  { id:"events", icon:Database, label:"Events" },
  { id:"mcp", icon:Wrench, label:"MCP Explorer" },
  { id:"integrity", icon:Lock, label:"Integrity" },
  { id:"demos", icon:Play, label:"Live Demos" },
]


export default function Sidebar({ page, setPage, appId, setAppId }) {
  return (
    <div style={{width:240,background:"rgba(10, 12, 20, 0.7)",backdropFilter:"blur(20px)",WebkitBackdropFilter:"blur(20px)",borderRight:"1px solid var(--border)",display:"flex",flexDirection:"column",flexShrink:0,boxShadow:"0 0 20px rgba(0,0,0,0.4)"}}>
      <div style={{padding:"24px 20px",borderBottom:"1px solid var(--border)"}}>
        <div className="brand-font" style={{fontSize:20,fontWeight:700,color:"#fff",letterSpacing:"-0.02em"}}>
          Apex <span style={{color:"var(--purple)",textShadow:"0 0 10px var(--purple-glow)"}}>Ledger</span>
        </div>
        <div style={{fontSize:11,color:"var(--muted)",marginTop:4,letterSpacing:"0.02em"}}>Event Store Dashboard</div>
      </div>
      <div style={{padding:"16px 20px",borderBottom:"1px solid var(--border)",background:"rgba(255,255,255,0.02)"}}>
        <div style={{fontSize:10,color:"var(--muted)",marginBottom:6,textTransform:"uppercase",letterSpacing:"0.05em",fontWeight:600}}>Application ID</div>
        <input value={appId} onChange={e=>setAppId(e.target.value)}
          style={{width:"100%",background:"rgba(0,0,0,0.5)",border:"1px solid var(--border)",borderRadius:6,padding:"8px 12px",color:"#fff",fontSize:13,transition:"border 0.2s"}}
          onFocus={e=>e.target.style.borderColor="var(--purple)"}
          onBlur={e=>e.target.style.borderColor="var(--border)"}
          placeholder="APEX-TEST-01" />
      </div>
      <nav style={{flex:1,padding:"16px 12px",overflowY:"auto",display:"flex",flexDirection:"column",gap:4}}>
        {links.map(l => (
          <button key={l.id} onClick={()=>setPage(l.id)}
            style={{
              width:"100%",display:"flex",alignItems:"center",gap:12,padding:"10px 14px",border:"none",
              background:page===l.id?"var(--purple-glow)":"transparent",
              color:page===l.id?"#fff":"var(--muted)",
              borderRadius:8,cursor:"pointer",fontSize:13,fontWeight:page===l.id?500:400,
              transition:"all 0.2s cubic-bezier(0.16, 1, 0.3, 1)"
            }}>
            <l.icon size={16} strokeWidth={page===l.id?2.5:2} color={page===l.id?"var(--purple)":"currentColor"} />
            {l.label}
          </button>
        ))}
      </nav>
      <div style={{padding:"16px 20px",borderTop:"1px solid var(--border)",background:"rgba(0,0,0,0.2)"}}>
        <div style={{display:"flex",alignItems:"center",gap:8,fontSize:11,color:"var(--muted)",fontWeight:500}}>
          <div style={{width:8,height:8,borderRadius:"50%",background:"var(--green)",boxShadow:"0 0 8px var(--green)",animation:"fadeIn 2s infinite alternate"}} />
          Connected to DB
        </div>
      </div>
    </div>
  )
}
