# KeepBook

**On-device tax document sorter for small CPA and bookkeeping firms.** Built for the Build with Gemma: JustBuild hackathon — On-Device AI with Gemma 4 track.

Drop a folder of scanned tax documents (or snap them with a phone). Gemma 4 running locally classifies each document (W-2, 1099, K-1, 1098...), extracts key fields, groups documents into per-client bins, and maintains a per-client checklist of what's still missing. A human reviews and corrects every extraction before it's trusted. No client SSN, wage figure, or tax record ever leaves the machine.

**Why local:** a firm handling client tax data can't legally or safely paste it into a cloud AI tool. Local inference removes the third-party processor entirely.

See [PRD.md](PRD.md) for the full product spec, architecture, and evidence.

## Stack

- **Backend** — Python / FastAPI. Intake queue, classification + extraction via local Gemma 4 (`gemma4:e4b` through Ollama at `localhost:11434`), binning, checklist state.
- **Frontend** — plain HTML/CSS/JS, no build step. Capture UI + bin-review/checklist dashboard.
- **Eval** — `eval/` contains the kill-test scripts: `gen_w2.py` generates a synthetic W-2 (all data fake), `run_test.py` runs extraction against a local Ollama model.

## The kill test

Same synthetic W-2, two model sizes:

| Model | Fields correct | Failure |
|---|---|---|
| `gemma4:e2b` | 5/6 | Silently returned the wrong number for federal tax withheld — confident, clean JSON, wrong value |
| `gemma4:e4b` | 6/6 | None |

Reproduced 3x. This is why we ship `e4b` and why mandatory human review is a core feature, not a nicety.

## Run

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload  # (main.py in progress)

# eval
cd eval
python gen_w2.py
python run_test.py gemma4:e4b
```

Requires [Ollama](https://ollama.com) with `gemma4:e4b` pulled.

## Team

Keepbook — Vin Jones, Andrew.
