#Gość na poziomie stworzył Wallyego i Waldo

import os
import csv
import json
import requests
from datetime import datetime
from openai import OpenAI
from typing import Optional, Dict, List
from dotenv import load_dotenv

# Wczytaj klucze API z pliku .env
load_dotenv()

HUB_API_KEY = os.getenv('HUB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

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
    print(result)
    return result.get('accessLevel', 0)

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
    print(locations)
    return locations

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

if __name__ == "__main__":
    try:
        print(get_person_access_level("Martin", "Handford", 1987))
    except Exception as e:
        print(e)
    try:
        print(get_person_locations("Martin", "Handford"))
    except Exception as e:
        print(e)
    try:
        print(submit_answer("Martin", "Handford", 0, "PWR0000PL"))
    except Exception as e:
        print(e)