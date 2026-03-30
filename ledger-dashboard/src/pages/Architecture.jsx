import React from "react"
import { Shield, Database, Zap, GitBranch, Lock, Activity, Wrench, TerminalSquare, AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react"

const ProblemStatement = () => (
  <div style={{ marginBottom: 60 }}>
    <h2 style={{ color: "#fff", fontSize: 24, marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
      <AlertTriangle color="var(--yellow)" /> The Enterprise AI Challenge
    </h2>
    <div style={{ background: "rgba(255, 191, 36, 0.05)", borderLeft: "4px solid var(--yellow)", padding: 32, borderRadius: "0 16px 16px 0", marginBottom: 32 }}>
      <p style={{ color: "#fff", fontSize: 20, fontStyle: "italic", lineHeight: 1.6, margin: 0 }}>
        "Every enterprise AI deployment I've seen fails the same way. Not because the models are bad. Because no one can answer the auditor's question: show me exactly what your AI decided, when, why, and what data it used. That question kills production deployments."
      </p>
    </div>
    
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 24, marginBottom: 32 }}>
      {[
        { title: "In-Memory Fragility", desc: "AI agents make decisions in memory — when the process ends, the decision, the 'thought', and the rationale are gone forever." },
        { title: "No Immutable Record", desc: "There is no cryptographic record of exactly what snapshot of data informed a specific billion-dollar AI decision." },
        { title: "No Temporal Recovery", desc: "Most systems have zero capability to reconstruct state at a precise past point in time for regulatory audit or error correction." },
        { title: "The Regulatory Wall", desc: "Regulators require all of the above — and most current AI systems simply cannot provide it, preventing production deployment." }
      ].map((p, i) => (
        <div key={i} style={{ padding: 20, background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 12 }}>
          <div style={{ color: "var(--yellow)", fontWeight: 700, fontSize: 13, textTransform: "uppercase", marginBottom: 8, letterSpacing: "0.05em" }}>{p.title}</div>
          <p style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.5, margin: 0 }}>{p.desc}</p>
        </div>
      ))}
    </div>

    <div style={{ textAlign: "center", padding: "20px 0" }}>
      <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 3, marginBottom: 12 }}>The Pivot</div>
      <div style={{ fontSize: 28, color: "#fff", fontWeight: 700 }}>
        "I built the infrastructure that fixes this <span style={{ color: "var(--purple)" }}>permanently</span>. It's called <span style={{ borderBottom: "1px solid var(--purple)" }}>The Ledger</span>."
      </div>
    </div>
  </div>
)

const SolutionOverview = () => (
  <div style={{ marginBottom: 60 }}>
    <h2 style={{ color: "#fff", fontSize: 24, marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
      <CheckCircle2 color="var(--green)" /> The Solution: Production-Grade Infrastructure
    </h2>
    <div style={{ background: "rgba(167, 139, 250, 0.05)", border: "1px solid var(--purple)", padding: 40, borderRadius: 20, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: -20, right: -20, opacity: 0.1 }}><Database size={120} color="var(--purple)" /></div>
      <p style={{ color: "#fff", fontSize: 22, fontWeight: 500, lineHeight: 1.5, marginBottom: 16 }}>
        The Ledger is an event sourcing engine for the Agentic Era.
      </p>
      <div style={{ color: "var(--muted)", fontSize: 16, lineHeight: 1.7, maxWidth: 800 }}>
        Every AI agent decision is an <strong>immutable, timestamped, and cryptographically signed fact.</strong> Nothing is ever deleted or updated. 
        <br/><br/>
        In Apex Ledger, the <strong>History is the Database</strong>. We don't store snapshots; we store the journey.
      </div>
    </div>
  </div>
)

const PipelineFlow = ({ title, steps, color }) => (
  <div style={{ flex: 1, minWidth: 320, background: "rgba(10, 12, 20, 0.4)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
    <div style={{ padding: "16px 24px", background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 12, height: 12, borderRadius: "50%", background: color }} />
      <h3 style={{ margin: 0, fontSize: 16, color: "#fff" }}>{title}</h3>
    </div>
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      {steps.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(255,255,255,0.05)", border: `1px solid ${color}`, display: "flex", alignItems: "center", justifyContent: "center", color: color, fontSize: 12, fontWeight: "bold" }}>
              {i + 1}
            </div>
            {i < steps.length - 1 && <div style={{ width: 1, height: 40, background: "var(--border)", marginTop: 4 }} />}
          </div>
          <div style={{ flex: 1, paddingTop: 4 }}>
            <div style={{ color: "#fff", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{s.label}</div>
            <div style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.5 }}>{s.desc}</div>
            {s.tags && (
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                {s.tags.map((t, ti) => (
                  <span key={ti} style={{ fontSize: 9, padding: "2px 6px", background: "rgba(255,255,255,0.05)", borderRadius: 4, color: color, border: `1px solid ${color}44` }}>{t}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  </div>
)

export default function Architecture() {
  return (
    <div style={{ padding: 40, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 60, textAlign: "center" }}>
        <h1 className="brand-font" style={{ fontSize: 48, marginBottom: 16 }}>System <span style={{ color: "var(--purple)" }}>Architecture</span></h1>
        <p style={{ color: "var(--muted)", fontSize: 18, maxWidth: 800, margin: "0 auto" }}>
          The complete Blueprint of the Apex Ledger event lifecycle. Understanding the bridge between LLM Agent autonomy and financial durability.
        </p>
      </div>

      <ProblemStatement />
      <SolutionOverview />

      <div style={{ marginBottom: 48 }}>
        <h2 style={{ color: "#fff", fontSize: 24, marginBottom: 24 }}>System Architecture Pipeline</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 32 }}>
          <PipelineFlow 
            title="WRITE PATH (Command Pipeline)" 
            color="var(--purple)"
            steps={[
              { label: "Claude Desktop", desc: "Agent generates intent/action.", tags: ["JSON-RPC 2.0 via stdio"] },
              { label: "LedgerMCPServer", desc: "Receives tool call and dispatches to handler.", tags: ["dispatch(tool_name, args)"] },
              { label: "LedgerToolExecutor", desc: "Invokes domain command handler with active store.", tags: ["execute()"] },
              { label: "Command Handlers", desc: "load_stream() ➔ UpcasterRegistry ➔ Aggregate.apply() ➔ Business Rule Check ➔ append().", tags: ["Logic Layer"] },
              { label: "EventStore (Postgres)", desc: "FOR UPDATE stream locking, event sequence insertion, and outbox commit.", tags: ["Optimistic Concurrency Control"] }
            ]}
          />
          <PipelineFlow 
            title="READ PATH (Query Pipeline)" 
            color="var(--green)"
            steps={[
              { label: "Event Store (Postgres)", desc: "Primary source of truth for all historical events.", tags: ["load_all()"] },
              { label: "ProjectionDaemon", desc: "Background process polling events every 100ms.", tags: ["Continuous Sync"] },
              { label: "Projection Tables", desc: "Read-optimized views (ApplicationSummary, ComplianceAudit, Performance).", tags: ["Materialized Views"] },
              { label: "LedgerResourceReader", desc: "Maps ledger:// URIs to projection record sets.", tags: ["Resource Dispatcher"] },
              { label: "Claude Desktop", desc: "Receives raw context grounding for the next agent turn.", tags: ["JSON-RPC Result"] }
            ]}
          />
        </div>
      </div>

      <div style={{ padding: 32, background: "rgba(167, 139, 250, 0.05)", border: "1px solid var(--purple)", borderRadius: 16, textAlign: "center" }}>
        <div style={{ color: "var(--purple)", fontWeight: "bold", fontSize: 12, textTransform: "uppercase", letterSpacing: 2, marginBottom: 12 }}>Key Architectural Differentiator</div>
        <h3 style={{ color: "#fff", fontSize: 20, marginBottom: 16 }}>Zero-Migration Schema Evolution</h3>
        <p style={{ color: "var(--muted)", fontSize: 15, maxWidth: 700, margin: "0 auto", lineHeight: 1.6 }}>
          By separating stored events (facts) from their representation (aggregates), Apex Ledger allows you to change your data structures infinity times without ever running a single SQL `ALTER TABLE` or risking historical data integrity.
        </p>
      </div>
    </div>
  )
}
