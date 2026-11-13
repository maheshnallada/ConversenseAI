import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.domain.golden import GoldenCallLabel


def load_golden_dataset(csv_path: Path | str) -> List[GoldenCallLabel]:
    """
    Parses and validates the golden dataset CSV containing human review labels.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset CSV not found: {path}")

    labels: List[GoldenCallLabel] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            call_id = row.get("Call", "").strip()
            what = row.get("What happened", "").strip()
            outcome = row.get("Correct outcome", "").strip()
            facts = row.get("Facts the customer gave", "").strip()
            sentiment = row.get("Sentiment", "").strip()
            emotion = row.get("Emotion", "").strip()
            overall = row.get("Overall", "").strip()
            line_str = row.get("First thing wrong: line", "").strip()
            first_line = int(line_str) if line_str.isdigit() else None
            first_what = row.get("First thing wrong: what", "").strip() or None
            never_rule = row.get("Never-rule broken", "None").strip() or "None"

            labels.append(
                GoldenCallLabel(
                    call_id=call_id,
                    what_happened=what,
                    correct_outcome=outcome,
                    facts_customer_gave=facts,
                    sentiment=sentiment,
                    emotion=emotion,
                    overall=overall,
                    first_thing_wrong_line=first_line,
                    first_thing_wrong_what=first_what,
                    never_rule_broken=never_rule,
                )
            )

    return labels


def load_reply_wait_checks(csv_path: Path | str) -> List[Dict[str, Any]]:
    """
    Parses the 20-call reply wait check CSV.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Reply wait check CSV not found: {path}")

    checks: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            checks.append({
                "call_id": row.get("Call", "").strip(),
                "customer_last_word_s": float(row.get("Customer last word (s)", 0.0)),
                "agent_first_sound_s": float(row.get("Agent first sound (s)", 0.0)),
                "gap_s": float(row.get("Gap (s)", 0.0)),
                "turn_index": int(row.get("Turn index")) if row.get("Turn index") else None,
                "notes": row.get("Notes", "").strip(),
            })

    return checks

