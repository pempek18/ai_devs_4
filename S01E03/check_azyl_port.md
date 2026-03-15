# Sprawdzanie portu na Azyl

## 1. Zaloguj się przez SSH

```bash
ssh agent11364@azyl.ag3nts.org -p 5022
```

## 2. Sprawdź czy port nasłuchuje

### Sprawdź czy port jest otwarty:
```bash
# Sprawdź czy port 51364 nasłuchuje
netstat -tuln | grep 51364

# Lub użyj ss (nowsze systemy)
ss -tuln | grep 51364

# Lub sprawdź wszystkie porty
netstat -tuln
```

### Sprawdź procesy nasłuchujące:
```bash
# Znajdź procesy na porcie 51364
lsof -i :51364

# Lub
fuser 51364/tcp
```

## 3. Przetestuj połączenie lokalnie na Azyl

```bash
# Test HTTP na porcie 51364
curl http://localhost:51364/health

# Lub
curl http://127.0.0.1:51364/health

# Test głównego endpointu
curl -X POST http://localhost:51364/ \
  -H "Content-Type: application/json" \
  -d '{"sessionID":"test","msg":"test"}'
```

## 4. Sprawdź zewnętrzny dostęp

```bash
# Sprawdź czy port jest dostępny z zewnątrz
curl https://azyl-51364.ag3nts.org/health

# Lub
curl http://azyl-51364.ag3nts.org/health
```

## 5. Sprawdź logi SSH/tunelu

```bash
# Sprawdź aktywne połączenia SSH
ps aux | grep ssh

# Sprawdź logi systemowe (jeśli masz dostęp)
tail -f /var/log/auth.log  # Linux
# lub
journalctl -u ssh  # systemd
```

## 6. Sprawdź firewall

```bash
# Sprawdź reguły firewall (jeśli masz dostęp)
iptables -L -n | grep 51364

# Lub
ufw status | grep 51364
```

## 7. Diagnostyka połączenia

```bash
# Sprawdź czy port odpowiada
nc -zv localhost 51364

# Lub
telnet localhost 51364
```

## 8. Sprawdź status tunelu SSH reverse

Jeśli tunel jest aktywny, powinieneś zobaczyć:
- W procesach: proces SSH z opcją `-R`
- W netstat: port 51364 w stanie LISTEN

## Przykładowy output

### Jeśli port jest otwarty:
```bash
$ netstat -tuln | grep 51364
tcp        0      0 127.0.0.1:51364         0.0.0.0:*               LISTEN
```

### Jeśli port nie jest otwarty:
```bash
$ netstat -tuln | grep 51364
(nic nie zwraca)
```

## Troubleshooting

### Port nie nasłuchuje:
1. Sprawdź czy tunel SSH jest aktywny na Twoim lokalnym komputerze
2. Sprawdź czy lokalny serwer działa na porcie 3000
3. Sprawdź czy komenda SSH była poprawna: `ssh -R 51364:localhost:3000 ...`

### Port nasłuchuje, ale nie odpowiada:
1. Sprawdź czy lokalny serwer działa: `curl http://localhost:3000/health`
2. Sprawdź logi serwera Flask
3. Sprawdź czy MCP server działa

### Port nasłuchuje tylko na localhost:
- To jest normalne dla SSH reverse tunnel
- Port powinien być dostępny przez publiczny URL (azyl-51364.ag3nts.org)
