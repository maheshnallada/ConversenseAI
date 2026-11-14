# Golden dataset format

The benchmark compares explicit human labels with the latest persisted evaluation run for each interaction. Import labels from UTF-8 or UTF-8-with-BOM CSV.

## Columns

The loader reads these existing columns:

| CSV column | Use |
|---|---|
| `Call` | Call or interaction identifier used to find the stored run. |
| `Correct outcome` | Ground-truth outcome label. |
| `Sentiment` | Ground-truth sentiment label. |
| `Emotion` | Ground-truth emotion label. |
| `Overall` | Ground-truth overall-quality label. |
| `Never-rule broken` | Use `None` when no never-rule was broken; any other non-empty value marks a violation for aggregate compliance metrics. |
| `What happened` | Human reference text; it is not inferred into a benchmark dimension. |
| `Facts the customer gave` | Human reference text; it is not currently a benchmark dimension. |
| `First thing wrong: line` | Optional transcript line reference for human review. |
| `First thing wrong: what` | Optional human-review note. |

Two optional columns enable additional labeled dimensions:

| CSV column | Use |
|---|---|
| `conversation_status` or `Conversation status` | Explicit conversation-completeness label. Values must be one of the status values below. |
| `language_slice` or `Language slice` | Explicit language or other slice label. It is trimmed but otherwise not restricted to a closed vocabulary. |

Blank optional cells are treated as unavailable. The loader does not infer a completeness or language label from the transcript or from `What happened`.

## Conversation status values

- `COMPLETED`
- `OUTCOME_REACHED_BUT_NOT_CLOSED`
- `CUSTOMER_LEFT_DURING_OPENING`
- `CUSTOMER_LEFT_DURING_DISCUSSION`
- `NO_MEANINGFUL_INTERACTION`
- `MACHINE_OR_VOICEMAIL`
- `UNKNOWN`

Use the exact enum spelling. Keep language-slice labels consistent, including capitalization, so equivalent slices are grouped together.

## Evaluation outputs compared

The benchmark consumes persisted versioned runs, not historical per-evaluator result rows. It supports outcome, sentiment, emotion, overall quality, explicitly labeled conversation status, and explicit language-slice metrics. Compliance false positives and false negatives are summarized separately from those dimensions. See [the benchmark interpretation guide](./PHASE_7_VALIDATION_BENCHMARK.md) for availability and metric details.
