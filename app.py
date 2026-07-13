"""Interface principal do Fiscal de Pomodoro."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from pomodoro_vision.alarm import AlarmPlayer, ASSETS_DIR
from pomodoro_vision.timer import PomodoroPhase, PomodoroTimer
from pomodoro_vision.vision_monitor import VisionMonitor

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#0b1020",
    "panel": "#151b2e",
    "panel_alt": "#1c2438",
    "work": "#ff5d5d",
    "break": "#45d483",
    "idle": "#6cb6ff",
    "text": "#eef2ff",
    "muted": "#9aa8c7",
    "warn": "#ffb347",
}


class PomodoroVisionApp(ctk.CTk):
    TICK_MS = 80
    CAMERA_INDEX = 0

    def __init__(self) -> None:
        super().__init__(fg_color=COLORS["bg"])

        self.title("Fiscal de Pomodoro")
        self.geometry("1120x820")
        self.minsize(1020, 780)

        self.timer = PomodoroTimer()
        self.monitor = VisionMonitor()
        self.alarm = AlarmPlayer()
        self.alarm.init_mixer()

        self._cap: cv2.VideoCapture | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._after_id: str | None = None
        self._closing = False
        self._pulse_on = False
        self._last_focus = 100
        self._previous_phase: PomodoroPhase = PomodoroPhase.IDLE
        self._mini_widget: MiniTimerWidget | None = None

        self._build_ui()
        self._open_camera()
        self._apply_timer_settings()
        self._load_alarm_ui_from_config()
        self._schedule_tick()
        self._schedule_pulse()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=18)
        left.grid(row=0, column=0, padx=(18, 8), pady=18, sticky="nsew")
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="Monitoramento ao vivo",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, padx=18, pady=(18, 4), sticky="w")

        ctk.CTkLabel(
            left,
            text="A câmera acompanha postura, olhar, presença e uso de celular.",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")

        self.camera_label = ctk.CTkLabel(
            left,
            text="",
            fg_color=COLORS["panel_alt"],
            corner_radius=14,
        )
        self.camera_label.grid(row=2, column=0, padx=18, pady=(0, 12), sticky="nsew")

        self.focus_bar = ctk.CTkProgressBar(left, height=14, corner_radius=8)
        self.focus_bar.grid(row=3, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.focus_bar.set(1.0)

        self.focus_label = ctk.CTkLabel(
            left,
            text="Índice de foco: 100%",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        )
        self.focus_label.grid(row=4, column=0, padx=18, pady=(0, 16), sticky="w")

        right = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=18)
        right.grid(row=0, column=1, padx=(8, 18), pady=18, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="Fiscal de Pomodoro",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, padx=20, pady=(20, 4), sticky="w")

        self.phase_badge = ctk.CTkLabel(
            right,
            text="Pronto para começar",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["panel_alt"],
            corner_radius=20,
            height=32,
            padx=14,
        )
        self.phase_badge.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

        self.time_label = ctk.CTkLabel(
            right,
            text="25:00",
            font=ctk.CTkFont(size=64, weight="bold"),
            text_color=COLORS["text"],
        )
        self.time_label.grid(row=2, column=0, padx=20, pady=(0, 8))

        self.timer_progress = ctk.CTkProgressBar(right, height=16, corner_radius=8)
        self.timer_progress.grid(row=3, column=0, padx=20, pady=(0, 14), sticky="ew")
        self.timer_progress.set(1.0)

        self.status_card = ctk.CTkFrame(right, fg_color=COLORS["panel_alt"], corner_radius=14)
        self.status_card.grid(row=4, column=0, padx=20, pady=(0, 14), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.status_card,
            text="Quando iniciar, vou te avisar se você perder o foco.",
            font=ctk.CTkFont(size=14),
            wraplength=340,
            justify="left",
            text_color=COLORS["text"],
        )
        self.status_label.pack(padx=16, pady=16, anchor="w")

        settings = ctk.CTkFrame(right, fg_color=COLORS["panel_alt"], corner_radius=14)
        settings.grid(row=5, column=0, padx=20, pady=(0, 14), sticky="ew")
        settings.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            settings,
            text="Ajuste dos tempos",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(12, 8), sticky="w")

        ctk.CTkLabel(settings, text="Estudo (min)", text_color=COLORS["muted"]).grid(
            row=1, column=0, padx=14, pady=(0, 4), sticky="w"
        )
        ctk.CTkLabel(settings, text="Descanso (min)", text_color=COLORS["muted"]).grid(
            row=1, column=1, padx=14, pady=(0, 4), sticky="w"
        )

        self.work_var = ctk.StringVar(value="25")
        self.break_var = ctk.StringVar(value="5")

        self.work_entry = ctk.CTkEntry(
            settings, textvariable=self.work_var, width=120, justify="center"
        )
        self.work_entry.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")

        self.break_entry = ctk.CTkEntry(
            settings, textvariable=self.break_var, width=120, justify="center"
        )
        self.break_entry.grid(row=2, column=1, padx=14, pady=(0, 12), sticky="ew")

        ctk.CTkButton(
            settings,
            text="Aplicar tempos",
            command=self._apply_timer_settings,
            fg_color="#3d5afe",
            hover_color="#2f49d0",
        ).grid(row=3, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="ew")

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_btn = ctk.CTkButton(
            btn_row,
            text="Iniciar",
            command=self._start,
            fg_color=COLORS["work"],
            hover_color="#e14b4b",
            height=40,
        )
        self.start_btn.grid(row=0, column=0, padx=4, sticky="ew")

        self.pause_btn = ctk.CTkButton(
            btn_row,
            text="Pausar",
            command=self._pause,
            fg_color="#4b5568",
            hover_color="#3b4354",
            height=40,
        )
        self.pause_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.reset_btn = ctk.CTkButton(
            btn_row,
            text="Reiniciar",
            command=self._reset,
            fg_color="#64748b",
            hover_color="#526072",
            height=40,
        )
        self.reset_btn.grid(row=0, column=2, padx=4, sticky="ew")

        ctk.CTkButton(
            right,
            text="Testar alarme",
            command=self._test_alarm,
            fg_color="#8b5cf6",
            hover_color="#7446d6",
            height=36,
        ).grid(row=7, column=0, padx=20, pady=(0, 6), sticky="ew")

        ctk.CTkButton(
            right,
            text="🗕 Modo Widget",
            command=self._enter_mini_mode,
            fg_color="#f59e0b",
            hover_color="#d97706",
            height=36,
        ).grid(row=8, column=0, padx=20, pady=(0, 12), sticky="ew")

        # Frame de Configurações do Alarme
        alarm_settings = ctk.CTkFrame(right, fg_color=COLORS["panel_alt"], corner_radius=14)
        alarm_settings.grid(row=9, column=0, padx=20, pady=(0, 14), sticky="ew")
        alarm_settings.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            alarm_settings,
            text="Configurações do Alarme",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(12, 8), sticky="w")

        self.audio_name_label = ctk.CTkLabel(
            alarm_settings,
            text="Áudio: Padrão (Irritante)",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            anchor="w",
            wraplength=320,
        )
        self.audio_name_label.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 8), sticky="ew")

        self.select_audio_btn = ctk.CTkButton(
            alarm_settings,
            text="Escolher Arquivo",
            command=self._select_custom_audio,
            fg_color="#3d5afe",
            hover_color="#2f49d0",
            height=28,
        )
        self.select_audio_btn.grid(row=2, column=0, padx=(14, 6), pady=(0, 12), sticky="ew")

        self.default_audio_btn = ctk.CTkButton(
            alarm_settings,
            text="Usar Padrão",
            command=self._reset_to_default_audio,
            fg_color="#4b5568",
            hover_color="#3b4354",
            height=28,
        )
        self.default_audio_btn.grid(row=2, column=1, padx=(6, 14), pady=(0, 12), sticky="ew")

        self.alarm_label = ctk.CTkLabel(
            right,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
            wraplength=360,
            justify="left",
        )
        self.alarm_label.grid(row=10, column=0, padx=20, pady=(0, 6), sticky="w")

        self.sessions_label = ctk.CTkLabel(
            right,
            text="Sessões concluídas: 0",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        )
        self.sessions_label.grid(row=11, column=0, padx=20, pady=(0, 18), sticky="w")

    def _refresh_alarm_label(self) -> None:
        if self.alarm.is_ready:
            text = f"Alarme pronto: {self.alarm.source_path.name}"
        elif self.alarm.source_path is not None:
            text = f"Problema no alarme: {self.alarm.error}"
        else:
            text = f"Coloque um audio em {ASSETS_DIR}"
        self.alarm_label.configure(text=text)

    def _parse_minutes(self, value: str, default: int) -> int:
        try:
            minutes = int(value.strip())
            return max(1, min(180, minutes))
        except ValueError:
            return default

    def _apply_timer_settings(self) -> None:
        work = self._parse_minutes(self.work_var.get(), 25)
        break_m = self._parse_minutes(self.break_var.get(), 5)
        self.work_var.set(str(work))
        self.break_var.set(str(break_m))
        self.timer.set_durations(work, break_m)
        self._update_timer_ui(self.timer.tick())

    def _open_camera(self) -> None:
        self._cap = cv2.VideoCapture(self.CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.CAMERA_INDEX)
        if not self._cap.isOpened():
            messagebox.showerror(
                "Camera",
                "Não foi possível abrir a câmera.\n"
                "Verifique se outro aplicativo não está usando ela.",
            )

    def _start(self) -> None:
        self._apply_timer_settings()
        self.timer.start()
        self.monitor.reset_violation_timers()
        self._enter_mini_mode()

    def _pause(self) -> None:
        self.timer.pause()
        self.monitor.reset_violation_timers()

    def _reset(self) -> None:
        self.timer.reset()
        self.monitor.reset_violation_timers()
        self._apply_timer_settings()

    def _test_alarm(self) -> None:
        self.alarm.reload()
        self._refresh_alarm_label()
        if not self.alarm.is_ready:
            messagebox.showwarning(
                "Alarme",
                self.alarm.error or "Nenhum áudio válido encontrado na pasta assets.",
            )
            return
        self.alarm.play()

    def _select_custom_audio(self) -> None:
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="Selecionar Áudio de Alarme",
            filetypes=[("Arquivos de Áudio", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac"), ("Todos os Arquivos", "*.*")]
        )
        if file_path:
            from pomodoro_vision.alarm import load_config
            from pomodoro_vision.audio_editor import AudioClipEditor
            config = load_config()
            current_start = config.get("alarm_start_sec", 0.0)
            current_duration = config.get("alarm_duration_sec", 5.0)
            
            # Abre o editor visual
            AudioClipEditor(
                self, 
                Path(file_path), 
                current_start, 
                current_duration, 
                self._on_audio_edited
            )

    def _on_audio_edited(self, audio_path: Path, start_sec: float, duration_sec: float) -> None:
        from pomodoro_vision.alarm import load_config, save_config
        config = load_config()
        config["custom_audio_path"] = str(audio_path)
        config["alarm_start_sec"] = start_sec
        config["alarm_duration_sec"] = duration_sec
        save_config(config)
        
        self._load_alarm_ui_from_config()
        messagebox.showinfo("Alarme Salvo", "Configurações do alarme atualizadas e áudio processado com sucesso!")
            
    def _reset_to_default_audio(self) -> None:
        from pomodoro_vision.alarm import load_config, save_config
        config = load_config()
        config["custom_audio_path"] = None
        save_config(config)
        self._load_alarm_ui_from_config()

    def _load_alarm_ui_from_config(self) -> None:
        from pomodoro_vision.alarm import load_config
        config = load_config()
        custom_path = config.get("custom_audio_path")
        if custom_path:
            self.audio_name_label.configure(text=f"Áudio: {Path(custom_path).name}")
        else:
            self.audio_name_label.configure(text="Áudio: Padrão (Irritante)")
            
        self.alarm.reload()
        self._refresh_alarm_label()

    def _schedule_tick(self) -> None:
        if not self._closing:
            self._after_id = self.after(self.TICK_MS, self._tick)

    def _schedule_pulse(self) -> None:
        if not self._closing:
            self._pulse_on = not self._pulse_on
            if self.timer.running and self.timer.phase == PomodoroPhase.WORK:
                color = COLORS["work"] if self._pulse_on else "#ff7a7a"
                self.phase_badge.configure(fg_color=color)
            self.after(600, self._schedule_pulse)

    def _tick(self) -> None:
        snapshot = self.timer.tick()
        self._update_timer_ui(snapshot)

        # Detecta transição WORK -> BREAK para aviso de descanso
        if self._previous_phase == PomodoroPhase.WORK and snapshot.phase == PomodoroPhase.BREAK:
            self.alarm.stop()
            self.alarm.play_break_warning()
        self._previous_phase = snapshot.phase

        # Atualiza o mini widget se existir
        if self._mini_widget is not None and self._mini_widget.winfo_exists():
            self._mini_widget.update_display(snapshot)

        if self._cap is not None and self._cap.isOpened():
            ok, frame = self._cap.read()
            if ok:
                annotated, status, should_alarm, should_warn_posture = self.monitor.process(
                    frame,
                    monitoring=self.timer.monitoring_active,
                )
                if should_alarm:
                    self.alarm.play()
                elif should_warn_posture:
                    self.alarm.play_posture_warning()

                # Se o alarme está tocando e o usuário recuperou o foco, para o alarme
                if self.alarm.is_playing and not status.active_violations:
                    self.alarm.stop()

                self._update_camera(annotated)
                self._update_status_label(status, snapshot.phase)
                self._update_focus_ui(status.focus_score, status.active_violations)

        self._schedule_tick()

    def _update_timer_ui(self, snapshot) -> None:
        self.time_label.configure(text=PomodoroTimer.format_time(snapshot.remaining_sec))

        if snapshot.total_sec > 0:
            progress = snapshot.remaining_sec / snapshot.total_sec
        else:
            progress = 1.0
        self.timer_progress.set(max(0.0, min(1.0, progress)))

        phase_map = {
            PomodoroPhase.IDLE: ("Pronto para começar", COLORS["idle"]),
            PomodoroPhase.WORK: ("Sessão de estudo ativa", COLORS["work"]),
            PomodoroPhase.BREAK: ("Hora do descanso", COLORS["break"]),
        }
        text, color = phase_map[snapshot.phase]
        self.phase_badge.configure(text=text, fg_color=color)

        progress_color = {
            PomodoroPhase.IDLE: COLORS["idle"],
            PomodoroPhase.WORK: COLORS["work"],
            PomodoroPhase.BREAK: COLORS["break"],
        }[snapshot.phase]
        self.timer_progress.configure(progress_color=progress_color)

        self.sessions_label.configure(
            text=f"Sessões concluídas: {snapshot.completed_work_sessions}"
        )

    def _update_status_label(self, status, phase: PomodoroPhase) -> None:
        if phase == PomodoroPhase.BREAK:
            self.status_label.configure(
                text="Descanso liberado. Sem alarmes, pode relaxar um pouco.",
                text_color=COLORS["break"],
            )
        elif phase == PomodoroPhase.WORK:
            if status.active_violations:
                self.status_label.configure(
                    text=status.violation_message,
                    text_color=COLORS["warn"],
                )
            else:
                self.status_label.configure(
                    text=status.violation_message,
                    text_color=COLORS["text"],
                )
        else:
            self.status_label.configure(
                text="Quando iniciar, vou te avisar se você perder o foco.",
                text_color=COLORS["muted"],
            )

    def _update_focus_ui(self, focus: int, violations) -> None:
        self.focus_bar.set(focus / 100.0)
        self.focus_label.configure(text=f"Índice de foco: {focus}%")
        if violations:
            self.focus_bar.configure(progress_color=COLORS["warn"])
        elif focus >= 80:
            self.focus_bar.configure(progress_color=COLORS["break"])
        else:
            self.focus_bar.configure(progress_color=COLORS["work"])

    def _update_camera(self, frame_bgr) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((720, 540), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image=img)
        self.camera_label.configure(image=self._photo, text="")

    def _enter_mini_mode(self) -> None:
        """Oculta a janela principal e abre o widget flutuante."""
        if self._mini_widget is not None and self._mini_widget.winfo_exists():
            return
        self._mini_widget = MiniTimerWidget(self)
        self.withdraw()

    def _exit_mini_mode(self) -> None:
        """Restaura a janela principal e fecha o widget flutuante."""
        if self._mini_widget is not None and self._mini_widget.winfo_exists():
            self._mini_widget.destroy()
        self._mini_widget = None
        self.deiconify()

    def _on_close(self) -> None:
        self._closing = True
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        if self._mini_widget is not None and self._mini_widget.winfo_exists():
            self._mini_widget.destroy()
        if self._cap is not None:
            self._cap.release()
        self.monitor.close()
        self.destroy()


class MiniTimerWidget(ctk.CTkToplevel):
    """Widget flutuante, arrastável e sem bordas para exibir o timer Pomodoro."""

    def __init__(self, app: PomodoroVisionApp) -> None:
        super().__init__(fg_color="#0d1117")
        self._app = app

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.92)
        self.geometry("260x100+50+50")
        self.resizable(False, False)

        # Variáveis para arrastar
        self._drag_x = 0
        self._drag_y = 0

        # Frame principal com borda arredondada visual
        main_frame = ctk.CTkFrame(self, fg_color="#161b28", corner_radius=16)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        main_frame.grid_columnconfigure(0, weight=1)

        # Header arrastável
        header = ctk.CTkFrame(main_frame, fg_color="transparent", height=6)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.bind("<Button-1>", self._on_drag_start)
        header.bind("<B1-Motion>", self._on_drag_motion)

        # Barra de arraste visual (grippy)
        grip = ctk.CTkLabel(
            header, text="⋯", font=ctk.CTkFont(size=14),
            text_color="#555e70", cursor="fleur",
        )
        grip.pack(pady=(2, 0))
        grip.bind("<Button-1>", self._on_drag_start)
        grip.bind("<B1-Motion>", self._on_drag_motion)

        # Badge de fase
        self._phase_label = ctk.CTkLabel(
            main_frame, text="⏱ Estudo",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#9aa8c7",
        )
        self._phase_label.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 2), sticky="w")

        # Timer grande
        self._time_label = ctk.CTkLabel(
            main_frame, text="25:00",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color="#eef2ff",
        )
        self._time_label.grid(row=2, column=0, padx=(14, 4), pady=(0, 4), sticky="w")
        self._time_label.bind("<Button-1>", self._on_drag_start)
        self._time_label.bind("<B1-Motion>", self._on_drag_motion)

        # Botões compactos
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=1, columnspan=2, padx=(0, 10), pady=(0, 4), sticky="e")

        self._play_btn = ctk.CTkButton(
            btn_frame, text="⏸", width=34, height=28,
            font=ctk.CTkFont(size=14),
            fg_color="#4b5568", hover_color="#3b4354",
            command=self._toggle_play_pause,
        )
        self._play_btn.pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="⏭", width=34, height=28,
            font=ctk.CTkFont(size=14),
            fg_color="#64748b", hover_color="#526072",
            command=self._skip_phase,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="⬜", width=34, height=28,
            font=ctk.CTkFont(size=14),
            fg_color="#3d5afe", hover_color="#2f49d0",
            command=self._expand,
        ).pack(side="left", padx=2)

    def _on_drag_start(self, event) -> None:
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag_motion(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def update_display(self, snapshot) -> None:
        self._time_label.configure(text=PomodoroTimer.format_time(snapshot.remaining_sec))

        phase_map = {
            PomodoroPhase.IDLE: ("⏱ Pronto", "#6cb6ff"),
            PomodoroPhase.WORK: ("📖 Estudo", "#ff5d5d"),
            PomodoroPhase.BREAK: ("☕ Descanso", "#45d483"),
        }
        text, color = phase_map[snapshot.phase]
        self._phase_label.configure(text=text, text_color=color)

        if snapshot.running:
            self._play_btn.configure(text="⏸")
        else:
            self._play_btn.configure(text="▶")

    def _toggle_play_pause(self) -> None:
        if self._app.timer.running:
            self._app._pause()
        else:
            self._app._start()

    def _skip_phase(self) -> None:
        if self._app.timer.phase == PomodoroPhase.WORK:
            self._app.timer.skip_to_break()
        else:
            self._app.timer.skip_to_work()

    def _expand(self) -> None:
        self._app._exit_mini_mode()


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    app = PomodoroVisionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
