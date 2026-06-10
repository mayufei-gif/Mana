from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import database

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs() -> dict:
    jobs = database.fetch_all(
        """
        SELECT j.*, v.title AS video_title
        FROM jobs j
        JOIN videos v ON v.id = j.video_id
        ORDER BY j.id DESC
        LIMIT 100
        """
    )
    return {"ok": True, "data": jobs}


@router.get("/{job_id}")
def get_job(job_id: int) -> dict:
    job = database.fetch_one(
        """
        SELECT j.*, v.title AS video_title
        FROM jobs j
        JOIN videos v ON v.id = j.video_id
        WHERE j.id = ?
        """,
        (job_id,),
    )
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "data": job}
