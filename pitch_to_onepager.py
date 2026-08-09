"""CLI: turn an investor pitch deck (PDF/PPTX) into a one-page summary PDF."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from analyzer import AnalysisError, analyze_deck
from extractor import ExtractionError, extract_text
from renderer import render_onepager


def main(argv: list[str]) -> int:
    """Run extract -> analyze -> render for one deck; return a process exit code."""
    if len(argv) != 2:
        print("Usage: python pitch_to_onepager.py <deck.pdf|deck.pptx>", file=sys.stderr)
        return 2
    load_dotenv()
    deck = Path(argv[1]).expanduser()
    try:
        print("Extracting text...")
        pages = extract_text(deck)
        print("Analyzing with Claude...")
        analysis = analyze_deck(pages, source_name=deck.name)
        print("Generating PDF...")
        output = render_onepager(analysis, output_dir=deck.parent)
    except (ExtractionError, AnalysisError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
