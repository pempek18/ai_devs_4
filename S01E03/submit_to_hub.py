"""
Skrypt do zgłoszenia URL serwera do Hub.
Użycie: python submit_to_hub.py <url> [sessionID]
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

HUB_API_KEY = os.getenv('HUB_API_KEY')
VERIFY_URL = "https://hub.ag3nts.org/verify"

def submit_to_hub(server_url: str, session_id: str = "test-session-123"):
    """Zgłasza URL serwera do Hub"""
    
    if not HUB_API_KEY:
        print("BŁĄD: Brak HUB_API_KEY w pliku .env")
        sys.exit(1)
    
    if not server_url:
        print("BŁĄD: Brak URL serwera")
        sys.exit(1)
    
    # Upewnij się, że URL kończy się na /
    if not server_url.endswith('/'):
        server_url = server_url + '/'
    
    payload = {
        "apikey": HUB_API_KEY,
        "task": "proxy",
        "answer": {
            "url": server_url,
            "sessionID": session_id
        }
    }
    
    print(f"Zgłaszanie do Hub...")
    print(f"URL: {server_url}")
    print(f"SessionID: {session_id}")
    print(f"Payload: {payload}")
    print()
    
    try:
        response = requests.post(VERIFY_URL, json=payload)
        response.raise_for_status()
        
        result = response.json()
        print("✅ SUKCES!")
        print(f"Odpowiedź z Hub:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
    
    except requests.exceptions.RequestException as e:
        print(f"❌ BŁĄD: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status: {e.response.status_code}")
            print(f"Odpowiedź: {e.response.text}")
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Użycie: python submit_to_hub.py <url> [sessionID]")
        print()
        print("Przykłady:")
        print("  python submit_to_hub.py https://abc123.ngrok-free.app/")
        print("  python submit_to_hub.py https://abc123.ngrok-free.app/ my-session-id")
        sys.exit(1)
    
    url = sys.argv[1]
    session_id = sys.argv[2] if len(sys.argv) > 2 else "test-session-123"
    
    submit_to_hub(url, session_id)
