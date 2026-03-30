
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Loading, Err } from "../components/Card"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

export default function Projections({ appId }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => { api.projections().then(setData).catch(e=>setErr(e.message)) }, [])

  if (err) return <Err msg={err} />
  if (!data) return <Loading />

  return (
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
            <div style={{marginTop:8,padding:"4px 8px",background:p.color+"22",borderRadius:4,fontSize:11,color:p.color,display:"inline-block"}}>SLO ≤ {p.slo}ms</div>
          </Card>
        ))}
      </div>

      <Card title="Projection Checkpoints" subtitle="Last processed global_position per projection">
        {data.checkpoints?.length ? data.checkpoints.map((c,i)=>(
          <div key={i} style={{display:"flex",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid #1e2030",fontSize:13}}>
            <span style={{color:"#a78bfa"}}>{c.projection_name}</span>
            <span style={{color:"#555"}}>last_position: <span style={{color:"#e2e2e2"}}>{c.last_position}</span></span>
            <span style={{color:"#444",fontSize:11}}>{String(c.updated_at||"").substring(0,19)}</span>
          </div>
        )) : <div style={{color:"#555",fontSize:12}}>No checkpoints found — ProjectionDaemon not running against this DB</div>}
      </Card>

      {data.agent_performance_ledger?.rows?.length > 0 && (
        <Card title="Agent Performance by Agent Type">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.agent_performance_ledger.rows}>
              <XAxis dataKey="agent_type" stroke="#555" tick={{fill:"#555",fontSize:11}} />
              <YAxis stroke="#555" tick={{fill:"#555",fontSize:11}} />
              <Tooltip contentStyle={{background:"#16192a",border:"1px solid #2a2a3a",color:"#e2e2e2"}} />
              <Bar dataKey="total_sessions" fill="#a78bfa" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}
