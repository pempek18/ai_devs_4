"""
Zadanie railway: aktywacja trasy X-01 przez API bez dokumentacji.
- Rozpoczynamy od akcji help (samo-dokumentujące API).
- Obsługa 503 (retry z backoff) i limitów zapytań (nagłówki HTTP).
- Cel: flaga w formacie {FLG:...} w odpowiedzi.
- Strategia „Nie będę czekać 4 minuty!”: zamiast samego sleep — **ciągle pytamy** API (getstatus)
  aż **minie ponad 4 minuty** od poprzedniej głównej odpowiedzi, dopiero wtedy kolejna akcja.
- Jeśli odpowiedź ma `"message": "Missing \\"answer\\" field."` — **czekamy 4 minuty** dopiero potem
  kolejne żądanie (macierz /verify, agent, api_call; w api_call bez dodatkowego busy_wait po tym czekaniu).

Agent railway (pętla akcji):
  python secrets.py --agent
  python secrets.py --agent --verbose

Ukryta flaga — testy **wyłącznie** na https://hub.ag3nts.org/verify (HEAD/GET + macierz POST):
  python secrets.py --verify
  python secrets.py --verify --verbose
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
# Całkowity limit czasu na skrypt (każda faza: 4 min+ getstatus + główne żądanie)
DEADLINE_SEC = 24 * 60 * 60
RETRY_TIME = 120
# Jak długo (sekundy) aktywnie zadawać pytania po każdej głównej odpowiedzi — ponad 4 min
MIN_BUSY_DURATION_SEC = 4 * 60 + 1
# Odstęp między kolejnymi getstatus — hub ma bardzo niski limit (~1 żądanie / 30 s).
# Za krótki (np. 3 s) szybko daje 429 „API rate limit exceeded”.
POLL_INTERVAL_SEC = 45
# Dodatkowy margines po 429 (sekundy)
POLL_AFTER_429_EXTRA_SEC = 5
# Backoff przy błędzie sieci
INITIAL_BACKOFF = 2
MAX_BACKOFF = 60
BACKOFF_MULTIPLIER = 2

# Gdy hub zwróci ten komunikat (np. POST bez answer), czekamy 4 min przed kolejnym żądaniem
MISSING_ANSWER_MESSAGE = 'Missing "answer" field.'
WAIT_AFTER_MISSING_ANSWER_SEC = 4 * 60


def log(msg: str) -> None:
    elapsed = time.perf_counter() - start_time
    print(f"[{elapsed:.1f}s] {msg}")


def _find_flg_in_text(s: str) -> list[str]:
    return re.findall(r"\{FLG:[^}]+\}", s)


def log_hidden_flag_hint(r: requests.Response) -> None:
    """
    Ukryta flaga (jak w S01E04: „GŁOWA” = nagłówki) — {FLG:...} w nazwie lub wartości nagłówka.
    Flaga w JSON (message) to zwykle główna flaga zadania, nie „ukryta”.
    """
    in_headers: list[tuple[str, str]] = []
    for name, value in r.headers.items():
        for m in _find_flg_in_text(name) + _find_flg_in_text(value):
            in_headers.append((name, m))
    if in_headers:
        log(">>> UKRYTA FLAGA W NAGŁÓWKACH HTTP <<<")
        for name, flg in in_headers:
            log(f"    {name}: ... {flg}")


def log_server_response(r: requests.Response) -> None:
    """Na konsolę: nagłówki i body każdej odpowiedzi serwera."""
    log("--- Odpowiedź serwera ---")
    log(f"HTTP {r.status_code} {r.reason}")
    log("Headers:")
    for name, value in sorted(r.headers.items()):
        log(f"  {name}: {value}")
    log("Body:")
    raw = r.text or ""
    if not raw.strip():
        log("(pusty)")
        log_hidden_flag_hint(r)
        return
    try:
        obj = json.loads(raw)
        log(json.dumps(obj, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        log(raw[:8000] + ("…" if len(raw) > 8000 else ""))
    log_hidden_flag_hint(r)


def is_missing_answer_message_response(r: requests.Response) -> bool:
    """True gdy JSON (lub tekst) zawiera komunikat o braku pola answer."""
    try:
        data = r.json()
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, str) and MISSING_ANSWER_MESSAGE in msg:
                return True
    except Exception:
        pass
    return MISSING_ANSWER_MESSAGE in (r.text or "")


def wait_if_missing_answer_response(r: requests.Response, where: str) -> None:
    """Jeśli serwer zwrócił Missing \"answer\" field. — czekaj 4 min przed kolejną akcją."""
    if not is_missing_answer_message_response(r):
        return
    log(
        f"{where}: odpowiedź z message o braku \"answer\" — "
        f"czekam {WAIT_AFTER_MISSING_ANSWER_SEC}s (4 min) przed kolejnym żądaniem..."
    )
    time.sleep(WAIT_AFTER_MISSING_ANSWER_SEC)


def _wait_after_429_sec(pr: requests.Response) -> float:
    """retry_after z JSON, potem nagłówek Retry-After."""
    try:
        data = pr.json()
        if isinstance(data, dict) and data.get("retry_after") is not None:
            return float(data["retry_after"])
    except Exception:
        pass
    ra = pr.headers.get("Retry-After")
    if ra is not None:
        try:
            return float(ra)
        except ValueError:
            pass
    return 30.0


def busy_wait_with_polls(route: str) -> None:
    """
    Nie czekamy w ciszy — getstatus(route) w bezpiecznych odstępach, aż minie MIN_BUSY_DURATION_SEC.
    Najpierw pauza (żeby nie uderzyć w limit tuż po help/reconfigure), potem polling.
    """
    t0 = time.perf_counter()
    n = 0
    poll_interval = float(POLL_INTERVAL_SEC)
    log(
        f"Aktywne oczekiwanie: getstatus({route}) co ~{POLL_INTERVAL_SEC}s, "
        f"dopóki nie minie {MIN_BUSY_DURATION_SEC}s (ponad 4 min)..."
    )
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= MIN_BUSY_DURATION_SEC:
            log(f"Minęło {elapsed:.0f}s — koniec fazy pytań (getstatus: {n}×).")
            break

        # Zawsze pauza PRZED kolejnym getstatus — unika serii 429 tuż po głównym żądaniu
        sleep_left = MIN_BUSY_DURATION_SEC - elapsed
        if sleep_left <= 0:
            break
        pause = min(poll_interval, sleep_left)
        label = "pierwsza pauza po głównej odpowiedzi" if n == 0 else "odstęp przed kolejnym getstatus"
        log(f"  ({label}: {pause:.0f}s, zostało do końca fazy ~{sleep_left:.0f}s)")
        time.sleep(pause)

        elapsed = time.perf_counter() - t0
        if elapsed >= MIN_BUSY_DURATION_SEC:
            log(f"Minęło {elapsed:.0f}s — koniec fazy pytań (getstatus: {n}×).")
            break

        n += 1
        payload = {
            "apikey": HUB_API_KEY,
            "task": TASK_NAME,
            "answer": {"action": "getstatus", "route": route},
        }
        try:
            pr = requests.post(VERIFY_URL, json=payload, timeout=RETRY_TIME)
        except requests.RequestException as e:
            log(f"  [pytanie #{n}] sieć: {e} — pauza {INITIAL_BACKOFF}s")
            time.sleep(INITIAL_BACKOFF)
            continue

        raw = pr.text or ""
        snippet = raw.replace("\n", " ")[:160]
        elapsed = time.perf_counter() - t0
        log(
            f"  [pytanie #{n}] getstatus → HTTP {pr.status_code} "
            f"({elapsed:.0f}s / {MIN_BUSY_DURATION_SEC}s) {snippet}"
        )

        for flg in _find_flg_in_text(raw):
            log(f"  >>> znaleziono w body: {flg}")
        log_hidden_flag_hint(pr)

        if pr.status_code == 429:
            wait_sec = _wait_after_429_sec(pr) + POLL_AFTER_429_EXTRA_SEC
            poll_interval = max(poll_interval, wait_sec, float(POLL_INTERVAL_SEC))
            log(
                f"  429 — limit API: czekam {wait_sec:.0f}s; "
                f"kolejne odstępy co min. {poll_interval:.0f}s"
            )
            time.sleep(wait_sec)
            continue
        if pr.status_code == 503:
            log("  503 — pauza 15s i kolejne pytanie (bez zmiany odstępu bazowego)")
            time.sleep(15)
            continue

        # Sukces — wróć do bazowego odstępu (nie eskaluj w nieskończoność)
        poll_interval = float(POLL_INTERVAL_SEC)


def wait_for_limit(response: requests.Response) -> None:
    """Faza pytań już odczekała ponad 4 min — tu tylko potwierdzenie."""
    _ = response
    log("(Po głównej odpowiedzi minęło ponad 4 min aktywnego getstatus.)")


def api_call(
    answer: dict,
    deadline_sec: float | None = None,
    poll_route: str = "X-01",
) -> tuple[dict | str, requests.Response]:
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
            raise TimeoutError("Przekroczono limit czasu skryptu")

        try:
            r = requests.post(VERIFY_URL, json=payload, timeout=RETRY_TIME)
        except requests.RequestException as e:
            log(f"Błąd sieci: {e}")
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue

        log_server_response(r)
        if is_missing_answer_message_response(r):
            wait_if_missing_answer_response(r, "api_call")
            # Już odczekano 4 min — pomijamy dodatkowe busy_wait z getstatus (unikaj podwójnego długiego czekania)
        else:
            busy_wait_with_polls(poll_route)

        if r.status_code == 503:
            log("503 — ponawiam to samo żądanie (po fazie pytań)...")
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue

        if r.status_code == 429:
            log("429 — ponawiam to samo żądanie (po fazie pytań)...")
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


def _find_flg_in_object(obj: object) -> list[str]:
    """Rekurencyjnie szuka {FLG:...} w stringach wewnątrz dict/list."""
    out: list[str] = []
    if isinstance(obj, str):
        out.extend(_find_flg_in_text(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_find_flg_in_object(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_find_flg_in_object(v))
    return out


def collect_flags_from_response(r: requests.Response) -> list[str]:
    """Wszystkie wystąpienia {FLG:...} w body (tekst + JSON), nagłówkach."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add_all(items: list[str]) -> None:
        for x in items:
            if x not in seen:
                seen.add(x)
                ordered.append(x)

    raw = r.text or ""
    add_all(_find_flg_in_text(raw))
    try:
        add_all(_find_flg_in_object(r.json()))
    except Exception:
        pass
    for name, value in r.headers.items():
        add_all(_find_flg_in_text(name))
        add_all(_find_flg_in_text(value))
    return ordered


def agent_post(answer: dict) -> requests.Response:
    """Jedno żądanie do /verify (bez busy_wait) — dla agenta."""
    return verify_post(TASK_NAME, answer)


def verify_post(task: str, answer: dict | None, extra: dict | None = None) -> requests.Response:
    """POST JSON na /verify — task + answer (+ opcjonalne dodatkowe klucze)."""
    body: dict = {"apikey": HUB_API_KEY, "task": task}
    if answer is not None:
        body["answer"] = answer
    if extra:
        body.update(extra)
    return requests.post(VERIFY_URL, json=body, timeout=RETRY_TIME)


def _sleep_rate_limit(r: requests.Response) -> None:
    if r.status_code == 429:
        w = _wait_after_429_sec(r) + POLL_AFTER_429_EXTRA_SEC
        log(f"  429 — czekam {w:.0f}s")
        time.sleep(w)
    elif r.status_code == 503:
        time.sleep(15)
    else:
        time.sleep(POLL_INTERVAL_SEC)


def build_verify_post_matrix() -> list[tuple[str, dict]]:
    """
    Macierz ładunków wyłącznie dla POST /verify
    (różne taski, brak answer, pusta answer, akcje railway).
    """
    k = HUB_API_KEY
    rows: list[tuple[str, dict]] = []

    def add(name: str, payload: dict) -> None:
        rows.append((name, payload))

    # Bez / z minimalnym ciałem
    add("tylko apikey", {"apikey": k})
    add("apikey + task railway (bez answer)", {"apikey": k, "task": "railway"})
    add("railway + answer null", {"apikey": k, "task": "railway", "answer": None})
    add("railway + answer {}", {"apikey": k, "task": "railway", "answer": {}})

    # Inne znane taski z kursu (hub może odpowiedzieć inaczej — czasem flaga/błąd z podpowiedzią)
    for task in ("people", "findhim", "sendit", "proxy"):
        add(f"task {task} bez answer", {"apikey": k, "task": task})
        add(f"task {task} + answer {{}}", {"apikey": k, "task": task, "answer": {}})

    # Railway — akcje z help
    railway_actions: list[dict] = [
        {"action": "help"},
        {"action": "getstatus", "route": "X-01"},
        {"action": "getstatus", "route": "x-01"},
        {"action": "reconfigure", "route": "X-01"},
        {"action": "setstatus", "route": "X-01", "value": "RTOPEN"},
        {"action": "setstatus", "route": "X-01", "value": "RTCLOSE"},
        {"action": "save", "route": "X-01"},
    ]
    for ans in railway_actions:
        add(f"railway {ans.get('action', ans)}", {"apikey": k, "task": "railway", "answer": ans})

    # Minimalne szkielety innych zadań (część może zwrócić komunikat z FLG)
    add(
        "people pusta tablica",
        {"apikey": k, "task": "people", "answer": {"people": []}},
    )
    add(
        "findhim minimal",
        {
            "apikey": k,
            "task": "findhim",
            "answer": {
                "name": "",
                "surname": "",
                "accessLevel": 0,
                "powerPlant": "",
            },
        },
    )
    add(
        "sendit pusta deklaracja",
        {"apikey": k, "task": "sendit", "answer": {"declaration": ""}},
    )

    return rows


def explore_verify_for_hidden_flag(verbose: bool = False) -> str | None:
    """
    Koncentracja na jednym endpoincie /verify: metody HTTP + macierz POST.
    Szuka {FLG:...} w body, zagnieżdżonym JSON i nagłówkach każdej odpowiedzi.
    """
    log("=== Eksploracja /verify — szukamy ukrytej {FLG:...} (nagłówki + body) ===")
    sess = requests.Session()

    def scan(r: requests.Response, label: str) -> str | None:
        if verbose:
            log_server_response(r)
        else:
            log(f"  {label} → HTTP {r.status_code}")
        flags = collect_flags_from_response(r)
        for flg in flags:
            log(f"*** /verify [{label}] → FLAGA: {flg} ***")
            return flg
        log_hidden_flag_hint(r)
        return None

    # ——— HEAD / GET / OPTIONS — ten sam URL co POST /verify ———
    for method in ("HEAD", "GET", "OPTIONS"):
        label = f"{method} /verify"
        try:
            r = sess.request(method, VERIFY_URL, timeout=RETRY_TIME)
            hit = scan(r, label)
            if hit:
                return hit
            wait_if_missing_answer_response(r, label)
            _sleep_rate_limit(r)
        except requests.RequestException as e:
            log(f"  {label} → błąd: {e}")
            time.sleep(POLL_INTERVAL_SEC)

    # ——— Macierz POST (jedno przejście); ukryta flaga często w nagłówku lub nietypowym body ———
    for name, payload in build_verify_post_matrix():
        label = f"POST /verify — {name}"
        try:
            r = sess.post(VERIFY_URL, json=payload, timeout=RETRY_TIME)
            hit = scan(r, label)
            if hit:
                return hit
            wait_if_missing_answer_response(r, label)
            _sleep_rate_limit(r)
        except requests.RequestException as e:
            log(f"  {label} → błąd: {e}")
            time.sleep(POLL_INTERVAL_SEC)

    log("=== Koniec przejścia macierzy /verify — nie znaleziono {FLG:...} w tej iteracji ===")
    return None


def flag_search_agent(
    verbose: bool = False,
    max_rounds: int | None = None,
) -> str | None:
    """
    Agent w pętli sonduje hub (task railway), szuka {FLG:...} w każdej odpowiedzi.
    Zwraca pierwszą znalezioną flagę lub None (gdy max_rounds).
    """
    # Kolejność: najpierw bezpieczne (read-only), potem warianty trasy
    probes: list[dict] = [
        {"action": "help"},
        {"action": "getstatus", "route": "X-01"},
        {"action": "getstatus", "route": "x-01"},
        {"action": "reconfigure", "route": "X-01"},
        {"action": "setstatus", "route": "X-01", "value": "RTOPEN"},
        {"action": "save", "route": "X-01"},
    ]
    log("=== Agent: pętla szukająca {FLG:...} na serwerze (Ctrl+C = stop) ===")
    round_num = 0
    while True:
        if max_rounds is not None and round_num >= max_rounds:
            log("Agent: osiągnięto max_rounds — koniec.")
            return None
        round_num += 1
        log(f"--- Runda agenta #{round_num} ---")
        for answer in probes:
            label = json.dumps(answer, ensure_ascii=False)
            try:
                r = agent_post(answer)
            except requests.RequestException as e:
                log(f"  {label} → błąd sieci: {e}")
                time.sleep(INITIAL_BACKOFF)
                continue

            if verbose:
                log_server_response(r)
            else:
                log(f"  {label} → HTTP {r.status_code}")

            flags = collect_flags_from_response(r)
            for flg in flags:
                log(f"*** AGENT ZNALAZŁ FLAGĘ: {flg} ***")
                return flg

            wait_if_missing_answer_response(r, f"agent {label}")

            if r.status_code == 429:
                w = _wait_after_429_sec(r) + POLL_AFTER_429_EXTRA_SEC
                log(f"  429 — czekam {w:.0f}s przed kolejną sondą")
                time.sleep(w)
            elif r.status_code == 503:
                log("  503 — pauza 15s")
                time.sleep(15)
            else:
                time.sleep(POLL_INTERVAL_SEC)


def main() -> None:
    global start_time
    start_time = time.perf_counter()

    if not HUB_API_KEY:
        raise SystemExit("Ustaw HUB_API_KEY w .env")

    # Tylko testy na /verify (HEAD/GET/OPTIONS + macierz POST)
    if "--verify" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        explore_verify_for_hidden_flag(verbose=verbose)
        return

    # Agent railway w pętli (POST /verify, task railway)
    if "--agent" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        flag_search_agent(verbose=verbose, max_rounds=None)
        return

    # Bonus "Nie będę czekać 4 minuty!" — pomijamy help, gdy znamy sekwencję (oszczędzamy 1 wywołanie i limit)
    skip_help = "--no-help" in sys.argv or "-n" in sys.argv
    log(
        "Start railway: po każdej głównej odpowiedzi — pytania getstatus aż minie ponad 4 min"
        + (" [pomijam help]" if skip_help else "")
    )

    route = "X-01"

    if not skip_help:
        log("Wywołuję action: help...")
        body, resp = api_call({"action": "help"}, deadline_sec=DEADLINE_SEC)
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
    flag = extract_flag(body) or extract_flag(resp.text or "")
    if flag:
        log(f"Flaga: {flag}")
        return
    remaining = DEADLINE_SEC - (time.perf_counter() - start_time)

    # 4) save — zapisz i wyjdź z trybu reconfigure
    log(f"Wywołuję action: save route={route}...")
    body, resp = api_call({"action": "save", "route": route}, deadline_sec=remaining)
    for candidate in [body, resp.text, json.dumps(dict(resp.headers))]:
        flag = extract_flag(candidate or "")
        if flag:
            log(f"Flaga: {flag}")
            return

    log("Koniec. Flaga nie znaleziona w odpowiedzi — sprawdź body/headers powyżej.")
    elapsed = time.perf_counter() - start_time
    log(f"Czas wykonania: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
