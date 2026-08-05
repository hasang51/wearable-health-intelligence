"""Payload hypotheses partitioning length-66 integers into signal vs metadata."""

from __future__ import annotations

from dataclasses import dataclass


PAYLOAD_LENGTH = 66


@dataclass(frozen=True)
class PayloadHypothesis:
    """Explicit partition of payload positions into signal and metadata."""

    hypothesis_id: str
    channel_count: int
    signal_indices: tuple[int, ...]
    metadata_indices: tuple[int, ...]
    description: str
    variant: str = "default"

    @property
    def samples_per_packet(self) -> int:
        return len(self.signal_indices)

    def validate(self, payload_length: int = PAYLOAD_LENGTH) -> None:
        sig = set(self.signal_indices)
        meta = set(self.metadata_indices)
        if sig & meta:
            raise ValueError(f"{self.hypothesis_id}: signal/metadata overlap")
        if sig | meta != set(range(payload_length)):
            raise ValueError(
                f"{self.hypothesis_id}: indices must partition 0..{payload_length - 1}"
            )
        if any(i < 0 or i >= payload_length for i in sig | meta):
            raise ValueError(f"{self.hypothesis_id}: index out of range")


def _all_indices(n: int = PAYLOAD_LENGTH) -> tuple[int, ...]:
    return tuple(range(n))


def _exclude(meta: tuple[int, ...], n: int = PAYLOAD_LENGTH) -> tuple[int, ...]:
    mset = set(meta)
    return tuple(i for i in range(n) if i not in mset)


def build_default_hypotheses(payload_length: int = PAYLOAD_LENGTH) -> list[PayloadHypothesis]:
    """Default Phase 3 payload hypotheses including sensitivity variants."""
    if payload_length != PAYLOAD_LENGTH:
        # Still build scaled equivalents for tests with other lengths if divisible.
        pass

    hyps: list[PayloadHypothesis] = []

    # H_2x33: all signal, 2 channels
    h233 = PayloadHypothesis(
        hypothesis_id="H_2x33",
        channel_count=2,
        signal_indices=_all_indices(payload_length),
        metadata_indices=(),
        description="2 channels x 33 signal samples; no metadata",
    )
    h233.validate(payload_length)
    hyps.append(h233)

    # H_2x32_plus_2global variants
    global_variants = {
        "endpoints": (0, payload_length - 1),
        "leading": (0, 1),
        "trailing": (payload_length - 2, payload_length - 1),
    }
    for name, meta in global_variants.items():
        h = PayloadHypothesis(
            hypothesis_id="H_2x32_plus_2global",
            channel_count=2,
            signal_indices=_exclude(meta, payload_length),
            metadata_indices=tuple(sorted(meta)),
            description="2x32 signal + 2 global metadata values",
            variant=name,
        )
        h.validate(payload_length)
        hyps.append(h)

    # H_2block_meta_per_ch variants (blocks of 33 for L=66)
    block = payload_length // 2
    block_variants = {
        "last_of_block": (block - 1, payload_length - 1),
        "first_of_block": (0, block),
    }
    for name, meta in block_variants.items():
        h = PayloadHypothesis(
            hypothesis_id="H_2block_meta_per_ch",
            channel_count=2,
            signal_indices=_exclude(meta, payload_length),
            metadata_indices=tuple(sorted(meta)),
            description="2 channel blocks with one metadata value per block",
            variant=name,
        )
        h.validate(payload_length)
        hyps.append(h)

    # H_3x22 control
    h322 = PayloadHypothesis(
        hypothesis_id="H_3x22",
        channel_count=3,
        signal_indices=_all_indices(payload_length),
        metadata_indices=(),
        description="3 channels x 22 signal samples (control)",
    )
    h322.validate(payload_length)
    hyps.append(h322)

    return hyps


def primary_hypotheses(payload_length: int = PAYLOAD_LENGTH) -> list[PayloadHypothesis]:
    """One default variant per hypothesis family (for main reconstruction grid)."""
    all_h = build_default_hypotheses(payload_length)
    selected: list[PayloadHypothesis] = []
    seen: set[str] = set()
    prefer_variant = {
        "H_2x33": "default",
        "H_2x32_plus_2global": "endpoints",
        "H_2block_meta_per_ch": "last_of_block",
        "H_3x22": "default",
    }
    for h in all_h:
        want = prefer_variant.get(h.hypothesis_id, "default")
        if h.hypothesis_id in seen:
            continue
        if h.variant == want or (want == "default" and h.variant == "default"):
            selected.append(h)
            seen.add(h.hypothesis_id)
    return selected


def extract_signal_values(
    payload: list[int] | tuple[int, ...],
    hypothesis: PayloadHypothesis,
) -> list[int]:
    """Order-preserving subsequence of signal indices only."""
    return [int(payload[i]) for i in hypothesis.signal_indices]


def hypothesis_key(h: PayloadHypothesis) -> str:
    return f"{h.hypothesis_id}:{h.variant}"
