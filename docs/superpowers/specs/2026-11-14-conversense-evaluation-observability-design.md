# Conversense AI Evaluation and Observability Design

## Intent

Align the existing application with the batched evaluation and observability
designs while keeping this phase focused on application behavior. The intended
users are call reviewers and operators who need reproducible, evidence-backed
evaluation results and a separate, factual view of technical call execution.

The supplied transcript remains the only source of conversation content.
Evaluation results must be traceable to exact original lines; observability
must report only what supplied events, timestamps, playback metadata and usage
records support.

## Goals

- Replace the five per-criterion evaluators with three modular batches:
  conversation understanding, conversation quality/lifecycle, and
  compliance/appointment interpretation.
- Run the independent LLM batches concurrently where configured, validate
  structured output and evidence deterministically, and preserve partial batch
  outcomes without substituting heuristic answers for provider failures.
- Derive objective timing, playback, booking validity, first-failure and
  overall-assessment results in Python.
- Keep technical observability independent from semantic evaluation, and expose
  the observable evidence through interaction detail and analytics APIs/UI.
- Remove out-of-design evaluation and local-ingestion product surfaces selected
  by the user, while retaining canonical interactions, human review and the
  golden-set benchmark.
- Preserve existing source interactions and historical evaluation rows without
  destructive data cleanup.

## Non-goals

- RabbitMQ or any other message broker, worker fleet, queue processing,
  transactional-outbox publisher, retry queue, dead-letter queue, replay
  service, or horizontal-scaling work.
- Moving audio, transcripts or other files to S3-compatible/object storage.
  Existing local artifact storage remains the phase boundary; audio remains an
  optional human-review artifact.
- OpenTelemetry, Prometheus, Grafana or platform-level telemetry deployment.
  Report queue/worker/trace values only when those values already exist in
  supplied interaction data; otherwise show unavailable.
- ASR, transcript regeneration, translation or normalization of evidence
  excerpts.
- A microservice split, new database platform, or broad rewrite of ingestion.

## Constraints and design principles

- Follow the existing Python/FastAPI, Pydantic, SQLAlchemy, React and SQLite
  development stack. Keep the current modular-monolith deployment model.
- Use the user's `Conversense_AI_Batched_Evaluation_Design.docx` as the source
  for exact prompt rules, JSON shapes and enum values, and
  `Conversense_AI_Observability_Design.pdf` as the source for metric definitions
  and API/dashboard separation. The scaling design is a deferred boundary only.
- The canonical interaction and original transcript are immutable inputs to
  evaluation. Original line IDs, speaker labels, scripts and spelling must be
  retained.
- Customer-only facts, sentiment and emotion must use customer turns. Evidence
  quotations must be exact and in the original language/script.
- Missing timestamps, playback metadata, booking events or usage are unknown or
  unavailable, never evidence of success or failure.
- Never infer consent from an agent claim or from an unqualified
  acknowledgement.
- Keep existing historical evaluation rows untouched. New code and APIs will
  not read them as current batch results; deleting old persisted rows is not
  part of this phase.

## Approaches considered

1. **Keep the generic evaluator contract and wrap it with batches.** This would
   reduce immediate API/UI changes, but would preserve the old score/confidence
   shape, per-criterion evaluator model and compatibility behavior the user
   asked to remove. Not selected.
2. **Replace evaluation with the three-batch contract and update the
   observability surface in place.** Retain SQLAlchemy, the canonical
   interaction, the existing database and UI shell; remove obsolete
   evaluator/ingestion surfaces and update only directly dependent APIs,
   persistence, analytics and views. Selected because it aligns with the
   supplied designs without prematurely introducing scale infrastructure.
3. **Implement the scaling architecture at the same time.** Adding object
   storage, RabbitMQ, workers and platform telemetry would increase operational
   scope and contradict the user's explicit sequencing. Deferred.

## Evaluation design

### Three independent batches

1. **Conversation understanding** returns outcome, customer-stated facts,
   customer sentiment and customer emotion.
2. **Conversation quality and lifecycle** returns the seven transcript-based
   quality dimensions, context-awareness findings and conversation-completeness
   stages/status.
3. **Compliance and appointment interpretation** returns the six never-rule
   findings, potential violations and appointment/consent interpretation.

Use the exact outcome, sentiment, emotion, completeness, appointment and
compliance enums from the batched evaluation design. Quality dimensions are
clarity, relevance, empathy, professionalism, naturalness, responsiveness and
closing quality (1-5 or null). Context dimensions are repeated questions,
ignored information, contradictory responses, irrelevant follow-ups and poor
objection handling. The six rule IDs are NR001 policy/insurer pushing, NR002
premium figure, NR003 booking outside allowed hours, NR004 booking without
clear consent, NR005 sensitive-information request and NR006 AI identity
denial. Their statuses are DETECTED, NOT_DETECTED, REVIEW_REQUIRED and
NOT_EVALUABLE. Follow the design document's exact nested JSON examples for
evidence, reasons, stage state and appointment interpretation.

Each batch has its own strict Pydantic response model, system prompt, version,
status and result. The shared multilingual rules are included in each system
prompt. Use a provider-supported structured-output mode when available. Run
independent provider requests concurrently within the request-serving process;
this is not a background-job system.

Evaluation is explicit, using the existing per-interaction evaluate action;
canonical ingestion does not automatically invoke the LLM. Every evaluation
invocation has a run ID and independent batch statuses. A rerun creates a new
versioned run; a retry request targets failed batches only. The API identifies
the latest run without overwriting prior batch evidence.

### Result persistence and failure handling

Persist one versioned result per batch with an evaluation ID, interaction ID,
batch name/status, model, prompt/schema versions, start/completion times,
provider token usage when reported, raw and parsed output, validation findings
and human-review state. Preserve successful batches if another batch fails;
retry only failed batches with bounded provider-aware retries. A missing
provider configuration, timeout, rate limit, invalid JSON/schema or invalid
evidence must be reported as a failed or review-required batch. Do not silently
switch to deterministic keyword heuristics.

The API returns the three batch states plus the deterministic derived
assessment. It does not expose a fabricated confidence score or a combined
numeric quality score. Human review remains available for ambiguous,
conflicting, invalid-evidence and high-severity outcomes.

### Evidence validation

Validate that cited line IDs exist in the supplied transcript, that speaker
restrictions are respected, and that each quote is an exact substring of the
original line. Invalid evidence is retained as a validation issue and routed
for review; it must not be presented as verified evidence. Missing evidence is
represented by null/empty evidence fields as specified by the batch schema.
Sensitive customer identifiers listed in the evaluation design must not be
extracted as customer facts.

### Deterministic derivation

- Validate transcript structure, line IDs, speaker labels, timestamps and
  playback states without changing the source transcript.
- Calculate duration, first response, sequential response latency, silence and
  overlap only from reliable supplied timestamps. Do not turn overlap into a
  negative response-latency measurement.
- Reconcile `heard`, `cut`, `not_played` and `no_audio` against supplied
  evidence; absent or contradictory metadata stays unknown or review-required.
- Determine appointment validity from interpreted consent plus actual booking
  event data and timezone. Carry forward the current health-insurance rule
  configuration: appointments are allowed from 09:00 inclusive to 21:00
  exclusive, and same-day bookings are disallowed. If local timezone/date
  evidence is unavailable, the objective check is not evaluable. An
  uttered/proposed time alone is not a booking.
- Merge timestamped technical, conversational and compliance failure
  candidates. Return unknown/ambiguous when ordering cannot be established;
  keep severity independent from chronology.
- Produce Good, OK, Bad or Can't tell through explicit deterministic rules.
  A customer rejection alone is not Bad; a confirmed critical compliance issue
  remains highlighted regardless of business outcome. Do not create a
  `LATE_AGENT_OPENING` failure label from latency alone until the threshold
  policy is confirmed; always expose the measured latency when available.

## Observability design

Keep observability result models and routes separate from evaluation batches.
Use the existing canonical interaction, transcript turns, timeline and
artifact references as inputs. Persist derived observability values with
documented units, source evidence and calculation version.

In this phase, cover the available per-interaction domains:

- Interaction and supplied-event status, schema/data-quality issues and
  processing outcomes already recorded in the database.
- Timeline/trace information supplied with an interaction, including span
  duration/failures when present.
- Turn counts, first-agent response, sequential response latency percentiles,
  silence gaps, overlaps and call duration where timestamps support them.
- Playback-state counts and metadata mismatches.
- Provider-reported tokens and explicitly labelled cost estimates from
  versioned rate-card data; missing usage/pricing remains unavailable.

Do not invent queue depth, oldest-message age, worker utilization, DLQ or
external telemetry. Do not treat the absence of an agent turn alone as proof
that audio was missing. Audio playback is for authorized human review only and
does not replace or alter transcript evidence.

Expose the design-aligned interaction list/detail/timeline/observability and
analytics overview/reliability/usage surfaces. Add event append and artifact
reference registration only as persistence of canonical metadata; these
endpoints do not upload binary audio or publish jobs to a broker.

Use the current tenant-scoped API boundary for the retained detail and audio
routes; do not broaden artifact access or return raw audio/artifacts in
analytics. Do not add a new role system in this phase.

Reliability analytics describe persisted interaction/processing outcomes and
supplied trace/event failures only. Usage analytics aggregate provider-reported
tokens and estimates using `configs/rate_cards.json`; add a rate-card version
for reproducibility. If a rate card is invalid, a model is unpriced, a
timestamp or usage value is absent, surface the value as unavailable rather
than falling back to hard-coded/default rates.

## API and UI surface

- Retain canonical interaction ingestion/detail, paginated interaction
  exploration, timeline and authorized audio review.
- Add/align per-interaction event and artifact-reference registration,
  observability detail, and overview/reliability/usage analytics.
- Replace the generic per-evaluator result response with the versioned
  three-batch result shape and derived assessment.
- Keep human-review submission/history and golden-dataset import/benchmark
  workflows; update them to use the new batch dimensions and labels.
- Remove folder-path processing, ZIP/file uploads, dataset seeding, and their
  UI flows. Remove the obsolete evaluator-configuration surface and metadata
  endpoint. Do not retain compatibility adapters for these routes.
- Update the dashboard to show technical observability separately from
  semantic evaluation, present batch validation/review state and exact
  evidence, and remove score/confidence displays that the design does not
  support.

## Data migration and compatibility

Add the new batch-result persistence without modifying the canonical
interaction payload or deleting prior evaluation rows. Historical generic
evaluation rows are archival only and are excluded from new batch APIs,
dashboards and aggregation. No automatic conversion is promised because old
rows do not contain the raw/parsed batch payloads, prompt/schema versions or
validation provenance required by the new contract.

Update the current schema initialization and tests for the new tables and
fields. Do not add a database server or a migration framework solely for this
phase.

## Acceptance criteria

- Exactly three independent LLM batch results are produced; configured
  provider requests can run concurrently, and one batch failure does not erase
  other completed results.
- No evaluation failure is converted into a heuristic success or fabricated
  confidence/score.
- Strict schemas, exact quote/line validation, speaker restrictions and
  multilingual evidence-preservation behavior are tested.
- Consent, actual booking-event/timezone validation, missing metadata,
  contradictory playback and unavailable timestamp behavior are tested.
- First-failure ordering and overall assessment are deterministic and become
  unknown when evidence cannot establish them.
- Observability and evaluation remain separate in models, API responses and
  dashboard sections.
- Supported analytics and interaction detail can be traced to supplied source
  evidence; absent queue/telemetry values are unavailable.
- Out-of-design folder/upload/seed and evaluator-configuration routes/UI are
  absent; canonical interaction, human review and golden benchmark flows still
  work.
- Existing persisted source interactions and historical evaluation rows are
  not deleted or rewritten by application startup.
- Focused backend tests, the relevant full backend suite and frontend build
  pass.

## Builder decisions

- Keep synchronous SQLAlchemy persistence and execute only the independent
  provider calls asynchronously in the current request-serving process.
- Use the existing database and local artifact references; do not perform
  storage migration or delete historical result rows.
- Treat operational values that the current inputs cannot establish as
  unavailable instead of adding infrastructure or guessing.
- Preserve human review and golden-set benchmarking because the evaluation
  design explicitly requires review routing and benchmark release gates.
- Evaluation runs are on-demand, not triggered by ingestion. Each rerun is a
  distinct run; only failed batches are eligible for batch-level retry.
- First-agent latency remains a measured metric only; it does not create a
  `LATE_AGENT_OPENING` failure label by itself.
- The existing health-insurance configuration is the policy source for
  appointment hours and same-day booking. Missing call timezone makes local
  hour validation unavailable.
- Reuse the tenant boundary already present in the API and keep audio/artifact
  payloads out of analytics. Adding user roles is not part of this phase.
- Use the existing rate-card configuration as the estimate source, add a
  version identifier, and report unknown pricing/usage as unavailable.
- Do not establish a numeric pass/fail release threshold for golden-set
  metrics in this phase; report benchmark results by dimension and language
  slice for later policy-setting. Completeness benchmarking requires an
  explicit `conversation_status` label using the design's allowed statuses;
  language-slice benchmarking requires an explicit `language_slice` label.
  Do not infer either label from `what_happened`, transcript text or another
  dimension. The current golden CSV lacks these labels; the owner will provide
  relabeled data before full completeness/language-slice benchmark validation.
