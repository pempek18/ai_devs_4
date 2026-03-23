"""
Dodatkowe podzadanie: kolejność wysyłki J-D-I-B-A-C-G-E-H-F
(A=1. wiersz CSV … J=10. wiersz). Uruchom po zrozumieniu zadania — zużywa budżet PP na hubie.
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

# import build z app
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import (  # noqa: E402
    BASE_DIR,
    CSV_URL,
    HUB_API_KEY,
    VERIFY_URL,
    build_prompt,
    download_csv,
    extract_flag,
    hub_reset,
    hub_verify,
    load_items,
    _encoder,
)

# A=1 … J=10 (indeks w CSV 0-based: A->0, J->9)
BONUS_LETTERS = "J-D-I-B-A-C-G-E-H-F".split("-")


def letter_to_row_index(letter: str) -> int:
    letter = letter.strip().upper()
    if not ("A" <= letter <= "J"):
        raise ValueError(letter)
    return ord(letter) - ord("A")


def run_bonus_order() -> str | None:
    enc = _encoder()
    csv_path = BASE_DIR / "categorize.csv"
    log_path = BASE_DIR / "categorize_bonus_log.jsonl"

    print("Reset…")
    print(json.dumps(hub_reset(), ensure_ascii=False, indent=2))
    print("Pobieram CSV…")
    download_csv(csv_path)

    rows = load_items(csv_path)
    if len(rows) != 10:
        raise RuntimeError(f"Oczekiwano 10 wierszy, jest {len(rows)}")

    order = [letter_to_row_index(L) for L in BONUS_LETTERS]
    print("Kolejność (litery -> indeks CSV):", list(zip(BONUS_LETTERS, order)))

    flag: str | None = None
    ordered_rows = [rows[i] for i in order]

    with log_path.open("w", encoding="utf-8") as log:
        for step, row in enumerate(ordered_rows, 1):
            code = (row.get("code") or "").strip()
            desc = (row.get("description") or "").strip()
            prompt = build_prompt(code, desc, enc)
            body = hub_verify(prompt)
            log.write(
                json.dumps(
                    {"step": step, "letter": BONUS_LETTERS[step - 1], "code": code, "response": body},
                    ensure_ascii=False,
                )
                + "\n"
            )
            msg = body.get("message") or ""
            print(f"{step}/10 {code} ({BONUS_LETTERS[step - 1]}) -> {body.get('code')} {msg[:100]}")
            f = extract_flag(msg) or extract_flag(json.dumps(body, ensure_ascii=False))
            if f:
                flag = f
                print("  *** flaga:", f)

    return flag


if __name__ == "__main__":
    if not HUB_API_KEY:
        print("Brak HUB_API_KEY", file=sys.stderr)
        sys.exit(1)
    f = run_bonus_order()
    out = BASE_DIR / "categorize_bonus_result.txt"
    if f:
        out.write_text(f + "\n", encoding="utf-8")
        print(f"\nZapisano: {out} -> {f}")
    else:
        out.write_text("Brak {FLG:...} w odpowiedziach.\n", encoding="utf-8")
        print(f"\nBrak flagi w bonus_order — zobacz {BASE_DIR / 'categorize_bonus_log.jsonl'}")
