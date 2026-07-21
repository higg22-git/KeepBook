# Dad Demo — KeepBook Phase 2 (visible autonomy)

Audience: one CPA who runs the real workflow. Goal is NOT applause — it's the
anomaly-flag gate check (ROADMAP Tier A #2) plus honest field feedback. He is a
primary source for questions no published data answers (docs/AI-NATIVE-FIRM.md §7).

The hackathon judge script (docs/DEMO-SCRIPT.md) is the historical record; this
one is slower, conversational, and ends in questions.

## Setup (before he's in the room)

```bash
# 1. Ollama up + model warm
ollama serve &            # if not already running
curl -s localhost:11434/api/generate -d '{"model":"gemma4:e4b","prompt":"READY","stream":false,"keep_alive":"45m"}'

# 2. Inbox folder for the AirDrop beat (pick any folder you'll AirDrop/save into)
export KEEPBOOK_INBOX="$HOME/Downloads/KeepBook Inbox"

# 3. Seed + start (KEEPBOOK_INBOX must be exported in THIS shell — the script
#    inherits it into uvicorn)
./scripts/demo_state.sh seed

# 4. Sanity: curl -s localhost:8100/health  → git_sha current, "inbox" shows the path
```

Stage in a Finder folder: 2-3 testset images + `chen_packet.pdf` style multi-page
PDF (build: `python -c "from PIL import Image; a=Image.open('eval/testset/k1_clean_01.png').convert('RGB'); a.save('/tmp/packet.pdf', save_all=True, append_images=[Image.open('eval/testset/1098_clean_02.png').convert('RGB')])"`).
Keep a copy of one already-seeded image (eval/w2_test.png) for the duplicate beat.

## The 6 beats (~8-10 min, let him drive after beat 2)

1. **The problem is his** (30s). Dashboard: three clients, missing-doc checklists,
   MISSING chips. "This is your February — who still owes you what."
2. **Drop the folder** (2 min). Drag the staged folder onto Capture — include the
   PDF. Narrate the queue honestly (~20-30s/doc on this Mac, nothing leaves it).
   PDF becomes one document per page with page badges (p. 1, p. 2).
3. **The red pen** (2 min). Open a doc in Review: image beside fields, identity
   gate ("this document belongs to..."), fix a field → red strike + ink
   correction. Line to say: "the model proposes, you confirm — the IRS said in
   June this is the only legal way to use AI output anyway."
4. **It notices things** (2 min). Double-drop the W-2 copy → "Possible duplicate"
   with side-by-side, Keep/Discard — his call, one click. Then AirDrop (or
   Finder-copy) an image into the inbox folder — KeepBook ingests it unprompted,
   "from inbox folder" chip. DO NOT claim it catches a scan-vs-phone-photo pair
   (it doesn't — dHash limit, documented).
5. **It drafts the chase** (1 min). Client card → Draft reminder → model-written
   note listing exactly the missing docs → Copy. "It never sends. You send."
6. **The close** (1 min). Confirm a doc → checklist item inks in with the new-entry
   dot; Export CSV ("imports into anything"); Nerd stats → the correction rate.
   "The number I watch is the red-pen rate — that's whether the gate is alive."

Fallback if live processing stalls: `./scripts/demo_state.sh fallback` (staged
terminal), same as demo day.

## The questions (the actual point — write his answers down)

1. How many IRS/state notices does the firm handle per season? (no published
   benchmark exists — his number is data)
2. What share of document requests need 2+ nags? What finally makes clients send?
3. Of an hour on a 1040, how much is typing numbers from paper into software?
4. **The gate question:** "If it flagged 'this K-1's TIN doesn't match the 1099
   from the same client', would you trust that flag? Want it?" — a clear yes =
   green light for ROADMAP Tier A #2 (anomaly flags); a shrug = stay stopped.
5. Would he point a scanner/phone at a watched folder, or is drag-and-drop the
   real motion?
6. Bank statements: would he run KeepBook's extraction against Tanya-style
   hand-booked ground truth? (Tier B #7 benchmark)
