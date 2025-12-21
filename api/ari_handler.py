import asyncio
import logging
import json
import os
import aiohttp
import aioari

from .yandex_tts import synthesize

# ================== НАСТРОЙКИ ==================

ARI_URL = "http://192.168.1.100:8088"
ARI_USER = "ai_ari_user"
ARI_PASS = "1"
ARI_APP = "ai_support_ari"

# TTS
TTS_TEXT = "Здравствуйте. Вы позвонили в техническую поддержку компании СКС сервис, чем мы можем вам помочь?"
TTS_NAME = "greeting"
TTS_PATH = f"/var/lib/asterisk/sounds/tts/{TTS_NAME}.wav"

# ================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("ARI")

# ================== GLOBAL =====================

ari = None
sessions = {}

IMPORTANT_EVENTS = {
    "StasisStart",
    "PlaybackFinished",
    "ChannelHangupRequest",
    "StasisEnd"
}

# ================== CALL SESSION ===============

class CallSession:
    def __init__(self, ari, channel_id):
        self.ari = ari
        self.channel_id = channel_id
        self.playback_id = None

    async def start(self):
        log.info("CallSession start: %s", self.channel_id)

        await self.ari.channels.answer(channelId=self.channel_id)
        log.info("Channel answered: %s", self.channel_id)

        playback = await self.ari.channels.play(
            channelId=self.channel_id,
            media=f"sound:tts/{TTS_NAME}"
        )

        self.playback_id = playback.id
        log.info(
            "Playback started: %s (%s)",
            TTS_NAME,
            self.playback_id
        )

    async def on_playback_finished(self):
        log.info("Playback finished for channel %s", self.channel_id)

        try:
            await self.ari.channels.hangup(channelId=self.channel_id)
            log.info("Channel hung up: %s", self.channel_id)
        except Exception as e:
            log.warning("Hangup failed: %s", e)

    async def cleanup(self):
        log.info("Cleanup session: %s", self.channel_id)

# ================== EVENT HANDLER ===============

async def handle_event(event: dict):
    event_type = event.get("type")

    if event_type not in IMPORTANT_EVENTS:
        return

    log.info("ARI event: %s", event_type)

    if event_type == "StasisStart":
        channel = event.get("channel", {})
        channel_id = channel.get("id")

        if not channel_id:
            return

        session = CallSession(ari, channel_id)
        sessions[channel_id] = session
        await session.start()

    elif event_type == "PlaybackFinished":
        playback = event.get("playback", {})
        playback_id = playback.get("id")

        for session in sessions.values():
            if session.playback_id == playback_id:
                await session.on_playback_finished()
                break

    elif event_type == "StasisEnd":
        channel = event.get("channel", {})
        channel_id = channel.get("id")

        session = sessions.pop(channel_id, None)
        if session:
            await session.cleanup()
            log.info("Call ended: %s", channel_id)

# ================== MAIN ========================

async def main():
    global ari

    log.info("Connecting to ARI REST: %s", ARI_URL)

    # --- Генерация TTS ОДИН РАЗ ---
    synthesize(TTS_TEXT, TTS_PATH)

    # --- ARI REST ---
    ari = await aioari.connect(
        ARI_URL,
        ARI_USER,
        ARI_PASS
    )

    log.info("ARI REST connected")

    # --- ARI WebSocket ---
    ws_url = (
        f"{ARI_URL.replace('http://', 'ws://')}/ari/events"
        f"?app={ARI_APP}"
        f"&api_key={ARI_USER}:{ARI_PASS}"
    )

    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url)

    log.info("ARI WebSocket connected")
    log.info("Waiting for calls...")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                await handle_event(event)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error("WebSocket error")
                break

    finally:
        await ws.close()
        await session.close()
        await ari.close()
        log.info("ARI handler stopped")

# ================== ENTRY =======================

if __name__ == "__main__":
    asyncio.run(main())
