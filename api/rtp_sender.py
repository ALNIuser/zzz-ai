# api/rtp_sender.py
import socket
import struct
import time

RTP_HEADER_SIZE = 12
PAYLOAD_TYPE = 96
SSRC = 12345678

class RTPSender:
    def __init__(self, host, port, sample_rate=8000):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        self.ts = 0
        self.sample_rate = sample_rate

    def send_pcm(self, pcm: bytes):
        frame_samples = 160  # 20 ms @ 8kHz
        frame_size = frame_samples * 2  # s16

        for i in range(0, len(pcm), frame_size):
            chunk = pcm[i:i + frame_size]
            header = struct.pack(
                "!BBHII",
                0x80,
                PAYLOAD_TYPE,
                self.seq,
                self.ts,
                SSRC
            )
            self.sock.sendto(header + chunk, self.addr)
            self.seq += 1
            self.ts += frame_samples
            time.sleep(0.02)
