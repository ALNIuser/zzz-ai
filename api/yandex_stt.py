import os
import requests
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")


def recognize_pcm(pcm_s16le: bytes, sample_rate: int = 8000, timeout: int = 30) -> str:
    """
    Yandex STT recognize: принимает raw PCM s16le mono.
    Возвращает текст или пустую строку.
    """
    if not YANDEX_API_KEY:
        raise RuntimeError("YANDEX_API_KEY not set")

    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    params = {
        "lang": "ru-RU",
        "format": "lpcm",
        "sampleRateHertz": str(sample_rate),
    }

    r = requests.post(url, headers=headers, params=params, data=pcm_s16le, timeout=timeout)

    if r.status_code != 200:
        # Не прячем причину (403/401 и т.п.)
        raise RuntimeError(f"Yandex STT HTTP {r.status_code}: {r.text[:400]}")

    data = r.json()
    return (data.get("result") or "").strip()
