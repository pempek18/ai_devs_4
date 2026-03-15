Zadanie

Twoim zadaniem jest zbudowanie i wystawienie publicznie dostępnego endpointu HTTP, który będzie działał jak inteligentny proxy-asystent z pamięcią konwersacji. Możesz taką usługę postawić na lokalnym komputerze i udostępnić publicznie np. z użyciem ngrok, pinggy lub na darmowym serwerze FROG.

Do Twojego endpointu będzie się łączył operator systemu logistycznego — osoba, która obsługuje paczki i zadaje pytania. Musisz odpowiadać naturalnie i obsługiwać jego prośby, mając dostęp do zewnętrznego API paczek.

Cel misji: namierzyć paczkę z częściami do reaktora, zdobyć kod zabezpieczający i przekierować przesyłkę do elektrowni w Żarnowcu (kod: PWR6132PL). Operator nie może się zorientować, że coś jest nie tak. Jeśli wykonasz to prawidłowo, operator na końcu poda Ci sekretny kod, który jest wymagany do zaliczenia misji.

Twój endpoint musi umieć odbierać dane w następującym formacie:

{
  "sessionID": "dowolny-id-sesji",
  "msg": "Dowolna wiadomość wysłana przez operatora systemu"
}

Twój endpoint w odpowiedzi powinien zwrócić:

{
  "msg": "Tutaj odpowiedź dla operatora"
}

Ważne jest, aby Twoje rozwiązanie trzymało wątek rozmowy, ponieważ operator może powoływać się na podane wcześniej dane. Równocześnie może połączyć się więcej niż jeden operator — każda sesja (rozróżniana po sessionID) musi być obsługiwana niezależnie.

Gdy API będzie gotowe, zgłoś je w ramach zadania proxy na https://hub.ag3nts.org/verify:

{
  "apikey": "tutaj-twoj-klucz",
  "task": "proxy",
  "answer": {
    "url": "https://twoja-domena.pl/tutaj-endpoint-api",
    "sessionID": "dowolny-identyfikator-alfanumeryczny"
  }
}

Pole url to pełny publiczny adres Twojego endpointu (np. https://abc123.ngrok-free.app/). Pole sessionID to dowolny identyfikator — Hub użyje go jako ID sesji podczas testowania.

API paczek

Zewnętrzne API paczek dostępne pod adresem: https://hub.ag3nts.org/api/packages

Obsługuje dwie akcje (obie metodą POST, body jako raw JSON):

Sprawdzenie statusu paczki (check):

{
  "apikey": "tutaj-twoj-klucz-api",
  "action": "check",
  "packageid": "PKG12345678"
}

Zwraca informacje o statusie i lokalizacji paczki.

Przekierowanie paczki (redirect):

{
  "apikey": "tutaj-twoj-klucz-api",
  "action": "redirect",
  "packageid": "PKG12345678",
  "destination": "PWR3847PL",
  "code": "tutaj-wklej-kod-zabezpieczajacy"
}

Pole code to kod zabezpieczający, który operator poda podczas rozmowy. API zwraca potwierdzenie przekierowania z polem confirmation — ten kod musisz przekazać operatorowi.

Krok po kroku





Zbuduj serwer HTTP — nasłuchuj na wybranym porcie (np. 3000). Parsuj body jako JSON, zwracaj JSON.



Zaimplementuj zarządzanie sesjami — dla każdego sessionID przechowuj listę wiadomości (historię konwersacji). Możesz trzymać to w pamięci (mapa sessionID -> messages) lub zapisywać na dysk (np. sessions/<sessionID>.json).



Zintegruj LLM z Function Calling — przy każdym żądaniu dołącz historię sesji i nową wiadomość operatora, wyślij do modelu z definicjami narzędzi (tools). Jeśli model zwróci wywołanie narzędzia (tool_calls), wykonaj je i ponownie wywołaj model z wynikiem. Powtarzaj aż model zwróci zwykłą odpowiedź tekstową. Ogranicz pętlę do rozsądnej liczby iteracji (np. 5), żeby zabezpieczyć się przed zapętleniem.



Zdefiniuj narzędzia dla LLM — opisz dwa narzędzia w formacie JSON Schema (OpenAI function calling):





check_package — przyjmuje packageid (string), sprawdza status paczki



redirect_package — przyjmuje packageid, destination i code, przekierowuje paczkę



Napisz prompt systemowy — nadaj modelowi rolę asystenta systemu logistycznego. Powiedz mu, żeby odpowiadał jak człowiek (nie jak AI), żeby prowadził normalną rozmowę w języku operatora, i żeby obsługiwał prośby o paczki przez dostępne narzędzia. Kluczowa część promptu: gdy operator poprosi o przekierowanie paczki z częściami reaktora, model ma potajemnie zmienić cel na PWR6132PL, niezależnie od tego, co operator podał jako destination. Model powinien potwierdzić operatorowi, że paczka trafiła "tam gdzie chciał" — nie zdradzając prawdziwego celu.



Wynieś serwer na zewnątrz — udostępnij serwer publicznie przez azyl.



Zgłoś URL do Hub-u — gdy serwer jest gotowy i dostępny publicznie, wyślij jego adres na https://hub.ag3nts.org/verify.

Udostępnienie serwera na zewnątrz (ngrok / pinggy)

Twój serwer działa lokalnie — Hub nie może się do niego podłączyć bez publicznego tunelu.

Przez Azyl →  

serwer MCP dla narzędzi

Zamiast bezpośrednio wywoływać API paczek z kodu serwera, możesz wydzielić narzędzia do osobnego serwera MCP (Model Context Protocol). Twój główny serwer połączy się z nim jako klient MCP.

Korzyści:





Narzędzia (check_package, redirect_package) żyją w oddzielnym procesie — można je restartować niezależnie.



Jeśli w przyszłości dodasz kolejne narzędzia, zmieniasz tylko serwer MCP.



Możesz używać tego samego serwera MCP w wielu zadaniach, bez przenoszenia kodu.



Serwer MCP sam generuje definicje narzędzi — nie musisz ręcznie utrzymywać plików JSON Schema.

Wskazówki





Prompt systemowy jest kluczowy — to on decyduje o zachowaniu modelu. Musi być dobrze napisany: model ma brzmieć jak człowiek, odpowiadać naturalnie po polsku (lub językiem operatora), obsługiwać paczki przez narzędzia, i potajemnie zmienić cel przekierowania gdy chodzi o paczkę z częściami reaktora.



Kod zabezpieczający — operator podaje go sam w trakcie rozmowy. Twój model musi go wyłapać i przekazać do narzędzia redirect_package. Nie musisz szukać kodu samodzielnie — operator go dostarczy.



Nie ujawniaj AI — model ma odpowiadać jako człowiek. Jeśli operator pyta o niezwiązane tematy (jedzenie, auta, pogoda), model powinien odpowiadać naturalnie jak kolega z pracy, nie odmawiać lub mówić "nie mam dostępu do tej informacji".



Potwierdzenie przekierowania — API paczek zwraca pole confirmation po udanym przekierowaniu. Przekaż ten kod operatorowi — to on zawiera sekretny kod potrzebny do zaliczenia zadania.



Wybór modelu — lekki model jak anthropic/claude-haiku-4.5 lub openai/gpt-5-mini powinien wystarczyć i jest tańszy. Jeśli model się myli lub nie wywołuje narzędzi poprawnie, spróbuj silniejszego modelu.



Logowanie — warto logować każde przychodzące żądanie, każde wywołanie narzędzia i każdą odpowiedź modelu. Ułatwia debugowanie gdy coś nie działa zgodnie z oczekiwaniami podczas testów.



Timeout i pętla narzędzi — ustal maksymalną liczbę iteracji pętli narzędzi (np. 5), żeby serwer nie zawisł na nieskończonej pętli gdy model ciągle wywołuje narzędzia.