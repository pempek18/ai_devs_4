Zadanie

Musisz namierzyć, która z podejrzanych osób z poprzedniego zadania przebywała blisko jednej z elektrowni atomowych. Musisz także ustalić jej poziom dostępu oraz informację koło której elektrowni widziano tę osobę. Zebrane tak dane prześlij do /verify. Nazwa zadania to findhim.

Skąd wziąć dane?





Lista elektrowni + ich kody





Pobierz JSON z listą elektrowni (wraz z kodami identyfikacyjnymi) z:





https://hub.ag3nts.org/data/tutaj-twój-klucz/findhim_locations.json



Gdzie widziano konkretną osobę (lokalizacje)





Endpoint: https://hub.ag3nts.org/api/location



Metoda: POST



Body: raw JSON (nie form-data!)



Zawsze wysyłasz pole apikey oraz dane osoby (name, surname)



Odpowiedź: lista współrzędnych (koordynatów), w których daną osobę widziano.

Przykładowy payload:

{
  "apikey": "tutaj-twój-klucz",
  "name": "Jan",
  "surname": "Kowalski"
}



Jaki poziom dostępu ma wskazana osoba





Endpoint: https://hub.ag3nts.org/api/accesslevel



Metoda: POST



Body: raw JSON



Wymagane: apikey, name, surname oraz birthYear (rok urodzenia bierzesz z danych z poprzedniego zadania, np. z CSV)

Przykładowy payload:

{
  "apikey": "tutaj-twój-klucz",
  "name": "Jan",
  "surname": "Kowalski",
  "birthYear": 1987
}

Co masz zrobić krok po kroku?

Dla każdej podejrzanej osoby:





Pobierz listę jej lokalizacji z /api/location.



Porównaj otrzymane koordynaty z koordynatami elektrowni z findhim_locations.json.



Jeśli lokalizacja jest bardzo blisko jednej z elektrowni — masz kandydata.



Dla tej osoby pobierz accessLevel z /api/accesslevel.



Zidentyfikuj kod elektrowni (format: PWR0000PL) i przygotuj raport.

Jak wysłać odpowiedź?

Wysyłasz ją metodą POST na https://hub.ag3nts.org/verify.

Nazwa zadania to: findhim.

Pole answer to pojedynczy obiekt zawierający:





name – imię podejrzanego



surname – nazwisko podejrzanego



accessLevel – poziom dostępu z /api/accesslevel



powerPlant – kod elektrowni z findhim_locations.json (np. PWR1234PL)

Przykład JSON do wysłania na /verify:

{
  "apikey": "tutaj-twój-klucz",
  "task": "findhim",
  "answer": {
    "name": "Jan",
    "surname": "Kowalski",
    "accessLevel": 3,
    "powerPlant": "PWR1234PL"
  }
}

Nagroda

Jeśli Twoja odpowiedź będzie poprawna, Hub odeśle Ci flagę w formacie {FLG:JAKIES_SLOWO} - flagę należy wpisać pod adresem: https://hub.ag3nts.org/ (wejdź na tą stronę w swojej przeglądarce, zaloguj się kontem którym robiłeś zakup kursu i wpisz flagę w odpowiednie pole na stronie).

Wskazówki





Dane wejściowe z poprzedniego zadania — lista podejrzanych pochodzi z zadania S01E01. Potrzebujesz imienia, nazwiska i roku urodzenia każdej osoby — warto zachować wynik S01E01 w formie nadającej się do ponownego użycia. Pamiętaj że chodzi tylko o osoby które wysyłałeś jako podejrzanych do Hubu.



Obliczanie odległości geograficznej — API zwraca współrzędne (latitude/longitude). Żeby sprawdzić, czy dana lokalizacja jest "bardzo blisko" elektrowni, użyj wzoru na odległość na kuli ziemskiej (np. Haversine). LLM pomoże Ci w napisaniu takiej funkcji. Szukamy osoby która była najbliżej którejś elektrowni.



Wykorzystaj Function Calling — to technika, w której model LLM zamiast odpowiadać tekstem wywołuje zdefiniowane przez Ciebie funkcje (narzędzia). Opisujesz narzędzia w formacie JSON Schema (nazwa, opis, parametry), a model sam decyduje, które wywołać i z jakimi argumentami. Ty obsługujesz wywołania i zwracasz wyniki z powrotem do modelu. W tym zadaniu Function Calling sprawdza się szczególnie dobrze: agent może samodzielnie iterować przez listę podejrzanych, odpytywać kolejne endpointy i wysłać gotową odpowiedź — bez sztywnego kodowania kolejności kroków w kodzie.



Format birthYear — endpoint /api/accesslevel oczekuje roku urodzenia jako liczby całkowitej (np. 1987). Jeśli Twoje dane zawierają pełną datę (np. "1987-08-07"), pamiętaj o wyciągnięciu samego roku przed wysłaniem żądania.



Zabezpieczenie pętli agenta — jeśli stosujesz podejście agentowe z Function Calling, ustal maksymalną liczbę iteracji (np. 10-15), żeby uchronić się przed nieskończoną pętlą w razie błędu modelu.



Wybór modelu - jeśli Twój agent myli się lub pracuje w kółko nie podając prawidłowej odpowiedzi, spróbuj użyć mocniejszego modelu lub lepiej sformułować prompt systemowy. W tym zadaniu dobrze sprawdza się na przykład model gpt-5-mini lub jego mocniejsza wersja gpt-5.



Jak znaleźć lokalizację elektrowni? - ponieważ dane z zadania nie precyzują lokalizacji elektrowni jako współrzędne, możesz podejść do tego od kilku stron:

- spróbować przekształcić lokalizacje w orientacyjne współrzędne (większość topowych LLMów to ogarnie)

- spróbuj przekształcić współrzędne, pod którymi byli użytkownicy w nazwy miejsc (jak wyżej - wybrane są dość znane lokalizacje).

- własna metoda?