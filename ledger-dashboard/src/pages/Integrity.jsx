
import { useEffect, useState } from "react"
import { api } from "../hooks/api"
import { Card, Loading, Err } from "../components/Card"

export default function Integrity({ appId }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!appId) return
    api.integrity(appId).then(setData).catch(e=>setErr(e.message))
  }, [appId])

  if (err) return <Err msg={err} />
  if (!data) return <Loading />

  return (
    <div>
      <div style={{marginBottom:20}}>
        <h1 style={{fontSize:22,fontWeight:600,color:"#fff"}}>Cryptographic Integrity</h1>
        <p style={{fontSize:13,color:"#555",marginTop:4}}>SHA-256 hash chain verification for <span style={{color:"#a78bfa"}}>{appId}</span></p>
      </div>

      {data.integrity_checks.length === 0 ? (
        <Card><div style={{color:"#555",fontSize:13}}>No integrity checks run yet for this application. Use ledger_run_integrity_check tool in Claude Desktop.</div></Card>
      ) : (
        data.integrity_checks.map((c,i)=>(
          <Card key={i} style={{borderLeft:`3px solid ${c.chain_valid?"#22c55e":"#ef4444"}`}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
              <div style={{fontSize:15,fontWeight:500,color:c.chain_valid?"#22c55e":"#ef4444"}}>
                {c.chain_valid ? "✅ Chain Valid" : "❌ Chain Invalid"}
              </div>
              <div style={{fontSize:12,color:"#555"}}>{c.check_timestamp?.substring(0,19)}</div>
            </div>
            {[["Events Verified", c.events_verified],["Tamper Detected", c.tamper_detected?"YES — ALERT":"No"],["Integrity Hash", c.integrity_hash]].map(([k,v])=>(
              <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid #1e2030",fontSize:12}}>
                <span style={{color:"#555"}}>{k}</span>
                <span style={{color:k==="Tamper Detected"&&v.includes("YES")?"#ef4444":"#e2e2e2",fontFamily:k.includes("Hash")?"monospace":"inherit"}}>{String(v)}</span>
              </div>
            ))}
          </Card>
        ))
      )}
    </div>
  )
}
