"""
scripts/demo_upcasting.py
==========================
Step 4 Video Demo — Upcasting & Immutability

Shows:
  STEP 1 — Raw stored event is v1 (no model_versions field)
  STEP 2 — Load through store returns v2 (model_versions added)
  STEP 3 — Raw storage after load is still v1 (UNCHANGED)

Run:
    python scripts/demo_upcasting.py
"""
import asyncio
from src.event_store import InMemoryEventStore
from src.upcasting.upcasters import registry


async def main():
    store = InMemoryEventStore(upcaster_registry=registry)

    print()
    print("=" * 55)
    print("  APEX LEDGER — Upcasting & Immutability Demo")
    print("=" * 55)

    # Store a v1 CreditAnalysisCompleted event
    v1_event = {
        "event_type": "CreditAnalysisCompleted",
        "event_version": 1,
        "payload": {
            "application_id": "APEX-UPCAST-DEMO",
            "model_version": "credit-v2.3.0",
            "decision": {
                "risk_tier": "MEDIUM",
                "confidence": 0.85,
                "rationale": "Strong financials"
            }
        }
    }

    await store.append(
        "credit-APEX-UPCAST-DEMO",
        [v1_event],
        expected_version=-1
    )

    # STEP 1 — raw stored event
    print()
    print("  STEP 1 — Raw stored event (directly from store)")
    print("  " + "-" * 45)
    raw = store._streams["credit-APEX-UPCAST-DEMO"][0]
    print(f"  event_version  : {raw['event_version']}")
    print(f"  payload keys   : {list(raw['payload'].keys())}")
    print(f"  model_versions : {raw['payload'].get('model_versions', '— NOT PRESENT —')}")

    # STEP 2 — load through upcaster
    print()
    print("  STEP 2 — Load through store with UpcasterRegistry")
    print("  " + "-" * 45)
    loaded = await store.load_stream("credit-APEX-UPCAST-DEMO")
    e = loaded[0]
    print(f"  event_version  : {e['event_version']}")
    print(f"  payload keys   : {list(e['payload'].keys())}")
    print(f"  model_versions : {e['payload'].get('model_versions')}")
    print(f"  confidence_score: {e['payload'].get('confidence_score')}")
    print(f"  regulatory_basis: {e['payload'].get('regulatory_basis')}")

    # STEP 3 — raw storage unchanged
    print()
    print("  STEP 3 — Raw storage AFTER load (must be unchanged)")
    print("  " + "-" * 45)
    raw_after = store._streams["credit-APEX-UPCAST-DEMO"][0]
    print(f"  event_version  : {raw_after['event_version']}")
    print(f"  model_versions : {raw_after['payload'].get('model_versions', '— NOT PRESENT —')}")

    # Assertions
    print()
    print("=" * 55)
    print("  ASSERTIONS")
    print("=" * 55)

    assert raw_after["event_version"] == 1, \
        "FAIL: stored event version was mutated!"
    assert e["event_version"] == 2, \
        "FAIL: upcaster did not run!"
    assert "model_versions" in e["payload"], \
        "FAIL: v2 field model_versions missing!"
    assert "model_versions" not in raw_after["payload"], \
        "FAIL: raw storage was modified by upcaster!"

    print()
    print("  ✅ stored version   : v1  (UNCHANGED in database)")
    print("  ✅ loaded version   : v2  (upcasted at read time)")
    print("  ✅ raw after load   : v1  (database never touched)")
    print("  ✅ immutability     : GUARANTEED")
    print()
    print("  The upcaster is a READ-TIME transformation.")
    print("  The database row is NEVER modified.")
    print("  This is the event sourcing immutability guarantee.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    asyncio.run(main())