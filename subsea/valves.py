"""Editable valve configurations inside equipment symbols."""
import math
import re

VALVE_TYPES = {
    "gate": "Isolation / gate", "ball": "Isolation / ball", "check": "Check",
    "control": "Control", "psv": "PSV", "esdv": "ESDV", "ssiv": "SSIV",
    "choke": "Choke", "xov": "Crossover",
}
VALVE_COLUMNS = ["id", "pipe", "position", "kind", "closed", "tag", "label", "provider", "rating"]
MAX_INTERNAL_VALVES = 144


def internal_valve_errors(item: dict, pipe_ids: set[str] | None = None) -> list[str]:
    if "internalValves" not in item:
        return []
    where = item.get("id", "Element")
    valves = item["internalValves"]
    if not isinstance(valves, list) or len(valves) > MAX_INTERNAL_VALVES:
        return [f"{where}: internal valves must be a list of at most {MAX_INTERNAL_VALVES} valves."]
    errors, used = [], set()
    for valve in valves:
        if not isinstance(valve, dict):
            errors.append(f"{where}: each internal valve must be an object.")
            continue
        valve_id = valve.get("id")
        if not isinstance(valve_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", valve_id):
            errors.append(f"{where}: valve IDs must contain letters, numbers, underscores or hyphens.")
        elif valve_id in used:
            errors.append(f"{where}: duplicate internal valve ID {valve_id}.")
        else:
            used.add(valve_id)
        pipe = valve.get("pipe")
        if not isinstance(pipe, str) or not pipe:
            errors.append(f"{where}: each internal valve needs an internal pipe.")
        elif pipe_ids is not None and pipe not in pipe_ids:
            errors.append(f"{where}: valve {valve_id} references missing internal pipe {pipe}.")
        if not isinstance(valve.get("kind", "gate"), str) or valve.get("kind", "gate") not in VALVE_TYPES:
            errors.append(f"{where}: valve {valve_id} has an unknown type.")
        position = valve.get("position", 50)
        if (isinstance(position, bool) or not isinstance(position, (int, float))
                or not math.isfinite(position) or not 0 <= position <= 100):
            errors.append(f"{where}: valve {valve_id} position must be between 0 and 100 percent.")
        if not isinstance(valve.get("closed", False), bool):
            errors.append(f"{where}: valve {valve_id} closed state must be true or false.")
        for field in ("tag", "label", "provider", "rating"):
            if not isinstance(valve.get(field, ""), str):
                errors.append(f"{where}: valve {valve_id} {field} must be text.")
    return errors


def valve_rows(valves: list[dict]) -> list[dict]:
    defaults = dict(pipe="", position=50, kind="gate", closed=False, tag="", label="", provider="", rating="")
    return [{column: valve.get(column, defaults.get(column, "")) for column in VALVE_COLUMNS}
            for valve in valves]
