"""Timer Pomodoro: 25 min estudo, 5 min descanso."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto


class PomodoroPhase(Enum):
    IDLE = auto()
    WORK = auto()
    BREAK = auto()


WORK_DURATION_SEC = 25 * 60
BREAK_DURATION_SEC = 5 * 60


@dataclass
class TimerSnapshot:
    phase: PomodoroPhase
    remaining_sec: int
    total_sec: int
    running: bool
    completed_work_sessions: int


class PomodoroTimer:
    def __init__(
        self,
        work_sec: int = WORK_DURATION_SEC,
        break_sec: int = BREAK_DURATION_SEC,
    ) -> None:
        self.work_sec = work_sec
        self.break_sec = break_sec
        self.phase = PomodoroPhase.IDLE
        self.remaining_sec = work_sec
        self.running = False
        self.completed_work_sessions = 0
        self._deadline: float | None = None

    @property
    def monitoring_active(self) -> bool:
        return self.running and self.phase == PomodoroPhase.WORK

    def start(self) -> None:
        if self.phase == PomodoroPhase.IDLE:
            self.phase = PomodoroPhase.WORK
            self.remaining_sec = self.work_sec
        self.running = True
        self._deadline = time.monotonic() + self.remaining_sec

    def pause(self) -> None:
        if self.running and self._deadline is not None:
            self.remaining_sec = max(0, int(round(self._deadline - time.monotonic())))
        self.running = False
        self._deadline = None

    def reset(self) -> None:
        self.phase = PomodoroPhase.IDLE
        self.remaining_sec = self.work_sec
        self.running = False
        self._deadline = None

    def set_durations(self, work_minutes: int, break_minutes: int) -> None:
        self.work_sec = max(1, int(work_minutes)) * 60
        self.break_sec = max(1, int(break_minutes)) * 60
        if self.phase == PomodoroPhase.IDLE:
            self.remaining_sec = self.work_sec
        elif self.phase == PomodoroPhase.WORK and not self.running:
            self.remaining_sec = self.work_sec
        elif self.phase == PomodoroPhase.BREAK and not self.running:
            self.remaining_sec = self.break_sec
        if self.running and self._deadline is not None:
            total = self.work_sec if self.phase == PomodoroPhase.WORK else self.break_sec
            elapsed = total - self.remaining_sec
            self.remaining_sec = max(0, total - elapsed)
            self._deadline = time.monotonic() + self.remaining_sec

    def skip_to_break(self) -> None:
        self.phase = PomodoroPhase.BREAK
        self.remaining_sec = self.break_sec
        if self.running:
            self._deadline = time.monotonic() + self.remaining_sec

    def skip_to_work(self) -> None:
        self.phase = PomodoroPhase.WORK
        self.remaining_sec = self.work_sec
        if self.running:
            self._deadline = time.monotonic() + self.remaining_sec

    def tick(self) -> TimerSnapshot:
        if self.running and self._deadline is not None:
            self.remaining_sec = max(0, int(round(self._deadline - time.monotonic())))
            if self.remaining_sec <= 0:
                self._advance_phase()

        total = self.work_sec if self.phase == PomodoroPhase.WORK else self.break_sec
        if self.phase == PomodoroPhase.IDLE:
            total = self.work_sec

        return TimerSnapshot(
            phase=self.phase,
            remaining_sec=self.remaining_sec,
            total_sec=total,
            running=self.running,
            completed_work_sessions=self.completed_work_sessions,
        )

    def _advance_phase(self) -> None:
        if self.phase == PomodoroPhase.WORK:
            self.completed_work_sessions += 1
            self.phase = PomodoroPhase.BREAK
            self.remaining_sec = self.break_sec
        elif self.phase == PomodoroPhase.BREAK:
            self.phase = PomodoroPhase.WORK
            self.remaining_sec = self.work_sec
        else:
            self.phase = PomodoroPhase.WORK
            self.remaining_sec = self.work_sec

        if self.running:
            self._deadline = time.monotonic() + self.remaining_sec

    @staticmethod
    def format_time(seconds: int) -> str:
        minutes, secs = divmod(max(0, seconds), 60)
        return f"{minutes:02d}:{secs:02d}"
