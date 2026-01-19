# Voice AI для Asterisk (ARI) + RTP media server

Этот репозиторий — прототип голосового AI-оператора для Asterisk. Asterisk управляет звонком через ARI и поднимает ExternalMedia (RTP), а отдельный media_server по UDP принимает/отдаёт аудио и подключает обработку (например STT → LLM → TTS).

Главные части: `api/media_server.py` — RTP/UDP медиасервер (аудио из Asterisk и ответ обратно), `api/ari_handler.py` — ARI-обработчик (события звонка, bridge/ExternalMedia, подключение звонка к медиасерверу).

Запуск: сначала медиасервер `python api/media_server.py`, затем ARI handler `python api/ari_handler.py`. Настройки подключения (ARI host/user/pass, IP:port медиасервера, ключи STT/TTS/LLM) задаются в конфиге/переменных окружения проекта.
