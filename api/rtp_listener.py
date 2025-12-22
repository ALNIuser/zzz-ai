import socket
import threading
import queue
import json
import time
import os
import audioop
import websocket

# ================== CONFIG ==================

RTP_IP = "0.0.0.0"
RTP_PORT = 4000

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
    raise RuntimeError("YANDEX_API_KEY or YANDEX_FOLDER_ID is not set")

STT_URL = (
    "wss://stt.api.cloud.yandex.net/speech/v1/stt:recognizeStreaming"
    "?lang=ru-RU&format=lpcm&sampleRateHertz=8000"
)

# ============================================

audio_queue = queue.Queue()
ws_ready = threading.Event()


def on_open(ws):
    print("✅ Connected to Yandex STT")
    ws_ready.set()


def on_message(ws, message):
    try:
        data = json.loads(message)
        if "result" in data:
            alt = data["result"].get("alternatives", [])
            if alt and "text" in alt[0]:
                print(f"STT: {alt[0]['text']}")
    except Exception as e:
        print("STT parse error:", e)


def on_error(ws, error):
    print("STT error:", error)


def on_close(ws, close_status_code, close_msg):
    print(f"STT connection closed: {close_status_code} {close_msg}")
    ws_ready.clear()


def stt_sender(ws):
    ws_ready.wait()  # ❗ НЕ ШЛЁМ АУДИО ДО OPEN
    while True:
        pcm = audio_queue.get()
        if pcm is None:
            break
        try:
            ws.send(pcm, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            print("STT send error:", e)
            break


def start_stt():
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "X-Folder-Id": YANDEX_FOLDER_ID,
    }

    ws = websocket.WebSocketApp(
        STT_URL,
        header=[f"{k}: {v}" for k, v in headers.items()],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    threading.Thread(
        target=lambda: ws.run_forever(ping_interval=10, ping_timeout=5),
        daemon=True,
    ).start()

    threading.Thread(
        target=stt_sender,
        args=(ws,),
        daemon=True,
    ).start()


def start_rtp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((RTP_IP, RTP_PORT))
    print(f"🎧 Listening RTP on {RTP_IP}:{RTP_PORT}")

    while True:
        data, addr = sock.recvfrom(2048)

        if len(data) <= 12:
            continue

        rtp_payload = data[12:]
        pcm = audioop.ulaw2lin(rtp_payload, 2)
        audio_queue.put(pcm)


def main():
    start_stt()
    start_rtp_listener()


if __name__ == "__main__":
    main()
