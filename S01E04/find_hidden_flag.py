"""
Ukryta flaga – podpowiedź: "Myśleli, że to usunęli, ale to zostało w mojej GŁOWIE"
GŁOWA = HEAD = nagłówki HTTP (response headers) lub metoda HTTP HEAD.

Skrypt sprawdza nagłówki odpowiedzi z różnych URL-i huba – flaga może być
w niestandardowym nagłówku (np. X-Flag, X-Hidden-Flag, Flag).
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("HUB_API_KEY")
BASE = "https://hub.ag3nts.org"


def print_headers(method: str, url: str, **kwargs) -> None:
    r = requests.request(method, url, timeout=15, **kwargs)
    print(f"\n{method} {url}")
    print(f"  Status: {r.status_code}")
    for name, value in sorted(r.headers.items()):
        # Wszystkie nagłówki – flaga może być w dowolnym
        print(f"  {name}: {value}")


def main():
    urls = [
        f"{BASE}/dane/doc/index.md",
        f"{BASE}/dane/doc/zalacznik-E.md",
        f"{BASE}/dane/doc/zalacznik-I.md",
        f"{BASE}/",
        f"{BASE}/task/sendit",  # ewentualny endpoint zadania
    ]
    print("=== GET (nagłówki) ===")
    for url in urls:
        try:
            print_headers("GET", url)
        except Exception as e:
            print(f"\nGET {url} -> błąd: {e}")

    print("\n=== HEAD (tylko nagłówki, bez body) ===")
    for url in urls[:3]:
        try:
            print_headers("HEAD", url)
        except Exception as e:
            print(f"\nHEAD {url} -> błąd: {e}")

    # Odpowiedź /verify też może mieć ukrytą flagę w nagłówku – sprawdź po wysłaniu deklaracji w app.py
    print("\n--- Podpowiedź ---")
    print("Jeśli flaga nie jest w powyższych, uruchom app.py i zobacz nagłówki odpowiedzi z POST /verify.")


if __name__ == "__main__":
    main()
