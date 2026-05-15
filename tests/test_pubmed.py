"""
Tests for PubMed E-utilities integration.
All HTTP calls are mocked with respx.
"""
import pytest
import respx
from httpx import Response

from app.integrations.pubmed import (
    _CACHE,
    Citation,
    search_citations,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


MOCK_ESEARCH_RESPONSE = {
    "esearchresult": {
        "count": "3",
        "retmax": "3",
        "idlist": ["38621045", "38100234", "37654321"],
    }
}

MOCK_ESUMMARY_RESPONSE = {
    "result": {
        "38621045": {
            "uid": "38621045",
            "title": "Pembrolizumab dermatologic adverse events: a systematic review",
            "authors": [
                {"name": "Smith A"},
                {"name": "Jones B"},
                {"name": "Lee C"},
            ],
            "source": "J Immunother Cancer",
            "pubdate": "2024 Jan",
            "articleids": [{"idtype": "doi", "value": "10.1136/jitc-2024-001"}],
        },
        "38100234": {
            "uid": "38100234",
            "title": "CTCAE grading of checkpoint inhibitor rash: interobserver variability",
            "authors": [{"name": "Garcia M"}],
            "source": "Ann Oncol",
            "pubdate": "2023 Dec",
            "articleids": [],
        },
        "37654321": {
            "uid": "37654321",
            "title": "Incidence and management of immune-related adverse events",
            "authors": [
                {"name": "Brown K"},
                {"name": "Wilson P"},
            ],
            "source": "JAMA Oncol",
            "pubdate": "2023 Aug",
            "articleids": [{"idtype": "doi", "value": "10.1001/jamaoncol.2023.001"}],
        },
    }
}


class TestSearchCitations:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_citations_on_success(self):
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, json=MOCK_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
            return_value=Response(200, json=MOCK_ESUMMARY_RESPONSE)
        )
        results = await search_citations("pembrolizumab maculopapular rash", max_results=3)
        assert len(results) == 3
        assert all(isinstance(c, Citation) for c in results)

    @pytest.mark.asyncio
    @respx.mock
    async def test_citation_fields_populated(self):
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, json=MOCK_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
            return_value=Response(200, json=MOCK_ESUMMARY_RESPONSE)
        )
        results = await search_citations("pembrolizumab rash")
        cit = results[0]
        assert cit.pmid == "38621045"
        assert "Pembrolizumab" in cit.title
        assert cit.authors == "Smith A et al."
        assert cit.journal == "J Immunother Cancer"
        assert cit.year == "2024"
        assert cit.doi == "10.1136/jitc-2024-001"
        assert cit.url.startswith("https://pubmed.ncbi.nlm.nih.gov/")

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_no_results(self):
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, json={"esearchresult": {"count": "0", "retmax": "0", "idlist": []}})
        )
        results = await search_citations("completely obscure query xyz123")
        assert results == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_returns_empty(self):
        import httpx
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            side_effect=httpx.ConnectError("refused")
        )
        results = await search_citations("pembrolizumab rash")
        assert results == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_caches_result(self):
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, json=MOCK_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
            return_value=Response(200, json=MOCK_ESUMMARY_RESPONSE)
        )
        r1 = await search_citations("pembrolizumab rash", max_results=3)
        r2 = await search_citations("pembrolizumab rash", max_results=3)
        assert r1 is r2
        # Both esearch and esummary only called once each
        esearch_calls = sum(1 for call in respx.calls if "esearch" in str(call.request.url))
        assert esearch_calls == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_publication_type_filter_added_to_query(self):
        captured_url = []
        def capture(req):
            captured_url.append(str(req.url))
            return Response(200, json={"esearchresult": {"count": "0", "idlist": []}})
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(side_effect=capture)
        await search_citations("rash", publication_types=["Randomized Controlled Trial"])
        assert captured_url
        assert "Randomized" in captured_url[0] or "%22Randomized" in captured_url[0]


class TestCitationModel:
    def test_format_citation_with_all_fields(self):
        cit = Citation(
            pmid="12345",
            title="Test Title",
            authors="Smith A et al.",
            journal="JAMA",
            year="2024",
            doi="10.1001/test",
        )
        formatted = cit.format_citation()
        assert "Test Title" in formatted
        assert "Smith A" in formatted
        assert "JAMA" in formatted
        assert "2024" in formatted
        assert "12345" in formatted

    def test_to_dict_has_url(self):
        cit = Citation(pmid="99999", title="Title", authors="Auth", journal="J", year="2024")
        d = cit.to_dict()
        assert d["url"] == "https://pubmed.ncbi.nlm.nih.gov/99999/"
        assert d["pmid"] == "99999"
