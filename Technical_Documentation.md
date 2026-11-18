# Conversense AI

## Health Call Observability and Evaluation Platform

**Project Technical Documentation**

**Document purpose:** Project submission and technical architecture explanation
**Evaluation dataset:** 50 health-insurance voice calls
**Document date:** 18 November 2026

---

# 1. Executive Summary

Conversense AI is a health-insurance voice-call observability and evaluation platform designed to analyze conversations between AI voice agents and customers.

The primary objective is to understand not only what happened during a call, but also how effectively the AI agent handled the conversation.

Traditional conversation evaluation often relies on transcripts alone. However, a transcript does not necessarily represent what the customer actually heard. An agent may generate a response successfully, but the response may be delayed, interrupted or cut off before the customer hears it.

Conversense AI addresses this problem by separating evaluation into two major dimensions:

1. **Call Observability:** Understand the technical execution of a voice interaction, including latency, interruptions, response delivery and call lifecycle events.
2. **Conversation Evaluation:** Assess the quality and effectiveness of the conversation, including customer sentiment, emotion, business outcome, overall quality and compliance.

The current implementation uses a hybrid evaluation approach combining Python-based deterministic logic and Large Language Model (LLM)-based contextual evaluation.

The platform also incorporates structured evaluation outputs, evidence validation, golden-dataset benchmarking and human-review indicators.

The current evaluation was performed on a dataset of 50 health-insurance calls.

---

# 2. Problem Statement

Evaluating an AI voice agent involves more than determining whether the generated response is grammatically correct or relevant.

Several situations can occur during a voice interaction:

- The agent generates a response, but the customer never hears it.
- The agent responds too slowly, causing the customer to disconnect.
- The customer interrupts the agent while it is speaking.
- The customer provides a meaningful answer but leaves before the call is completed.
- The customer only says hello or a few introductory words before disconnecting.
- The agent misunderstands a customer response or repeats a question.
- The agent violates a business or regulatory compliance rule.
- The conversation ends without achieving the intended business outcome.

A transcript alone cannot reliably explain all these situations.

Therefore, the platform aims to combine conversation information, call metadata, playback information and execution traces to produce explainable call evaluations.

# 3. Project Objectives

The primary objectives are:

1. Analyze individual voice calls and reconstruct their interaction timelines.
2. Identify technical issues such as latency, interruptions and incomplete audio delivery.
3. Evaluate customer sentiment and emotion using the available conversation transcript.
4. Determine the conversation lifecycle and business outcome.
5. Identify the first significant failure in an interaction.
6. Detect violations of predefined business and compliance rules.
7. Validate evaluation results against transcript evidence.
8. Compare predicted evaluations against a human-prepared golden dataset.
9. Identify uncertain cases and flag them for human review.
10. Optimize LLM usage by avoiding unnecessary model invocations.

# 4. Input Dataset and Data Sources

The current project uses a dataset containing 50 health-insurance voice calls.

Each call contains multiple related data sources.

| Data source      | Description                                  | Purpose                                         |
| ---------------- | -------------------------------------------- | ----------------------------------------------- |
| Transcript       | Agent and customer messages                  | Conversation evaluation                         |
| `call.json`      | Call metadata, messages and turn information | Conversation reconstruction                     |
| Audio recording  | Recorded conversation                        | Playback verification and future audio analysis |
| Audio manifest   | Audio segment references                     | Associate audio with conversation messages      |
| Call logs        | Execution and interaction logs               | Technical troubleshooting                       |
| Execution traces | STT, LLM and TTS processing information      | Latency and performance analysis                |

## 4.1 Audio characteristics

The supplied audio recordings are stereo, with:

- Left channel: Agent audio
- Right channel: Customer audio

The dataset also contains message-level playback information, including whether the agent response was heard, cut, not played or unavailable.

## 4.2 Important metadata

The source data provides useful fields such as:

| Field           | Description                           |
| --------------- | ------------------------------------- |
| `call_id`       | Unique call identifier                |
| `messages`      | Conversation messages                 |
| `turns`         | Turn-level execution information      |
| `spoken`        | Audio playback status                 |
| `audio_s`       | Audio duration                        |
| `stt_ms`        | Speech-to-text processing time        |
| `tts_ms`        | Text-to-speech processing time        |
| `response_time` | Response timing                       |
| `llm_ttft_ms`   | LLM time to first token               |
| `tts_ttfb_ms`   | TTS time to first audio byte          |
| `perceived_ms`  | Perceived response latency            |
| `overlap_ms`    | Speech overlap or interruption timing |
| `end_reason`    | Call termination information          |
| `disposition`   | Call disposition information          |

These fields are useful for reconstructing the interaction and identifying technical problems.

**Important data-handling decision:** The supplied transcript is treated as the ground truth for this assignment. We do not run another ASR model to regenerate or overwrite the supplied transcript. This avoids introducing additional transcription errors into the evaluation process.

# 5. Current System Architecture

The current architecture follows a modular application design, with separate responsibilities for data ingestion, conversation reconstruction, observability, evaluation and result validation.

The design avoids introducing unnecessary distributed services at the current scale.

## 5.1 High-level architecture

```text
              INPUT DATA
                  |
                  v
       Data Ingestion and Validation
                  |
                  v
       Normalization and Parsing
                  |
                  v
       Conversation Reconstruction
                  |
                  v
          Evaluation Workflow
                  |
          +-------+-------+
          |               |
          v               v
    Observability     Evaluation Engine
       Analysis       (Hybrid Approach)
          |               |
          |         +-----+------+
          |         |            |
          |         v            v
          |    Python Rules    LLM Evaluation
          |         |            |
          +---------+------------+
                    |
                    v
          Result Validation
                    |
          +---------+----------+
          |                    |
          v                    v
    Structured Results    Human Review
          |
          v
    Benchmarking and
    Evaluation Dashboard
```

## 5.2 Architectural components

### A. Data ingestion and validation

This component reads the supplied call data and validates the available structures.

Responsibilities include:

- Reading call metadata and messages.
- Validating call identifiers.
- Parsing timestamps and turn information.
- Associating audio references and execution traces.
- Identifying missing or invalid metadata.
- Preserving original source information.

Missing metadata is not automatically treated as evidence of a failure.

For example, if an optional call-ending field is absent, the system should not assume that the customer disconnected. It should treat the information as unavailable.

### B. Conversation reconstruction

This component reconstructs the sequence of interactions during a call.

It combines:

- Customer and agent messages.
- Message timestamps.
- Turn metadata.
- Playback status.
- Audio references.
- Execution traces.

The objective is to understand the relationship between generated responses and actual audio delivery.

For example, an LLM may successfully generate a response, but the customer may interrupt the agent before the complete audio response is played.

Therefore, the generated text and the delivered audio must be treated as different events.

### C. Observability engine

The observability engine focuses on the technical execution of calls.

It evaluates:

- Response latency.
- STT processing latency.
- LLM response latency.
- TTS processing latency.
- Perceived response time.
- Audio delivery status.
- Customer interruptions.
- Speech overlap.
- Unexpected call termination.

The objective is to identify where the interaction experienced technical problems.

### D. Evaluation engine

The evaluation engine assesses the conversational and business quality of the call.

It evaluates:

- What happened during the call.
- Business outcome.
- Customer sentiment.
- Customer emotion.
- Overall conversation quality.
- Compliance violations.
- First significant failure.
- Supporting evidence.

### E. Validation and aggregation

This component validates the generated evaluation results.

Responsibilities include:

- Structured output validation.
- Allowed-category validation.
- Transcript evidence validation.
- Missing-value handling.
- Confidence and human-review indicators.
- Aggregation of call-level results.

---

# 6. Evaluation Methodology

The project uses a hybrid evaluation approach.

Instead of relying entirely on an LLM, responsibilities are divided between deterministic Python logic and contextual LLM reasoning.

## 6.1 Why a hybrid approach?

Some evaluation tasks involve explicit rules and structured information. Other tasks require understanding conversational context.

Using an LLM for every task can increase cost, latency and output variability.

Using only deterministic rules would make it difficult to evaluate subjective conversational characteristics.

Therefore, the system combines both approaches.

| Evaluation responsibility       | Approach                          |
| ------------------------------- | --------------------------------- |
| Input validation                | Python                            |
| Required-field checks           | Python                            |
| Timing calculations             | Python                            |
| Playback-state interpretation   | Python                            |
| Explicit compliance checks      | Python and contextual evaluation  |
| Sentiment classification        | LLM                               |
| Emotion classification          | LLM                               |
| Overall conversation quality    | LLM                               |
| Business outcome interpretation | LLM with deterministic validation |
| Evidence verification           | Python                            |
| Result aggregation              | Python                            |

The LLM is used where contextual interpretation is needed, while Python handles deterministic validation and consistency checks.

## 6.2 Evaluation dimensions

### 1. What happened

This metric describes the lifecycle of the interaction.

The current taxonomy includes:

- Machine or call screener answered.
- Heard nothing from the agent.
- Agent's first words came late.
- Left during the first line, said nothing.
- Said hello or a few words, then left.
- Gave a real answer, then left before an ending.
- Call reached an ending.
- Can't tell.

This metric is important because not every incomplete call represents the same failure.

### 2. Business outcome

This metric identifies the result of the interaction.

Current categories include:

- Expert call booked.
- Call later agreed.
- Not interested.
- Do not call.
- Voicemail.
- Call screener or machine.
- No outcome: customer left first.
- Can't tell.

The business outcome is separate from the call lifecycle.

For example, a customer can provide a meaningful answer and then disconnect before the agent closes the conversation. The lifecycle and business outcome should represent these two different aspects.

### 3. Customer sentiment

Current sentiment categories:

- Positive
- Neutral
- Negative
- Can't tell

**Current implementation:** Sentiment is predicted using the conversation transcript.

### 4. Customer emotion

Current emotion categories:

- Cooperative
- Confused
- Frustrated
- Disengaged
- Neutral
- Can't tell

**Current implementation:** Emotion is predicted using the conversation transcript. Audio-based emotion recognition has not yet been implemented.

### 5. Overall conversation quality

The overall evaluation categories are:

- Good
- OK
- Bad
- Can't tell

This represents the overall effectiveness of the conversation, rather than simply whether the agent generated a technically valid response.

### 6. Compliance evaluation

The project defines six never-rule categories.

| Rule  | Description                                                                |
| ----- | -------------------------------------------------------------------------- |
| NR001 | Pushing a particular policy or insurer                                     |
| NR002 | Disclosing premium figures                                                 |
| NR003 | Booking outside 9 AM–9 PM                                                  |
| NR004 | Booking without clear customer consent                                     |
| NR005 | Requesting sensitive information such as PAN, Aadhaar, bank details or OTP |
| NR006 | Denying the agent's AI identity                                            |

Compliance results should be supported by relevant conversation evidence.

### 7. First significant failure

This metric identifies the earliest meaningful issue in the conversation.

Examples include:

- Repeatedly asking the same question.
- Poor objection handling.
- Incorrect understanding of the customer.
- Inappropriate follow-up questions.
- Audio delivery failure.
- Unclear conversation handling.

The intention is to identify the first point where the interaction starts going wrong, rather than only reporting the final outcome.

---

# 7. Handling Empty and Incomplete Transcripts

One important optimization implemented in the evaluation workflow concerns empty transcripts.

## 7.1 Problem

When a conversation transcript is empty, sending it to an LLM for sentiment, emotion and overall-quality evaluation does not provide useful information.

The model would receive no meaningful conversational context and could return speculative or unreliable results.

Repeatedly invoking the LLM in such situations also wastes tokens and increases evaluation cost.

## 7.2 Current implementation

The system checks whether meaningful conversation transcript content is available before invoking transcript-dependent evaluation.

If the transcript is empty:

- Sentiment is returned as `Can't tell`.
- Emotion is returned as `Can't tell`.
- Overall quality is returned as `Can't tell`.
- Other transcript-dependent evaluation dimensions are returned as `Can't tell`.
- Unnecessary LLM evaluation is skipped.

This is a deliberate cost optimization and an uncertainty-handling decision.

It prevents the model from inventing an interpretation when there is no conversation content to analyze.

## 7.3 Important distinction

An empty transcript does not necessarily mean that the customer said nothing.

Possible explanations include:

- The customer did not speak.
- The customer spoke, but the transcription was unavailable.
- The transcription process failed.
- The conversation data was incomplete.
- The audio exists, but the corresponding transcript was not provided.

Therefore, `Can't tell` should not be interpreted as proof that no conversation occurred.

Where audio and telemetry are available, technical observability can still identify whether speech or playback events occurred, even when transcript-dependent evaluation is skipped.

---

# 8. Current Limitations and Challenges

The current evaluation has some limitations because of the available dataset, data consistency and implementation time constraints.

## 8.1 Data inconsistency

The supplied call data contains incomplete or inconsistent information across certain records.

Examples include:

- Missing optional call-ending metadata.
- Incomplete audio manifests.
- Differences between transcript content and playback information.
- Ambiguous call outcomes.
- Missing or insufficient evidence for some evaluation dimensions.

These inconsistencies affect the ability to confidently identify the actual conversation outcome.

As a result, sentiment, emotion and overall-quality predictions may not always reflect the real customer experience.

For example, a transcript may contain an agent response, but the available playback information may indicate that the customer did not hear the complete response.

Similarly, an incomplete conversation may not contain enough customer language to determine sentiment reliably.

We therefore treat uncertain results cautiously and use `Can't tell` or human-review indicators when sufficient evidence is unavailable.

## 8.2 Transcript-only emotion and sentiment recognition

Due to the project timeline, customer sentiment and emotion are currently evaluated using transcript text only.

This means the current implementation cannot fully identify emotions expressed through:

- Vocal tone.
- Pitch variation.
- Speaking intensity.
- Speech rate.
- Pauses.
- Voice tremors.
- Other acoustic characteristics.

A customer may use neutral words while sounding frustrated, or use negative words in a neutral conversational manner.

Text-only evaluation cannot reliably capture all these distinctions.

Voice-based emotion recognition is therefore an important future enhancement.

## 8.3 Limited golden dataset

The current benchmark uses 50 calls.

This is useful for validating the evaluation pipeline and identifying classification weaknesses, but it is not sufficient to establish reliable production-level performance across all customer populations, accents and call scenarios.

Additional human-reviewed examples and consistent annotation guidelines are required.

---

# 9. Handling the Interviewer's Conversation-Lifecycle Scenarios

One of the key design discussions concerns identifying exactly how a customer leaves or interrupts a conversation.

A single label such as `Customer disconnected` is not sufficient to describe all possible scenarios.

The proposed solution is to separate conversation lifecycle classification from individual interaction events.

## 9.1 Scenario A: Customer says hello and leaves

Example:

```text
Agent: Hello, am I speaking with Mr. Kumar?
Customer: Hello.
Customer disconnects.
```

Expected classification:

- What happened: Said hello or a few words, then left.
- Business outcome: No outcome, if no business result was established.
- Sentiment: Can't tell, if there is insufficient evidence.
- Overall quality: Can't tell, if there is insufficient interaction to assess.

The key distinction is that the customer spoke, but did not provide a meaningful response to the agent's substantive question.

## 9.2 Scenario B: Customer provides a meaningful answer and leaves

Example:

```text
Agent: Are you interested in discussing health insurance options?
Customer: I already have insurance through my employer.
Customer disconnects.
```

Expected classification:

- What happened: Gave a real answer, then left before an ending.
- Business outcome: Determine from the actual conversation; do not automatically classify it as a successful booking or rejection.
- Sentiment: Evaluate from available conversational evidence.
- Overall quality: Evaluate whether the agent handled the interaction appropriately.

The important distinction is that the customer provided a meaningful response before leaving.

## 9.3 Scenario C: Customer interrupts the agent

Example:

```text
Agent: Let me explain the available options and the benefits—

Customer: I already know about that. I don't need it.

Agent audio stops.
```

This is not necessarily a customer disconnect.

It is an interruption event.

The platform should distinguish:

1. Customer started speaking while the agent was speaking.
2. Agent playback was interrupted or stopped.
3. Customer continued speaking or disconnected afterward.
4. The agent either resumed, responded or failed to continue.

The source dataset already contains useful playback and timing information such as:

- `spoken`
- `audio_s`
- `overlap_ms`
- Message timestamps
- Turn information
- Audio references

These should be used to reconstruct the interruption sequence.

## 9.4 Proposed improvement: separate lifecycle labels and interaction events

Instead of making one metric represent every possible interaction, I recommend introducing a separate interaction-event taxonomy.

| Interaction event                  | Meaning                                              |
| ---------------------------------- | ---------------------------------------------------- |
| `CUSTOMER_GREETING_ONLY`           | Customer only says hello or a few introductory words |
| `CUSTOMER_MEANINGFUL_RESPONSE`     | Customer answers a substantive question              |
| `CUSTOMER_INTERRUPTED_AGENT`       | Customer begins speaking while agent audio is active |
| `AGENT_AUDIO_CUT_OFF`              | Agent audio stops before the response is completed   |
| `CUSTOMER_DISCONNECTED`            | Customer leaves the call                             |
| `AGENT_RESUMED_AFTER_INTERRUPTION` | Agent continues after customer interruption          |
| `AGENT_DID_NOT_RESUME`             | Agent did not continue after the interruption        |
| `CALL_COMPLETED`                   | Interaction reaches a normal ending                  |
| `UNKNOWN_EVENT`                    | Available evidence is insufficient                   |

These are proposed additional events, not all existing evaluation labels.

The existing `What happened` metric can continue to represent the overall lifecycle classification.

The additional events provide more detailed information about what occurred within that lifecycle.

## 9.5 Proposed event reconstruction logic

A practical approach would be:

**Step 1:** Identify agent playback start and end events.

**Step 2:** Identify customer speech intervals using available customer audio and message timestamps.

**Step 3:** Compare customer speech intervals with agent playback intervals.

**Step 4:** If customer speech begins while agent playback is active, mark a potential interruption.

**Step 5:** Verify whether agent playback was cut, stopped or continued.

**Step 6:** Determine whether the customer subsequently disconnected or the agent resumed.

**Step 7:** Produce both the lifecycle classification and the individual interaction events.

A simplified overlap condition is:

```python
def has_interruption(
    customer_start,
    agent_start,
    agent_end
):
    return agent_start <= customer_start <= agent_end
```

This is only a conceptual example. A production implementation should use actual audio intervals, timestamps, buffering delays and overlap tolerances rather than relying on message timestamps alone.

Also, a customer speaking while the agent is speaking does not automatically prove that the agent was interrupted. The playback status and actual audio intervals should be checked.

## 9.6 Why this design is better

This approach prevents different situations from being grouped into one ambiguous category.

For example:

- A customer who only says hello and leaves is different from a customer who answers a question and leaves.
- A customer who interrupts an agent is different from a customer who disconnects.
- An agent response being cut off is different from an agent failing to generate a response.
- A call reaching its normal ending is different from a customer disconnecting after a substantive answer.

This produces more useful observability metrics and more meaningful conversation-quality evaluations.

---

# 10. Future Enhancement: Audio-Based Emotion Recognition

## 10.1 Objective

The current implementation uses transcript-based sentiment and emotion classification.

A future enhancement is to introduce speech emotion recognition so that the system can analyze vocal characteristics in addition to linguistic content.

## 10.2 Proposed industry-aligned approach

Rather than immediately selecting a model and assuming it will perform well, we propose a research and benchmarking phase.

The approach would involve:

1. Extracting the customer audio channel from the stereo recording.
2. Segmenting the audio into customer speech turns.
3. Aligning each audio segment with its corresponding transcript message.
4. Evaluating pretrained speech emotion recognition models.
5. Testing acoustic feature-based and transformer-based approaches.
6. Comparing model performance on representative customer-call data.
7. Selecting and validating the best-performing approach for the target domain.

Potential acoustic features include:

- Pitch and pitch variation.
- Energy and speaking intensity.
- Speech rate.
- Pauses and speaking rhythm.
- Spectral characteristics.
- Voice quality and prosody.

Pretrained speech representations and transformer-based models can also be evaluated as feature extractors or classification backbones.

## 10.3 Recommended multimodal architecture

The future system can combine two independent information sources:

**Text-based analysis**

- Linguistic sentiment.
- Customer intent.
- Contextual meaning.
- Explicit positive or negative statements.

**Audio-based analysis**

- Vocal emotion.
- Pitch and intensity.
- Speech rate.
- Prosodic variation.
- Acoustic indicators of frustration or uncertainty.

These outputs can then be combined through a multimodal fusion layer.

```text
          Customer Audio
                |
                v
       Customer Audio Channel
                |
                v
       Speech Segmentation
                |
                v
       Audio Emotion Model
                |
                v
       Audio Emotion Features
                |
                +-------------------+
                                    |
                                    v
                             Multimodal Fusion
                                    |
                                    v
Customer Transcript              Final Emotion
        |                           Assessment
        v
  Text Emotion Model
        |
        v
  Text Emotion Features
```

The fusion layer could use a weighted or learned combination of text and audio predictions, with confidence calibration and an explicit unknown/uncertain state.

The exact fusion strategy and model should be selected through testing rather than assumed in advance.

## 10.4 Model evaluation considerations

Speech emotion recognition has important generalization challenges.

A model trained on one dataset may perform poorly on a different set of speakers, recording conditions or languages.

Recent research has highlighted the difficulty of cross-dataset and speaker-independent speech emotion recognition. A 2025 benchmarking review reported that many cross-dataset transformer experiments achieved less than 40% accuracy, while a broader multi-dataset evaluation achieved up to 58.85% in its reported setting.

Therefore, model selection should include:

- Speaker-independent evaluation.
- Cross-dataset evaluation.
- Noise robustness testing.
- Evaluation on real customer-call recordings.
- Class-wise precision, recall and F1.
- Confusion-matrix analysis.
- Confidence calibration.
- Human annotation agreement.

The selected approach should be tested on representative data before being integrated into the production evaluation workflow.

**Important:** Audio-based emotion recognition is a future enhancement and has not been implemented or benchmarked in the current project.

---

# 11. LLM Cost Optimization

LLM inference can become a significant operating cost when the platform processes a large number of calls.

The current implementation includes an early validation step to avoid unnecessary LLM invocations.

## 11.1 Empty-transcript optimization

When no meaningful transcript is available, the system skips transcript-dependent LLM evaluation and returns `Can't tell` for the affected dimensions.

This avoids spending tokens on an input that does not contain enough information to support a meaningful evaluation.

## 11.2 Additional proposed optimizations

Future improvements could include:

- Evaluate multiple dimensions in a structured LLM request when appropriate.
- Cache results using call ID, input version, evaluator version and prompt version.
- Avoid rerunning unchanged evaluations.
- Use smaller models for simple classification tasks after benchmarking.
- Reserve larger models for ambiguous contextual reasoning.
- Apply confidence-based human-review routing.
- Track token consumption and cost per call.
- Store evaluation versions for reproducibility.

These optimizations should preserve evaluation quality rather than optimizing cost alone.

---

# 12. Golden Dataset and Benchmarking

A golden dataset was prepared to compare predicted evaluations against expected human-provided labels.

The benchmark measures exact-match accuracy for each evaluation dimension.

Formula:

Accuracy = (Correct predictions / Total evaluated records) × 100

## 12.1 Latest benchmark results

The latest benchmark run was performed on 18 November 2026.

| Evaluation dimension | Latest result   | 
| -------------------- | --------------: |
| What happened        |             68% |
| Business outcome     |             88% |
| Sentiment            |             90% |
| Emotion              |             84% |
| Overall quality      |             72% |
| Compliance           |             86% |

The latest run completed with 50 records marked as ready.

## 12.2 Interpretation

The largest improvement was in overall-quality evaluation, which increased from 34% to 46%.

The benchmark also identified several areas requiring further improvement:

- Greetings and introductory responses are sometimes confused with meaningful customer answers.
- Bad conversations are sometimes classified as OK.
- Confused customers may be classified as disengaged.
- Some evidence references require additional validation.
- Some call outcomes remain ambiguous.

The benchmark is based on the available golden labels. It should not be interpreted as independently verified real-world accuracy.

The golden dataset also has incomplete labels for certain dimensions, including conversation status and first-failure categories. Those dimensions should not be assigned benchmark accuracy until suitable reference labels are available.

---

# 13. Reliability and Error Handling

For reliable evaluation, the platform should preserve the relationship between source data, processing jobs and evaluation results.

Important design considerations include:

| Concern              | Proposed handling                          |
| -------------------- | ------------------------------------------ |
| Duplicate ingestion  | Idempotent call ingestion                  |
| Invalid input        | Validation and error reporting             |
| Missing metadata     | Explicit unknown or unavailable state      |
| LLM timeout          | Retry transient failures                   |
| Invalid LLM response | Schema validation and controlled retry     |
| Unsupported evidence | Flag for human review                      |
| Repeated processing  | Version-aware evaluation                   |
| Failed evaluation    | Preserve failure details for investigation |
| Re-evaluation        | Replay without duplicating call records    |

The system should also retain the evaluator version and prompt/schema version used for each result so that benchmark comparisons remain reproducible.

---

# 14. Current Architecture vs Future Architecture

It is important to distinguish what is currently implemented from what can be introduced as the platform scales.

| Area                       | Current implementation                   | Future enhancement                            |
| -------------------------- | ---------------------------------------- | --------------------------------------------- |
| Call input                 | Supplied call dataset                    | Continuous call ingestion                     |
| Transcript                 | Supplied transcript used as ground truth | Improved transcript quality checks            |
| Sentiment                  | Transcript-based LLM evaluation          | Text and audio-based fusion                   |
| Emotion                    | Transcript-based LLM evaluation          | Speech emotion recognition                    |
| Observability              | Available call metadata and traces       | Richer real-time telemetry                    |
| Audio handling             | Supplied recordings and references       | Dedicated scalable audio storage              |
| Transactional data         | Current application data layer           | Continued PostgreSQL scaling and optimization |
| Analytics database         | No separate OLAP database currently      | ClickHouse                                    |
| Raw audio/artifact storage | No S3-based storage currently            | S3-compatible object storage                  |
| Evaluation                 | Hybrid Python and LLM approach           | More model routing and calibration            |
| Human review               | Review indicators                        | Full adjudication workflow                    |
| Benchmarking               | 50-call golden dataset                   | Larger, continuously updated benchmark        |

## 14.1 Future use of S3-compatible object storage

The current architecture does not use Amazon S3 for raw audio or artifact storage.

As the platform scales, an object-storage solution such as Amazon S3 or another S3-compatible service could be introduced for:

- Original audio recordings.
- Processed audio segments.
- Evaluation reports.
- Exported benchmark datasets.
- Historical artifacts.

This would separate large binary files from structured transactional records.

## 14.2 Future use of ClickHouse

The current architecture does not use ClickHouse.

As the number of calls and telemetry events increases, ClickHouse could be introduced as a dedicated OLAP database.

Potential analytical workloads include:

- Average and P95 response latency.
- Agent-version performance comparison.
- Emotion and sentiment trends.
- Compliance violation trends.
- First-failure distribution.
- Cost per call.
- Model usage and token consumption.

PostgreSQL would continue to serve as the transactional application database, while ClickHouse would serve analytical queries.

Data could be transferred using a transactional outbox and asynchronous event-processing pipeline.

This avoids overloading the transactional database with large analytical queries.

---

# 15. Future Roadmap

The following improvements are recommended for the next development phases.

### Phase 1 — Improve evaluation accuracy

- Refine conversation lifecycle taxonomy.
- Improve the distinction between introductory and substantive customer responses.
- Improve overall-quality classification.
- Strengthen evidence validation.
- Complete missing golden labels.
- Introduce systematic human adjudication.

### Phase 2 — Improve voice observability

- Reconstruct customer and agent audio intervals.
- Identify customer speech during agent playback.
- Detect agent audio cutoff events.
- Distinguish customer interruption from customer disconnection.
- Track whether the agent resumes after an interruption.
- Improve correlation between audio segments and transcript messages.

### Phase 3 — Introduce audio-based emotion recognition

- Benchmark pretrained speech emotion models.
- Evaluate speaker-independent and cross-dataset performance.
- Test on representative customer calls.
- Combine text and acoustic features.
- Calibrate confidence and unknown predictions.
- Validate with human annotations.

### Phase 4 — Improve analytics and scalability

- Introduce scalable object storage for audio and artifacts.
- Introduce ClickHouse for analytical workloads.
- Add near-real-time performance dashboards.
- Introduce model and prompt version comparisons.
- Improve asynchronous processing and monitoring.

---

# 16. Conclusion

Conversense AI aims to provide an explainable evaluation and observability layer for AI-powered voice interactions.

The project addresses an important limitation of transcript-only call evaluation: generated text does not necessarily represent the actual customer experience.

By combining call metadata, execution traces, playback information, deterministic rules and contextual LLM evaluation, the platform can provide a more complete understanding of voice-agent performance.

The current implementation establishes the core evaluation workflow, including lifecycle classification, business outcomes, sentiment, emotion, overall quality, compliance and evidence validation.

The initial benchmark also highlights areas where data quality, taxonomy design and contextual reasoning need improvement.

The proposed future enhancements focus on more detailed interruption detection, audio-based emotion recognition, scalable audio storage and dedicated analytical infrastructure.

The long-term goal is to move from basic call scoring toward a reliable, explainable and scalable voice-agent observability platform that helps organizations understand not just whether an AI agent completed a call, but how effectively and correctly it handled the customer interaction.

---

# 17. References and Further Reading

The following research provides background for the proposed future speech emotion recognition work:

1. **A Performance Benchmarking Review of Transformers for Speaker-Independent Speech Emotion Recognition (2025).**
   [https://pubmed.ncbi.nlm.nih.gov/40726155/](https://pubmed.ncbi.nlm.nih.gov/40726155/)

2. **SER Evals: In-domain and Out-of-domain Benchmarking for Speech Emotion Recognition (Interspeech 2024).**
   [https://www.isca-archive.org/interspeech_2024/osman24_interspeech.html](https://www.isca-archive.org/interspeech_2024/osman24_interspeech.html)

3. **A Review on Speech Emotion Recognition: A Survey, Recent Advances, Challenges, and the Influence of Noise (2024).**
   [https://doi.org/10.1016/j.neucom.2023.127015](https://doi.org/10.1016/j.neucom.2023.127015)

4. **Multimodal Emotion Recognition in Conversations: A Survey of Methods, Trends, Challenges and Prospects (2025).**
   [https://aclanthology.org/2025.findings-emnlp.332/](https://aclanthology.org/2025.findings-emnlp.332/)

5. **Speech Emotion Recognition in Conversations Using Artificial Intelligence: A Systematic Review and Meta-analysis (2025).**
   [https://doi.org/10.1007/s10462-025-11197-8](https://doi.org/10.1007/s10462-025-11197-8)

*Note: The research references support the proposed future direction. They do not represent experiments performed as part of the current Conversense AI implementation.*
