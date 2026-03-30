import { useState, useEffect } from "react"
import { api } from "../hooks/api"
import { Card, Err } from "../components/Card"
import { Activity, Play, CheckCircle2, Shield, AlertTriangle, XCircle, FileText, Bot } from "lucide-react"

export default function ApplicationFlow({ appId }) {
  const [form, setForm] = useState({ applicant_id: "COMP-005", amount: 750000, jurisdiction: "CA" })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const [appState, setAppState] = useState(null)

  // Polling for state while loading
  useEffect(() => {
    let interval;
    if (loading || result) {
      interval = setInterval(() => {
        api.application(appId).then(setAppState).catch(()=>{})
      }, 1000)
    }
    return () => clearInterval(interval)
  }, [loading, result, appId])

  const runPipeline = async () => {
    setLoading(true); setErr(null); setResult(null); setAppState(null)
    try {
      const res = await api.runPipeline({ application_id: appId, ...form })
      if (res.returncode !== 0 && res.error) {
        setErr(res.error || "Execution failed with code " + res.returncode)
      } else {
        setResult(res)
      }
    } catch (e) {
      setErr(e.message)
    }
    setLoading(false)
  }

  const steps = [
    { id: "SUBMITTED", label: "Application Submitted", icon: FileText },
    { id: "DOCUMENTS", label: "Document Processing", icon: Bot },
    { id: "CREDIT", label: "Credit Analysis", icon: Activity },
    { id: "FRAUD", label: "Fraud Detection", icon: Shield },
    { id: "COMPLIANCE", label: "Compliance Check", icon: CheckCircle2 },
    { id: "DECISION", label: "Decision Orchestration", icon: Play },
  ]

  const getCurrentStepIndex = () => {
    if (!appState) return -1
    if (appState.state === "SUBMITTED") return 0
    if (appState.state === "PENDING_HUMAN_REVIEW" || appState.final_decision) return 5
    return 3 // intermediate mock
  }

  const currIdx = getCurrentStepIndex()

  return (
    <div className="animate-in">
      <div style={{marginBottom:24,display:"flex",justifyContent:"space-between",alignItems:"flex-end"}}>
        <div>
          <h1 className="brand-font" style={{fontSize:28,fontWeight:700,color:"#fff",letterSpacing:"-0.02em"}}>End-to-End Flow</h1>
          <p style={{fontSize:14,color:"var(--muted)",marginTop:6}}>Submit an application and watch the agents process it sequentially.</p>
        </div>
        <div style={{background:"rgba(167,139,250,0.1)",padding:"6px 16px",borderRadius:20,border:"1px solid rgba(167,139,250,0.3)",color:"var(--purple)",fontSize:13,fontWeight:600}}>
          Target Application: {appId}
        </div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 340px",gap:24,alignItems:"start"}}>
        <Card title="Agent Processing Pipeline" style={{display:"flex",flexDirection:"column",gap:16}}>
          
          <div style={{display:"grid",gridTemplateColumns:"repeat(6, 1fr)",gap:12,marginBottom:20,marginTop:10}}>
            {steps.map((step, i) => {
              const active = currIdx >= i
              const current = currIdx === i && loading
              return (
                <div key={step.id} style={{display:"flex",flexDirection:"column",alignItems:"center",gap:8,position:"relative"}}>
                  {i < steps.length - 1 && (
                    <div style={{position:"absolute",top:20,left:"50%",width:"100%",height:2,background:active?"var(--purple)":"var(--border)",zIndex:0}} />
                  )}
                  <div style={{
                    position:"relative",zIndex:1,width:40,height:40,borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center",
                    background:active?"var(--purple)":"var(--bg-card)",border:`2px solid ${active?"var(--purple)":"var(--border)"}`,
                    color:active?"#fff":"var(--muted)",boxShadow:current?"0 0 15px var(--purple)":""
                  }}>
                    <step.icon size={20} />
                  </div>
                  <div style={{fontSize:11,color:active?"#fff":"var(--muted)",textAlign:"center",fontWeight:active?500:400}}>{step.label}</div>
                  {current && <div style={{fontSize:10,color:"var(--purple)",animation:"pulse 1.5s infinite"}}>processing...</div>}
                </div>
              )
            })}
          </div>

          <div style={{background:"rgba(0,0,0,0.2)",border:"1px solid var(--border)",borderRadius:8,padding:16}}>
            <div style={{fontSize:14,color:"#fff",fontWeight:600,marginBottom:12}}>Application State</div>
            {appState ? (
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:16}}>
                <div>
                  <div style={{fontSize:11,color:"var(--muted)",marginBottom:2}}>Applicant</div>
                  <div style={{fontSize:16,color:"#fff"}}>{appState.applicant_id}</div>
                </div>
                <div>
                  <div style={{fontSize:11,color:"var(--muted)",marginBottom:2}}>Amount Requested</div>
                  <div style={{fontSize:16,color:"#fff"}}>${Number(appState.requested_amount_usd||0).toLocaleString()}</div>
                </div>
                <div>
                  <div style={{fontSize:11,color:"var(--muted)",marginBottom:2}}>Final Decision</div>
                  <div style={{
                    fontSize:14,fontWeight:600,display:"inline-block",padding:"4px 12px",borderRadius:4,
                    background:appState.final_decision==="APPROVED"?"rgba(34,197,94,0.1)":appState.final_decision==="DECLINED"?"rgba(239,68,68,0.1)":"rgba(245,158,11,0.1)",
                    color:appState.final_decision==="APPROVED"?"var(--green)":appState.final_decision==="DECLINED"?"var(--red)":"var(--amber)",
                    border:`1px solid ${appState.final_decision==="APPROVED"?"var(--green)":appState.final_decision==="DECLINED"?"var(--red)":"var(--amber)"}`
                  }}>
                    {appState.final_decision || "PENDING"}
                  </div>
                </div>
              </div>
            ) : <div style={{fontSize:13,color:"var(--muted)"}}>No application data yet. Submit to begin.</div>}
          </div>

          {result && (
            <div style={{background:"rgba(0,0,0,0.4)",border:"1px solid var(--border)",borderRadius:8,padding:16,height:300,overflowY:"auto"}}>
              <div style={{fontSize:12,color:"var(--green)",marginBottom:8,fontWeight:600}}>Pipeline Execution Output:</div>
              <pre style={{fontSize:12,color:"#a3a8cc",fontFamily:"monospace",whiteSpace:"pre-wrap"}}>{result.output}</pre>
            </div>
          )}
          {err && <Err msg={err} />}

        </Card>

        <Card title="Submit New Application">
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <div>
              <div style={{fontSize:12,color:"var(--muted)",marginBottom:6}}>Applicant ID</div>
              <input value={form.applicant_id} onChange={e=>setForm({...form,applicant_id:e.target.value})}
                style={{width:"100%",background:"rgba(0,0,0,0.5)",border:"1px solid var(--border)",borderRadius:6,padding:"10px 12px",color:"#fff",fontSize:14,transition:"border 0.2s"}}
                onFocus={e=>e.target.style.borderColor="var(--purple)"} onBlur={e=>e.target.style.borderColor="var(--border)"} />
            </div>
            <div>
              <div style={{fontSize:12,color:"var(--muted)",marginBottom:6}}>Requested Amount (USD)</div>
              <input type="number" value={form.amount} onChange={e=>setForm({...form,amount:Number(e.target.value)})}
                style={{width:"100%",background:"rgba(0,0,0,0.5)",border:"1px solid var(--border)",borderRadius:6,padding:"10px 12px",color:"#fff",fontSize:14,transition:"border 0.2s"}}
                onFocus={e=>e.target.style.borderColor="var(--purple)"} onBlur={e=>e.target.style.borderColor="var(--border)"} />
            </div>
            <div>
              <div style={{fontSize:12,color:"var(--muted)",marginBottom:6}}>Jurisdiction</div>
              <select value={form.jurisdiction} onChange={e=>setForm({...form,jurisdiction:e.target.value})}
                style={{width:"100%",background:"rgba(0,0,0,0.5)",border:"1px solid var(--border)",borderRadius:6,padding:"10px 12px",color:"#fff",fontSize:14,transition:"border 0.2s",outline:"none"}}>
                <option value="CA">California (CA)</option>
                <option value="NY">New York (NY)</option>
                <option value="MT">Montana (MT)</option>
                <option value="EU">Europe (EU)</option>
              </select>
            </div>
            
            <button onClick={runPipeline} disabled={loading} className="btn-primary" style={{marginTop:8,padding:"12px 0",fontSize:15,fontWeight:600,display:"flex",alignItems:"center",justifyContent:"center",gap:8}}>
              {loading ? <div style={{width:18,height:18,border:"2px solid #fff",borderTopColor:"transparent",borderRadius:"50%",animation:"spin 1s linear infinite"}}/> : <Play size={18} fill="currentColor" />}
              {loading ? "Running Agents..." : "Run AI Pipeline"}
            </button>
            <div style={{fontSize:11,color:"var(--amber)",textAlign:"center",marginTop:4}}>
              Note: The pipeline executes fully in the background. It may take 10-15s to complete all agent orchestrations.
            </div>
          </div>
        </Card>
      </div>
      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
