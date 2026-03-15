import os
import csv
import requests
from datetime import datetime
from openai import OpenAI
from typing import List, Dict
from dotenv import load_dotenv

# Wczytaj klucze API z pliku .env
load_dotenv()

HUB_API_KEY = os.getenv('HUB_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)