"""Production classify + extract pipeline for KeepBook.

This is the single source of the prompts and parsing that the backend worker
runs in production. eval/run_eval.py imports THIS module (not a copy) so the
eval always measures the exact prompt path that will demo.

Two model calls per document (docs/API.md "Processing loop" permits this):
  1. classify  -> strict-JSON doc_type, mapped to the canonical enum
  2. extract   -> strict-JSON, type-specific field keys

Strict JSON, temperature 0 (enforced by model_runtime). One retry on
unparseable JSON, then the document is marked UNRECOGNIZED.
"""

import json
import re

from model_runtime import extract as model_extract

# ---------------------------------------------------------------------------
# Canonical doc types + per-type field schema.
# Field keys are aligned to eval/labels.json (the scored ground truth) and
# docs/API.md. UNRECOGNIZED never carries fields.
# ---------------------------------------------------------------------------
DOC_TYPES = ["W-2", "1099-NEC", "1099-INT", "1099-MISC", "K-1", "1098"]
UNRECOGNIZED = "UNRECOGNIZED"

FIELD_SCHEMA = {
    "W-2": ["employee_name", "ssn", "employer", "box1_wages", "box2_fed_withheld"],
    "1099-NEC": ["payer", "recipient_name", "recipient_tin", "box1_nonemployee_comp"],
    "1099-INT": ["payer", "recipient_name", "box1_interest_income"],
    "1099-MISC": ["payer", "recipient_name", "recipient_tin", "box3_other_income"],
    "K-1": ["partnership_name", "partner_name", "partnership_ein", "ordinary_income"],
    "1098": ["lender", "borrower_name", "box1_mortgage_interest"],
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def build_classify_prompt() -> str:
    types = ", ".join(f'"{t}"' for t in DOC_TYPES)
    return (
        "You are a US tax-document intake classifier. Look at this document image "
        "and decide which single IRS form it is.\n"
        "Return STRICT JSON only, no prose, no markdown:\n"
        '{"doc_type": "<TYPE>"}\n'
        f"where <TYPE> is EXACTLY one of: {types}, or "
        f'"{UNRECOGNIZED}" if it is not one of those forms (for example a '
        "receipt, a letter, or any non-tax document).\n"
        "Do not guess a tax form when the document is clearly not one — return "
        f'"{UNRECOGNIZED}" instead.'
    )


def build_extract_prompt(doc_type: str) -> str:
    fields = FIELD_SCHEMA[doc_type]
    shape = ", ".join(f'"{k}": "..."' for k in fields)
    return (
        f"You are a US tax-document data extractor. This is a {doc_type} form.\n"
        "Read the values printed on the form and return STRICT JSON only, no "
        "prose, no markdown:\n"
        f"{{{shape}}}\n"
        "Use the EXACT values printed on the form. For money fields return the "
        "number as printed (digits, commas and decimal point are fine). If a "
        'field is genuinely not present, use an empty string "".'
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_json(text):
    """Best-effort strict-JSON parse of a model response. Returns dict or None."""
    if not text:
        return None
    s = text.strip()
    # Strip ```json ... ``` / ``` ... ``` fences if present.
    fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    # Grab the outermost {...} span.
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    snippet = s[start : end + 1]
    try:
        obj = json.loads(snippet)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


_SSN_RE = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")
_MONEY_KEY_TOKENS = ("box", "wage", "income", "comp", "interest", "withheld", "mortgage")


def is_money_key(key: str) -> bool:
    k = key.lower()
    return any(tok in k for tok in _MONEY_KEY_TOKENS)


def field_format_ok(key: str, value) -> bool:
    """Deterministic format check for the low_confidence signal. No probabilities."""
    v = str(value or "").strip()
    if not v:
        return False
    k = key.lower()
    if k == "ssn":
        return bool(_SSN_RE.match(v))
    if "tin" in k or "ein" in k:
        return len(re.sub(r"\D", "", v)) == 9  # SSN- or EIN-format = 9 digits
    if is_money_key(k):
        cleaned = re.sub(r"[,$\s]", "", v)
        try:
            float(cleaned)
            return True
        except ValueError:
            return False
    return True  # names / free-text: no format to fail


def field_low_confidence(key: str, value, retried: bool = False) -> bool:
    """True from honest signals only: extraction retried, empty, or bad format."""
    return bool(retried) or not field_format_ok(key, value)


def correction_category(key: str) -> str:
    """Map a corrected field key to a stats category (docs/API.md)."""
    k = key.lower()
    if any(tok in k for tok in ("box", "wage", "income", "comp", "interest")):
        return "money"
    if k == "ssn" or "tin" in k or "ein" in k:
        return "tin_ssn"
    return "names"  # *name* / payer / employer / lender / partnership* / other strings


def normalize_doc_type(raw) -> str:
    """Map a free-form model doc_type string to the canonical enum.

    Gemma often answers 'Form W-2 Wage and Tax Statement' instead of 'W-2'.
    """
    if not raw or not isinstance(raw, str):
        return UNRECOGNIZED
    t = raw.strip().lower()
    if not t:
        return UNRECOGNIZED
    # Order matters: check the more specific 1099 variants first.
    if "1099" in t and "nec" in t:
        return "1099-NEC"
    if "1099" in t and "int" in t:
        return "1099-INT"
    if "1099" in t and "misc" in t:
        return "1099-MISC"
    if "1098" in t:
        return "1098"
    if re.search(r"\bw[\s\-]?2\b", t) or "wage and tax" in t:
        return "W-2"
    if re.search(r"\bk[\s\-]?1\b", t) or "schedule k" in t:
        return "K-1"
    if "unrecogni" in t or "unknown" in t or "not a tax" in t:
        return UNRECOGNIZED
    return UNRECOGNIZED


# ---------------------------------------------------------------------------
# Model calls with one retry
# ---------------------------------------------------------------------------
def _call_and_parse(image_b64: str, prompt: str):
    """Call the model, parse JSON, retry once on unparseable output.

    Returns (parsed_dict_or_None, raw_text_of_last_attempt, retried_bool).
    """
    raw = model_extract(image_b64, prompt)
    parsed = parse_json(raw)
    if parsed is not None:
        return parsed, raw, False
    raw2 = model_extract(image_b64, prompt)
    parsed2 = parse_json(raw2)
    return parsed2, raw2, True


def classify(image_b64: str):
    parsed, raw, retried = _call_and_parse(image_b64, build_classify_prompt())
    if parsed is None:
        return UNRECOGNIZED, raw, retried
    return normalize_doc_type(parsed.get("doc_type")), raw, retried


def extract_fields(image_b64: str, doc_type: str):
    """Return (fields_dict_or_None, raw, retried). fields keyed per FIELD_SCHEMA."""
    parsed, raw, retried = _call_and_parse(image_b64, build_extract_prompt(doc_type))
    if parsed is None:
        return None, raw, retried
    fields = {}
    for key in FIELD_SCHEMA[doc_type]:
        val = parsed.get(key, "")
        fields[key] = "" if val is None else str(val).strip()
    return fields, raw, retried


def run_pipeline(image_b64: str) -> dict:
    """Full two-step pipeline for one document image.

    Returns a runtime-neutral result:
      {
        "status": "extracted" | "unrecognized",
        "doc_type": <canonical type or "UNRECOGNIZED">,
        "fields": {key: value_str},   # plain values; {} when unrecognized
        "classify_raw": str,
        "extract_raw": str | None,
        "retried": bool,   # either model call needed a retry (low_confidence signal)
      }
    """
    doc_type, classify_raw, c_retried = classify(image_b64)
    if doc_type == UNRECOGNIZED:
        return {
            "status": "unrecognized",
            "doc_type": UNRECOGNIZED,
            "fields": {},
            "classify_raw": classify_raw,
            "extract_raw": None,
            "retried": c_retried,
        }
    fields, extract_raw, e_retried = extract_fields(image_b64, doc_type)
    if fields is None:
        # Extraction JSON unparseable after one retry -> honest UNRECOGNIZED.
        return {
            "status": "unrecognized",
            "doc_type": UNRECOGNIZED,
            "fields": {},
            "classify_raw": classify_raw,
            "extract_raw": extract_raw,
            "retried": c_retried or e_retried,
        }
    return {
        "status": "extracted",
        "doc_type": doc_type,
        "fields": fields,
        "classify_raw": classify_raw,
        "extract_raw": extract_raw,
        "retried": c_retried or e_retried,
    }
