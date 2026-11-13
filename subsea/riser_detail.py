"""Detailed schematic equipment layouts and drawing primitives."""
import math
import re

from .valves import internal_valve_errors

DETAIL_SERVICES = {
    "production": {"label": "Production", "color": "#FF0000", "lane": "P", "connectionType": "multiphase", "width": 3},
    "meg": {"label": "MEG / Service", "color": "#00B050", "lane": "S", "connectionType": "service", "width": 1.8},
    "chemical": {"label": "Chemical", "color": "#0070C0", "lane": "S", "connectionType": "chemical", "width": 1.8},
    "spare": {"label": "Spare", "color": "#7030A0", "lane": "U", "connectionType": "umbilical_static", "width": 1.8},
}

def blank_element_configuration() -> dict:
    return {"riserDetail": {"width": 420, "height": 340, "hubs": [],
                            "junctions": [], "routes": [], "shapes": [], "showFrame": True},
            "internalValves": []}


def detail_shape_errors(layout: dict, where: str) -> list[str]:
    shapes = layout.get("shapes", [])
    if not isinstance(shapes, list) or len(shapes) > 144:
        return [f"{where}: shapes must be a list of at most 144 entries."]
    errors, ids = [], set()
    finite = lambda v: not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    for shape in shapes:
        if not isinstance(shape, dict):
            errors.append(f"{where}: shapes must be objects.")
            continue
        sid, kind = shape.get("id"), shape.get("kind")
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in ids:
            errors.append(f"{where}: shape IDs must be valid and unique.")
        else:
            ids.add(sid)
        if not isinstance(kind, str) or kind not in ("rect", "ellipse", "line", "text"):
            errors.append(f"{where}: unsupported shape kind.")
            continue
        if not all(finite(shape.get(a)) and 0 <= shape[a] <= layout[d]
                   for a, d in (("x", "width"), ("y", "height"))):
            errors.append(f"{where}: shape positions must be inside the frame.")
            continue
        if kind in ("rect", "ellipse"):
            if not all(finite(shape.get(d)) and shape[d] > 0 and shape[a] + shape[d] <= layout[d] + 1e-6
                       for a, d in (("x", "width"), ("y", "height"))):
                errors.append(f"{where}: shape dimensions must be positive and fit inside the frame.")
        elif kind == "line":
            if not all(finite(shape.get(a)) and 0 <= shape[a] <= layout[d]
                       for a, d in (("x2", "width"), ("y2", "height"))) or (
                    shape.get("x2") == shape["x"] and shape.get("y2") == shape["y"]):
                errors.append(f"{where}: lines need a different endpoint inside the frame.")
        else:
            if not isinstance(shape.get("text"), str) or len(shape["text"]) > 2000:
                errors.append(f"{where}: text shapes require text of at most 2000 characters.")
            if not finite(shape.get("fontSize")) or not 4 <= shape["fontSize"] <= 72:
                errors.append(f"{where}: text size must be 4-72 drawing units.")
        for key in ("stroke", "fill"):
            value = shape.get(key, "#111111" if key == "stroke" else "none")
            if not isinstance(value, str) or not (re.fullmatch(r"#[0-9A-Fa-f]{6}", value) or key == "fill" and value == "none"):
                errors.append(f"{where}: shape colours must be six-digit hex colours (fill also allows none).")
        if not finite(shape.get("strokeWidth", 1.5)) or not 0.2 <= shape.get("strokeWidth", 1.5) <= 12:
            errors.append(f"{where}: stroke width must be 0.2-12 drawing units.")
    return errors


def illustrated_riser_configuration() -> dict:
    hubs = [
        ("P-left", 0, 130, "left", "production", "KVB / Riser side"),
        ("P-in-1", 0, 205, "left", "production", ""),
        ("P-right", 420, 130, "right", "production", "Manifold / Flowline side"),
        ("P-out-1", 420, 205, "right", "production", "Future"),
        ("S-left", 0, 265, "left", "meg", "KVB / Umbilical side"),
        ("S-right", 420, 265, "right", "meg", "MEG / Service line"),
        ("S-out-1", 420, 40, "right", "meg", "Service hub system"),
        ("S-out-2", 420, 70, "right", "meg", ""),
        ("S-in-1", 0, 281, "left", "chemical", ""),
        ("U-left", 0, 297, "left", "spare", ""),
        ("S-out-3", 420, 313, "right", "chemical", "Umbilical"),
        ("U-right", 420, 329, "right", "spare", ""),
        ("S-in-2", 145, 340, "bottom", "meg", "Umbilical Future"),
        ("S-in-3", 159, 340, "bottom", "chemical", ""),
        ("U-in-1", 173, 340, "bottom", "spare", ""),
    ]
    junctions = [
        ("upper_feed", 85, 130), ("cross_upper", 260, 130),
        ("cross_lower", 260, 205), ("lower_feed", 347, 205),
        ("header_left", 85, 70), ("header_middle", 300, 70), ("header_right", 370, 70),
        ("meg_future", 145, 265), ("meg_tap", 390, 265),
        ("chem_future", 159, 281), ("spare_future", 173, 297),
    ]
    routes = [
        ("upper_in", "P-left", "@upper_feed", "production", []),
        ("upper_middle", "@upper_feed", "@cross_upper", "production", []),
        ("upper_out", "@cross_upper", "P-right", "production", []),
        ("lower_in", "P-in-1", "@cross_lower", "production", []),
        ("lower_middle", "@cross_lower", "@lower_feed", "production", []),
        ("lower_out", "@lower_feed", "P-out-1", "production", []),
        ("crossover", "@cross_upper", "@cross_lower", "production", []),
        ("injection_upper", "@header_left", "@upper_feed", "meg", []),
        ("header_a", "@header_left", "@header_middle", "meg", []),
        ("header_b", "@header_middle", "@header_right", "meg", []),
        ("injection_lower", "@header_middle", "@lower_feed", "meg", [(347, 70)]),
        ("header_upper_out", "@header_right", "S-out-1", "meg", [(370, 40)]),
        ("header_lower_out", "@header_right", "S-out-2", "meg", []),
        ("meg_in", "S-left", "@meg_future", "meg", []),
        ("meg_middle", "@meg_future", "@meg_tap", "meg", []),
        ("meg_out", "@meg_tap", "S-right", "meg", []),
        ("meg_header", "@meg_tap", "@header_right", "meg", [(390, 148), (347, 148), (347, 70)]),
        ("meg_future_branch", "@meg_future", "S-in-2", "meg", []),
        ("chemical_in", "S-in-1", "@chem_future", "chemical", []),
        ("chemical_out", "@chem_future", "S-out-3", "chemical", [(335, 281), (335, 313)]),
        ("chemical_future_branch", "@chem_future", "S-in-3", "chemical", []),
        ("spare_in", "U-left", "@spare_future", "spare", []),
        ("spare_out", "@spare_future", "U-right", "spare", [(328, 297), (328, 329)]),
        ("spare_future_branch", "@spare_future", "U-in-1", "spare", []),
    ]
    valves = [
        ("upper_middle", 35, "ssiv"), ("lower_middle", 50, "ssiv"), ("crossover", 50, "xov"),
        ("injection_upper", 50, "check"), ("injection_lower", 53, "check"),
        ("header_upper_out", 63, "gate"), ("header_lower_out", 70, "gate"),
        ("meg_in", 40, "gate"), ("meg_middle", 86, "gate"),
        ("meg_header", 24, "check"), ("meg_header", 59, "gate"),
        ("meg_future_branch", 68, "check"), ("chemical_in", 38, "gate"),
        ("chemical_out", 82, "gate"), ("chemical_future_branch", 75, "gate"),
        ("spare_in", 35, "gate"), ("spare_out", 86, "gate"), ("spare_future_branch", 70, "gate"),
    ]
    return {
        "riserDetail": {
            "width": 420, "height": 340,
            "hubs": [dict(id=i, x=x, y=y, side=s, service=f, label=label) for i, x, y, s, f, label in hubs],
            "junctions": [dict(id=i, x=x, y=y) for i, x, y in junctions],
            "routes": [dict(id=i, **{"from": a, "to": b}, service=s,
                            points=[dict(x=x, y=y) for x, y in points]) for i, a, b, s, points in routes],
        },
        "internalValves": [dict(id=f"v{index}", pipe=f"route-{route}", position=position, kind=kind,
                                closed=False, tag="", label="", provider="", rating="")
                           for index, (route, position, kind) in enumerate(valves, 1)],
    }


def riser_detail_errors(item: dict) -> list[str]:
    if "riserDetail" not in item:
        return []
    where = item.get("id", "Element")
    layout = item["riserDetail"]
    finite = lambda value: not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    if item.get("type") not in ("riser_base", "riser_skid", "custom_element"):
        return [f"{where}: detailed drawing is only supported on riser bases, riser skids and custom elements."]
    if not isinstance(layout, dict) or any(
        not finite(layout.get(field)) or not 120 <= layout[field] <= 1000 for field in ("width", "height")
    ):
        return [f"{where}: detailed layout width and height must be finite drawing units from 120 to 1000."]
    if (any(field in item for field in ("internalRoutes", "riserPorts", "portConfig"))
            or item.get("bundleServiceInlet") or item.get("portOverrides")):
        return [f"{where}: use detailed piping or legacy internal piping/hub settings, not both."]
    errors, endpoints, route_ids = [], {}, set()
    if "showFrame" in layout and not isinstance(layout["showFrame"], bool):
        errors.append(f"{where}: showFrame must be true or false.")
    errors.extend(detail_shape_errors(layout, where))
    for field, limit in (("hubs", 64), ("junctions", 144), ("routes", 144)):
        if not isinstance(layout.get(field), list) or len(layout[field]) > limit:
            errors.append(f"{where}: detail {field} must be a list of at most {limit} entries.")
    if errors:
        return errors

    def point_valid(point):
        return isinstance(point, dict) and all(
            finite(point.get(axis)) and 0 <= point[axis] <= layout[dimension]
            for axis, dimension in (("x", "width"), ("y", "height")))

    for field in ("hubs", "junctions"):
        used = set()
        for entry in layout[field]:
            if not isinstance(entry, dict):
                errors.append(f"{where}: each detail {field} entry must be an object.")
                continue
            entry_id = entry.get("id")
            pattern = r"[PSU]-(left|right|in-\d+|out-\d+)" if field == "hubs" else r"[A-Za-z0-9_-]+"
            if not isinstance(entry_id, str) or not re.fullmatch(pattern, entry_id) or entry_id in used:
                errors.append(f"{where}: detail {field} IDs must be valid and unique.")
            else:
                used.add(entry_id)
                endpoints[entry_id if field == "hubs" else "@" + entry_id] = entry
            if not point_valid(entry):
                errors.append(f"{where}: detail {field} coordinates must lie inside the frame.")
            if not isinstance(entry.get("label", ""), str):
                errors.append(f"{where}: detail labels must be text.")
            if field == "hubs":
                side = entry.get("side")
                if (side not in ("left", "right", "top", "bottom")
                        or not isinstance(entry.get("service"), str) or entry["service"] not in DETAIL_SERVICES):
                    errors.append(f"{where}: detail hubs need a valid side and service.")
                elif point_valid(entry):
                    coordinate, expected = {
                        "left": ("x", 0), "right": ("x", layout["width"]),
                        "top": ("y", 0), "bottom": ("y", layout["height"]),
                    }[side]
                    if abs(entry[coordinate] - expected) > 1e-6:
                        errors.append(f"{where}: hub {entry_id} must be on its selected frame edge.")
    for route in layout["routes"]:
        if not isinstance(route, dict):
            errors.append(f"{where}: detail routes must be objects.")
            continue
        route_id = route.get("id")
        if not isinstance(route_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", route_id) or route_id in route_ids:
            errors.append(f"{where}: detail route IDs must be valid and unique.")
        else:
            route_ids.add(route_id)
        if any(not isinstance(route.get(end), str) or route[end] not in endpoints for end in ("from", "to")):
            errors.append(f"{where}: detail route {route_id} references a missing hub/junction.")
        elif route["from"] == route["to"]:
            errors.append(f"{where}: detail routes must connect different endpoints.")
        if not isinstance(route.get("service"), str) or route["service"] not in DETAIL_SERVICES:
            errors.append(f"{where}: detail routes need a valid service.")
        points = route.get("points", [])
        if not isinstance(points, list) or len(points) > 32 or any(not point_valid(p) for p in points):
            errors.append(f"{where}: detail routes allow up to 32 bends inside the frame.")
        elif all(isinstance(route.get(end), str) and route[end] in endpoints for end in ("from", "to")):
            positions = [endpoints[route["from"]], *points, endpoints[route["to"]]]
            if all(point_valid(p) for p in positions) and all(
                p["x"] == positions[0]["x"] and p["y"] == positions[0]["y"] for p in positions):
                errors.append(f"{where}: detail routes must have a non-zero length.")
        if not isinstance(route.get("label", ""), str):
            errors.append(f"{where}: detail route labels must be text.")
    errors.extend(internal_valve_errors(item, {f"route-{i}" for i in route_ids}))
    return errors
