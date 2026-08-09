"""Generate a minimal multi-slide sample pitch deck PDF for smoke-testing the CLI."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import landscape, LETTER
from reportlab.pdfgen import canvas as pdfcanvas

SLIDES: list[tuple[str, list[str]]] = [
    (
        "Verdant Grid",
        [
            "Forecasting software that keeps distributed energy grids stable.",
            "Seed round — 2026",
        ],
    ),
    (
        "The Problem",
        [
            "US utilities curtailed 8.2 TWh of renewable generation in 2025 because",
            "they cannot forecast distributed solar and battery output hour-by-hour.",
            "Curtailment cost operators an estimated $1.4B last year.",
            "Legacy SCADA forecasting tools were built for centralised thermal plants.",
        ],
    ),
    (
        "Our Solution",
        [
            "Verdant Grid ingests smart-meter and inverter telemetry and produces",
            "15-minute-resolution generation forecasts per feeder.",
            "Deployed as a read-only SaaS layer alongside existing SCADA - no",
            "utility-side hardware, no control-plane integration, no NERC CIP scope.",
            "Mean absolute error of 4.1% vs 11.7% for the incumbent baseline.",
        ],
    ),
    (
        "Traction",
        [
            "$620K ARR, up from $180K twelve months ago.",
            "Four paying utility customers; two on multi-year contracts.",
            "Eleven-utility pilot pipeline via the EPRI distribution working group.",
            "Net revenue retention 128%. Zero logo churn to date.",
        ],
    ),
    (
        "Market",
        [
            "TAM: 3,000 US electric distribution utilities x $250K average annual",
            "contract value = $750M. Bottom-up from our current contract pricing.",
            "SAM: the 420 utilities with >5% distributed generation penetration,",
            "roughly $105M.",
        ],
    ),
    (
        "Business Model",
        [
            "Annual SaaS subscription, priced per feeder under management.",
            "Average contract value $155K; land-and-expand from one district to",
            "the full service territory. Gross margin 81%.",
        ],
    ),
    (
        "Team",
        [
            "Dr. Amara Oyelaran, CEO - 9 years at PJM Interconnection leading",
            "day-ahead forecasting; PhD in power systems, Georgia Tech.",
            "Ben Kaur, CTO - former staff engineer on Tesla Autobidder.",
            "Advisor: former Chief Grid Officer of a top-10 US IOU.",
        ],
    ),
    (
        "The Ask",
        [
            "Raising $4M seed. $1.6M committed, lead not yet named.",
            "Use of funds: 5 utility-sales hires (45%), forecasting model R&D (35%),",
            "SOC 2 Type II and utility security review (20%).",
            "24 months of runway to $3M ARR.",
        ],
    ),
]


def build(path: Path) -> Path:
    """Write the sample deck to ``path`` and return it."""
    page = landscape(LETTER)
    canvas = pdfcanvas.Canvas(str(path), pagesize=page)
    width, height = page
    for title, lines in SLIDES:
        canvas.setFont("Helvetica-Bold", 30)
        canvas.drawString(60, height - 100, title)
        canvas.setFont("Helvetica", 16)
        y = height - 160
        for line in lines:
            canvas.drawString(60, y, line)
            y -= 26
        canvas.showPage()
    canvas.save()
    return path


if __name__ == "__main__":
    print(build(Path(__file__).with_name("sample_deck.pdf")))
