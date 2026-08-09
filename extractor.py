"""Text extraction from investor pitch decks (PDF, PPTX, DOCX).

Every reader returns one string per page, slide, or document section, in
document order, so the analyzer can reason about where a claim appeared.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from docx import Document
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

SUPPORTED_SUFFIXES: tuple[str, ...] = (".pdf", ".pptx", ".docx")


class ExtractionError(RuntimeError):
    """Raised when a deck cannot be read, is empty, or has an unsupported format."""


def extract_text(path: Path) -> list[str]:
    """Extract readable text from a pitch deck, one entry per page or slide.

    Args:
        path: Path to a ``.pdf``, ``.pptx``, or ``.docx`` file.

    Returns:
        Page/slide text in document order. Entries may be empty strings for
        image-only pages; slide order is always preserved.

    Raises:
        ExtractionError: The file is missing, unsupported, unreadable, or
            contains no extractable text at all.
    """
    if not path.is_file():
        raise ExtractionError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = _extract_pdf(path)
    elif suffix == ".pptx":
        pages = _extract_pptx(path)
    elif suffix == ".docx":
        pages = _extract_docx(path)
    else:
        supported = ", ".join(SUPPORTED_SUFFIXES)
        raise ExtractionError(
            f"Unsupported file format '{suffix or path.name}'. Supported formats: {supported}"
        )

    if not any(page.strip() for page in pages):
        raise ExtractionError(
            f"No readable text found in {path.name}. "
            "The deck may be image-only or scanned; OCR is not supported."
        )
    return pages


def format_pages(pages: list[str]) -> str:
    """Render extracted pages as a single labelled transcript for the model.

    Args:
        pages: Page/slide text in document order, as returned by ``extract_text``.

    Returns:
        A transcript with an explicit ``--- Page N ---`` marker per page, so the
        model can cite where a claim came from.
    """
    blocks = []
    for index, text in enumerate(pages, start=1):
        body = text.strip() or "[no extractable text on this page]"
        blocks.append(f"--- Page {index} ---\n{body}")
    return "\n\n".join(blocks)


def _extract_pdf(path: Path) -> list[str]:
    """Extract per-page text from a PDF using pdfplumber."""
    try:
        with pdfplumber.open(path) as pdf:
            return [(page.extract_text() or "").strip() for page in pdf.pages]
    except ExtractionError:
        raise
    except Exception as exc:  # pdfplumber/pdfminer raise a wide range of types
        raise ExtractionError(f"Could not read PDF {path.name}: {exc}") from exc


def _extract_pptx(path: Path) -> list[str]:
    """Extract per-slide text from a PPTX using python-pptx."""
    try:
        presentation = Presentation(str(path))
    except Exception as exc:  # python-pptx raises PackageNotFoundError and friends
        raise ExtractionError(f"Could not read PPTX {path.name}: {exc}") from exc

    slides: list[str] = []
    for slide in presentation.slides:
        fragments: list[str] = []
        for shape in _iter_shapes(slide.shapes):
            fragments.extend(_shape_text(shape))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None and notes.text.strip():
                fragments.append(f"[Speaker notes] {notes.text.strip()}")
        slides.append("\n".join(fragments).strip())
    return slides


def _extract_docx(path: Path) -> list[str]:
    """Extract text from a DOCX, splitting into sections at heading paragraphs."""
    try:
        document = Document(str(path))
    except Exception as exc:  # python-docx raises PackageNotFoundError and friends
        raise ExtractionError(f"Could not read DOCX {path.name}: {exc}") from exc

    sections: list[list[str]] = [[]]
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style is not None and str(paragraph.style.name).startswith("Heading"):
            sections.append([])
        sections[-1].append(text)

    for table in document.tables:
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        rows = [row for row in rows if row.strip(" |")]
        if rows:
            sections.append(rows)

    return ["\n".join(block).strip() for block in sections if block]


def _iter_shapes(shapes):
    """Yield every shape on a slide, descending into grouped shapes."""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def _shape_text(shape) -> list[str]:
    """Return the text fragments carried by a single PPTX shape."""
    fragments: list[str] = []
    if shape.has_text_frame:
        text = shape.text_frame.text.strip()
        if text:
            fragments.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                fragments.append(" | ".join(cells))
    if getattr(shape, "has_chart", False):
        try:
            title = shape.chart.chart_title.text_frame.text.strip()
        except Exception:  # charts without a title raise rather than return None
            title = ""
        if title:
            fragments.append(f"[Chart] {title}")
    return fragments
