"""Per-station sequence tracking and rain accounting (docs/protocol.md section 5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

TIPS_MODULUS = 1 << 16  # rainfall_tips is uint16 and wraps


class SeqStatus(str, Enum):
    FIRST = "first"
    OK = "ok"
    DUPLICATE = "duplicate"
    GAP = "gap"
    RESET = "reset"


@dataclass(frozen=True)
class TrackResult:
    status: SeqStatus
    missing: int  # packets missing immediately before this one (GAP only)
    rain_tips_delta: int | None  # None when there is no baseline (FIRST) or for duplicates


@dataclass
class _StationState:
    sequence: int
    tips: int


def tips_to_mm(tips: int, mm_per_tip: float) -> float:
    return tips * mm_per_tip


def rain_tips_delta(previous_tips: int, current_tips: int) -> int:
    """Increase in a cumulative uint16 counter, allowing for wrap-around."""
    return (current_tips - previous_tips) % TIPS_MODULUS


class SequenceTracker:
    """Classify each packet by sequence and compute the rain increment.

    The tracker can be seeded from storage so a gateway restart doesn't lose
    the rain baseline.
    """

    def __init__(self) -> None:
        self._stations: dict[int, _StationState] = {}

    def seed(self, station_id: int, sequence: int, tips: int) -> None:
        self._stations[station_id] = _StationState(sequence, tips)

    def update(self, station_id: int, sequence: int, tips: int, boot: bool) -> TrackResult:
        state = self._stations.get(station_id)

        if state is None:
            self._stations[station_id] = _StationState(sequence, tips)
            # After a reboot the counter starts from zero, so the value itself
            # is the rain since boot; otherwise there is no baseline yet.
            return TrackResult(SeqStatus.FIRST, 0, tips if boot else None)

        # Checked before the BOOT flag so a repeated boot packet isn't counted twice.
        if sequence == state.sequence and tips == state.tips:
            return TrackResult(SeqStatus.DUPLICATE, 0, None)

        # Same sequence with different data can only be a restart whose BOOT
        # packet was lost, so it is treated as a reset.
        if boot or sequence <= state.sequence:
            return self._reset(state, sequence, tips)

        delta = rain_tips_delta(state.tips, tips)
        missing = sequence - state.sequence - 1
        state.sequence, state.tips = sequence, tips
        if missing:
            return TrackResult(SeqStatus.GAP, missing, delta)
        return TrackResult(SeqStatus.OK, 0, delta)

    @staticmethod
    def _reset(state: _StationState, sequence: int, tips: int) -> TrackResult:
        state.sequence, state.tips = sequence, tips
        return TrackResult(SeqStatus.RESET, 0, tips)
