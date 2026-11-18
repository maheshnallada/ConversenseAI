from types import SimpleNamespace
from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.evaluation.derivation import (
    FailureCandidate,
    derive_evaluation_summary,
    validate_what_happened_guard,
)


def _make_timeline(customer_texts, first_tech=None, total_cust_turns=None):
    events = []
    for i, txt in enumerate(customer_texts):
        events.append(
            TimelineEvent(
                event_id=f"t_cust_{i}",
                event_type="turn",
                speaker="customer",
                start_s=float(i * 2),
                end_s=float(i * 2 + 1),
                text=txt,
            )
        )
    return SimpleNamespace(
        events=events,
        first_technical_failure=first_tech,
        first_conversational_failure=None,
        technical_failure_ordering_unknown=False,
        conversational_failure_ordering_unknown=False,
        customer_turn_count=len(customer_texts) if total_cust_turns is None else total_cust_turns,
        agent_turn_count=1,
        total_duration_s=20.0,
    )


# 1. Says nothing -> Left during first line, said nothing
def test_case_1_says_nothing():
    tl = _make_timeline([], total_cust_turns=0)
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "No outcome: customer left first"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_OPENING"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Left during first line, said nothing"


# 2. Says "Hello" only -> Said hello or a few words, then left
def test_case_2_says_hello_only():
    tl = _make_timeline(["Hello"])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "No outcome: customer left first"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_OPENING"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Said hello or a few words, then left"


# 3. Says "Haan" to identity confirmation -> Said hello or a few words, then left
def test_case_3_says_haan_to_identity():
    tl = _make_timeline(["Haan"])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "No outcome: customer left first"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_OPENING"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Said hello or a few words, then left"


# 4. Confirms own name only -> Said hello or a few words, then left
def test_case_4_confirms_own_name():
    tl = _make_timeline(["Haan, main Vinayak bol raha hoon."])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "No outcome: customer left first"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_OPENING"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Said hello or a few words, then left"


# 5. Asks "Kaun bol rahe ho?" only -> Said hello or a few words, then left
def test_case_5_asks_who_is_calling():
    tl = _make_timeline(["Kaun bol rahe ho?"])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "No outcome: customer left first"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_OPENING"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Said hello or a few words, then left"


# 6. Says they have company health insurance -> Gave a real answer, then left before an ending
def test_case_6_has_company_insurance():
    tl = _make_timeline(["Haan, mere paas company ka health insurance hai."])
    batch_results = {
        "conversation_understanding": {
            "outcome": {"label": "No outcome: customer left first"},
            "customer_facts": [
                {"category": "existing_insurance", "field": "policy_type", "value": "company", "evidence_line": 2, "quote": "company ka health insurance"}
            ],
        },
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_DISCUSSION"},
            "what_happened": {"label": "Gave a real answer, then left before an ending"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Gave a real answer, then left before an ending"


# 7. Gives family coverage requirement -> Gave a real answer, then left before an ending
def test_case_7_family_coverage_requirement():
    tl = _make_timeline(["Mujhe family floater chahiye 10 lakh ka."])
    batch_results = {
        "conversation_understanding": {
            "outcome": {"label": "No outcome: customer left first"},
            "customer_facts": [
                {"category": "insurance_requirements", "field": "coverage", "value": "family floater 10 lakh", "evidence_line": 2, "quote": "family floater"}
            ],
        },
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_DISCUSSION"},
            "what_happened": {"label": "Gave a real answer, then left before an ending"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Gave a real answer, then left before an ending"


# 8. Gives a specific rejection reason, then disconnects without close -> Gave a real answer, then left before an ending
def test_case_8_rejection_reason_before_close():
    tl = _make_timeline(["Mera premium bahut high ho gaya tha pichli baar, isliye nahi chahiye."])
    batch_results = {
        "conversation_understanding": {
            "outcome": {"label": "No outcome: customer left first"},
            "customer_facts": [
                {"category": "rejection_reason", "field": "reason", "value": "premium too high previously", "evidence_line": 2, "quote": "premium bahut high ho gaya tha"}
            ],
        },
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "CUSTOMER_LEFT_DURING_DISCUSSION"},
            "what_happened": {"label": "Gave a real answer, then left before an ending"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Gave a real answer, then left before an ending"


# 9. Explicitly rejects offer; agent acknowledges and closes -> Call reached an ending
def test_case_9_rejects_acknowledged_and_closed():
    tl = _make_timeline(["Nahi, mujhe insurance nahi chahiye."])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "Not interested"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "COMPLETED"},
            "what_happened": {"label": "Call reached an ending"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Call reached an ending"


# 10. Customer and agent mutually establish callback -> Call reached an ending
def test_case_10_mutually_established_callback():
    tl = _make_timeline(["Haan, kal 4 baje call kar lena."])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "Call later agreed"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "COMPLETED"},
            "what_happened": {"label": "Call reached an ending"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Call reached an ending"


# 11. Machine/IVR answers -> Machine or call screener answered
def test_case_11_machine_ivr():
    tl = _make_timeline([])
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "Voicemail"}},
        "conversation_quality": {
            "conversation_completeness": {"conversation_status": "MACHINE_OR_VOICEMAIL"},
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Machine or call screener answered"


# 12. Reliable metadata proves no agent speech was played -> Heard nothing from the agent
def test_case_12_no_agent_speech():
    first_tech = SimpleNamespace(
        failure_type="NO_AGENT_AUDIO_PLAYED",
        time_s=0.0,
        turn_index=None,
        severity="critical",
        evidence="Zero audio recordings",
    )
    tl = _make_timeline([], first_tech=first_tech)
    batch_results = {
        "conversation_understanding": {"outcome": {"label": "Can't tell"}},
        "conversation_quality": {
            "what_happened": {"label": "Can't tell"},
        },
    }
    summary = derive_evaluation_summary(batch_results, tl, None)
    assert summary.what_happened == "Heard nothing from the agent"
