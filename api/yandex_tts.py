import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("TTS")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"


def synthesize(text: str, output_path: str):
    """
    Генерация WAV-файла через Yandex Speech Kit (API Key)
    """
    logger.info(f"TTS: Generating TTS: {text}")

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}"
    }

    data = {
        "text": text,
        "lang": "ru-RU",
        "voice": "alena",
        "folderId": YANDEX_FOLDER_ID,
        "format": "wav",
        "sampleRateHertz": 8000
    }

    response = requests.post(
        TTS_URL,
        headers=headers,
        data=data,
        timeout=15
    )

    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    logger.info(f"TTS: Audio saved to {output_path}")
