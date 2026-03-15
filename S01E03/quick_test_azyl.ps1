# Szybki test serwera przez Azyl
# Użycie: .\quick_test_azyl.ps1

$baseUrl = "https://azyl-51364.ag3nts.org"

Write-Host "=" * 70
Write-Host "TEST SERWERA PRZEZ AZYL"
Write-Host "=" * 70
Write-Host "URL: $baseUrl"
Write-Host ""

# Test 1: Health endpoint
Write-Host "1. Test /health..."
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/health" -SkipCertificateCheck -TimeoutSec 5
    Write-Host "   ✅ DZIAŁA! Odpowiedź:" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "   ❌ Błąd: $_" -ForegroundColor Red
}

Write-Host ""

# Test 2: Główny endpoint POST
Write-Host "2. Test POST /..."
try {
    $body = @{
        sessionID = "test-$(Get-Date -Format 'yyyyMMddHHmmss')"
        msg = "Test przez Azyl"
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "$baseUrl/" -Method POST -Body $body -ContentType "application/json" -SkipCertificateCheck -TimeoutSec 30
    Write-Host "   ✅ DZIAŁA! Odpowiedź:" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "   ❌ Błąd: $_" -ForegroundColor Red
    Write-Host "   Szczegóły: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=" * 70
Write-Host "URL do zgłoszenia do Hub:"
Write-Host "$baseUrl/"
Write-Host "=" * 70
