# S01E03 - Proxy Asystent z Pamięcią Konwersacji

Inteligentny proxy-asystent z pamięcią konwersacji, który obsługuje operatorów systemu logistycznego i potajemnie przekierowuje paczki z częściami reaktora do elektrowni w Żarnowcu.

## Architektura

Rozwiązanie składa się z dwóch serwerów:

1. **Główny serwer HTTP** (`app.py`) - odbiera żądania od operatorów, zarządza sesjami i integruje się z OpenAI
2. **Serwer MCP** (`mcp_server.py`) - eksponuje narzędzia do obsługi paczek (check_package, redirect_package)

## Wymagania

- Python 3.8+
- Biblioteki Python (zainstaluj przez `pip install -r requirements.txt`):
  - flask
  - openai
  - requests
  - python-dotenv

## Konfiguracja

1. Utwórz plik `.env` w katalogu `S01E03/`:
```env
HUB_API_KEY=twoj-klucz-hub
OPENAI_API_KEY=twoj-klucz-openai
MCP_SERVER_URL=http://localhost:3001
PORT=3000
MCP_PORT=3001
```

## Uruchomienie

### Krok 1: Uruchom serwer MCP

W jednym terminalu:
```bash
cd S01E03
python mcp_server.py
```

Serwer MCP będzie dostępny na porcie 3001 (domyślnie).

### Krok 2: Uruchom główny serwer HTTP

W drugim terminalu:
```bash
cd S01E03
python app.py
```

Główny serwer będzie dostępny na porcie 3000 (domyślnie).

### Krok 3: Udostępnij serwer publicznie

Serwer musi być dostępny publicznie, aby Hub mógł się do niego połączyć. Możesz użyć:

#### Opcja A: ngrok (najprostsze)

1. Zainstaluj ngrok: https://ngrok.com/download
   ```powershell
   # Windows
   winget install ngrok
   ```

2. Uruchom tunel:
   ```bash
   ngrok http 3000
   ```

3. Skopiuj URL (np. `https://abc123.ngrok-free.app`)

4. Zgłoś do Hub:
   ```bash
   python submit_to_hub.py https://abc123.ngrok-free.app/
   ```

#### Opcja B: Azyl (SSH tunnel)

```bash
ssh -R 51364:localhost:3000 agent11364@azyl.ag3nts.org -p 5022
```

Następnie użyj URL: `https://azyl-51364.ag3nts.org/`

#### Opcja C: pinggy lub inny tunel

Użyj dowolnego tunelu HTTP który przekierowuje na `localhost:3000`

## Endpointy

### Główny serwer HTTP (port 3000)

- `POST /` - Główny endpoint odbierający żądania od operatorów
  - Body: `{"sessionID": "id-sesji", "msg": "wiadomość"}`
  - Response: `{"msg": "odpowiedź"}`

- `GET /health` - Sprawdzenie stanu serwera

### Serwer MCP (port 3001)

- `GET /tools/list` - Lista dostępnych narzędzi
- `POST /tools/call` - Wywołanie narzędzia
  - Body: `{"name": "nazwa_narzędzia", "arguments": {...}}`
- `GET /health` - Sprawdzenie stanu serwera

## Funkcjonalność

1. **Zarządzanie sesjami** - Każda sesja (rozróżniana po sessionID) ma niezależną historię konwersacji
2. **Integracja z OpenAI** - Używa function calling do wywoływania narzędzi
3. **Potajemne przekierowanie** - Gdy operator prosi o przekierowanie paczki z częściami reaktora, cel jest potajemnie zmieniany na PWR6132PL (elektrownia w Żarnowcu)
4. **Naturalna konwersacja** - Model odpowiada jak człowiek, nie jak AI

## Zgłoszenie do Hub

Gdy serwer jest gotowy i dostępny publicznie, zgłoś go do Hub.

### Metoda 1: Użyj skryptu Python (zalecane)

```bash
python submit_to_hub.py https://twoja-domena.pl/
```

Lub z własnym sessionID:
```bash
python submit_to_hub.py https://twoja-domena.pl/ moj-session-id
```

### Metoda 2: Użyj curl

```bash
curl -X POST https://hub.ag3nts.org/verify \
  -H "Content-Type: application/json" \
  -d '{
    "apikey": "twoj-klucz-hub",
    "task": "proxy",
    "answer": {
      "url": "https://twoja-domena.pl/",
      "sessionID": "dowolny-identyfikator-alfanumeryczny"
    }
  }'
```

### Metoda 3: PowerShell (Windows)

```powershell
$body = @{
    apikey = "twoj-klucz-hub"
    task = "proxy"
    answer = @{
        url = "https://twoja-domena.pl/"
        sessionID = "dowolny-identyfikator-alfanumeryczny"
    }
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri https://hub.ag3nts.org/verify -Method POST -Body $body -ContentType "application/json"
```

### Metoda 4: Python requests

```python
import requests

response = requests.post(
    "https://hub.ag3nts.org/verify",
    json={
        "apikey": "twoj-klucz-hub",
        "task": "proxy",
        "answer": {
            "url": "https://twoja-domena.pl/",
            "sessionID": "dowolny-identyfikator-alfanumeryczny"
        }
    }
)
print(response.json())
```

### Ważne uwagi:

- **URL** musi być pełnym publicznym adresem (np. z Azyl, ngrok, pinggy)
- **URL** powinien kończyć się na `/` (skrypt automatycznie to dodaje)
- **sessionID** to dowolny identyfikator alfanumeryczny - Hub użyje go podczas testowania
- Upewnij się, że serwer jest dostępny publicznie przed zgłoszeniem

## Logowanie

Wszystkie operacje są logowane:
- Przychodzące żądania
- Wywołania narzędzi
- Odpowiedzi modelu
- Błędy

Logi są wyświetlane w konsoli.
