# Golden dataset format

The benchmark compares explicit human labels with versioned evaluations of the supplied dataset's outcome-free model input. The source file, `Conversense_AI_25_Records_Input_and_Golden.csv`, is user-provided data and is not bundled or tracked in this repository. Provision it at the repository root with that exact filename before importing or generating a report.

## Columns

The loader reads these supplied dataset columns:

| CSV column | Use |
|---|---|
| `call_id` | Unique source record and benchmark interaction identifier. |
| `model_input_json_excluding_saved_outcome` | Canonical model input containing the interaction and transcript. This is the only input used for evaluation. |
| `gold_correct_outcome` | Ground-truth outcome label. |
| `gold_sentiment` | Ground-truth sentiment label. |
| `gold_emotion` | Ground-truth emotion label. |
| `gold_overall` | Ground-truth overall-quality label. |
| `gold_never_rule_broken` | Use `None` when no never-rule was broken; any other non-empty value marks a violation for aggregate compliance metrics. |
| `gold_test_flag` | Exclude a record only when this value is explicitly `True`; `False`, `Unknown`, and blank values are included. |
| `manifest_jsonl`, `agent_manifest_jsonl` | Optional supporting input metadata used to reconstruct canonical turns and scope the input hash. |
| `gold_what_happened`, `gold_facts_the_customer_gave`, `gold_first_thing_wrong_line`, `gold_first_thing_wrong_what`, `gold_human_review_notes`, `gold_observability_notes` | Human or narrative reference only; not scored. |
| `conversation_status`, `Conversation status`, `language_slice`, `Language slice` | Optional reference labels; not scored by golden dataset processing. |
| `source_call_json`, `call_log`, and other reference columns | Not used as evaluator input or scored labels. |

`model_input_json_excluding_saved_outcome` must be outcome-free. Saved outcomes and all `gold_*` columns are labels or references and are never passed to the evaluator. `conversation_status` and `language_slice` labels may be used for reporting by other datasets, but the golden processing workflow keeps these reference dimensions unscored.

## Conversation status values

- `COMPLETED`
- `OUTCOME_REACHED_BUT_NOT_CLOSED`
- `CUSTOMER_LEFT_DURING_OPENING`
- `CUSTOMER_LEFT_DURING_DISCUSSION`
- `NO_MEANINGFUL_INTERACTION`
- `MACHINE_OR_VOICEMAIL`
- `UNKNOWN`

If these labels are present for reference, use the exact enum spelling. Keep language-slice labels consistent, including capitalization, so equivalent slices are grouped together.

## Evaluation outputs compared

The benchmark consumes persisted versioned runs in an input-specific `golden_dataset:<input-hash>` namespace, not normal interaction runs or historical per-evaluator result rows. It scores outcome, sentiment, emotion, and overall quality; compliance false positives and false negatives are summarized separately. Narrative observability labels and other reference columns are not scored. See [the benchmark interpretation guide](./PHASE_7_VALIDATION_BENCHMARK.md) for availability and metric details.

## Import and report

The dashboard's **Import golden CSV** action explicitly imports the root-level file, stores its labels, evaluates each eligible row from the outcome-free input, and reports created, reused, and failed evaluations with per-record errors. Import is separate from call ingestion and does not create normal interaction, transcript, artifact, timeline, or observability records.

The CLI report utility reads the same root-level CSV and only looks up runs in the matching benchmark namespace. It does not import labels or fall back to normal interaction runs. Provision the source CSV at the repository root before using either workflow.
