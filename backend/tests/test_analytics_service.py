from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.analytics.service import AnalyticsService

@pytest.fixture
def analytics_service():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return AnalyticsService(factory)

def test_overview_analytics(analytics_service):
    overview = analytics_service.get_overview_analytics(tenant_id="health_campaign")

    assert overview["total_interactions"] == 50
    assert overview["completed_interactions"] >= 0
    assert overview["abandoned_interactions"] >= 0
    assert "quality_distribution" in overview
    assert "compliance_findings" in overview
    assert overview["total_cost_usd"] > 0
    assert overview["avg_latency_s"] is not None

def test_quality_analytics(analytics_service):
    quality = analytics_service.get_quality_analytics(tenant_id="health_campaign")

    assert "outcomes" in quality
    assert "sentiment" in quality
    assert "emotion" in quality
    assert "overall_quality" in quality
    assert sum(quality["overall_quality"].values()) == 50

def test_cost_analytics(analytics_service):
    cost = analytics_service.get_cost_analytics(tenant_id="health_campaign")

    assert cost["total_cost_usd"] > 0
    assert cost["currency"] == "USD"
    assert cost["total_tokens"] > 0
    assert cost["telephony_cost_usd"] > 0

def test_interactions_page_pagination(analytics_service):
    page1 = analytics_service.get_interactions_page(tenant_id="health_campaign", page=1, page_size=10)

    assert page1["total"] == 50
    assert len(page1["items"]) == 10
    assert page1["page"] == 1
    assert page1["pages"] == 5

    first = page1["items"][0]
    assert "interaction_id" in first
    assert "status" in first
    assert "cost_usd" in first

