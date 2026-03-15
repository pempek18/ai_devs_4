"""
Skrypt do testowania serwera przez Azyl SSH tunnel.
Użycie: python test_azyl.py [agent_id] [port]
"""
import sys
import requests
import json
from datetime import datetime

def test_azyl_server(agent_id: str, port: int = 51364):
    """Testuje serwer przez Azyl"""
    
    # Spróbuj różne warianty URL (Azyl używa formatu azyl-{port}.ag3nts.org)
    urls_to_try = [
        f"https://azyl-{port}.ag3nts.org",
        f"http://azyl-{port}.ag3nts.org",
        f"https://{agent_id}.azyl.ag3nts.org:{port}",
        f"http://{agent_id}.azyl.ag3nts.org:{port}",
        f"https://azyl.ag3nts.org:{port}",
        f"http://azyl.ag3nts.org:{port}",
    ]
    
    print("=" * 70)
    print("TEST SERWERA PRZEZ AZYL")
    print("=" * 70)
    print(f"Agent ID: {agent_id}")
    print(f"Port: {port}")
    print(f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Sprawdzam różne warianty URL...")
    print()
    
    working_url = None
    
    for url in urls_to_try:
        print(f"Testowanie: {url}/health")
        try:
            response = requests.get(f"{url}/health", timeout=5, verify=False)
            if response.status_code == 200:
                # Sprawdź czy to JSON (serwer) czy HTML (strona błędu)
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type or response.text.strip().startswith('{'):
                    try:
                        data = response.json()
                        print(f"   ✅ DZIAŁA! URL: {url}")
                        print(f"   Odpowiedź: {data}")
                        working_url = url
                        break
                    except:
                        print(f"   ⚠️ Status 200, ale nie JSON: {response.text[:100]}")
                else:
                    print(f"   ⚠️ Status 200, ale to HTML (strona błędu), nie serwer")
                    print(f"   Content-Type: {content_type}")
            else:
                print(f"   ❌ Status: {response.status_code}")
        except requests.exceptions.SSLError:
            # Spróbuj HTTP zamiast HTTPS
            try:
                http_url = url.replace('https://', 'http://')
                response = requests.get(f"{http_url}/health", timeout=5)
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type or response.text.strip().startswith('{'):
                        print(f"   ✅ DZIAŁA! URL: {http_url}")
                        working_url = http_url
                        break
            except:
                print(f"   ❌ Błąd połączenia")
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Nie można połączyć")
        except Exception as e:
            print(f"   ❌ Błąd: {e}")
        print()
    
    if not working_url:
        print("❌ Nie znaleziono działającego URL!")
        print()
        print("Sprawdź:")
        print("1. Czy tunel SSH jest aktywny?")
        print("2. Czy serwer lokalny działa na porcie 3000?")
        print("3. Czy używasz poprawnego agent_id i portu?")
        return None
    
    print()
    print("=" * 70)
    print(f"✅ ZNALEZIONO DZIAŁAJĄCY URL: {working_url}")
    print("=" * 70)
    print()
    
    # Teraz przetestuj pełny endpoint
    print("Testowanie głównego endpointu...")
    try:
        test_payload = {
            "sessionID": "test-azyl-" + datetime.now().strftime("%Y%m%d%H%M%S"),
            "msg": "Test przez Azyl"
        }
        response = requests.post(
            f"{working_url}/",
            json=test_payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
            verify=False
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Główny endpoint działa!")
            print(f"   Odpowiedź: {data.get('msg', '')[:100]}...")
        else:
            print(f"   ⚠️ Status: {response.status_code}")
    except Exception as e:
        print(f"   ⚠️ Błąd: {e}")
    
    print()
    print("=" * 70)
    print("Użyj tego URL do zgłoszenia do Hub:")
    print(f"{working_url}/")
    print("=" * 70)
    
    return working_url


if __name__ == '__main__':
    # Wyłącz ostrzeżenia SSL (dla testów)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    if len(sys.argv) < 2:
        print("Użycie: python test_azyl.py <agent_id> [port]")
        print()
        print("Przykład:")
        print("  python test_azyl.py agent11364 51364")
        print()
        print("Z komendy SSH:")
        print("  ssh -R 51364:localhost:3000 agent11364@azyl.ag3nts.org -p 5022")
        print("  → agent_id = agent11364, port = 51364")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 51364
    
    test_azyl_server(agent_id, port)
