"""
Zadanie railway: aktywacja trasy X-01 przez API bez dokumentacji.
- Rozpoczynamy od akcji help (samo-dokumentujące API).
- Obsługa 503 (retry z backoff) i limitów zapytań (nagłówki HTTP).
- Cel: flaga w formacie {FLG:...} w odpowiedzi.
- Bonus: "Nie będę czekać 4 minuty!" — zmieścić się w < 4 min (mniej wywołań = mniej czekania).
"""
import os
import sys
import re
import time
import json
import requests
from dotenv import load_dotenv

load_dotenv()

HUB_API_KEY = os.getenv("HUB_API_KEY")
VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "railway"
DEADLINE_SEC = 4 * 60  # 4 minuty — bonus

# Backoff przy 503
INITIAL_BACKOFF = 2
MAX_BACKOFF = 60
BACKOFF_MULTIPLIER = 2


def log(msg: str) -> None:
    elapsed = time.perf_counter() - start_time
    print(f"[{elapsed:.1f}s] {msg}")


def get_retry_after_sec(response: requests.Response) -> float | None:
    """Zwraca liczbę sekund do odczekania (z Retry-After lub innego nagłówka)."""
    ra = response.headers.get("Retry-After")
    if ra is not None:
        try:
            return float(ra)
        except ValueError:
            pass
    # Często jest X-RateLimit-Reset (timestamp) lub podobny
    for name in ("X-RateLimit-Reset", "X-Ratelimit-Reset", "RateLimit-Reset"):
        v = response.headers.get(name)
        if v is not None:
            try:
                reset_ts = float(v)
                return max(0, reset_ts - time.time())
            except (ValueError, TypeError):
                pass
    return None


def wait_for_limit(response: requests.Response) -> None:
    """Czeka do resetu limitu, jeśli nagłówki to wskazują."""
    sec = get_retry_after_sec(response)
    if sec is not None and sec > 0:
        log(f"Limit zapytań — czekam {sec:.0f}s (Retry-After / reset)...")
        time.sleep(min(sec, 120))  # max 2 min czekania na raz


def api_call(answer: dict, deadline_sec: float | None = None) -> tuple[dict | str, requests.Response]:
    """
    Wysyła jedno żądanie do /verify. Retry przy 503 z backoffem.
    Respektuje Retry-After po każdej odpowiedzi.
    Zwraca (body jako dict lub string, response).
    """
    payload = {
        "apikey": HUB_API_KEY,
        "task": TASK_NAME,
        "answer": answer,
    }
    backoff = INITIAL_BACKOFF
    deadline = (time.perf_counter() + deadline_sec) if deadline_sec else None

    while True:
        if deadline is not None and time.perf_counter() >= deadline:
            raise TimeoutError("Przekroczono limit czasu (4 min)")

        try:
            r = requests.post(VERIFY_URL, json=payload, timeout=30)
        except requests.RequestException as e:
            log(f"Błąd sieci: {e}")
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue

        if r.status_code == 503:
            wait_sec = get_retry_after_sec(r) or backoff
            log(f"503 — czekam {wait_sec:.0f}s, potem retry...")
            time.sleep(min(wait_sec, MAX_BACKOFF))
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue

        if r.status_code == 429:
            try:
                data = r.json()
                wait_sec = data.get("retry_after") or get_retry_after_sec(r) or 30
            except Exception:
                wait_sec = get_retry_after_sec(r) or 30
            log(f"429 rate limit — czekam {wait_sec:.0f}s, potem retry tej samej akcji...")
            time.sleep(min(wait_sec, 120))
            continue

        # Inny status — sprawdź limity i zwróć wynik
        if r.status_code != 200:
            wait_for_limit(r)
            try:
                body = r.json()
            except Exception:
                body = r.text
            return body, r

        wait_for_limit(r)
        try:
            body = r.json()
        except Exception:
            body = r.text
        return body, r


def extract_flag(text: str | dict) -> str | None:
    s = text if isinstance(text, str) else json.dumps(text)
    m = re.search(r"\{FLG:[^}]+\}", s)
    return m.group(0) if m else None


def main() -> None:
    global start_time
    start_time = time.perf_counter()

    if not HUB_API_KEY:
        raise SystemExit("Ustaw HUB_API_KEY w .env")

    # Bonus "Nie będę czekać 4 minuty!" — pomijamy help, gdy znamy sekwencję (oszczędzamy 1 wywołanie i limit)
    skip_help = "--no-help" in sys.argv or "-n" in sys.argv
    log("Start zadania railway (cel: < 4 min)" + (" [pomijam help]" if skip_help else ""))

    route = "X-01"

    if not skip_help:
        log("Wywołuję action: help...")
        body, resp = api_call({"action": "help"}, deadline_sec=DEADLINE_SEC)
        log(f"Status: {resp.status_code}")
        # Zapis odpowiedzi help do pliku
        help_path = os.path.join(os.path.dirname(__file__), "help.md")
        with open(help_path, "w", encoding="utf-8") as f:
            if isinstance(body, dict):
                f.write(json.dumps(body, ensure_ascii=False, indent=2))
            else:
                f.write(str(body))
        log(f"Odpowiedź help zapisana do {help_path}")
        if isinstance(body, dict):
            log("Help OK. Sekwencja: reconfigure → setstatus(RTOPEN) → save.")
        flag = extract_flag(body)
        if flag:
            log(f"Flaga w help: {flag}")
            return
    else:
        log("Sekwencja: reconfigure → setstatus → save (bez help).")

    remaining = DEADLINE_SEC - (time.perf_counter() - start_time)
    # 2) reconfigure — włącz tryb rekonfiguracji dla trasy X-01
    log(f"Wywołuję action: reconfigure route={route}...")
    body, resp = api_call({"action": "reconfigure", "route": route}, deadline_sec=remaining)
    log(f"Status: {resp.status_code}, body: {str(body)[:400]}")
    flag = extract_flag(body) or extract_flag(resp.text or "")
    if flag:
        log(f"Flaga: {flag}")
        return
    if resp.status_code != 200 or (isinstance(body, dict) and body.get("ok") is False):
        log("Błąd reconfigure — sprawdź odpowiedź powyżej.")
    remaining = DEADLINE_SEC - (time.perf_counter() - start_time)

    # 3) setstatus — ustaw status na RTOPEN (otwarcie trasy)
    log(f"Wywołuję action: setstatus route={route} value=RTOPEN...")
    body, resp = api_call({"action": "setstatus", "route": route, "value": "RTOPEN"}, deadline_sec=remaining)
    log(f"Status: {resp.status_code}, body: {str(body)[:400]}")
    flag = extract_flag(body) or extract_flag(resp.text or "")
    if flag:
        log(f"Flaga: {flag}")
        return
    remaining = DEADLINE_SEC - (time.perf_counter() - start_time)

    # 4) save — zapisz i wyjdź z trybu reconfigure
    log(f"Wywołuję action: save route={route}...")
    body, resp = api_call({"action": "save", "route": route}, deadline_sec=remaining)
    log(f"Status: {resp.status_code}, body: {str(body)[:400]}")
    for candidate in [body, resp.text, json.dumps(dict(resp.headers))]:
        flag = extract_flag(candidate or "")
        if flag:
            log(f"Flaga: {flag}")
            return

    log("Koniec. Flaga nie znaleziona w odpowiedzi — sprawdź body/headers powyżej.")
    elapsed = time.perf_counter() - start_time
    log(f"Czas wykonania: {elapsed:.1f}s" + (" (w limicie 4 min)" if elapsed < DEADLINE_SEC else " (przekroczono 4 min)"))


if __name__ == "__main__":
    main()
