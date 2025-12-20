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

# Имя звукового файла БЕЗ расширения
# Если demo-congrats.gsm существует - оставьте
# Если нет - замените на hello-world или beep
SOUND = "demo-congrats"

# ================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("ARI")

# ============== GLOBAL CLIENT ==================

ari = None

# ============== ВАЖНЫЕ СОБЫТИЯ =================

IMPORTANT_EVENTS = {
    "StasisStart",
    "StasisEnd",
    "PlaybackFinished",
    "ChannelHangupRequest"
}

# ============== EVENT HANDLER ==================

async def handle_event(event: dict):
    event_type = event.get("type")
    
    # Логируем только важные события
    if event_type not in IMPORTANT_EVENTS:
        return
        
    log.info("ARI event received: %s", event_type)

    if event_type == "StasisStart":
        channel = event.get("channel", {})
        channel_id = channel.get("id")

        log.info("Call entered Stasis: channel=%s", channel_id)

        try:
            # 1. Ответить на канал
            await ari.channels.answer(channelId=channel_id)
            log.info("Channel answered: %s", channel_id)
            
            # 2. Проиграть звук
            await ari.channels.play(
                channelId=channel_id,
                media=f"sound:{SOUND}"
            )
            log.info("Playback started: %s", SOUND)
            
        except Exception as e:
            log.error("Failed to handle channel %s: %s", channel_id, e)
            # При ошибке возвращаем канал в dialplan
            try:
                await ari.channels.continueInDialplan(channelId=channel_id)
            except:
                pass

    elif event_type == "PlaybackFinished":
        log.info("Playback finished")
        # После завершения воспроизведения можно что-то сделать
        # Например, вернуть в dialplan или начать запись
        
    elif event_type == "StasisEnd":
        channel = event.get("channel", {})
        channel_id = channel.get("id")
        log.info("Call left Stasis: channel=%s", channel_id)


# ============== MAIN ===========================

async def main():
    global ari

    log.info("Connecting to ARI REST at %s", ARI_URL)

    # Подключаемся к REST API aioari
    ari = await aioari.connect(
        ARI_URL,
        ARI_USER,
        ARI_PASS
    )

    log.info("ARI REST client connected")

    # --- WebSocket вручную через aiohttp ---
    ws_url = (
        f"{ARI_URL.replace('http://', 'ws://')}/ari/events"
        f"?app={ARI_APP}"
        f"&api_key={ARI_USER}:{ARI_PASS}"
        f"&subscribeAll=true"
    )

    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url)

    log.info("WebSocket connected to ARI events")
    log.info("ARI handler started. Waiting for calls...")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                await handle_event(event)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error("WebSocket error: %s", ws.exception())
                break
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                log.info("WebSocket closed")
                break
                
    except asyncio.CancelledError:
        log.info("Shutting down...")
    except Exception as e:
        log.error("Unexpected error: %s", e)
    finally:
        await ws.close()
        await session.close()
        await ari.close()
        log.info("ARI handler stopped")


# ============== ENTRY POINT ====================

if __name__ == "__main__":
    asyncio.run(main())
