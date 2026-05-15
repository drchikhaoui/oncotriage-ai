"""
Tests for OpenFDA FAERS integration.
All HTTP calls are mocked with respx.
"""
import pytest
import respx
from httpx import Response

from app.integrations.openfda import (
    _CACHE,
    build_enrichment_summary,
    fetch_adverse_events_for_drug,
    fetch_top_reactions_for_drug,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the TTL cache between tests."""
    _CACHE.clear()
    yield
    _CACHE.clear()


MOCK_FAERS_RESPONSE = {
    "results": [
        {
            "patient": {
                "drug": [{"medicinalproduct": "PEMBROLIZUMAB"}],
                "reaction": [{"reactionmeddrapt": "Rash maculo-papular"}],
            }
        },
        {
            "patient": {
                "drug": [{"medicinalproduct": "PEMBROLIZUMAB"}],
                "reaction": [{"reactionmeddrapt": "Colitis"}],
            }
        },
    ]
}

MOCK_TOP_REACTIONS = {
    "results": [
        {"term": "Rash maculo-papular", "count": 4127},
        {"term": "Diarrhea", "count": 3810},
        {"term": "Colitis", "count": 2915},
    ]
}


class TestFetchAdverseEvents:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_reports_on_success(self):
        respx.get("https://api.fda.gov/drug/event.json").mock(
            return_value=Response(200, json=MOCK_FAERS_RESPONSE)
        )
        results = await fetch_adverse_events_for_drug("pembrolizumab", "rash maculo-papular")
        assert len(results) > 0
        assert results[0].source == "OpenFDA FAERS"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_404(self):
        respx.get("https://api.fda.gov/drug/event.json").mock(
            return_value=Response(404, json={"error": {"message": "No results"}})
        )
        results = await fetch_adverse_events_for_drug("unknowndrug123", "rash")
        assert results == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_timeout(self):
        import httpx
        respx.get("https://api.fda.gov/drug/event.json").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        results = await fetch_adverse_events_for_drug("pembrolizumab")
        assert results == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_caches_result(self):
        respx.get("https://api.fda.gov/drug/event.json").mock(
            return_value=Response(200, json=MOCK_FAERS_RESPONSE)
        )
        # First call
        r1 = await fetch_adverse_events_for_drug("pembrolizumab", "rash")
        # Second call — should use cache, not make another HTTP request
        r2 = await fetch_adverse_events_for_drug("pembrolizumab", "rash")
        assert r1 is r2  # Same list object from cache
        assert respx.calls.call_count == 1  # Only one HTTP call

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_reaction_term_still_works(self):
        respx.get("https://api.fda.gov/drug/event.json").mock(
            return_value=Response(200, json=MOCK_FAERS_RESPONSE)
        )
        results = await fetch_adverse_events_for_drug("pembrolizumab")
        assert isinstance(results, list)


class TestFetchTopReactions:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_sorted_reactions(self):
        respx.get("https://api.fda.gov/drug/event.json").mock(
            return_value=Response(200, json=MOCK_TOP_REACTIONS)
        )
        results = await fetch_top_reactions_for_drug("pembrolizumab", limit=3)
        assert len(results) == 3
        assert results[0]["term"] == "Rash maculo-papular"
        assert results[0]["count"] == 4127

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_returns_empty(self):
        import httpx
        respx.get("https://api.fda.gov/drug/event.json").mock(
            side_effect=httpx.ConnectError("refused")
        )
        results = await fetch_top_reactions_for_drug("pembrolizumab")
        assert results == []


class TestBuildEnrichmentSummary:
    def test_formats_summary_string(self):
        summary = build_enrichment_summary("pembrolizumab", "rash maculo-papular", 4127)
        assert "pembrolizumab" in summary
        assert "rash maculo-papular" in summary
        assert "4,127" in summary
        assert "FAERS" in summary

    def test_summary_is_string(self):
        result = build_enrichment_summary("drug", "reaction", 100)
        assert isinstance(result, str)
        assert len(result) > 20
