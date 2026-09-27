"""Conservative leaf implementation status, separate from test verdicts."""

STATUSES = (
    "attempted",
    "partial_or_rejected",
    "contract_incomplete",
    "implemented_unverified",
    "behavior_verified",
)


def initial_status(*, ok: bool, outcome: str, changed: bool,
                   refused: bool = False, preexisting: bool = False) -> str:
    """Classify the source turn without treating a completed turn as a feature.

    An existing application can satisfy a leaf without a new write, but a
    refused, malformed or incomplete response is still explicit contrary
    evidence. A later trusted behavior check may promote this status.
    """
    if refused or outcome in {"partial", "guard_refused", "anchor_failed",
                              "incomplete_blocks", "tool_incomplete"}:
        return "partial_or_rejected" if changed or refused else "contract_incomplete"
    if not ok or outcome in {"no_blocks", "format_error", "export_contract",
                             "helper_contract_error", "route_conflict", "placeholder_overwrite"}:
        return "partial_or_rejected" if changed else "contract_incomplete"
    if changed or preexisting:
        return "implemented_unverified"
    return "contract_incomplete"
