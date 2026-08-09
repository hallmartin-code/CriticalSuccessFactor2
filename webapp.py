"""FastAPI front end: upload a deck, get the one-pager PDF back.

Wraps the same extract -> analyze -> render pipeline the CLI uses. Uploads are
held in memory only for the duration of the request; nothing is persisted.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

import template
from analyzer import AnalysisError, analyze_deck
from extractor import SUPPORTED_SUFFIXES, ExtractionError, extract_text
from renderer import output_filename, render_onepager_bytes

load_dotenv()

logger = logging.getLogger("onepager")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
CHUNK_BYTES = 1 << 20
INDEX_PATH = Path(__file__).with_name("web") / "index.html"

APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

app = FastAPI(
    title=f"{template.ORGANIZATION} — Deck Analyzer",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    """Gate every route behind HTTP basic auth when APP_PASSWORD is configured.

    A public URL that spends Anthropic credits on each request is worth locking
    down; with no password set the app stays open and this is a no-op.
    """
    if not APP_PASSWORD or request.url.path == "/healthz":
        return await call_next(request)

    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
        except (ValueError, UnicodeDecodeError):
            username = password = ""
        if secrets.compare_digest(username, APP_USERNAME) and secrets.compare_digest(
            password, APP_PASSWORD
        ):
            return await call_next(request)

    return Response(
        status_code=401,
        content="Authentication required.",
        headers={"WWW-Authenticate": 'Basic realm="Deck Analyzer"'},
    )


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the upload page."""
    return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness probe that also reports whether the API key is configured."""
    return JSONResponse(
        {
            "status": "ok",
            "anthropic_api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
        }
    )


@app.post("/api/generate")
async def generate(deck: UploadFile = File(...)) -> Response:
    """Analyze an uploaded deck and return the rendered one-pager PDF.

    Args:
        deck: Multipart upload of a ``.pdf``, ``.pptx``, or ``.docx`` file.

    Returns:
        The PDF as an attachment response.

    Raises:
        HTTPException: 400 empty upload, 413 too large, 415 unsupported type,
            422 unreadable deck, 502 upstream Claude failure.
    """
    suffix = Path(deck.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(SUPPORTED_SUFFIXES)
        raise HTTPException(415, f"Unsupported file type '{suffix or 'unknown'}'. Use {supported}.")

    payload = await _read_capped(deck)
    if not payload:
        raise HTTPException(400, "That file is empty.")

    pdf_bytes, filename = await run_in_threadpool(
        _build_onepager, payload, suffix, deck.filename or f"deck{suffix}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


async def _read_capped(upload: UploadFile) -> bytes:
    """Read an upload into memory, aborting once it exceeds the size cap."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def _build_onepager(payload: bytes, suffix: str, source_name: str) -> tuple[bytes, str]:
    """Run the blocking pipeline on a temp copy of the upload; return PDF bytes and filename."""
    handle, temp_name = tempfile.mkstemp(suffix=suffix)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(payload)
        pages = extract_text(temp_path)
        analysis = analyze_deck(pages, source_name=source_name)
    except ExtractionError as exc:
        logger.info("extraction failed for %s: %s", source_name, exc)
        raise HTTPException(422, str(exc)) from exc
    except AnalysisError as exc:
        logger.warning("analysis failed for %s: %s", source_name, exc)
        raise HTTPException(502, str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    logger.info("generated one-pager for %s", analysis.get(template.TITLE_KEY, "unknown"))
    return render_onepager_bytes(analysis), output_filename(analysis)
