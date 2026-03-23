"""
S01E04 sendit - wypełnienie i wysłanie deklaracji SPK (Gdańsk -> Żarnowiec).
Analizuje załączniki dokumentacji, buduje deklarację i wysyła do /verify.
"""
import os
import base64
import requests
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

HUB_API_KEY = os.getenv("HUB_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HUB_VERIFY_URL = "https://hub.ag3nts.org/verify"
DIR = Path(__file__).resolve().parent

client = OpenAI(api_key=OPENAI_API_KEY)


def get_route_code_from_image() -> str:
    """Odczytuje kod trasy Gdańsk-Żarnowiec z obrazu trasy-wylaczone.png (vision)."""
    img_path = DIR / "trasy-wylaczone.png"
    if not img_path.exists():
        raise FileNotFoundError(f"Brak pliku {img_path}")
    with open(img_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Na obrazie jest lista tras wyłączonych w systemie kolejowym. Podaj dokładnie kod trasy łączącej Gdańsk z Żarnowcem (format np. X-XX lub L-XX). Odpowiedz tylko tym kodem, bez cudzysłowów i bez dodatkowego opisu.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            }
        ],
        max_tokens=50,
    )
    code = (response.choices[0].message.content or "").strip().strip('"')
    return code or "X-01"


def build_declaration(route_code: str) -> str:
    """Buduje deklarację zgodnie ze wzorem z załącznika E i danymi z task.md."""
    # WDP: 1000 kg = 2 wagony bazowe, każdy kolejny 500 kg; 2800 kg -> (2800-1000)/500 = 3.6 -> 4 wagony dodatkowe
    wdp = 4
    data_str = datetime.now().strftime("%Y-%m-%d")
    return f"""SYSTEM PRZESYŁEK KONDUKTORSKICH - DEKLARACJA ZAWARTOŚCI
======================================================
DATA: {data_str}
PUNKT NADAWCZY: Gdańsk
------------------------------------------------------
NADAWCA: 450202122
PUNKT DOCELOWY: Żarnowiec
TRASA: {route_code}
------------------------------------------------------
KATEGORIA PRZESYŁKI: A
------------------------------------------------------
OPIS ZAWARTOŚCI (max 200 znaków): kasety z paliwem do reaktora
------------------------------------------------------
DEKLAROWANA MASA (kg): 2800
------------------------------------------------------
WDP: {wdp}
------------------------------------------------------
UWAGI SPECJALNE: 
------------------------------------------------------
KWOTA DO ZAPŁATY: 0
------------------------------------------------------
OŚWIADCZAM, ŻE PODANE INFORMACJE SĄ PRAWDZIWE.
BIORĘ NA SIEBIE KONSEKWENCJĘ ZA FAŁSZYWE OŚWIADCZENIE.
======================================================"""


def verify(declaration: str) -> tuple[dict, requests.Response]:
    """Wysyła deklarację do Hub /verify. Zwraca (body JSON, obiekt Response)."""
    r = requests.post(
        HUB_VERIFY_URL,
        json={
            "apikey": HUB_API_KEY,
            "task": "sendit",
            "answer": {"declaration": declaration},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json(), r


def main():
    if not HUB_API_KEY or not OPENAI_API_KEY:
        raise SystemExit("Ustaw HUB_API_KEY i OPENAI_API_KEY w .env")

    print("Analizuję obraz tras wyłączonych (trasy-wylaczone.png)...")
    route_code = get_route_code_from_image()
    print(f"Kod trasy Gdańsk–Żarnowiec: {route_code}")

    declaration = build_declaration(route_code)
    print("\nDeklaracja:\n")
    print(declaration)
    print("\nWysyłam do /verify...")

    result, response = verify(declaration)
    print("Odpowiedź Hub (body):", result)
    # Ukryta flaga: "zostało w mojej GŁOWIE" = w nagłówkach HTTP (HEAD)
    print("\nNagłówki odpowiedzi (szukaj ukrytej flagi):")
    for name, value in response.headers.items():
        print(f"  {name}: {value}")
    if "flag" in result:
        print("\nFlaga (z body):", result.get("flag", result.get("message", result)))


if __name__ == "__main__":
    main()
