import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.reconstruct_calls import _connected_seconds


@pytest.mark.parametrize(
    "call_data",
    [
        {},
        {"meta": None},
        {"meta": {"usage": None}},
        {"meta": {"usage": {"line": None}}},
    ],
)
def test_connected_seconds_is_null_safe_for_optional_metadata(call_data):
    assert _connected_seconds(call_data) is None


def test_connected_seconds_returns_value_when_present():
    call_data = {"meta": {"usage": {"line": {"connected_s": 12}}}}

    assert _connected_seconds(call_data) == 12
