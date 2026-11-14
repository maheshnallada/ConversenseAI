# Golden benchmark interpretation

The golden benchmark measures agreement between explicit human labels and the latest versioned evaluation run for each labeled interaction. It is a diagnostic report, not a release gate: the design defines no combined numeric score or fixed release threshold.

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
- `conversation_status`, only when explicitly labeled

Language-slice metrics are computed for the same dimensions within each explicitly labeled slice. If no `conversation_status` or `language_slice` labels are present, that dimension is reported as unavailable; values are never inferred from transcript text or `What happened`.

Compliance false positives and false negatives are reported separately using the `Never-rule broken` label. `What happened` is retained as reference text and is not benchmarked as a predicted category.

## Run and interpret the benchmark

From the repository root, run:

```powershell
python scripts/validate_golden_dataset.py --golden-csv data/golden_dataset.csv --tenant-id health_campaign
```

The script reads persisted versioned runs and writes `docs/GOLDEN_DATASET_BENCHMARK.md`. Missing evaluation runs are treated as abstentions (`Can't tell`) for supported dimensions. Confirm that each CSV row points to the intended interaction and that optional labels use the documented format before interpreting a slice.

The checked-in dataset may not contain the optional completeness and language labels. In that case the report marks those metrics unavailable rather than suggesting that coverage or quality is zero.
