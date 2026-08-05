"""Decoder decision status assignment."""

from __future__ import annotations

from src.forensics.models import DecoderStatus
from src.forensics.score import THRESHOLDS, CandidateAccumulator, CandidateMetrics


def assign_statuses(
    scored: list[tuple[CandidateAccumulator, CandidateMetrics, float]],
    *,
    vendor_documented: bool = False,
    schema_anomaly_count: int = 0,
    samples_per_packet: int | None = None,
    nested_time_aligned: bool = False,
) -> dict[str, tuple[DecoderStatus, list[str]]]:
    """Return map candidate_id -> (status, rationale_codes)."""
    result: dict[str, tuple[DecoderStatus, list[str]]] = {}
    if not scored:
        return result

    costs = [c for _, _, c in scored]
    best_cost = costs[0]
    second_cost = costs[1] if len(costs) > 1 else best_cost + 1.0

    # Identify near-ties with different (C, layout)
    def layout_key(acc: CandidateAccumulator) -> tuple[int, str]:
        return acc.channel_count, acc.layout_mode

    best_acc, best_metrics, _ = scored[0]
    near_tie_conflict = False
    for acc, metrics, cost in scored[1:]:
        if cost - best_cost <= THRESHOLDS["near_tie_epsilon"]:
            if layout_key(acc) != layout_key(best_acc):
                near_tie_conflict = True
                break

    # Signedness twin conflict
    twin_conflict = False
    for acc, metrics, cost in scored[1:]:
        if (
            acc.byte_order == best_acc.byte_order
            and acc.channel_count == best_acc.channel_count
            and acc.layout_mode == best_acc.layout_mode
            and acc.signedness != best_acc.signedness
            and abs(cost - best_cost) <= THRESHOLDS["signedness_twin_epsilon"]
        ):
            twin_conflict = True
            break

    for rank, (acc, metrics, cost) in enumerate(scored):
        codes: list[str] = []
        status = DecoderStatus.UNVERIFIED

        if metrics.saturation_rate >= THRESHOLDS["reject_saturation_rate"]:
            status = DecoderStatus.REJECTED
            codes.append("reject_saturation")
        elif metrics.flatline_rate >= THRESHOLDS["reject_flatline_rate"]:
            status = DecoderStatus.REJECTED
            codes.append("reject_flatline")
        elif metrics.boundary_jump_ratio >= THRESHOLDS["reject_boundary_jump_ratio"]:
            status = DecoderStatus.REJECTED
            codes.append("reject_boundary_jump")
        elif acc.channel_count > 1 and metrics.channel_duplication >= 0.999:
            # Extreme duplication with multiple channels — likely false split
            # but only reject if also flatline-ish energy
            if metrics.channel_energy_balance < 1e-6 and metrics.flatline_rate > 0.5:
                status = DecoderStatus.REJECTED
                codes.append("reject_duplicate_channels")

        if status != DecoderStatus.REJECTED:
            codes.append("unverified_default")
            status = DecoderStatus.UNVERIFIED

        result[acc.cid] = (status, codes)

    # Provisional / accepted only for top non-rejected
    top_acc, top_metrics, top_cost = scored[0]
    top_status, top_codes = result[top_acc.cid]
    if top_status != DecoderStatus.REJECTED:
        provisional_ok = (
            top_metrics.boundary_jump_ratio
            <= THRESHOLDS["provisional_boundary_jump_ratio"]
            and top_metrics.cross_session_consistency
            <= THRESHOLDS["provisional_cross_session_consistency"]
            and not near_tie_conflict
            and not twin_conflict
        )
        if provisional_ok:
            codes = [
                "top_ranked",
                "boundary_ok",
                "cross_session_ok",
                "no_layout_near_tie",
                "no_signedness_twin",
                "not_physiological_proof",
            ]
            status = DecoderStatus.PROVISIONALLY_ACCEPTED

            exceptional = (
                (second_cost - best_cost) >= THRESHOLDS["exceptional_score_gap"]
                and schema_anomaly_count == 0
                and samples_per_packet is not None
                and nested_time_aligned
            )
            if vendor_documented or exceptional:
                status = DecoderStatus.ACCEPTED
                codes.append(
                    "vendor_documented" if vendor_documented else "exceptional_evidence_lock"
                )
            result[top_acc.cid] = (status, codes)
        else:
            codes = list(top_codes)
            if near_tie_conflict:
                codes.append("layout_near_tie")
            if twin_conflict:
                codes.append("signedness_twin")
            if (
                top_metrics.boundary_jump_ratio
                > THRESHOLDS["provisional_boundary_jump_ratio"]
            ):
                codes.append("boundary_above_provisional")
            if (
                top_metrics.cross_session_consistency
                > THRESHOLDS["provisional_cross_session_consistency"]
            ):
                codes.append("cross_session_above_provisional")
            result[top_acc.cid] = (DecoderStatus.UNVERIFIED, codes)

    return result


def selection_summary(
    statuses: dict[str, tuple[DecoderStatus, list[str]]],
    scored: list[tuple[CandidateAccumulator, CandidateMetrics, float]],
) -> tuple[str | None, DecoderStatus, list[str]]:
    if not scored:
        return None, DecoderStatus.UNVERIFIED, ["no_candidates"]
    best_id = scored[0][0].cid
    status, codes = statuses[best_id]
    notes = [
        f"selected_rank1={best_id}",
        f"status={status.value}",
        "phase2_does_not_validate_physiological_ppg",
    ]
    notes.extend(codes)
    return best_id, status, notes
