from __future__ import annotations

"""Sound effects for Ninja Chess.

Generates simple WAV files programmatically (no external audio files needed)
and plays them non-blocking via arcade / pyglet.
"""

import math
import os
import struct
import wave
import io
import threading

import arcade

from utils.constants import ASSETS_DIR

_SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")
_loaded: dict[str, arcade.Sound | None] = {}
_enabled = True


def _sine_wave(freq: float, duration: float, sample_rate: int = 22050,
               amplitude: float = 0.4) -> bytes:
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        val = amplitude * math.sin(2 * math.pi * freq * t)
        # Fade in/out (10 ms each)
        fade = min(1.0, t / 0.01, (duration - t) / 0.01)
        val *= fade
        samples.append(int(max(-32767, min(32767, val * 32767))))
    return struct.pack(f"<{n}h", *samples)


def _mix(*waves: bytes) -> bytes:
    """Mix multiple mono 16-bit PCM byte strings (same length or shorter)."""
    max_len = max(len(w) // 2 for w in waves)
    result = []
    for i in range(max_len):
        s = 0
        for w in waves:
            idx = i * 2
            if idx + 1 < len(w):
                val = struct.unpack_from("<h", w, idx)[0]
                s += val
        result.append(int(max(-32767, min(32767, s))))
    return struct.pack(f"<{max_len}h", *result)


def _sweep(f0: float, f1: float, duration: float,
           sample_rate: int = 22050, amplitude: float = 0.35) -> bytes:
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        freq = f0 + (f1 - f0) * (t / duration)
        val = amplitude * math.sin(2 * math.pi * freq * t)
        fade = min(1.0, t / 0.008, (duration - t) / 0.01)
        val *= fade
        samples.append(int(max(-32767, min(32767, val * 32767))))
    return struct.pack(f"<{n}h", *samples)


def _make_wav_bytes(pcm: bytes, sample_rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _generate_sounds() -> dict[str, bytes]:
    """Return a dict of sound_name → WAV bytes."""
    SR = 22050
    sounds: dict[str, bytes] = {}

    # move: short soft click (400 Hz, 60 ms)
    sounds["move"] = _make_wav_bytes(_sine_wave(400, 0.06, SR, 0.30), SR)

    # capture: crunchier double-tone (520 Hz + 260 Hz, 90 ms)
    sounds["capture"] = _make_wav_bytes(
        _mix(_sine_wave(520, 0.09, SR, 0.28), _sine_wave(260, 0.09, SR, 0.22)), SR
    )

    # check: warning low-high (300→600 Hz sweep, 140 ms)
    sounds["check"] = _make_wav_bytes(_sweep(300, 600, 0.14, SR, 0.38), SR)

    # game_over_win: triumphant ascending tones
    pcm = _mix(
        _sine_wave(523, 0.12, SR, 0.30),  # C5
        _sine_wave(659, 0.12, SR, 0.20),  # E5 (quiet layer)
    )
    sounds["game_over_win"] = _make_wav_bytes(pcm, SR)

    # game_over_lose: descending tone
    sounds["game_over_lose"] = _make_wav_bytes(_sweep(400, 200, 0.20, SR, 0.35), SR)

    # augment: activation sparkle (high sweep up then down, 180 ms)
    pcm = _mix(
        _sweep(700, 1200, 0.09, SR, 0.25),
        _sweep(1200, 900, 0.09, SR, 0.15),
    )
    sounds["augment"] = _make_wav_bytes(pcm, SR)

    # round_start: "FIGHT" boom (deep sine burst, 200 ms)
    sounds["round_start"] = _make_wav_bytes(_sine_wave(100, 0.20, SR, 0.45), SR)

    return sounds


def init_sounds():
    """Generate sound files if needed and load them into arcade."""
    global _enabled
    os.makedirs(_SOUNDS_DIR, exist_ok=True)

    generated = _generate_sounds()
    for name, wav_bytes in generated.items():
        path = os.path.join(_SOUNDS_DIR, f"{name}.wav")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(wav_bytes)

    for name in generated:
        path = os.path.join(_SOUNDS_DIR, f"{name}.wav")
        try:
            _loaded[name] = arcade.load_sound(path)
        except Exception:
            _loaded[name] = None


def play(name: str, volume: float = 0.6):
    """Play a named sound effect non-blocking. Silently ignored if unavailable."""
    if not _enabled:
        return
    sound = _loaded.get(name)
    if sound:
        try:
            arcade.play_sound(sound, volume=volume)
        except Exception:
            pass
