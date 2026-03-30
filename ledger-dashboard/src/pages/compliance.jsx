
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Badge, Loading, Err } from "../components/Card"

export default function Compliance({ appId }) {
  const [data, setData] = useState(null)
  const [temporal, setTemporal] = useState(null)
  const [asOf, setAsOf] = useState("")
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!appId) return
    api.compliance(appId).then(setData).catch(e=>setErr(e.message))
    const d = new Date(); d.setHours(d.getHours()-2)
    setAsOf(d.toISOString().substring(0,19)+"Z")
  }, [appId])

  const queryTemporal = async () => {
    setLoading(true)
    try { setTemporal(await api.complianceTemporal(appId, asOf)) }
    catch(e) { setErr(e.message) }
    setLoading(false)
  }

  if (err) return <Err msg={err} />
  if (!data) return <Loading />
  const s = data.summary || {}
  const verdict = s.overall_verdict || "PENDING"
  const verdictColor = verdict==="CLEAR"?"#22c55e":verdict==="BLOCKED"?"#ef4444":"#f59e0b"

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Compliance</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>Regulatory compliance state for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16,marginBottom:16}}>
        <Card title="Compliance Summary">
          <div style={{textAlign:"center",marginBottom:16}}>
            <div style={{fontSize:24,fontWeight:600,color:verdictColor,padding:"8px 20px",display:"inline-block",background:verdictColor+"22",borderRadius:8,border:`1px solid ${verdictColor}44`}}>{verdict}</div>
          </div>
          {[["Rules Evaluated", s.rules_evaluated, "#60a5fa"],["Rules Passed", s.rules_passed, "#22c55e"],["Rules Failed", s.rules_failed, "#ef4444"],["Rules Noted", s.rules_noted, "#f59e0b"],["Hard Block", s.has_hard_block?"YES":"NO", s.has_hard_block?"#ef4444":"#22c55e"]].map(([k,v,c])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"6px 0",borderBottom:"1px solid #1e2030",fontSize:13}}>
              <span style={{color:"#555"}}>{k}</span>
              <span style={{color:c,fontWeight:500}}>{v}</span>
            </div>
          ))}
          {s.completed_at && <div style={{fontSize:11,color:"#444",marginTop:8}}>Completed: {s.completed_at.substring(0,19)}</div>}
        </Card>

        <Card title="Rule Evaluation Detail">
          <div style={{maxHeight:300,overflowY:"auto"}}>
            {data.events?.filter(e=>["ComplianceRulePassed","ComplianceRuleFailed","ComplianceRuleNoted"].includes(e.event_type)).map((e,i)=>{
              const p = e.payload||{}
              const icon = e.event_type==="ComplianceRulePassed"?"✓":e.event_type==="ComplianceRuleFailed"?"✗":"!"
              const color = e.event_type==="ComplianceRulePassed"?"#22c55e":e.event_type==="ComplianceRuleFailed"?"#ef4444":"#f59e0b"
              return (
                <div key={i} style={{display:"flex",gap:10,padding:"7px 0",borderBottom:"1px solid #1e2030",fontSize:12,alignItems:"center"}}>
                  <div style={{width:20,height:20,borderRadius:"50%",background:color+"22",color,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,flexShrink:0}}>{icon}</div>
                  <div style={{flex:1}}>
                    <div style={{fontWeight:500}}>{p.rule_id}</div>
                    <div style={{color:"#555",fontSize:11}}>{p.rule_name}</div>
                  </div>
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
            placeholder="2026-03-25T10:00:00Z" />
          <button onClick={queryTemporal} disabled={loading}
            style={{padding:"8px 20px",background:"#6c63ff",color:"#fff",border:"none",borderRadius:6,cursor:"pointer",fontSize:13,fontWeight:500}}>
            {loading?"Querying...":"Query Past State"}
          </button>
        </div>
        {temporal && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
            {[{label:"Current State",d:s,border:"#60a5fa"},{label:`Past State (${asOf.substring(0,19)})`,d:temporal,border:"#f59e0b"}].map(({label,d,border})=>(
              <div key={label} style={{background:"#0f1117",border:`1px solid ${border}44`,borderTop:`2px solid ${border}`,borderRadius:8,padding:14}}>
                <div style={{fontSize:11,color:border,textTransform:"uppercase",marginBottom:10}}>{label}</div>
                <div style={{fontSize:24,fontWeight:600,color:d.overall_verdict==="CLEAR"?"#22c55e":d.overall_verdict==="BLOCKED"?"#ef4444":"#f59e0b",marginBottom:8}}>{d.overall_verdict||"PENDING"}</div>
                <div style={{fontSize:12,color:"#555"}}>Rules evaluated: <span style={{color:"#e2e2e2"}}>{d.rules_evaluated||0}</span></div>
                <div style={{fontSize:12,color:"#555"}}>Rules passed: <span style={{color:"#22c55e"}}>{d.rules_passed||0}</span></div>
                {d.message && <div style={{fontSize:11,color:"#f59e0b",marginTop:8}}>{d.message}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
