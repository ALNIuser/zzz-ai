# api/tts_config.py

AVAILABLE_VOICES = {
    "1": ("oksana", "Женский, нейтральный"),
    "2": ("alena", "Женский, мягкий"),
    "3": ("filipp", "Мужской, спокойный"),
    "4": ("ermil", "Мужской, уверенный"),
}

def select_voice() -> str:
    print("\nВыберите голос TTS:")
    for k, (v, d) in AVAILABLE_VOICES.items():
        print(f" {k}. {v} — {d}")

    while True:
        choice = input("Введите номер: ").strip()
        if choice in AVAILABLE_VOICES:
            voice = AVAILABLE_VOICES[choice][0]
            print(f"✔ Используется голос: {voice}\n")
            return voice
        print("Неверный выбор.")
