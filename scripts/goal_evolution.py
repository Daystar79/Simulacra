"""Interpret host-observed choices and changes to a character's goals."""

STATUSES = {"active", "blocked", "dormant", "completed", "abandoned"}
CHOICES = {"pursued", "passed", "prevented"}
GOAL_FIELDS = {"objective", "motivation", "horizon", "progress", "status", "commitment"}


def current_goals(authored, durable, runtime):
    """Overlay only changed fields. Preserve legacy goal descriptions and log-only goals."""
    goals = {}
    for layer in (authored, durable, runtime):
        if not isinstance(layer, dict):
            continue  # Unkeyed legacy notes stay in the original card passed to the host.
        for goal_id, fields in layer.items():
            entry = goals.setdefault(goal_id, {"status": "active"})
            if isinstance(fields, str):
                entry["objective"] = fields
            elif isinstance(fields, dict):
                entry.update(fields)
    return goals


def record_goal_events(config, request, changes):
    """Apply one resolved turn's observations and goal amendments to its runtime state."""
    if not isinstance(changes, dict):
        raise ValueError("goal_events must be a mapping keyed by goal ID")
    known = request.get("current_goals")
    if known is None:  # Pending requests created before this feature.
        known = current_goals(request.get("goals"), request.get("goal_updates"), config.get("goal_changes"))
    for goal_id, change in changes.items():
        if not isinstance(goal_id, str) or not goal_id.strip() or not isinstance(change, dict):
            raise ValueError("Each goal event requires a nonempty goal ID and an object")
        unknown = change.keys() - GOAL_FIELDS - {"evidence", "choice"}
        if unknown or any(not isinstance(value, str) or not value.strip() for value in change.values()):
            raise ValueError("Goal events require known fields with nonempty text values")
        if "evidence" not in change:
            raise ValueError("Describe the observed event or choice supporting the goal event")
        if goal_id not in known and "objective" not in change:
            raise ValueError("A newly formed goal requires an objective")
        if "status" in change and change["status"] not in STATUSES:
            raise ValueError("Unknown goal status")
        fields = {key: change[key] for key in GOAL_FIELDS if key in change}
        if not fields and "choice" not in change:
            raise ValueError("A goal event requires a choice or a goal amendment")
        summary = config.setdefault("goal_evidence", {}).setdefault(goal_id, {"choices": {}})
        if "choice" in change:
            choice = change["choice"]
            if choice not in CHOICES:
                raise ValueError("Goal choice must be pursued, passed, or prevented")
            counts = summary["choices"]
            counts[choice] = counts.get(choice, 0) + 1
        summary.update(last_event=request["event"]["id"], at=request["at"], evidence=change["evidence"])
        if fields:
            config.setdefault("goal_changes", {}).setdefault(goal_id, {}).update(fields)
