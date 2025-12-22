## Запуск

### 1) На AI-сервере (Ubuntu 192.168.1.2)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
