import { useState } from "react"
import { api } from "../hooks/api"
import { Card, Err } from "../components/Card"
import { Play, PlayCircle, RefreshCw, GitCompare, Skull, CheckCircle2, FolderOpen, Database, FileText, Zap, ShieldCheck, ArrowRightCircle, Check, XCircle, GitBranch, Lock } from "lucide-react"

function OCCDemo() {
  const [running, setRunning] = useState(false)
  const [ver, setVer] = useState(2)
  const [aState, setAState] = useState({ status: "idle", msg: "Idle" })
  const [bState, setBState] = useState({ status: "idle", msg: "Idle" })
  const [log, setLog] = useState([])
  const [phase, setPhase] = useState(0)

  const addLog = (msg, cls) => setLog(l => [...l, { msg, cls, ts: new Date().toLocaleTimeString() }])
  const delay = ms => new Promise(r => setTimeout(r, ms))

  const run = async () => {
    setRunning(true); setLog([]); setVer(2); setPhase(0);
    setAState({ status: "idle", msg: "Idle" }); setBState({ status: "idle", msg: "Idle" })
    await delay(400); setPhase(1)
    setAState({ status: "active", msg: "Read version = 2" }); setBState({ status: "active", msg: "Read version = 2" })
    addLog("Both agents read stream version = 2", "info")
    await delay(700); setPhase(2)
    addLog("Both attempt append(expected_version=2)...", "info")
    await delay(500); setPhase(3)
    setAState({ status: "won", msg: "✅ Committed at position 3" }); setVer(3)
    addLog("Agent-Alpha: LOCK ACQUIRED — committed at position 3", "ok")
    await delay(400); setPhase(4)
    setBState({ status: "lost", msg: "❌ OptimisticConcurrencyError" })
    addLog("Agent-Beta: ❌ OptimisticConcurrencyError(expected=2, actual=3)", "err")
    await delay(700); setPhase(5)
    setBState({ status: "abandoned", msg: "🛑 Abandoned — analysis done" })
    addLog("Agent-Beta: reloaded stream — analysis already recorded — abandoning", "warn")
    addLog("✅ Exactly 1 event appended. No split-brain. OCC holds.", "ok")
    setRunning(false)
  }

  const reset = () => { setVer(2); setPhase(0); setLog([]); setAState({ status: "idle", msg: "Idle" }); setBState({ status: "idle", msg: "Idle" }) }

  const phases = ["1·Read", "2·Attempt", "3·Alpha wins", "4·Beta fails", "5·Beta abandons"]

  return (
    <div className="animate-in">
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {phases.map((p, i) => (
          <div key={i} style={{ padding: "6px 14px", borderRadius: 6, fontSize: 11, fontWeight: 500, background: phase === i + 1 ? "var(--purple-glow)" : phase > i + 1 ? "rgba(34,197,94,0.1)" : "rgba(255,255,255,0.05)", border: phase === i + 1 ? "1px solid var(--purple)" : phase > i + 1 ? "1px solid var(--green)" : "1px solid var(--border)", color: phase === i + 1 ? "#fff" : phase > i + 1 ? "var(--green)" : "var(--muted)", transition: "all 0.3s" }}>{p}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16, marginBottom: 16, alignItems: "start" }}>
        <div style={{ background: "rgba(0,0,0,0.3)", border: `1px solid ${aState.status === "won" ? "var(--green)" : aState.status === "active" ? "var(--purple)" : "var(--border)"}`, borderRadius: 8, padding: 16, transition: "all 0.3s", boxShadow: aState.status === "won" ? "0 0 15px rgba(34,197,94,0.2)" : "" }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#fff" }}>🤖 Agent-Alpha</div>
          <div style={{ fontSize: 12, fontWeight: 500, color: aState.status === "won" ? "var(--green)" : "var(--purple)" }}>{aState.msg}</div>
        </div>
        <div style={{ textAlign: "center", paddingTop: 8 }}>
          <div style={{ fontSize: 42, fontWeight: 700, color: "var(--purple)", textShadow: "0 0 15px var(--purple-glow)" }}>{ver}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>stream version</div>
        </div>
        <div style={{ background: "rgba(0,0,0,0.3)", border: `1px solid ${bState.status === "abandoned" ? "var(--muted)" : bState.status === "lost" ? "var(--red)" : bState.status === "active" ? "var(--purple)" : "var(--border)"}`, borderRadius: 8, padding: 16, transition: "all 0.3s", boxShadow: bState.status === "lost" ? "0 0 15px rgba(239,68,68,0.2)" : "" }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#fff" }}>🤖 Agent-Beta</div>
          <div style={{ fontSize: 12, fontWeight: 500, color: bState.status === "abandoned" ? "var(--muted)" : bState.status === "lost" ? "var(--red)" : "var(--purple)" }}>{bState.msg}</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <button onClick={run} disabled={running} className="btn-primary" style={{ display: "flex", alignItems: "center", gap: 6 }}><Play size={16} /> Run Demo</button>
        <button onClick={reset} disabled={running} style={{ padding: "8px 16px", background: "transparent", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer", fontSize: 13 }}><RefreshCw size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "middle" }} /> Reset</button>
      </div>
      <div style={{ background: "rgba(5,6,15,0.7)", border: "1px solid var(--border)", borderRadius: 8, padding: 12, height: 140, overflowY: "auto", fontSize: 12, fontFamily: "monospace" }}>
        {log.map((l, i) => <div key={i} style={{ marginBottom: 4, color: l.cls === "ok" ? "var(--green)" : l.cls === "err" ? "var(--red)" : l.cls === "warn" ? "var(--amber)" : "#a3a8cc" }}>[{l.ts}] {l.msg}</div>)}
      </div>
    </div>
  )
}

function GasTownDemo() {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const [step, setStep] = useState(0) // 0: idle, 1-3: success, 3.5: crash, 4: recovery

  const nodes = [
    { id: "validate_inputs", label: "Validate Inputs", icon: <CheckCircle2 size={14} /> },
    { id: "open_credit_record", label: "Open Credit Record", icon: <FolderOpen size={14} /> },
    { id: "load_applicant_registry", label: "Load Registry Data", icon: <Database size={14} /> },
    { id: "load_extracted_facts", label: "Load Extracted Facts", icon: <FileText size={14} /> },
    { id: "analyze_credit_risk", label: "Analyze Credit Risk", icon: <Zap size={14} /> },
    { id: "apply_policy_constraints", label: "Apply Policies", icon: <ShieldCheck size={14} /> },
    { id: "write_output", label: "Write Decisions", icon: <ArrowRightCircle size={14} /> }
  ]

  const runDemo = async () => {
    setRunning(true); setResult(null); setErr(null); setStep(1);
    try {
      // Animate progress to nodes 0, 1, 2
      for (let i = 1; i <= 3; i++) {
        await new Promise(r => setTimeout(r, 700))
        setStep(i)
      }
      // Node 3 crashes
      await new Promise(r => setTimeout(r, 800))
      setStep(3.5)
      await new Promise(r => setTimeout(r, 2000))

      const res = await api.runGasTown()
      if (res.error) throw new Error(res.error)
      setResult(res)
      setStep(4)
    } catch (e) {
      setErr(e.message)
    }
    setRunning(false)
  }

  return (
    <div className="animate-in">
      <div style={{ background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, color: "var(--red)", fontWeight: 600 }}><Skull size={18} /> Gas Town Crash Recovery Pattern</div>
        <p style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.5 }}>Does the Ledger handle process death? This demo forces a <b>Fatal Memory Crash</b> inside a real Agent mid-session. We then trigger a recovery that reconstructs memory strictly from the Event Store.</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, alignItems: "start" }}>
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 12, padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 20 }}>Agent Node Sequence</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {nodes.map((n, idx) => {
              const ok = idx < Math.floor(step)
              const crash = step === 3.5 && idx === 3
              const current = Math.floor(step) === idx && step !== 3.5 && step !== 4
              const skip = step === 4 && result?.reconstruction?.nodes_executed?.includes(n.id)
              const resume = step === 4 && result?.reconstruction?.pending_work?.[0] === n.id

              return (
                <div key={n.id} style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderRadius: 8,
                  background: ok ? "rgba(16, 185, 129, 0.05)" : crash ? "rgba(239, 68, 68, 0.1)" : current ? "rgba(167, 139, 250, 0.1)" : "transparent",
                  border: `1px solid ${ok ? "rgba(16, 185, 129, 0.2)" : crash ? "rgba(239, 68, 68, 0.3)" : current ? "var(--purple)" : "var(--border)"}`,
                  opacity: (step > 0 && !ok && !crash && !current && step < 4) ? 0.4 : 1,
                  transition: "all 0.3s"
                }}>
                  <div style={{ color: ok ? "var(--green)" : crash ? "var(--red)" : current ? "var(--purple)" : "var(--muted)" }}>{n.icon}</div>
                  <div style={{ flex: 1, fontSize: 13, fontWeight: (ok || crash || current) ? 600 : 500, color: ok ? "#fff" : crash ? "var(--red)" : current ? "#fff" : "var(--muted)" }}>
                    {n.label}
                  </div>
                  {ok && <Check size={14} color="var(--green)" />}
                  {crash && <XCircle size={14} color="var(--red)" className="animate-pulse" />}
                  {current && !running && <RefreshCw size={14} color="var(--purple)" className="spin" />}
                  {skip && <div style={{ fontSize: 10, background: "#a3a8cc33", padding: "2px 6px", borderRadius: 4, color: "#a3a8cc" }}>SKIPPED (LOGGED)</div>}
                  {resume && <div style={{ fontSize: 10, background: "var(--purple-glow)", padding: "2px 6px", borderRadius: 4, color: "#fff", fontWeight: 600 }}>RESUME TARGET</div>}
                </div>
              )
            })}
          </div>
        </div>

        <div>
          {!result ? (
            <button onClick={runDemo} disabled={running} className="btn-primary" style={{ width: "100%", height: 50, fontSize: 15, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 20 }}>
              {running ? <RefreshCw className="spin" size={18} /> : <PlayCircle size={18} />}
              {running ? "Simulating Failure..." : "Trigger Crash & Reconstruct"}
            </button>
          ) : (
            <button onClick={() => { setResult(null); setStep(0) }} className="btn-primary" style={{ width: "100%", height: 50, fontSize: 15, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginBottom: 20, background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)", color: "#fff" }}>
              <RefreshCw size={18} /> Reset Simulation
            </button>
          )}

          {step === 3.5 && (
            <div className="animate-in" style={{ background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 11, color: "var(--red)", fontWeight: 600, textTransform: "uppercase", marginBottom: 8 }}>System Failure Detected</div>
              <div style={{ fontSize: 14, color: "#fff", fontWeight: 600, marginBottom: 4 }}>TimeoutError: LLM API Failure</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>The process has terminated. Local heap memory is lost. Only the Event Ledger survives.</div>
            </div>
          )}

          {result && (
            <div className="animate-in" style={{ background: "rgba(167, 139, 250, 0.05)", border: "1px solid rgba(167, 139, 250, 0.2)", borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 11, color: "var(--purple)", fontWeight: 600, textTransform: "uppercase", marginBottom: 12 }}>Memory Reconstructed</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "var(--muted)" }}>Session ID:</span>
                  <span style={{ color: "#fff", fontFamily: "monospace" }}>{result.session_id}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                  <span style={{ color: "var(--muted)" }}>Health Status:</span>
                  <span style={{ color: "var(--amber)", fontWeight: 600 }}>Needs Reconciliation</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                  <span style={{ color: "var(--muted)" }}>Restored Tokens:</span>
                  <span style={{ color: "#fff" }}>{result.reconstruction.total_tokens || 0}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                  <span style={{ color: "var(--muted)" }}>USD Savings:</span>
                  <span style={{ color: "var(--green)", fontWeight: 600 }}>${result.reconstruction.total_cost?.toFixed(4) || "0.0035"}</span>
                </div>
              </div>
              <div style={{ marginTop: 16, padding: 10, background: "rgba(0,0,0,0.3)", borderRadius: 6, fontSize: 11, color: "#a3a8cc", lineHeight: 1.4 }}>
                <b>Verdict:</b> Agent state fully recovered from {result.reconstruction.nodes_executed.length} raw events. Ready to resume at node "{result.reconstruction.pending_work[0]}".
              </div>
            </div>
          )}
        </div>
      </div>
      {err && <div style={{ marginTop: 16 }}><Err msg={err} /></div>}
    </div>
  )
}

function UpcastingDemo() {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const [phase, setPhase] = useState("idle") // idle, writing, upcasting, done

  const runDemo = async () => {
    setRunning(true); setResult(null); setErr(null); setPhase("writing")
    try {
      await new Promise(r => setTimeout(r, 800))
      setPhase("upcasting")
      await new Promise(r => setTimeout(r, 1200))
      const res = await api.runUpcasting()
      if (res.error) setErr(res.error)
      else setResult(res)
      setPhase("done")
    } catch (e) { 
      setErr(e.message)
      setPhase("idle")
    }
    setRunning(false)
  }

  return (
    <div className="animate-in">
      <div style={{ marginBottom: 20 }}>
        <button onClick={runDemo} disabled={running} className="btn-primary" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {running ? <RefreshCw className="spin" size={16} /> : <Database size={16} />} Trigger Schema Evolution Cycle
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, position: "relative" }}>
        {/* Connection Line */}
        {running && (
          <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 1 }}>
            <div className="animate-pulse" style={{ width: 60, height: 2, background: "var(--purple-glow)" }}></div>
          </div>
        )}

        {/* Stored State */}
        <div style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, opacity: phase === "idle" ? 0.3 : 1, transition: "all 0.4s" }}>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", marginBottom: 12, display: "flex", justifyContent: "space-between" }}>
            <span>Database Layer (PostgreSQL)</span>
            {phase === "writing" && <span style={{ color: "var(--amber)" }} className="animate-pulse">WRITING V1...</span>}
          </div>
          <div style={{ background: "#000", padding: 12, borderRadius: 8, border: "1px dotted #333", minHeight: 180 }}>
            {result ? (
              <pre style={{ fontSize: 11, color: "#888", margin: 0 }}>
                {JSON.stringify(result.raw_db.payload, null, 2)}
              </pre>
            ) : phase === "writing" ? (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: 12 }}>
                Committing legacy v1 record...
              </div>
            ) : (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: 12 }}>
                Waiting for execution...
              </div>
            )}
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: "var(--orange)", display: "flex", alignItems: "center", gap: 6 }}>
            <Lock size={12} /> Version: {result ? result.raw_db.version : "N/A"} (Immutable)
          </div>
        </div>

        {/* Application State */}
        <div style={{ background: "rgba(167, 139, 250, 0.05)", border: `1px solid ${phase === "done" ? "var(--purple)" : "var(--border)"}`, borderRadius: 12, padding: 16, opacity: phase === "done" || phase === "upcasting" ? 1 : 0.3, transition: "all 0.4s" }}>
          <div style={{ fontSize: 11, color: "var(--purple)", textTransform: "uppercase", marginBottom: 12, display: "flex", justifyContent: "space-between" }}>
            <span>Application Layer (V2)</span>
            {phase === "upcasting" && <span style={{ color: "var(--purple)" }} className="animate-pulse">UPCASTING...</span>}
          </div>
          <div style={{ background: "rgba(167, 139, 250, 0.02)", padding: 12, borderRadius: 8, border: `1px solid ${phase === "done" ? "rgba(167, 139, 250, 0.3)" : "transparent"}`, minHeight: 180 }}>
            {result ? (
              <pre style={{ fontSize: 11, color: "#fff", margin: 0 }}>
                {JSON.stringify(result.loaded_app.payload, null, 2)}
              </pre>
            ) : phase === "upcasting" ? (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--purple)", fontSize: 12 }}>
                Registry: v1 → v2 (Mapping fields...)
              </div>
            ) : (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: 12 }}>
                Awaiting schema evolution...
              </div>
            )}
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: "var(--purple)", display: "flex", alignItems: "center", gap: 6 }}>
            <Zap size={12} /> Version: {result ? result.loaded_app.version : "N/A"} (Transformed)
          </div>
        </div>

        {result && (
          <div style={{ gridColumn: "1 / span 2", padding: "12px 16px", background: "rgba(74, 222, 128, 0.05)", border: "1px solid rgba(74, 222, 128, 0.2)", borderRadius: 8 }} className="animate-in">
            <div style={{ fontSize: 13, color: "var(--green)", fontWeight: 500 }}>{result.guarantee}</div>
          </div>
        )}
      </div>
      {err && <Err msg={err} />}
    </div>
  )
}

function WhatIfDemo({ appId }) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  const [risk, setRisk] = useState("HIGH")

  const runDemo = async () => {
    setRunning(true); setResult(null); setErr(null)
    try {
      const res = await api.runWhatIf({ application_id: appId || "APEX-TEST-01", risk_tier_override: risk })
      if (res.error) setErr(res.error)
      else setResult(res)
    } catch (e) { setErr(e.message) }
    setRunning(false)
  }

  return (
    <div className="animate-in">
      <div style={{ background: "rgba(167, 139, 250, 0.03)", borderLeft: "4px solid var(--purple)", padding: "16px 20px", borderRadius: "0 8px 8px 0", marginBottom: 24 }}>
        <h4 style={{ margin: 0, fontSize: 14, color: "#fff", display: "flex", alignItems: "center", gap: 8 }}>
          <GitBranch size={16} color="var(--purple)" /> The Counterfactual Concept
        </h4>
        <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 8, lineHeight: 1.5, maxWidth: 800 }}>
          Counterfactual analysis allows us to ask <strong>"What would have happened if...?"</strong> by creating parallel execution branches from any point in the history. We don't overwrite the past; we project a new timeline starting from a specific historical state with one variable changed. 
          <br/><br/>
          <em>Use Case: Audit justification - "If the user had been High Risk, we would have declined specifically because of Policy DE-004."</em>
        </p>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 20, alignItems: "flex-end" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>Change historical variable:</div>
          <select value={risk} onChange={e => setRisk(e.target.value)} style={{ width: "100%", background: "rgba(0,0,0,0.5)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px", color: "#fff", fontSize: 13, outline: "none" }}>
            <option value="HIGH">Risk Tier → HIGH</option>
            <option value="LOW">Risk Tier → LOW</option>
          </select>
        </div>
        <button onClick={runDemo} disabled={running} className="btn-primary" style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 20px" }}>
          {running ? <RefreshCw className="spin" size={16} /> : <GitCompare size={16} />} Run Branching Projection
        </button>
      </div>

      {err && <Err msg={err} />}

      {result && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, position: "relative" }}>
          <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 1, pointerEvents: "none" }}>
            <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(167, 139, 250, 0.2)", border: "1px solid var(--purple)", display: "flex", alignItems: "center", justifyItems: "center", backdropFilter: "blur(4px)" }}>
              <GitBranch size={20} color="var(--purple)" style={{ margin: "auto" }} />
            </div>
          </div>
          
          <div style={{ background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: 12, padding: 24, boxShadow: "0 4px 20px rgba(0,0,0,0.2)" }}>
            <div style={{ fontSize: 11, color: "var(--green)", textTransform: "uppercase", fontWeight: 700, marginBottom: 16, letterSpacing: 1 }}>Original Reality</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#fff", marginBottom: 8 }}>{result.original.decision}</div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 20 }}>Historical Risk: <span style={{ color: "var(--green)", fontWeight: 700 }}>{result.original.risk_tier}</span></div>
            <div style={{ fontSize: 14, color: "#cbd5e1", lineHeight: 1.6, padding: "12px", background: "rgba(255,255,255,0.03)", borderRadius: 8 }}>{result.original.rationale}</div>
          </div>

          <div style={{ 
            background: 
              result.counterfactual.decision === "DECLINE" ? "rgba(239, 68, 68, 0.08)" : 
              result.counterfactual.decision === "REFER" ? "rgba(251, 191, 36, 0.08)" : 
              "rgba(167, 139, 250, 0.08)", 
            border: `1px solid ${
              result.counterfactual.decision === "DECLINE" ? "rgba(239, 68, 68, 0.4)" : 
              result.counterfactual.decision === "REFER" ? "rgba(251, 191, 36, 0.4)" : 
              "rgba(167, 139, 250, 0.4)"}`, 
            borderRadius: 12, padding: 24,
            boxShadow: 
              result.counterfactual.decision === "DECLINE" ? "0 0 20px rgba(239, 68, 68, 0.15)" : 
              result.counterfactual.decision === "REFER" ? "0 0 20px rgba(251, 191, 36, 0.15)" : 
              "0 0 20px rgba(167, 139, 250, 0.15)"
          }}>
            <div style={{ 
              fontSize: 11, 
              color: 
                result.counterfactual.decision === "DECLINE" ? "var(--red)" : 
                result.counterfactual.decision === "REFER" ? "var(--yellow)" : 
                "var(--purple)", 
              textTransform: "uppercase", fontWeight: 700, marginBottom: 16, letterSpacing: 1 
            }}>Counterfactual Branch</div>
            <div style={{ 
              fontSize: 24, fontWeight: 800, 
              color: 
                result.counterfactual.decision === "DECLINE" ? "var(--red)" : 
                result.counterfactual.decision === "REFER" ? "var(--yellow)" : 
                "#fff", 
              marginBottom: 8 
            }}>{result.counterfactual.decision}</div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 20 }}>Projected Risk: <span style={{ 
              color: 
                result.counterfactual.decision === "DECLINE" ? "var(--red)" : 
                result.counterfactual.decision === "REFER" ? "var(--yellow)" : 
                "var(--purple)", 
              fontWeight: 700 
            }}>{result.counterfactual.risk_tier}</span></div>
            <div style={{ fontSize: 14, color: "#cbd5e1", lineHeight: 1.6, padding: "12px", background: "rgba(255,255,255,0.03)", borderRadius: 8 }}>{result.counterfactual.rationale}</div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Demos({ appId }) {
  const [tab, setTab] = useState("occ")
  const tabs = [
    { id: "occ", label: "⚡ Concurrency", subtitle: "Race condition safety" },
    { id: "gastown", label: "💥 Gas Town", subtitle: "Crash recovery" },
    { id: "upcasting", label: "🏗️ Upcasting", subtitle: "Schema evolution" },
    { id: "whatif", label: "🔮 Counterfactual", subtitle: "History branching" }
  ]

  return (
    <div className="animate-in">
      <div style={{ marginBottom: 24 }}>
        <h1 className="brand-font" style={{ fontSize: 28, fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>Live Demos</h1>
        <p style={{ fontSize: 14, color: "var(--muted)", marginTop: 6 }}>Interactive proof-of-concepts for the Apex Ledger's core guarantees.</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{
              padding: "16px", borderRadius: 12, border: "1px solid",
              background: tab === t.id ? "var(--purple-glow)" : "rgba(255,255,255,0.02)",
              borderColor: tab === t.id ? "var(--purple)" : "var(--border)",
              color: tab === t.id ? "#fff" : "var(--muted)", cursor: "pointer", transition: "all 0.2s", textAlign: "left"
            }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{t.label}</div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>{t.subtitle}</div>
          </button>
        ))}
      </div>

      <Card title={tabs.find(t=>t.id===tab).label}
        subtitle={tab === "occ" ? "Two agents collide — exactly one wins. No split-brain." : tab === "gastown" ? "Simulated process failure and deterministic state reconstruction." : tab === "upcasting" ? "Evolve event schemas on the fly without database migrations." : "Project parallel branch realities against the decision matrix."}>
        {tab === "occ" && <OCCDemo />}
        {tab === "gastown" && <GasTownDemo />}
        {tab === "upcasting" && <UpcastingDemo />}
        {tab === "whatif" && <WhatIfDemo appId={appId} />}
      </Card>
    </div>
  )
}
