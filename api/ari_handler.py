import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import aiohttp
import aioari
from dotenv import load_dotenv

load_dotenv()

# ====== НАСТРОЙКИ ======
ARI_HOST = os.getenv("ARI_HOST", "192.168.1.100")
ARI_PORT = int(os.getenv("ARI_PORT", "8088"))
ARI_USER = os.getenv("ARI_USER", "ai_ari_user")
ARI_PASSWORD = os.getenv("ARI_PASSWORD", "1")
ARI_APP_NAME = os.getenv("ARI_APP_NAME", "ai_support_ari")

MEDIA_SERVER_IP = os.getenv("UBUNTU_IP", "192.168.1.2")
MEDIA_SERVER_PORT = int(os.getenv("RTP_PORT", "9000"))
MEDIA_FORMAT = "ulaw"
# ======================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ARI")

ari = None


def is_external(channel: dict) -> bool:
    name = channel.get("name", "")
    return name.startswith("UnicastRTP/") or name.startswith("ExternalMedia/")


async def on_stasis_start(event: dict):
    channel = event.get("channel", {})
    channel_id = channel.get("id")
    channel_name = channel.get("name", "")

    if not channel_id:
        return

    if is_external(channel):
        log.info(f"Ignored ExternalMedia channel: {channel_name}")
        return

    log.info(f"Incoming call: {channel_name} ({channel_id})")

    try:
        await ari.channels.answer(channelId=channel_id)

        bridge = await ari.bridges.create(type="mixing")
        await ari.bridges.addChannel(bridgeId=bridge.id, channel=channel_id)

        external = await ari.channels.externalMedia(
            app=ARI_APP_NAME,
            external_host=f"{MEDIA_SERVER_IP}:{MEDIA_SERVER_PORT}",
            format=MEDIA_FORMAT,
            direction="both",
            encapsulation="rtp",
        )

        await ari.bridges.addChannel(bridgeId=bridge.id, channel=external.id)

        log.info(
            f"ExternalMedia connected -> {MEDIA_SERVER_IP}:{MEDIA_SERVER_PORT} ({MEDIA_FORMAT})"
        )

    except Exception as e:
        log.error(f"Call setup failed: {e}")


async def main():
    global ari

    base_url = f"http://{ARI_HOST}:{ARI_PORT}"
    ws_url = (
        f"ws://{ARI_HOST}:{ARI_PORT}/ari/events"
        f"?app={ARI_APP_NAME}&api_key={ARI_USER}:{ARI_PASSWORD}"
    )

    log.info(f"Connecting ARI REST: {base_url}")
    ari = await aioari.connect(base_url, ARI_USER, ARI_PASSWORD)
    log.info("ARI REST connected")

    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url)
    log.info("ARI WS connected, waiting for calls...")

    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue

        event = json.loads(msg.data)
        if event.get("type") == "StasisStart":
            await on_stasis_start(event)


if __name__ == "__main__":
    asyncio.run(main())
