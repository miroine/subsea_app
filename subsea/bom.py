"""Equipment list / bill of quantities derived from a field spec (mirrors the engine's auto-tagging)."""
from __future__ import annotations

import pandas as pd
import json

from .catalog import BY_ID, TAGS
from .spec import FLUIDS, trains
from .equipment import DESIGN_FIELDS, effective_design_limits

SENSORS = {"pt_sensor", "tt_sensor", "sand_detector"}


def equipment_list(spec: dict) -> pd.DataFrame:
    rows, counters = [], {}
    auto = spec.get("autoTag", True)
    for tid, tr in trains(spec):
        for pos, c in enumerate(tr.get("chain", []), start=1):
            meta = BY_ID.get(c.get("type"), {})
            tag = c.get("tag", "")
            pre = TAGS.get(c.get("type"))
            if auto and pre and "tag" not in c:
                counters[pre] = counters.get(pre, 100) + 1
                tag = f"{pre}-{counters[pre]}"
            rows.append({
                "Train": "Main" if tid == "main" else tr.get("name", tid),
                "Fluid": FLUIDS.get(tr.get("fluid", "production"), tr.get("fluid", "")),
                "No.": pos, "Id": c.get("id"), "Tag": tag, "Type": c.get("type"),
                "Equipment": meta.get("name", c.get("type")), "Category": meta.get("category", "Custom"),
                "Label": c.get("label", ""),
                "Size (in)": c.get("pId"), "Length (km)": c.get("pKm"),
                "Wells": c.get("wells") if c.get("type") == "template" else (1 if c.get("type") in {"satellite_well", "vxt", "hxt"} else None),
                "Qty": 1,
                "HIPPS": c.get("hipps", True) if c.get("type") == "template" else None,
                "Xmas tree type": c.get("treeType", ""),
                "Port mode": c.get("portConfig", {}).get("mode", "default"),
                "Port lane": c.get("portConfig", {}).get("lane", ""),
                "Configured inlets": c.get("portConfig", {}).get("inlets"),
                "Configured outlets": c.get("portConfig", {}).get("outlets"),
                "Per-port fluids": json.dumps(c.get("portOverrides", {}), sort_keys=True),
                "Internal valves (JSON)": json.dumps(c["internalValves"], sort_keys=True) if "internalValves" in c else "Symbol defaults",
                **{field["label"]: effective_design_limits(spec, c).get(key) for key, field in DESIGN_FIELDS.items()},
            })
    cols = ["Train", "Fluid", "No.", "Id", "Tag", "Type", "Equipment", "Category", "Label", "Size (in)", "Length (km)", "Wells", "Qty"]
    cols += ["HIPPS", "Xmas tree type", "Port mode", "Port lane", "Configured inlets", "Configured outlets"]
    cols += ["Per-port fluids"]
    cols += ["Internal valves (JSON)"]
    cols += [field["label"] for field in DESIGN_FIELDS.values()]
    return pd.DataFrame(rows, columns=cols)


def summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (df.groupby(["Category", "Equipment"], as_index=False)["Qty"].sum().sort_values(["Category", "Equipment"]))


def totals(df: pd.DataFrame) -> dict:
    return {
        "items": int(df["Qty"].sum()) if not df.empty else 0,
        "wells": int(df["Wells"].fillna(0).sum()) if not df.empty else 0,
        "flowline_km": float(df["Length (km)"].fillna(0).sum()) if not df.empty else 0.0,
    }
