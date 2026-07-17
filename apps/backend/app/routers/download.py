"""Signed temporary download links with HTTP Range support and brute-force guard."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import DownloadLink, StoredFile
from ..security.ratelimit import is_locked_out, register_failure
from ..storage import get_storage_provider

router = APIRouter(tags=["download"])


def _parse_range(range_header: str | None, size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    try:
        spec = range_header.split("=", 1)[1].split(",")[0]
        start_s, end_s = spec.split("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else size - 1
        if start > end or start >= size:
            return None
        return start, min(end, size - 1)
    except (ValueError, IndexError):
        return None


@router.get("/download/{token}")
async def download(token: str, request: Request, range: str | None = Header(default=None),
                   session: AsyncSession = Depends(get_session)):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if await is_locked_out(f"dl:{ip}", threshold=30):
        raise HTTPException(status_code=429, detail="too many attempts")

    if len(token) < 16:
        await register_failure(f"dl:{ip}")
        raise HTTPException(status_code=404, detail="not found")

    link = (await session.execute(
        select(DownloadLink).where(DownloadLink.token == token)
    )).scalar_one_or_none()
    if not link or link.revoked:
        await register_failure(f"dl:{ip}")
        raise HTTPException(status_code=404, detail={"code": "link_expired",
                            "message": "Временная ссылка недействительна."})
    if link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail={"code": "link_expired",
                            "message": "Временная ссылка истекла."})
    if link.max_downloads is not None and link.download_count >= link.max_downloads:
        raise HTTPException(status_code=410, detail={"code": "link_expired",
                            "message": "Лимит скачиваний исчерпан."})

    sf = await session.get(StoredFile, link.stored_file_id)
    if not sf or sf.deleted_at:
        raise HTTPException(status_code=404, detail="file removed")

    provider = get_storage_provider()
    # S3-style: redirect to presigned url
    presigned = await provider.presigned_url(sf.rel_path, sf.filename, 3600)
    if presigned:
        link.download_count += 1
        sf.last_access_at = datetime.now(timezone.utc)
        await session.commit()
        return RedirectResponse(presigned)

    size = await provider.size(sf.rel_path)
    rng = _parse_range(range, size)
    link.download_count += 1
    sf.last_access_at = datetime.now(timezone.utc)
    await session.commit()

    headers = {
        "Content-Disposition": f'attachment; filename="{sf.filename}"',
        "Accept-Ranges": "bytes",
        "Content-Type": sf.mime_type or "application/octet-stream",
    }
    if rng:
        start, end = rng
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(provider.open_stream(sf.rel_path, start, end), status_code=206,
                                 headers=headers, media_type=headers["Content-Type"])
    headers["Content-Length"] = str(size)
    return StreamingResponse(provider.open_stream(sf.rel_path), headers=headers,
                             media_type=headers["Content-Type"])
