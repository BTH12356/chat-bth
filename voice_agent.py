import os
import sys
import threading
from pathlib import Path

# ปิด Warning ALSA / JACK / Pygame
sys.stderr = open(os.devnull, 'w')
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import speech_recognition as sr
import requests
import pygame
from faster_whisper import WhisperModel
from local_tts import LocalTTSError, synthesize_mp3

try:
    from pynput import keyboard
    HOTKEY_IMPORT_ERROR = ""
except Exception as error:  # Global hooks may be unavailable on headless/Wayland sessions.
    keyboard = None
    HOTKEY_IMPORT_ERROR = str(error)

OLLAMA_URL = "http://localhost:11434/api/generate"
PUSH_TO_TALK_KEYS = frozenset(
    key.strip().lower() for key in os.getenv("HERMES_PUSH_TO_TALK_KEYS", "5+6").split("+") if key.strip()
)

# โหลดโมเดล Whisper ออฟไลน์ (โหลดครั้งแรกอาจใช้เวลานิดหน่อย)
sys.__stdout__.write("กำลังโหลดโมเดล Whisper (Local STT)...\n")
sys.__stdout__.flush()
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")


class PushToTalk:
    """Wait for an explicit global key chord before recording one utterance."""

    def __init__(self, keys: frozenset[str]):
        if not keys:
            raise ValueError("HERMES_PUSH_TO_TALK_KEYS ต้องมีอย่างน้อยหนึ่งปุ่ม")
        self.keys = keys
        self.pressed: set[str] = set()
        self.activated = False
        self.event = threading.Event()
        self.listener = None

    @staticmethod
    def _name(key):
        char = getattr(key, "char", None)
        if char:
            return char.lower()
        name = str(key).lower().removeprefix("key.")
        return {
            "ctrl_l": "ctrl", "ctrl_r": "ctrl",
            "alt_l": "alt", "alt_r": "alt",
            "shift_l": "shift", "shift_r": "shift",
        }.get(name, name)

    def _on_press(self, key):
        name = self._name(key)
        if name:
            self.pressed.add(name)
        if not self.activated and self.keys.issubset(self.pressed):
            self.activated = True
            self.event.set()

    def _on_release(self, key):
        name = self._name(key)
        if name:
            self.pressed.discard(name)
        if not self.keys.issubset(self.pressed):
            self.activated = False

    def start(self):
        if keyboard is None:
            detail = f" ({HOTKEY_IMPORT_ERROR})" if HOTKEY_IMPORT_ERROR else ""
            raise RuntimeError("ไม่สามารถใช้งาน global hotkey ได้" + detail)
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()

    def wait(self):
        self.event.wait()
        self.event.clear()

    def stop(self):
        if self.listener:
            self.listener.stop()

def listen(recognizer):
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = False  # ล็อกความไวไมค์ ไม่ให้ตัดเสียงท้ายประโยค
    recognizer.pause_threshold = 2.0
    
    try:
        with sr.Microphone() as source:
            sys.__stdout__.write("\n[Nitro 5 Whisper] พร้อมฟัง... (พูดประโยคยาวๆ ได้เลย / พูด 'ออก' เพื่อเลิก): ")
            sys.__stdout__.flush()
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            # รองรับการฟังประโยคยาวสูงสุด 60 วินาที
            audio = recognizer.listen(source, timeout=15, phrase_time_limit=60)
        
        sys.__stdout__.write("\nกำลังถอดรหัสเสียงด้วย Whisper...\n")
        sys.__stdout__.flush()
        
        # บันทึกเป็นไฟล์ชั่วคราวให้ Whisper อ่าน
        wav_data = audio.get_wav_data()
        audio_file = "temp_voice.wav"
        with open(audio_file, "wb") as f:
            f.write(wav_data)
            
        # ถอดความภาษาไทย
        segments, _ = whisper_model.transcribe(audio_file, language="th", beam_size=5)
        text = "".join([segment.text for segment in segments]).strip()
        
        if os.path.exists(audio_file):
            os.remove(audio_file)
            
        sys.__stdout__.write(f"คุณพูดว่า: {text}\n")
        sys.__stdout__.flush()
        return text
        
    except sr.WaitTimeoutError:
        return None
    except Exception as e:
        sys.__stdout__.write(f"เกิดข้อผิดพลาดในการฟัง: {e}\n")
        return None

def speak(text):
    if not text:
        return
    response_file = "response.mp3"
    try:
        synthesize_mp3(text, "th", Path(response_file))
    except LocalTTSError as error:
        sys.__stdout__.write(f"สร้างเสียงแบบ local ไม่สำเร็จ: {error}\n")
        return
    
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    os.dup2(devnull, 2)
    
    pygame.mixer.init()
    pygame.mixer.music.load(response_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    pygame.mixer.quit()
    
    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    os.close(devnull)
    
    if os.path.exists(response_file):
        os.remove(response_file)

if __name__ == "__main__":
    recognizer = sr.Recognizer()
    context = []
    hotkey = PushToTalk(PUSH_TO_TALK_KEYS)
    
    sys.__stdout__.write("=== ระบบ Voice Agent พร้อมใช้งาน (Whisper + Hermes) ===\n")
    sys.__stdout__.write(f"กด {' + '.join(sorted(PUSH_TO_TALK_KEYS))} พร้อมกันเพื่อพูด\n")
    sys.__stdout__.flush()
    try:
        hotkey.start()
        while True:
            hotkey.wait()
            user_input = listen(recognizer)

            if user_input:
                if "จบการทำงาน" in user_input or "ออก" in user_input or "เลิก" in user_input:
                    sys.__stdout__.write("จบการสนทนา ขอบคุณครับ!\n")
                    speak("จบการสนทนา ขอบคุณครับ")
                    break

                payload = {
                    "model": "hermes3:8b",
                    "system": "นายคือเพื่อนที่พร้อมให้กำลังใจฉัน",
                    "prompt": user_input,
                    "context": context,
                    "stream": False
                }

                try:
                    res = requests.post(OLLAMA_URL, json=payload).json()
                    reply = res.get("response", "")
                    context = res.get("context", [])

                    sys.__stdout__.write(f"Hermes ตอบ: {reply}\n")
                    sys.__stdout__.flush()
                    speak(reply)
                except Exception as e:
                    sys.__stdout__.write(f"เชื่อมต่อ Ollama ไม่ได้: {e}\n")
    finally:
        hotkey.stop()
