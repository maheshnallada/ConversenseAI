# Conversense AI evaluation code — updated package

## Targeted changes
- Expanded first-failure schema to accept all categories present in the 50-call gold set.
- Made `What happened` derivation conservative: `Can't tell` and
  `NO_MEANINGFUL_INTERACTION` no longer imply customer disconnect.
- Require explicit technical evidence before overriding a label with no-agent-audio
  or late-opening failure; expected cancellations are not treated as technical failure.
- Evidence matching prefers exact quotes, with a fallback for Unicode compatibility
  normalization and whitespace only. Quotes are not rewritten; paraphrases remain invalid.
- Keep parsed outputs from `review_required` batches in partial derivation while
  retaining the review-required state.
- Retry review-required batches when retrying from an earlier run.
- Distinguish callback events from expert appointment events.
- Mark unanswered-call compliance rules `NOT_EVALUABLE` instead of `NOT_DETECTED`.
- Align prompt taxonomy and clarification-question boundaries with the supplied labels.

## Included modules
`derivation.py`, `errors.py`, `evidence.py`, `llm_client.py`, `prompts.py`,
`registry.py`, `schemas.py`, `service.py`.

## Important limitations
This package was syntax-compiled but not executed inside the full application runtime.
Run unit/integration tests against your actual timeline classes, database, configuration,
and LLM provider before deployment. The cleaned golden dataset is a draft and does not
silently relabel disputed calls; audio adjudication is still needed.
