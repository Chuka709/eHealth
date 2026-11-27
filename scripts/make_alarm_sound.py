"""The dose reminders' alarm tone (mobile/assets/sounds/dose_alarm.wav) - made here, no third-party
audio: three rising beeps, four times, 8 s, 16-bit mono 22.05 kHz WAV (iOS: <= 30 s).
    python scripts/make_alarm_sound.py mobile/assets/sounds/dose_alarm.wav
"""
import math, struct, sys, wave

RATE = 22050
def tone(freq, ms, vol=0.6):
    n = int(RATE * ms / 1000); fade = int(RATE * 0.01)
    out = []
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        s = math.sin(2 * math.pi * freq * i / RATE) + 0.3 * math.sin(4 * math.pi * freq * i / RATE)
        out.append(int(32767 * vol * env * s / 1.3))
    return out
def silence(ms): return [0] * int(RATE * ms / 1000)
frames = []
for _ in range(4):
    for f in (880, 1047, 1319):
        frames += tone(f, 220) + silence(80)
    frames += silence(1100)
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
print(len(frames) / RATE, "s")
