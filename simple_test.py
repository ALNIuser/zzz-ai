#!/usr/bin/env python3
import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

TEXT = "Здравствуйте. Вы позвонили в техническую поддержку компании СКС сервис, чем мы можем вам помочь?"
OUTPUT = "/tmp/test_phrase.wav"

headers = {"Authorization": f"Api-Key {os.getenv('YANDEX_API_KEY')}"}
params = {
    "text": TEXT,
    "lang": "ru-RU",
    "voice": "filipp",
    "folderId": os.getenv('YANDEX_FOLDER_ID'),
    "format": "wav",
    "sampleRateHertz": 8000
}

print("Синтез текста...")
response = requests.post(
    "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
    headers=headers,
    params=params
)

if response.status_code == 200:
    with open(OUTPUT, 'wb') as f:
        f.write(response.content)
    size = os.path.getsize(OUTPUT)
    print(f"Создан: {OUTPUT}")
    print(f"Размер: {size} байт")
    print(f"\nВоспроизвести: aplay {OUTPUT}")
else:
    print(f"Ошибка {response.status_code}: {response.text[:200]}")
