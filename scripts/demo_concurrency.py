"""
scripts/demo_concurrency.py
============================
Live demonstration of optimistic concurrency control for the video demo.

Shows two AI agents colliding on the same loan application stream:
  - Both agents read stream at version 3
  - Both attempt to append CreditAnalysisCompleted
  - Exactly one wins
  - The loser receives OptimisticConcurrencyError and retries

Run:
    python scripts/demo_concurrency.py
"""
import asyncio
import time
from src.event_store import InMemoryEventStore, OptimisticConcurrencyError
from src.upcasting.upcasters import registry

APP_ID = "APEX-CONCURRENCY-DEMO"
STREAM_ID = f"credit-{APP_ID}"

# ── HELPERS ───────────────────────────────────────────────────────────────────

def log(agent: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {agent:20s} │ {msg}")

def separator():
    print("─" * 60)

# ── AGENT TASK ────────────────────────────────────────────────────────────────

async def agent_append(
    store: InMemoryEventStore,
    agent_name: str,
    risk_tier: str,
    barrier: asyncio.Barrier,
):
    """
    Simulates an AI agent that:
    1. Reads the current stream version
    2. Waits at a barrier (so both agents are ready simultaneously)
    3. Attempts to append — one wins, one collides
    4. On OptimisticConcurrencyError, reloads and retries
    """
    # Step 1 — Read current version
    version = await store.stream_version(STREAM_ID)
    log(agent_name, f"read stream version = {version}")

    # Step 2 — Wait for both agents to be ready (simulate simultaneous execution)
    log(agent_name, "waiting at barrier — ready to append simultaneously...")
    await barrier.wait()

    event = {
        "event_type": "CreditAnalysisCompleted",
        "event_version": 1,
        "payload": {
            "application_id": APP_ID,
            "agent": agent_name,
            "risk_tier": risk_tier,
            "confidence": 0.85,
        },
    }

    # Step 3 — First attempt
    try:
        await store.append(STREAM_ID, [event], expected_version=version)
        new_ver = await store.stream_version(STREAM_ID)
        log(agent_name, f"✅ SUCCEEDED — appended at stream_position={new_ver}")
        return "won"

    except OptimisticConcurrencyError as e:
        log(agent_name,
            f"⚠️  OptimisticConcurrencyError — "
            f"expected={e.expected}, actual={e.actual}")

        # Step 4 — Reload and retry
        log(agent_name, "reloading stream to check if analysis is still needed...")
        await asyncio.sleep(0.05)  # small backoff

        events = await store.load_stream(STREAM_ID)
        already_analysed = any(
            e.get("event_type") == "CreditAnalysisCompleted"
            for e in events
        )

        if already_analysed:
            log(agent_name,
                "🛑 analysis already recorded by winning agent — abandoning (correct behaviour)")
            return "abandoned"
        else:
            # Retry at new version
            new_ver = await store.stream_version(STREAM_ID)
            await store.append(STREAM_ID, [event], expected_version=new_ver)
            log(agent_name, f"✅ RETRY SUCCEEDED — appended at stream_position={new_ver + 1}")
            return "retried"


# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    store = InMemoryEventStore(upcaster_registry=registry)

    print()
    print("=" * 60)
    print("  APEX LEDGER — Optimistic Concurrency Control Demo")
    print("  Two agents colliding on the same loan application stream")
    print("=" * 60)
    print()

    # Set up stream with 3 prior events (simulating existing stream state)
    separator()
    print("Setting up loan stream with 3 existing events...")
    separator()

    for i, et in enumerate(["ApplicationSubmitted",
                             "CreditAnalysisRequested",
                             "AgentSessionStarted"]):
        ver = await store.stream_version(STREAM_ID)
        await store.append(
            STREAM_ID,
            [{"event_type": et, "event_version": 1,
              "payload": {"application_id": APP_ID}}],
            expected_version=ver,
        )
        log("setup", f"appended {et} → stream_position={i}")

    current_ver = await store.stream_version(STREAM_ID)
    print()
    log("setup", f"stream '{STREAM_ID}' is now at version {current_ver}")
    print()

    # Run two agents simultaneously
    separator()
    print("Launching Agent-Alpha and Agent-Beta simultaneously...")
    print("Both read version=2, both attempt to append CreditAnalysisCompleted")
    separator()
    print()

    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        agent_append(store, "Agent-Alpha", "MEDIUM", barrier),
        agent_append(store, "Agent-Beta",  "HIGH",   barrier),
        return_exceptions=False,
    )

    print()
    separator()
    print("RESULTS")
    separator()

    final_ver = await store.stream_version(STREAM_ID)
    events = await store.load_stream(STREAM_ID)

    print(f"Final stream version : {final_ver}")
    print(f"Total events in stream: {len(events)}")
    print(f"Agent-Alpha outcome  : {results[0]}")
    print(f"Agent-Beta outcome   : {results[1]}")
    print()
    print("Events in stream:")
    for e in events:
        p = e.get("payload", {})
        agent = p.get("agent", "")
        tier  = p.get("risk_tier", "")
        suffix = f" (agent={agent}, risk_tier={tier})" if agent else ""
        print(f"  [{e['stream_position']}] {e['event_type']}{suffix}")

    print()

    # Assertions
    credit_events = [
        e for e in events
        if e["event_type"] == "CreditAnalysisCompleted"
    ]
    assert len(credit_events) == 1, \
        f"FAIL: expected exactly 1 CreditAnalysisCompleted, got {len(credit_events)}"
    assert set(results) == {"won", "abandoned"} or \
           "retried" in results, \
        "FAIL: unexpected outcome combination"

    print("✅ ASSERTION PASSED: exactly one CreditAnalysisCompleted in stream")
    print("✅ No duplicate analysis — OCC prevented split-brain state")
    print()
    print("=" * 60)
    print("  Demo complete — optimistic concurrency working correctly")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())