import os
import socket
import time
import audioop
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from api.yandex_stt import recognize_pcm
from api.yandex_tts import synthesize_pcm
from api.llm_client import chat

load_dotenv()

RTP_PORT = int(os.getenv("RTP_PORT", os.getenv("RTP_IN_PORT", "4000")))
RTP_FORMAT = (os.getenv("RTP_FORMAT", "ulaw") or "ulaw").strip().lower()
SAMPLE_RATE = int(os.getenv("RTP_SAMPLE_RATE", "8000"))

RMS_SPEECH_THRESHOLD = int(os.getenv("RMS_SPEECH_THRESHOLD", "200"))
MIN_UTTERANCE_MS = int(os.getenv("MIN_UTTERANCE_MS", "800"))
END_SILENCE_MS = int(os.getenv("END_SILENCE_MS", "700"))

FRAME_MS = 20
executor = ThreadPoolExecutor(max_workers=4)


def parse_rtp(pkt: bytes):
    if len(pkt) < 12:
        return None

    b0 = pkt[0]
    version = b0 >> 6
    if version != 2:
        return None

    padding = (b0 >> 5) & 1
    extension = (b0 >> 4) & 1
    cc = b0 & 0x0F

    b1 = pkt[1]
    pt = b1 & 0x7F

    seq = int.from_bytes(pkt[2:4], "big")
    ts = int.from_bytes(pkt[4:8], "big")
    ssrc = int.from_bytes(pkt[8:12], "big")

    off = 12 + cc * 4
    if len(pkt) < off:
        return None

    if extension:
        if len(pkt) < off + 4:
            return None
        # extension: profile(16) + length(16 words)
        ext_len_words = int.from_bytes(pkt[off + 2: off + 4], "big")  # FIX: было ff
        off += 4 + ext_len_words * 4
        if len(pkt) < off:
            return None

    end = len(pkt)
    if padding:
        pad_len = pkt[-1]
        if 0 < pad_len <= end:
            end -= pad_len

    payload = pkt[off:end]
    return pt, seq, ts, ssrc, payload


def build_rtp(pt: int, seq: int, ts: int, ssrc: int, payload: bytes) -> bytes:
    # V=2, P=0, X=0, CC=0
    b0 = 0x80
    # M=0, PT
    b1 = pt & 0x7F
    hdr = bytearray(12)
    hdr[0] = b0
    hdr[1] = b1
    hdr[2:4] = (seq & 0xFFFF).to_bytes(2, "big")
    hdr[4:8] = (ts & 0xFFFFFFFF).to_bytes(4, "big")
    hdr[8:12] = (ssrc & 0xFFFFFFFF).to_bytes(4, "big")
    return bytes(hdr) + payload


class Session:
    def __init__(self, sock: socket.socket, addr, pt: int, ssrc_in: int):
        self.sock = sock
        self.addr = addr
        self.pt = pt
        self.ssrc_in = ssrc_in

        self.out_seq = int.from_bytes(os.urandom(2), "big")
        self.out_ts = int.from_bytes(os.urandom(4), "big")
        self.out_ssrc = int.from_bytes(os.urandom(4), "big")

        self.buf = bytearray()
        self.in_speech = False
        self.silence_ms = 0

        self.greeted = False

        self.messages = [
            {"role": "system", "content": (
                "Ты инженер первой линии техподдержки компании СКС Сервис "
                "(видеонаблюдение, СКУД, пожарная сигнализация BOLID). "
                "Коротко и по делу: уточняй модель/симптомы/когда началось/что меняли. "
                "Давай пошаговую диагностику. Если это безопасность/пожарка/авария или не получается удалённо — эскалируй."
            )}
        ]

    def payload_to_pcm(self, payload: bytes) -> bytes:
        if RTP_FORMAT == "ulaw":
            return audioop.ulaw2lin(payload, 2)
        # slin/slin16: это уже PCM s16le
        return payload

    def pcm_to_payload(self, pcm_s16le: bytes) -> tuple[bytes, int]:
        """
        Возвращает (payload_bytes, frame_payload_bytes) для 20ms.
        """
        if RTP_FORMAT == "ulaw":
            payload = audioop.lin2ulaw(pcm_s16le, 2)
            return payload, 160  # 20ms@8k: 160 байт ulaw
        return pcm_s16le, 320    # 160 samples * 2 bytes

    def send_payload_stream(self, payload: bytes, frame_payload_bytes: int):
        for i in range(0, len(payload), frame_payload_bytes):
            chunk = payload[i:i + frame_payload_bytes]
            if len(chunk) < frame_payload_bytes:
                if RTP_FORMAT == "ulaw":
                    chunk += b"\xff" * (frame_payload_bytes - len(chunk))
                else:
                    chunk += b"\x00" * (frame_payload_bytes - len(chunk))

            pkt = build_rtp(self.pt, self.out_seq, self.out_ts, self.out_ssrc, chunk)
            self.sock.sendto(pkt, self.addr)

            self.out_seq = (self.out_seq + 1) & 0xFFFF
            self.out_ts = (self.out_ts + 160) & 0xFFFFFFFF  # 20ms шаг для 8kHz
            time.sleep(0.02)

    def maybe_greet(self):
        if self.greeted:
            return
        self.greeted = True
        greeting = (
            "Здравствуйте. Вы позвонили в техническую поддержку компании СКС сервис. "
            "Опишите, пожалуйста, вашу проблему."
        )
        executor.submit(self._tts_and_send, greeting)

    def _tts_and_send(self, text: str):
        tts_pcm = synthesize_pcm(text)
        out_payload, frame_payload_bytes = self.pcm_to_payload(tts_pcm)
        self.send_payload_stream(out_payload, frame_payload_bytes)

    def feed(self, payload: bytes):
        if not payload:
            return

        # как только пошёл RTP от Asterisk — можно слать greeting назад
        self.maybe_greet()

        pcm = self.payload_to_pcm(payload)

        try:
            rms = audioop.rms(pcm, 2)
        except Exception:
            return

        if rms >= RMS_SPEECH_THRESHOLD:
            if not self.in_speech:
                self.in_speech = True
                self.silence_ms = 0
            self.buf.extend(pcm)
        else:
            if self.in_speech:
                self.silence_ms += FRAME_MS
                self.buf.extend(pcm)

                if self.silence_ms >= END_SILENCE_MS:
                    pcm_bytes = bytes(self.buf)
                    self.buf.clear()
                    self.in_speech = False
                    self.silence_ms = 0

                    utter_ms = int((len(pcm_bytes) / 2) / SAMPLE_RATE * 1000)
                    if utter_ms >= MIN_UTTERANCE_MS:
                        executor.submit(process_utterance, self, pcm_bytes)


def process_utterance(sess: Session, pcm_bytes: bytes):
    try:
        text = recognize_pcm(pcm_bytes, sample_rate=SAMPLE_RATE)
        if not text:
            reply = "Я вас не расслышал. Назовите, пожалуйста, модель оборудования и что именно не работает."
        else:
            sess.messages.append({"role": "user", "content": text})
            reply = chat(sess.messages) or "Уточните, пожалуйста, модель оборудования и симптомы."
            sess.messages.append({"role": "assistant", "content": reply})

        tts_pcm = synthesize_pcm(reply)
        out_payload, frame_payload_bytes = sess.pcm_to_payload(tts_pcm)
        sess.send_payload_stream(out_payload, frame_payload_bytes)

    except Exception as e:
        print(f"[media_server] error for {sess.addr}: {e}")


def main():
    if RTP_FORMAT not in ("ulaw", "slin", "slin16"):
        raise RuntimeError("RTP_FORMAT must be ulaw or slin/slin16")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", RTP_PORT))

    print(f"[media_server] RTP listening on 0.0.0.0:{RTP_PORT}, format={RTP_FORMAT}, sr={SAMPLE_RATE}")

    sessions = {}

    while True:
        pkt, addr = sock.recvfrom(4096)
        parsed = parse_rtp(pkt)
        if not parsed:
            continue

        pt, _seq, _ts, ssrc, payload = parsed
        if not payload:
            continue

        key = (addr[0], addr[1], ssrc)
        sess = sessions.get(key)
        if not sess:
            sess = Session(sock=sock, addr=addr, pt=pt, ssrc_in=ssrc)
            sessions[key] = sess
            print(f"[media_server] new session from {addr}, pt={pt}, ssrc={ssrc}")

        sess.feed(payload)


if __name__ == "__main__":
    main()
