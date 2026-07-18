# Classify-only eval bucket (T65) — UNVERIFIED

Classify-only doc types (`extract: false`) are classified + human-confirmed with
zero field extraction. They are scored on **doc_type only**; `run_eval.py` skips
field scoring for any label carrying `"classify_only": true`, so these docs can
never register a silent-wrong.

## Samples

Rendered offline by `eval/gen_classify_only.py` (pure PIL, deterministic) into
`eval/testset/`, with `classify_only: true` label entries merged into
`eval/labels.json`:

| file | doc_type |
|---|---|
| `charitable_receipt_01.png` | `charitable receipt` |
| `w9_01.png` | `W-9` |
| `brokerage_stmt_01.png` | `brokerage statement` |

## Status: UNVERIFIED (model run deferred)

The images render offline, but the **model has not been run** against this bucket
in this lane (no Ollama/GPU here). The classification-accuracy numbers on these
samples — and the check that the larger enum did not erode UNRECOGNIZED
discipline on the existing `receipt_01`/`letter_01` negatives — require a GPU
eval run, which is **deferred to the orchestrator**.

To run it once a model host is available:

```
cd eval
python run_eval.py --model gemma4:e4b            # scores the whole labeled set,
                                                 # incl. the 3 classify-only docs
```

Expected: each classify-only doc's `doc_type` matches its label; `field_total`
for these docs is 0 (fields skipped); `classify_only_docs` = 3 in the summary.
Until that run lands, treat classify accuracy on these types as UNVERIFIED.
