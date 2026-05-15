from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KillSwitch:
    active: bool = False
    reason: str | None = None

    def activate(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("reason must not be empty")
        self.active = True
        self.reason = reason

    def deactivate(self) -> None:
        self.active = False
        self.reason = None

    def status(self) -> tuple[bool, str | None]:
        return self.active, self.reason
