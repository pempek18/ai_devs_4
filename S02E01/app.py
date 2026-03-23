"""
Zadanie categorize (hub): klasyfikacja towarów DNG/NEU przy limicie 100 tokenów na prompt.

Hub wymaga literalnego kodu produktu (i + cyfry) w treści promptu — nie wystarczy sam szablon {id}.
Statyczna część na początku (lepszy cache), zmienne dane na końcu.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    import tiktoken
except ImportError:
    tiktoken = None

BASE_DIR = Path(__file__).resolve().parent
# .env z katalogu repo lub S02E01
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

HUB_API_KEY = os.getenv("HUB_API_KEY")
VERIFY_URL = "https://hub.ag3nts.org/verify"
CSV_URL = f"https://hub.ag3nts.org/data/{HUB_API_KEY}/categorize.csv"

MAX_PROMPT_TOKENS = 100
ENCODING_NAME = "cl100k_base"

# Zwięzła instrukcja (angielski — mniej tokenów). Reaktor/kasety zawsze NEU.
STATIC_PREFIX = (
    "Output only DNG or NEU. DNG: firearm, gun, pistol, magazine, flamethrower, military weapon. "
    "NEU: else. Reactor fuel cassette, uranium, nuclear fuel, depleted core, reactor: NEU.\n"
)


def _encoder():
    if not tiktoken:
        return None
    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str, enc) -> int:
    if enc is None:
        return max(1, len(text) // 4)
    return len(enc.encode(text))


def build_prompt(code: str, description: str, enc) -> str:
    """Pełny prompt ≤ MAX_PROMPT_TOKENS; kod iXXXX musi być w treści."""
    desc = (description or "").strip()
    body = f"{code}: {desc}"
    full = STATIC_PREFIX + body
    while count_tokens(full, enc) > MAX_PROMPT_TOKENS and len(desc) > 24:
        desc = desc[: len(desc) - 32].rstrip() + "…"
        body = f"{code}: {desc}"
        full = STATIC_PREFIX + body
    return full


def hub_reset() -> dict:
    return hub_verify("reset")


def hub_verify(prompt: str) -> dict:
    if not HUB_API_KEY:
        raise RuntimeError("Brak HUB_API_KEY w .env")
    r = requests.post(
        VERIFY_URL,
        json={"apikey": HUB_API_KEY, "task": "categorize", "answer": {"prompt": prompt}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def download_csv(path: Path) -> None:
    r = requests.get(CSV_URL, timeout=60)
    r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")


def load_items(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def extract_flag(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"\{FLG:[^}]+\}", text)
    return m.group(0) if m else None


def run_cycle(enc) -> str | None:
    csv_path = BASE_DIR / "categorize.csv"
    log_path = BASE_DIR / "categorize_log.jsonl"

    print("Reset budżetu…")
    reset_body = hub_reset()
    print(json.dumps(reset_body, ensure_ascii=False, indent=2))

    print(f"Pobieram {csv_path.name}…")
    download_csv(csv_path)

    rows = load_items(csv_path)
    if not rows:
        raise RuntimeError("Pusty CSV")

    flag: str | None = None

    with log_path.open("w", encoding="utf-8") as log:
        for row in rows:
            code = (row.get("code") or "").strip()
            desc = (row.get("description") or "").strip()
            if not re.match(r"^i\d+$", code):
                raise ValueError(f"Nieoczekiwany format kodu: {code!r}")

            prompt = build_prompt(code, desc, enc)
            tok_n = count_tokens(prompt, enc)
            if tok_n > MAX_PROMPT_TOKENS:
                print(f"UWAGA {code}: {tok_n} tokenów > {MAX_PROMPT_TOKENS}", file=sys.stderr)

            rec = {"code": code, "tokens": tok_n, "prompt_len": len(prompt)}
            body = hub_verify(prompt)
            rec["response"] = body
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")

            msg = body.get("message") or ""
            dbg = body.get("debug") or {}
            print(f"{code} → code={body.get('code')} {msg[:80]}")

            f = extract_flag(msg) or extract_flag(json.dumps(body, ensure_ascii=False))
            if f:
                flag = f

            classified = dbg.get("classified_items")
            required = dbg.get("required_items")
            if classified is not None and required is not None:
                print(f"   postęp: {classified}/{required}  balance={body.get('balance')}")

        if not flag:
            # czasem flaga tylko w ostatniej odpowiedzi jako osobne pole
            last = body
            flag = extract_flag(json.dumps(last, ensure_ascii=False))

    return flag


def main() -> None:
    enc = _encoder()
    if enc is None:
        print("Instalacja: pip install tiktoken (zalecane do liczenia tokenów).", file=sys.stderr)

    try:
        flag = run_cycle(enc)
    except requests.HTTPError as e:
        print(e, file=sys.stderr)
        if e.response is not None:
            print(e.response.text, file=sys.stderr)
        sys.exit(1)

    out_path = BASE_DIR / "categorize_result.txt"
    if flag:
        out_path.write_text(flag + "\n", encoding="utf-8")
        print(f"\nFlaga zapisana w {out_path.name}: {flag}")
    else:
        out_path.write_text(
            "Brak flagi w odpowiedziach — sprawdź categorize_log.jsonl i ewentualnie popraw STATIC_PREFIX w app.py.\n",
            encoding="utf-8",
        )
        print(f"\nBrak flagi. Szczegóły: categorize_log.jsonl, podsumowanie: {out_path}")


if __name__ == "__main__":
    main()
