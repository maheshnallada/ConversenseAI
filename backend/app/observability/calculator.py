import math
from collections.abc import Mapping
from typing import Any

from app.domain.observability import InteractionMetrics, PercentilesResult
from app.domain.transcript import TranscriptTurn
from app.observability.config import RateCardManager
from app.reconstruction.timing import calculate_overlap


def calculate_percentiles(values: list[float]) -> PercentilesResult:
    if not values:
        return PercentilesResult(None, None, None, None, None)

    sorted_v = sorted(values)
    n = len(sorted_v)
    avg_val = round(sum(sorted_v) / float(n), 3)

    if n == 1:
        v = round(sorted_v[0], 3)
        return PercentilesResult(avg=v, p50=v, p90=v, p95=v, p99=v)

    def _get_pct(p: float) -> float:
        # Linear interpolation between ranks
        k = (n - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_v[int(k)], 3)
        val = sorted_v[f] * (c - k) + sorted_v[c] * (k - f)
        return round(val, 3)

    return PercentilesResult(
        avg=avg_val,
        p50=_get_pct(50.0),
        p90=_get_pct(90.0),
        p95=_get_pct(95.0),
        p99=_get_pct(99.0),
    )


def extract_sequential_latencies(turns: list[TranscriptTurn]) -> list[float]:
    latencies: list[float] = []
    for i in range(1, len(turns)):
        prev = turns[i - 1]
        curr = turns[i]
        # Sequential turn: customer spoke, then agent responded
        if prev.speaker == "customer" and curr.speaker == "agent":
            if prev.end_s is not None and curr.start_s is not None:
                diff = curr.start_s - prev.end_s
                # Only strictly sequential non-overlapping turns count as ordinary response latency
                if diff >= 0.0:
                    latencies.append(round(diff, 3))
    return latencies


def calculate_interaction_metrics(
    tenant_id: str,
    interaction_id: str,
    call_data: dict[str, Any],
    turns: list[TranscriptTurn],
    recording_duration_s: float | None = None,
    rate_card: RateCardManager | None = None,
) -> InteractionMetrics:
    rc = rate_card or RateCardManager()

    usage_data = call_data.get("usage")
    if not isinstance(usage_data, Mapping):
        meta = call_data.get("meta")
        usage_data = meta.get("usage") if isinstance(meta, Mapping) else None
    usage = usage_data if isinstance(usage_data, Mapping) else {}
    line_data = usage.get("line")
    line = line_data if isinstance(line_data, Mapping) else {}
    telephony_duration = line.get("connected_s")
    if telephony_duration is not None:
        telephony_duration = round(float(telephony_duration), 3)

    models_data = call_data.get("models")
    models = models_data if isinstance(models_data, Mapping) else {}
    llm_data = usage.get("llm")
    llm_usage = llm_data if isinstance(llm_data, Mapping) else {}

    agent_turns = [t for t in turns if t.speaker == "agent"]
    customer_turns = [t for t in turns if t.speaker == "customer"]

    # First agent latency
    first_agent_latency = None
    if agent_turns and agent_turns[0].start_s is not None:
        first_agent_latency = round(agent_turns[0].start_s, 3)

    # Sequential response latencies & percentiles
    sequential_latencies = extract_sequential_latencies(turns)
    percentiles = calculate_percentiles(sequential_latencies)

    # Overlaps and silence
    overlap_count = 0
    total_overlap_s = 0.0
    longest_silence = None

    for i in range(1, len(turns)):
        prev = turns[i - 1]
        curr = turns[i]

        overlap = calculate_overlap(prev.start_s, prev.end_s, curr.start_s, curr.end_s)
        if overlap > 0.0:
            overlap_count += 1
            total_overlap_s += overlap

        if prev.end_s is not None and curr.start_s is not None:
            gap = curr.start_s - prev.end_s
            if gap > 0.0:
                if longest_silence is None or gap > longest_silence:
                    longest_silence = round(gap, 3)

    # Token counts
    in_tokens = llm_usage.get("input_tokens")
    if in_tokens is None:
        in_tokens = llm_usage.get("total_input_tokens") or llm_usage.get("estimated_input_tokens")

    out_tokens = llm_usage.get("output_tokens")
    if out_tokens is None:
        out_tokens = llm_usage.get("total_output_tokens") or llm_usage.get("estimated_output_tokens")

    tot_tokens = None
    if in_tokens is not None or out_tokens is not None:
        tot_tokens = (in_tokens or 0) + (out_tokens or 0)

    # STT and TTS duration
    stt_data = usage.get("stt")
    stt_usage = stt_data if isinstance(stt_data, Mapping) else {}
    tts_data = usage.get("tts")
    tts_usage = tts_data if isinstance(tts_data, Mapping) else {}
    stt_audio_s = stt_usage.get("audio_s")
    tts_audio_s = tts_usage.get("audio_s")
    tts_model = tts_usage.get("model") or "bulbul:v3"

    model_name = models.get("model")
    cost_breakdown = rc.calculate_interaction_cost(
        model_name=model_name,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        stt_audio_s=stt_audio_s,
        tts_audio_s=tts_audio_s,
        connected_s=telephony_duration,
        tts_model=tts_model,
    )

    audio_missing = len(agent_turns) == 0
    audio_silent = (
        len(turns) == 0
        and (recording_duration_s is not None and recording_duration_s > 0)
        and (telephony_duration == 0 or telephony_duration is None)
    )

    return InteractionMetrics(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        recording_duration_s=recording_duration_s,
        telephony_duration_s=telephony_duration,
        turn_count=len(turns),
        agent_turn_count=len(agent_turns),
        customer_turn_count=len(customer_turns),
        first_agent_latency_s=first_agent_latency,
        response_latency_percentiles=percentiles,
        response_latency_samples=sequential_latencies,
        longest_silence_s=longest_silence,
        overlap_count=overlap_count,
        total_overlap_s=round(total_overlap_s, 3),
        audio_missing=audio_missing,
        audio_silent=audio_silent,
        llm_provider=models.get("provider"),
        llm_model=model_name,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        total_tokens=tot_tokens,
        cost_breakdown=cost_breakdown,
    )
