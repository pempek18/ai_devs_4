"""
Prosty skrypt do monitorowania ruchu na serwerze.
Używa requests do okresowego sprawdzania endpointu /health
"""
import time
import requests
import sys
from datetime import datetime

SERVER_URL = "http://localhost:3000"

def check_server():
    """Sprawdza czy serwer odpowiada"""
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return True, data
        else:
            return False, f"Status: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Serwer nie odpowiada - upewnij się że działa"
    except Exception as e:
        return False, str(e)

def monitor():
    """Monitoruje serwer co kilka sekund"""
    print("=" * 60)
    print("MONITOROWANIE SERWERA")
    print("=" * 60)
    print(f"URL: {SERVER_URL}")
    print(f"Sprawdzam co 3 sekundy...")
    print("Naciśnij Ctrl+C aby zatrzymać")
    print("=" * 60)
    print()
    
    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_ok, data = check_server()
            
            if is_ok:
                sessions = data.get("sessions", 0)
                status = "✅ OK"
                print(f"[{timestamp}] {status} | Sesje: {sessions} | Status: {data.get('status')}")
            else:
                status = "❌ BŁĄD"
                print(f"[{timestamp}] {status} | {data}")
            
            time.sleep(3)
    
    except KeyboardInterrupt:
        print("\n\nMonitorowanie zatrzymane.")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        SERVER_URL = sys.argv[1]
    
    monitor()
