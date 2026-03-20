# The Ledger — Weeks 9-10 Starter Code

## Quick Start
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL
docker run -d -e POSTGRES_PASSWORD=apex -e POSTGRES_DB=apex_ledger -p 5432:5432 postgres:16

# 3. Set environment
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

# 4. Generate all data (companies + documents + seed events → DB)
python datagen/generate_all.py --db-url postgresql://postgres:apex@localhost/apex_ledger

# 5. Validate schema (no DB needed)
python datagen/generate_all.py --skip-db --skip-docs --validate-only

# 6. Run Phase 0 tests (must pass before starting Phase 1)
pytest tests/test_schema_and_generator.py -v

# 7. Begin Phase 1: implement EventStore
# Edit: ledger/event_store.py
# Test: pytest tests/test_event_store.py -v
```

## What Works Out of the Box
- Full event schema (45 event types) — `ledger/schema/events.py`
- Complete data generator (GAAP PDFs, Excel, CSV, 1,200+ seed events)
- Event simulator (all 5 agent pipelines, deterministic)
- Schema validator (validates all events against EVENT_REGISTRY)
- Phase 0 tests: 10/10 passing

## What You Implement
| Component | File | Phase |
|-----------|------|-------|
| EventStore | `ledger/event_store.py` | 1 |
| ApplicantRegistryClient | `ledger/registry/client.py` | 1 |
| Domain aggregates | `ledger/domain/aggregates/` | 2 |
| DocumentProcessingAgent | `ledger/agents/base_agent.py` | 2 |
| CreditAnalysisAgent | `ledger/agents/base_agent.py` | 2 (reference given) |
| FraudDetectionAgent | `ledger/agents/base_agent.py` | 3 |
| ComplianceAgent | `ledger/agents/base_agent.py` | 3 |
| DecisionOrchestratorAgent | `ledger/agents/base_agent.py` | 3 |
| Projections + daemon | `ledger/projections/` | 4 |
| Upcasters | `ledger/upcasters.py` | 4 |
| MCP server | `ledger/mcp_server.py` | 5 |

## Gate Tests by Phase
```bash
pytest tests/test_schema_and_generator.py -v  # Phase 0: all must pass before Phase 1
pytest tests/test_event_store.py -v           # Phase 1
pytest tests/test_domain.py -v               # Phase 2
pytest tests/test_narratives.py -v           # Phase 3: all 5 must pass
pytest tests/test_projections.py -v          # Phase 4
pytest tests/test_mcp.py -v                  # Phase 5
```

# The Ledger — Agentic Event Store & Audit Infrastructure

Apex Financial Services loan decisioning platform. Five LangGraph agents. Full event-sourced audit trail. PostgreSQL-backed.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Anthropic API key

---

## Install

```bash
pip install -r requirements.txt
```

---

## Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required variables:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://ledger:ledger@localhost:5432/apex_ledger
TEST_DB_URL=postgresql://ledger:ledger@localhost:5432/apex_ledger_test
DOCUMENTS_DIR=./documents
REGULATION_VERSION=2026-Q1
LOG_LEVEL=INFO
```

---

## Database Setup

Create the databases:

```bash
psql -U postgres -c "CREATE DATABASE apex_ledger;"
psql -U postgres -c "CREATE DATABASE apex_ledger_test;"
psql -U postgres -c "CREATE USER ledger WITH PASSWORD 'ledger';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE apex_ledger TO ledger;"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE apex_ledger_test TO ledger;"
```

Run migrations:

```bash
psql -U ledger -d apex_ledger -f src/schema.sql
psql -U ledger -d apex_ledger_test -f src/schema.sql
```

---

## Seed Data

Run the data generator (once — idempotent):

```bash
python datagen/generate_all.py \
    --applicants 80 \
    --db-url postgresql://ledger:ledger@localhost:5432/apex_ledger \
    --docs-dir ./documents \
    --output-dir ./data \
    --random-seed 42
```

Expected output: 80 companies, 320 documents, 1,847 seed events.

---

## Run Tests

```bash
# Phase 1 — InMemoryEventStore (no DB required)
pytest tests/phase1/ -v

# Concurrency test (mandated)
pytest tests/test_concurrency.py -v

# All tests
pytest tests/ -v
```

---

## Run Pipeline

Process one application end-to-end:

```bash
python scripts/run_pipeline.py --app APEX-0007 --phase document
python scripts/run_pipeline.py --app APEX-0012 --phase credit
```

---

## MCP Server

```bash
python -m ledger.mcp_server
```

Server runs on port 8765 by default.

---

## Project Structure

```
apex-ledger/
├── schema/events.py          # Canonical event schema — never modify
├── agents/                   # LangGraph agents
├── registry/client.py        # Applicant Registry — read-only
├── src/                      # Core implementation
│   ├── schema.sql            # PostgreSQL schema
│   ├── event_store.py        # EventStore + InMemoryEventStore
│   ├── models/events.py      # Re-exports from schema/events.py
│   ├── aggregates/           # Domain aggregates
│   ├── commands/handlers.py  # Command handlers
│   ├── projections/          # Read model projections
│   ├── upcasting/            # Schema evolution
│   ├── integrity/            # Audit chain + Gas Town
│   └── mcp/                  # MCP server
├── tests/                    # Test suite
├── datagen/                  # Data generator
├── scripts/                  # Pipeline + demo scripts
└── artifacts/                # Generated outputs
```