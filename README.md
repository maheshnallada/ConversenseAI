# ConversenseAI

ConversenseAI stores canonical voice interactions and evaluates supplied transcripts. The supplied transcript is ground truth; the service does not transcribe audio.

## Run locally

```powershell
Set-Location backend
python -m pip install -e ".[dev]"
python -m pytest
```

`DATABASE_URL` is documented in `.env.example`. Tests use in-memory SQLite. PostgreSQL is the intended deployment database and is not required for local development.

Build the dashboard from the repository root:

```powershell
Set-Location frontend
npm ci
npm run build
```

## Evaluation workflow

An evaluation run executes three structured batches concurrently:

- `conversation_understanding` — outcome, sentiment, emotion, and customer facts.
- `conversation_quality` — quality dimensions, context-awareness observations, and conversation completeness.
- `compliance_appointment` — never-rule checks and appointment/consent interpretation.

Each persisted run exposes the status and provider error for every batch. A retry can reuse successful batches from an earlier run and rerun failed batches. Review submissions refer to a batch's `evaluation_id`.

Evidence is checked against the exact transcript lines. Non-null quality scores and explicit appointment consent require verified transcript evidence; an empty transcript cannot produce an assessment. Invalid evidence remains reviewable but is excluded from evidence-dependent derivations. A customer-fact batch that extracts a prohibited sensitive identifier is failed and its output is discarded. The dashboard shows structured results, review reasons, and exact quotes; the evaluation contract does not expose a confidence score or a combined numeric score.

Benchmark metrics are calculated from explicit golden labels and the latest versioned runs. Supported dimensions and CSV columns are documented in [docs/GOLDEN_DATASET_FORMAT.md](docs/GOLDEN_DATASET_FORMAT.md); interpretation and availability rules are in [docs/PHASE_7_VALIDATION_BENCHMARK.md](docs/PHASE_7_VALIDATION_BENCHMARK.md).
