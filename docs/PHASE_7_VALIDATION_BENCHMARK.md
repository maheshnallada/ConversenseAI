# Golden benchmark interpretation

The golden benchmark measures agreement between explicit human labels and versioned evaluations of the dataset's outcome-free model input. Runs are isolated in an input-specific `golden_dataset:<input-hash>` namespace; normal interaction runs are not used. It is a diagnostic report, not a release gate: the design defines no combined numeric score or fixed release threshold.

## Evaluation runs

The evaluator produces three independent batches:

1. `conversation_understanding` predicts outcome, sentiment, emotion, and customer facts.
2. `conversation_quality` assesses quality dimensions, context-awareness observations, and conversation completeness.
3. `compliance_appointment` checks never-rules and interprets appointment and consent evidence.

Each run records a status, model, prompt and schema versions, validation details, and any provider error for every batch. Provider failures remain visible as failed batches. Retries create a new run, reuse successful batches from the selected source run, and rerun its failed batches.

Evidence validation checks each cited line and exact quote against the supplied transcript. Non-null quality scores require supporting citations, and an empty transcript cannot produce an assessment. Explicit consent requires a customer citation; an unqualified acknowledgement remains for human review and cannot validate a booking. Invalid evidence is retained for review, but cannot support evidence-dependent derivations. Prohibited sensitive identifiers are not returned as customer facts. The dashboard exposes validation state and review reasons; it does not display confidence or present a combined numeric score.

## Reported metrics

The benchmark reports per-dimension accuracy, precision, recall, macro F1, support, and confusion matrices for dimensions with ground-truth labels:

- `correct_outcome`
- `sentiment`
- `emotion`
- `overall_quality`

Golden dataset processing scores these four dimensions only. Narrative observability labels, conversation status, language slices, and other reference columns remain unscored. Compliance false positives and false negatives are reported separately using the `gold_never_rule_broken` label. `gold_observability_notes` and similar fields are not evaluator input.

The loader excludes only rows whose `gold_test_flag` is explicitly `True`; `False`, `Unknown`, and blank values remain eligible. The model input is read only from `model_input_json_excluding_saved_outcome`; no `source_call_json`, `call_log`, saved outcome, or `gold_*` field is passed to the evaluator.

## Run and interpret the benchmark

The source CSV is user-provided and not bundled with the repository. Provision `Conversense_AI_25_Records_Input_and_Golden.csv` at the repository root before either workflow. The dashboard's **Import golden CSV** action is the explicit step that persists labels and evaluates the dataset. Its result shows records seen, imported labels, excluded tests, created/reused/failed runs, per-record errors, and the benchmark report from that import.

After import, run the report utility from the repository root:

```powershell
python scripts/validate_golden_dataset.py --tenant-id health_campaign
```

The script reads the supplied root-level CSV and only persisted runs in the corresponding input-specific benchmark namespace. It does not import labels or fall back to normal latest interaction runs. Missing evaluation runs are treated as abstentions (`Can't tell`) for supported dimensions. The report is written to `docs/GOLDEN_DATASET_BENCHMARK.md`.
