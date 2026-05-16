from fastapi import APIRouter, Depends, Query

from app.api.deps import require_clinician
from app.db.database import get_recent_triages, get_triage_detail

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(require_clinician)])


@router.get("/recent")
async def recent_triages(
    limit: int = Query(default=50, le=200),
    level: str | None = Query(default=None, description="Filter: EMERGENCY, URGENT, ROUTINE, SELF_CARE"),
) -> dict:
    """Return recent triage sessions for clinician dashboard."""
    valid_levels = {"EMERGENCY", "URGENT", "ROUTINE", "SELF_CARE"}
    level_filter = level.upper() if level and level.upper() in valid_levels else None
    rows = await get_recent_triages(limit=limit, level_filter=level_filter)
    return {"triages": rows, "count": len(rows)}


@router.get("/session/{session_id}")
async def triage_detail(session_id: str) -> dict:
    """Return full detail for a specific triage session."""
    detail = await get_triage_detail(session_id)
    if not detail:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.get("/stats")
async def triage_stats() -> dict:
    """Return aggregate stats for all triage sessions."""
    all_rows = await get_recent_triages(limit=10000)
    if not all_rows:
        return {"total": 0, "by_level": {}}
    by_level: dict[str, int] = {}
    for row in all_rows:
        lvl = row["triage_level"]
        by_level[lvl] = by_level.get(lvl, 0) + 1
    return {
        "total": len(all_rows),
        "by_level": by_level,
        "llm_used_count": sum(1 for r in all_rows if r.get("llm_used")),
    }
