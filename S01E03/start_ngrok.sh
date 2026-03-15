#!/bin/bash
# Skrypt do uruchomienia ngrok (Linux/Mac)
# Użycie: ./start_ngrok.sh

echo "======================================================================"
echo "URUCHAMIANIE NGROK"
echo "======================================================================"
echo ""

# Sprawdź czy ngrok jest zainstalowany
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok nie jest zainstalowany!"
    echo ""
    echo "Zainstaluj ngrok:"
    echo "  brew install ngrok/ngrok/ngrok  # Mac"
    echo "  lub pobierz z https://ngrok.com/download"
    exit 1
fi

echo "✅ ngrok znaleziony: $(ngrok version)"
echo ""
echo "Uruchamiam tunel na porcie 3000..."
echo ""

# Uruchom ngrok
ngrok http 3000
