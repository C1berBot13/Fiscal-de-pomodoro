"""Interface visual para recorte da waveform do áudio."""

import subprocess
import threading
import wave
from pathlib import Path
from tkinter import Canvas, messagebox

import customtkinter as ctk
import numpy as np
import pygame

from pomodoro_vision.alarm import _ffmpeg_path, build_alarm_clip, ASSETS_DIR


class AudioClipEditor(ctk.CTkToplevel):
    def __init__(self, parent, audio_path: Path, current_start: float, current_duration: float, on_apply):
        super().__init__(parent)
        self.title("Editor de Áudio")
        self.geometry("800x400")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()

        self.audio_path = audio_path
        self.on_apply = on_apply
        self.total_duration_sec = 0.0
        self.start_sec = current_start
        self.duration_sec = current_duration
        self.pixels_per_second = 0.0
        
        self.temp_pcm_path = ASSETS_DIR / "temp_preview.wav"
        self.preview_clip_path = ASSETS_DIR / "temp_clip.wav"

        # UI
        self.status_label = ctk.CTkLabel(self, text="Carregando áudio...", font=ctk.CTkFont(size=14))
        self.status_label.pack(pady=20)
        
        self.canvas_width = 760
        self.canvas_height = 200
        
        # Container for canvas to allow padding and borders
        self.canvas_frame = ctk.CTkFrame(self, width=self.canvas_width, height=self.canvas_height)
        self.canvas_frame.pack(pady=10)
        
        self.canvas = Canvas(
            self.canvas_frame, 
            width=self.canvas_width, 
            height=self.canvas_height,
            bg="#1c2438", 
            highlightthickness=0
        )
        self.canvas.pack()

        # Controls
        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_frame.pack(pady=10, fill="x", padx=20)
        
        self.info_label = ctk.CTkLabel(self.controls_frame, text="", font=ctk.CTkFont(size=12))
        self.info_label.pack(side="left", padx=10)

        self.apply_btn = ctk.CTkButton(self.controls_frame, text="Aplicar", fg_color="#10b981", hover_color="#059669", command=self._apply)
        self.apply_btn.pack(side="right", padx=10)
        self.apply_btn.configure(state="disabled")

        self.play_btn = ctk.CTkButton(self.controls_frame, text="Ouvir Seleção", fg_color="#3d5afe", hover_color="#2f49d0", command=self._play_selection)
        self.play_btn.pack(side="right", padx=10)
        self.play_btn.configure(state="disabled")

        # Bind events
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)

        # Inicia extração em background
        threading.Thread(target=self._load_waveform, daemon=True).start()

    def _load_waveform(self):
        try:
            ffmpeg = _ffmpeg_path()
            # Converte para WAV mono, 8000Hz para análise rápida
            self.temp_pcm_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(self.audio_path),
                    "-ac", "1", "-ar", "8000",
                    str(self.temp_pcm_path)
                ],
                capture_output=True,
                check=True,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )

            with wave.open(str(self.temp_pcm_path), "rb") as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                self.total_duration_sec = nframes / framerate
                
                audio_data = wf.readframes(nframes)
                # Convert to numpy array based on sample width (assume 16-bit)
                if wf.getsampwidth() == 2:
                    samples = np.frombuffer(audio_data, dtype=np.int16)
                else:
                    samples = np.frombuffer(audio_data, dtype=np.uint8) - 128
                    
            if self.total_duration_sec == 0:
                raise ValueError("Áudio muito curto ou corrompido.")

            # Sanitize current selection
            if self.start_sec >= self.total_duration_sec:
                self.start_sec = 0.0
            
            # Downsample to canvas width
            samples_per_pixel = max(1, len(samples) // self.canvas_width)
            # Truncate samples to fit exactly into shaped blocks
            pad_size = (samples_per_pixel - len(samples) % samples_per_pixel) % samples_per_pixel
            if pad_size > 0:
                samples = np.pad(samples, (0, pad_size))
            
            blocks = samples.reshape(-1, samples_per_pixel)
            
            # Use max amplitude per block
            amplitudes = np.max(np.abs(blocks), axis=1)
            
            # Normalize to canvas height
            max_amp = np.max(amplitudes) if np.max(amplitudes) > 0 else 1
            normalized = (amplitudes / max_amp) * (self.canvas_height / 2.0)
            
            self.after(0, self._draw_waveform, normalized)
            
        except Exception as e:
            self.after(0, self._show_error, str(e))

    def _show_error(self, err_msg):
        self.status_label.configure(text=f"Erro ao carregar: {err_msg}", text_color="red")
        
    def _draw_waveform(self, amplitudes):
        self.status_label.configure(text="Arraste o mouse no gráfico para selecionar o trecho (5 a 10 seg).")
        self.canvas.delete("all")
        
        mid_y = self.canvas_height / 2
        for x, amp in enumerate(amplitudes):
            # Limita a largura ao canvas
            if x >= self.canvas_width:
                break
            self.canvas.create_line(x, mid_y - amp, x, mid_y + amp, fill="#6cb6ff")

        self.pixels_per_second = self.canvas_width / self.total_duration_sec
        self._update_selection_box()
        self.apply_btn.configure(state="normal")
        self.play_btn.configure(state="normal")

    def _update_selection_box(self):
        self.canvas.delete("selection")
        
        if self.duration_sec < 5.0:
            self.duration_sec = 5.0
        elif self.duration_sec > 10.0:
            self.duration_sec = 10.0

        if self.start_sec + self.duration_sec > self.total_duration_sec:
            self.start_sec = max(0.0, self.total_duration_sec - self.duration_sec)
            
        x1 = self.start_sec * self.pixels_per_second
        x2 = (self.start_sec + self.duration_sec) * self.pixels_per_second

        # Draw semi-transparent selection. Tkinter doesn't do alpha well, so we draw a stipple or outline
        self.canvas.create_rectangle(x1, 0, x2, self.canvas_height, outline="#ffb347", width=3, tags="selection")
        self.canvas.create_rectangle(x1, 0, x2, self.canvas_height, fill="#ffb347", stipple="gray25", tags="selection")
        
        self.info_label.configure(text=f"Início: {self.start_sec:.1f}s | Duração: {self.duration_sec:.1f}s")

    def _on_canvas_press(self, event):
        self._update_selection_from_mouse(event.x)

    def _on_canvas_drag(self, event):
        self._update_selection_from_mouse(event.x)

    def _update_selection_from_mouse(self, x):
        if self.pixels_per_second == 0:
            return
            
        # Center the selection around the click, but keep duration fixed
        center_sec = x / self.pixels_per_second
        self.start_sec = center_sec - (self.duration_sec / 2)
        
        # Clamping
        if self.start_sec < 0:
            self.start_sec = 0.0
        if self.start_sec + self.duration_sec > self.total_duration_sec:
            self.start_sec = max(0.0, self.total_duration_sec - self.duration_sec)
            
        self._update_selection_box()

    def _play_selection(self):
        self.play_btn.configure(state="disabled", text="Extraindo...")
        threading.Thread(target=self._extract_and_play, daemon=True).start()

    def _extract_and_play(self):
        try:
            build_alarm_clip(self.audio_path, self.preview_clip_path, self.start_sec, self.duration_sec)
            
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            sound = pygame.mixer.Sound(str(self.preview_clip_path))
            sound.set_volume(1.0)
            
            self.after(0, lambda: self.play_btn.configure(text="Tocando..."))
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(50)
            
            self.after(0, lambda: self.play_btn.configure(state="normal", text="Ouvir Seleção"))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Erro", f"Não foi possível tocar o preview: {e}"))
            self.after(0, lambda: self.play_btn.configure(state="normal", text="Ouvir Seleção"))

    def _apply(self):
        pygame.mixer.stop() # Stop any preview
        self.on_apply(self.audio_path, self.start_sec, self.duration_sec)
        self.destroy()
