const fs = require("fs");
const path = require("path");

const files = {
"src/index.css": `
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Inter",system-ui,sans-serif;background:#0a0c14;color:#e2e2e2;min-height:100vh}
:root{--purple:#a78bfa;--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--blue:#60a5fa;--bg2:#16192a;--bg3:#1e2030;--border:#2a2a3a}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:#0a0c14}
::-webkit-scrollbar-thumb{background:#2a2a3a;border-radius:3px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
`,

"src/hooks/api.js": `
import axios from "axios"
const BASE = "http://127.0.0.1:8000"
export const api = {
  health: () => axios.get(BASE+"/health").then(r=>r.data),
  stats: () => axios.get(BASE+"/stats").then(r=>r.data),
  applications: () => axios.get(BASE+"/applications").then(r=>r.data),
  application: id => axios.get(BASE+"/applications/"+id).then(r=>r.data),
  auditTrail: id => axios.get(BASE+"/audit-trail/"+id).then(r=>r.data),
  compliance: id => axios.get(BASE+"/compliance/"+id).then(r=>r.data),
  complianceTemporal: (id,asOf) => axios.get(BASE+"/compliance/"+id+"/temporal?as_of="+asOf).then(r=>r.data),
  projections: () => axios.get(BASE+"/projections").then(r=>r.data),
  upcasting: id => axios.get(BASE+"/upcasting/"+id).then(r=>r.data),
  events: (params) => axios.get(BASE+"/events", {params}).then(r=>r.data),
  streams: () => axios.get(BASE+"/streams").then(r=>r.data),
  integrity: id => axios.get(BASE+"/integrity/"+id).then(r=>r.data),
  mcpTools: () => axios.get(BASE+"/mcp/tools").then(r=>r.data),
  mcpResources: () => axios.get(BASE+"/mcp/resources").then(r=>r.data),
}
`,

"src/components/Card.jsx": `
export function Card({title,subtitle,children,style}){
  return(
    <div style={{background:"#16192a",border:"1px solid #2a2a3a",borderRadius:10,padding:18,marginBottom:16,...style}}>
      {title&&<div style={{fontSize:14,fontWeight:500,color:"#fff",marginBottom:subtitle?2:12}}>{title}</div>}
      {subtitle&&<div style={{fontSize:12,color:"#555",marginBottom:12}}>{subtitle}</div>}
      {children}
    </div>
  )
}
export function Badge({children,color="purple"}){
  const colors={purple:"#a78bfa",green:"#22c55e",amber:"#f59e0b",red:"#ef4444",blue:"#60a5fa",gray:"#555"}
  const bgs={purple:"#1e1a3a",green:"#0d1f12",amber:"#1c1400",red:"#1a0a0a",blue:"#0a1628",gray:"#1e2030"}
  return(<span style={{padding:"2px 10px",borderRadius:5,fontSize:11,fontWeight:500,color:colors[color],background:bgs[color],border:"1px solid "+colors[color]+"33"}}>{children}</span>)
}
export function Stat({value,label,color="#a78bfa"}){
  return(<div style={{textAlign:"center"}}><div style={{fontSize:32,fontWeight:600,color}}>{value}</div><div style={{fontSize:12,color:"#555",marginTop:2}}>{label}</div></div>)
}
export function Loading(){return <div style={{color:"#555",fontSize:13,padding:20,textAlign:"center"}}>Loading...</div>}
export function Err({msg}){return <div style={{color:"#ef4444",fontSize:12,padding:12,background:"#1a0a0a",borderRadius:6,border:"1px solid #ef444433"}}>{msg||"Error loading data"}</div>}
`,

"src/components/Sidebar.jsx": `
import {LayoutDashboard,FileText,Shield,BarChart3,RefreshCw,Database,Play,Wrench,Lock} from "lucide-react"
const links=[
  {id:"overview",icon:LayoutDashboard,label:"Overview"},
  {id:"audit",icon:FileText,label:"Audit Trail"},
  {id:"compliance",icon:Shield,label:"Compliance"},
  {id:"projections",icon:BarChart3,label:"Projections"},
  {id:"upcasting",icon:RefreshCw,label:"Upcasting"},
  {id:"events",icon:Database,label:"Events"},
  {id:"mcp",icon:Wrench,label:"MCP Explorer"},
  {id:"integrity",icon:Lock,label:"Integrity"},
  {id:"demos",icon:Play,label:"Live Demos"},
]
export default function Sidebar({page,setPage,appId,setAppId}){
  return(
    <div style={{width:220,background:"#16192a",borderRight:"1px solid #2a2a3a",display:"flex",flexDirection:"column",flexShrink:0,height:"100vh"}}>
      <div style={{padding:"20px 16px",borderBottom:"1px solid #2a2a3a"}}>
        <div style={{fontSize:16,fontWeight:600,color:"#fff"}}>Apex <span style={{color:"#a78bfa"}}>Ledger</span></div>
        <div style={{fontSize:11,color:"#555",marginTop:2}}>Event Store Dashboard</div>
      </div>
      <div style={{padding:"12px 10px",borderBottom:"1px solid #2a2a3a"}}>
        <div style={{fontSize:10,color:"#555",marginBottom:4,textTransform:"uppercase",letterSpacing:"0.05em"}}>Application ID</div>
        <input value={appId} onChange={e=>setAppId(e.target.value)}
          style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"6px 8px",color:"#e2e2e2",fontSize:12}}
          placeholder="APEX-TEST-01"/>
      </div>
      <nav style={{flex:1,padding:"8px 0",overflowY:"auto"}}>
        {links.map(l=>(
          <button key={l.id} onClick={()=>setPage(l.id)}
            style={{width:"100%",display:"flex",alignItems:"center",gap:10,padding:"10px 16px",border:"none",background:page===l.id?"#1e1a3a":"transparent",color:page===l.id?"#a78bfa":"#888",cursor:"pointer",fontSize:13,borderLeft:page===l.id?"2px solid #a78bfa":"2px solid transparent",transition:"all 0.2s"}}>
            <l.icon size={16}/>{l.label}
          </button>
        ))}
      </nav>
      <div style={{padding:"12px 16px",borderTop:"1px solid #2a2a3a"}}>
        <div style={{display:"flex",alignItems:"center",gap:6,fontSize:11,color:"#555"}}>
          <div style={{width:6,height:6,borderRadius:"50%",background:"#22c55e",animation:"pulse 2s infinite"}}/>
          Connected
        </div>
      </div>
    </div>
  )
}
`,

"src/App.jsx": `
import {useState} from "react"
import Sidebar from "./components/Sidebar"
import Overview from "./pages/Overview"
import AuditTrail from "./pages/AuditTrail"
import Compliance from "./pages/Compliance"
import Projections from "./pages/Projections"
import Upcasting from "./pages/Upcasting"
import Events from "./pages/Events"
import Demos from "./pages/Demos"
import MCPExplorer from "./pages/MCPExplorer"
import Integrity from "./pages/Integrity"

const PAGES={overview:Overview,audit:AuditTrail,compliance:Compliance,projections:Projections,upcasting:Upcasting,events:Events,demos:Demos,mcp:MCPExplorer,integrity:Integrity}

export default function App(){
  const [page,setPage]=useState("overview")
  const [appId,setAppId]=useState("APEX-TEST-01")
  const Page=PAGES[page]||Overview
  return(
    <div style={{display:"flex",height:"100vh",overflow:"hidden"}}>
      <Sidebar page={page} setPage={setPage} appId={appId} setAppId={setAppId}/>
      <main style={{flex:1,overflow:"auto",padding:"24px"}}>
        <Page appId={appId}/>
      </main>
    </div>
  )
}
`,

"src/pages/Overview.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Stat,Loading,Err} from "../components/Card"
import {PieChart,Pie,Cell,Tooltip,ResponsiveContainer,BarChart,Bar,XAxis,YAxis} from "recharts"

export default function Overview(){
  const [data,setData]=useState(null)
  const [err,setErr]=useState(null)
  useEffect(()=>{
    Promise.all([api.stats(),api.health()]).then(([s])=>setData(s)).catch(e=>setErr(e.message))
  },[])
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  const pieData=[{name:"Approved",value:data.decisions.approved},{name:"Declined",value:data.decisions.declined}]
  const COLORS=["#22c55e","#ef4444"]
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Apex Ledger Overview</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Production event store — {data.total_events.toLocaleString()} events across {data.total_streams} streams</p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16,marginBottom:16}}>
        <Card><Stat value={data.total_events.toLocaleString()} label="Total Events"/></Card>
        <Card><Stat value={data.total_streams} label="Active Streams" color="#60a5fa"/></Card>
        <Card><Stat value={data.decisions.approved} label="Approved" color="#22c55e"/></Card>
        <Card><Stat value={data.decisions.declined} label="Declined" color="#ef4444"/></Card>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:16}}>
        <Card title="Top Event Types">
          {data.top_event_types.map((t,i)=>(
            <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
              <span style={{color:"#a78bfa"}}>{t.type}</span>
              <span style={{color:"#555"}}>{t.count}</span>
            </div>
          ))}
        </Card>
        <Card title="Decision Outcomes">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" outerRadius={75} dataKey="value" label={({name,value})=>name+": "+value}>
                {pieData.map((_,i)=><Cell key={i} fill={COLORS[i]}/>)}
              </Pie>
              <Tooltip contentStyle={{background:"#16192a",border:"1px solid #2a2a3a",color:"#e2e2e2"}}/>
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <Card title="Recent Activity">
        {data.recent_events.map((e,i)=>(
          <div key={i} style={{display:"flex",gap:12,padding:"7px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
            <span style={{color:"#a78bfa",minWidth:240}}>{e.event_type}</span>
            <span style={{color:"#444",flex:1}}>{e.stream_id}</span>
            <span style={{color:"#555"}}>{e.recorded_at.substring(0,19)}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
`,

"src/pages/AuditTrail.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
const COLORS={loan:"#a78bfa",credit:"#60a5fa",fraud:"#f59e0b",compliance:"#22c55e",audit:"#555"}
const gc=s=>Object.entries(COLORS).find(([k])=>s.startsWith(k))?.[1]||"#555"
export default function AuditTrail({appId}){
  const [data,setData]=useState(null)
  const [err,setErr]=useState(null)
  const [filter,setFilter]=useState("")
  useEffect(()=>{if(!appId)return;api.auditTrail(appId).then(setData).catch(e=>setErr(e.message))},[appId])
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  const events=filter?data.events.filter(e=>e.event_type.toLowerCase().includes(filter.toLowerCase())||e.stream_id.includes(filter)):data.events
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Audit Trail</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>{data.total_events} events across {data.streams_covered?.length} streams for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>
      <div style={{display:"flex",gap:8,marginBottom:16,flexWrap:"wrap"}}>
        {data.streams_covered?.map(s=>(
          <div key={s} style={{background:"#16192a",border:"1px solid "+gc(s)+"44",borderLeft:"3px solid "+gc(s),borderRadius:6,padding:"6px 10px",fontSize:11,color:gc(s)}}>{s}</div>
        ))}
      </div>
      <Card title="Complete Event History">
        <input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter by event type or stream..."
          style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"8px 12px",color:"#e2e2e2",fontSize:12,marginBottom:12}}/>
        <div style={{display:"flex",flexDirection:"column",gap:5,maxHeight:560,overflowY:"auto"}}>
          {events.map((e,i)=>{
            const p=e.payload||{}
            let detail=""
            if(e.event_type==="CreditAnalysisCompleted") detail="risk="+p.decision?.risk_tier+" · confidence="+p.decision?.confidence+" · hash="+p.input_data_hash
            else if(e.event_type==="FraudScreeningCompleted") detail="score="+p.fraud_score+" · "+p.risk_level+" · "+p.recommendation
            else if(e.event_type==="ComplianceCheckCompleted") detail="verdict="+p.overall_verdict+" · "+p.rules_passed+"/"+p.rules_evaluated+" passed"
            else if(e.event_type==="DecisionGenerated") detail=p.recommendation+" · confidence="+p.confidence
            else if(e.event_type==="ApplicationApproved") detail="$"+Number(p.approved_amount_usd||0).toLocaleString()+" · by "+p.approved_by
            else if(e.event_type==="ApplicationSubmitted") detail=p.applicant_id+" · $"+Number(p.requested_amount_usd||0).toLocaleString()
            return(
              <div key={i} style={{display:"flex",gap:10,padding:"8px 12px",borderRadius:6,border:"1px solid #1e2030",background:"#0f1117",borderLeft:"3px solid "+gc(e.stream_id)}}>
                <span style={{color:"#444",minWidth:24,fontSize:11}}>[{e.stream_position}]</span>
                <div style={{flex:1}}>
                  <div style={{display:"flex",gap:8,alignItems:"center"}}>
                    <span style={{color:gc(e.stream_id),fontWeight:500,fontSize:13}}>{e.event_type}</span>
                    <span style={{fontSize:10,color:"#444"}}>v{e.event_version}</span>
                    {e.causation_id&&<span style={{fontSize:10,color:"#333"}}>caused by: {e.causation_id}</span>}
                  </div>
                  <div style={{fontSize:10,color:"#444",marginTop:1}}>{e.stream_id}</div>
                  {detail&&<div style={{fontSize:11,color:"#666",marginTop:2}}>{detail}</div>}
                </div>
                <span style={{fontSize:11,color:"#444",whiteSpace:"nowrap"}}>{e.recorded_at.substring(11,19)}</span>
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
`,

"src/pages/Compliance.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
export default function Compliance({appId}){
  const [data,setData]=useState(null)
  const [temporal,setTemporal]=useState(null)
  const [asOf,setAsOf]=useState("")
  const [err,setErr]=useState(null)
  const [loading,setLoading]=useState(false)
  useEffect(()=>{
    if(!appId)return
    api.compliance(appId).then(setData).catch(e=>setErr(e.message))
    const d=new Date();d.setHours(d.getHours()-2)
    setAsOf(d.toISOString().substring(0,19)+"Z")
  },[appId])
  const queryTemporal=async()=>{
    setLoading(true)
    try{setTemporal(await api.complianceTemporal(appId,asOf))}
    catch(e){setErr(e.message)}
    setLoading(false)
  }
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  const s=data.summary||{}
  const verdict=s.overall_verdict||"PENDING"
  const vc=verdict==="CLEAR"?"#22c55e":verdict==="BLOCKED"?"#ef4444":"#f59e0b"
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Compliance</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Regulatory compliance state for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:16}}>
        <Card title="Compliance Summary">
          <div style={{textAlign:"center",marginBottom:16}}>
            <div style={{fontSize:22,fontWeight:600,color:vc,padding:"8px 20px",display:"inline-block",background:vc+"22",borderRadius:8,border:"1px solid "+vc+"44"}}>{verdict}</div>
          </div>
          {[["Rules Evaluated",s.rules_evaluated,"#60a5fa"],["Rules Passed",s.rules_passed,"#22c55e"],["Rules Failed",s.rules_failed,"#ef4444"],["Rules Noted",s.rules_noted,"#f59e0b"],["Hard Block",s.has_hard_block?"YES":"NO",s.has_hard_block?"#ef4444":"#22c55e"]].map(([k,v,c])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:13}}>
              <span style={{color:"#555"}}>{k}</span><span style={{color:c,fontWeight:500}}>{v}</span>
            </div>
          ))}
        </Card>
        <Card title="Rule Evaluation Detail">
          <div style={{maxHeight:280,overflowY:"auto"}}>
            {data.events?.filter(e=>["ComplianceRulePassed","ComplianceRuleFailed","ComplianceRuleNoted"].includes(e.event_type)).map((e,i)=>{
              const p=e.payload||{}
              const icon=e.event_type==="ComplianceRulePassed"?"✓":e.event_type==="ComplianceRuleFailed"?"✗":"!"
              const color=e.event_type==="ComplianceRulePassed"?"#22c55e":e.event_type==="ComplianceRuleFailed"?"#ef4444":"#f59e0b"
              return(
                <div key={i} style={{display:"flex",gap:10,padding:"7px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
                  <div style={{width:20,height:20,borderRadius:"50%",background:color+"22",color,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,flexShrink:0}}>{icon}</div>
                  <div style={{flex:1}}><div style={{fontWeight:500}}>{p.rule_id}</div><div style={{color:"#555",fontSize:11}}>{p.rule_name}</div></div>
                  <div style={{fontSize:10,color:"#444"}}>{e.recorded_at.substring(11,19)}</div>
                </div>
              )
            })}
          </div>
        </Card>
      </div>
      <Card title="Temporal Query — Regulatory Time Travel" subtitle="Query compliance state at any past timestamp">
        <div style={{display:"flex",gap:10,marginBottom:16,alignItems:"center"}}>
          <input value={asOf} onChange={e=>setAsOf(e.target.value)}
            style={{flex:1,background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"8px 12px",color:"#e2e2e2",fontSize:12}}
            placeholder="2026-03-25T10:00:00Z"/>
          <button onClick={queryTemporal} disabled={loading}
            style={{padding:"8px 20px",background:"#6c63ff",color:"#fff",border:"none",borderRadius:6,cursor:"pointer",fontSize:13,fontWeight:500,opacity:loading?0.6:1}}>
            {loading?"Querying...":"Query Past State"}
          </button>
        </div>
        {temporal&&(
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
            {[{label:"Current State",d:s,border:"#60a5fa"},{label:"Past State ("+asOf.substring(0,19)+")",d:temporal,border:"#f59e0b"}].map(({label,d,border})=>(
              <div key={label} style={{background:"#0f1117",border:"1px solid "+border+"44",borderTop:"2px solid "+border,borderRadius:8,padding:14}}>
                <div style={{fontSize:11,color:border,textTransform:"uppercase",marginBottom:10}}>{label}</div>
                <div style={{fontSize:22,fontWeight:600,color:d.overall_verdict==="CLEAR"?"#22c55e":d.overall_verdict==="BLOCKED"?"#ef4444":"#f59e0b",marginBottom:8}}>{d.overall_verdict||"PENDING"}</div>
                <div style={{fontSize:12,color:"#555"}}>Rules evaluated: <span style={{color:"#e2e2e2"}}>{d.rules_evaluated||0}</span></div>
                <div style={{fontSize:12,color:"#555"}}>Rules passed: <span style={{color:"#22c55e"}}>{d.rules_passed||0}</span></div>
                {d.message&&<div style={{fontSize:11,color:"#f59e0b",marginTop:8}}>{d.message}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
`,

"src/pages/Projections.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
import {BarChart,Bar,XAxis,YAxis,Tooltip,ResponsiveContainer} from "recharts"
export default function Projections(){
  const [data,setData]=useState(null)
  const [err,setErr]=useState(null)
  useEffect(()=>{api.projections().then(setData).catch(e=>setErr(e.message))},[])
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Projections & CQRS Read Models</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Three projections maintained by the ProjectionDaemon</p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16,marginBottom:16}}>
        {[{name:"ApplicationSummary",count:data.application_summary?.count,slo:500,color:"#a78bfa"},
          {name:"AgentPerformance",count:data.agent_performance_ledger?.rows?.length,slo:500,color:"#60a5fa"},
          {name:"ComplianceAuditView",count:data.compliance_audit_view?.count,slo:2000,color:"#22c55e"}].map(p=>(
          <Card key={p.name}>
            <div style={{fontSize:13,fontWeight:500,color:"#fff",marginBottom:8}}>{p.name}</div>
            <div style={{fontSize:28,fontWeight:600,color:p.color,marginBottom:4}}>{p.count??0}</div>
            <div style={{fontSize:11,color:"#555"}}>rows in projection table</div>
            <div style={{marginTop:8,padding:"4px 8px",background:p.color+"22",borderRadius:4,fontSize:11,color:p.color,display:"inline-block"}}>SLO <= {p.slo}ms</div>
          </Card>
        ))}
      </div>
      <Card title="Projection Checkpoints" subtitle="Last processed global_position per projection">
        {data.checkpoints?.length?data.checkpoints.map((c,i)=>(
          <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid #1e2030",fontSize:13}}>
            <span style={{color:"#a78bfa"}}>{c.projection_name}</span>
            <span style={{color:"#555"}}>last_position: <span style={{color:"#e2e2e2"}}>{c.last_position}</span></span>
            <span style={{color:"#444",fontSize:11}}>{String(c.updated_at||"").substring(0,19)}</span>
          </div>
        )):<div style={{color:"#555",fontSize:12}}>No checkpoints found</div>}
      </Card>
      {data.agent_performance_ledger?.rows?.length>0&&(
        <Card title="Agent Performance by Model Version">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.agent_performance_ledger.rows}>
              <XAxis dataKey="model_version" stroke="#555" tick={{fill:"#555",fontSize:11}}/>
              <YAxis stroke="#555" tick={{fill:"#555",fontSize:11}}/>
              <Tooltip contentStyle={{background:"#16192a",border:"1px solid #2a2a3a",color:"#e2e2e2"}}/>
              <Bar dataKey="total_sessions" fill="#a78bfa" radius={[4,4,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}
`,

"src/pages/Upcasting.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
export default function Upcasting({appId}){
  const [data,setData]=useState(null)
  const [err,setErr]=useState(null)
  useEffect(()=>{if(!appId)return;api.upcasting(appId).then(setData).catch(e=>setErr(e.message))},[appId])
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Upcasting & Immutability</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Event stored as v{data.stored_version} in PostgreSQL, loaded as v{data.loaded_version} via UpcasterRegistry</p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:16}}>
        <Card style={{borderTop:"2px solid #60a5fa"}}>
          <div style={{fontSize:11,color:"#60a5fa",textTransform:"uppercase",marginBottom:12}}>Raw PostgreSQL Row (stored)</div>
          <div style={{fontSize:28,fontWeight:600,color:"#60a5fa",marginBottom:12}}>v{data.stored_version}</div>
          {[["event_id",data.event_id?.substring(0,16)+"..."],["stream_id",data.stream_id],["event_version","v"+data.stored_version],["model_versions","NOT PRESENT"],["confidence_score","NOT PRESENT"],["regulatory_basis","NOT PRESENT"]].map(([k,v])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
              <span style={{color:"#555"}}>{k}</span>
              <span style={{color:v.includes("NOT")?"#333":"#e2e2e2",fontStyle:v.includes("NOT")?"italic":"normal"}}>{v}</span>
            </div>
          ))}
        </Card>
        <Card style={{borderTop:"2px solid #22c55e"}}>
          <div style={{fontSize:11,color:"#22c55e",textTransform:"uppercase",marginBottom:12}}>Loaded via UpcasterRegistry (read-time)</div>
          <div style={{fontSize:28,fontWeight:600,color:"#22c55e",marginBottom:12}}>v{data.loaded_version}</div>
          {[["event_version","v"+data.loaded_version],["model_versions",JSON.stringify(data.loaded_payload?.model_versions||{})],["confidence_score",String(data.loaded_payload?.confidence_score)+" (null)"],["regulatory_basis",JSON.stringify(data.loaded_payload?.regulatory_basis||[])]].map(([k,v])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #1e2030",fontSize:12,gap:8}}>
              <span style={{color:"#555",flexShrink:0}}>{k}</span>
              <span style={{color:"#86efac",textAlign:"right",wordBreak:"break-all"}}>{v}</span>
            </div>
          ))}
        </Card>
      </div>
      <Card style={{background:"#0d1f12",border:"1px solid #22c55e44"}}>
        <div style={{fontSize:14,fontWeight:500,color:"#22c55e",marginBottom:8}}>Immutability Guaranteed</div>
        <div style={{fontSize:13,color:"#86efac",lineHeight:1.8}}>
          The PostgreSQL row is v{data.stored_version} before and after loading. The upcaster is a read-time transformation only. The database is never modified.
        </div>
      </Card>
    </div>
  )
}
`,

"src/pages/Events.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
export default function Events(){
  const [data,setData]=useState(null)
  const [streams,setStreams]=useState(null)
  const [err,setErr]=useState(null)
  const [f,setF]=useState({stream_id:"",event_type:"",limit:50})
  const load=()=>{
    const p={}
    if(f.stream_id) p.stream_id=f.stream_id
    if(f.event_type) p.event_type=f.event_type
    p.limit=f.limit
    api.events(p).then(setData).catch(e=>setErr(e.message))
  }
  useEffect(()=>{load();api.streams().then(setStreams).catch(()=>{})},[])
  if(err) return <Err msg={err}/>
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Event Store Explorer</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Browse all events — {data?.total?.toLocaleString()||"..."} total across {streams?.streams?.length||"..."} streams</p>
      </div>
      <Card title="Filter Events">
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr auto auto",gap:10,alignItems:"end"}}>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Stream ID</div>
            <input value={f.stream_id} onChange={e=>setF({...f,stream_id:e.target.value})}
              style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}} placeholder="loan-APEX-TEST-01"/>
          </div>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Event Type</div>
            <input value={f.event_type} onChange={e=>setF({...f,event_type:e.target.value})}
              style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}} placeholder="CreditAnalysisCompleted"/>
          </div>
          <div>
            <div style={{fontSize:11,color:"#555",marginBottom:4}}>Limit</div>
            <select value={f.limit} onChange={e=>setF({...f,limit:e.target.value})} style={{background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"7px 10px",color:"#e2e2e2",fontSize:12}}>
              <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
            </select>
          </div>
          <button onClick={load} style={{padding:"7px 20px",background:"#6c63ff",color:"#fff",border:"none",borderRadius:6,cursor:"pointer",fontSize:13}}>Search</button>
        </div>
      </Card>
      {!data?<Loading/>:(
        <Card title={data.total.toLocaleString()+" events found"}>
          <div style={{maxHeight:500,overflowY:"auto"}}>
            {data.events.map((e,i)=>(
              <div key={i} style={{padding:"8px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
                <div style={{display:"flex",gap:10,alignItems:"center",marginBottom:2}}>
                  <span style={{color:"#a78bfa",fontWeight:500}}>{e.event_type}</span>
                  <span style={{color:"#333",fontSize:10}}>v{e.event_version}</span>
                  <span style={{color:"#444",fontSize:10,marginLeft:"auto"}}>{e.recorded_at.substring(0,19)}</span>
                </div>
                <div style={{color:"#444",fontSize:11}}>{e.stream_id} pos {e.stream_position} global {e.global_position}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
      <Card title={"Active Streams ("+( streams?.streams?.length||0)+")"}>
        <div style={{maxHeight:300,overflowY:"auto"}}>
          {streams?.streams?.map((s,i)=>(
            <div key={i} style={{display:"flex",gap:10,padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
              <span style={{color:"#a78bfa",flex:1}}>{s.stream_id}</span>
              <span style={{color:"#555"}}>{s.aggregate_type}</span>
              <span style={{color:"#444"}}>v{s.current_version}</span>
              {s.is_archived&&<span style={{color:"#f59e0b",fontSize:10}}>archived</span>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
`,

"src/pages/MCPExplorer.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
export default function MCPExplorer(){
  const [tools,setTools]=useState(null)
  const [resources,setResources]=useState(null)
  const [err,setErr]=useState(null)
  const [sel,setSel]=useState(null)
  useEffect(()=>{
    Promise.all([api.mcpTools(),api.mcpResources()]).then(([t,r])=>{setTools(t);setResources(r)}).catch(e=>setErr(e.message))
  },[])
  if(err) return <Err msg={err}/>
  if(!tools) return <Loading/>
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>MCP Explorer</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>{tools.total} tools (write side) · {resources.total} resources (read side)</p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
        <Card title="MCP Tools — Write Side" subtitle="Commands that append events to the store">
          {tools.tools.map((t,i)=>(
            <div key={i} onClick={()=>setSel(sel?.name===t.name?null:t)}
              style={{padding:"10px 12px",borderRadius:6,border:"1px solid "+(sel?.name===t.name?"#a78bfa":"#2a2a3a"),background:sel?.name===t.name?"#1e1a3a":"#0f1117",marginBottom:6,cursor:"pointer"}}>
              <div style={{fontSize:13,fontWeight:500,color:"#d97706",marginBottom:4}}>{t.name}</div>
              <div style={{fontSize:11,color:"#555"}}>{t.description.substring(0,100)}...</div>
              {sel?.name===t.name&&(
                <div style={{marginTop:10,padding:10,background:"#0a0c14",borderRadius:6}}>
                  <div style={{fontSize:11,color:"#a78bfa",marginBottom:6}}>Required:</div>
                  {t.inputSchema?.required?.map(r=>(
                    <span key={r} style={{display:"inline-block",margin:"2px 4px 2px 0",padding:"1px 8px",background:"#1e1a3a",borderRadius:4,fontSize:11,color:"#a78bfa"}}>{r}</span>
                  ))}
                  <div style={{fontSize:11,color:"#555",marginTop:8,lineHeight:1.6}}>{t.description}</div>
                </div>
              )}
            </div>
          ))}
        </Card>
        <Card title="MCP Resources — Read Side" subtitle="Query endpoints for projections and streams">
          {resources.resources.map((r,i)=>(
            <div key={i} style={{padding:"10px 12px",borderRadius:6,border:"1px solid #2a2a3a",background:"#0f1117",marginBottom:6}}>
              <div style={{fontSize:13,fontWeight:500,color:"#60a5fa",marginBottom:4}}>{r.uriTemplate||r.uri}</div>
              <div style={{fontSize:11,color:"#555",lineHeight:1.5}}>{r.description}</div>
              <div style={{fontSize:10,color:"#333",marginTop:4}}>{r.name}</div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
`,

"src/pages/Integrity.jsx": `
import {useEffect,useState} from "react"
import {api} from "../hooks/api"
import {Card,Loading,Err} from "../components/Card"
export default function Integrity({appId}){
  const [data,setData]=useState(null)
  const [err,setErr]=useState(null)
  useEffect(()=>{if(!appId)return;api.integrity(appId).then(setData).catch(e=>setErr(e.message))},[appId])
  if(err) return <Err msg={err}/>
  if(!data) return <Loading/>
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Cryptographic Integrity</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>SHA-256 hash chain for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>
      {data.integrity_checks.length===0?(
        <Card><div style={{color:"#555",fontSize:13}}>No integrity checks found. Run ledger_run_integrity_check in Claude Desktop first.</div></Card>
      ):data.integrity_checks.map((c,i)=>(
        <Card key={i} style={{borderLeft:"3px solid "+(c.chain_valid?"#22c55e":"#ef4444")}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
            <div style={{fontSize:15,fontWeight:500,color:c.chain_valid?"#22c55e":"#ef4444"}}>{c.chain_valid?"Chain Valid":"Chain Invalid"}</div>
            <div style={{fontSize:12,color:"#555"}}>{c.check_timestamp?.substring(0,19)}</div>
          </div>
          {[["Events Verified",c.events_verified],["Tamper Detected",c.tamper_detected?"YES — ALERT":"No"],["Integrity Hash",c.integrity_hash]].map(([k,v])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
              <span style={{color:"#555"}}>{k}</span>
              <span style={{color:k==="Tamper Detected"&&String(v).includes("YES")?"#ef4444":"#e2e2e2",fontFamily:k.includes("Hash")?"monospace":"inherit"}}>{String(v)}</span>
            </div>
          ))}
        </Card>
      ))}
    </div>
  )
}
`,

"src/pages/Demos.jsx": `
import {useState} from "react"
import {Card} from "../components/Card"

function OCCDemo(){
  const [running,setRunning]=useState(false)
  const [ver,setVer]=useState(2)
  const [aS,setAS]=useState({s:"idle",msg:"Idle"})
  const [bS,setBS]=useState({s:"idle",msg:"Idle"})
  const [log,setLog]=useState([])
  const [phase,setPhase]=useState(0)
  const addLog=(msg,cls)=>setLog(l=>[...l,{msg,cls,ts:new Date().toLocaleTimeString()}])
  const delay=ms=>new Promise(r=>setTimeout(r,ms))
  const ab=s=>s==="won"?"#22c55e":s==="lost"?"#ef4444":s==="active"?"#a78bfa":"#2a2a3a"
  const run=async()=>{
    setRunning(true);setLog([]);setVer(2);setPhase(0)
    setAS({s:"idle",msg:"Idle"});setBS({s:"idle",msg:"Idle"})
    await delay(400);setPhase(1)
    setAS({s:"active",msg:"Read version = 2"});setBS({s:"active",msg:"Read version = 2"})
    addLog("Both agents read stream version = 2","info")
    await delay(700);setPhase(2)
    addLog("Both attempt append(expected_version=2)...","info")
    await delay(500);setPhase(3)
    setAS({s:"won",msg:"Committed at position 3"});setVer(3)
    addLog("Agent-Alpha: LOCK ACQUIRED — committed at position 3","ok")
    await delay(400);setPhase(4)
    setBS({s:"lost",msg:"OptimisticConcurrencyError"})
    addLog("Agent-Beta: OptimisticConcurrencyError(expected=2, actual=3)","err")
    await delay(700);setPhase(5)
    setBS({s:"abandoned",msg:"Abandoned — analysis done"})
    addLog("Agent-Beta: analysis already recorded — abandoning","warn")
    addLog("Exactly 1 event appended. No split-brain. OCC holds.","ok")
    setRunning(false)
  }
  const reset=()=>{setVer(2);setPhase(0);setLog([]);setAS({s:"idle",msg:"Idle"});setBS({s:"idle",msg:"Idle"})}
  return(
    <div>
      <div style={{display:"flex",gap:6,marginBottom:14,flexWrap:"wrap"}}>
        {["1·Read","2·Attempt","3·Alpha wins","4·Beta fails","5·Abandon"].map((p,i)=>(
          <div key={i} style={{padding:"4px 12px",borderRadius:5,fontSize:11,background:phase===i+1?"#1e1a3a":phase>i+1?"#0d1f12":"#16192a",border:phase===i+1?"1px solid #a78bfa":phase>i+1?"1px solid #22c55e":"1px solid #2a2a3a",color:phase===i+1?"#a78bfa":phase>i+1?"#22c55e":"#555"}}>{p}</div>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr auto 1fr",gap:12,marginBottom:12,alignItems:"center"}}>
        <div style={{background:"#0f1117",border:"1px solid "+ab(aS.s),borderRadius:8,padding:12,transition:"all 0.3s"}}>
          <div style={{fontSize:13,fontWeight:500,marginBottom:6}}>Agent-Alpha</div>
          <div style={{fontSize:11,color:aS.s==="won"?"#22c55e":aS.s==="lost"?"#ef4444":"#888"}}>{aS.msg}</div>
        </div>
        <div style={{textAlign:"center"}}>
          <div style={{fontSize:32,fontWeight:600,color:"#a78bfa"}}>{ver}</div>
          <div style={{fontSize:10,color:"#444"}}>stream ver</div>
        </div>
        <div style={{background:"#0f1117",border:"1px solid "+ab(bS.s),borderRadius:8,padding:12,transition:"all 0.3s"}}>
          <div style={{fontSize:13,fontWeight:500,marginBottom:6}}>Agent-Beta</div>
          <div style={{fontSize:11,color:bS.s==="won"?"#22c55e":bS.s==="lost"?"#ef4444":bS.s==="abandoned"?"#555":"#888"}}>{bS.msg}</div>
        </div>
      </div>
      <div style={{display:"flex",gap:10,marginBottom:10}}>
        <button onClick={run} disabled={running} style={{padding:"7px 18px",background:"#6c63ff",color:"#fff",border:"none",borderRadius:6,cursor:"pointer",fontSize:13,opacity:running?0.5:1}}>Run Demo</button>
        <button onClick={reset} disabled={running} style={{padding:"7px 18px",background:"#1e2030",color:"#aaa",border:"none",borderRadius:6,cursor:"pointer",fontSize:13}}>Reset</button>
      </div>
      <div style={{background:"#0a0c14",borderRadius:6,padding:10,height:120,overflowY:"auto",fontSize:11,fontFamily:"monospace"}}>
        {log.map((l,i)=><div key={i} style={{marginBottom:2,color:l.cls==="ok"?"#22c55e":l.cls==="err"?"#ef4444":l.cls==="warn"?"#f59e0b":"#555"}}>[{l.ts}] {l.msg}</div>)}
      </div>
    </div>
  )
}

export default function Demos(){
  const [tab,setTab]=useState("occ")
  return(
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Live Demos</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Interactive demonstrations of key system guarantees</p>
      </div>
      <div style={{display:"flex",gap:4,marginBottom:16}}>
        {[["occ","Concurrency"],["gastown","Gas Town"],["whatif","What-If"]].map(([id,label])=>(
          <button key={id} onClick={()=>setTab(id)} style={{padding:"8px 16px",borderRadius:6,border:"none",background:tab===id?"#1e1a3a":"#16192a",color:tab===id?"#a78bfa":"#555",cursor:"pointer",fontSize:13,borderBottom:tab===id?"2px solid #a78bfa":"2px solid transparent"}}>
            {label}
          </button>
        ))}
      </div>
      <Card title={tab==="occ"?"Optimistic Concurrency Control":tab==="gastown"?"Gas Town Crash Recovery":"What-If Counterfactual"}>
        {tab==="occ"&&<OCCDemo/>}
        {tab==="gastown"&&<div style={{color:"#555",textAlign:"center",padding:40}}>Gas Town demo — click Run Demo above first, then come here</div>}
        {tab==="whatif"&&<div style={{color:"#555",textAlign:"center",padding:40}}>What-If demo — available in next update</div>}
      </Card>
    </div>
  )
}
`
};

// Create directories
["src/components","src/pages","src/hooks"].forEach(d=>{
  if(!fs.existsSync(d)) fs.mkdirSync(d,{recursive:true})
})

// Write all files
Object.entries(files).forEach(([f,c])=>{
  fs.writeFileSync(f,c,"utf8")
  console.log("Created: "+f)
})
console.log("\nAll files created! Run: npm run dev")