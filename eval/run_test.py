import base64, json, sys, time, urllib.request

img_b64 = base64.b64encode(open("w2_test.png","rb").read()).decode()
prompt = """You are a tax-document intake assistant. Look at this image and return STRICT JSON only, no prose:
{"doc_type": "...", "employee_name": "...", "ssn": "...", "employer": "...", "box1_wages": "...", "box2_fed_withheld": "..."}
Use the exact values printed on the form."""

def run(model):
    payload = json.dumps({"model": model, "prompt": prompt, "images":[img_b64], "stream": False, "options":{"temperature":0}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=payload, headers={"Content-Type":"application/json"})
    t=time.time()
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    dt=time.time()-t
    print(f"=== {model}  ({dt:.1f}s) ===")
    print(r.get("response","<none>"))
    print()

run(sys.argv[1])
