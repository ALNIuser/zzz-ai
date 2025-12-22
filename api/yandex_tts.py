import os
import wave
import requests
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")


def synthesize_pcm(text: str, timeout: int = 30) -> bytes:
    """
    Yandex TTS: возвращает PCM s16le mono 8000 Hz (lpcm).
    """
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        raise RuntimeError("YANDEX_API_KEY / YANDEX_FOLDER_ID not set")

    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    params = {
        "text": text,
        "lang": "ru-RU",
        "voice": "oksana",
        "folderId": YANDEX_FOLDER_ID,
        "format": "lpcm",
        "sampleRateHertz": "8000",
    }

    r = requests.post(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    return r.content


def synthesize_wav(text: str, wav_path: str, timeout: int = 30) -> str:
    """
    Утилита: TTS -> WAV (PCM s16le mono 8000).
    """
    pcm = synthesize_pcm(text, timeout=timeout)

    os.makedirs(os.path.dirname(wav_path) or ".", exist_ok=True)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # 16-bit
        wf.setframerate(8000)
        wf.writeframes(pcm)

    return wav_path
