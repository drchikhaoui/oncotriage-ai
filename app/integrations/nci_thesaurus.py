"""
NCI Thesaurus (NCIt) integration.
Provides official multilingual oncology terminology.
Falls back to local cache at app/data/nci_translations.json.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).parent.parent / "data" / "nci_translations.json"
_API_BASE = "https://api-evsrest.nci.nih.gov/api/v1"
_MEM_CACHE: TTLCache = TTLCache(maxsize=512, ttl=3600)

_local_cache: dict | None = None


def _load_local() -> dict:
    global _local_cache
    if _local_cache is None:
        _local_cache = json.loads(_CACHE_PATH.read_text())
    return _local_cache


class NCIConcept:
    def __init__(self, code: str, name: str, synonyms: list[str], translations: dict[str, str]):
        self.code = code
        self.name = name
        self.synonyms = synonyms
        self.translations = translations  # {"en": ..., "fr": ..., "ar": ...}

    def label(self, language: str = "en") -> str:
        return self.translations.get(language) or self.translations.get("en", self.name)


def get_term_local(term_key: str, language: str = "en") -> Optional[str]:
    """Look up a term in the local NCI cache. Returns translated label or None."""
    data = _load_local()
    entry = data.get("terms", {}).get(term_key)
    if not entry:
        return None
    return entry.get(language) or entry.get("en")


def get_ncit_code(term_key: str) -> Optional[str]:
    """Get the NCIt code for a term key."""
    data = _load_local()
    entry = data.get("terms", {}).get(term_key)
    return entry.get("ncit_code") if entry else None


async def lookup_concept(term: str, language: str = "en") -> Optional[NCIConcept]:
    """
    Look up an NCI concept by term string.
    Checks local cache first, then calls EVS REST API.
    """
    cache_key = f"{term.lower()}::{language}"
    if cache_key in _MEM_CACHE:
        return _MEM_CACHE[cache_key]

    # Check local pre-seeded cache first
    data = _load_local()
    for key, entry in data.get("terms", {}).items():
        if (
            entry.get("en", "").lower() == term.lower()
            or key.lower() == term.lower().replace(" ", "_")
        ):
            concept = NCIConcept(
                code=entry.get("ncit_code", ""),
                name=entry.get("en", term),
                synonyms=[],
                translations={lang: entry.get(lang, "") for lang in ("en", "fr", "ar")},
            )
            _MEM_CACHE[cache_key] = concept
            return concept

    # Fall through to API
    concept = await _fetch_from_api(term)
    if concept:
        _MEM_CACHE[cache_key] = concept
    return concept


async def _fetch_from_api(term: str) -> Optional[NCIConcept]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_API_BASE}/concept/ncit/search",
                params={"term": term, "type": "CONTAINS", "pageSize": 1},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as exc:
        logger.warning("NCI Thesaurus API error: %s", exc)
        return None

    concepts = data.get("concepts", [])
    if not concepts:
        return None

    c = concepts[0]
    return NCIConcept(
        code=c.get("code", ""),
        name=c.get("name", term),
        synonyms=[s.get("name", "") for s in c.get("synonyms", [])[:5]],
        translations={"en": c.get("name", term)},
    )
