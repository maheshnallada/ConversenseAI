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

## Interaction ingestion

Submit canonical interaction data using the tenant-scoped API. Transcript turns and optional artifact metadata are appended separately; audio is only a review artifact and is not used to reconstruct transcript text.

```powershell
$headers = @{ "X-Tenant-Id" = "health_campaign" }
$interaction = @{
  tenant_id = "health_campaign"
  interaction_id = "interaction-123"
  schema_version = "1.0"
  use_case = "health_insurance"
  status = "completed"
  started_at = "2026-11-14T08:00:00Z"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/interactions" `
  -Headers $headers -ContentType "application/json" -Body $interaction

$turn = @{
  event_id = "turn-1"
  event_type = "transcript.turn"
  occurred_at = "2026-11-14T08:00:01Z"
  payload = @{
    turn_id = "turn-1"
    turn_index = 1
    speaker = "agent"
    raw_text = "Hello, how can I help?"
    start_s = 0.0
    end_s = 1.2
    playback_spoken = "unknown"
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/interactions/interaction-123/events" `
  -Headers $headers -ContentType "application/json" -Body $turn
```

Use `GET /api/v1/interactions` for paginated interaction search and filtering, and register optional review-artifact metadata at `/api/v1/interactions/{interaction_id}/artifacts`. The API does not accept call-folder paths or ZIP uploads.

## Evaluation workflow

An evaluation run executes three structured batches concurrently:

- `conversation_understanding` — outcome, sentiment, emotion, and customer facts.
- `conversation_quality` — quality dimensions, context-awareness observations, and conversation completeness.
- `compliance_appointment` — never-rule checks and appointment/consent interpretation.

Each persisted run exposes the status and provider error for every batch. A retry can reuse successful batches from an earlier run and rerun failed batches. Review submissions refer to a batch's `evaluation_id`.

Evidence is checked against the exact transcript lines. Non-null quality scores and explicit appointment consent require verified transcript evidence; an empty transcript cannot produce an assessment. Invalid evidence remains reviewable but is excluded from evidence-dependent derivations. A customer-fact batch that extracts a prohibited sensitive identifier is failed and its output is discarded. The dashboard shows structured results, review reasons, and exact quotes; the evaluation contract does not expose a confidence score or a combined numeric score.

Benchmark metrics are calculated from explicit golden labels and the latest versioned runs. Supported dimensions and CSV columns are documented in [docs/GOLDEN_DATASET_FORMAT.md](docs/GOLDEN_DATASET_FORMAT.md); interpretation and availability rules are in [docs/PHASE_7_VALIDATION_BENCHMARK.md](docs/PHASE_7_VALIDATION_BENCHMARK.md).
