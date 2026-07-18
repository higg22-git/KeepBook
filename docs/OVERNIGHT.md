# Overnight Report — Sat Jul 18, ~2:00 AM

What happened while you slept, what's true now, and your morning checklist. Claim labels: VERIFIED = observed directly; INFERRED = concluded from evidence.

## Headline

**The product works end-to-end.** Backend + frontend integrated on the first real attempt (VERIFIED, walked in a real browser ~1:45 AM): folder/file intake → Gemma classifies + extracts (13-16s/doc two-step) → review screen with red-strike/blue-ink correction → confirm → per-client checklist inks in → stats + Stats-for-Nerds telemetry, all served from `localhost:8100`, zero external requests. State survives server restart. The receipt landed in UNRECOGNIZED, not force-fit.

Run it: `cd backend && MODEL_RUNTIME=ollama .venv/bin/python -m uvicorn main:app --port 8100` → http://localhost:8100/

## The eval saved us from ourselves (the "what broke at 2 AM" story)

The overnight provisional eval returned 26/26 doc-type but **0/94 fields for BOTH models** — and that symmetry was the tell. Root cause (VERIFIED by image inspection + a crop experiment): the generated test images were full 2200px IRS pages with the form in the top 40%; after the vision encoder downscales, field text is illegible. e4b honestly returned empty strings; e2b hallucinated box labels. Same image cropped to the form region → e4b read the fields immediately. A second bug: the W-2 SSN value was overlaid outside its box. **The models were never broken — our test set was.** Codex wrote red tests pinning both bugs; an Opus agent is fixing the generator, regenerating all 26 images, and rerunning both models through the production pipeline. Final numbers: see eval/results.json (T21/T22 in TASKS.md) — if unchecked when you read this, the rerun was still in flight.

This is writeup gold: "our eval caught our own test set lying" is the eval-driven story judges score for.

## Bugs found by the E2E + their status

1. `/intake` collapsed repeated multipart keys → only 1 of N files queued. Caught by pinning the field name in the contract; backend fixed + verified with 26-file folder intake (commit 70211d0). CLOSED.
2. `/stats/timeline` returns sparse buckets (1 instead of 24 zero-filled) and omits zero-count correction categories → nerd screen renders one giant bar + "undefined". Codex red tests + backend fix in flight. Check backend/tests/test_timeline_contract.py is green in the morning.

## Courier OS status (T41) — morning task, ~20 min

- Installed v1.63.1, fully self-hosted, **no account needed** (server localhost:9100, CourierDB takes port 8000 — backend moved to 8100 for this). Local API key auto-wired into backend/.env. Both Gemma models downloaded into it: E4B (11.5GB 8-bit) + E2B (5GB).
- Wire format: their API **accepted** the OpenAI image_url content part and began generating (INFERRED acceptance from a generation-stall 504 rather than a format 4xx). Never completed a response tonight — first attempt hit a pool/DB error (clean restart fixed that class), retry stalled mid-generation, almost certainly memory contention: Ollama's e4b was simultaneously loaded for eval reruns on a 24GB machine.
- **Morning protocol (do in this order, quiet machine):** (1) quit Chrome + heavy apps; (2) `ollama stop gemma4:e4b; ollama stop gemma4:e2b`; (3) rerun the E2B image test (script: ask Claude, it has it staged); (4) if E2B answers, run E4B same way, then the kill test + a 5-doc eval subset with `MODEL_RUNTIME=courier MODEL_NAME="gemma4:e4b"` (nickname registered, matches Ollama tag); (5) record verdict in PRD §8 either way. Only a kill-test pass permits naming Courier anywhere public. Note for honesty: Courier's E4B is 8-bit (14GB), Ollama's is Q4 (9.6GB) — not identical weights; report as "runtime + quant" comparison.

## Fleet ledger (who did what)

- Backend + adapter + eval runner: built, verified, T10-T14 + T20 checked with evidence (Opus agent). Two-step pipeline 13-16s/doc.
- Frontend: 4 screens incl. Stats for Nerds, mock + real modes, font vendored, zero external deps (Opus agent).
- Test set generators + fix: Codex red tests → Opus fix + regen + eval reruns (in flight at time of writing).
- Baseline test suites: API contract conformance + eval scoring rules (Codex, in flight).
- Docs: ownership sweep to solo-Vin, dual-runtime PRD, demo script + Q&A crib, writeup draft, distribution path, this file.

## Your morning checklist (in order)

1. Coffee. Read this file. Check TASKS.md — anything checked overnight has evidence lines.
2. Skim eval/results.json numbers → they flow into docs/WRITEUP.md bracketed slots (teammate-check rule: verify each number against the file before submitting).
3. Courier bake-off (protocol above, ~20 min) → PRD §8 verdict → writeup "model stack" line.
4. **Real phone photos** (T23): print 2-3 testset docs, photograph, label, rerun eval including them.
5. **Wi-Fi off E2E** (T40) — the on-device proof; also your best demo rehearsal.
6. Demo prep: T42 seed data + T43 fallback state (agents can do; ask Claude), then three stopwatch dry-runs (T50) with docs/DEMO-SCRIPT.md. Fill the "what broke at 2 AM" Q&A slot — the answer is the eval story above.
7. 1:00 PM freeze → writeup final + submit (T51) → repo sweep (T52) → 3:00 PM.

Merge note: `agent/vin-overnight` → main is pre-authorized and will happen (or has happened) once the in-flight lanes land green — check `git log main` vs the branch.
