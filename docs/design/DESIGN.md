# Design Reference

Source of truth for the frontend look. The mockup was generated in Claude Design from a written brief; the render below is **verified** against the brief (PRD §10) — paper/ink system, red-pen correction, yellow low-confidence flag, masked TINs, Caveat headlines all present.

- Live editable mockup: https://claude.ai/design/p/a5c13b14-c435-46b8-a62b-dfb9f1fcf786?file=Tax+Intake.dc.html&via=share
- [tax-intake-mockup.html](tax-intake-mockup.html) — the actual mockup markup/CSS. Open locally: `python3 -m http.server 8471` in this dir → http://localhost:8471/tax-intake-mockup.html (needs `support.js` + `ios-frame.jsx` beside it, both included).
- [mockup-full.png](mockup-full.png) — full-page render of all four screens.

**Lift the markup/CSS directly** — the frontend is plain HTML/CSS/JS, so the mockup's inner section markup is a legitimate starting point, not just a picture.

## Screens in the mockup

| Section | Screen | Key moment |
|---|---|---|
| 2a | Desktop file drop ("Add files") | Drop zone + queued files with source hints ("from Mail attachment") + Process button |
| 1a | Phone capture (iPhone frame) | "Snap the next document", queued photo thumbnails, Submit |
| 1b | Bin Review & Correction | The trust screen: wrong value struck in red pen with handwritten note ("digits swapped — fixed"), corrected value in ink blue; yellow-highlighted low-confidence field; Confirm bin |
| 1c | Checklist Dashboard | Client name in Caveat; per-doc checklist; missing K-1 row with Request link; "seeded from Ruth's 2024 file" |

## Tokens

| Token | Value | Use |
|---|---|---|
| Paper background | `#f7f5ee` | Warm base surface (grid-paper texture) |
| Ink navy | `#1c2a3a` | Primary text |
| Ink blue | `#2f5fd0` | Primary accent; corrected values; buttons |
| Highlighter yellow | `#ffd24a` | Low-confidence / needs-review flags |
| Red pen | `#c0392b` | Human corrections only (struck-through wrong value) |

Type: **Caveat** (handwritten) for personality/headlines only; system sans with `tabular-nums` for all data. Single light theme, no dark mode — committed choice.

Recurring copy element: "Processed on this Mac. Nothing is uploaded." / "On-device only" badge — keep it on every screen; it's the product thesis in the UI.
