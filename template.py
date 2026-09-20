"""Document template — the single source of truth for one-pager structure and format.

Nothing in this module is specific to any company, deck, or analysis run. It
declares three things:

* ``PALETTE`` / ``TYPE_SCALE`` / ``LAYOUT`` — the visual format.
* ``SECTIONS`` / ``CALLOUTS`` — the document structure, in render order.
* ``FIELD_GUIDANCE`` — the fields to be analyzed in any future deck.

Both the analyzer and the renderer are driven from here: adding a field means
adding one entry below, and it flows into the model's JSON schema, the prompt,
and the rendered page automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --- identity ---------------------------------------------------------------

ORGANIZATION = "TEN Capital Network"
DOCUMENT_LABEL = "Investor One-Pager"
DOCUMENT_TITLE = "Deck Analysis"

# --- palette ----------------------------------------------------------------

PALETTE: dict[str, str] = {
    "page": "#0B1526",
    "card_top": "#101E33",
    "card_bottom": "#16283F",
    "hairline": "#1E354F",
    "coral": "#EE5A4E",
    "coral_soft": "#F0776C",
    "amber": "#F3A22A",
    "teal": "#35BEBB",
    "text_primary": "#F3F6FA",
    "text_secondary": "#C4D0E0",
    "text_muted": "#7E90A8",
    "text_faint": "#5C6E86",
    "on_accent": "#17130E",
}

ACCENT_SEQUENCE = ("coral", "amber", "teal")

# --- typography -------------------------------------------------------------

FONT_ROLES: dict[str, dict] = {
    "display": {"files": ("Sora-Bold.ttf", "Sora-ExtraBold.ttf"), "fallback": "Helvetica-Bold"},
    "body": {"files": ("Inter-Regular.ttf", "Inter.ttf"), "fallback": "Helvetica"},
    "body_bold": {"files": ("Inter-SemiBold.ttf", "Inter-Bold.ttf"), "fallback": "Helvetica-Bold"},
    "mono": {"files": ("JetBrainsMono-Regular.ttf",), "fallback": "Courier"},
    "mono_bold": {"files": ("JetBrainsMono-Medium.ttf", "JetBrainsMono-Bold.ttf"), "fallback": "Courier-Bold"},
}

FONT_DIR = Path(__file__).with_name("fonts")

TYPE_SCALE: dict[str, dict] = {
    "title": {"size": 25, "leading": 29, "min_size": 15},
    "subtitle": {"size": 9.8, "leading": 13},
    "eyebrow": {"size": 7.4, "leading": 10, "tracking": 1.3},
    "section_label": {"size": 7.2, "leading": 9.5, "tracking": 1.1},
    "body": {"size": 8.6, "leading": 11.6},
    "callout_label": {"size": 7.2, "leading": 9.5, "tracking": 1.0},
    "callout_headline": {"size": 11.5, "leading": 13.5},
    "callout_body": {"size": 7.9, "leading": 10.4},
    "disclosure": {"size": 7.2, "leading": 10},
    "footer": {"size": 7, "leading": 9},
}

# --- layout (points; 72pt = 1in) --------------------------------------------

LAYOUT: dict[str, float] = {
    "page_margin": 28,
    "brand_mark_size": 26,
    "brand_block_height": 30,
    "gap_brand_to_card": 15,
    "card_radius": 16,
    "card_padding": 30,
    "card_border_width": 0.75,
    "accent_rule_height": 2.5,
    "gap_card_to_footer": 13,
    "footer_block_height": 26,
    "column_gutter": 20,
    "left_column_ratio": 0.60,
    "section_gap": 11,
    "callout_radius": 11,
    "callout_padding": 11,
    "callout_gap": 10,
    "logo_width": 48,
    "logo_height": 18,
}

# --- structure --------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """A plain heading-plus-prose block in one of the two body columns."""

    key: str
    label: str
    column: str  # "left" or "right"


@dataclass(frozen=True)
class Callout:
    """A filled accent panel: small label, bold headline, supporting rationale."""

    headline_key: str
    body_key: str
    label: str
    accent: str  # a key in PALETTE
    marker: str = ""  # optional emoji, dropped when no emoji font is available


TITLE_KEY = "company_name"
SUBTITLE_KEY = "tagline"

SECTIONS: tuple[Section, ...] = (
    Section("problem", "Problem", "left"),
    Section("solution", "Solution", "left"),
    Section("traction", "Traction & Key Metrics", "left"),
    Section("market_size", "Market Opportunity", "left"),
    Section("business_model", "Business Model", "left"),
    Section("team", "Team", "right"),
    Section("ask", "The Ask", "right"),
)

CALLOUTS: tuple[Callout, ...] = (
    Callout(
        headline_key="critical_variable",
        body_key="critical_variable_rationale",
        label="Critical Success Factor",
        accent="amber",
        marker="⚡",
    ),
    Callout(
        headline_key="top_activity",
        body_key="top_activity_rationale",
        label="Top Priority Activity",
        accent="teal",
        marker="\U0001f3af",
    ),
)

DISCLOSURE = (
    "Generated from the source deck by an automated analysis. Every figure is drawn from the "
    "deck as submitted and has not been independently verified. Not investment advice."
)

# --- fields to analyze ------------------------------------------------------

FIELD_GUIDANCE: dict[str, str] = {
    "company_name": "The company name exactly as it appears in the deck.",
    "tagline": "One sentence describing what the company does.",
    "problem": "The core problem being solved, with any quantification the deck gives.",
    "solution": "How the company solves the problem, including the mechanism or technology.",
    "traction": "Key metrics and proof points: ARR, users, growth rate, pilots, grants, data.",
    "market_size": "TAM/SAM figures and the methodology behind them, if present.",
    "business_model": "How the company makes money: pricing, unit of sale, contract structure.",
    "team": "Key founders and the background that makes them credible for this company.",
    "ask": "Funding amount sought, instrument/terms, and use of funds.",
    "critical_variable": (
        "The single variable that most determines whether this business succeeds or fails. "
        "Be specific and concrete (for example a named sales-cycle, unit-economics, or "
        "regulatory-approval variable) — not a generic category such as 'execution' or "
        "'the market'. Maximum 8 words."
    ),
    "critical_variable_rationale": (
        "Two to three sentences on why this variable dominates the others, grounded in what "
        "the deck says about this company's stage, model, and risks."
    ),
    "top_activity": (
        "The single highest-leverage activity the team should be doing right now to move the "
        "critical variable. State it as a concrete action, maximum 12 words."
    ),
    "top_activity_rationale": (
        "Two to three sentences on why this activity outranks the alternatives right now."
    ),
}

FALLBACK_VALUE = "Not specified"

ANALYSIS_RULES = (
    "Base every factual field solely on the deck. Do not introduce outside market data, "
    "comparables, or figures the deck does not contain.",
    f'If a field is not addressed anywhere in the deck, return exactly "{FALLBACK_VALUE}".',
    "Keep each descriptive field under 70 words. This is a one-page summary; density matters "
    "more than completeness.",
    "The critical variable and top activity are your analytical judgment, not extraction. "
    "Reason from what the deck reveals about the business model, stage, and risk profile. "
    "Pick the variable whose failure would sink the company even if everything else worked.",
)


def field_keys() -> tuple[str, ...]:
    """Return every analyzed field key, in document order."""
    keys = [TITLE_KEY, SUBTITLE_KEY]
    keys += [section.key for section in SECTIONS]
    for callout in CALLOUTS:
        keys += [callout.headline_key, callout.body_key]
    seen: dict[str, None] = {}
    for key in keys:
        seen.setdefault(key, None)
    missing = [key for key in seen if key not in FIELD_GUIDANCE]
    if missing:
        raise ValueError(f"Template fields missing FIELD_GUIDANCE entries: {missing}")
    return tuple(seen)


def sections_for(column: str) -> tuple[Section, ...]:
    """Return the sections assigned to ``column``, in render order."""
    return tuple(section for section in SECTIONS if section.column == column)
