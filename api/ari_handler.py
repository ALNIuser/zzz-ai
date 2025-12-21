import asyncio
import logging
import json
import aiohttp
import aioari

# ================== НАСТРОЙКИ ==================

ARI_URL = "http://192.168.1.100:8088"
ARI_USER = "ai_ari_user"
ARI_PASS = "1"
ARI_APP = "ai_support_ari"

SOUND = "demo-congrats"

# ================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

log = logging.getLogger("ARI")

# ================== GLOBAL =====================

ari = None

# playback_id -> channel_id
PLAYBACK_CHANNEL_MAP = {}

IMPORTANT_EVENTS = {
    "StasisStart",
    "PlaybackFinished",
    "StasisEnd",
}

# ================== EVENT HANDLER ==============

async def handle_event(event: dict):
    event_type = event.get("type")

    if event_type not in IMPORTANT_EVENTS:
        return

    log.info("ARI event: %s", event_type)

    # -------- STASIS START --------
    if event_type == "StasisStart":
        channel = event["channel"]
        channel_id = channel["id"]

        log.info("Call entered Stasis: %s", channel_id)

        try:
            await ari.channels.answer(channelId=channel_id)
            log.info("Channel answered: %s", channel_id)

            playback = await ari.channels.play(
                channelId=channel_id,
                media=f"sound:{SOUND}"
            )

            playback_id = playback.id   # <-- КЛЮЧЕВОЙ ФИКС
            PLAYBACK_CHANNEL_MAP[playback_id] = channel_id

            log.info(
                "Playback started: %s (playback_id=%s)",
                SOUND,
                playback_id
            )

        except Exception as e:
            log.error("Error handling channel %s: %s", channel_id, e)
            try:
                await ari.channels.hangup(channelId=channel_id)
            except Exception:
                pass

    # -------- PLAYBACK FINISHED --------
    elif event_type == "PlaybackFinished":
        playback = event["playback"]
        playback_id = playback["id"]

        channel_id = PLAYBACK_CHANNEL_MAP.pop(playback_id, None)

        log.info(
            "Playback finished: playback=%s channel=%s",
            playback_id,
            channel_id
        )

        if not channel_id:
            log.warning("No channel mapped to playback %s", playback_id)
            return

        try:
            await ari.channels.hangup(channelId=channel_id)
            log.info("Channel hung up: %s", channel_id)
        except Exception as e:
            log.error("Failed to hangup channel %s: %s", channel_id, e)

    # -------- STASIS END --------
    elif event_type == "StasisEnd":
        channel = event["channel"]
        channel_id = channel["id"]
        log.info("Call left Stasis: %s", channel_id)

# ================== MAIN =======================

async def main():
    global ari

    log.info("Connecting to ARI REST: %s", ARI_URL)

    ari = await aioari.connect(
        ARI_URL,
        ARI_USER,
        ARI_PASS
    )

    log.info("ARI REST connected")

    ws_url = (
        f"{ARI_URL.replace('http://', 'ws://')}/ari/events"
        f"?app={ARI_APP}"
        f"&api_key={ARI_USER}:{ARI_PASS}"
        f"&subscribeAll=true"
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
                log.error("WebSocket error: %s", ws.exception())
                break

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                log.warning("WebSocket closed")
                break

    finally:
        await ws.close()
        await session.close()
        await ari.close()
        log.info("ARI handler stopped")

# ================== ENTRY ======================

if __name__ == "__main__":
    asyncio.run(main())
