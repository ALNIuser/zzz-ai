import asyncio
import logging
import uuid

log = logging.getLogger("ARI")

class CallSession:
    def __init__(self, ari, channel_id, sound):
        self.ari = ari
        self.channel_id = channel_id
        self.sound = sound

        self.playback_id = None
        self.recording_name = None

    async def start(self):
        log.info("CallSession start: %s", self.channel_id)

        # Ответить
        await self.ari.channels.answer(channelId=self.channel_id)
        log.info("Channel answered: %s", self.channel_id)

        # Проиграть звук
        playback = await self.ari.channels.play(
            channelId=self.channel_id,
            media=f"sound:{self.sound}"
        )

        self.playback_id = playback.id
        log.info("Playback started: %s (%s)", self.sound, self.playback_id)

    async def on_playback_finished(self):
        log.info("Playback finished for channel %s", self.channel_id)

        # Завершаем вызов (пока без STT)
        await self.ari.channels.hangup(channelId=self.channel_id)
        log.info("Channel hung up: %s", self.channel_id)

    async def cleanup(self):
        log.info("Cleanup session: %s", self.channel_id)
