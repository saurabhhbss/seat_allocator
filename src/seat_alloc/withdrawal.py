"""Withdrawal logic between rounds.

Handles student withdrawals — their seats are freed for subsequent rounds.
"""

from __future__ import annotations

from .models import Decision, ReportingStatus
from .rounds import SimulationState


def apply_withdrawals(
    state: SimulationState,
    withdrawn_app_nos: set[str],
) -> list[str]:
    """Mark students as withdrawn and free their seats.

    Returns a list of log messages describing what happened.
    """
    log: list[str] = []

    for app_no in withdrawn_app_nos:
        student = state.student_map.get(app_no)
        if student is None:
            log.append(f"{app_no}: unknown student, skipped")
            continue

        alloc = state.current_allocations.pop(app_no, None)
        student.decision = Decision.WITHDRAW
        student.reporting_status = ReportingStatus.CANCELLED

        if alloc:
            log.append(
                f"{app_no}: withdrawn from {alloc.institute_code}/"
                f"{alloc.program_code} ({alloc.category_token})"
            )
        else:
            log.append(f"{app_no}: withdrawal recorded (was not allotted)")

    return log


def apply_reporting_statuses(
    state: SimulationState,
    status_updates: dict[str, ReportingStatus],
) -> None:
    """Bulk-update reporting statuses (used between rounds)."""
    for app_no, status in status_updates.items():
        student = state.student_map.get(app_no)
        if student:
            student.reporting_status = status
            if status == ReportingStatus.CANCELLED:
                state.current_allocations.pop(app_no, None)


def apply_decisions(
    state: SimulationState,
    decisions: dict[str, Decision],
) -> None:
    """Bulk-update freeze/allow-upgrade decisions."""
    for app_no, decision in decisions.items():
        student = state.student_map.get(app_no)
        if student:
            student.decision = decision


def auto_cancel_unreported(
    state: SimulationState,
) -> list[str]:
    """Cancel students who are still PENDING after the reporting deadline.

    Returns log of cancelled students.
    """
    log: list[str] = []
    for app_no in list(state.current_allocations.keys()):
        student = state.student_map.get(app_no)
        if student and student.reporting_status == ReportingStatus.PENDING:
            student.reporting_status = ReportingStatus.CANCELLED
            alloc = state.current_allocations.pop(app_no, None)
            if alloc:
                log.append(
                    f"{app_no}: auto-cancelled (unreported) from "
                    f"{alloc.institute_code}/{alloc.program_code}"
                )
    return log
