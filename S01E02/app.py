import os
import csv
import requests
import json
import math
from datetime import datetime
from openai import OpenAI
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Wczytaj klucze API z pliku .env
load_dotenv()

HUB_API_KEY = os.getenv('HUB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# Globalne zmienne
suspicious_people: List[Dict] = []
power_plants: List[Dict] = []
found_person: Optional[Dict] = None


def load_suspicious_people() -> List[Dict]:
    """Ładuje listę podejrzanych osób z wyniku zadania S01E01 (people.json)"""
    # Ścieżka do pliku people.json
    json_paths = [
        '../S01E01/people.json',
        'S01E01/people.json',
        'people.json'
    ]
    
    json_path = None
    for path in json_paths:
        if os.path.exists(path):
            json_path = path
            break
    
    if not json_path:
        raise FileNotFoundError("Nie znaleziono pliku people.json z wynikami zadania S01E01")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        people = json.load(f)
    
    # Upewnij się, że mamy tylko potrzebne pola (name, surname, born)
    result = []
    for person in people:
        result.append({
            'name': person['name'],
            'surname': person['surname'],
            'born': person['born']
        })
    
    print(f"Załadowano {len(result)} podejrzanych osób z wyniku zadania S01E01")
    return result


def get_city_coordinates() -> Dict[str, Dict[str, float]]:
    """Zwraca mapowanie nazw miast na współrzędne geograficzne"""
    return {
        "Zabrze": {"latitude": 50.3249, "longitude": 18.7857},
        "Piotrków Trybunalski": {"latitude": 51.4054, "longitude": 19.7032},
        "Grudziądz": {"latitude": 53.4874, "longitude": 18.7544},
        "Tczew": {"latitude": 54.0924, "longitude": 18.7774},
        "Radom": {"latitude": 51.4025, "longitude": 21.1471},
        "Chelmno": {"latitude": 53.3486, "longitude": 18.4251},
        "Żarnowiec": {"latitude": 54.7500, "longitude": 18.0833}
    }


def get_power_plants() -> List[Dict]:
    """Pobiera listę elektrowni z JSON, dodaje współrzędne i zapisuje do pliku"""
    url = f"https://hub.ag3nts.org/data/{HUB_API_KEY}/findhim_locations.json"
    response = requests.get(url)
    response.raise_for_status()
    plants_data = response.json()
    
    # Struktura z API: {"power_plants": {"Zabrze": {...}, "Piotrków Trybunalski": {...}, ...}}
    # Przekształć na listę obiektów z współrzędnymi
    city_coords = get_city_coordinates()
    plants = []
    
    # Sprawdź różne możliwe struktury danych
    cities_dict = None
    
    if isinstance(plants_data, dict):
        # Sprawdź czy jest klucz "power_plants"
        if 'power_plants' in plants_data:
            cities_dict = plants_data['power_plants']
        else:
            # Może być bezpośrednio słownik z miastami
            cities_dict = plants_data
    elif isinstance(plants_data, list) and len(plants_data) > 0:
        # Jeśli to lista, sprawdź pierwszy element
        first_item = plants_data[0]
        if isinstance(first_item, dict):
            if 'power_plants' in first_item:
                cities_dict = first_item['power_plants']
            else:
                cities_dict = first_item
    
    # Przetwórz miasta na listę elektrowni
    if cities_dict and isinstance(cities_dict, dict):
        for city_name, plant_info in cities_dict.items():
            if isinstance(plant_info, dict):
                coords = city_coords.get(city_name, {})
                plant = {
                    'name': city_name,
                    'code': plant_info.get('code'),
                    'power': plant_info.get('power'),
                    'is_active': plant_info.get('is_active'),
                    'latitude': coords.get('latitude'),
                    'longitude': coords.get('longitude')
                }
                plants.append(plant)
    
    # Zapisz do pliku JSON
    output_file = 'S01E02/power_plants.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(plants, f, indent=2, ensure_ascii=False)
    
    print(f"Pobrano {len(plants)} elektrowni i zapisano do {output_file}")
    if len(plants) > 0:
        print(f"Przykładowa elektrownia: {plants[0]['name']} ({plants[0]['code']}) - lat: {plants[0]['latitude']}, lon: {plants[0]['longitude']}")
    return plants


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Oblicza odległość między dwoma punktami na kuli ziemskiej (w km) używając wzoru Haversine"""
    R = 6371  # Promień Ziemi w km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c
    
    return distance


def get_person_locations(name: str, surname: str) -> List[Dict]:
    """Pobiera lokalizacje osoby z API"""
    url = "https://hub.ag3nts.org/api/location"
    payload = {
        "apikey": HUB_API_KEY,
        "name": name,
        "surname": surname
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    locations = response.json()
    with open('S01E02/locations.json', 'w', encoding='utf-8') as f:
        json.dump(locations, f, indent=2, ensure_ascii=False)
    print(f"Zapisano {len(locations)} lokalizacji dla {name} {surname} do pliku S01E02/locations.json")
    return locations


def get_person_access_level(name: str, surname: str, birth_year: int) -> int:
    """Pobiera poziom dostępu osoby z API"""
    url = "https://hub.ag3nts.org/api/accesslevel"
    payload = {
        "apikey": HUB_API_KEY,
        "name": name,
        "surname": surname,
        "birthYear": birth_year
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    return result.get('accessLevel', 0)


def find_closest_power_plant(lat: float, lon: float, threshold_km: float = None) -> Optional[Dict]:
    """Znajduje najbliższą elektrownię dla danej lokalizacji (zawsze zwraca najbliższą, nawet jeśli daleko)"""
    min_distance = float('inf')
    closest_plant = None
    
    if not power_plants or len(power_plants) == 0:
        return None
    
    for plant in power_plants:
        # Pobierz współrzędne - teraz powinny być bezpośrednio w obiekcie plant
        plant_lat = plant.get('latitude')
        plant_lon = plant.get('longitude')
        
        # Jeśli nie ma współrzędnych, spróbuj znaleźć po nazwie miasta
        if plant_lat is None or plant_lon is None:
            city_name = plant.get('name')
            if city_name:
                city_coords = get_city_coordinates().get(city_name, {})
                plant_lat = city_coords.get('latitude')
                plant_lon = city_coords.get('longitude')
        
        if plant_lat is None or plant_lon is None:
            # Pomijamy elektrownie bez współrzędnych
            continue
        
        distance = haversine_distance(lat, lon, plant_lat, plant_lon)
        
        # ZAWSZE znajdź najbliższą, bez względu na odległość
        # Jeśli threshold jest None, zawsze zapisuj najbliższą
        # Jeśli threshold jest ustawiony, zapisuj tylko jeśli w progu
        if threshold_km is None:
            # Bez progu - zawsze znajdź najbliższą
            if distance < min_distance:
                min_distance = distance
                closest_plant = {
                    'code': plant.get('code'),
                    'name': plant.get('name'),
                    'distance_km': distance,
                    'latitude': plant_lat,
                    'longitude': plant_lon
                }
        else:
            # Z progiem - tylko jeśli w progu
            if distance < min_distance and distance <= threshold_km:
                min_distance = distance
                closest_plant = {
                    'code': plant.get('code'),
                    'name': plant.get('name'),
                    'distance_km': distance,
                    'latitude': plant_lat,
                    'longitude': plant_lon
                }
    
    return closest_plant


def submit_answer(name: str, surname: str, access_level: int, power_plant_code: str) -> Dict:
    """Wysyła odpowiedź na endpoint /verify"""
    url = "https://hub.ag3nts.org/verify"
    payload = {
        "apikey": HUB_API_KEY,
        "task": "findhim",
        "answer": {
            "name": name,
            "surname": surname,
            "accessLevel": access_level,
            "powerPlant": power_plant_code
        }
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    return result


# Funkcje dla Function Calling
def create_function_tools():
    """Tworzy listę narzędzi (funkcji) dla Function Calling"""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_person_locations",
                "description": "Pobiera listę lokalizacji (współrzędnych), w których widziano daną osobę",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Imię osoby"
                        },
                        "surname": {
                            "type": "string",
                            "description": "Nazwisko osoby"
                        }
                    },
                    "required": ["name", "surname"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_person_access_level",
                "description": "Pobiera poziom dostępu osoby do elektrowni atomowych",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Imię osoby"
                        },
                        "surname": {
                            "type": "string",
                            "description": "Nazwisko osoby"
                        },
                        "birth_year": {
                            "type": "integer",
                            "description": "Rok urodzenia osoby"
                        }
                    },
                    "required": ["name", "surname", "birth_year"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_location_near_power_plant",
                "description": "Sprawdza czy dana lokalizacja (współrzędne) jest blisko którejś z elektrowni atomowych. ZAWSZE zwraca najbliższą elektrownię, nawet jeśli jest daleko. Użyj tej funkcji dla każdej lokalizacji, aby znaleźć osobę która była NAJBLIŻEJ elektrowni.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Szerokość geograficzna lokalizacji"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Długość geograficzna lokalizacji"
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "submit_final_answer",
                "description": "Wysyła finalną odpowiedź z danymi znalezionej osoby (użyj tylko gdy masz wszystkie dane: imię, nazwisko, poziom dostępu i kod elektrowni)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Imię podejrzanego"
                        },
                        "surname": {
                            "type": "string",
                            "description": "Nazwisko podejrzanego"
                        },
                        "access_level": {
                            "type": "integer",
                            "description": "Poziom dostępu z API"
                        },
                        "power_plant_code": {
                            "type": "string",
                            "description": "Kod elektrowni (np. PWR1234PL)"
                        }
                    },
                    "required": ["name", "surname", "access_level", "power_plant_code"]
                }
            }
        }
    ]


def handle_function_call(function_name: str, arguments: dict) -> str:
    """Obsługuje wywołania funkcji z Function Calling"""
    global found_person
    
    if function_name == "get_person_locations":
        name = arguments.get("name")
        surname = arguments.get("surname")
        locations = get_person_locations(name, surname)
        return json.dumps({"locations": locations, "count": len(locations)})
    
    elif function_name == "get_person_access_level":
        name = arguments.get("name")
        surname = arguments.get("surname")
        birth_year = arguments.get("birth_year")
        access_level = get_person_access_level(name, surname, birth_year)
        return json.dumps({"accessLevel": access_level})
    
    elif function_name == "check_location_near_power_plant":
        lat = arguments.get("latitude")
        lon = arguments.get("longitude")
        
        # Sprawdź czy power_plants jest załadowane
        if not power_plants or len(power_plants) == 0:
            return json.dumps({
                "error": "Brak danych o elektrowniach",
                "note": "Lista elektrowni nie została załadowana"
            })
        
        # Zawsze znajdź najbliższą elektrownię (bez progu odległości)
        closest = find_closest_power_plant(lat, lon, threshold_km=None)
        
        if closest:
            # Uznaj za "blisko" jeśli < 50km, ale zawsze zwróć najbliższą
            is_near = closest['distance_km'] <= 50.0
            return json.dumps({
                "near_power_plant": is_near,
                "power_plant_code": closest['code'],
                "power_plant_name": closest.get('name', 'Unknown'),
                "distance_km": round(closest['distance_km'], 2),
                "latitude": closest.get('latitude'),
                "longitude": closest.get('longitude'),
                "note": "Zawsze zwracana jest najbliższa elektrownia, nawet jeśli jest daleko. Porównaj distance_km dla wszystkich lokalizacji i wybierz tę z najmniejszą wartością."
            })
        else:
            return json.dumps({
                "near_power_plant": False,
                "error": "Nie znaleziono najbliższej elektrowni",
                "note": "Sprawdź czy lista elektrowni jest poprawnie załadowana"
            })
    
    elif function_name == "submit_final_answer":
        name = arguments.get("name")
        surname = arguments.get("surname")
        access_level = arguments.get("access_level")
        power_plant_code = arguments.get("power_plant_code")
        result = submit_answer(name, surname, access_level, power_plant_code)
        found_person = {
            "name": name,
            "surname": surname,
            "accessLevel": access_level,
            "powerPlant": power_plant_code
        }
        return json.dumps({"result": result, "status": "submitted"})
    
    return json.dumps({"error": f"Unknown function: {function_name}"})


def run_agent():
    """Uruchamia agenta z Function Calling do znalezienia osoby blisko elektrowni"""
    global suspicious_people, power_plants
    
    # Przygotuj listę osób dla agenta
    people_list = "\n".join([
        f"- {p['name']} {p['surname']} (ur. {p['born']})"
        for p in suspicious_people
    ])
    
    # Przygotuj listę elektrowni dla agenta
    # Upewnij się, że power_plants jest listą
    if not isinstance(power_plants, list):
        power_plants = list(power_plants) if power_plants else []
    
    plants_list = "\n".join([
        f"- {p.get('code', 'N/A')}: {p.get('name', 'Unknown')}"
        for p in (power_plants[:10] if len(power_plants) > 10 else power_plants)  # Pokaż pierwsze 10 jako przykład
    ])
    
    system_prompt = f"""Jesteś agentem śledczym, który ma znaleźć osobę z listy podejrzanych, która przebywała blisko jednej z elektrowni atomowych.

Lista podejrzanych osób (z zadania S01E01):
{people_list}

Lista elektrowni atomowych (przykładowe, pełna lista jest dostępna w systemie):
{plants_list}

Twoje zadanie:
1. Dla każdej osoby z listy podejrzanych:
   - Pobierz jej lokalizacje używając funkcji get_person_locations
   - Dla każdej lokalizacji sprawdź czy jest blisko elektrowni używając check_location_near_power_plant
   - Jeśli znajdziesz osobę blisko elektrowni, pobierz jej poziom dostępu używając get_person_access_level
   - Gdy masz wszystkie dane (imię, nazwisko, poziom dostępu, kod elektrowni), wyślij odpowiedź używając submit_final_answer

2. WAŻNE: Szukaj osoby która była NAJBLIŻEJ którejś elektrowni (najmniejsza odległość). Funkcja check_location_near_power_plant ZAWSZE zwraca najbliższą elektrownię, nawet jeśli jest daleko. Porównaj odległości dla wszystkich lokalizacji wszystkich osób i wybierz tę z NAJMNIEJSZĄ odległością.

3. Po znalezieniu osoby z najmniejszą odległością do elektrowni, pobierz jej poziom dostępu i natychmiast wyślij odpowiedź używając submit_final_answer.

4. Bądź systematyczny - sprawdzaj wszystkie lokalizacje wszystkich osób, zapisuj odległości i wybierz najmniejszą.

5. Pamiętaj: endpoint /api/accesslevel wymaga roku urodzenia (birthYear) - masz go w danych osób jako 'born'.

6. Jeśli sprawdziłeś wszystkie osoby i wszystkie ich lokalizacje, wybierz tę z najmniejszą odległością i wyślij odpowiedź."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Rozpocznij poszukiwania. Znajdź osobę, która przebywała blisko elektrowni atomowej i wyślij odpowiedź."}
    ]
    
    tools = create_function_tools()
    max_iterations = 12  # Zmniejszono z 20 do 12
    iteration = 0
    consecutive_no_action = 0  # Licznik iteracji bez wywołań funkcji
    
    print("\n" + "="*60)
    print("Uruchamianie agenta z Function Calling...")
    print("="*60 + "\n")
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteracja {iteration} ---")
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3
            )
            
            message = response.choices[0].message
            
            # Dodaj odpowiedź modelu do historii
            messages.append(message)
            
            # Sprawdź czy model chce wywołać funkcję
            if message.tool_calls:
                print(f"Agent wywołuje {len(message.tool_calls)} funkcji...")
                
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    print(f"  -> {function_name}({json.dumps(function_args, ensure_ascii=False)})")
                    
                    # Wywołaj funkcję
                    function_result = handle_function_call(function_name, function_args)
                    
                    # Dodaj wynik do historii
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_result
                    })
                    
                    print(f"  <- Wynik: {function_result[:200]}...")
                    
                    # Jeśli wysłano odpowiedź, zakończ
                    if function_name == "submit_final_answer":
                        print("\n" + "="*60)
                        print("ODPOWIEDŹ WYSŁANA!")
                        print("="*60)
                        return found_person
            else:
                # Model odpowiedział tekstem
                content = message.content or ""
                print(f"Agent: {content}")
                
                # Jeśli agent mówi że zakończył, sprawdź czy wysłał odpowiedź
                if found_person:
                    return found_person
                
                # Sprawdź czy agent mówi że sprawdził wszystko
                completion_keywords = ["sprawdziłem", "sprawdziłem wszystkie", "żadna", "nie znalazłem", "nie było blisko"]
                if any(keyword in content.lower() for keyword in completion_keywords):
                    consecutive_no_action += 1
                    if consecutive_no_action >= 2:
                        # Agent 2 razy z rzędu mówi że sprawdził wszystko - zakończ
                        print("\n" + "="*60)
                        print("Agent zakończył sprawdzanie, ale nie znalazł osoby lub nie wysłał odpowiedzi.")
                        print("="*60)
                        return None
                    # Pierwszy raz - daj jeszcze jedną szansę z bardziej precyzyjną instrukcją
                    messages.append({
                        "role": "user",
                        "content": "WAŻNE: Funkcja check_location_near_power_plant ZAWSZE zwraca najbliższą elektrownię, nawet jeśli jest daleko. Sprawdź WSZYSTKIE lokalizacje WSZYSTKICH osób, zapisz odległości i wybierz tę z NAJMNIEJSZĄ odległością. Następnie pobierz accessLevel i wyślij odpowiedź."
                    })
                else:
                    consecutive_no_action = 0
                    # Jeśli agent nie wywołuje funkcji i nie mówi że skończył, kontynuuj
                    messages.append({
                        "role": "user",
                        "content": "Kontynuuj poszukiwania. Sprawdź wszystkie lokalizacje wszystkich osób i znajdź tę z najmniejszą odległością do elektrowni."
                    })
        
        except Exception as e:
            print(f"Błąd w iteracji {iteration}: {e}")
            import traceback
            traceback.print_exc()
            break
    
    print(f"\nOsiągnięto maksymalną liczbę iteracji ({max_iterations})")
    return found_person


def main():
    """Główna funkcja aplikacji"""
    global suspicious_people, power_plants
    
    print("="*60)
    print("ZADANIE: findhim - Znajdź osobę blisko elektrowni")
    print("="*60)
    
    try:
        # Krok 1: Załaduj podejrzanych z S01E01
        print("\n[1/3] Ładowanie listy podejrzanych osób...")
        suspicious_people = load_suspicious_people()
        
        if not suspicious_people:
            print("BŁĄD: Nie znaleziono podejrzanych osób!")
            return
        
        print(f"Załadowano {len(suspicious_people)} osób")
        for person in suspicious_people[:5]:  # Pokaż pierwsze 5
            print(f"  - {person['name']} {person['surname']} (ur. {person['born']})")
        if len(suspicious_people) > 5:
            print(f"  ... i {len(suspicious_people) - 5} więcej")
        
        # Krok 2: Pobierz listę elektrowni
        print("\n[2/3] Pobieranie listy elektrowni...")
        power_plants = get_power_plants()
        print(f"Załadowano {len(power_plants)} elektrowni")
        
        # Krok 3: Uruchom agenta
        print("\n[3/3] Uruchamianie agenta...")
        result = run_agent()
        
        if result:
            print("\n" + "="*60)
            print("SUKCES! Znaleziono osobę:")
            print("="*60)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("="*60)
        else:
            print("\nNie udało się znaleźć osoby lub wysłać odpowiedzi.")
    
    except Exception as e:
        print(f"\nBŁĄD: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()