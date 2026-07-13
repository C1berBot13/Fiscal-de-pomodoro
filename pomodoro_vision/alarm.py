"""Reprodução e configuração do alarme e avisos sonoros."""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import threading
import wave
from pathlib import Path

import imageio_ffmpeg
import pygame

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CLIP_CACHE = ASSETS_DIR / "_alarm_clip.wav"
CONFIG_FILE = ASSETS_DIR / "config.json"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}


def generate_default_annoying_alarm(dest_path: Path, duration_sec: float = 10.0) -> None:
    """Gera um alarme muito barulhento, irritante e de alta frequência (onda quadrada)."""
    if dest_path.is_file() and dest_path.stat().st_size > 0:
        return
    
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)
    
    data = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Alterna frequências de 2500Hz e 3500Hz a cada 0.15 segundos
        freq = 2500 if int(t / 0.15) % 2 == 0 else 3500
        
        # Padrão de bipe rápido: silêncio de 0.05s a cada 0.3s
        if (t % 0.3) < 0.05:
            val = 0
        else:
            # Onda quadrada no volume máximo (16-bit signed int)
            val = 32767 if math.sin(2 * math.pi * freq * t) >= 0 else -32768
            
        data.extend(struct.pack("<h", val))
        
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(data)


def generate_posture_warning_voice(dest_path: Path) -> None:
    """Sintetiza por voz 'Por favor, corrija a sua postura' via PowerShell, com fallback para bipe duplo."""
    if dest_path.is_file() and dest_path.stat().st_size > 0:
        return
    
    ps_script = f"""
    try {{
        Add-Type -AssemblyName System.Speech
        $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $synth.SetOutputToWaveFile('{dest_path}')
        $synth.Speak('Por favor, corrija a sua postura.')
        $synth.Dispose()
    }} catch {{
        exit 1
    }}
    """
    
    # Executa silenciosamente no Windows
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            check=True,
            creationflags=0x08000000
        )
    except Exception:
        # Fallback caso falhe: gera um bipe duplo diferenciado (sine wave)
        sample_rate = 44100
        duration_sec = 0.6
        num_samples = int(sample_rate * duration_sec)
        
        data = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Dois bipes em 1000Hz (0.0 a 0.15s, e 0.3s a 0.45s)
            is_beep = (0.0 <= t < 0.15) or (0.3 <= t < 0.45)
            if is_beep:
                val = int(20000 * math.sin(2 * math.pi * 1000 * t))
            else:
                val = 0
            data.extend(struct.pack("<h", val))
            
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(data)


def generate_break_warning_voice(dest_path: Path) -> None:
    """Sintetiza por voz 'Hora do descanso' via PowerShell, com fallback para bipe triplo."""
    if dest_path.is_file() and dest_path.stat().st_size > 0:
        return

    ps_script = f"""
    try {{
        Add-Type -AssemblyName System.Speech
        $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $synth.SetOutputToWaveFile('{dest_path}')
        $synth.Speak('Está no horário de descanso. Aproveite para relaxar.')
        $synth.Dispose()
    }} catch {{
        exit 1
    }}
    """

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            check=True,
            creationflags=0x08000000
        )
    except Exception:
        # Fallback: bipe triplo agradável em 800Hz
        sample_rate = 44100
        duration_sec = 0.9
        num_samples = int(sample_rate * duration_sec)

        data = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            is_beep = (0.0 <= t < 0.12) or (0.2 <= t < 0.32) or (0.4 <= t < 0.52)
            if is_beep:
                val = int(18000 * math.sin(2 * math.pi * 800 * t))
            else:
                val = 0
            data.extend(struct.pack("<h", val))

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(data)


def load_config() -> dict:
    """Lê as configurações de alarme personalizadas."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "custom_audio_path": None,
        "alarm_start_sec": 0.0,
        "alarm_duration_sec": 5.0,
    }


def save_config(config: dict) -> None:
    """Salva as configurações de alarme personalizadas."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def _ffmpeg_path() -> str:
    bundled = imageio_ffmpeg.get_ffmpeg_exe()
    if bundled and Path(bundled).is_file():
        return bundled
    system = shutil.which("ffmpeg")
    if system:
        return system
    raise RuntimeError("FFmpeg não disponível")


def _extract_wav_segment(
    source: Path,
    dest: Path,
    start_sec: float,
    duration_sec: float,
) -> None:
    with wave.open(str(source), "rb") as audio:
        rate = audio.getframerate()
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        start_frame = int(start_sec * rate)
        end_frame = min(int((start_sec + duration_sec) * rate), audio.getnframes())
        if end_frame <= start_frame:
            start_frame = 0
            end_frame = min(int(duration_sec * rate), audio.getnframes())
        audio.setpos(start_frame)
        frames = audio.readframes(end_frame - start_frame)

    with wave.open(str(dest), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(frames)


def _extract_with_ffmpeg(
    source: Path,
    dest: Path,
    start_sec: float,
    duration_sec: float,
) -> None:
    ffmpeg = _ffmpeg_path()
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-ss",
            str(start_sec),
            "-t",
            str(duration_sec),
            "-ac",
            "2",
            "-ar",
            "44100",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Falha ao recortar áudio: {detail[-300:]}")


def build_alarm_clip(
    source: Path,
    dest: Path = CLIP_CACHE,
    start_sec: float = 0.0,
    duration_sec: float = 5.0,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".wav":
        _extract_wav_segment(source, dest, start_sec, duration_sec)
    else:
        _extract_with_ffmpeg(source, dest, start_sec, duration_sec)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("Arquivo de alarme gerado vazio")



class AlarmPlayer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playing = False
        self._clip_path: Path | None = None
        self._source_path: Path | None = None
        self._source_mtime: float = 0.0
        self._cached_start_sec: float = -1.0
        self._cached_duration_sec: float = -1.0
        self._error: str | None = None
        self._sound: pygame.mixer.Sound | None = None
        self._posture_sound: pygame.mixer.Sound | None = None
        self._break_sound: pygame.mixer.Sound | None = None
        self._alarm_channel: pygame.mixer.Channel | None = None
        self._mixer_ready = False
        
        # Gera os arquivos padrão no início
        generate_default_annoying_alarm(ASSETS_DIR / "default_alarm.wav")
        generate_posture_warning_voice(ASSETS_DIR / "posture_warning.wav")
        generate_break_warning_voice(ASSETS_DIR / "break_warning.wav")
        
        self._prepare_clip()

    def init_mixer(self) -> None:
        if not self._mixer_ready:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._mixer_ready = True

    def _prepare_clip(self) -> None:
        self._error = None
        config = load_config()
        custom_path_str = config.get("custom_audio_path")
        start_sec = float(config.get("alarm_start_sec", 0.0))
        duration_sec = float(config.get("alarm_duration_sec", 5.0))
        
        source_path: Path | None = None
        if custom_path_str:
            p = Path(custom_path_str)
            if p.is_file():
                source_path = p
                
        if source_path is None:
            source_path = ASSETS_DIR / "default_alarm.wav"

        try:
            mtime = source_path.stat().st_mtime
            if (
                self._clip_path
                and self._clip_path.is_file()
                and self._source_path == source_path
                and mtime == self._source_mtime
                and self._cached_start_sec == start_sec
                and self._cached_duration_sec == duration_sec
            ):
                return

            build_alarm_clip(source_path, CLIP_CACHE, start_sec, duration_sec)
            self._clip_path = CLIP_CACHE
            self._source_path = source_path
            self._source_mtime = mtime
            self._cached_start_sec = start_sec
            self._cached_duration_sec = duration_sec

            if self._mixer_ready:
                self._sound = pygame.mixer.Sound(str(CLIP_CACHE))
        except Exception as exc:
            self._clip_path = None
            self._source_path = source_path
            self._sound = None
            self._error = str(exc)

    @property
    def is_ready(self) -> bool:
        return self._clip_path is not None and self._clip_path.is_file()

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def is_playing(self) -> bool:
        return self._playing

    def reload(self) -> None:
        with self._lock:
            self._source_mtime = 0.0
            self._prepare_clip()
            if self._mixer_ready and self._clip_path:
                self._sound = pygame.mixer.Sound(str(self._clip_path))

    def play(self) -> None:
        self.reload()
        if self._clip_path is None:
            return

        with self._lock:
            if self._playing:
                return
            self._playing = True

        def _run() -> None:
            try:
                if not self._mixer_ready:
                    self.init_mixer()
                if self._sound is None:
                    self._sound = pygame.mixer.Sound(str(self._clip_path))
                self._sound.set_volume(1.0)
                channel = self._sound.play()
                with self._lock:
                    self._alarm_channel = channel
                if channel is not None:
                    while channel.get_busy():
                        pygame.time.wait(50)
            except Exception as exc:
                self._error = str(exc)
            finally:
                with self._lock:
                    self._playing = False
                    self._alarm_channel = None

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        """Para o alarme principal imediatamente quando o usuário recupera o foco."""
        with self._lock:
            if self._alarm_channel is not None and self._alarm_channel.get_busy():
                self._alarm_channel.stop()
                self._alarm_channel = None
            self._playing = False

    def play_posture_warning(self) -> None:
        """Toca o aviso de postura na segunda linha de áudio sem parar o alarme principal."""
        warning_path = ASSETS_DIR / "posture_warning.wav"
        if not warning_path.is_file():
            generate_posture_warning_voice(warning_path)
            
        if not warning_path.is_file():
            return
            
        with self._lock:
            if not self._mixer_ready:
                self.init_mixer()
            try:
                if self._posture_sound is None:
                    self._posture_sound = pygame.mixer.Sound(str(warning_path))
                
                # Executa no canal 1 para não sobrepor outros sons se estiver tocando
                channel = pygame.mixer.Channel(1)
                if not channel.get_busy():
                    channel.play(self._posture_sound)
            except Exception as exc:
                self._error = f"Erro no aviso de postura: {exc}"

    def play_break_warning(self) -> None:
        """Toca o aviso de descanso em um canal dedicado."""
        warning_path = ASSETS_DIR / "break_warning.wav"
        if not warning_path.is_file():
            generate_break_warning_voice(warning_path)

        if not warning_path.is_file():
            return

        with self._lock:
            if not self._mixer_ready:
                self.init_mixer()
            try:
                if self._break_sound is None:
                    self._break_sound = pygame.mixer.Sound(str(warning_path))

                channel = pygame.mixer.Channel(2)
                if not channel.get_busy():
                    channel.play(self._break_sound)
            except Exception as exc:
                self._error = f"Erro no aviso de descanso: {exc}"

    def test(self) -> bool:
        """Toca o alarme imediatamente (para teste na interface)."""
        self.play()
        return self.is_ready
