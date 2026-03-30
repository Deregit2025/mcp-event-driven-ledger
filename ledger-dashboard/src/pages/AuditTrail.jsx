
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Badge, Loading, Err } from "../components/Card"

const STREAM_COLORS = { loan:"#a78bfa", credit:"#60a5fa", fraud:"#f59e0b", compliance:"#22c55e", audit:"#555" }
const getColor = s => Object.entries(STREAM_COLORS).find(([k])=>s.startsWith(k))?.[1] || "#555"

export default function AuditTrail({ appId }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [filter, setFilter] = useState("")

  useEffect(() => {
    if (!appId) return
    api.auditTrail(appId).then(setData).catch(e=>setErr(e.message))
  }, [appId])

  if (err) return <Err msg={err} />
  if (!data) return <Loading />

  const events = filter ? data.events.filter(e=>e.event_type.toLowerCase().includes(filter.toLowerCase())||e.stream_id.includes(filter)) : data.events

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Audit Trail</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>{data.total_events} events across {data.streams_covered?.length} streams for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:8,marginBottom:16}}>
        {data.streams_covered?.map(s => (
          <div key={s} style={{background:"#16192a",border:`1px solid ${getColor(s)}44`,borderLeft:`3px solid ${getColor(s)}`,borderRadius:6,padding:"8px 12px"}}>
            <div style={{fontSize:10,color:getColor(s),textTransform:"uppercase",marginBottom:2}}>Stream</div>
            <div style={{fontSize:11,color:"#888"}}>{s}</div>
          </div>
        ))}
      </div>

      <Card title="Complete Event History">
        <input value={filter} onChange={e=>setFilter(e.target.value)}
          placeholder="Filter by event type or stream..."
          style={{width:"100%",background:"#0a0c14",border:"1px solid #2a2a3a",borderRadius:6,padding:"8px 12px",color:"#e2e2e2",fontSize:12,marginBottom:12}} />
        <div style={{display:"flex",flexDirection:"column",gap:5,maxHeight:600,overflowY:"auto"}}>
          {events.map((e,i) => {
            const p = e.payload || {}
            let detail = ""
            if (e.event_type==="CreditAnalysisCompleted") detail = `risk=${p.decision?.risk_tier} · confidence=${p.decision?.confidence} · hash=${p.input_data_hash}`
            else if (e.event_type==="FraudScreeningCompleted") detail = `score=${p.fraud_score} · ${p.risk_level} · ${p.recommendation}`
            else if (e.event_type==="ComplianceCheckCompleted") detail = `verdict=${p.overall_verdict} · ${p.rules_passed}/${p.rules_evaluated} passed`
            else if (e.event_type==="DecisionGenerated") detail = `${p.recommendation} · confidence=${p.confidence}`
            else if (e.event_type==="ApplicationApproved") detail = `$${Number(p.approved_amount_usd||0).toLocaleString()} · by ${p.approved_by}`
            else if (e.event_type==="ApplicationSubmitted") detail = `${p.applicant_id} · $${Number(p.requested_amount_usd||0).toLocaleString()}`
            return (
              <div key={i} style={{display:"flex",gap:10,padding:"8px 12px",borderRadius:6,border:"1px solid #1e2030",background:"#0f1117",borderLeft:`3px solid ${getColor(e.stream_id)}`}}>
                <span style={{color:"#444",minWidth:24,fontSize:11}}>[{e.stream_position}]</span>
                <div style={{flex:1}}>
                  <div style={{display:"flex",gap:8,alignItems:"center"}}>
                    <span style={{color:getColor(e.stream_id),fontWeight:500,fontSize:13}}>{e.event_type}</span>
                    <span style={{fontSize:10,color:"#444"}}>v{e.event_version}</span>
                    {e.causation_id && <span style={{fontSize:10,color:"#333"}}>caused by: {e.causation_id}</span>}
                  </div>
                  <div style={{fontSize:10,color:"#444",marginTop:1}}>{e.stream_id}</div>
                  {detail && <div style={{fontSize:11,color:"#666",marginTop:2}}>{detail}</div>}
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
