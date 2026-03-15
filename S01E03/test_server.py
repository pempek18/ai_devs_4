"""
Skrypt do testowania czy serwer odpowiada.
Użycie: python test_server.py [url]
"""
import sys
import requests
import json
import urllib3
from datetime import datetime

# Wyłącz ostrzeżenia SSL dla testów
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_server(base_url: str):
    """Testuje czy serwer odpowiada"""
    print("=" * 70)
    print("TEST SERWERA")
    print("=" * 70)
    print(f"URL: {base_url}")
    print(f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test 1: Health check
    print("1. Test endpointu /health...")
    try:
        # Wyłącz weryfikację SSL dla testów (jeśli używasz self-signed cert)
        response = requests.get(f"{base_url}/health", timeout=5, verify=False)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ OK - Status: {data.get('status')}, Sesje: {data.get('sessions')}")
        else:
            print(f"   ❌ BŁĄD - Status code: {response.status_code}")
            print(f"   Odpowiedź: {response.text}")
    except requests.exceptions.ConnectionError:
        print(f"   ❌ BŁĄD - Nie można połączyć się z serwerem")
        print(f"   Upewnij się że serwer działa na {base_url}")
        return False
    except Exception as e:
        print(f"   ❌ BŁĄD - {e}")
        return False
    
    print()
    
    # Test 2: Test endpoint
    print("2. Test endpointu /test...")
    try:
        response = requests.get(f"{base_url}/test", timeout=5, verify=False)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ OK")
            print(f"   Aktywne sesje: {data.get('active_sessions')}")
            print(f"   MCP Server: {'✅ Dostępny' if data.get('mcp_server_available') else '❌ Niedostępny'}")
        else:
            print(f"   ❌ BŁĄD - Status code: {response.status_code}")
    except Exception as e:
        print(f"   ❌ BŁĄD - {e}")
    
    print()
    
    # Test 3: Główny endpoint (POST)
    print("3. Test głównego endpointu POST /...")
    try:
        test_payload = {
            "sessionID": "test-session-" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "msg": "Test - czy serwer odpowiada?"
        }
        response = requests.post(
            f"{base_url}/",
            json=test_payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
            verify=False
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ OK - Serwer odpowiedział")
            print(f"   Odpowiedź: {data.get('msg', '')[:100]}...")
        else:
            print(f"   ❌ BŁĄD - Status code: {response.status_code}")
            print(f"   Odpowiedź: {response.text[:200]}")
    except requests.exceptions.Timeout:
        print(f"   ⚠️ TIMEOUT - Serwer nie odpowiedział w ciągu 30 sekund")
        print(f"   To może oznaczać że LLM/MCP działa zbyt długo")
    except Exception as e:
        print(f"   ❌ BŁĄD - {e}")
    
    print()
    print("=" * 70)
    print("TEST ZAKOŃCZONY")
    print("=" * 70)
    
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1:
        url = sys.argv[1]
        # Upewnij się że URL kończy się na /
        if not url.endswith('/'):
            url = url + '/'
        # Usuń końcowy / dla testów
        url = url.rstrip('/')
    else:
        url = "http://localhost:3000"
    
    test_server(url)
