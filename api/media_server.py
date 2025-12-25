#!/usr/bin/env python3
import os
import socket
import time
import audioop
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from api.yandex_stt import recognize_pcm
from api.yandex_tts import synthesize_pcm
from api.llm_client import chat

load_dotenv()

# ================== CONFIG ==================
RTP_PORT = int(os.getenv("RTP_PORT", "4000"))
RTP_FORMAT = "ulaw"
SAMPLE_RATE = 8000

FRAME_MS = 20
FRAME_SAMPLES = 160

RMS_SPEECH_THRESHOLD = 250
END_SILENCE_MS = 900
MIN_UTTERANCE_MS = 1000

# ============================================

AVAILABLE_VOICES = {
    "1": "oksana",
    "2": "jane",
    "3": "alena",
    "4": "filipp",
}

print("\nВыберите голос TTS:")
for k, v in AVAILABLE_VOICES.items():
    print(f" {k}. {v}")

VOICE_CHOICE = input("Введите номер голоса: ").strip()
VOICE = AVAILABLE_VOICES.get(VOICE_CHOICE, "oksana")
os.environ["YANDEX_TTS_VOICE"] = VOICE

print(f"\n✅ Используется голос: {VOICE}\n")

executor = ThreadPoolExecutor(max_workers=4)

# ======= Telegram (заготовка) =======
def telegram_escalate(text: str):
    # TODO: отправка в TG (token/chat_id из env)
    print(f"[TG] ЭСКАЛАЦИЯ: {text}")
# ===================================

def ulaw_to_pcm(payload: bytes) -> bytes:
    return audioop.ulaw2lin(payload, 2)

def pcm_to_ulaw(pcm: bytes) -> bytes:
    return audioop.lin2ulaw(pcm, 2)

def build_rtp(seq, ts, ssrc, payload):
    hdr = bytearray(12)
    hdr[0] = 0x80
    hdr[1] = 0x00
    hdr[2:4] = seq.to_bytes(2, "big")
    hdr[4:8] = ts.to_bytes(4, "big")
    hdr[8:12] = ssrc.to_bytes(4, "big")
    return bytes(hdr) + payload

class Session:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr

        self.seq = 0
        self.ts = 0
        self.ssrc = int.from_bytes(os.urandom(4), "big")

        self.buf = bytearray()
        self.in_speech = False
        self.silence_ms = 0

        self.speaking_lock = threading.Lock()
        self.dialog_lock = threading.Lock()

        self.messages = [
            {"role": "system", "content":
             (
                "Ты оператор первой линии техподдержки компании СКС Сервис "
                "(видеонаблюдение, СКУД, пожарная сигнализация BOLID). "
                "Твой ответ будет озвучен голосом (TTS), поэтому пиши так, как говорят вслух.\n\n"

                "СТРОГИЕ ПРАВИЛА ФОРМАТА (обязательно):\n"
                "1) Отвечай одним связным текстом, максимум 2–3 коротких предложения.\n"
                "2) Никаких списков, нумерации и маркированных пунктов.\n"
                "3) Не используй Markdown и символы: *, #, -, _, /, |, >, [], (), {}, кавычки-ёлочки.\n"
                "4) Не пиши 'пункты', 'шаг 1', '1)', '1.' и подобные обозначения.\n"
                "5) Не используй двоеточия для перечислений. Если нужно перечислить — перечисляй словами в одной фразе.\n"
                "6) Не вставляй служебные пометки вроде 'Важно:', 'Примечание:', 'Ответ:' или 'Как оператор:'.\n"
                "7) Пиши профессионально и дружелюбно, как живой оператор, без канцелярита.\n\n"

                "СМЫСЛОВЫЕ ТРЕБОВАНИЯ:\n"
                "Сначала коротко уточни 2–3 ключевых вопроса: что именно не работает, когда началось и что меняли. "
                "Если похоже на угрозу безопасности, пожар, ложные сработки, критический отказ или нельзя решить удаленно — "
                "сразу предложи эскалацию и уточни адрес/контакт.\n\n"

                "Выводи только текст для озвучки, без лишних символов и форматирования."
            )}
        ]

        self.greeted = False

    def send_pcm(self, pcm: bytes):
        with self.speaking_lock:
            payload = pcm_to_ulaw(pcm)
            for i in range(0, len(payload), 160):
                chunk = payload[i:i+160]
                if len(chunk) < 160:
                    chunk += b"\xff" * (160 - len(chunk))
                pkt = build_rtp(self.seq, self.ts, self.ssrc, chunk)
                self.sock.sendto(pkt, self.addr)
                self.seq = (self.seq + 1) & 0xFFFF
                self.ts += FRAME_SAMPLES
                time.sleep(0.02)

    def tts_and_play(self, text: str):
        print(f"[TTS] {text}")
        pcm = synthesize_pcm(text)
        self.send_pcm(pcm)

    def maybe_greet(self):
        if self.greeted:
            return
        self.greeted = True
        executor.submit(self.tts_and_play,
            "Здравствуйте. Техническая поддержка СКС Сервис. Опишите проблему.")

    def feed(self, payload: bytes):
        self.maybe_greet()

        pcm = ulaw_to_pcm(payload)
        rms = audioop.rms(pcm, 2)

        if rms >= RMS_SPEECH_THRESHOLD:
            self.in_speech = True
            self.silence_ms = 0
            self.buf.extend(pcm)
        elif self.in_speech:
            self.silence_ms += FRAME_MS
            self.buf.extend(pcm)
            if self.silence_ms >= END_SILENCE_MS:
                utter = bytes(self.buf)
                self.buf.clear()
                self.in_speech = False

                dur_ms = int(len(utter) / 2 / SAMPLE_RATE * 1000)
                if dur_ms >= MIN_UTTERANCE_MS:
                    executor.submit(self.process_utterance, utter)

    def process_utterance(self, pcm: bytes):
        with self.dialog_lock:
            text = recognize_pcm(pcm)
            if not text:
                return

            print(f"[STT] {text}")
            self.messages.append({"role": "user", "content": text})

            if "авар" in text.lower() or "пожар" in text.lower():
                telegram_escalate(text)

            reply = chat(self.messages)
            self.messages.append({"role": "assistant", "content": reply})

            self.tts_and_play(reply)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", RTP_PORT))
    print(f"[media_server] RTP listening on :{RTP_PORT}")

    sessions = {}

    while True:
        pkt, addr = sock.recvfrom(2048)
        if len(pkt) <= 12:
            continue

        payload = pkt[12:]
        if not payload:
            continue

        sess = sessions.get(addr)
        if not sess:
            sess = Session(sock, addr)
            sessions[addr] = sess
            print(f"[media_server] new call from {addr}")

        sess.feed(payload)

if __name__ == "__main__":
    main()
