# Konfiguracja ngrok

## Instalacja ngrok

### Windows
1. Pobierz z https://ngrok.com/download
2. Rozpakuj i dodaj do PATH lub umieść w folderze projektu

### Lub użyj Chocolatey:
```powershell
choco install ngrok
```

### Lub użyj winget:
```powershell
winget install ngrok
```

### Linux/Mac
```bash
# Homebrew (Mac)
brew install ngrok/ngrok/ngrok

# Lub pobierz z https://ngrok.com/download
```

## Konfiguracja (opcjonalna)

1. Zarejestruj się na https://dashboard.ngrok.com (darmowe konto)
2. Pobierz authtoken z dashboard
3. Skonfiguruj:
```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

## Uruchomienie tunelu

### Podstawowe użycie (darmowe, ale URL zmienia się przy każdym uruchomieniu):
```bash
ngrok http 3000
```

### Z własną domeną (wymaga płatnego planu):
```bash
ngrok http 3000 --domain=twoja-domena.ngrok-free.app
```

## Co zobaczysz

Po uruchomieniu ngrok pokaże:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:3000
```

Użyj tego URL do zgłoszenia do Hub.

## Testowanie

```bash
# Test health endpoint
curl https://abc123.ngrok-free.app/health

# Test głównego endpointu
curl -X POST https://abc123.ngrok-free.app/ \
  -H "Content-Type: application/json" \
  -d '{"sessionID":"test","msg":"test"}'
```

## Zgłoszenie do Hub

```bash
python submit_to_hub.py https://abc123.ngrok-free.app/
```
