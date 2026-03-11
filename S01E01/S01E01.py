import json
import csv
import requests
from datetime import datetime
from openai import OpenAI
from typing import List, Dict

# Wczytaj klucze API
with open('secrets.json', 'r', encoding='utf-8') as f:
    secrets = json.load(f)

HUB_API_KEY = secrets.get('hub_api_key')
OPENAI_API_KEY = secrets.get('openai_api_key')

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

def download_people_csv():
    """Pobiera plik people.csv z hubu"""
    url = f"https://hub.ag3nts.org/people.csv?apikey={HUB_API_KEY}"
    response = requests.get(url)
    response.raise_for_status()
    
    with open('people.csv', 'w', encoding='utf-8') as f:
        f.write(response.text)
    print("Pobrano plik people.csv")

def filter_people():
    """Filtruje osoby spełniające kryteria: mężczyźni, 20-40 lat w 2026, urodzeni w Grudziądzu"""
    filtered = []
    current_year = 2026
    
    with open('people.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Sprawdź płeć
            if row['gender'] != 'M':
                continue
            
            # Sprawdź miejsce urodzenia
            if row['birthPlace'] != 'Grudziądz':
                continue
            
            # Sprawdź wiek (20-40 lat w 2026)
            birth_date = datetime.strptime(row['birthDate'], '%Y-%m-%d')
            birth_year = birth_date.year
            age = current_year - birth_year
            
            if 20 <= age <= 40:
                filtered.append({
                    'name': row['name'],
                    'surname': row['surname'],
                    'gender': row['gender'],
                    'born': birth_year,
                    'city': row['birthPlace'],
                    'job': row['job']
                })
    
    print(f"Znaleziono {len(filtered)} osób spełniających kryteria demograficzne")
    return filtered

def tag_jobs_batch(jobs: List[Dict]) -> List[Dict]:
    """Otaguje zawody używając LLM z Structured Output (batch processing)"""
    
    # Przygotuj listę opisów stanowisk z numerami
    job_descriptions = []
    for idx, person in enumerate(jobs):
        job_descriptions.append(f"{idx}: {person['job']}")
    
    jobs_text = "\n".join(job_descriptions)
    
    # Przygotuj prompt z opisami tagów
    prompt = f"""Przeanalizuj poniższe opisy stanowisk pracy i przypisz do każdego odpowiednie tagi z dostępnej listy.

Dostępne tagi:
- IT: Praca związana z technologiami informatycznymi, programowaniem, systemami komputerowymi
- transport: Praca związana z przewozem towarów, logistyką, zarządzaniem transportem
- edukacja: Praca związana z nauczaniem, przekazywaniem wiedzy, kształceniem
- medycyna: Praca związana z opieką zdrowotną, leczeniem, diagnostyką medyczną
- praca z ludźmi: Praca wymagająca bezpośredniego kontaktu z klientami, pacjentami, uczniami
- praca z pojazdami: Praca związana z obsługą, naprawą, prowadzeniem pojazdów
- praca fizyczna: Praca wymagająca wysiłku fizycznego, manualna

Opisy stanowisk (każde zaczyna się od numeru):
{jobs_text}

Przypisz tagi do każdego stanowiska. Zwróć tablicę obiektów, gdzie każdy obiekt ma pole "index" (numer z listy) i pole "tags" (tablica tagów). Jedna osoba może mieć wiele tagów."""

    # JSON Schema dla Structured Output
    response_schema = {
        "type": "object",
        "properties": {
            "job_tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "Numer stanowiska z listy (0, 1, 2, ...)"
                        },
                        "tags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["IT", "transport", "edukacja", "medycyna", "praca z ludźmi", "praca z pojazdami", "praca fizyczna"]
                            },
                            "description": "Lista tagów przypisanych do stanowiska"
                        }
                    },
                    "required": ["index", "tags"]
                },
                "description": "Lista tagów dla każdego stanowiska"
            }
        },
        "required": ["job_tags"]
    }
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Jesteś ekspertem w klasyfikacji zawodów. Przypisujesz tagi do opisów stanowisk pracy. Zawsze zwracasz poprawny JSON zgodny ze schematem."},
                {"role": "user", "content": prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "job_tags_response",
                    "strict": True,
                    "schema": response_schema
                }
            },
            temperature=0.3
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Mapuj tagi z powrotem do osób
        tags_map = {}
        if 'job_tags' in result:
            for item in result['job_tags']:
                tags_map[item['index']] = item['tags']
        
        for idx, person in enumerate(jobs):
            person['tags'] = tags_map.get(idx, [])
        
        print(f"Otagowano {len(jobs)} stanowisk")
        return jobs
        
    except Exception as e:
        print(f"Błąd podczas tagowania: {e}")
        import traceback
        traceback.print_exc()
        # Fallback - spróbuj bez structured output
        return tag_jobs_fallback(jobs)

def tag_jobs_fallback(jobs: List[Dict]) -> List[Dict]:
    """Fallback - tagowanie bez structured output"""
    print("Używam metody fallback...")
    for person in jobs:
        job_lower = person['job'].lower()
        tags = []
        
        # Proste heurystyki
        if any(word in job_lower for word in ['transport', 'logistyk', 'przewoz', 'towar', 'magazyn', 'trasa']):
            tags.append('transport')
        if any(word in job_lower for word in ['komputer', 'program', 'system', 'algorytm', 'technolog', 'it', 'software']):
            tags.append('IT')
        if any(word in job_lower for word in ['naucz', 'edukac', 'uczeń', 'szkoła', 'wiedza']):
            tags.append('edukacja')
        if any(word in job_lower for word in ['zdrow', 'lekarz', 'medycz', 'pacjent', 'diagnoz', 'terapi']):
            tags.append('medycyna')
        if any(word in job_lower for word in ['pojazd', 'samochód', 'kierowca', 'mechanik']):
            tags.append('praca z pojazdami')
        if any(word in job_lower for word in ['fizyczn', 'manualn', 'montaż', 'napraw']):
            tags.append('praca fizyczna')
        if any(word in job_lower for word in ['klient', 'pacjent', 'uczeń', 'ludźmi']):
            tags.append('praca z ludźmi')
        
        person['tags'] = tags if tags else []
    
    return jobs

def filter_transport_people(people: List[Dict]) -> List[Dict]:
    """Filtruje osoby z tagiem transport"""
    transport_people = [p for p in people if 'transport' in p.get('tags', [])]
    print(f"Znaleziono {len(transport_people)} osób pracujących w transporcie")
    return transport_people

def send_answer(people: List[Dict]):
    """Wysyła odpowiedź na hub"""
    # Przygotuj odpowiedź w wymaganym formacie
    answer = []
    for person in people:
        answer.append({
            "name": person['name'],
            "surname": person['surname'],
            "gender": person['gender'],
            "born": person['born'],
            "city": person['city'],
            "tags": person['tags']
        })
    
    payload = {
        "apikey": HUB_API_KEY,
        "task": "people",
        "answer": answer
    }
    
    url = "https://hub.ag3nts.org/verify"
    response = requests.post(url, json=payload)
    response.raise_for_status()
    
    result = response.json()
    print(f"Odpowiedź z hubu: {result}")
    
    # Wyświetl flagę jeśli jest
    if 'flag' in result or 'FLG' in str(result):
        print(f"\n{'='*50}")
        print("FLAGA ZNALEZIONA!")
        print(f"{'='*50}")
        print(result)
        print(f"{'='*50}\n")
    
    return result

def main():
    print("Rozpoczynam zadanie people...")
    
    # Krok 1: Pobierz dane (lub użyj istniejącego pliku)
    try:
        download_people_csv()
    except Exception as e:
        print(f"Nie udało się pobrać pliku (używam istniejącego): {e}")
    
    # Krok 2: Przefiltruj dane
    filtered_people = filter_people()
    
    if not filtered_people:
        print("Nie znaleziono osób spełniających kryteria!")
        return
    
    # Krok 3: Otaguj zawody
    tagged_people = tag_jobs_batch(filtered_people)
    
    # Krok 4: Wybierz osoby z tagiem transport
    transport_people = filter_transport_people(tagged_people)
    
    if not transport_people:
        print("Nie znaleziono osób pracujących w transporcie!")
        return
    
    # Wyświetl wyniki
    print(f"\nZnalezione osoby ({len(transport_people)}):")
    for person in transport_people:
        print(f"  - {person['name']} {person['surname']} ({person['born']}), tagi: {person['tags']}")
    
    # Krok 5: Wyślij odpowiedź
    result = send_answer(transport_people)
    
    print("\nZadanie zakończone!")

if __name__ == "__main__":
    main()
