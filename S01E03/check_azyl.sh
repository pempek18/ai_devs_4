#!/bin/bash
# Skrypt do sprawdzania portu na Azyl
# Użyj po zalogowaniu przez SSH: ssh agent11364@azyl.ag3nts.org -p 5022

PORT=${1:-51364}

echo "======================================================================"
echo "SPRAWDZANIE PORTU NA AZYL"
echo "======================================================================"
echo "Port: $PORT"
echo ""

# 1. Sprawdź czy port nasłuchuje
echo "1. Sprawdzam czy port $PORT nasłuchuje..."
if command -v ss &> /dev/null; then
    PORT_CHECK=$(ss -tuln | grep ":$PORT ")
else
    PORT_CHECK=$(netstat -tuln 2>/dev/null | grep ":$PORT ")
fi

if [ -n "$PORT_CHECK" ]; then
    echo "   ✅ Port $PORT jest otwarty i nasłuchuje"
    echo "   $PORT_CHECK"
else
    echo "   ❌ Port $PORT NIE nasłuchuje"
    echo "   Sprawdź czy tunel SSH jest aktywny na Twoim lokalnym komputerze"
fi

echo ""

# 2. Sprawdź procesy na porcie
echo "2. Sprawdzam procesy na porcie $PORT..."
if command -v lsof &> /dev/null; then
    PROC_CHECK=$(lsof -i :$PORT 2>/dev/null)
    if [ -n "$PROC_CHECK" ]; then
        echo "   $PROC_CHECK"
    else
        echo "   Brak procesów na porcie $PORT"
    fi
elif command -v fuser &> /dev/null; then
    FUSER_CHECK=$(fuser $PORT/tcp 2>/dev/null)
    if [ -n "$FUSER_CHECK" ]; then
        echo "   $FUSER_CHECK"
    else
        echo "   Brak procesów na porcie $PORT"
    fi
else
    echo "   (lsof/fuser nie dostępne)"
fi

echo ""

# 3. Test lokalnego połączenia
echo "3. Testuję lokalne połączenie na porcie $PORT..."
HTTP_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/health 2>/dev/null)
if [ "$HTTP_TEST" = "200" ]; then
    echo "   ✅ HTTP endpoint odpowiada (status 200)"
    echo "   Odpowiedź:"
    curl -s http://localhost:$PORT/health | head -3
elif [ -n "$HTTP_TEST" ]; then
    echo "   ⚠️ HTTP endpoint odpowiada, ale status: $HTTP_TEST"
else
    echo "   ❌ Nie można połączyć się z http://localhost:$PORT/health"
    echo "   Sprawdź czy lokalny serwer działa na porcie 3000"
fi

echo ""

# 4. Test zewnętrznego dostępu
echo "4. Testuję zewnętrzny dostęp..."
EXTERNAL_URL="https://azyl-$PORT.ag3nts.org"
EXTERNAL_TEST=$(curl -s -o /dev/null -w "%{http_code}" $EXTERNAL_URL/health 2>/dev/null)
if [ "$EXTERNAL_TEST" = "200" ]; then
    echo "   ✅ Zewnętrzny URL odpowiada: $EXTERNAL_URL"
elif [ -n "$EXTERNAL_TEST" ]; then
    echo "   ⚠️ Zewnętrzny URL odpowiada, ale status: $EXTERNAL_TEST"
    echo "   URL: $EXTERNAL_URL"
else
    echo "   ❌ Nie można połączyć się z $EXTERNAL_URL"
fi

echo ""

# 5. Sprawdź aktywne połączenia SSH
echo "5. Sprawdzam aktywne połączenia SSH..."
SSH_CONN=$(ps aux | grep "ssh.*-R.*$PORT" | grep -v grep)
if [ -n "$SSH_CONN" ]; then
    echo "   ✅ Znaleziono aktywne połączenie SSH z reverse tunnel:"
    echo "   $SSH_CONN"
else
    echo "   ⚠️ Nie znaleziono aktywnego połączenia SSH z reverse tunnel"
    echo "   Upewnij się że uruchomiłeś: ssh -R $PORT:localhost:3000 ..."
fi

echo ""
echo "======================================================================"
echo "PODSUMOWANIE"
echo "======================================================================"
echo ""
echo "Jeśli port nasłuchuje i odpowiada lokalnie, ale nie z zewnątrz:"
echo "  - To może być normalne (port dostępny przez publiczny URL)"
echo "  - Sprawdź czy publiczny URL działa: curl https://azyl-$PORT.ag3nts.org/health"
echo ""
echo "Jeśli port nie nasłuchuje:"
echo "  - Sprawdź czy tunel SSH jest aktywny na lokalnym komputerze"
echo "  - Sprawdź czy lokalny serwer działa: curl http://localhost:3000/health"
echo ""
