import os
import requests
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

TTS_VOICE = os.getenv("TTS_VOICE", "oksana")


def set_voice(voice: str):
    global TTS_VOICE
    TTS_VOICE = voice


def synthesize_pcm(text: str, timeout: int = 30) -> bytes:
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY / YANDEX_FOLDER_ID not set")

    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    params = {
        "text": text,
        "lang": "ru-RU",
        "voice": TTS_VOICE,
        "folderId": YANDEX_FOLDER_ID,
        "format": "lpcm",
        "sampleRateHertz": "8000",
    }

    r = requests.post(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    return r.content
