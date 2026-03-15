# Skrypt do uruchomienia ngrok i automatycznego wyciągnięcia URL
# Użycie: .\start_ngrok.ps1

Write-Host "=" * 70
Write-Host "URUCHAMIANIE NGROK"
Write-Host "=" * 70
Write-Host ""

# Sprawdź czy ngrok jest zainstalowany
try {
    $ngrokVersion = ngrok version
    Write-Host "✅ ngrok znaleziony: $ngrokVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ ngrok nie jest zainstalowany!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Zainstaluj ngrok:"
    Write-Host "  winget install ngrok"
    Write-Host "  lub pobierz z https://ngrok.com/download"
    exit 1
}

Write-Host ""
Write-Host "Uruchamiam tunel na porcie 3000..."
Write-Host ""

# Uruchom ngrok w tle i przechwytuj output
$ngrokProcess = Start-Process -FilePath "ngrok" -ArgumentList "http", "3000" -NoNewWindow -PassThru -RedirectStandardOutput "ngrok_output.txt" -RedirectStandardError "ngrok_error.txt"

# Poczekaj chwilę na uruchomienie
Start-Sleep -Seconds 3

# Spróbuj pobrać URL z API ngrok (jeśli dostępne)
try {
    $ngrokApi = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 2
    if ($ngrokApi.tunnels.Count -gt 0) {
        $publicUrl = $ngrokApi.tunnels[0].public_url
        Write-Host "✅ Tunel aktywny!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Publiczny URL: $publicUrl" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Testuj serwer:"
        Write-Host "  python test_server.py $publicUrl" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Zgłoś do Hub:"
        Write-Host "  python submit_to_hub.py $publicUrl/" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Naciśnij Ctrl+C aby zatrzymać ngrok"
        Write-Host "=" * 70
    }
} catch {
    Write-Host "⚠️ Nie można pobrać URL z API ngrok" -ForegroundColor Yellow
    Write-Host "Sprawdź output ngrok w terminalu lub przejdź do http://localhost:4040" -ForegroundColor Yellow
}

# Czekaj na zakończenie
try {
    Wait-Process -Id $ngrokProcess.Id
} catch {
    Write-Host "ngrok zatrzymany"
}
