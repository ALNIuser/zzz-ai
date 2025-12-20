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

# ================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("ARI")

# ============== GLOBAL CLIENT ==================

ari = None


# ============== EVENT HANDLER ==================

async def handle_event(event: dict):
    event_type = event.get("type")
    log.info("ARI event received: %s", event_type)

    if event_type == "StasisStart":
        channel = event.get("channel", {})
        channel_id = channel.get("id")

        log.info("Call entered Stasis: channel=%s", channel_id)

        try:
            await ari.channels.answer(channelId=channel_id)
            log.info("Channel answered: %s", channel_id)
        except Exception as e:
            log.error("Failed to answer channel %s: %s", channel_id, e)

    elif event_type == "StasisEnd":
        channel = event.get("channel", {})
        channel_id = channel.get("id")
        log.info("Call left Stasis: channel=%s", channel_id)


# ============== MAIN ===========================

async def main():
    global ari

    log.info("Connecting to ARI REST at %s", ARI_URL)

    ari = await aioari.connect(
        ARI_URL,
        ARI_USER,
        ARI_PASS
    )

    log.info("ARI REST client connected")

    # --- WebSocket вручную (aioari НЕ управляет WS) ---
    ws_url = (
        f"{ARI_URL}/ari/events"
        f"?app={ARI_APP}"
        f"&api_key={ARI_USER}:{ARI_PASS}"
    )

    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url)

    log.info("WebSocket connected to ARI events")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                await handle_event(event)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error("WebSocket error: %s", ws.exception())
                break
    finally:
        await ws.close()
        await session.close()
        await ari.close()


# ============== ENTRY POINT ====================

if __name__ == "__main__":
    asyncio.run(main())
