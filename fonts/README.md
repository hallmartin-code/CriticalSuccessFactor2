# Brand fonts (optional)

The PDF renderer looks for the brand faces here and silently falls back to
ReportLab's built-in Helvetica / Courier when they are absent — output is always
produced, it just uses the fallback faces.

To match the web template's typography exactly, drop these `.ttf` files into
this directory (all are open-licensed and downloadable from Google Fonts):

| File | Role in `template.FONT_ROLES` |
|---|---|
| `Sora-Bold.ttf` | `display` — company name, callout headlines, wordmark |
| `Inter-Regular.ttf` | `body` — body copy, tagline, footer |
| `Inter-SemiBold.ttf` | `body_bold` — section labels, callout labels |
| `JetBrainsMono-Regular.ttf` | `mono` — eyebrow, wordmark subline |
| `JetBrainsMono-Medium.ttf` | `mono_bold` |

Optionally add `NotoEmoji-Regular.ttf` so the ⚡ and 🎯 callout markers render on
Linux hosts (Railway included). Without it the markers are dropped and the
labels render as plain text — deliberately, so no missing-glyph boxes appear.

Only the filenames above are detected. To use different files, edit
`FONT_ROLES` in `template.py`.
