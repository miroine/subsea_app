"""Local, transactional case/version storage and deterministic design comparisons."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .catalog import HOST_IDS
from .spec import trains


def storage_path() -> Path:
    override = os.environ.get("SUBSEA_CASES_PATH")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SubseaLayoutDesigner" / "cases.sqlite3"


class CaseStore:
    def __init__(self, path: Path | None = None):
        self.path = path or storage_path()

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, next_version INTEGER NOT NULL DEFAULT 1,
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS versions (
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL, label TEXT NOT NULL, spec TEXT NOT NULL,
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY(case_id, number));
            """)
            with db:
                yield db
        finally:
            db.close()

    def list_cases(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT c.id,c.name,c.created,COUNT(v.number) AS versions,MAX(v.number) AS latest "
                "FROM cases c LEFT JOIN versions v ON v.case_id=c.id GROUP BY c.id ORDER BY c.created,c.id"
            )]

    def versions(self, case_id: str) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT number,label,created FROM versions WHERE case_id=? ORDER BY number DESC", (case_id,)
            )]

    def save(self, name: str, spec: dict, label: str = "", case_id: str | None = None) -> tuple[str, int]:
        if not name.strip():
            raise ValueError("A case name is required.")
        if not isinstance(spec, dict):
            raise ValueError("A design must be a JSON object.")
        payload = json.dumps(spec, ensure_ascii=False, allow_nan=False)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if case_id is None:
                case_id = uuid4().hex
                db.execute("INSERT INTO cases(id,name) VALUES (?,?)", (case_id, name.strip()))
            elif not db.execute("SELECT id FROM cases WHERE id=?", (case_id,)).fetchone():
                raise ValueError("The case no longer exists. Save as a new case.")
            number = db.execute("SELECT next_version FROM cases WHERE id=?", (case_id,)).fetchone()[0]
            db.execute("UPDATE cases SET next_version=next_version+1 WHERE id=?", (case_id,))
            db.execute("INSERT INTO versions(case_id,number,label,spec) VALUES (?,?,?,?)",
                       (case_id, number, label.strip(), payload))
        return case_id, number

    def load(self, case_id: str, number: int) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT spec FROM versions WHERE case_id=? AND number=?", (case_id, number)).fetchone()
        if row is None:
            raise ValueError("That case version no longer exists.")
        return json.loads(row["spec"])

    def duplicate(self, case_id: str, number: int, name: str) -> tuple[str, int]:
        return self.save(name, self.load(case_id, number), f"Copied from version {number}")

    def delete(self, case_id: str, number: int | None = None):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if number is None:
                result = db.execute("DELETE FROM cases WHERE id=?", (case_id,))
            else:
                result = db.execute("DELETE FROM versions WHERE case_id=? AND number=?", (case_id, number))
                if not db.execute("SELECT 1 FROM versions WHERE case_id=?", (case_id,)).fetchone():
                    db.execute("DELETE FROM cases WHERE id=?", (case_id,))
            if result.rowcount == 0:
                raise ValueError("The case or version no longer exists.")


def _identified_spec(spec: dict) -> dict:
    result = copy.deepcopy(spec)
    used = {item.get("id") for _, train in trains(result)
            for item in ([train["host"]] if train.get("host") else []) + train.get("chain", [])}
    for index, (_, train) in enumerate(trains(result), start=1):
        if train.get("host") and not train["host"].get("id"):
            # Match the renderer's stable IDs for older presets with anonymous hosts.
            host_id = f"host_{index}"
            while host_id in used:
                host_id += "_host"
            train["host"]["id"] = host_id
            used.add(host_id)
    return result


def equipment_rows(spec: dict) -> list[dict]:
    rows = []
    for tid, train in trains(_identified_spec(spec)):
        for host, item in ([(True, train["host"])] if train.get("host") else []) + [(False, it) for it in train.get("chain", [])]:
            override = spec.get("overrides", {}).get(item.get("id"), {})
            rows.append({
                "Id": item.get("id", ""), "Train": tid, "Role": "Host" if host or item["type"] in HOST_IDS else "Equipment",
                "Type": item["type"], "Label": override.get("label", item.get("label", "")),
                "Size (%)": override.get("scale", 1) * 100,
                "Offset X": override.get("dx", 0), "Offset Y": override.get("dy", 0),
                "Hidden": bool(override.get("hidden", False)),
                "Properties (JSON)": json.dumps({key: value for key, value in item.items() if key not in ("id", "type", "label")}, sort_keys=True),
            })
    return rows


def apply_equipment_rows(spec: dict, rows: list[dict]) -> dict:
    from .spec import validate
    from .equipment import customization_errors
    result = _identified_spec(spec)
    items = {
        item.get("id"): item for _, train in trains(result)
        for item in ([train["host"]] if train.get("host") else []) + train.get("chain", [])
    }
    original_rows = {row["Id"]: row for row in equipment_rows(spec)}
    if len(rows) != len(items) or {row["Id"] for row in rows} != set(items):
        raise ValueError("Equipment rows no longer match the drawing. Refresh and retry.")
    for row in rows:
        if row == original_rows[row["Id"]]:
            continue
        item = items[row["Id"]]
        props = json.loads(row["Properties (JSON)"])
        if not isinstance(props, dict) or any(key in props for key in ("id", "type", "label")):
            raise ValueError(f"{row['Id']}: properties must be an object without id, type or label.")
        json.dumps(props, allow_nan=False)
        type_, old_label = item["type"], item.get("label")
        item.clear()
        item.update(props, id=row["Id"], type=type_)
        if old_label is not None:
            item["label"] = old_label
        errors = customization_errors(item)
        if errors:
            raise ValueError(" ".join(errors))
        for field in ("x", "y", "w"):
            if field in props and (isinstance(props[field], bool) or not isinstance(props[field], (int, float))
                                   or not math.isfinite(props[field])):
                raise ValueError(f"{row['Id']}: {field} must be a finite number.")
        if "risers" in props and (not isinstance(props["risers"], list)
                                 or any(not isinstance(riser, dict) for riser in props["risers"])):
            raise ValueError(f"{row['Id']}: risers must be a list of objects.")
        if any(isinstance(riser.get("slot", 0), bool) or not isinstance(riser.get("slot", 0), int)
               or riser.get("slot", 0) < 0 for riser in props.get("risers", [])):
            raise ValueError(f"{row['Id']}: riser slot numbers must be non-negative integers.")
        scale = float(row["Size (%)"]) / 100
        dx, dy = float(row["Offset X"]), float(row["Offset Y"])
        if not all(math.isfinite(value) for value in (scale, dx, dy)) or scale <= 0:
            raise ValueError(f"{row['Id']}: size must be positive and offsets finite.")
        override = result.setdefault("overrides", {}).setdefault(row["Id"], {})
        override.update(scale=scale, dx=dx, dy=dy, hidden=bool(row["Hidden"]))
        if row["Label"] != original_rows[row["Id"]]["Label"]:
            override["label"] = row["Label"] or ""
    errors = validate(result)
    if errors:
        raise ValueError(" ".join(errors))
    return result


def compare_designs(left: dict, right: dict) -> list[dict]:
    def flatten(spec):
        spec = _identified_spec(spec)
        items = {}
        for tid, train in trains(spec):
            for index, item in enumerate(([train["host"]] if train.get("host") else []) + train.get("chain", [])):
                items[f"Equipment/{item.get('id')}"] = {**item, "_train": tid, "_order": index,
                                                       "_override": spec.get("overrides", {}).get(item.get("id"), {})}
        counts = {}
        for connection in spec.get("connections", []):
            base = f"Connection/{connection.get('from')}:{connection.get('fromPort', '')} -> {connection.get('to')}:{connection.get('toPort', '')}"
            counts[base] = counts.get(base, 0) + 1
            items[f"{base}/{counts[base]}"] = connection
        excluded = {"chain", "host", "branches", "connections", "overrides"}
        items["Settings/Layout"] = {key: value for key, value in spec.items() if key not in excluded}
        for tid, train in trains(spec):
            if tid != "main":
                items[f"Settings/{tid}"] = {key: value for key, value in train.items() if key not in ("chain", "host")}
        return items

    def fields(value, prefix=""):
        if isinstance(value, dict) and value:
            return {field: entry for key, val in sorted(value.items()) for field, entry in fields(val, f"{prefix}.{key}" if prefix else key).items()}
        return {prefix: json.dumps(value, sort_keys=True, ensure_ascii=False)}

    a, b = flatten(left), flatten(right)
    changes = []
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            changes.append({"Object": key, "Change": "Added" if key not in a else "Removed", "Field": "",
                            "Left": json.dumps(a[key], sort_keys=True) if key in a else "",
                            "Right": json.dumps(b[key], sort_keys=True) if key in b else ""})
            continue
        af, bf = fields(a[key]), fields(b[key])
        for field in sorted(set(af) | set(bf)):
            if af.get(field) != bf.get(field):
                changes.append({"Object": key, "Change": "Changed", "Field": field,
                                "Left": af.get(field, "(unset)"), "Right": bf.get(field, "(unset)")})
    return changes
