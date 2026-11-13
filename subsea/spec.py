"""Pure-Python helpers for editing a field spec (no Streamlit import)."""
from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from .catalog import BY_ID, HOST_IDS, LINK_IDS, NODE_IDS
from .connections import CONNECTION_KINDS, CONNECTION_TYPES, RISER_STYLES
from .equipment import customization_errors, design_limit_errors, label_style_errors, removed_port_errors

# shapes understood by the JS engine for user-defined equipment
CUSTOM_SHAPES = [
    "box", "hatch", "dashbox", "pump", "compressor", "separator", "hx", "tank", "sensor",
    "frame", "mattress", "mound", "anodes", "support", "pig", "scm", "transformer", "switchgear",
]

# columns shown in the chain table; anything else lives in the `props` JSON column
CHAIN_COLS = ["type", "id", "label", "w", "pKm", "pId", "pCount", "sKm", "sId", "uKm", "wells", "slots"]
_NUMERIC = {"w", "pKm", "pId", "pCount", "sKm", "sId", "uKm", "wells", "slots"}


def _blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""


def _num(v: Any):
    f = float(v)
    return int(f) if f.is_integer() else f


def chain_to_df(chain: list[dict]) -> pd.DataFrame:
    rows = []
    for it in chain:
        row = {c: it.get(c) for c in CHAIN_COLS}
        extra = {k: v for k, v in it.items() if k not in CHAIN_COLS}
        if it.get("type") in HOST_IDS and isinstance(it.get("slots"), list):
            extra["slots"] = it["slots"]
            row["slots"] = None
        row["props"] = json.dumps(extra, ensure_ascii=False) if extra else ""
        rows.append(row)
    df = pd.DataFrame(rows, columns=CHAIN_COLS + ["props"])
    for c in _NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


FLUIDS = {
    "production": "Production", "water": "Water injection", "gas": "Gas", "gaslift": "Gas lift",
    "export": "Export", "chemical": "Chemical / MEG", "co2": "CO2", "power": "Power cable",
}


FLOW_MODES = ("auto", "forward", "reverse", "none")


def trains(spec: dict) -> list[tuple[str, dict]]:
    """[('main', spec), ('b1', branch1), ...] – each has host / chain / lanes / fluid."""
    return [("main", spec)] + [(f"b{i + 1}", b) for i, b in enumerate(spec.get("branches", []))]


def get_train(spec: dict, tid: str) -> dict:
    for name, tr in trains(spec):
        if name == tid:
            return tr
    return spec


def all_ids(spec: dict, exclude_train: str | None = None) -> list[str]:
    out = []
    for name, tr in trains(spec):
        if name != exclude_train:
            out += [c.get("id") for c in tr.get("chain", [])]
    return out


def add_branch(spec: dict, from_item: str | None, side: str = "down", fluid: str = "water", name: str = "") -> str:
    br = spec.setdefault("branches", [])
    n = len(br) + 1
    b = {"name": name or f"Branch {n}", "fluid": fluid, "lanes": {"S": False, "U": False}, "chain": []}
    if from_item:
        b["from"] = {"item": from_item, "side": side}
    br.append(b)
    return f"b{n}"


def remove_branch(spec: dict, tid: str) -> None:
    idx = int(tid[1:]) - 1
    br = spec.get("branches", [])
    if 0 <= idx < len(br):
        gone = {c.get("id") for c in br[idx].get("chain", [])}
        br.pop(idx)
        # branches hanging off the removed one are detached
        for b in br:
            if b.get("from", {}).get("item") in gone:
                b.pop("from", None)
        spec["zones"] = [z for z in spec.get("zones", []) if z.get("from") not in gone and z.get("to", z.get("from")) not in gone]


def df_to_chain(df: pd.DataFrame, taken: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Return (chain, problems).  Rows without a type are dropped; ids are made unique."""
    chain, problems, seen = [], [], set(taken or [])
    for n, (_, r) in enumerate(df.iterrows(), start=1):
        if _blank(r.get("type")):
            continue
        it: dict[str, Any] = {}
        props = r.get("props")
        if not _blank(props):
            try:
                extra = json.loads(props)
                if isinstance(extra, dict):
                    it.update(extra)
                else:
                    problems.append(f"row {n}: props must be a JSON object")
            except json.JSONDecodeError as e:
                problems.append(f"row {n}: props is not valid JSON ({e.msg})")
        for c in CHAIN_COLS:
            v = r.get(c)
            if c == "label" and isinstance(v, str):
                it[c] = v  # "" is meaningful: it hides the default caption
                continue
            if _blank(v):
                continue
            it[c] = _num(v) if c in _NUMERIC else str(v)
        base = it.get("id") or f"{it['type']}_{len(chain)}"
        uid, k = base, 1
        while uid in seen:
            k += 1
            uid = f"{base}_{k}"
        seen.add(uid)
        it["id"] = uid
        chain.append(it)
    return chain, problems


def validate(spec: dict, custom_ids: list[str] | None = None) -> list[str]:
    known = set(NODE_IDS) | set(LINK_IDS) | set(HOST_IDS) | set(custom_ids or [])
    known |= {c.get("id") for c in spec.get("customSymbols", [])}
    out = design_limit_errors(spec.get("designLimits", {}), "Layout")
    def finite(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

    if "connectionWidth" in spec and (not finite(spec["connectionWidth"]) or not 0.5 <= spec["connectionWidth"] <= 20):
        out.append("Default connection thickness must be between 0.5 and 20.")
    sea = spec.get("seaLevel", {})
    if not isinstance(sea, dict):
        out.append("Sea level must be an object.")
    elif "offset" in sea and not finite(sea["offset"]):
        out.append("Sea-level offset must be a finite number.")
    ids: list[str] = []
    for name, tr in trains(spec):
        h = tr.get("host")
        if h and h.get("id"):
            ids.append(h["id"])
        if h and h.get("type") not in HOST_IDS:
            out.append(f"{name}: unknown host type {h.get('type')!r}")
        if h:
            out.extend(customization_errors(h))
            out.extend(removed_port_errors(spec, h))
        if tr.get("fluid") and tr["fluid"] not in FLUIDS:
            out.append(f"{name}: unknown fluid {tr['fluid']!r}")
        for c in tr.get("chain", []):
            ids.append(c.get("id"))
            out.extend(customization_errors(c))
            out.extend(removed_port_errors(spec, c))
            if "lineWidth" in c and (not finite(c["lineWidth"]) or not 0.5 <= c["lineWidth"] <= 20):
                out.append(f"{c.get('id')}: flowline thickness must be between 0.5 and 20.")
            if c.get("type") not in known:
                out.append(f"unknown equipment type {c.get('type')!r} (id {c.get('id')})")
        for item in ([h] if h else []) + tr.get("chain", []):
            for index, riser in enumerate(item.get("risers", []), start=1):
                out.extend(psv_errors(riser, f"{name} preset riser {index}"))
    dup = {i for i in ids if ids.count(i) > 1}
    for d in sorted(dup, key=str):
        out.append(f"duplicate id {d!r} – ids must be unique across the whole network")
    for name, tr in trains(spec)[1:]:
        f = tr.get("from")
        if f and f.get("item") not in ids:
            out.append(f"{name}: tie-in item {f.get('item')!r} does not exist")
    for name, tr in trains(spec)[1:]:
        t = tr.get("to")
        if t and t.get("item") not in ids:
            out.append(f"{name}: rejoin item {t.get('item')!r} does not exist")
    for name, tr in trains(spec):
        if tr.get("flow") and tr["flow"] not in FLOW_MODES:
            out.append(f"{name}: unknown flow mode {tr['flow']!r}")
        if tr.get("mirror") not in (None, True, False):
            out.append(f"{name}: mirror must be true or false")
    for z in spec.get("zones", []):
        if z.get("placement", "anchored") not in ("anchored", "free"):
            out.append("Zone placement must be anchored or free.")
        if z.get("distanceUnit", "m") not in ("m", "km"):
            out.append("Zone distance unit must be m or km.")
        for field in ("edges", "arrows"):
            if z.get(field, "both") not in ("both", "left", "right", "none"):
                out.append(f"Zone {field} must be both, left, right or none.")
        for field in ("leftOffset", "rightOffset", "yOffset", "bottomOffset", "labelDx", "labelDy"):
            if field in z and not finite(z[field]):
                out.append(f"Zone {field} must be a finite drawing-coordinate number.")
        if z.get("placement") == "free":
            positions = ("leftOffset", "rightOffset", "yOffset", "bottomOffset")
            if not all(field in z and finite(z[field]) for field in positions):
                out.append("A free zone requires finite left/right, arrow and bottom positions.")
            elif z["rightOffset"] - z["leftOffset"] < 10 or z["bottomOffset"] <= z["yOffset"]:
                out.append("A free zone needs right at least 10 drawing units after left, and bottom below the arrow.")
        if "distanceM" in z and (not finite(z["distanceM"]) or z["distanceM"] <= 0):
            out.append("Zone distance must be a positive finite number of metres.")
        if z.get("distanceDirection", "right") not in ("left", "right"):
            out.append("Zone distance direction must be left or right.")
        if "distanceM" in z and z.get("fromHost"):
            out.append("A distance zone starts at its selected element, not at the host.")
        for k in ("from", "to"):
            if z.get(k) and z[k] not in ids:
                out.append(f"zone {z.get('label')!r}: '{k}' refers to missing id {z[k]!r}")
    for index, connection in enumerate(spec.get("connections", []), start=1):
        out.extend(psv_errors(connection, f"connection {index}"))
        out.extend(label_style_errors(connection.get("labelStyle", {}), f"connection {index}"))
        if connection.get("kind") is not None and connection["kind"] not in CONNECTION_KINDS:
            out.append(f"connection {index}: unknown physical connection kind.")
        if connection.get("kind") == "riser" and connection.get("style", "rigid") not in (*RISER_STYLES, "static", "scr"):
            out.append(f"connection {index}: unknown riser shape.")
        if connection.get("connectionType") and connection["connectionType"] not in CONNECTION_TYPES:
            out.append(f"connection {index}: unknown connection type {connection['connectionType']!r}")
        if "width" in connection and (not finite(connection["width"]) or not 0.5 <= connection["width"] <= 20):
            out.append(f"connection {index}: thickness must be between 0.5 and 20.")
        if connection.get("flow", "auto") not in FLOW_MODES:
            out.append(f"connection {index}: unknown flow direction.")
        points = connection.get("waypoints", [])
        if not isinstance(points, list) or any(
            not isinstance(point, dict) or not finite(point.get("x")) or not finite(point.get("y"))
            for point in points
        ):
            out.append(f"connection {index}: route bends must have finite x/y coordinates.")
    return out


def psv_errors(item: dict, where: str) -> list[str]:
    errors = []
    if not isinstance(item.get("psv", False), bool):
        errors.append(f"{where}: PSV must be true or false.")
    position = item.get("psvPosition", 50)
    if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position) or not 0 <= position <= 100:
        errors.append(f"{where}: PSV position must be between 0 and 100 percent.")
    if not isinstance(item.get("psvTag", ""), str):
        errors.append(f"{where}: PSV tag must be text.")
    return errors


def unique_id(chain: list[dict], type_: str, taken: list[str] | None = None) -> str:
    ids = {c.get("id") for c in chain} | set(taken or [])
    n = len(chain)
    while f"{type_}_{n}" in ids:
        n += 1
    return f"{type_}_{n}"


def insert_item(chain: list[dict], type_: str, after_id: str | None, taken: list[str] | None = None, **props) -> list[dict]:
    new = {"type": type_, "id": unique_id(chain, type_, taken)}
    new.update({k: v for k, v in props.items() if not _blank(v)})
    out = list(chain)
    pos = len(out)
    if after_id:
        for i, c in enumerate(out):
            if c.get("id") == after_id:
                pos = i + 1
                break
    out.insert(pos, new)
    return out


def move_item(chain: list[dict], item_id: str, delta: int) -> list[dict]:
    out = list(chain)
    idx = next((i for i, c in enumerate(out) if c.get("id") == item_id), None)
    if idx is None:
        return out
    j = max(0, min(len(out) - 1, idx + delta))
    out.insert(j, out.pop(idx))
    return out


def remove_item(chain: list[dict], item_id: str) -> list[dict]:
    return [c for c in chain if c.get("id") != item_id]


def type_label(t: str) -> str:
    e = BY_ID.get(t)
    return f"{e['name']}  ({t})" if e else t
