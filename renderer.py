"""ReportLab rendering of the one-pager, driven entirely by ``template.py``.

Nothing here knows the name of a section or a field: the structure comes from
``template.SECTIONS`` / ``template.CALLOUTS`` and the format from
``template.PALETTE`` / ``TYPE_SCALE`` / ``LAYOUT``.

The page is measured before it is drawn, so the card wraps its content and the
whole stack is centred vertically rather than stretching to the page edges.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Flowable, Frame, KeepInFrame, Paragraph, Spacer

import template

PAGE_WIDTH, PAGE_HEIGHT = LETTER
_UNBOUNDED = 10_000.0
_MIN_CARD_HEIGHT = 330.0

_EMOJI_FONT_CANDIDATES = (
    template.FONT_DIR / "NotoEmoji-Regular.ttf",
    Path(r"C:\Windows\Fonts\seguiemj.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf"),
    Path("/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf"),
)
_EMOJI_FONT_NAME = "OnePagerEmoji"
_FONT_CACHE: dict[str, str] = {}
_EMOJI_CACHE: list[str | None] = []


# --- public API -------------------------------------------------------------


def render_onepager(analysis: dict[str, str], output_dir: Path | None = None) -> Path:
    """Render the analysis to ``<company_name>_onepager.pdf`` and return the path.

    Args:
        analysis: Field dict keyed by ``template.field_keys()``.
        output_dir: Destination directory. Defaults to the working directory.
    """
    output_dir = Path(output_dir) if output_dir is not None else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename(analysis)
    output_path.write_bytes(render_onepager_bytes(analysis))
    return output_path


def render_onepager_bytes(analysis: dict[str, str]) -> bytes:
    """Render the analysis and return the PDF as bytes, without touching disk.

    Args:
        analysis: Field dict keyed by ``template.field_keys()``.
    """
    buffer = io.BytesIO()
    canvas = pdfcanvas.Canvas(buffer, pagesize=LETTER)
    title = analysis.get(template.TITLE_KEY) or "Company"
    canvas.setTitle(f"{title} — {template.DOCUMENT_LABEL}")
    canvas.setAuthor(template.ORGANIZATION)
    canvas.setSubject(template.DOCUMENT_TITLE)

    _draw_page(canvas, analysis)

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def output_filename(analysis: dict[str, str]) -> str:
    """Return the download filename for an analysis."""
    return f"{_slugify(analysis.get(template.TITLE_KEY, 'company'))}_onepager.pdf"


# --- measurement ------------------------------------------------------------


@dataclass
class _Plan:
    """Everything measured up front so the card can be sized to its content."""

    title: str
    title_size: float
    subtitle: Paragraph | None
    subtitle_height: float
    header_height: float
    left_story: list[Flowable]
    right_story: list[Flowable]
    left_width: float
    right_width: float
    columns_height: float
    disclosure: Paragraph
    disclosure_height: float
    card_height: float


def _plan(analysis: dict[str, str], card_width: float, max_card_height: float) -> _Plan:
    """Measure every block and decide the card height."""
    layout = template.LAYOUT
    pad = layout["card_padding"]
    content_width = card_width - 2 * pad
    gutter = layout["column_gutter"]
    left_width = (content_width - gutter) * layout["left_column_ratio"]
    right_width = content_width - gutter - left_width

    fonts = _fonts()
    scale = template.TYPE_SCALE["title"]
    title = analysis.get(template.TITLE_KEY) or "Company"
    title_size = _fit_font_size(
        title, fonts["display"], scale["size"], scale["min_size"], content_width
    )

    subtitle_text = analysis.get(template.SUBTITLE_KEY) or ""
    subtitle = None
    subtitle_height = 0.0
    if subtitle_text and subtitle_text != template.FALLBACK_VALUE:
        subtitle = Paragraph(escape(subtitle_text), _style("subtitle", "body", "text_secondary"))
        subtitle_height = subtitle.wrap(content_width, _UNBOUNDED)[1]

    # eyebrow line + gap, title, gap, subtitle, gap, hairline, gap
    header_height = 12 + template.TYPE_SCALE["eyebrow"]["size"] + title_size + 8
    header_height += subtitle_height + 10 + 12

    left_story = _column_story(analysis, "left", left_width)
    right_story = _column_story(analysis, "right", right_width)
    columns_height = max(
        _story_height(left_story, left_width), _story_height(right_story, right_width)
    )

    disclosure = Paragraph(escape(template.DISCLOSURE), _style("disclosure", "body", "text_faint"))
    disclosure_height = disclosure.wrap(content_width, _UNBOUNDED)[1]

    desired = pad + header_height + columns_height + 14 + disclosure_height + 9 + pad
    card_height = max(min(desired, max_card_height), min(_MIN_CARD_HEIGHT, max_card_height))

    return _Plan(
        title=title,
        title_size=title_size,
        subtitle=subtitle,
        subtitle_height=subtitle_height,
        header_height=header_height,
        left_story=left_story,
        right_story=right_story,
        left_width=left_width,
        right_width=right_width,
        columns_height=columns_height,
        disclosure=disclosure,
        disclosure_height=disclosure_height,
        card_height=card_height,
    )


def _story_height(story: list[Flowable], width: float) -> float:
    """Sum the wrapped heights of a column's flowables."""
    return sum(flowable.wrap(width, _UNBOUNDED)[1] for flowable in story)


# --- page composition -------------------------------------------------------


def _draw_page(canvas: pdfcanvas.Canvas, analysis: dict[str, str]) -> None:
    """Paint the background, then centre the brand / card / footer stack."""
    layout = template.LAYOUT
    margin = layout["page_margin"]
    brand_height = layout["brand_block_height"]
    footer_height = layout["footer_block_height"]
    gap_top = layout["gap_brand_to_card"]
    gap_bottom = layout["gap_card_to_footer"]

    canvas.setFillColor(_color("page"))
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    card_width = PAGE_WIDTH - 2 * margin
    max_card_height = (
        PAGE_HEIGHT - 2 * margin - brand_height - footer_height - gap_top - gap_bottom
    )
    plan = _plan(analysis, card_width, max_card_height)

    stack_height = brand_height + gap_top + plan.card_height + gap_bottom + footer_height
    stack_top = min(PAGE_HEIGHT - margin, (PAGE_HEIGHT + stack_height) / 2)

    brand_bottom = stack_top - brand_height
    card_top = brand_bottom - gap_top
    card_bottom = card_top - plan.card_height
    footer_bottom = card_bottom - gap_bottom - footer_height

    _draw_brand_lockup(canvas, margin, brand_bottom)
    _draw_card(canvas, plan, margin, card_bottom, card_width, plan.card_height)
    _draw_footer(canvas, footer_bottom)


def _draw_brand_lockup(canvas: pdfcanvas.Canvas, x: float, y: float) -> None:
    """Draw the tri-colour mark plus the stacked organization wordmark."""
    fonts = _fonts()
    size = template.LAYOUT["brand_mark_size"]
    _draw_brand_mark(canvas, x, y, size)

    words = template.ORGANIZATION.split()
    primary = " ".join(words[:-1]) if len(words) > 1 else template.ORGANIZATION
    secondary = words[-1] if len(words) > 1 else ""

    text_x = x + size + 10
    _draw_tracked(
        canvas, text_x, y + size - 11, primary.upper(), fonts["display"], 11,
        _color("text_primary"), 0.5,
    )
    if secondary:
        _draw_tracked(
            canvas, text_x, y + size - 22, secondary.upper(), fonts["mono"], 6.4,
            _color("text_muted"), 1.9,
        )


def _draw_brand_mark(canvas: pdfcanvas.Canvas, x: float, y: float, size: float) -> None:
    """Draw the three-figure ring mark: three arcs, each with a head inside."""
    center_x, center_y = x + size / 2, y + size / 2
    ring_radius = size * 0.34
    head_radius = size * 0.085
    head_orbit = size * 0.17

    canvas.saveState()
    canvas.setLineCap(1)
    canvas.setLineWidth(size * 0.13)
    figures = (
        ("coral", 105, 95, 150),
        ("amber", 335, 95, 20),
        ("teal", 215, 95, 265),
    )
    for token, start_angle, extent, head_angle in figures:
        color = _color(token)
        canvas.setStrokeColor(color)
        path = canvas.beginPath()
        path.arc(
            center_x - ring_radius,
            center_y - ring_radius,
            center_x + ring_radius,
            center_y + ring_radius,
            start_angle,
            extent,
        )
        canvas.drawPath(path, stroke=1, fill=0)

        canvas.setFillColor(color)
        radians = math.radians(head_angle)
        canvas.circle(
            center_x + head_orbit * math.cos(radians),
            center_y + head_orbit * math.sin(radians),
            head_radius,
            stroke=0,
            fill=1,
        )
    canvas.restoreState()


def _draw_card(
    canvas: pdfcanvas.Canvas,
    plan: _Plan,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    """Draw the gradient card shell and lay out everything inside it."""
    layout = template.LAYOUT
    radius = layout["card_radius"]
    pad = layout["card_padding"]

    canvas.saveState()
    clip = canvas.beginPath()
    clip.roundRect(x, y, width, height, radius)
    canvas.clipPath(clip, stroke=0, fill=0)
    canvas.linearGradient(
        x, y + height, x, y, (_color("card_top"), _color("card_bottom")), extend=True
    )
    canvas.restoreState()

    canvas.setStrokeColor(_color("hairline"))
    canvas.setLineWidth(layout["card_border_width"])
    canvas.roundRect(x, y, width, height, radius, stroke=1, fill=0)

    _draw_accent_rule(
        canvas,
        x + pad,
        y + height - layout["accent_rule_height"] / 2,
        width - 2 * pad,
        layout["accent_rule_height"],
    )

    content_x = x + pad
    content_width = width - 2 * pad
    cursor = y + height - pad

    cursor = _draw_eyebrow(canvas, content_x, cursor, template.DOCUMENT_LABEL)
    cursor = _draw_title(canvas, content_x, cursor, plan)
    cursor -= 10
    _draw_hairline(canvas, content_x, cursor, content_width)
    cursor -= 12

    disclosure_top = y + pad + plan.disclosure_height + 9
    plan.disclosure.drawOn(canvas, content_x, y + pad)
    _draw_hairline(canvas, content_x, disclosure_top, content_width)

    _draw_columns(canvas, plan, content_x, disclosure_top + 14, cursor)


def _draw_accent_rule(
    canvas: pdfcanvas.Canvas, x: float, y: float, width: float, height: float
) -> None:
    """Draw the coral-to-amber-to-teal gradient bar across the top of the card."""
    canvas.saveState()
    clip = canvas.beginPath()
    clip.roundRect(x, y, width, height, height / 2)
    canvas.clipPath(clip, stroke=0, fill=0)
    canvas.linearGradient(
        x, y, x + width, y,
        tuple(_color(token) for token in template.ACCENT_SEQUENCE),
        extend=True,
    )
    canvas.restoreState()


def _draw_eyebrow(canvas: pdfcanvas.Canvas, x: float, top: float, text: str) -> float:
    """Draw the teal dot plus mono label; return the new cursor position."""
    scale = template.TYPE_SCALE["eyebrow"]
    baseline = top - scale["size"]
    canvas.setFillColor(_color("teal"))
    canvas.circle(x + 2.5, baseline + scale["size"] * 0.33, 2.5, stroke=0, fill=1)
    _draw_tracked(
        canvas, x + 11, baseline, text.upper(), _fonts()["mono"], scale["size"],
        _color("teal"), scale.get("tracking", 0),
    )
    return baseline - 12


def _draw_title(canvas: pdfcanvas.Canvas, x: float, top: float, plan: _Plan) -> float:
    """Draw the company name and tagline; return the new cursor position."""
    baseline = top - plan.title_size
    canvas.setFillColor(_color("text_primary"))
    canvas.setFont(_fonts()["display"], plan.title_size)
    canvas.drawString(x, baseline, plan.title)
    cursor = baseline - 8
    if plan.subtitle is not None:
        plan.subtitle.drawOn(canvas, x, cursor - plan.subtitle_height)
        cursor -= plan.subtitle_height
    return cursor


def _draw_hairline(canvas: pdfcanvas.Canvas, x: float, y: float, width: float) -> None:
    """Draw a single hairline rule."""
    canvas.setStrokeColor(_color("hairline"))
    canvas.setLineWidth(0.6)
    canvas.line(x, y, x + width, y)


def _draw_columns(
    canvas: pdfcanvas.Canvas, plan: _Plan, x: float, bottom: float, top: float
) -> None:
    """Lay out the two body columns, shrinking content rather than spilling to page two."""
    height = max(top - bottom, 1)
    gutter = template.LAYOUT["column_gutter"]
    columns = (
        (x, plan.left_width, plan.left_story),
        (x + plan.left_width + gutter, plan.right_width, plan.right_story),
    )
    for column_x, column_width, story in columns:
        if not story:
            continue
        frame = Frame(
            column_x, bottom, column_width, height,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0,
        )
        frame.addFromList([KeepInFrame(column_width, height, story, mode="shrink")], canvas)


def _column_story(analysis: dict[str, str], column: str, width: float) -> list[Flowable]:
    """Build the flowables for one column: its sections, then any callouts."""
    story: list[Flowable] = []
    for index, section in enumerate(template.sections_for(column)):
        if index:
            story.append(Spacer(1, template.LAYOUT["section_gap"]))
        story.append(_section_label(section.label))
        story.append(Spacer(1, 3))
        story.append(
            Paragraph(escape(analysis[section.key]), _style("body", "body", "text_secondary"))
        )

    if column == "right":
        for callout in template.CALLOUTS:
            story.append(Spacer(1, template.LAYOUT["callout_gap"] + 6))
            story.append(_callout_panel(callout, analysis, width))
    return story


def _section_label(text: str) -> Flowable:
    """Return the tracked, uppercase heading used above each body section."""
    scale = template.TYPE_SCALE["section_label"]
    return _TrackedLabel(
        text.upper(),
        _fonts()["body_bold"],
        scale["size"],
        scale["leading"],
        _color("text_muted"),
        scale.get("tracking", 0),
        rule_color=_color("hairline"),
    )


def _callout_panel(callout: template.Callout, analysis: dict[str, str], width: float) -> Flowable:
    """Return a filled accent panel for one callout."""
    text_color = _color("on_accent")
    marker_font = _emoji_font(callout.marker) if callout.marker else None
    prefix = f'<font name="{marker_font}">{callout.marker}</font>  ' if marker_font else ""

    content: list[Flowable] = [
        Paragraph(
            prefix + escape(callout.label.upper()),
            _style("callout_label", "body_bold", color=text_color),
        ),
        Spacer(1, 5),
        Paragraph(
            escape(analysis[callout.headline_key]),
            _style("callout_headline", "display", color=text_color),
        ),
        Spacer(1, 5),
        Paragraph(
            escape(analysis[callout.body_key]),
            _style("callout_body", "body", color=text_color),
        ),
    ]
    return _RoundedPanel(
        content,
        width=width,
        radius=template.LAYOUT["callout_radius"],
        padding=template.LAYOUT["callout_padding"],
        fill=_color(callout.accent),
    )


def _draw_footer(canvas: pdfcanvas.Canvas, bottom: float) -> None:
    """Draw the centred house footer line: title, page, compiled-on stamp, and mark."""
    fonts = _fonts()
    scale = template.TYPE_SCALE["footer"]
    stamp = (
        f"{template.DOCUMENT_TITLE}     1     "
        f"Compiled on {date.today():%d %B %Y} by {template.ORGANIZATION}"
    )
    mark_size = 12
    gap = 9
    text_width = pdfmetrics.stringWidth(stamp, fonts["body"], scale["size"])
    start_x = (PAGE_WIDTH - (text_width + gap + mark_size)) / 2
    baseline = bottom + (template.LAYOUT["footer_block_height"] - scale["size"]) / 2

    canvas.setFillColor(_color("text_faint"))
    canvas.setFont(fonts["body"], scale["size"])
    canvas.drawString(start_x, baseline, stamp)
    _draw_brand_mark(canvas, start_x + text_width + gap, baseline - 3, mark_size)


# --- flowables --------------------------------------------------------------


class _TrackedLabel(Flowable):
    """A single-line label with letter tracking and an optional hairline beneath it."""

    def __init__(
        self,
        text: str,
        font: str,
        size: float,
        leading: float,
        color,
        tracking: float = 0.0,
        rule_color=None,
    ) -> None:
        super().__init__()
        self.text = text
        self.font = font
        self.size = size
        self.leading = leading
        self.color = color
        self.tracking = tracking
        self.rule_color = rule_color
        self._width = 0.0

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        """Reserve one line, plus room for the rule when one is configured."""
        self._width = available_width
        return available_width, self.leading + (5 if self.rule_color else 0)

    def draw(self) -> None:
        """Paint the label and its rule."""
        canvas = self.canv
        rule_space = 5 if self.rule_color else 0
        _draw_tracked(
            canvas, 0, rule_space + (self.leading - self.size) * 0.5, self.text,
            self.font, self.size, self.color, self.tracking,
        )
        if self.rule_color:
            canvas.setStrokeColor(self.rule_color)
            canvas.setLineWidth(0.5)
            canvas.line(0, rule_space - 2, self._width, rule_space - 2)


class _RoundedPanel(Flowable):
    """A rounded, filled panel wrapping a stack of flowables."""

    def __init__(
        self, content: list[Flowable], *, width: float, radius: float, padding: float, fill
    ) -> None:
        super().__init__()
        self.content = content
        self.width = width
        self.radius = radius
        self.padding = padding
        self.fill = fill
        self._heights: list[float] = []
        self._height = 0.0

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        """Measure the stacked content and add padding on all four sides."""
        if available_width > 0:
            self.width = min(self.width, available_width)
        inner_width = max(self.width - 2 * self.padding, 1)
        self._heights = [
            flowable.wrap(inner_width, available_height)[1] for flowable in self.content
        ]
        self._height = sum(self._heights) + 2 * self.padding
        return self.width, self._height

    def draw(self) -> None:
        """Paint the panel background, then each child flowable top-down."""
        canvas = self.canv
        canvas.setFillColor(self.fill)
        canvas.roundRect(0, 0, self.width, self._height, self.radius, stroke=0, fill=1)
        y = self._height - self.padding
        for flowable, height in zip(self.content, self._heights):
            y -= height
            flowable.drawOn(canvas, self.padding, y)


# --- fonts, colours, helpers ------------------------------------------------


def _fonts() -> dict[str, str]:
    """Resolve every template font role to a registered font name, once per process.

    Brand faces are picked up from the ``fonts/`` directory when present; each role
    otherwise falls back to a built-in ReportLab face so rendering never fails.
    """
    if _FONT_CACHE:
        return _FONT_CACHE
    for role, spec in template.FONT_ROLES.items():
        _FONT_CACHE[role] = spec["fallback"]
        for filename in spec["files"]:
            path = template.FONT_DIR / filename
            if not path.is_file():
                continue
            name = f"Brand-{role}"
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:  # a malformed drop-in font must not break rendering
                continue
            _FONT_CACHE[role] = name
            break
    return _FONT_CACHE


def _emoji_font(char: str) -> str | None:
    """Return a font that can draw ``char``, or None so the caller drops the marker."""
    if not _EMOJI_CACHE:
        _EMOJI_CACHE.append(_register_emoji_font())
    name = _EMOJI_CACHE[0]
    if name is None:
        return None
    coverage = pdfmetrics.getFont(name).face.charToGlyph
    return name if all(coverage.get(ord(c)) for c in char) else None


def _register_emoji_font() -> str | None:
    """Register the first available emoji-capable font, if any."""
    for path in _EMOJI_FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(_EMOJI_FONT_NAME, str(path)))
        except Exception:  # bitmap-only and collection fonts raise a range of errors
            continue
        return _EMOJI_FONT_NAME
    return None


def _draw_tracked(
    canvas: pdfcanvas.Canvas,
    x: float,
    y: float,
    text: str,
    font: str,
    size: float,
    color,
    tracking: float = 0.0,
) -> None:
    """Draw one line with letter tracking, resetting the char-space text state after.

    ReportLab exposes char spacing only on text objects, and the PDF ``Tc`` operator
    persists across text objects — leaving it set would letterspace every later
    paragraph on the page.
    """
    text_object = canvas.beginText(x, y)
    text_object.setFont(font, size)
    text_object.setFillColor(color)
    text_object.setCharSpace(tracking)
    text_object.textOut(text)
    text_object.setCharSpace(0)
    canvas.drawText(text_object)


def _color(token: str):
    """Look up a palette token and return a ReportLab colour."""
    return HexColor(template.PALETTE[token])


def _style(scale_key: str, font_role: str, color_token: str | None = None, *, color=None):
    """Build a ParagraphStyle from a type-scale entry, a font role, and a colour."""
    scale = template.TYPE_SCALE[scale_key]
    return ParagraphStyle(
        f"{scale_key}-{font_role}",
        fontName=_fonts()[font_role],
        fontSize=scale["size"],
        leading=scale["leading"],
        textColor=color if color is not None else _color(color_token or "text_primary"),
    )


def _fit_font_size(text: str, font: str, start: float, minimum: float, max_width: float) -> float:
    """Return the largest size in [minimum, start] at which text fits max_width."""
    size = start
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _slugify(value: str) -> str:
    """Turn a company name into a filesystem-safe filename stem."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return cleaned[:60] or "company"
