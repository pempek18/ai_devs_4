"""
Zadanie failure (hub): skondensowane logi awarii elektrowni, limit 1500 tokenów, POST /verify.

Uruchomienie:
  python app.py                    # agent + function calling
  python app.py --max-rounds 40

Wymaga: HUB_API_KEY, OPENAI_API_KEY w .env (katalog S02E03 lub rodzic).
Opcjonalnie: tiktoken (cl100k_base) — dokładniejsze liczenie tokenów; bez niego używany jest konserwatywny przybliżony licznik.

Materiały (failure.log, historia weryfikacji, notatki ukrytej flagi) trafiają do katalogu S02E03/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI

try:
    import tiktoken
except ImportError:
    tiktoken = None

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

HUB_API_KEY = os.getenv("HUB_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "failure"
LOG_FILENAME = "failure.log"
MAX_LOG_TOKENS = 1500
ENCODING_NAME = "cl100k_base"

DEFAULT_AGENT_MODEL = os.getenv("FAILURE_AGENT_MODEL", "gpt-4o-mini")

FLG_PATTERN = re.compile(r"\{FLG:[^}]+\}")

# Stan narzędzi (mutowalny słownik — jedna instancja na run)
_state: dict[str, Any] = {
    "condensed_logs": "",
    "verify_round": 0,
    "rejection_records": [],
    "hidden_char_stream_from_messages": "",
}


def _encoder():
    if not tiktoken:
        return None
    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is None:
        return max(1, (len(text) + 3) // 3)
    return len(enc.encode(text))


def failure_log_url() -> str:
    if not HUB_API_KEY:
        raise RuntimeError("Brak HUB_API_KEY")
    return f"https://hub.ag3nts.org/data/{HUB_API_KEY}/{LOG_FILENAME}"


def extract_flag_any(obj: Any) -> str | None:
    s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    m = FLG_PATTERN.search(s)
    return m.group(0) if m else None


def _mask_apikey(key: str | None) -> str:
    if not key:
        return "(brak)"
    if len(key) <= 10:
        return "***"
    return f"{key[:4]}…{key[-4:]}"


def _append_verify_history(entry: dict) -> None:
    path = BASE_DIR / "verify_history.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _save_hidden_flag_material() -> None:
    """Ukryte podzadanie: „Tokeny złych odpowiedzi to znaki” — zapisujemy znaki z komunikatów odrzuceń i metadane."""
    path = BASE_DIR / "hidden_flag_material.json"
    payload = {
        "hint_pl": (
            "Tokeny złych odpowiedzi to znaki — traktuj znaki z pola message (i/lub długość odrzuconego payloadu) "
            "jako materiał do osobnej flagi; szukaj też {FLG:...} w surowej odpowiedzi."
        ),
        "concatenated_rejection_messages": _state["hidden_char_stream_from_messages"],
        "rejection_payload_char_lengths": [r["payload_char_len"] for r in _state["rejection_records"]],
        "rejection_records": _state["rejection_records"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def tool_download_failure_log(force: bool = False) -> dict[str, Any]:
    path = BASE_DIR / LOG_FILENAME
    if path.exists() and not force:
        return {
            "ok": True,
            "path": str(path),
            "skipped": True,
            "reason": "plik już istnieje; użyj force=true aby pobrać ponownie",
            "size_bytes": path.stat().st_size,
        }
    url = failure_log_url()
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    path.write_bytes(r.content)
    return {"ok": True, "path": str(path), "url": url, "size_bytes": path.stat().st_size}


def tool_inspect_log_file() -> dict[str, Any]:
    path = BASE_DIR / LOG_FILENAME
    if not path.exists():
        return {"ok": False, "error": "brak failure.log — najpierw download_failure_log"}
    n = 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for _ in f:
            n += 1
    size = path.stat().st_size
    head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    sample_lines = head.splitlines()[:12]
    return {
        "ok": True,
        "path": str(path),
        "line_count": n,
        "size_bytes": size,
        "sample_first_lines": sample_lines,
    }


def tool_grep_log(
    pattern: str,
    levels: list[str] | None = None,
    max_matches: int = 80,
) -> dict[str, Any]:
    path = BASE_DIR / LOG_FILENAME
    if not path.exists():
        return {"ok": False, "error": "brak failure.log"}
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return {"ok": False, "error": f"regex: {e}"}
    level_set = None
    if levels:
        level_set = {x.upper() for x in levels}
    matches: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, start=1):
            if level_set:
                mlev = re.search(r"\[(INFO|WARN|ERRO|CRIT)\]", line)
                if not mlev or mlev.group(1) not in level_set:
                    continue
            if rx.search(line):
                matches.append({"line_no": i, "text": line.rstrip("\n")})
                if len(matches) >= max_matches:
                    break
    return {"ok": True, "match_count": len(matches), "matches": matches, "truncated": len(matches) >= max_matches}


def tool_set_condensed_logs(logs: str) -> dict[str, Any]:
    logs = (logs or "").strip()
    lines = [ln for ln in logs.splitlines() if ln.strip()]
    tok = count_tokens(logs)
    issues: list[str] = []
    if tok > MAX_LOG_TOKENS:
        issues.append(f"przekroczono limit {MAX_LOG_TOKENS} tokenów (jest ~{tok})")
    for i, ln in enumerate(lines, 1):
        if not re.search(r"\[\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\]", ln):
            issues.append(f"linia {i}: brak znacznika [YYYY-MM-DD H:MM lub HH:MM]")
        if not re.search(r"\[(INFO|WARN|ERRO|CRIT)\]", ln):
            issues.append(f"linia {i}: brak poziomu [INFO|WARN|ERRO|CRIT]")
    _state["condensed_logs"] = logs
    return {
        "ok": len(issues) == 0,
        "line_count": len(lines),
        "token_estimate": tok,
        "validation_issues": issues,
        "stored": True,
    }


def tool_get_condensed_logs() -> dict[str, Any]:
    s = _state["condensed_logs"]
    return {
        "ok": True,
        "token_estimate": count_tokens(s),
        "line_count": len([x for x in s.splitlines() if x.strip()]),
        "logs": s,
    }


def tool_count_tokens(text: str) -> dict[str, Any]:
    return {"ok": True, "token_estimate": count_tokens(text), "char_len": len(text)}


def tool_submit_logs_to_hub() -> dict[str, Any]:
    logs = _state["condensed_logs"].strip()
    if not logs:
        print("[Centrala] Nie wysłano — brak skondensowanych logów (set_condensed_logs).")
        return {"ok": False, "error": "puste condensed_logs — użyj set_condensed_logs"}
    tok = count_tokens(logs)
    if tok > MAX_LOG_TOKENS:
        print(
            f"[Centrala] Nie wysłano — przekroczono limit tokenów: {tok} > {MAX_LOG_TOKENS}.",
            flush=True,
        )
        return {
            "ok": False,
            "error": f"za dużo tokenów: {tok} > {MAX_LOG_TOKENS}",
            "token_estimate": tok,
        }
    if not HUB_API_KEY:
        print("[Centrala] Nie wysłano — brak HUB_API_KEY.", flush=True)
        return {"ok": False, "error": "brak HUB_API_KEY"}

    next_round = _state["verify_round"] + 1
    n_lines = len([x for x in logs.splitlines() if x.strip()])
    print("", flush=True)
    print("=" * 72, flush=True)
    print(
        f"[Centrala] → WYSYŁKA  POST {VERIFY_URL}  |  task={TASK_NAME}  |  próba #{next_round}",
        flush=True,
    )
    print(f"  apikey: {_mask_apikey(HUB_API_KEY)}", flush=True)
    print(f"  szacunek tokenów (answer.logs): {tok}", flush=True)
    print(f"  linii zdarzeń: {n_lines}  |  znaków (logs): {len(logs)}", flush=True)
    print("-" * 72, flush=True)
    print("answer.logs (treść wysyłana do Centrali):", flush=True)
    print(logs, flush=True)
    print("-" * 72, flush=True)

    body = {
        "apikey": HUB_API_KEY,
        "task": TASK_NAME,
        "answer": {"logs": logs},
    }
    r = requests.post(VERIFY_URL, json=body, timeout=120)
    try:
        data = r.json()
    except Exception:
        data = {"_non_json": True, "http_status": r.status_code, "raw_preview": r.text[:4000]}

    print(f"[Centrala] ← ODPOWIEDŹ  HTTP {r.status_code}", flush=True)
    print("body (JSON / tekst od Centrali):", flush=True)
    if isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
    else:
        print(repr(data), flush=True)
    if not isinstance(data, dict) or data.get("_non_json"):
        print("--- surowy fragment odpowiedzi (text) ---", flush=True)
        print(r.text[:4000], flush=True)
    print("=" * 72, flush=True)
    print("", flush=True)

    _state["verify_round"] += 1
    round_id = _state["verify_round"]
    entry = {"round": round_id, "token_estimate_sent": tok, "response": data}
    _append_verify_history(entry)

    flag = extract_flag_any(data)
    if not flag:
        flag = extract_flag_any(r.text)

    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("message") or data.get("msg") or "")

    code = data.get("code") if isinstance(data, dict) else None
    successish = flag is not None or (code == 0 and "FLG" in msg)

    if not successish and msg:
        _state["hidden_char_stream_from_messages"] += msg
        _state["rejection_records"].append(
            {
                "round": round_id,
                "message": msg,
                "code": code,
                "payload_char_len": len(logs),
                "tiktoken_estimate_tokens": tok,
            }
        )
        _save_hidden_flag_material()

    out: dict[str, Any] = {
        "ok": True,
        "http_status": r.status_code,
        "hub_json": data,
        "token_estimate_sent": tok,
        "round": round_id,
    }
    if flag:
        out["flag"] = flag
        out["success"] = True
        (BASE_DIR / "flag_success.txt").write_text(flag + "\n", encoding="utf-8")
    else:
        out["success"] = False
        out["technician_hint"] = msg or json.dumps(data, ensure_ascii=False)[:1500]

    return out


def tool_save_text_file(filename: str, content: str) -> dict[str, Any]:
    name = Path(filename).name
    if not name or ".." in filename:
        return {"ok": False, "error": "nieprawidłowa nazwa"}
    path = BASE_DIR / name
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(path)}


def dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "download_failure_log":
        return tool_download_failure_log(force=bool(args.get("force")))
    if name == "inspect_log_file":
        return tool_inspect_log_file()
    if name == "grep_log":
        return tool_grep_log(
            str(args.get("pattern", "")),
            args.get("levels"),
            int(args.get("max_matches", 80)),
        )
    if name == "set_condensed_logs":
        return tool_set_condensed_logs(str(args.get("logs", "")))
    if name == "get_condensed_logs":
        return tool_get_condensed_logs()
    if name == "count_tokens":
        return tool_count_tokens(str(args.get("text", "")))
    if name == "submit_logs_to_hub":
        return tool_submit_logs_to_hub()
    if name == "save_text_file":
        return tool_save_text_file(str(args.get("filename", "")), str(args.get("content", "")))
    return {"ok": False, "error": f"nieznane narzędzie: {name}"}


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "download_failure_log",
            "description": "Pobiera failure.log z huba do folderu zadania (S02E03).",
            "parameters": {
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Jeśli true, nadpisuje istniejący plik.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_log_file",
            "description": "Rozmiar, liczba linii, próbka początku failure.log.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_log",
            "description": "Przeszukuje failure.log regexem; opcjonalnie filtr poziomów logu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Wzorzec regex (np. FIRMWARE|ECCS8|WTANK07)."},
                    "levels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Opcjonalnie: INFO, WARN, ERRO, CRIT",
                    },
                    "max_matches": {"type": "integer", "default": 80},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_condensed_logs",
            "description": (
                "Zapisuje kandydata na odpowiedź: jedna linia = jedno zdarzenie; "
                "format [YYYY-MM-DD H:MM lub HH:MM] [LEVEL] ... z identyfikatorem podzespołu."
            ),
            "parameters": {
                "type": "object",
                "properties": {"logs": {"type": "string"}},
                "required": ["logs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_condensed_logs",
            "description": "Zwraca aktualny skondensowany tekst i liczbę tokenów.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_tokens",
            "description": "Szacuje tokeny dla dowolnego tekstu (przed wysłaniem).",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_logs_to_hub",
            "description": "Wysyła skondensowane logi do POST /verify (task failure). Zwraca feedback techników lub flagę.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_text_file",
            "description": "Zapisuje notatkę / fragment do pliku w S02E03 (tylko nazwa pliku, bez ścieżek).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
]

AGENT_SYSTEM = """Jesteś agentem realizującym zadanie „failure” na hubie ag3nts.

CEL: Z pliku failure.log wybierz zdarzenia istotne dla analizy awarii elektrowni (zasilanie, chłodzenie, pompy, oprogramowanie FIRMWARE itd.).
Zbuduj JEDEN string `logs`: każda linia to jedno zdarzenie, znacznik czasu [YYYY-MM-DD H:MM] lub [YYYY-MM-DD HH:MM], poziom [INFO|WARN|ERRO|CRIT], treść ze skrótem — musi być czytelny identyfikator podzespołu (ECCS8, WTRPMP, WTANK07, PWR01, STMTURB12, WSTPOOL2, FIRMWARE, …).

LIMIT: ≤ 1500 tokenów (używaj count_tokens / set_condensed_logs przed submit).

FEEDBACK: Po submit_logs_to_hub czytaj technician_hint. Jeśli brakuje opisu urządzenia (np. FIRMWARE), dołąwz z grep_log linie ERRO/WARN/CRIT dotyczące tego tagu — zwłaszcza nietrywialne: validation queue, emergency guard, SAFETY_CHECK, cross-check hardware interface.

UKRYTE PODZADANIE (świadomość): „Tokeny złych odpowiedzi to znaki — nadaj FLAG”. Odrzucone odpowiedzi zapisują się w hidden_flag_material.json (znaki z message, długości payloadu). Szukaj też {FLG:...} w odpowiedzi huba.

WORKFLOW: download_failure_log → inspect_log_file → grep_log (krytyczne podzespoły) → set_condensed_logs → count_tokens jeśli trzeba → submit_logs_to_hub → poprawiaj aż pole flag lub sukces.

Gdy otrzymasz flagę {FLG:...}, krótko podsumuj w odpowiedzi tekstowej i nie wysyłaj ponownie bez potrzeby."""


def run_agent(max_rounds: int) -> int:
    if not HUB_API_KEY or not OPENAI_API_KEY:
        print("Ustaw HUB_API_KEY i OPENAI_API_KEY w .env", file=sys.stderr)
        return 1

    client = OpenAI(api_key=OPENAI_API_KEY)
    model = DEFAULT_AGENT_MODEL

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {
            "role": "user",
            "content": (
                "Rozpocznij zadanie failure: pobierz log, przeanalizuj awarię, "
                "przygotuj skondensowane logi ≤1500 tokenów i weryfikuj aż sukces. "
                "Pamiętaj o pełnym kontekście FIRMWARE przy odrzuceniach o tym urządzeniu."
            ),
        },
    ]

    print(
        f"Agent: {model} | katalog: {BASE_DIR}",
        flush=True,
    )
    print(
        "Uwaga: pierwsza odpowiedź modelu może trwać od kilku do kilkudziesięciu sekund "
        "(sieć + kolejka API) — nic się nie zawiesiło, czekasz na chat.completions.create().",
        flush=True,
    )

    for round_i in range(max_rounds):
        print(
            f"[runda {round_i + 1}/{max_rounds}] Czekam na odpowiedź modelu (OpenAI API)…",
            flush=True,
        )
        t0 = time.monotonic()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=AGENT_TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        dt = time.monotonic() - t0
        msg = resp.choices[0].message
        tcalls = getattr(msg, "tool_calls", None) or []
        if tcalls:
            names = ", ".join(tc.function.name for tc in tcalls)
            print(
                f"[runda {round_i + 1}] Model odpowiedział w {dt:.1f}s — wywołania narzędzi: {names}",
                flush=True,
            )
        else:
            raw = (msg.content or "").strip().replace("\n", " ")
            disp = (raw[:120] + "…") if len(raw) > 120 else (raw or "(pusto)")
            print(
                f"[runda {round_i + 1}] Model odpowiedział w {dt:.1f}s — sam tekst (bez narzędzi): {disp}",
                flush=True,
            )

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if tcalls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in tcalls
            ]
        messages.append(assistant_msg)

        if not tcalls:
            text = (msg.content or "").strip()
            print(f"[agent] {text}")
            if "FLG" in text and "{" in text:
                return 0
            messages.append(
                {
                    "role": "user",
                    "content": "Kontynuuj: użyj narzędzi (grep / set_condensed_logs / submit) aż uzyskasz flagę lub jasny komunikat sukcesu z huba.",
                },
            )
            continue

        got_flag = False
        for tc in tcalls:
            name = tc.function.name
            print(f"  → narzędzie: {name}", flush=True)
            try:
                raw = tc.function.arguments or "{}"
                args = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            result = dispatch_tool(name, args)
            result_str = json.dumps(result, ensure_ascii=False)
            if result.get("flag"):
                print(result_str)
                got_flag = True
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

        if got_flag:
            print("Sukces: znaleziono flagę w wyniku narzędzia.")
            return 0

    print("Przekroczono limit rund agenta.", file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="failure — hub, agent logów awarii")
    parser.add_argument("--max-rounds", type=int, default=36, help="maks. iteracji pętli agenta")
    args = parser.parse_args()
    return run_agent(max_rounds=args.max_rounds)


if __name__ == "__main__":
    raise SystemExit(main())
