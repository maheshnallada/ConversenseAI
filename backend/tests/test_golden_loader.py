from pathlib import Path
import csv
import json

import pytest

from app.domain.golden import GoldenDataset
from app.reconstruction.processor import TranscriptProcessor
from app.validation.golden_loader import load_golden_dataset, load_reply_wait_checks


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CSV = PROJECT_ROOT / "Conversense_AI_25_Records_Input_and_Golden.csv"


def _write_basic_csv(path: Path, rows: list[dict[str, str]]):
    fieldnames = [
        "call_id",
        "model_input_json_excluding_saved_outcome",
        "gold_correct_outcome",
        "gold_sentiment",
        "gold_emotion",
        "gold_overall",
        "gold_never-rule_broken",
        "gold_test_flag",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_golden_dataset_parses_supplied_csv_and_maps_model_inputs():
    dataset = load_golden_dataset(GOLDEN_CSV, tenant_id="tenant_gold")

    assert isinstance(dataset, GoldenDataset)
    assert len(dataset.records) == 25
    assert dataset.dataset_hash
    assert dataset.records[0].label.call_id == "call_01"
    assert dataset.records[0].label.correct_outcome == "Not interested"
    assert dataset.records[0].error
    assert "does not match" in dataset.records[0].error
    assert dataset.records[0].input_hash is None
    assert dataset.records[0].evaluation_input is None


def test_golden_dataset_rejects_duplicate_headers_before_reading_rows(tmp_path: Path):
    csv_path = tmp_path / "duplicate_headers.csv"
    csv_path.write_text(
        "call_id,model_input_json_excluding_saved_outcome,"
        "gold_correct_outcome,gold_correct_outcome,gold_sentiment,"
        "gold_emotion,gold_overall,gold_never-rule_broken\n"
        "call_duplicate,not-json,Expected,Corrupted,Neutral,Neutral,Good,None\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate CSV header"):
        load_golden_dataset(csv_path, tenant_id="tenant_gold")


def test_process_call_data_matches_manifest_enrichment_and_embedded_call_id():
    with GOLDEN_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        record = next(csv.DictReader(file))

    call_data = json.loads(record["model_input_json_excluding_saved_outcome"])
    user_manifest = {}
    agent_manifest = {}
    for line in (record["manifest_jsonl"] or "").splitlines():
        item = json.loads(line)
        user_manifest[str(item["turn"])] = item
    for line in (record["agent_manifest_jsonl"] or "").splitlines():
        item = json.loads(line)
        agent_manifest[str(item["turn"])] = item

    turns = TranscriptProcessor().process_call_data(call_data, "tenant_gold", user_manifest, agent_manifest)

    assert len(turns) == len(call_data["messages"])
    assert turns[0].speaker == "agent"
    assert "Hello" in str(turns[0].metadata["manifest_text"])
    assert turns[0].metadata["at_s"] == 25.79
    assert turns[1].speaker == "customer"
    assert turns[1].metadata["manifest_transcript"] == ""


def test_golden_dataset_accepts_missing_unknown_and_false_test_flags_and_rejects_file_level_duplicates(tmp_path: Path):
    csv_path = tmp_path / "golden_flags.csv"
    _write_basic_csv(
        csv_path,
        [
            {
                "call_id": "call_01",
                "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_01", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {"campaign_id": "campaign-1"}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
                "gold_correct_outcome": "Not interested",
                "gold_sentiment": "Neutral",
                "gold_emotion": "Neutral",
                "gold_overall": "Good",
                "gold_never-rule_broken": "None",
                "gold_test_flag": "False",
            },
            {
                "call_id": "call_02",
                "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_02", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {"campaign_id": "campaign-2"}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
                "gold_correct_outcome": "Not interested",
                "gold_sentiment": "Neutral",
                "gold_emotion": "Neutral",
                "gold_overall": "Good",
                "gold_never-rule_broken": "None",
                "gold_test_flag": "Unknown",
            },
            {
                "call_id": "call_03",
                "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_03", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {"campaign_id": "campaign-3"}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
                "gold_correct_outcome": "Not interested",
                "gold_sentiment": "Neutral",
                "gold_emotion": "Neutral",
                "gold_overall": "Good",
                "gold_never-rule_broken": "None",
                "gold_test_flag": "true",
            },
            {
                "call_id": "call_04",
                "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_04", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {"campaign_id": "campaign-4"}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
                "gold_correct_outcome": "Not interested",
                "gold_sentiment": "Neutral",
                "gold_emotion": "Neutral",
                "gold_overall": "Good",
                "gold_never-rule_broken": "None",
            },
        ],
    )

    dataset = load_golden_dataset(csv_path, tenant_id="tenant_gold")
    assert [record.test_flag for record in dataset.records] == [False, None, True, None]
    assert [record.label.call_id for record in dataset.records] == ["call_01", "call_02", "call_03", "call_04"]

    duplicate = tmp_path / "duplicate.csv"
    rows = [
        {
            "call_id": "call_01",
            "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_01", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        },
        {
            "call_id": "call_01",
            "model_input_json_excluding_saved_outcome": json.dumps({"call_id": "call_01", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]}),
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        },
    ]
    with duplicate.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["call_id", "model_input_json_excluding_saved_outcome", "gold_correct_outcome", "gold_sentiment", "gold_emotion", "gold_overall", "gold_never-rule_broken"])
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="duplicate|Duplicate"):
        load_golden_dataset(duplicate, tenant_id="tenant_gold")


def test_golden_dataset_reports_row_level_json_errors_and_missing_headers(tmp_path: Path):
    good_path = tmp_path / "tmp_golden_invalid.csv"
    payload = json.dumps({"call_id": "call_02", "started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00", "end_reason": "ended", "channel": "phone", "environment": "staging", "meta": {}, "messages": [{"role": "assistant", "content": "hello", "t": 0.0}]})
    with good_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["call_id", "model_input_json_excluding_saved_outcome", "gold_correct_outcome", "gold_sentiment", "gold_emotion", "gold_overall", "gold_never-rule_broken"])
        writer.writeheader()
        writer.writerow({
            "call_id": "call_01",
            "model_input_json_excluding_saved_outcome": "not-json",
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        })
        writer.writerow({
            "call_id": "call_02",
            "model_input_json_excluding_saved_outcome": payload,
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        })

    dataset = load_golden_dataset(good_path, tenant_id="tenant_gold")
    assert dataset.records[0].error
    assert dataset.records[1].evaluation_input is not None

    missing_headers = tmp_path / "tmp_golden_missing_headers.csv"
    missing_headers.write_text("call_id,gold_correct_outcome\ncall_01,Not interested\n", encoding="utf-8")
    with pytest.raises(ValueError, match="required"):
        load_golden_dataset(missing_headers, tenant_id="tenant_gold")


def test_golden_dataset_rejects_any_embedded_call_id_mismatch(tmp_path: Path):
    csv_path = tmp_path / "mismatch.csv"
    payload = json.dumps({
        "call_id": "embedded-9",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:01:00+00:00",
        "end_reason": "ended",
        "channel": "phone",
        "environment": "staging",
        "meta": {"campaign_id": "campaign-9"},
        "messages": [{"role": "assistant", "content": "hello", "t": 0.0}],
    })
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["call_id", "model_input_json_excluding_saved_outcome", "gold_correct_outcome", "gold_sentiment", "gold_emotion", "gold_overall", "gold_never-rule_broken"])
        writer.writeheader()
        writer.writerow({
            "call_id": "call_01",
            "model_input_json_excluding_saved_outcome": payload,
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        })

    dataset = load_golden_dataset(csv_path, tenant_id="tenant_gold")
    assert dataset.records[0].error
    assert "does not match" in dataset.records[0].error


def test_golden_dataset_rejects_embedded_call_id_when_outer_id_is_empty(tmp_path: Path):
    csv_path = tmp_path / "empty_outer_id.csv"
    payload = json.dumps({
        "call_id": "embedded-9",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:01:00+00:00",
        "end_reason": "ended",
        "channel": "phone",
        "environment": "staging",
        "meta": {"campaign_id": "campaign-9"},
        "messages": [{"role": "assistant", "content": "hello", "t": 0.0}],
    })
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["call_id", "model_input_json_excluding_saved_outcome", "gold_correct_outcome", "gold_sentiment", "gold_emotion", "gold_overall", "gold_never-rule_broken"])
        writer.writeheader()
        writer.writerow({
            "call_id": "",
            "model_input_json_excluding_saved_outcome": payload,
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        })

    dataset = load_golden_dataset(csv_path, tenant_id="tenant_gold")

    assert dataset.records[0].label.call_id == ""
    assert dataset.records[0].error
    assert "does not match" in dataset.records[0].error
    assert dataset.records[0].evaluation_input is None


def test_golden_dataset_rejects_missing_embedded_call_id_when_outer_id_is_set(tmp_path: Path):
    csv_path = tmp_path / "missing_embedded_id.csv"
    payload = json.dumps({
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:01:00+00:00",
        "end_reason": "ended",
        "channel": "phone",
        "environment": "staging",
        "meta": {"campaign_id": "campaign-9"},
        "messages": [{"role": "assistant", "content": "hello", "t": 0.0}],
    })
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["call_id", "model_input_json_excluding_saved_outcome", "gold_correct_outcome", "gold_sentiment", "gold_emotion", "gold_overall", "gold_never-rule_broken"])
        writer.writeheader()
        writer.writerow({
            "call_id": "call_01",
            "model_input_json_excluding_saved_outcome": payload,
            "gold_correct_outcome": "Not interested",
            "gold_sentiment": "Neutral",
            "gold_emotion": "Neutral",
            "gold_overall": "Good",
            "gold_never-rule_broken": "None",
        })

    dataset = load_golden_dataset(csv_path, tenant_id="tenant_gold")

    assert dataset.records[0].error
    assert "does not match" in dataset.records[0].error
    assert dataset.records[0].evaluation_input is None


@pytest.mark.parametrize(
    "rows",
    [
        [
            "call_id,model_input_json_excluding_saved_outcome,gold_correct_outcome,gold_sentiment,gold_emotion,gold_overall,gold_never-rule_broken\n",
            "call_01,{\"call_id\":\"call_01\",\"started_at\":\"2026-01-01T00:00:00+00:00\",\"ended_at\":\"2026-01-01T00:01:00+00:00\",\"end_reason\":\"ended\",\"channel\":\"phone\",\"environment\":\"staging\",\"meta\":{},\"messages\":[{\"role\":\"assistant\",\"content\":\"hello\",\"t\":0.0}],\"call_key\":\"c1\"},Not interested,Neutral,Neutral,Good,None\n",
        ],
        [
            "call_id,model_input_json_excluding_saved_outcome,gold_correct_outcome,gold_sentiment,gold_emotion,gold_overall,gold_never-rule_broken\n",
            "call_01,\"{\\\"call_id\\\":\\\"call_01\\\"}\",Not interested,Neutral,Neutral,Good,None,EXTRA\n",
        ],
    ],
)
def test_golden_dataset_rejects_short_and_surplus_csv_rows(tmp_path: Path, rows: list[str]):
    csv_path = tmp_path / "malformed_structure.csv"
    csv_path.write_text("".join(rows), encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed CSV row structure|row structure"):
        load_golden_dataset(csv_path, tenant_id="tenant_gold")


def test_golden_dataset_isolates_malformed_manifest_json(tmp_path: Path):
    csv_path = tmp_path / "manifest_error.csv"
    fieldnames = [
        "call_id",
        "model_input_json_excluding_saved_outcome",
        "manifest_jsonl",
        "agent_manifest_jsonl",
        "gold_correct_outcome",
        "gold_sentiment",
        "gold_emotion",
        "gold_overall",
        "gold_never-rule_broken",
    ]
    valid_payload = {
        "call_id": "call_01",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:01:00+00:00",
        "end_reason": "ended",
        "channel": "phone",
        "environment": "staging",
        "meta": {"campaign_id": "campaign-1"},
        "messages": [{"role": "assistant", "content": "hello", "t": 0.0}, {"role": "user", "content": "hi", "t": 1.0}],
    }
    good_row = {
        "call_id": "call_02",
        "model_input_json_excluding_saved_outcome": json.dumps({
            **valid_payload,
            "call_id": "call_02",
            "messages": [{"role": "assistant", "content": "hello", "t": 0.0}],
        }),
        "manifest_jsonl": '{"turn": 0, "transcript": "hello"}\n',
        "agent_manifest_jsonl": '{"turn": 0, "text": "hello"}\n',
        "gold_correct_outcome": "Not interested",
        "gold_sentiment": "Neutral",
        "gold_emotion": "Neutral",
        "gold_overall": "Good",
        "gold_never-rule_broken": "None",
    }
    bad_row = {
        "call_id": "call_01",
        "model_input_json_excluding_saved_outcome": json.dumps(valid_payload),
        "manifest_jsonl": '{"turn": 0, "transcript": "hello"}\nnot-json\n',
        "agent_manifest_jsonl": '{"turn": 0, "text": "hello"}\n',
        "gold_correct_outcome": "Not interested",
        "gold_sentiment": "Neutral",
        "gold_emotion": "Neutral",
        "gold_overall": "Good",
        "gold_never-rule_broken": "None",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(bad_row)
        writer.writerow(good_row)

    dataset = load_golden_dataset(csv_path, tenant_id="tenant_gold")
    assert dataset.records[0].error
    assert "manifest" in dataset.records[0].error.lower()
    assert dataset.records[1].evaluation_input is not None


def test_reply_wait_checks_validation(tmp_path: Path):
    csv_path = tmp_path / "reply_wait_check_20_calls.csv"
    csv_path.write_text(
        "Call,Customer last word (s),Agent first sound (s),Gap (s),Turn index,Notes\n"
        "call_01,1.0,2.0,3.0,0,ok\n"
        "call_02,2.0,3.0,5.0,1,ok\n",
        encoding="utf-8",
    )
    checks = load_reply_wait_checks(csv_path)
    assert len(checks) == 2
    assert checks[0]["call_id"] == "call_01"
    assert checks[0]["gap_s"] == 3.0
