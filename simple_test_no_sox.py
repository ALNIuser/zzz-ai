#!/usr/bin/env python3
"""
simple_test_no_sox.py - Синтез текста с созданием WAV в Python
"""

import os
import sys
import requests
import struct
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
    print("ERROR: Set YANDEX_API_KEY and YANDEX_FOLDER_ID in .env file")
    sys.exit(1)

TEXT = "Здравствуйте. Вы позвонили в техподдержку компании СКС сервис чем мы можем вам помочь?"
OUTPUT_PATH = "/tmp/test_phrase.wav"

print("Synthesizing text...")

# Запрос к Yandex TTS API
url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
params = {
    "text": TEXT,
    "lang": "ru-RU",
    "voice": "oksana",
    "folderId": YANDEX_FOLDER_ID,
    "format": "lpcm",
    "sampleRateHertz": 8000
}

response = requests.post(url, headers=headers, params=params, timeout=30)

if response.status_code == 200:
    # Получаем сырые PCM данные
    pcm_data = response.content
    
    # Создаем WAV-файл
    sample_rate = 8000
    num_channels = 1
    bits_per_sample = 16
    
    # Рассчитываем размер данных
    data_size = len(pcm_data)
    
    # Создаем WAV-заголовок
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',                     # ChunkID
        36 + data_size,              # ChunkSize
        b'WAVE',                     # Format
        b'fmt ',                     # Subchunk1ID
        16,                          # Subchunk1Size
        1,                           # AudioFormat (PCM)
        num_channels,                # NumChannels
        sample_rate,                 # SampleRate
        sample_rate * num_channels * (bits_per_sample // 8),  # ByteRate
        num_channels * (bits_per_sample // 8),  # BlockAlign
        bits_per_sample,             # BitsPerSample
        b'data',                     # Subchunk2ID
        data_size                    # Subchunk2Size
    )
    
    # Сохраняем WAV-файл
    with open(OUTPUT_PATH, 'wb') as f:
        f.write(wav_header)
        f.write(pcm_data)
    
    file_size = os.path.getsize(OUTPUT_PATH)
    print(f"✓ File created: {OUTPUT_PATH}")
    print(f"  Size: {file_size} bytes")
    
    # Проверяем, можно ли воспроизвести
    print(f"\nTo play the file:")
    print(f"  aplay {OUTPUT_PATH}")
    print(f"  or open with any media player")
    
else:
    print(f"✗ Error {response.status_code}: {response.text[:200]}")
