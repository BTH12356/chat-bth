"""Offline text-to-speech helpers.

This module deliberately invokes only programs and model files stored on the
local machine. Piper produces a WAV file and FFmpeg encodes it to MP3.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class LocalTTSError(RuntimeError):
    """Raised when the local speech engine cannot produce an audio file."""


def _model_path(language: str) -> Path:
    """Get a language-specific Piper model, falling back to the default model."""
    normalized = language.lower().replace("-", "_")
    configured = os.getenv(f"HERMES_PIPER_MODEL_{normalized.upper()}") or os.getenv("HERMES_PIPER_MODEL")
    if not configured:
        raise LocalTTSError(
            "ยังไม่ได้ตั้งค่าโมเดลเสียงแบบ local: กำหนด HERMES_PIPER_MODEL "
            "(หรือ HERMES_PIPER_MODEL_TH สำหรับภาษาไทย) ให้ชี้ไปที่ไฟล์ .onnx"
        )
    path = Path(configured).expanduser()
    if not path.is_file():
        raise LocalTTSError(f"ไม่พบไฟล์โมเดล Piper: {path}")
    return path


def _executable(setting: str, default: str, label: str) -> str:
    executable = os.getenv(setting, default)
    resolved = shutil.which(executable)
    if not resolved:
        raise LocalTTSError(f"ไม่พบ {label} ในเครื่อง: {executable}")
    return resolved


def _piper_command() -> list[str]:
    """Use the application's interpreter unless an explicit Piper binary is set."""
    configured = os.getenv("HERMES_PIPER_COMMAND", "").strip()
    if configured:
        return [_executable("HERMES_PIPER_COMMAND", configured, "Piper")]
    return [sys.executable, "-m", "piper"]


def _run(command: list[str], *, input_text: str | None = None) -> None:
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LocalTTSError(f"เรียก local TTS ไม่สำเร็จ: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise LocalTTSError(detail or "local TTS ทำงานไม่สำเร็จ")


def synthesize_mp3(text: str, language: str, output: Path) -> Path:
    """Create an MP3 entirely locally using Piper and FFmpeg.

    The caller must provision Piper and its voice model ahead of time. No
    download or HTTP request is made here.
    """
    spoken_text = text.strip()
    if not spoken_text:
        raise LocalTTSError("ไม่มีข้อความสำหรับสร้างเสียง")

    model = _model_path(language)
    piper = _piper_command()
    ffmpeg = _executable("HERMES_FFMPEG_COMMAND", "ffmpeg", "FFmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(prefix="hermes-tts-", suffix=".wav", dir=output.parent, delete=False) as wav_file:
        wav_path = Path(wav_file.name)
    try:
        _run([*piper, "--model", str(model), "--output_file", str(wav_path)], input_text=spoken_text)
        _run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "4", str(output)])
        if not output.is_file() or output.stat().st_size == 0:
            raise LocalTTSError("local TTS ไม่ได้สร้างไฟล์ MP3")
        return output
    finally:
        wav_path.unlink(missing_ok=True)
