"""
Refresh the NCI Thesaurus translation cache.
Run: uv run python scripts/refresh_nci_cache.py
Suitable as a weekly cron job.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

CACHE_PATH = Path(__file__).parent.parent / "app" / "data" / "nci_translations.json"
NCI_SEARCH = "https://api-evsrest.nci.nih.gov/api/v1/concept/ncit/search"

REFRESH_TERMS = [
    ("fever", "Fever"), ("nausea", "Nausea"), ("vomiting", "Vomiting"),
    ("diarrhea", "Diarrhea"), ("constipation", "Constipation"),
    ("fatigue", "Fatigue"), ("pain", "Pain"), ("dyspnea", "Dyspnea"),
    ("mucositis", "Mucositis oral"), ("peripheral_neuropathy", "Peripheral neuropathy"),
    ("bleeding", "Hemorrhage"), ("anxiety", "Anxiety"), ("depression", "Depression"),
    ("anorexia", "Anorexia"), ("skin_rash", "Rash"), ("xerostomia", "Xerostomia"),
    ("papulopustular_eruption", "Papulopustular eruption"),
    ("hand_foot_syndrome", "Palmar-plantar erythrodysesthesia syndrome"),
    ("radiation_dermatitis", "Radiation dermatitis"),
    ("oral_mucositis", "Mucositis oral"),
    ("checkpoint_dermatitis", "Rash maculo-papular"),
]


async def refresh():
    print("Loading existing cache...")
    data = json.loads(CACHE_PATH.read_text())
    terms = data.get("terms", {})
    updated = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for key, search_term in REFRESH_TERMS:
            try:
                resp = await client.get(NCI_SEARCH, params={"term": search_term, "type": "CONTAINS", "pageSize": 1})
                if resp.status_code == 200:
                    concepts = resp.json().get("concepts", [])
                    if concepts:
                        c = concepts[0]
                        if key not in terms:
                            terms[key] = {}
                        terms[key]["ncit_code"] = c.get("code", "")
                        terms[key]["en"] = c.get("name", search_term)
                        updated += 1
                        print(f"  Updated: {key} → {c.get('code', '')} ({c.get('name', '')})")
                await asyncio.sleep(0.2)  # Rate-limit courtesy
            except Exception as exc:
                print(f"  Warning: Failed to refresh {key}: {exc}")

    import time
    data["_meta"]["refreshed"] = time.strftime("%Y-%m-%d")
    data["terms"] = terms
    CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nDone. Updated {updated}/{len(REFRESH_TERMS)} terms. Cache saved to {CACHE_PATH}")


if __name__ == "__main__":
    asyncio.run(refresh())
