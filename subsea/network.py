"""Network inventories and transactional edits of explicitly drawn connections."""
from __future__ import annotations

import copy

import pandas as pd

from .spec import trains, validate

CONNECTION_COLUMNS = ["Connection", "From", "From port", "To", "To port", "Lane",
                      "Kind", "Service", "Shape", "Label", "PSV", "PSV tag", "PSV position (%)"]
EDIT_FIELDS = {"Kind": "kind", "Service": "connectionType", "Shape": "style", "Label": "label",
               "PSV": "psv", "PSV tag": "psvTag", "PSV position (%)": "psvPosition"}


def connection_rows(spec: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Connection": index, "From": item.get("from", ""), "From port": item.get("fromPort", ""),
        "To": item.get("to", ""), "To port": item.get("toPort", ""), "Lane": item.get("lane", "P"),
        "Kind": item.get("kind", ""), "Service": item.get("connectionType", ""),
        "Shape": item.get("style", "rigid"), "Label": item.get("label", ""),
        "PSV": item.get("psv", False), "PSV tag": item.get("psvTag", ""),
        "PSV position (%)": item.get("psvPosition", 50),
    } for index, item in enumerate(spec.get("connections", []))], columns=CONNECTION_COLUMNS)


def apply_connection_rows(spec: dict, rows: list[dict]) -> dict:
    before = connection_rows(spec).to_dict("records")
    if len(rows) != len(before):
        raise ValueError("Connections no longer match the drawing. Refresh and retry.")
    result = copy.deepcopy(spec)
    for original, row in zip(before, rows):
        if any(row[key] != original[key] for key in CONNECTION_COLUMNS if key not in EDIT_FIELDS):
            raise ValueError("Connection endpoints and identity are read-only.")
        item = result["connections"][original["Connection"]]
        for column, key in EDIT_FIELDS.items():
            value = row[column]
            if value is None or pd.isna(value):
                value = False if key == "psv" else 50 if key == "psvPosition" else ""
            if value != original[column]:
                item[key] = value
        if item.get("psv") and item.get("kind") != "riser":
            raise ValueError("PSV can only be enabled on a Riser connection.")
    errors = [error for error in validate(result) if error not in validate(spec)]
    if errors:
        raise ValueError(" ".join(errors))
    return result


def implicit_rows(spec: dict) -> pd.DataFrame:
    rows = []
    for tid, train in trains(spec):
        chain = train.get("chain", [])
        if not spec.get("freeform"):
            for left, right in zip(chain, chain[1:]):
                rows.append({"Train": tid, "From": left.get("id"), "To": right.get("id"),
                             "Kind": "Inline train path"})
        for field, label in (("from", "Branch tie-in"), ("to", "Branch rejoin")):
            target = train.get(field, {}).get("item")
            if target:
                rows.append({"Train": tid, "From": target if field == "from" else tid,
                             "To": tid if field == "from" else target, "Kind": label})
        for item in ([train["host"]] if train.get("host") else []) + chain:
            for index, riser in enumerate(item.get("risers", [])):
                rows.append({"Train": tid, "From": item.get("id", f"{tid}/host"),
                             "To": f"{riser.get('lane', 'P')} train lane",
                             "Kind": f"Preset riser {index + 1}"})
    return pd.DataFrame(rows, columns=["Train", "From", "To", "Kind"])
