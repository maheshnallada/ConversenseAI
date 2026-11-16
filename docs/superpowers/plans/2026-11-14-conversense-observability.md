# Conversense Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align technical interaction timelines, playback/timing/usage metrics, APIs and dashboard with the observability design while removing out-of-design local ingestion flows.

**Architecture:** Keep the canonical interaction model and local SQLAlchemy artifact/SQLite development setup. Persist idempotent supplied events and artifact references, derive only evidence-supported per-call metrics with versioned calculations, and expose observability separately from the batched evaluation results produced by the evaluation plan. Do not introduce queues, object storage, platform telemetry or background workers.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, pytest, React, Vite.

**Spec:** `docs/superpowers/specs/2026-11-14-conversense-evaluation-observability-design.md`

**Prerequisite:** Complete `docs/superpowers/plans/2026-11-14-conversense-batched-evaluation.md` through its API contract task before implementing the combined analytics/UI tasks.

## Global Constraints

- The supplied transcript is immutable ground truth; audio is only an optional human-review artifact.
- Missing/unreliable timestamps and absent playback metadata produce null, unknown or unavailable results.
- Playback contradictions must be surfaced, not silently resolved.
- Latency, duration, silence and overlap require reliable supplied timestamps.
- Missing provider usage or pricing is unavailable; estimates must identify their rate-card version.
- Do not report queue depth, oldest-message age, worker utilization, DLQ or external telemetry when those sources are not present.
- Keep technical observability separate from semantic evaluation in models, API responses and dashboard sections.
- Reuse the existing tenant-scoped API boundary; do not add a new role system or broaden artifact access.
- Remove out-of-design folder-path processing, ZIP/file upload, dataset seeding and evaluator-configuration surfaces; retain canonical interactions, human review and golden-set benchmarking.
- Do not add RabbitMQ, object-storage migration, OpenTelemetry/Prometheus/Grafana, a migration framework or a new database server.
- Preserve existing interaction payloads and historical evaluation rows; do not delete or rewrite persisted data during schema initialization.

## Review Focus

- Duplicate event IDs with identical versus conflicting payloads must be idempotent versus conflict; pin this in Task 1.
- Transcript turns with missing/unknown speaker labels or timestamps must remain traceable and mark data quality unknown; pin this in Tasks 1-2.
- Playback says `not_played` while heard text exists, or `cut` conflicts with complete delivery; preserve mismatch state and review flag in Task 2.
- Missing model usage or unpriced model must not produce zero or a default estimate; pin this in Task 3.
- Tenant A must not retrieve tenant B's events, timeline, artifact references or audio; pin this in Task 4.

---

### Task 1: Persist canonical events and register artifact references

**Files:**
- Modify: `backend/app/storage/orm.py`
- Create: `backend/app/storage/event_repo.py`
- Create: `backend/app/storage/artifact_reference_repo.py`
- Modify: `backend/app/storage/transcript_repo.py`
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/domain/envelope.py`
- Test: `backend/tests/test_interaction_events_api.py`
- Test: `backend/tests/test_artifact_store.py`

**Interfaces:**
- Produces `POST /api/v1/interactions/{interaction_id}/events` for idempotent event append. Duplicate event ID plus same payload is a no-op; same ID plus different payload returns 409.
- Event rows are unique on `(tenant_id, interaction_id, event_id)` and preserve original event type, timestamp and payload.
- Artifact references are persisted separately from local artifact-file metadata so optional hash/media fields remain optional and no byte upload is added.
- For `event_type="transcript.turn"`, `payload` uses `turn_id`, `turn_index`, `speaker`, `raw_text`, optional `normalized_text`, `start_s`, `end_s`, `duration_s`, `playback_spoken`, `playback_heard_text`, `audio_s`, `barged_in` and `metadata`; map these to the existing `TranscriptTurn`/`TurnRow` without changing source text.
- Produces `POST /api/v1/interactions/{interaction_id}/artifacts` to register references/metadata only; it does not upload bytes.
- Every read/write is tenant-scoped and requires an existing canonical interaction.

- [ ] **Step 1: Write failing tests** for valid transcript-turn event persistence, original line/text preservation, identical duplicate replay, conflicting duplicate 409, unknown event type preservation, artifact metadata registration and missing interaction/tenant isolation.
- [ ] **Step 2: Run `tests\test_interaction_events_api.py` and confirm failures** show missing routes/storage.
- [ ] **Step 3: Implement event and artifact repositories plus tenant-scoped endpoints.** Use a unique constraint for event idempotency; persist transcript-turn payloads in the existing turn repository without deriving transcript text from audio.
- [ ] **Step 4: Run focused event and artifact tests and confirm they pass.**
- [ ] **Step 5: Commit** as `feat: persist canonical interaction events`.

### Task 2: Correct timeline reconciliation and per-interaction metrics

**Files:**
- Modify: `backend/app/domain/observability.py`
- Modify: `backend/app/domain/timeline.py`
- Modify: `backend/app/reconstruction/reconciliation.py`
- Modify: `backend/app/reconstruction/failures.py`
- Modify: `backend/app/reconstruction/reconstructor.py`
- Modify: `backend/app/observability/calculator.py`
- Modify: `backend/app/observability/service.py`
- Test: `backend/tests/test_reconciliation.py`
- Test: `backend/tests/test_failure_detection.py`
- Test: `backend/tests/test_metrics_calculator.py`
- Test: `backend/tests/test_timeline_reconstructor.py`

**Interfaces:**
- Produces `calculate_interaction_metrics(..., calculation_version) -> InteractionMetrics` with playback counts/mismatches, timing samples/percentiles, call duration, turn/speaker/timestamp quality and usage/cost availability.
- Produces a separate timeline reconciliation result with source evidence and unknown/review state.
- Consumes `TranscriptTurn`, supplied `InteractionEvent` records and existing recording metadata; no folder path is required for per-interaction derivation.

- [ ] **Step 1: Write failing tests** for reliable versus absent timestamps, overlapping turns (no negative sequential latency), `heard`/`cut`/`not_played`/`no_audio`, conflicting `not_played` plus heard text, `cut` with complete exact heard text, transcript presence without playback proof, absent agent turns without proof of missing audio, and first-agent latency remaining a metric only.
- [ ] **Step 2: Run the focused reconciliation, failure and metric tests and confirm failures** identify unsupported inferences in current logic.
- [ ] **Step 3: Implement the corrected reconciliation and calculations** using only supplied evidence. Retain all supported failure candidates; order by reliable timestamp and original sequence, and return unknown if ordering cannot be established.
- [ ] **Step 4: Run the focused tests and confirm they pass.**
- [ ] **Step 5: Commit** as `fix: keep observability evidence grounded`.

### Task 3: Persist versioned observability and expose analytics

**Files:**
- Modify: `backend/app/storage/observability_repo.py`
- Modify: `backend/app/observability/config.py`
- Modify: `configs/rate_cards.json`
- Modify: `backend/app/analytics/service.py`
- Modify: `backend/app/api/app.py`
- Test: `backend/tests/test_observability_repo.py`
- Test: `backend/tests/test_analytics_api.py`
- Test: `backend/tests/test_analytics_service.py`
- Test: `backend/tests/test_rate_card_cost.py`

**Interfaces:**
- Produces `GET /api/v1/interactions/{interaction_id}/observability`.
- Produces `GET /api/v1/analytics/overview`, `GET /api/v1/analytics/reliability` and `GET /api/v1/analytics/usage`.
- Persist calculation version, metric values, units/source, availability, playback/data-quality reconciliation and rate-card version in the existing metrics JSON payload; do not require new columns on existing tables.
- Usage totals include provider-reported evaluation batch tokens from the evaluation plan; price estimates use only a configured model/provider rate. Missing values remain unavailable.

- [ ] **Step 1: Write failing persistence/API tests** for versioned per-call metrics, tenant separation, available/unavailable fields, reliability from persisted statuses/events only, and usage with absent/unpriced provider data.
- [ ] **Step 2: Write failing cost tests** for configured rate-card version, invalid/missing rates and unpriced models; assert no hard-coded fallback rate is used.
- [ ] **Step 3: Run the focused tests and confirm they fail** against current table/analytics routes and rate-card fallback behavior.
- [ ] **Step 4: Implement persistence, versioned rate-card validation and three analytics endpoints.** Add a version field to `configs/rate_cards.json`; when pricing data is invalid or absent, return unavailable rather than a default estimate.
- [ ] **Step 5: Run the focused observability, analytics and cost tests and confirm they pass.**
- [ ] **Step 6: Commit** as `feat: expose versioned observability analytics`.

### Task 4: Align interaction detail and dashboard with both result models

**Files:**
- Modify: `frontend/src/views/OverviewView.jsx`
- Modify: `frontend/src/views/DrillDownView.jsx`
- Modify: `frontend/src/views/InteractionsView.jsx`
- Modify: `frontend/src/components/TimelineTurnCard.jsx`
- Modify: `frontend/src/components/TimelineMarker.jsx`
- Modify: `frontend/src/api/client.js`
- Test: `backend/tests/test_dashboard_integration.py`
- Test: `backend/tests/test_ui_static.py`

**Interfaces:**
- Overview reads operational overview, reliability and usage analytics; it does not combine them with semantic batch assessments.
- Interaction detail reads the canonical interaction, timeline, observability detail, latest evaluation run and reviews as separate sections.
- Playback/detail UI marks uncertain or contradictory delivery metadata and never infers ?heard? from transcript presence.
- List filters support date range, use case, processing status, outcome and error state; tenant scope continues to come from the request header.

- [ ] **Step 1: Write failing dashboard integration assertions** for separate observability/evaluation sections, unavailable metrics, playback mismatch display, new overview/reliability/usage data and date/use-case/error-state list filtering.
- [ ] **Step 2: Run `tests\test_dashboard_integration.py` and `tests\test_ui_static.py` and confirm the old contract fails.**
- [ ] **Step 3: Update interaction-list query parameters, API client calls and dashboard rendering** to the new endpoint/output shapes; remove unsupported latency or audio-success claims where evidence is missing.
- [ ] **Step 4: Run focused dashboard tests and `Set-Location frontend; npm run build`; confirm they pass.**
- [ ] **Step 5: Commit** as `feat: separate observability dashboard views`.

### Task 5: Remove local folder/upload/seed product flows

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/evaluation/service.py`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Modify: `frontend/src/components/Topbar.jsx`
- Modify: `frontend/src/api/client.js`
- Delete: `frontend/src/views/IngestView.jsx`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_dashboard_integration.py`
- Modify: `README.md`

**Interfaces:**
- Remove `POST /api/v1/interactions/process-and-evaluate`, `/upload-zip`, `/upload-files` and `/seed-all`, plus their request DTOs and UI/API-client entry points.
- Remove superseded `/api/v1/interactions-list`, `/api/v1/analytics/quality`, `/api/v1/analytics/cost` and `/api/v1/use-cases`; callers use the documented paginated interactions and overview/reliability/usage surfaces.
- Remove folder-alias resolution and folder-processing methods from `EvaluationService`; canonical interaction IDs remain the only runtime identifiers.
- Keep canonical interaction ingestion, interaction list/detail/timeline, authorized audio review, event/artifact-reference APIs, golden benchmark and human review.
- Remove only now-unused folder-upload helpers after checking references; retain canonical ingestion and dataset utilities that still have supported callers.

- [ ] **Step 1: Write failing route/navigation tests** asserting all listed superseded routes and the ingest tab are absent while canonical interaction ingestion/list, observability, benchmark and review routes remain.
- [ ] **Step 2: Run the focused API/dashboard tests and confirm failures** show the legacy routes/navigation are still present.
- [ ] **Step 3: Remove folder/upload/seed API handlers, folder-alias resolution, obsolete analytics/list/use-case routes, their request models and UI flows**; update README setup to use canonical interaction/event/artifact APIs.
- [ ] **Step 4: Run focused route/dashboard tests and frontend build; confirm canonical flows remain available and obsolete routes return 404.**
- [ ] **Step 5: Commit** as `refactor: remove legacy local ingestion flows`.

### Task 6: Verify observability and end-to-end regression

**Files:**
- Test: `backend/tests/test_observability_repo.py`
- Test: `backend/tests/test_metrics_calculator.py`
- Test: `backend/tests/test_dashboard_integration.py`
- Test: `backend/tests/test_full_dataset_metrics.py`
- Test: `backend/tests/test_full_dataset_reconstruction.py`

- [ ] **Step 1: Run all focused event, timeline, observability, analytics and dashboard tests** with the in-memory SQLite fixture; confirm the checked-in SQLite database is unchanged.
- [ ] **Step 2: Run full backend tests** with `Set-Location backend; .\.venv\Scripts\python.exe -m pytest -q`; confirm all supported flows pass.
- [ ] **Step 3: Run `Set-Location frontend; npm run build`; confirm the Vite build completes and refreshes the FastAPI static bundle.**
- [ ] **Step 4: Commit** as `test: verify observability design alignment`.

## Dependencies and execution order

Task 1 establishes event data inputs. Task 2 derives metrics from those inputs.
Task 3 persists and exposes the results. Task 4 requires the completed
evaluation plan's API and adapts the combined detail dashboard. Task 5 removes
the user-selected obsolete local ingestion flows after canonical paths are
covered by tests. Task 6 is the final regression gate.
