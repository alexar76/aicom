"""Should this cycle run at all — and if the factory is held, what still moves.

Three separate decisions used to sit inline at the top of a 330-line cycle, where the only way
to exercise them was to run a worker against real state:

* a **hard stop** from the environment: nothing runs, full stop.
* **focus mode**: an operator has named the products they want worked on. That is honoured
  *through* the hold — the factory stays paused for everything else (Director analysis,
  discovery, auto-enqueue all still see it), but the named products keep moving instead of
  waiting for a full resume.
* a plain **soft hold**: nothing advances, and anything left `running` is put back to `pending`
  so a resumed factory does not inherit tasks whose runners died with the pause.

The last one is the subtle one. Leaving a task `running` across a hold means the recovery sweep
has to guess later whether a runner is alive; resetting it here makes the answer trivial, and it
is the only mutation this gate performs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HoldVerdict:
    """What the gate decided. The caller performs any persistence — this gate does no IO."""

    proceed: bool
    """Run the rest of the cycle. False means return now."""

    soft_hold: bool
    """The factory is held but the cycle still runs (currently only reached via focus mode,
    where it is False — kept explicit so a future partial hold has somewhere to live)."""

    reset_running: int = 0
    """How many tasks this gate moved from `running` back to `pending`. Non-zero means the caller
    must save with a full write: the queue changed under a hold, when nothing else will."""

    reason: str = ""
    """Operator-facing, and logged. A hold that does not say why is a hold nobody can lift."""

    focus_ids: tuple[str, ...] = ()


class HoldGate:
    """Reads the factory's pause switches. Injected so a test never touches the real ones."""

    def __init__(self, *, is_hard_stopped, is_on_hold, focus_ids):
        self._is_hard_stopped = is_hard_stopped
        self._is_on_hold = is_on_hold
        self._focus_ids = focus_ids

    @classmethod
    def from_defaults(cls) -> "HoldGate":
        from core.factory_hold import is_factory_hard_stopped, is_factory_on_hold
        from core.pipeline_product_pause import get_factory_focus_product_ids

        return cls(is_hard_stopped=is_factory_hard_stopped, is_on_hold=is_factory_on_hold,
                   focus_ids=get_factory_focus_product_ids)

    def hard_stopped(self) -> bool:
        """The one switch that means "touch nothing", asked separately.

        Startup repairs have to run under a soft hold — a task the last run died in is
        wreckage, not work — but never under a hard stop, where the instruction is to leave
        the state exactly as an operator found it.
        """
        return bool(self._is_hard_stopped())

    def evaluate(self, task_queue: list[dict[str, Any]]) -> HoldVerdict:
        if self._is_hard_stopped():
            return HoldVerdict(proceed=False, soft_hold=False,
                               reason="Factory hard-stopped (env) — skipping pipeline processing cycle")

        if not self._is_on_hold():
            return HoldVerdict(proceed=True, soft_hold=False)

        focus = tuple(self._focus_ids() or ())
        if focus:
            # Honoured THROUGH the hold: everything else stays paused, the named products move.
            return HoldVerdict(proceed=True, soft_hold=False, focus_ids=focus,
                               reason="Factory on hold — running focus products only: "
                                      + ", ".join(focus))

        reset = 0
        for task in task_queue:
            if str(task.get("status") or "").lower() == "running":
                task["status"] = "pending"
                reset += 1
        return HoldVerdict(proceed=False, soft_hold=True, reset_running=reset,
                           reason="Factory on hold")
