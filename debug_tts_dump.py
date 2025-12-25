from api.yandex_tts import synthesize_pcm

def main():
    pcm = synthesize_pcm("Проверка связи один два три")
    print("len(pcm) =", len(pcm))
    print("first 16 bytes =", pcm[:16])

    with open("tts_dump.bin", "wb") as f:
        f.write(pcm)

    print("Saved to tts_dump.bin")

if __name__ == "__main__":
    main()
