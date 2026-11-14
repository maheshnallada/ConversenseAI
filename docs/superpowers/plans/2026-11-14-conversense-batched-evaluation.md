# Conversense Batched Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy per-evaluator scoring with three parallel, evidence-validated evaluation batches and auditable deterministic results.

**Architecture:** Keep the existing canonical interaction and synchronous SQLAlchemy service boundary. Use an asynchronous OpenAI-compatible client to run three strict Pydantic batch requests concurrently; persist each run and batch independently, then derive deterministic validation, first-failure and overall assessments. Keep the existing database rows as archival data, not current evaluation results.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, OpenAI async client, pytest, React.

**Spec:** `docs/superpowers/specs/2026-11-14-conversense-evaluation-observability-design.md`

## Global Constraints

- The supplied transcript is immutable ground truth; do not run ASR or regenerate it.
- Evidence quotations must be exact substrings of original lines and preserve original script/spelling.
- Customer facts, sentiment and emotion use customer turns only.
- Missing timestamps, playback metadata, booking events or usage are unknown or unavailable, never evidence of success or failure.
- Missing provider configuration, provider failures, invalid schema or invalid evidence must not silently become heuristic results.
- Independent provider requests run concurrently in the current request-serving process; do not add background jobs or workers.
- Evaluation runs are on-demand; each rerun has a distinct run ID, and batch retries target failed batches only.
- Appointment policy is 09:00 inclusive to 21:00 exclusive; same-day bookings are disallowed; missing local timezone makes the objective check unavailable.
- First-agent response latency is a metric only and does not by itself create a `LATE_AGENT_OPENING` failure.
- Do not add a combined numeric quality score or calibrated confidence.
- Preserve existing historical evaluation rows without exposing them as current batch results or deleting them.
- Preserve human review and golden-set benchmarking; do not add numeric release thresholds for benchmark metrics.
- Do not add RabbitMQ, object-storage migration, platform telemetry, or a new database/migration framework.

## Review Focus

- Multilingual/code-mixed input and exact non-ASCII evidence quotes must survive unchanged. Pin this in Task 3 with exact quote and speaker-validation tests.
- Missing provider configuration, timeout, rate limit, malformed output and one-batch failure must remain visible without erasing successful batches. Pin this in Tasks 2, 4 and 5.
- Ambiguous acknowledgement, refused consent, absent timezone and missing booking events must not be interpreted as a valid appointment. Pin this in Task 4.
- Empty transcripts and missing timestamps must produce unknown/unavailable values rather than fabricated scores or latency. Pin this in Task 4.
- Reruns must not overwrite prior batch evidence, and historical generic rows must not appear as new results. Pin this in Task 5.

---

### Task 1: Define strict batch result schemas and prompts

**Files:**
- Create: `backend/app/evaluation/schemas.py`
- Create: `backend/app/evaluation/prompts.py`
- Test: `backend/tests/test_evaluation_batches.py`

**Interfaces:**
- Produces `ConversationUnderstandingResult`, `ConversationQualityResult`, and `ComplianceAppointmentResult` Pydantic models.
- Produces `BATCH_SYSTEM_PROMPTS` keyed by `conversation_understanding`, `conversation_quality`, and `compliance_appointment`.
- Consumes the exact nested examples, enums and multilingual instructions in `Conversense_AI_Batched_Evaluation_Design.docx`.

- [ ] **Step 1: Write failing schema tests** for all allowed outcome, sentiment, emotion, completeness and compliance values; verify quality scores accept 1-5 or null and reject out-of-range values; verify the batch result fields match the design examples.
- [ ] **Step 2: Run the focused tests and confirm they fail** with missing model/prompt definitions or invalid-value acceptance.

Run: `Set-Location backend; .\.venv\Scripts\python.exe -m pytest tests\test_evaluation_batches.py -q`

Expected: FAIL because the batch models/prompts are not defined yet.

- [ ] **Step 3: Implement the three strict Pydantic result models and stable prompt constants** in the two new modules. Include the shared multilingual block once in each batch system prompt; do not add a fourth overall-evaluation prompt.
- [ ] **Step 4: Run the focused tests and confirm they pass.**
- [ ] **Step 5: Commit** the schema, prompt and tests as `feat: define batched evaluation contracts`.

### Task 2: Add explicit asynchronous structured LLM calls

**Files:**
- Modify: `backend/app/evaluation/llm_client.py`
- Create: `backend/app/evaluation/errors.py`
- Test: `backend/tests/test_llm_client.py`

**Interfaces:**
- Produces `async def complete_structured(messages, response_model) -> BaseModel`.
- Produces typed `LLMConfigurationError`, `LLMRequestError` and `LLMResponseError` failures with model/provider context and no secret values.
- Consumes the result models from Task 1.

- [ ] **Step 1: Write failing async client tests** for missing API key, structured success, timeout/rate-limit exception propagation, empty/malformed responses and secret redaction.
- [ ] **Step 2: Run `tests\test_llm_client.py` and confirm failures** demonstrate the current client returns `None` and hides the failure.
- [ ] **Step 3: Implement the async structured client using `AsyncOpenAI`** and existing endpoint/model/provider environment configuration. Do not catch broad exceptions into `None`; translate only known provider/configuration/parse failures into the typed errors.
- [ ] **Step 4: Run the focused client tests and confirm they pass.**
- [ ] **Step 5: Commit** as `feat: expose structured llm failures`.

### Task 3: Validate evidence against immutable transcript turns

**Files:**
- Create: `backend/app/evaluation/evidence.py`
- Test: `backend/tests/test_evaluation_evidence.py`

**Interfaces:**
- Produces `validate_batch_evidence(batch_name, result, turns) -> ValidationReport`.
- `ValidationReport` contains `schema_valid`, `evidence_valid`, issues and review reasons.
- Consumes the three batch result models from Task 1 and `TranscriptTurn`.

- [ ] **Step 1: Write failing tests** for exact quote acceptance, quote normalization/case changes rejection, unknown line IDs, non-customer evidence on customer-only fields, absent evidence, and original-script/code-mixed text.
- [ ] **Step 2: Run `tests\test_evaluation_evidence.py` and confirm it fails** because the validator does not exist.
- [ ] **Step 3: Implement exact line lookup, speaker checks and case-sensitive substring matching** without changing or normalizing the source transcript.
- [ ] **Step 4: Run the focused evidence tests and confirm they pass.**
- [ ] **Step 5: Commit** as `feat: validate evaluation evidence`.

### Task 4: Derive appointments, failure ordering and overall assessment

**Files:**
- Create: `backend/app/evaluation/derivation.py`
- Test: `backend/tests/test_evaluation_derivation.py`

**Interfaces:**
- Produces `derive_appointment_validity(interpretation, booking_event, call_date, timezone_name, rules) -> AppointmentValidation`.
- Produces `derive_evaluation_summary(batch_results, timeline, appointment_validation) -> EvaluationSummary`.
- Produces `merge_failure_candidates(technical, conversational, compliance) -> FirstFailureSummary`, ordered by reliable timestamp and then original line/sequence; returns unknown when chronology cannot be established.
- Consumes batch schemas from Task 1, evidence validation from Task 3, configured health-insurance appointment rules and existing timeline failure candidates.

- [ ] **Step 1: Write failing tests** for clear consent versus ?okay?/silence, callbacks versus expert calls, actual event versus proposed time, 09:00/21:00 boundaries, same-day booking, absent timezone/event, timestamp ordering, original-line ordering, unknown ordering, and severity remaining separate from chronology.
- [ ] **Step 2: Run `tests\test_evaluation_derivation.py` and confirm failures** show missing deterministic derivation.
- [ ] **Step 3: Implement appointment and summary derivation** using the configured 09:00 inclusive/21:00 exclusive window and no same-day booking. Do not create a late-opening failure based on latency alone. A confirmed critical compliance issue remains independently visible; a customer rejection alone does not make the overall result Bad.
- [ ] **Step 4: Run the focused derivation tests and confirm they pass.**
- [ ] **Step 5: Commit** as `feat: derive deterministic evaluation summary`.

### Task 5: Orchestrate and persist versioned evaluation runs

**Files:**
- Modify: `backend/app/evaluation/registry.py`
- Modify: `backend/app/evaluation/service.py`
- Modify: `backend/app/storage/orm.py`
- Modify: `backend/app/storage/evaluation_repo.py`
- Modify: `backend/app/domain/evaluation.py`
- Test: `backend/tests/test_evaluation_storage.py`
- Test: `backend/tests/test_evaluation_batches.py`

**Interfaces:**
- Produces `EvaluationRun` with `run_id`, interaction ID, batch records, derived summary and review state.
- Produces `def evaluate_interaction(tenant_id, interaction_id, retry_from_run_id=None) -> EvaluationRun`.
- Persists `EvaluationRunRow` and `EvaluationBatchRow` records with batch status, model/prompt/schema versions, timestamps, raw/parsed output, reported tokens, validation and review fields.
- Consumes Tasks 1-4; the synchronous service uses `asyncio.run` to execute its async registry from the existing synchronous request boundary.

- [ ] **Step 1: Write failing repository/orchestration tests** for three parallel fake calls, one failed batch plus two successes, retrying only failed batches from a prior run while carrying forward successful batch results with source references, a distinct run ID, tenant scoping, and old generic evaluation rows not returned.
- [ ] **Step 2: Run `tests\test_evaluation_storage.py` and the selected batch tests and confirm failures.**
- [ ] **Step 3: Implement run/batch ORM rows and atomic repository save/load operations.** Keep old physical rows untouched and remove their ORM/API read path; do not convert unavailable provenance into current results.
- [ ] **Step 4: Implement registry orchestration with concurrent batch tasks and bounded retries**; persist partial results and explicit provider/schema/evidence failure status. Do not use a heuristic fallback.
- [ ] **Step 5: Run the focused storage and orchestration tests and confirm they pass.**
- [ ] **Step 6: Commit** as `feat: persist independent evaluation batches`.

### Task 6: Update review, benchmark and evaluation API contracts

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/storage/review_repo.py`
- Modify: `backend/app/validation/benchmark.py`
- Modify: `backend/app/domain/golden.py`
- Modify: `backend/app/validation/golden_loader.py`
- Modify: `backend/app/storage/golden_repo.py`
- Modify: `backend/app/storage/orm.py`
- Modify: `backend/app/analytics/service.py`
- Test: `backend/tests/test_evaluation_api.py`
- Test: `backend/tests/test_human_review_storage.py`
- Test: `backend/tests/test_benchmark_engine.py`
- Test: `backend/tests/test_golden_loader.py`
- Test: `backend/tests/test_golden_storage.py`

**Interfaces:**
- `POST /api/v1/interactions/{interaction_id}/evaluate` returns one `EvaluationRun`.
- The request body optionally supplies `retry_from_run_id`; a retry creates a new run, reuses only successful batch results from that run, and calls the provider only for its failed batches.
- `GET /api/v1/interactions/{interaction_id}/evaluations` returns the latest run and versioned batch states, not generic per-evaluator rows.
- Review submissions target a batch evaluation ID; existing historical review records remain readable as archived history.
- Golden labels accept optional `conversation_status` (the exact design enum) and `language_slice` fields. The benchmark reports completeness and language-slice metrics only when those explicit labels are present; never infer labels from `what_happened` or transcripts.
- The current checked-in golden CSV lacks these labels. Use explicit test fixtures for the new dimensions; full benchmark validation on the owner-provided relabeled dataset remains an external prerequisite.

- [ ] **Step 1: Write failing endpoint/repository/benchmark tests** for the three batch response shape, partial failures, latest-run selection, review-by-evaluation-ID, archive exclusion, optional gold-label fields, absent-label benchmark availability and benchmark extraction from explicit completeness/language labels.
- [ ] **Step 2: Run the focused tests and confirm failures** demonstrate the old family/method/label contract.
- [ ] **Step 3: Implement API serialization, new review targeting, benchmark extraction and aggregation** from persisted batch outputs. Preserve human-review audit records and golden labels.
- [ ] **Step 4: Run `tests\test_evaluation_api.py`, `tests\test_human_review_storage.py` and `tests\test_benchmark_engine.py`; confirm they pass.**
- [ ] **Step 5: Commit** as `feat: expose batched evaluation results`.

### Task 7: Update evaluation dashboard and remove legacy evaluator surfaces

**Files:**
- Modify: `frontend/src/views/DrillDownView.jsx`
- Modify: `frontend/src/components/EvaluationCard.jsx`
- Modify: `frontend/src/components/ReviewModal.jsx`
- Modify: `frontend/src/views/BenchmarkView.jsx`
- Delete: `frontend/src/views/EvaluatorsView.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Modify: `frontend/src/api/client.js`
- Modify: `backend/app/api/app.py`
- Delete: `backend/app/evaluation/base.py`
- Delete: `backend/app/evaluation/compliance.py`
- Delete: `backend/app/evaluation/outcome.py`
- Delete: `backend/app/evaluation/experience.py`
- Delete: `backend/app/evaluation/quality.py`
- Delete: `backend/app/evaluation/facts.py`
- Test: `backend/tests/test_ui_static.py`
- Test: `backend/tests/test_evaluation_api.py`

**Interfaces:**
- Evaluation views consume `EvaluationRun`; show three batch states, deterministic assessment, evidence validation/review reasons and exact quotes.
- Review submission uses the versioned evaluation ID.
- The public evaluator-metadata/config endpoint and its UI are removed; no compatibility adapters remain.

- [ ] **Step 1: Write failing API/UI integration assertions** for batch cards, invalid-evidence review state, no score/confidence display, working review action and absent evaluator-config route/navigation.
- [ ] **Step 2: Run the focused tests and confirm they fail** against the legacy evaluator result shape and evaluator-config view.
- [ ] **Step 3: Implement the new evaluation presentation and review interaction**, then remove old evaluator implementations and generic result consumers after confirming no production call sites remain.
- [ ] **Step 4: Run focused backend tests and `Set-Location frontend; npm run build`; confirm both pass.**
- [ ] **Step 5: Commit** as `feat: replace legacy evaluator dashboard`.

### Task 8: Update evaluation documentation and run regression tests

**Files:**
- Modify: `README.md`
- Modify: `docs/GOLDEN_DATASET_FORMAT.md`
- Modify: `docs/PHASE_7_VALIDATION_BENCHMARK.md`
- Test: `backend/tests/test_evaluation_api.py`
- Test: `backend/tests/test_dashboard_integration.py`

- [ ] **Step 1: Update evaluation setup and benchmark docs** to explain explicit three-batch execution, supported dimensions, provider failure visibility, evidence validation and no confidence/combined numeric score.
- [ ] **Step 2: Run focused evaluation, review, benchmark and dashboard tests** with an in-memory SQLite fixture; confirm test execution does not modify the checked-in SQLite database.
- [ ] **Step 3: Run the full backend suite** with `Set-Location backend; .\.venv\Scripts\python.exe -m pytest -q`; confirm all tests pass.
- [ ] **Step 4: Run the frontend build** with `Set-Location frontend; npm run build`; confirm it completes successfully and refreshes the served static bundle.
- [ ] **Step 5: Commit** as `docs: document batched evaluation workflow`.

## Dependencies and execution order

Tasks 1-4 define and test the result contract and derivations. Task 5 consumes
those interfaces. Task 6 consumes the persisted run model. Task 7 updates UI and
removes the old evaluator implementation only after API consumers move. Task 8
is the final documentation and regression gate. Complete this plan before the
observability plan's UI integration task.
