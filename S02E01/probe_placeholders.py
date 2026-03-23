"""Probe categorize prompt validation — run manually."""
import os
import re
import requests
from dotenv import load_dotenv

load_dotenv("c:/git_workspace/ai_devs_4/.env")
key = os.getenv("HUB_API_KEY")

# brute single chars and words
candidates = []
for w in ["id", "ID", "Id", "code", "CODE", "sku", "uuid", "key", "nr", "idx", "index", "ident", "identyfikator"]:
    candidates.append("{" + w + "}")
    candidates.append("{{" + w + "}}")

# str.format style
candidates += ["{0}", "{1}", "%s", "%(id)s", "$1", "$2"]

# literal product code pattern (maybe validator wants regex i\d+)
candidates += ["i1234", "i0000", "x{i}"]

seen = set()
for p in candidates:
    if p in seen:
        continue
    seen.add(p)
    r = requests.post(
        "https://hub.ag3nts.org/verify",
        json={"apikey": key, "task": "categorize", "answer": {"prompt": f"X {p} Y {{description}}"}},
        timeout=60,
    )
    j = r.json()
    if j.get("code") != -940:
        print("HIT", repr(p), j)
        break
else:
    print("No hit in first batch; sample:")
    r = requests.post(
        "https://hub.ag3nts.org/verify",
        json={"apikey": key, "task": "categorize", "answer": {"prompt": "{id} {description}"}},
        timeout=60,
    )
    print(r.json())
