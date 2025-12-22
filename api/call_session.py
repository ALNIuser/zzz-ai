import os
import uuid
import asyncio
import logging

from api.yandex_tts import synthesize
from api.yandex_stt import recognize_pcm


class CallSession:
    def __init__(self, ari, channel, recordings_dir):
        self.ari = ari
        self.channel = channel
        self.recordings_dir = recordings_dir

        self.call_id = str(uuid.uuid4())
        self.logger = logging.getLogger(f"CallSession[{self.call_id[:8]}]")

        self.active = True

    async def start(self):
        self.logger.info("Call started")

        await self.channel.answer()
        self.logger.info("Channel answered")

        # 1. Приветствие
        greeting_text = (
            "Здравствуйте. Вы позвонили в техническую поддержку компании СКС сервис. "
            "Пожалуйста, опишите вашу проблему."
        )

        greeting_path = f"/tmp/greeting_{self.call_id}.wav"
        synthesize(greeting_text, greeting_path)

        await self.play(greeting_path)

        # 2. Запись речи пользователя (3 сек)
        recording_path = await self.record_user()

        # 3. STT
        text = self.process_stt(recording_path)

        if text:
            self.logger.info(f"User said: {text}")
            response_text = "Спасибо. Ваше обращение принято."
        else:
            response_text = "Извините, я вас не расслышал."

        # 4. Ответ
        response_path = f"/tmp/response_{self.call_id}.wav"
        synthesize(response_text, response_path)

        await self.play(response_path)

        # 5. Завершение
        await asyncio.sleep(0.5)
        await self.channel.hangup()
        self.logger.info("Call finished")

    async def play(self, wav_path: str):
        playback = self.ari.playbacks.create()
        await self.channel.play(
            media=f"sound:{wav_path}",
            playbackId=playback.id
        )

        # Ждём завершения воспроизведения
        future = asyncio.get_event_loop().create_future()

        async def on_finished(event, *args):
            if not future.done():
                future.set_result(True)

        self.ari.on_event("PlaybackFinished", on_finished)
        await future

    async def record_user(self) -> str:
        os.makedirs(self.recordings_dir, exist_ok=True)

        recording_name = f"user_{self.call_id}"
        recording_path = os.path.join(self.recordings_dir, recording_name)

        self.logger.info("Recording user speech (3 seconds)")

        await self.channel.record(
            name=recording_name,
            format="slin",
            maxDurationSeconds=3,
            beep=False,
            terminateOn="none"
        )

        await asyncio.sleep(3.2)

        return recording_path + ".slin"

    def process_stt(self, recording_path: str) -> str | None:
        if not os.path.exists(recording_path):
            self.logger.error("Recording file not found")
            return None

        with open(recording_path, "rb") as f:
            pcm_data = f.read()

        return recognize_pcm(pcm_data)

