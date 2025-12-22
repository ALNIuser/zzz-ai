import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import aiohttp
import aioari
from dotenv import load_dotenv

load_dotenv()

ARI_BASE_URL = os.getenv("ARI_BASE_URL", "").strip()  # например: http://192.168.1.100:8088/ari
ARI_HOST = os.getenv("ARI_HOST", "192.168.1.100")
ARI_PORT = int(os.getenv("ARI_PORT", "8088"))

ARI_USER = os.getenv("ARI_USER", "ai_ari_user")
ARI_PASSWORD = os.getenv("ARI_PASSWORD", "1")
ARI_APP_NAME = os.getenv("ARI_APP_NAME", "ai_support_ari")
ARI_WS_URL = os.getenv("ARI_WS_URL", "").strip()

UBUNTU_IP = os.getenv("UBUNTU_IP", "192.168.1.2")
RTP_PORT = int(os.getenv("RTP_PORT", os.getenv("RTP_IN_PORT", "4000")))

RTP_FORMAT = (os.getenv("RTP_FORMAT", "ulaw") or "ulaw").strip().lower()
if RTP_FORMAT not in ("ulaw", "slin", "slin16"):
    RTP_FORMAT = "ulaw"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ARI")

ari = None
sessions = {}  # key=channel_id -> {bridge_id, external_id}


def _ari_http_base() -> str:
    """
    aioari.connect ждёт базу вида http://host:port (без /ari).
    """
    if ARI_BASE_URL:
        p = urlparse(ARI_BASE_URL)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    return f"http://{ARI_HOST}:{ARI_PORT}"


def _ari_ws_url() -> str:
    if ARI_WS_URL:
        return ARI_WS_URL
    return f"ws://{ARI_HOST}:{ARI_PORT}/ari/events?app={ARI_APP_NAME}&api_key={ARI_USER}:{ARI_PASSWORD}"


def is_external_channel(channel: dict) -> bool:
    name = channel.get("name", "") or ""
    return name.startswith("UnicastRTP/") or "UnicastRTP" in name or name.startswith("ExternalMedia/")


async def cleanup(channel_id: str):
    data = sessions.pop(channel_id, None)
    if not data:
        return
    try:
        await ari.channels.hangup(channelId=data["external_id"])
    except Exception:
        pass
    try:
        await ari.bridges.destroy(bridgeId=data["bridge_id"])
    except Exception:
        pass
    try:
        await ari.channels.hangup(channelId=channel_id)
    except Exception:
        pass


async def handle_stasis_start(event: dict):
    channel = event.get("channel") or {}
    channel_id = channel.get("id")
    channel_name = channel.get("name", "")

    if not channel_id:
        return

    # чтобы не зациклиться на ExternalMedia канале
    if is_external_channel(channel):
        log.info(f"Ignored ExternalMedia channel: {channel_name}")
        return

    if channel_id in sessions:
        return

    log.info(f"StasisStart: {channel_name} ({channel_id})")

    try:
        await ari.channels.answer(channelId=channel_id)

        bridge = await ari.bridges.create(type="mixing")
        await ari.bridges.addChannel(bridgeId=bridge.id, channel=channel_id)

        # ExternalMedia: Asterisk будет слать RTP на UBUNTU_IP:RTP_PORT
        ext = await ari.channels.externalMedia(
            app=ARI_APP_NAME,
            external_host=f"{UBUNTU_IP}:{RTP_PORT}",
            format=RTP_FORMAT,          # ulaw
            direction="both",
            encapsulation="rtp",
        )

        await ari.bridges.addChannel(bridgeId=bridge.id, channel=ext.id)

        sessions[channel_id] = {"bridge_id": bridge.id, "external_id": ext.id}
        log.info(f"Connected ExternalMedia to {UBUNTU_IP}:{RTP_PORT} format={RTP_FORMAT}")

    except Exception as e:
        log.error(f"Call setup failed: {e}")
        await cleanup(channel_id)


async def handle_stasis_end(event: dict):
    channel = event.get("channel") or {}
    channel_id = channel.get("id")
    if channel_id:
        await cleanup(channel_id)
        log.info(f"StasisEnd: {channel_id} cleaned")


async def main():
    global ari

    ari_http = _ari_http_base()
    ws_url = _ari_ws_url()

    log.info(f"Connecting ARI REST: {ari_http} (user={ARI_USER}, app={ARI_APP_NAME})")
    ari = await aioari.connect(ari_http, ARI_USER, ARI_PASSWORD)
    log.info("ARI REST connected")

    log.info(f"Connecting ARI WS: {ws_url}")
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url)
    log.info("ARI WS connected. Waiting for calls...")

    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            event = json.loads(msg.data)
            etype = event.get("type")

            if etype == "StasisStart":
                await handle_stasis_start(event)
            elif etype in ("StasisEnd", "ChannelHangupRequest"):
                await handle_stasis_end(event)
    finally:
        await ws.close()
        await session.close()
        await ari.close()


if __name__ == "__main__":
    asyncio.run(main())
