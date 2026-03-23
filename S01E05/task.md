Zadanie

Musisz aktywować trasę kolejową o nazwie X-01 za pomocą API, do którego nie mamy dokumentacji. Wiemy tylko, że API obsługuje akcję help, która zwraca jego własną dokumentację — od niej należy zacząć.

Nazwa zadania to railway. Komunikacja odbywa się przez ten sam endpoint co poprzednie zadania. Wszystkie żądania to POST na https://hub.ag3nts.org/verify, body jako raw JSON.

Przykład wywołania akcji help:

{
  "apikey": "tutaj-twoj-klucz",
  "task": "railway",
  "answer": {
    "action": "help"
  }
}

Niestety, tylko tyle udało nam się dowiedzieć na temat funkcjonowania tego systemu. API jest celowo przeciążone i regularnie zwraca błędy 503 (to nie jest prawdziwa awaria, a symulacja), a do tego ma bardzo restrykcyjne limity zapytań. Zadanie wymaga cierpliwości.

Krok po kroku





Zacznij od help — wyślij akcję help i dokładnie przeczytaj odpowiedź. API jest samo-dokumentujące: odpowiedź opisuje wszystkie dostępne akcje, ich parametry i kolejność wywołań potrzebną do aktywacji trasy.



Postępuj zgodnie z dokumentacją API — nie zgaduj nazw akcji ani parametrów. Używaj dokładnie tych wartości, które zwróciło help.



Obsługuj błędy 503 — jeśli API zwróci 503, poczekaj chwilę i spróbuj ponownie. To celowe zachowanie symulujące przeciążenie serwera, nie prawdziwy błąd.



Pilnuj limitów zapytań — sprawdzaj nagłówki HTTP każdej odpowiedzi. Nagłówki informują o czasie resetu limitu. Odczekaj do resetu przed kolejnym wywołaniem.



Szukaj flagi w odpowiedzi — gdy API zwróci w treści odpowiedzi flagę w formacie {FLG:...}, zadanie jest ukończone.

Wskazówki





API jest samo-dokumentujące — nie szukaj dokumentacji gdzie indziej. Odpowiedź na help to wszystko, czego potrzebujesz.



Czytaj błędy uważnie — jeśli akcja się nie powiedzie, komunikat błędu zwykle precyzyjnie wskazuje co poszło nie tak (zły parametr, zła kolejność akcji itp.).



503 to nie awaria — błąd 503 jest częścią zadania. Kod musi go obsługiwać automatycznie przez retry z backoffem, inaczej zadanie nie da się ukończyć.



Limity zapytań są bardzo restrykcyjne — to główne utrudnienie zadania. Monitoruj nagłówki po każdym żądaniu i bezwzględnie respektuj limity. Zbyt agresywne odpytywanie spowoduje długie blokady.



Wybór modelu ma znaczenie — przy restrykcyjnych limitach API liczy się każde zapytanie. Modele, które potrzebują więcej kroków do rozwiązania zadania (lub robią niepotrzebne wywołania API), szybciej wyczerpią limit. Warto przetestować różne modele.



Loguj każde wywołanie i odpowiedź — przy zadaniach z limitami i losowymi błędami dobre logowanie to podstawa debugowania.