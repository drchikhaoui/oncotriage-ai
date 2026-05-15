"""
OpenFDA Adverse Event Reports (FAERS) integration.
Public API — no authentication required.
https://open.fda.gov/apis/drug/event/
"""
import logging
import time
from typing import Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_OPENFDA_BASE = "https://api.fda.gov/drug/event.json"
_CACHE: TTLCache = TTLCache(maxsize=256, ttl=86400)  # 24-hour TTL


class AdverseEventReport:
    def __init__(self, drug: str, reaction: str, count: int, source: str):
        self.drug = drug
        self.reaction = reaction
        self.count = count
        self.source = source

    def to_dict(self) -> dict:
        return {
            "drug": self.drug,
            "reaction": self.reaction,
            "count": self.count,
            "source": self.source,
        }


async def fetch_adverse_events_for_drug(
    drug_name: str,
    reaction_term: Optional[str] = None,
    limit: int = 5,
) -> list[AdverseEventReport]:
    """
    Query FAERS for adverse event patterns.

    Example: fetch_adverse_events_for_drug("pembrolizumab", "rash maculo-papular")
    Returns top reported similar events to enrich reasoning trace.
    """
    cache_key = f"{drug_name.lower()}::{(reaction_term or '').lower()}::{limit}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    results = await _fetch_from_openfda(drug_name, reaction_term, limit)
    _CACHE[cache_key] = results
    return results


async def fetch_top_reactions_for_drug(drug_name: str, limit: int = 5) -> list[dict]:
    """
    Get the most commonly reported reactions for a drug from FAERS.
    Returns list of {term, count} sorted by frequency.
    """
    cache_key = f"top_reactions::{drug_name.lower()}::{limit}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = _OPENFDA_BASE
    params = {
        "search": f'patient.drug.medicinalproduct:"{drug_name}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("OpenFDA top reactions fetch failed: %s", exc)
        return []

    results = [
        {"term": item.get("term", ""), "count": item.get("count", 0)}
        for item in data.get("results", [])
    ]
    _CACHE[cache_key] = results
    return results


def build_enrichment_summary(
    drug_name: str,
    reaction_term: str,
    report_count: int,
) -> str:
    """Format an OpenFDA FAERS fact for inclusion in a reasoning trace."""
    return (
        f"Per OpenFDA FAERS, '{reaction_term}' is a reported adverse reaction for "
        f"{drug_name} (n={report_count:,} reports in FAERS database). "
        f"Source: OpenFDA FAERS, accessed {time.strftime('%Y-%m-%d')}."
    )


async def _fetch_from_openfda(
    drug_name: str,
    reaction_term: Optional[str],
    limit: int,
) -> list[AdverseEventReport]:
    search_parts = [f'patient.drug.medicinalproduct:"{drug_name}"']
    if reaction_term:
        search_parts.append(f'patient.reaction.reactionmeddrapt:"{reaction_term}"')

    params: dict = {"search": " AND ".join(search_parts), "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_OPENFDA_BASE, params=params)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("OpenFDA request timed out for drug=%s", drug_name)
        return []
    except Exception as exc:
        logger.warning("OpenFDA request failed: %s", exc)
        return []

    reports = []
    for r in data.get("results", [])[:limit]:
        reactions = r.get("patient", {}).get("reaction", [])
        drugs = r.get("patient", {}).get("drug", [])
        matched_drug = drug_name
        for d in drugs:
            name = d.get("medicinalproduct", "")
            if drug_name.lower() in name.lower():
                matched_drug = name
                break
        for rx in reactions[:1]:
            reports.append(
                AdverseEventReport(
                    drug=matched_drug,
                    reaction=rx.get("reactionmeddrapt", ""),
                    count=1,
                    source="OpenFDA FAERS",
                )
            )

    return reports
