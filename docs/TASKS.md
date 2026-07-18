# Task Board — Sat Jul 18, submission 3:00 PM

Single source of truth for what's done and what's left. Humans and coding agents both work from this file.

**Rules for checking off a task (agents: this is binding):**
1. Flip `[ ]` → `[x]` ONLY after you personally ran the task's **Verify** step and observed it pass. Building it is not completing it.
2. Fill in **Evidence** with what you observed: the command you ran + decisive output line, and the commit hash if code changed. `Evidence: _none_` with a checked box is a violation.
3. If Verify fails, leave the box unchecked and append a `BLOCKED:` line explaining what you saw.
4. Never delete or reword a task's DoD to make it pass. If the DoD is wrong, add a note and flag a human.
5. Commit this file with the work it describes.

Owners: **V** = Vin, **agent** = any coding agent (with the owner reviewing).

---

## Phase 0 — Done before Saturday morning

- [x] **T01 — PRD + API contract + eval spec in repo** (V + agent)
  Evidence: commits `518b8e0`, `fa4c5f0`; PRD.md, docs/API.md, docs/EVAL.md on main.
- [x] **T02 — Labeled test set (26 images) + generators + augmenter** (agent)
  Evidence: commit `7075003`; `eval/testset/` 26 files, `eval/labels.json` cross-validated both directions.
- [x] **T03 — Model sources locked** (agent)
  Evidence: README Models section; `ollama pull gemma4:e4b` (9.6GB) / `e2b` (7.2GB) verified locally and on ollama.com registry; `gemma4:cloud` warning documented.
- [x] **T04 — Design reference in repo** (agent)
  Evidence: commit `7075003`; docs/design/ mockup HTML + full render + DESIGN.md.
- [x] **T05 — Dual-runtime design + user journey** (V + agent)
  Evidence: commits `8052649`, `5dcded1`; PRD §8, docs/API.md adapter contract, docs/USER-JOURNEY.md.
- [x] **T06 — Team registered; repo public** (V/agent)
  Evidence: Vin confirmed registration; `gh repo view higg22-git/KeepBook --json isPrivate` → `false`.

---

## Phase 1 — Backend core (owner V/agent; target ~11:00 AM)

- [x] **T10 — `backend/model_runtime.py` adapter** (V/agent)
  DoD: `extract(image_b64, prompt) -> str` implementing both shapes in docs/API.md, runtime/env-var selected; no other backend file contains a model URL.
  Verify: `MODEL_RUNTIME=ollama python -c "..."` returns non-empty model output for `eval/w2_test.png`; `grep -rn "11434\|api/generate\|chat/completions" backend/ --include="*.py" | grep -v model_runtime.py` returns nothing.
  Evidence: `MODEL_RUNTIME=ollama .venv/bin/python -c "model_runtime.extract(w2_test)"` → JSON `{"doc_type":"W-2","employee_name":"Marcus D. Whitfield","box2_fed_withheld":"9,183.44"}`. Scoped grep `grep -rnE "11434|api/generate|chat/completions|COURIER_BASE_URL" backend/ --include=*.py --exclude-dir=.venv | grep -v model_runtime.py` → CLEAN (only backend source is model_runtime/pipeline/main; venv is gitignored, ignore its lib hits). Commit `be0662d`.

- [x] **T11 — FastAPI endpoints per docs/API.md** (V/agent)
  DoD: `/intake`, `/queue`, `/documents`, `/documents/{id}`, `/documents/{id}/image`, `/documents/{id}/confirm`, `/clients`, `/stats` all return contract-shaped JSON; `state.json` persisted on every mutation.
  Verify: curl sequence — POST a testset image to `/intake` → doc reaches `status: extracted` in `/documents` → POST `/confirm` with one changed field → doc `confirmed`, field carries `corrected: true` + `original_value`, client checklist updates; kill and restart server → state intact.
  Evidence: uvicorn :8100 — `POST /intake -F file=@eval/w2_test.png` → `{"queued":["doc_001"]}`; polled `/queue` to `done:1`; `/documents/doc_001` → `status:"extracted"` all 5 W-2 fields (box2 `9,183.44`), `received_at` set; `POST /documents/doc_001/confirm` with box2→`"8,000.00"` → `box2_fed_withheld:{"value":"8,000.00","corrected":true,"original_value":"9,183.44"}`, `status:"confirmed"`, `/clients` → `received_docs:["W-2"]`; `pkill uvicorn` then restart → `/documents/doc_001` still `confirmed` with correction + client intact, `/queue` `done:1`. `/image` → `http=200 image/png`. Commit `be0662d`.

- [x] **T12 — Classification + extraction prompts** (V/agent)
  DoD: strict-JSON prompts at temperature 0; unparseable JSON → one retry → `UNRECOGNIZED`; per-type field keys match docs/API.md.
  Verify: `w2_clean_01.png` through the real pipeline → `doc_type: "W-2"` with all five W-2 field keys present.
  Evidence: intake `w2_clean_01.png` → `status:"extracted"`, `doc_type:"W-2"`, field keys `['employee_name','ssn','employer','box1_wages','box2_fed_withheld']` (all five). NOTE: field VALUES came back empty on this image — the known testset generator illegibility bug, NOT a prompt bug (same pipeline on `eval/w2_test.png` returns 6/6 correct incl. box2 `9,183.44`); DoD is type + keys, both correct. Empty values are honestly flagged `low_confidence`. Commit `be0662d`.

- [x] **T13 — UNRECOGNIZED path** (V/agent)
  DoD: non-tax documents are never force-fit; they land in review queue for manual classification, and manual classify → normal confirm flow.
  Verify: `receipt_01.png` through the pipeline → `status: unrecognized`; then POST `/confirm` with a manual `doc_type` + `client_id` succeeds.
  Evidence: intake `receipt_01.png` → `status:"unrecognized"`, `doc_type:"UNRECOGNIZED"`, `fields:{}` (not force-fit); then `POST /confirm {"client_id":"client_whitfield_m","doc_type":"1099-MISC","fields":{"payer":"Acme Corp"}}` → `status:"confirmed"`, `doc_type:"1099-MISC"`, `/clients received_docs` gained `1099-MISC`. Commit `be0662d`.

- [x] **T14 — Event log + /stats/timeline (STRETCH — only after T10-T13 green)** (V/agent)
  DoD: backend appends extraction/confirm events to `backend/events.jsonl` per docs/API.md "Event log"; `GET /stats/timeline?hours=24` aggregates buckets + totals incl. corrections_by_category and first_try_type_acc.
  Verify: process 2 docs, correct 1 field, confirm both → timeline totals show 2 docs, correct correction count, category attribution matches the corrected key.
  Evidence: T10-T13 green first. `events.jsonl` carries `extracted`/`unrecognized`/`confirmed` rows in contract shape (incl. `fields_low_confidence` per `acbe402`). Ran 3 docs / 2 confirms / 1 field correction → `GET /stats/timeline?hours=24` totals: `docs_processed:3, fields_extracted:10, fields_low_confidence:5, fields_corrected:2, correction_rate:0.2, first_try_type_acc:0.5, median_latency_s:15.73, corrections_by_category:{"money":1,"names":1,"doc_type":1}` — attribution matches corrected keys (box2_fed_withheld→money, payer→names, receipt→1099-MISC type change→doc_type). Separately: w2_clean_01 (empty fields) → `fields_low_confidence:5` in its extracted event; w2_test (valid) → `0`. Commits `be0662d` + `966ba5f`.
  ADDENDUM (contract fix + observability): live E2E found two timeline contract violations, pinned red by `backend/tests/test_timeline_contract.py` (`04d0c52`) — sparse buckets and zero-count categories omitted. Fixed: exactly `hours` zero-filled buckets oldest-first ending current hour; `corrections_by_category` always carries all four keys. Both tests green (`pytest backend/tests/test_timeline_contract.py` → 2 passed), plus `test_api_contract.py` 4 passed and `eval/test_scoring.py` 8 passed, verified in a clean worktree at `04d0c52` + this change (the shared tree's in-flight re-ask/cascade `pipeline.py` edits break the api suite's fake-adapter signature — that lane's to reconcile). Bundled: per-doc raw model I/O capture → `backend/raws/{doc_id}.json` (gitignored) referenced as `raw_ref` in the extracted event, and `p95_latency_s` in timeline totals; real-model check: w2_test → raws file with 2 calls (exact classify+extract prompts + raw responses), event `raw_ref:"raws/doc_001.json"`, timeline `buckets=24` zero-filled, `p95_latency_s:32.0`, categories all present.

## Phase 2 — Eval (owner V/agent; target ~12:30 PM)

- [x] **T20 — `eval/run_eval.py` per docs/EVAL.md** (V/agent)
  DoD: imports the backend adapter + production prompts (not copies); implements the scoring rules (money normalization, casefold strings, silent-wrong-value counter); emits summary + `eval/results.json`.
  Verify: run against any 3 testset images with labels; hand-check one scored field against labels.json.
  Evidence: `run_eval.py --model gemma4:e4b --labels labels.json --docs ./testset/ --images w2_clean_01.png,1099int_clean_01.png,receipt_01.png` → completed, `doc-type accuracy: 3/3 (100.0%)`, `field accuracy: 0/8 (0.0%)`, `silent wrong values: 0`, `median latency: 13.1s`, wrote results.json. `run_eval.py` imports `backend/pipeline.run_pipeline` (not a copy). Hand-check: w2_clean_01 `box1_wages` expected `"101775.13"` (== labels.json) vs predicted `""` → verdict `missing` (empty counts as miss, not silent-wrong — correct). Field 0/8 is the known testset illegibility bug, not a scorer bug. Commit `a7cb7d2`. (Full 26-doc runs = T21/T22, left for orchestrator.)

- [x] **T21 — Full e4b run over the 26-doc test set** (V/agent)
  DoD: `eval/results.json` committed with doc-type accuracy, field accuracy, silent-wrong count, median latency.
  Verify: `python run_eval.py --model gemma4:e4b ...` completes all 26; results.json parses; numbers transcribed nowhere they don't match.
  Evidence: `backend/.venv/bin/python eval/run_eval.py --model gemma4:e4b --labels eval/labels.json --docs eval/testset/` on the FIXED testset (commit `e376cc8` content-crop + W-2 SSN placement, regenerated in `39b1aa8`) → all 26 scored, `doc-type accuracy: 26/26 (100%)`, `field accuracy: 41/94 (43.6%)`, `silent wrong values: 23`, `median latency: 17.23s`. results.json parses (json.load, `docs_scored: 26`). Split: clean 29/47 fields, photo 12/47. Misses are genuine vision errors (e.g. `Coppell Bank` for `Copperline Bank`), not the pre-fix all-empty artifact. Commit `30a66b7`.

- [ ] **T22 — e2b comparison run** (V/agent)
  DoD: same set through `gemma4:e2b`; comparison table committed (extends the kill test from n=1 to n=26).
  Verify: results file for e2b exists; silent-wrong count for each model recorded.
  Evidence: _none_

- [ ] **T23 — Real phone-photo bucket** (V)
  DoD: ≥2 printed-then-photographed docs added to testset with labels; eval includes them.
  Verify: new files in labels.json; rerun eval covers them.
  Evidence: _none_

## Phase 3 — Frontend (owner V; target ~12:30 PM)

- [ ] **T30 — Capture/Submit screen** (V)
  DoD: drag-and-drop posts files to `/intake`; queue progress polls `/queue`; paper/ink tokens per docs/design/DESIGN.md; "Processed on this Mac. Nothing is uploaded." visible.
  Verify: drop 2 testset images in a browser → both appear in `/documents` and progress shows.
  Evidence: Frontend half verified in mock mode (`frontend/`, branch `agent/vin-overnight`) — dropped 2 files onto the zone → "Queued · 2 files" list → Process → `/queue` polling rendered "0 of 2" with progress bar → "2 documents ready", and both materialized into Review (doc_007 `1099-INT`, doc_008 `UNRECOGNIZED`, each with preview image). Paper/ink tokens + "Processed on this Mac. Nothing is uploaded." present; page load fires ZERO external network requests (all `localhost` + `blob:`, Caveat font from local `assets/caveat.woff2`). Awaiting backend for full DoD (real `/intake` round-trip). LIVE-STACK ADDENDUM (orchestrator ~01:40): real /intake verified via curl multipart (2 files, repeated `file` key) → processed → rendered in Review with images; box stays unchecked only because the literal browser drag-and-drop gesture on the real stack hasn't been performed — covered by T40's morning Wi-Fi-off run.

- [x] **T31 — Bin Review & Correction screen** (V)
  DoD: source image beside extracted fields; editing a field and confirming POSTs `/confirm`; corrected value renders red-strike original + ink-blue correction; survives reload.
  Verify: correct one field in the browser → reload → correction still displayed; `/stats` correction count incremented.
  Evidence (full DoD, live stack, orchestrator ~01:45): real browser against running backend on :8100 — selected Ruth Okafor, edited box2_fed_withheld on doc_001 (real e4b extraction of w2_test.png), Confirm → GET /documents/doc_001 showed `{"value":"9,999.99","corrected":true,"original_value":"9,183.44"}`, status confirmed; /stats went to fields_corrected:1, correction_rate:0.2; state persisted server-side (state.json). Mock-mode render spec evidence below stands.
  Prior evidence: Frontend half verified in mock mode (`frontend/`, branch `agent/vin-overnight`) — source image renders beside editable fields; corrected Marcus Whitfield W-2 Box 2 `70,110.00`→`9,183.44` in the browser, rendered original struck in red pen (computed `rgb(192,57,43)` + `line-through`) beside corrected value in ink blue (`rgb(47,95,208)`, weight 700) with a Caveat "corrected" note; the correction persists across reload (localStorage in mock; real backend `state.json` for full DoD) and `/stats` corrected-count went 1→2. UNRECOGNIZED receipt shows the manual `doc_type` + client pickers, empty confirm is blocked ("Pick a document type first"), and classifying it as K-1 for Chen flowed to the checklist. Awaiting backend for full DoD (real `/confirm` + server-side reload persistence).

- [x] **T32 — Checklist Dashboard** (V)
  DoD: clients from `/clients`; confirming a doc checks its checklist item with the ink animation; missing items obvious; stats line shows fields extracted / corrected.
  Verify: confirm a W-2 for a client expecting one → item inks in; client missing a K-1 shows it missing.
  Evidence (full DoD, live stack, orchestrator ~01:50): real browser, live /clients — confirmed W-2 for Ruth Okafor (expected [W-2]) → row inked "all in ✓" with "Received Jul 18 · 1 correction"; Chen Partnership showed K-1 + 1098 MISSING in highlighter; Marcus Whitfield showed W-2 + 1099-INT MISSING; stats line rendered live 5 extracted / 1 corrected / 20.0%. Screenshot in transcript.
  Prior evidence: Frontend half verified in mock mode (`frontend/`, branch `agent/vin-overnight`) — three journey clients render with correct gaps: Ruth Okafor 2/3 then 3/3 ("all in ✓") after confirming her 1099-INT, with the ink-in animation classes (`row-settle` + `ink-draw` check path) applied to ONLY the newly-confirmed row; Marcus Whitfield shows 1099-INT MISSING in highlighter (#ffd24a) with a Request link; Chen Partnership shows K-1 + 1098 MISSING. Stats line renders from `/stats` (fields extracted / corrected / correction rate, e.g. 26 / 2 / 7.7%). Awaiting backend for full DoD (live `/clients` + `/stats`).

- [ ] **T33 — "Stats for Nerds" screen (STRETCH — only after T30-T32 green)** (V/agent)
  DoD: fourth view rendering `GET /stats/timeline?hours=24` per mockup screen 3 (docs/design/tax-intake-mockup.html): headline tiles (docs processed, first-try classification %, correction rate, median latency), docs-per-hour bars, corrections-by-category list, the "Past 24 hours only... Nothing leaves this Mac" line, "the red-pen rate is the number to watch" tagline.
  Verify: with seeded events, all tiles render real numbers; mock mode works without backend.
  Evidence: Frontend half verified in mock mode (`frontend/`, branch `agent/vin-overnight`) — fourth "Nerd stats" view renders `mock/timeline.json` (exact `GET /stats/timeline?hours=24` shape): tiles 31 docs / 94% first-try / 4.2% correction rate / 19.2s median; 24 CSS bars (last 3 ink-blue, "now ←" + axis labels); extraction block 214 / 17 · 7.9% flagged (highlighter) / corrected in red; corrections-by-category 4/2/2/1; both required lines present ("Past 24 hours only — stats reset as they age out. Nothing leaves this Mac." + Caveat "the red-pen rate is the number to watch"). Mock overlays live deltas the way the backend will recompute from events.jsonl: demo-time corrections ticked corrected 9→10 (rate tile 4.2%→4.7%), money 4→5, doc_type reclass 1→2, flagged count correctly did NOT shrink. Zero external requests, console clean. Awaiting backend T14 (`events.jsonl` + real `/stats/timeline`) for full DoD.

## Phase 4 — Integration + runtime (both; target ~1:00 PM = FREEZE)

- [ ] **T40 — E2E on the demo Mac, fully local** (V/agent)
  DoD: folder-drop → classify → bin → review/correct → checklist, all on the M4 with default env (no Tailscale dependency).
  Verify: run the full flow once **with Wi-Fi off** — this is also the demo's on-device proof.
  Evidence: _none_

- [ ] **T41 — Courier OS verification (env flip)** (V)
  DoD: install + auth; kill test via `MODEL_RUNTIME=courier`; result recorded in PRD §8 EITHER WAY. Only a pass permits naming Courier in writeup/demo.
  Verify: `run_test.py` equivalent through the courier adapter path returns 6/6 on the W-2, or the failure is documented.
  Evidence: _none_

- [x] **T42 — Demo seed data** (agent)
  DoD: `state.json` with 3 clients matching docs/USER-JOURNEY.md — Ruth Okafor (complete after one confirm), Marcus Whitfield (missing 1099-INT), Chen partnership (missing K-1 + 1098).
  Verify: dashboard renders the three rows with exactly those gaps.
  Evidence: `backend/state.demo.json` (5 docs, images copied from `eval/testset/` + `eval/w2_test.png`, real labels.json field values). `./scripts/demo_state.sh seed` against the RUNNING :8100 server → `GET /clients` → `client_ruth_okafor` expected `["W-2","1099-INT","1098"]` received `["1099-INT","1098"]` (doc_003 W-2 sits `status:"extracted"` — the confirm moment); `client_marcus_whitfield` expected `["W-2","1099-INT"]` received `["W-2"]` (1099-INT has no document at all); `client_chen_partnership` expected `["K-1","1098"]` received `[]` (zero docs). `GET /documents/doc_003` → W-2 extracted, all 5 fields filled, awaiting review. `GET /documents/doc_005` → `UNRECOGNIZED`, `fields:{}`, `client_id:null` (receipt awaiting manual classification). `doc_004` (Marcus's confirmed W-2, `eval/w2_test.png`) carries the correction already recorded: `box2_fed_withheld:{"value":"9,183.44","corrected":true,"original_value":"70,110.00"}` — the exact kill-test number from docs/API.md and PRD. Image serving: `doc_001`..`doc_005` all `200 image/png`. `GET /queue` → `{"pending":0,"processing":null,"done":5}` (nothing stuck). Seed left loaded per instructions. Commit `<PENDING>`.

- [x] **T43 — Pre-processed fallback session** (agent)
  DoD: a fully-processed backup `state.json` + one-command restore, for use if live processing stalls on stage.
  Verify: restore command swaps state and dashboard renders instantly.
  Evidence: `backend/state.fallback.json` (adds doc_006 Marcus 1099-INT confirmed + doc_007 Chen K-1 confirmed, plus doc_003 flips to `confirmed`) + `scripts/demo_state.sh` (portable bash 3.2, no assoc arrays — stages images from `eval/` into `backend/uploads/` since `uploads/` is gitignored, copies the chosen state file to `backend/state.json`, then kill+restarts uvicorn on :8100 because `main.py` only loads state at the FastAPI startup event, no hot-reload path). `./scripts/demo_state.sh fallback` against the running server → `GET /clients`: Ruth `received_docs:["1099-INT","1098","W-2"]` (3/3 complete), Marcus `["W-2","1099-INT"]` (2/2 complete), Chen `["K-1"]` (1/2, mostly complete — 1098 still open, matches DoD "mostly complete" not staged as suspiciously perfect). `doc_003` status flips `extracted`→`confirmed`. `doc_006`/`doc_007` images `200 image/png`. Then `./scripts/demo_state.sh seed` run again → dashboard flips back to the T42 gaps (verified above) and left loaded as the final state. Commit `<PENDING>`.

- [ ] **T44 — FREEZE at 1:00 PM** (all)
  DoD: no feature code after 1:00 PM; only demo prep, writeup, and fixes for demo-blocking bugs.
  Evidence: _none_

## Phase 5 — Demo + submission (hard deadlines)

- [ ] **T50 — Three stopwatch dry-runs** (V/agent; by 2:00 PM)
  DoD: three timed runs of the docs/USER-JOURNEY.md demo script, each ≤ 3:00; live path and fallback path each rehearsed at least once.
  Verify: times written here.
  Evidence: _none_

- [ ] **T51 — Kaggle Writeup submitted** (V; **by 3:00 PM — no writeup = ineligible**)
  DoD: product story, model stack (verified runtime only — see T41), GitHub link, eval numbers that match `eval/results.json` exactly.
  Verify: submission confirmation visible; a teammate cross-checks numbers against results.json.
  Evidence: _none_

- [ ] **T52 — Repo final sweep** (agent; by 2:45 PM)
  DoD: README numbers match results.json; no secrets (`grep -ri "api[_-]key\|secret\|token" --exclude-dir=.git` clean or false-positives only); repo confirmed public; fresh-clone run instructions actually work.
  Verify: run the greps + `gh repo view --json isPrivate`; fresh clone in /tmp follows README successfully.
  Evidence: _none_

- [ ] **T53 — Demo logistics** (V/agent; by 2:55 PM)
  DoD: model warmed (one inference completed), demo docs staged, backend + frontend running, screen/adapter tested, fallback restore command in a ready terminal.
  Verify: one warm inference logged < 5 min before demo slot.
  Evidence: _none_
