Wiemy, że do organizacji transportów między elektrowniami angażowani są ludzie, którzy:





są mężczyznami, którzy teraz w 2026 roku mająmiędzy 20, a 40 lat



urodzonych w Grudziądzu



pracują w branży transportowej

Każdą z potencjalnych osób musisz odpowiednio otagować. Mamy do dyspozycji następujące tagi:





IT



transport



edukacja



medycyna



praca z ludźmi



praca z pojazdami



praca fizyczna

Jedna osoba może mieć wiele tagów. Nas interesują tylko ludzie pracujący w transporcie, którzy spełniają też poprzednie warunki.

Prześlij nam listę osób, którymi powinniśmy się zainteresować. Oczekujemy formatu odpowiedzi jak poniżej, wysłanego na adres https://hub.ag3nts.org/verify

Nazwa zadania to: people.

{
       "apikey": "tutaj-twój-klucz-api",
       "task": "people",
       "answer": [
         {
           "name": "Jan",
           "surname": "Kowalski",
           "gender": "M",
           "born": 1987,
           "city": "Warszawa",
           "tags": ["tag1", "tag2"]
         },
         {
           "name": "Anna",
           "surname": "Nowak",
           "gender": "F",
           "born": 1993,
           "city": "Grudziądz",
           "tags": ["tagA", "tagB", "tagC"]
         }
       ]
     }

Co należy zrobić w zadaniu?





Pobierz dane z hubu - plik people.csv dostępny pod linkiem z treści zadania (wstaw swój klucz API z https://hub.ag3nts.org/). Plik zawiera dane osobowe wraz z opisem stanowiska pracy (job).



Przefiltruj dane - zostaw wyłącznie osoby spełniające wszystkie kryteria: płeć, miejsce urodzenia, wiek.



Otaguj zawody modelem językowym - wyślij opisy stanowisk (job) do LLM i poproś o przypisanie tagów z listy dostępnej w zadaniu. Użyj mechanizmu Structured Output, aby wymusić odpowiedź modelu w określonym formacie JSON. Szczegóły we Wskazówkach.



Wybierz osoby z tagiem transport - z otagowanych rekordów wybierz wyłącznie te z tagiem transport.



Wyślij odpowiedź - prześlij tablicę obiektów na adres https://hub.ag3nts.org/verify w formacie pokazanym powyżej (nazwa zadania: people).



Zdobycie flagi - jeśli wysłane dane będą poprawne, Hub w odpowiedzi odeśle flagę w formacie {FLG:JAKIES_SLOWO} - flagę należy wpisać pod adresem: https://hub.ag3nts.org/ (wejdź na tą stronę w swojej przeglądarce, zaloguj się kontem którym robiłeś zakup kursu i wpisz flagę w odpowiednie pole na stronie)

Wskazówki





Structured Output - cel i sposób użycia: Celem zadania jest zastosowanie mechanizmu Structured Output przy klasyfikacji zawodów przez LLM. Polega on na wymuszeniu odpowiedzi modelu w ściśle określonym formacie JSON przez przekazanie schematu (JSON Schema) w polu response_format wywołania API. Zadanie da się rozwiązać bez Structured Output, na przykład prosząc model o zwrócenie JSON-a i parsując go ręcznie - ale Structured Output eliminuje całą klasę błędów. Możesz też użyć bibliotek jak Instructor (Python/JS/TypeScript), które obsługują ten mechanizm za Ciebie.



Batch tagging - jedno wywołanie dla wielu rekordów: Zamiast wywoływać LLM osobno dla każdej osoby, możesz na przykład wysłać w jednym żądaniu ponumerowaną listę opisów stanowisk i poprosić o zwrócenie listy obiektów z numerem rekordu i przypisanymi tagami. Znacznie zredukuje to liczbę wywołań API.



Opisy tagów pomagają modelowi: Do każdej kategorii dołącz krótki opis zakresu - pomaga to modelowi poprawnie sklasyfikować niejednoznaczne stanowiska.



Format pól w odpowiedzi: Pole born to liczba całkowita (sam rok urodzenia). Pole tags to tablica stringów, nie jeden string z przecinkami.