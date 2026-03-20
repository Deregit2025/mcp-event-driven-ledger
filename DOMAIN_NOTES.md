# DOMAIN_NOTES.md — The Ledger: Agentic Event Store & Enterprise Audit Infrastructure

---

## Question 1: EDA vs ES Distinction

**Scenario:** A component uses callbacks (like LangChain traces) to capture event-like data. Is this Event-Driven Architecture (EDA) or Event Sourcing (ES)? If you redesigned it using The Ledger, what exactly would change in the architecture and what would you gain?

**Answer:**

A component using callbacks to capture event-like data is **Event-Driven Architecture (EDA)**, not Event Sourcing (ES). The distinction is fundamental and often misunderstood.

In EDA, events are **messages** — they are fired from a source, consumed by a listener, and then discarded. The LangChain trace callback fires when an LLM chain step completes. A listener receives it, perhaps logs it or sends it to a monitoring service. If the listener is down, the event is lost. If the process restarts, there is no record of what happened. The events are ephemeral communication channels, not the system's source of truth. The actual state of the system lives somewhere else — in a database, in memory, in a file.

In Event Sourcing, events are **facts** — they are the database. The events table IS the source of truth. Nothing is ever deleted or updated. The current state of any aggregate is derived by replaying its event stream from position 0. If the process restarts, the agent loads its full history from the event store and continues exactly where it left off. This is the Gas Town pattern.

**What exactly would change if redesigned using The Ledger:**

*Before (EDA with callbacks):*
- LangChain fires `on_chain_start`, `on_llm_end`, `on_tool_end` callbacks
- A callback handler receives them and writes to a log file or sends to a monitoring API
- If the process crashes mid-chain, the partial execution is lost
- On restart, the agent starts fresh with no memory of prior work
- The callback data is never used to reconstruct agent state
- Two concurrent agents can make conflicting decisions with no detection

*After (ES with The Ledger):*
- Before executing any action, the agent calls `start_agent_session` — this writes `AgentContextLoaded` to the store as the first event
- Every agent action writes a domain event to the store BEFORE being executed: `CreditAnalysisCompleted`, `FraudScreeningCompleted`, `AgentDecisionContributed`
- If the process crashes, the agent calls `reconstruct_agent_context()` which replays the stream and rebuilds exact context — including pending work and partial decisions
- Two concurrent agents attempting to write to the same stream are serialised by optimistic concurrency control — exactly one wins, the other receives `OptimisticConcurrencyError` with `suggested_action: reload_stream_and_retry`
- Every event is permanently stored, cryptographically hashed into the audit chain, and queryable at any point in time

**What you gain:**
- **Crash recovery** — the agent stream IS the agent's memory. No cold starts.
- **Auditability** — every decision is permanently recorded with the model version, input data hash, and confidence score that produced it.
- **Concurrency safety** — optimistic concurrency control prevents split-brain state.
- **Temporal queries** — "what did this agent know at 14:32:07?" is answerable by replaying to that timestamp.
- **Regulatory compliance** — the cryptographic hash chain makes tampering detectable.

The architectural shift is from "events as notifications" to "events as the database." This is not an incremental improvement — it is a different storage paradigm.

---

## Question 2: The Aggregate Question

**Scenario:** In the Apex Financial implementation, four aggregates were built. Identify one alternative boundary you considered and rejected. What coupling problem does your chosen boundary prevent?

**Answer:**

**The alternative boundary considered and rejected:** Merging `ComplianceRecord` into `LoanApplication` as a single aggregate with stream ID `loan-{application_id}`.

This is the intuitive first design. A loan application has compliance checks — why not put them in the same stream? The `LoanApplication` aggregate already needs to know whether compliance is cleared before it can approve. Putting them together seems to simplify the cross-stream dependency.

**Why it was rejected — the coupling problem it would cause:**

The `LoanApplication` stream and the `ComplianceRecord` stream have fundamentally different write concurrency profiles.

In the Apex scenario, when a compliance review begins, the compliance agent evaluates multiple rules concurrently. Under `APRA-2026-Q1`, there are three mandatory checks: `AML-001`, `KYC-002`, and `CREDIT-003`. A production compliance system runs these in parallel — three concurrent evaluation tasks, each appending `ComplianceRulePassed` or `ComplianceRuleFailed` as they complete.

If compliance events lived on `loan-{application_id}`, all three concurrent compliance writes would contend for the same stream version. With optimistic concurrency control, this is guaranteed to produce conflicts:

- Compliance task A reads stream at version 3, appends `ComplianceRulePassed(AML-001)` at version 4 ✅
- Compliance task B reads stream at version 3, tries to append at version 4 → `OptimisticConcurrencyError`
- Compliance task B reloads at version 4, appends at version 5 ✅
- Compliance task C reads stream at version 3, tries to append at version 4 → `OptimisticConcurrencyError`
- Compliance task C reloads at version 5, appends at version 6 ✅

Three concurrent compliance checks produce two guaranteed concurrency conflicts, each requiring a reload and retry. At the same time, the credit analysis agent is also trying to append `CreditAnalysisCompleted` to the same `loan-{id}` stream, adding a third source of contention. The fraud screening agent adds a fourth.

This is O(N²) concurrency conflicts for N concurrent agents on the same application — a cascade of retries that degrades throughput as the number of agents increases.

**What the chosen boundary prevents:**

By separating `ComplianceRecord` onto its own `compliance-{application_id}` stream, the three concurrent compliance writes contend only with each other on the compliance stream, while credit and fraud analysis writes go to the loan stream. Zero cross-aggregate write contention.

The `LoanApplication` aggregate still enforces the compliance dependency (business rule 5) by checking for `ComplianceClearanceIssued` at decision time — but this check is a read, not a write, and reads never cause concurrency conflicts.

This is the correct aggregate boundary: group events that must be mutually consistent under concurrent writes; separate events whose concurrent writes would otherwise contend unnecessarily.

---

## Question 3: Concurrency in Practice

**Scenario:** Two AI agents simultaneously process the same loan application and both call `append_events` with `expected_version=3`. Trace the exact sequence of operations. What does the losing agent receive, and what must it do next?

**Answer:**

**Exact sequence of operations in the event store:**

Both agents have loaded the `loan-{application_id}` stream and observed `current_version=3`. Both have computed their `CreditAnalysisCompleted` events and are now calling `store.append()` concurrently.

The `EventStore.append()` method enters `_append_in_transaction()` which executes under a PostgreSQL transaction:

**Step 1 — Stream row locking:**
```sql
SELECT current_version, archived_at 
FROM event_streams 
WHERE stream_id = 'loan-app-abc123' 
FOR UPDATE
```

PostgreSQL's row-level lock means only ONE agent can hold this lock at a time. Agent A acquires it first. Agent B blocks at this SELECT, waiting.

**Step 2 — Agent A proceeds (the winner):**
- Agent A reads `current_version=3`, which matches `expected_version=3` ✅
- Agent A inserts its event at `stream_position=4`:
  ```sql
  INSERT INTO events (stream_id, stream_position, event_type, ...) 
  VALUES ('loan-app-abc123', 4, 'CreditAnalysisCompleted', ...)
  ```
- Agent A updates the stream version:
  ```sql
  UPDATE event_streams SET current_version = 4 WHERE stream_id = 'loan-app-abc123'
  ```
- Agent A writes its outbox entry
- Agent A commits the transaction
- Agent A releases the row lock

**Step 3 — Agent B acquires the lock:**
Agent B's blocked `SELECT FOR UPDATE` now proceeds. It reads `current_version=4`.

**Step 4 — Version mismatch detected:**
Agent B compares `current_version=4` against `expected_version=3`. They do not match. Agent B raises `OptimisticConcurrencyError`:
```python
OptimisticConcurrencyError(
    stream_id="loan-app-abc123",
    expected_version=3,
    actual_version=4,
)
```

Agent B rolls back its transaction (the INSERT never happened). The outbox entry for Agent B is also rolled back — guaranteed by the same transaction.

**What the losing agent receives:**

A structured error object:
```json
{
  "error_type": "OptimisticConcurrencyError",
  "message": "Concurrency conflict on stream 'loan-app-abc123': expected version 3, found 4",
  "stream_id": "loan-app-abc123",
  "expected_version": 3,
  "actual_version": 4,
  "suggested_action": "reload_stream_and_retry"
}
```

**What the losing agent must do next:**

The losing agent must:

1. **Reload the stream** — call `store.load_stream('loan-app-abc123')` to get the current state including Agent A's newly appended event at position 4.

2. **Reconstruct aggregate state** — replay all 4 events through `LoanApplicationAggregate._apply()` to get the current state.

3. **Re-evaluate business rules** — check whether its analysis is still relevant. Specifically:
   - Has Agent A's credit analysis made Agent B's analysis redundant? If both are credit analysis agents, business rule 3 (model version locking) will reject the second analysis unless a `HumanReviewOverride` has been issued.
   - If Agent B is a fraud screening agent (different analysis type), its analysis is still valid — it should retry the append at `expected_version=4`.

4. **Retry if valid** — call `store.append()` again with `expected_version=4`.

5. **Abandon if invalid** — if the re-evaluation shows the operation is no longer valid (e.g., another agent already completed the same analysis type), Agent B should not retry. It should log the abandonment and allow the application to proceed with Agent A's result.

This is the correct behaviour of optimistic concurrency control: no locks, no deadlocks, no distributed coordination. Conflicts are detected at commit time and resolved by the application logic.

---

## Question 4: Projection Lag and Its Consequences

**Scenario:** The `LoanApplication` projection is eventually consistent with typical lag of 200ms. A loan officer queries "available credit limit" immediately after an agent commits a disbursement event. They see the old limit. What does your system do, and how do you communicate this to the user interface?

**Answer:**

**What the system does:**

The `ApplicationSummary` projection is maintained by the `ProjectionDaemon` which polls the events table every 100ms and processes new events in batches. When an agent commits a `CreditAnalysisCompleted` event with `recommended_limit_usd`, the daemon has not yet processed that event. The projection table still shows the previous state.

When the loan officer queries `ledger://applications/{id}`, the MCP resource reads from `application_summary` — the projection table — not from the event stream. It returns the stale value. This is the intended behaviour for an eventually consistent read model. The system is working correctly; the loan officer is seeing the state as of the last time the daemon processed events.

The `ProjectionDaemon` exposes `get_lag()` which returns the milliseconds between the latest event in the store and the latest event the projection has processed. The health endpoint `ledger://ledger/health` exposes this in real time.

**How the system communicates this to the user interface:**

The MCP resource response includes metadata that the UI should surface to the user. The health endpoint response contains:

```json
{
  "projection_lags_ms": {
    "application_summary": 187
  },
  "slo_definitions": {
    "application_summary": 500
  }
}
```

The UI has three options, ordered by user experience quality:

**Option 1 — Lag indicator (recommended):** Display a "last updated X seconds ago" timestamp derived from the `last_event_at` field in the `application_summary` row. The loan officer sees "Credit limit updated 0.2 seconds ago" and understands the value is current within the SLO.

**Option 2 — Stale warning:** If `lag_ms > 1000` (twice the SLO), display a yellow warning banner: "This data may be up to 1 second out of date. Refresh to get the latest." This is triggered by the health endpoint's `slo_breaches` array becoming non-empty.

**Option 3 — Optimistic read (for critical decisions):** For high-stakes queries like "available credit limit before disbursement," the UI can bypass the projection and load the event stream directly via `ledger://applications/{id}/audit-trail`. This gives the authoritative current state at the cost of higher latency (p99 < 500ms vs p99 < 50ms). This is the justified exception: for decisions where stale data has financial consequences, pay the latency cost for strong consistency.

**What we do NOT do:** We do not hide the eventual consistency from the user. A system that presents stale data as if it were current without any indication is a system that erodes trust when users notice discrepancies. The correct design surfaces the freshness of the data and lets the user decide whether to wait for the projection to catch up.

---

## Question 5: The Upcasting Scenario

**Scenario:** The `CreditDecisionMade` event was defined in 2024 with `{application_id, decision, reason}`. In 2026 it needs `{application_id, decision, reason, model_version, confidence_score, regulatory_basis}`. Write the upcaster. What is your inference strategy for historical events that predate `model_version`?

**Answer:**

**The upcaster implementation:**

```python
from src.upcasting.registry import UpcasterRegistry

registry = UpcasterRegistry()

@registry.register("CreditDecisionMade", from_version=1)
def upcast_credit_decision_v1_to_v2(payload: dict) -> dict:
    """
    CreditDecisionMade v1 (2024) → v2 (2026).
    
    Adds three fields: model_version, confidence_score, regulatory_basis.
    Each field has a different inference strategy justified below.
    """
    return {
        **payload,
        "model_version":    _infer_model_version(payload),
        "confidence_score": None,
        "regulatory_basis": _infer_regulatory_basis(payload),
    }

def _infer_model_version(payload: dict) -> str:
    """
    Inference: tag all pre-2026 events as 'legacy-pre-2026'.
    
    Rationale: We do not know which model version produced any specific
    v1 event. Every v1 event was written before model version tracking
    was mandated. 'legacy-pre-2026' is factually accurate — it tells
    downstream consumers "this decision predates model versioning" rather
    than silently fabricating a version that may be wrong.
    
    Error rate: 0%. This inference is definitionally correct for all v1 events.
    
    Downstream consequence: These events are excluded from model version
    comparison analysis in AgentPerformanceLedger, which is correct — we
    cannot compare a 'legacy' version against v2.3.0 meaningfully.
    """
    return "legacy-pre-2026"

def _infer_regulatory_basis(payload: dict) -> str:
    """
    Inference: 'APRA-2024-inferred' for all v1 events.
    
    Rationale: All v1 events were written in 2024. APRA-2024 was the active
    regulation set. The '-inferred' suffix explicitly marks this as an
    inference, distinguishing it from authoritative values in v2 events.
    
    Error rate: estimated 5% for events near regulation set boundaries
    where a new set came into effect mid-quarter.
    
    Downstream consequence: Low. regulatory_basis is used for filtering and
    grouping compliance reports, not for binary pass/fail decisions. A 5%
    misattribution on historical events is disclosed in audit documentation.
    """
    return "APRA-2024-inferred"
```

**Inference strategy for `model_version` — why NOT null, why NOT fabricate:**

Three strategies were considered:

1. **Fabricate a plausible value** (e.g., guess the model version from the date range): Rejected. A fabricated model version silently corrupts the `AgentPerformanceLedger` metrics — approve rates, confidence averages, and human override rates for the fabricated version would be meaningless. A regulator examining model performance would see phantom data. Fabrication is actively harmful.

2. **Null** (honest absence): Valid for `confidence_score` because confidence is a continuous float used in calculations. A null confidence score in an average calculation correctly signals "this event has no confidence data" whereas a fabricated 0.75 would silently bias the average. Null is the right choice for `confidence_score`.

3. **Sentinel string** (`'legacy-pre-2026'`): The right choice for `model_version` because version is a categorical identifier, not a numeric quantity. A sentinel string correctly communicates "this event belongs to a pre-versioning era" and groups all such events together for analysis. It is factually accurate, not fabricated, and clearly distinguishable from real version strings.

**The core principle:** When inference is uncertain, choose the strategy that makes the uncertainty **visible** rather than the strategy that hides it. Null makes absence visible. A sentinel string makes the pre-versioning era visible. Fabrication hides uncertainty — always reject fabrication.

---

## Question 6: The Marten Async Daemon Parallel

**Scenario:** Marten 7.0 introduced distributed projection execution across multiple nodes. Describe how you would achieve the same pattern in Python. What coordination primitive do you use, and what failure mode does it guard against?

**Answer:**

**Marten's distributed daemon:**

Marten 7.0 uses distributed lock coordination (via PostgreSQL advisory locks) to elect a leader node for each projection. Multiple application instances compete to own a projection's processing. The node that holds the advisory lock for a given projection is the only one allowed to advance that projection's checkpoint. If the leader node dies, another node acquires the lock and resumes from the last committed checkpoint.

**Python equivalent implementation:**

```python
import asyncio
import logging
from src.store.connection import get_connection
from src.projections.base import Projection

logger = logging.getLogger(__name__)

class DistributedProjectionDaemon:
    """
    Multi-node projection daemon using PostgreSQL advisory locks for
    leader election — the Python equivalent of Marten's Async Daemon.
    """
    
    async def run_projection(self, projection: Projection) -> None:
        """
        Compete for the advisory lock for this projection.
        Only the lock holder processes events. Others wait and retry.
        """
        lock_key = self._projection_lock_key(projection.name)
        
        while True:
            async with get_connection() as conn:
                # Try to acquire the advisory lock (non-blocking)
                row = await conn.fetchone(
                    "SELECT pg_try_advisory_lock(%s) AS acquired",
                    (lock_key,)
                )
                if not row["acquired"]:
                    # Another node holds the lock — wait and retry
                    logger.debug(
                        "Projection '%s' lock held by another node — waiting",
                        projection.name
                    )
                    await asyncio.sleep(5.0)
                    continue
                
                # We hold the lock — process events until we lose it or crash
                logger.info(
                    "Acquired leader lock for projection '%s'",
                    projection.name
                )
                try:
                    await self._process_forever(projection, conn)
                finally:
                    # Release the lock on clean shutdown
                    await conn.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (lock_key,)
                    )
    
    def _projection_lock_key(self, projection_name: str) -> int:
        """
        Convert projection name to a stable integer lock key.
        PostgreSQL advisory locks use bigint keys.
        """
        import hashlib
        return int(hashlib.md5(projection_name.encode()).hexdigest()[:8], 16)
```

**Coordination primitive:** `pg_try_advisory_lock()` — a PostgreSQL session-level advisory lock. It is acquired by one connection and automatically released when that connection closes (including on crash). No explicit unlock is needed on failure — this is the key property.

**Failure mode it guards against:** **Dual processing** — two nodes simultaneously advancing the same projection's checkpoint, leading to duplicate event processing and inconsistent projection state.

Without the advisory lock, if two instances of the application start, both run the `ProjectionDaemon`. Both read from `projection_checkpoints`, both process event batch [1..500], both write to `application_summary`. The result is either:
- Duplicate writes (idempotent upserts handle this, but it doubles database load)
- Race conditions on running average calculations in `AgentPerformanceLedger` (not idempotent — `new_avg = (old_avg * n + new_val) / (n+1)` gives wrong results if two nodes simultaneously increment `n`)

The advisory lock ensures exactly one node processes each projection at any time. When the leader node crashes, PostgreSQL releases the advisory lock (because the connection closes), and a follower node acquires it within 5 seconds and resumes from the last committed checkpoint. No events are skipped; some events may be re-processed if the leader crashed after processing but before committing the checkpoint — this is handled by idempotent upsert logic in each projection handler.

**Per-projection checkpointing** (rather than a single global cursor) means each projection can be independently assigned to different nodes, enabling horizontal scaling: ApplicationSummary on node A, ComplianceAuditView on node B, AgentPerformanceLedger on node C.