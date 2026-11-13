"""Equipment customization and user-entered design-limit metadata."""
import math
import re
from .catalog import HOST_IDS
from .connections import CONNECTION_TYPES
from .valves import internal_valve_errors
from .riser_detail import DETAIL_SERVICES, riser_detail_errors

DESIGN_FIELDS = {
    "pressureBar": {"label": "Design pressure (bar)", "minimum": 0, "exclusive": True},
    "temperatureC": {"label": "Maximum temperature (deg C)", "minimum": -273.15},
    "waterDepthM": {"label": "Water depth (m)", "minimum": 0},
    "flowM3Day": {"label": "Design flow rate (m3/day)", "minimum": 0, "exclusive": True},
}
TREE_TYPES = {"vxt": "Vertical Xmas tree (VXT)", "hxt": "Horizontal Xmas tree (HXT)"}
MAX_PORTS = 24


def furb_configuration(item: dict | None = None) -> dict:
    configuration = {
        "riserPorts": {"P": {"inlets": 1, "outlets": 1}, "S": {"inlets": 0, "outlets": 1},
                       "U": {"inlets": 1, "outlets": 1}},
        "internalRoutes": [
            {"id": "process", "from": "P-left", "to": "P-right", "connectionType": "gas"},
            {"id": "umb", "from": "U-left", "to": "U-right", "connectionType": "umbilical_static"},
            {"id": "chem", "from": "@umb", "to": "S-right", "connectionType": "chemical"},
        ],
    }
    if item is not None:
        counts = riser_hub_counts(item)
        for lane in ("P", "S", "U"):
            for side in ("inlets", "outlets"):
                configuration["riserPorts"][lane][side] = max(
                    configuration["riserPorts"][lane][side], counts[lane][side])
    return configuration


def riser_hub_counts(item: dict) -> dict:
    if "riserPorts" in item:
        return item["riserPorts"]
    counts = {lane: {"inlets": int(bool(enabled)), "outlets": int(bool(enabled))}
              for lane, enabled in (("P", True), ("S", item.get("servicePorts")), ("U", item.get("umbilicalPorts")))}
    config = item.get("portConfig")
    if config:
        for side in ("inlets", "outlets"):
            counts[config["lane"]][side] = config[side] + (
                max(counts[config["lane"]][side], int(config[side] > 0)) if config["mode"] == "additional" else 0)
    return counts


def riser_port_ids(item: dict, include_bundled: bool = False) -> set[str]:
    if "riserDetail" in item:
        return {hub["id"] for hub in item["riserDetail"]["hubs"]}
    if "riserPorts" not in item:
        config = item.get("portConfig", {})
        ports = {f"{lane}-{side}" for lane, enabled in (
            ("P", True), ("S", item.get("servicePorts")), ("U", item.get("umbilicalPorts")))
            if enabled and not (config.get("mode") == "replace" and config.get("lane") == lane)
            for side in ("left", "right")}
        if config:
            lane = config["lane"]
            for side, short, boundary in (("inlets", "in", "left"), ("outlets", "out", "right")):
                count = config[side]
                if config["mode"] == "replace" and count:
                    ports.add(f"{lane}-{boundary}")
                    count -= 1
                ports.update(f"{lane}-{short}-{index + 1}" for index in range(count))
    else:
        ports = set()
        for lane, counts in riser_hub_counts(item).items():
            for side, short, boundary in (("inlets", "in", "left"), ("outlets", "out", "right")):
                if counts[side]:
                    ports.add(f"{lane}-{boundary}")
                ports.update(f"{lane}-{short}-{index}" for index in range(1, counts[side]))
    if item.get("bundleServiceInlet"):
        if include_bundled:
            ports.add("S-left")
        else:
            ports.discard("S-left")
    return ports


def internal_routing_errors(item: dict, ports: set[str]) -> list[str]:
    routes = item.get("internalRoutes", [])
    where = item.get("id", "Element")
    if not isinstance(routes, list) or len(routes) > 144:
        return [f"{where}: internal routes must be a list of at most 144 routes."]
    errors, by_id = [], {}
    for route in routes:
        if not isinstance(route, dict):
            errors.append(f"{where}: each internal route must be an object.")
            continue
        route_id = route.get("id")
        if not isinstance(route_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", route_id):
            errors.append(f"{where}: internal route IDs must contain letters, numbers, underscores or hyphens.")
        elif route_id in by_id:
            errors.append(f"{where}: duplicate internal route ID {route_id}.")
        else:
            by_id[route_id] = route
        if not isinstance(route.get("from"), str) or not isinstance(route.get("to"), str):
            errors.append(f"{where}: internal routes need From and To ports.")
        if not isinstance(route.get("connectionType"), str) or route["connectionType"] not in CONNECTION_TYPES:
            errors.append(f"{where}: internal routes need a valid fluid/service.")
    if errors:
        return errors
    for route in routes:
        source, target = route["from"], route["to"]
        if target not in ports:
            errors.append(f"{where}: internal route {route['id']} ends at missing port {target}.")
        if source.startswith("@"):
            trunk = by_id.get(source[1:])
            if not trunk or trunk is route or trunk["from"] not in ports or trunk["to"] not in ports:
                errors.append(f"{where}: {source} must reference a direct port-to-port route junction.")
        elif source not in ports:
            errors.append(f"{where}: internal route {route['id']} starts at missing port {source}.")
        if source == target:
            errors.append(f"{where}: internal route {route['id']} must connect different endpoints.")
    return errors


def connect_internal_hub(item: dict, port: str, route_id: str) -> list[dict]:
    ports = riser_port_ids(item, include_bundled=True)
    errors = internal_routing_errors(item, ports)
    if errors:
        raise ValueError(" ".join(errors))
    routes = item.get("internalRoutes", [])
    trunk = next((route for route in routes if route["id"] == route_id), None)
    if not trunk or trunk["from"] not in ports or trunk["to"] not in ports:
        raise ValueError("Choose a direct port-to-port internal line.")
    if port not in ports:
        raise ValueError("Choose an existing hub to connect internally.")
    if any(port in (route["from"], route["to"]) for route in routes):
        raise ValueError("This hub is already internally routed. Edit or remove its existing route first.")
    service = CONNECTION_TYPES[trunk["connectionType"]]
    lane = service.get("lane") or ("S" if service.get("fluid") == "chemical" else "P")
    if effective_port_lane(item, port) != lane:
        raise ValueError("The hub and internal line must use the same service lane.")
    stem, suffix = f"branch_{port}", 2
    branch_id = stem
    while any(route["id"] == branch_id for route in routes):
        branch_id = f"{stem}_{suffix}"
        suffix += 1
    return [*routes, {"id": branch_id, "from": f"@{route_id}", "to": port,
                     "connectionType": trunk["connectionType"]}]


def effective_port_lane(item: dict, port: str) -> str:
    settings = item.get("portOverrides", {}).get(port, {})
    service = CONNECTION_TYPES.get(settings.get("connectionType"))
    if item.get("type") == "plet" and service:
        return service.get("lane", "S" if service.get("fluid") == "chemical" else "P")
    if item.get("riserDetail"):
        hub = next((hub for hub in item["riserDetail"]["hubs"] if hub["id"] == port), None)
        if hub:
            return settings.get("lane", DETAIL_SERVICES[hub["service"]]["lane"])
    return settings.get("lane", port[:1])


def design_limit_errors(limits: dict, where: str) -> list[str]:
    if not isinstance(limits, dict):
        return [f"{where}: design limits must be an object."]
    errors = []
    for key, value in limits.items():
        if key not in DESIGN_FIELDS:
            errors.append(f"{where}: unknown design limit {key!r}.")
            continue
        field = DESIGN_FIELDS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{where}: {field['label']} must be a finite number.")
        elif value < field["minimum"] or (field.get("exclusive") and value == field["minimum"]):
            relation = "greater than" if field.get("exclusive") else "at least"
            errors.append(f"{where}: {field['label']} must be {relation} {field['minimum']}.")
    return errors


def parse_design_limits(values: dict) -> dict:
    limits = {}
    for key, text in values.items():
        if str(text).strip():
            try:
                limits[key] = float(text)
            except ValueError as error:
                raise ValueError(f"{DESIGN_FIELDS[key]['label']} must be a number or blank.") from error
    errors = design_limit_errors(limits, "Design limits")
    if errors:
        raise ValueError(" ".join(errors))
    return limits


def effective_design_limits(spec: dict, item: dict) -> dict:
    return {**spec.get("designLimits", {}), **item.get("designLimits", {})}


def label_style_errors(style: object, where: str) -> list[str]:
    if not isinstance(style, dict):
        return [f"{where}: labelStyle must be an object."]
    errors = []
    for field, low, high in (("size", 0, 72), ("dx", -math.inf, math.inf),
                             ("dy", -math.inf, math.inf), ("rotation", -180, 180)):
        if field in style:
            value = style[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                errors.append(f"{where}: label {field} must be a finite number between {low} and {high}.")
    for field, choices in (("font", ("auto", "sans", "serif", "mono")),
                           ("anchor", ("auto", "start", "middle", "end")),
                           ("weight", ("auto", "normal", "bold"))):
        if field in style and style[field] not in choices:
            errors.append(f"{where}: unknown label {field}.")
    if "italic" in style and not isinstance(style["italic"], bool):
        errors.append(f"{where}: label italic must be true or false.")
    return errors


def customization_errors(item: dict) -> list[str]:
    where = item.get("id", "Element")
    errors = design_limit_errors(item.get("designLimits", {}), where)
    errors.extend(label_style_errors(item.get("labelStyle", {}), where))
    if "riserDetail" not in item:
        errors.extend(internal_valve_errors(item))
    errors.extend(riser_detail_errors(item))
    if item.get("type") in ("riser_base", "riser_skid"):
        for field in ("servicePorts", "umbilicalPorts", "bundleServiceInlet"):
            if field in item and not isinstance(item[field], bool):
                errors.append(f"{where}: {field} must be true or false.")
        if "riserPorts" in item:
            counts = item["riserPorts"]
            if not isinstance(counts, dict) or set(counts) != {"P", "S", "U"} or any(
                not isinstance(counts[lane], dict) or any(
                    isinstance(counts[lane].get(side), bool) or not isinstance(counts[lane].get(side), int)
                    or not 0 <= counts[lane][side] <= MAX_PORTS for side in ("inlets", "outlets"))
                for lane in ("P", "S", "U")
            ):
                errors.append(f"{where}: independent P/S/U counts must be whole numbers from 0 to {MAX_PORTS}.")
            elif "portConfig" in item:
                errors.append(f"{where}: use independent service counts or legacy hub configuration, not both.")
        if not errors and not item.get("portConfig"):
            if item.get("bundleServiceInlet"):
                ports = riser_port_ids(item)
                if not {"U-left", "S-right"} <= ports or effective_port_lane(item, "U-left") != "U":
                    errors.append(f"{where}: bundled inlet requires a U-compatible U-left port and an S-right chemical/service outlet.")
            if "internalRoutes" in item and not errors:
                errors.extend(internal_routing_errors(item, riser_port_ids(item, include_bundled=True)))
    if item.get("type") == "plet" and item.get("pletPorts", "PSU") not in ("P", "S", "U", "PSU"):
        errors.append(f"{where}: PLET standard ports must be P, S, U or PSU.")
    if item.get("type") in HOST_IDS and "slots" in item:
        slots = item["slots"]
        if not isinstance(slots, list) or len(slots) > MAX_PORTS or any(
            not isinstance(slot, str) or not slot.strip() for slot in slots
        ):
            errors.append(f"{where}: J-tubes must be a list of 0-{MAX_PORTS} non-empty names.")
    if item.get("type") in HOST_IDS and "showJTubes" in item and not isinstance(item["showJTubes"], bool):
        errors.append(f"{where}: showJTubes must be true or false.")
    if item.get("type") in HOST_IDS and item.get("jTubeSide", "left") not in ("left", "right"):
        errors.append(f"{where}: J-tube seabed exit must be left or right.")
    settings = item.get("portOverrides", {})
    if not isinstance(settings, dict):
        errors.append(f"{where}: per-port settings must be an object.")
    else:
        for port, setting in settings.items():
            if not isinstance(port, str) or not re.fullmatch(r"[PSU]-(left|right|in-\d+|out-\d+)", port):
                errors.append(f"{where}: invalid port id {port!r}.")
            if not isinstance(setting, dict):
                errors.append(f"{where}: {port} settings must be an object.")
                continue
            if setting.get("lane", "P") not in ("P", "S", "U"):
                errors.append(f"{where}: {port} lane must be P, S or U.")
            if setting.get("connectionType") and setting["connectionType"] not in CONNECTION_TYPES:
                errors.append(f"{where}: {port} has an unknown fluid/service.")
            if "label" in setting and not isinstance(setting["label"], str):
                errors.append(f"{where}: {port} label must be text.")
        if item.get("bundleServiceInlet") and isinstance(settings.get("U-left", {}), dict):
            if settings.get("U-left", {}).get("connectionType", "") not in ("", "umbilical_static", "umbilical_dynamic"):
                errors.append(f"{where}: the bundled U-left inlet must use Automatic, Static umbilical or Dynamic umbilical.")
    if item.get("type") == "template":
        if item.get("treeType") is not None and item["treeType"] not in TREE_TYPES:
            errors.append(f"{where}: unsupported Xmas tree type.")
        if "hipps" in item and not isinstance(item["hipps"], bool):
            errors.append(f"{where}: HIPPS must be true or false.")
        wells = item.get("wells", 4)
        if isinstance(wells, bool) or not isinstance(wells, (int, float)) or not math.isfinite(wells) or wells != int(wells) or not 0 <= wells <= 24:
            errors.append(f"{where}: wells must be a whole number between 0 and 24.")
    if "portConfig" not in item:
        return errors
    config = item["portConfig"]
    if not isinstance(config, dict):
        return errors + [f"{where}: port configuration must be an object."]
    if config.get("mode") not in ("additional", "replace"):
        errors.append(f"{where}: port mode must be additional or replace.")
    if config.get("lane") not in ("P", "S", "U"):
        errors.append(f"{where}: port lane must be P, S or U.")
    for side in ("inlets", "outlets"):
        count = config.get(side)
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_PORTS:
            errors.append(f"{where}: {side} must be a whole number between 0 and {MAX_PORTS}.")
    if "internalRoutes" in item and not errors:
        errors.extend(internal_routing_errors(item, riser_port_ids(item, include_bundled=True)))
    if item.get("bundleServiceInlet") and not errors:
        if not {"U-left", "S-right"} <= riser_port_ids(item) or effective_port_lane(item, "U-left") != "U":
            errors.append(f"{where}: bundled inlet requires a U-compatible U-left port and an S-right chemical/service outlet.")
    return errors


def removed_port_errors(spec: dict, item: dict) -> list[str]:
    """Reject removal of explicitly connected ports rather than hiding their lines."""
    if item.get("type") in HOST_IDS:
        slots = item.get("slots", ["J1", "J2"])
        if not isinstance(slots, list):
            return []
        errors = []
        for connection in spec.get("connections", []):
            for endpoint in ("from", "to"):
                port = connection.get(endpoint + "Port", "")
                if connection.get(endpoint) == item.get("id") and re.fullmatch(r"J-\d+", port) and int(port[2:]) >= len(slots):
                    errors.append(f"{item['id']}: J-tube {port} is connected. Reconnect or delete its riser before removing it.")
        if any(riser.get("slot", 0) >= len(slots) for riser in item.get("risers", [])):
            errors.append(f"{item.get('id', 'Host')}: a preset riser uses a removed J-tube.")
        return errors
    config = item.get("portConfig")
    if item.get("type") in ("riser_base", "riser_skid", "custom_element") and ("riserPorts" in item or "riserDetail" in item):
        if customization_errors(item):
            return []
        allowed = riser_port_ids(item)
        errors = []
        for connection in spec.get("connections", []):
            for endpoint in ("from", "to"):
                port = connection.get(endpoint + "Port", "")
                if connection.get(endpoint) != item.get("id") or not port:
                    continue
                if port not in allowed:
                    errors.append(f"{item['id']}: port {port} is connected. Reconnect or delete its connection before removing this port.")
                elif effective_port_lane(item, port) != connection.get("lane", "P"):
                    errors.append(f"{item['id']}: port {port} is connected. Reconnect or delete its connection before changing lane.")
        return errors
    if config is not None and (not isinstance(config, dict) or customization_errors(item)):
        return []
    config = config or {"mode": "additional", "lane": "P", "inlets": 0, "outlets": 0}
    lane = config["lane"]
    allowed = set()
    for side, short, boundary in (("inlets", "in", "left"), ("outlets", "out", "right")):
        count = config[side]
        if config["mode"] == "replace" and count:
            allowed.add(f"{lane}-{boundary}")
            count -= 1
        allowed.update(f"{lane}-{short}-{index + 1}" for index in range(count))
    errors = []
    for connection in spec.get("connections", []):
        for endpoint in ("from", "to"):
            port = connection.get(endpoint + "Port", "")
            if connection.get(endpoint) != item.get("id"):
                continue
            port_lane = effective_port_lane(item, port)
            if port_lane in ("P", "S", "U") and port_lane != connection.get("lane", "P"):
                errors.append(f"{item['id']}: port {port} is connected on lane {connection.get('lane', 'P')}. Reconnect or delete its connection before changing lane.")
            custom = re.fullmatch(r"[PSU]-(in|out)-\d+", port)
            replaced = config["mode"] == "replace" and port in (f"{lane}-left", f"{lane}-right")
            disabled_plet_port = item.get("type") == "plet" and re.fullmatch(r"[PSU]-(left|right)", port) and (
                port[0] not in item.get("pletPorts", "PSU"))
            bundled_inlet = item.get("bundleServiceInlet") and port == "S-left"
            disabled_riser_port = item.get("type") in ("riser_base", "riser_skid") and (
                (port in ("S-left", "S-right") and not item.get("servicePorts"))
                or (port in ("U-left", "U-right") and not item.get("umbilicalPorts")))
            if bundled_inlet or ((custom or replaced or disabled_plet_port or disabled_riser_port) and port not in allowed):
                errors.append(f"{item['id']}: port {port} is connected. Reconnect or delete its connection before removing this port.")
    return errors
