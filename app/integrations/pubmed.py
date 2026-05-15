"""
PubMed E-utilities integration for citation retrieval.
https://www.ncbi.nlm.nih.gov/books/NBK25499/
"""
import logging
from typing import Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
_CACHE: TTLCache = TTLCache(maxsize=256, ttl=604800)  # 7-day TTL


class Citation:
    def __init__(
        self,
        pmid: str,
        title: str,
        authors: str,
        journal: str,
        year: str,
        doi: Optional[str] = None,
    ):
        self.pmid = pmid
        self.title = title
        self.authors = authors
        self.journal = journal
        self.year = year
        self.doi = doi

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "url": self.url,
        }

    def format_citation(self) -> str:
        parts = []
        if self.authors:
            parts.append(self.authors)
        parts.append(f'"{self.title}"')
        if self.journal:
            parts.append(self.journal)
        if self.year:
            parts.append(f"({self.year})")
        if self.pmid:
            parts.append(f"PMID: {self.pmid}")
        return ". ".join(parts)


async def search_citations(
    query: str,
    max_results: int = 3,
    publication_types: Optional[list[str]] = None,
) -> list[Citation]:
    """
    Search PubMed for citations relevant to a clinical query.

    Args:
        query: Free-text query, e.g. "pembrolizumab maculopapular rash incidence"
        max_results: Maximum number of citations to return
        publication_types: Optional filter, e.g. ["Randomized Controlled Trial"]

    Returns:
        List of Citation objects
    """
    cache_key = f"{query}::{max_results}::{publication_types}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    pmids = await _esearch(query, max_results, publication_types)
    if not pmids:
        return []

    citations = await _esummary(pmids)
    _CACHE[cache_key] = citations
    return citations


async def _esearch(
    query: str,
    max_results: int,
    publication_types: Optional[list[str]],
) -> list[str]:
    full_query = query
    if publication_types:
        pt_filter = " OR ".join(f'"{pt}"[pt]' for pt in publication_types)
        full_query = f"({query}) AND ({pt_filter})"

    params = {
        "db": "pubmed",
        "term": full_query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_ESEARCH, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("PubMed esearch failed: %s", exc)
        return []

    return data.get("esearchresult", {}).get("idlist", [])


async def _esummary(pmids: list[str]) -> list[Citation]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_ESUMMARY, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("PubMed esummary failed: %s", exc)
        return []

    result = data.get("result", {})
    citations = []
    for pmid in pmids:
        article = result.get(pmid)
        if not article or "error" in article:
            continue

        authors_list = article.get("authors", [])
        if authors_list:
            first = authors_list[0].get("name", "")
            authors = f"{first} et al." if len(authors_list) > 1 else first
        else:
            authors = ""

        year = article.get("pubdate", "")[:4]
        doi = next(
            (
                a.get("value", "")
                for a in article.get("articleids", [])
                if a.get("idtype") == "doi"
            ),
            None,
        )

        citations.append(
            Citation(
                pmid=pmid,
                title=article.get("title", ""),
                authors=authors,
                journal=article.get("source", ""),
                year=year,
                doi=doi,
            )
        )

    return citations
