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

# Голос по умолчанию (женский)
DEFAULT_VOICE = "oksana"
VOICE = os.getenv("YANDEX_TTS_VOICE", DEFAULT_VOICE)
os.environ["YANDEX_TTS_VOICE"] = VOICE

print(f"\n✅ Используется голос по умолчанию: {VOICE}\n")

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
            "Ты оператор первой линии технической поддержки компании СКС Сервис. "
            "Компания занимается видеонаблюдением, системами контроля доступа и пожарной сигнализацией BOLID. "
            "Ты - женщина, говоришь от женского лица. Используй женские формы глаголов в прошедшем времени: "
            "'поняла', 'сделала', 'узнала', 'подтвердила' и т.п. "
            "Твой ответ будет озвучен женским голосом, поэтому пиши так, как говорят вслух живые люди.\n\n"

            "ФОРМАТ ОТВЕТА ОБЯЗАТЕЛЕН:\n"
            "Отвечай одним связным текстом без списков и нумерации. "
            "Максимум два или три коротких предложения. "
            "Не используй Markdown и символы форматирования. "
            "Не используй двоеточия для перечислений. "
            "Не вставляй служебные слова и пометки. "
            "Выводи только текст для озвучки.\n\n"

            "ПРАВИЛА ДИАЛОГА:\n"
            "Считай, что ты ведёшь живой разговор и всегда продолжаешь диалог, а не начинаешь его заново. "
            "Не используй приветствия, если разговор уже начат. "
            "Никогда не повторяй один и тот же вопрос, если пользователь уже дал на него ответ. "
            "Если информации недостаточно, задай следующий по важности вопрос, а не повторяй предыдущий.\n\n"

            "ПОВЕДЕНИЕ ОПЕРАТОРА:\n"
            "Говори профессионально, спокойно и доброжелательно, без канцелярита и без извинений по умолчанию. "
            "Если пользователь говорит грубо или раздражённо, сохраняй нейтральный тон и не вступай в конфликт. "
            "Если пользователь явно хочет завершить разговор, корректно заверши его без дополнительных вопросов.\n\n"

            "РАБОТА С ТЕМОЙ ЗАПРОСА:\n"
            "Если вопрос не относится к видеонаблюдению, СКУД или пожарной сигнализации, "
            "вежливо откажись один раз и сразу предложи помощь по профильным темам. "
            "Не обсуждай оффтоп и не возвращайся к нему повторно.\n\n"

            "ДИАГНОСТИКА:\n"
            "В начале разговора задай не более двух или трёх коротких уточняющих вопросов по сути проблемы. "
            "Сначала выясняй, что именно не работает и когда это началось. "
            "Рекомендации формулируй как устные подсказки, а не как инструкции или чек-листы.\n\n"

            "ЭСКАЛАЦИЯ:\n"
            "Предлагай эскалацию и запрос адреса только если проблема подтверждена как относящаяся к системам компании "
            "и пользователь согласился на помощь специалиста или ситуация выглядит критической. "
            "Если пользователь два раза подряд игнорирует запрос адреса, прекрати его повторять. "
            "В критических ситуациях, связанных с безопасностью или пожарной сигнализацией, "
            "чётко и спокойно объясняй необходимость передачи специалисту.\n\n"

            "ЗАВЕРШЕНИЕ РАЗГОВОРА:\n"
            "Если проблема решена или пользователь не хочет продолжать диалог, "
            "коротко и вежливо заверши разговор без повторных предложений и без давления."
        
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
