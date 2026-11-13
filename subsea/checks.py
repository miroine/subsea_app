"""Rule-based design review of a field spec.  Advisory only – not a substitute for engineering studies."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from .catalog import BY_ID, HOST_IDS
from .connections import CONNECTION_TYPES
from .equipment import DESIGN_FIELDS, design_limit_errors, effective_port_lane, riser_port_ids
from .installation import installation_items
from .network import implicit_rows
from .spec import trains, validate

CONTROLLED = {"esdv", "ssiv", "hipps", "scm", "choke", "valve_control", "template"}
HYDROCARBON = {"production", "gas", "export"}
ROTATING = {"mpp", "wgc", "srp"}


def _nodes(chain):
    return [c for c in chain if BY_ID.get(c.get("type"), {}).get("kind") == "node"]


def _has_isolation(item: dict) -> bool:
    return item.get("type") in {"valve_gate", "valve_ball", "esdv", "ssiv"} or any(
        valve.get("kind", "gate") in {"gate", "ball", "esdv", "ssiv"}
        for valve in item.get("internalValves", []))


def _train_checks(spec: dict) -> list[dict]:
    out: list[dict] = []
    if spec.get("freeform"):
        return out

    def add(level, rule, msg, where=""):
        out.append({"level": level, "rule": rule, "message": msg, "where": where})

    for tid, tr in trains(spec):
        chain = tr.get("chain", [])
        nodes = _nodes(chain)
        types = [c["type"] for c in chain]
        fluid = tr.get("fluid", spec.get("fluid", "production"))
        name = tr.get("name", "Main train") if tid != "main" else "Main train"
        if not chain:
            add("warning", "empty-train", "Train has no equipment.", name)
            continue
        # R1 isolation at flowline ends
        if nodes:
            if not any(_has_isolation(n) for n in nodes[:2]):
                add("warning", "isolation-start", "No explicit isolation valve within the first two nodes; a structure name alone is not isolation evidence.", name)
            if not any(_has_isolation(n) for n in nodes[-2:]):
                add("warning", "isolation-end", "No explicit isolation valve within the last two nodes; confirm terminal isolation.", name)
        # R2 riser base
        host = tr.get("host") or {}
        if any(r.get("lane", "P") == "P" for r in host.get("risers", [])) and fluid in HYDROCARBON \
                and not any(c["type"] == "ssiv" or any(v.get("kind") == "ssiv"
                    for v in c.get("internalValves", [])) for c in chain):
            add("warning", "ssiv", "Hydrocarbon riser without an explicitly identified SSIV: confirm riser-inventory isolation; a riser-base symbol alone is not proof.", name)
        # R3 HIPPS
        for c in chain:
            if c["type"] == "template" and c.get("wells", 4) and c.get("hipps") is False and "hipps" not in types:
                add("info", "hipps", f"Template '{c.get('label', c['id'])}' has no HIPPS; confirm flowline rating covers shut-in pressure.", name)
        # R4 pigging on long lines
        km = sum(float(c.get("pKm") or 0) for c in chain if BY_ID.get(c["type"], {}).get("kind") == "link")
        if km > 15 and not {"pig_launcher", "pig_receiver"} <= set(types):
            add("warning", "pigging", f"{km:g} km of flowline without an explicit launcher/receiver pair; confirm facilities at the terminals. The 15 km trigger is a screening heuristic, not a standard.", name)
        # R5 controls vs umbilical
        lanes = tr.get("lanes", {})
        u_active = lanes.get("U", True) or {"sdu", "uta", "suta", "pct", "fibre_hub", "junction_box"} & set(types)
        if CONTROLLED & set(types) and not u_active:
            add("warning", "controls", "Controlled equipment present but no umbilical lane, SDU or UTA is defined.", name)
        s_active = lanes.get("S", True) or "sdu" in types
        if "civ" in types and not s_active:
            add("warning", "chem", "Chemical injection valve present but no service line is active.", name)
        # R6 rotating equipment isolation
        for i, c in enumerate(nodes):
            if c["type"] in ROTATING:
                before, after = nodes[max(0, i - 2): i], nodes[i + 1: i + 3]
                if not any(_has_isolation(n) for n in before) or not any(_has_isolation(n) for n in after):
                    add("info", "rotating", f"{BY_ID[c['type']]['name']} '{c['id']}' lacks explicit isolation on both sides within the nearby nodes; also confirm non-return protection.", name)
        # R7 size changes
        last = None
        for c in chain:
            kind = BY_ID.get(c["type"], {}).get("kind")
            if kind == "link" and c.get("pId"):
                if last and float(c["pId"]) != last:
                    add("info", "size-change", f"Line size changes from {last:g}\" to {float(c['pId']):g}\" between links; add a reducer / spool or confirm.", name)
                last = float(c["pId"])
        # R9 fluid compatibility
        if fluid == "water" and {"separator", "wgc"} & set(types):
            add("info", "fluid", "Gas / liquid processing equipment on a water-injection train.", name)
    return out


MANUAL_REVIEWS = (
    ("basis", "Design basis", "Applicable standards/editions, operating cases, shut-in and transient envelopes, design life and acceptance criteria are not supplied.",
     "Agree a project design basis and a discipline-by-discipline compliance register."),
    ("pressure-qualification", "Pressure & temperature", "Declared design limits and free-text ratings do not establish certified pressure/temperature capacity or gauge/absolute reference.",
     "Verify datasheets, pressure reference, temperature derating, shut-in/transient loads and the weakest pressure-containing component, including internal valves."),
    ("barriers", "Isolation & safety", "Valve symbols, HIPPS and PSV presence do not establish independent barriers, fail-safe action, SIL or adequate relief.",
     "Complete HAZID/HAZOP, isolation/ESD and barrier reviews; verify HIPPS independence, relief setpoints/capacity and safe discharge."),
    ("hydraulics", "Hydraulics & flow assurance", "No hydraulic or transient model is evaluated.",
     "Check pressure drop, arrival conditions, surge, slugging, erosion, turndown, hydrate/wax risk, cooldown and chemical/heating duties."),
    ("mechanical", "Materials & mechanical integrity", "Wall thickness, material classes, corrosion allowance, weld qualification and structural capacity are not modelled.",
     "Verify burst/collapse, buckling, fracture, fatigue, corrosion/H2S/CO2 compatibility, cathodic protection and pressure testing."),
    ("risers", "Risers & host interface", "Riser/J-tube geometry is illustrative; slot occupancy is not a bend-radius, fatigue or structural calculation.",
     "Verify host motions, hang-off and guide loads, J-tube clearances, minimum bend radius, touchdown/fatigue, supports and installation envelopes."),
    ("seabed", "Seabed, routing & protection", "Drawing coordinates, zone labels and procedural terrain are not surveyed distances, elevations or clearances.",
     "Use survey/geotechnical data to check route separation, crossings, free spans, stability, foundations, burial, fishing and dropped-object protection."),
    ("controls", "Controls & power", "A service lane or connected cable does not demonstrate a working control or power supply.",
     "Verify control paths, cause-and-effect, fail positions, hydraulic autonomy, chemical supply, power/load/fault studies and communications."),
    ("pigging-study", "Operability & maintenance", "A launcher/receiver or PLET/PLEM symbol does not prove a continuous piggable bore or maintainability.",
     "Verify pigging direction, bores/bends/check valves, drainage, venting, isolation/depressurisation, ROV access, retrieval and maintenance philosophy."),
    ("installation", "Installation & commissioning", "No installation, lifting, testing, commissioning or integrity-management study is evaluated.",
     "Verify vessel/lift/lay limits, tie-in tolerances, testing and flushing, preservation, commissioning, inspection and operating procedures."),
)


def _number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def run_checks(spec: dict) -> list[dict]:
    """Screen declared design data without certifying equipment or physical behaviour."""
    out: list[dict] = []

    def add(category, rule, status, message, where="Design", action="", evidence="", level="info"):
        out.append({"category": category, "rule": rule, "status": status, "level": level,
                    "message": message, "where": where, "action": action, "evidence": evidence})

    for rule, category, message, action in MANUAL_REVIEWS:
        add(category, rule, "Not assessed", message, action=action)

    entries = installation_items(spec)
    problems = []
    for ref, _, item in entries:
        for field in ("tag", "provider", "installationType", "rating", "installationStatus"):
            if field in item and not isinstance(item[field], str):
                problems.append(f"{ref}: {field} must be text.")
        if "id" in item and (not isinstance(item["id"], str) or not item["id"].strip()):
            problems.append(f"{ref}: ID must be non-empty text.")
        for field in ("pKm", "sKm", "uKm", "installedLengthKm", "pId", "sId"):
            if field in item and (not _number(item[field]) or item[field] < 0
                                 or (field in ("pId", "sId") and item[field] == 0)):
                problems.append(f"{ref}: {field} must be a finite {'positive' if field.endswith('Id') else 'non-negative'} number.")
        for message in design_limit_errors(item.get("designLimits", {}), ref):
            if message not in problems:
                problems.append(message)
        if "/risers/" in ref:
            slot = item.get("slot", 0)
            if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
                problems.append(f"{ref}: host slot must be a non-negative integer.")
        if ref.startswith("connections/"):
            for field in ("from", "to", "fromPort", "toPort"):
                if field in item and not isinstance(item[field], str):
                    problems.append(f"{ref}: {field} must be text.")
            if item.get("lane", "P") not in ("P", "S", "U"):
                problems.append(f"{ref}: connection lane must be P, S or U.")
    if not problems:
        problems.extend(validate(spec))
    for message in problems:
        add("Data integrity", "spec-invalid", "Action required", message,
            action="Correct the design data before relying on dependent checks.", level="error")
    if problems:
        add("Data integrity", "screening-blocked", "Not assessed",
            "Dependent automated checks were not run because the specification is invalid.",
            action="Resolve the validation errors and review again.")
        return out

    equipment = [(ref, tid, item) for ref, tid, item in entries
                 if not ref.startswith("connections/") and "/risers/" not in ref]
    if not equipment:
        add("Data integrity", "empty-design", "Action required", "There is no equipment to review.",
            action="Create or load a design before requesting a technical review.", level="warning")
        return out
    add("Data integrity", "spec-valid", "Screened", "Existing specification validators found no data errors.",
        evidence="Schema/customisation checks only; not engineering approval.")

    incomplete_ids = [ref for ref, _, item in equipment if not item.get("id") and not ref.endswith("/host")]
    for ref in incomplete_ids:
        add("Data integrity", "missing-id", "Action required", "Equipment has no explicit identifier.", ref,
            "Assign a unique ID so connections can be resolved.", level="error")
    if incomplete_ids:
        add("Network topology", "topology-blocked", "Not assessed", "Topology cannot be resolved with missing equipment IDs.")
    else:
        _network_checks(spec, equipment, add)

    for finding in [] if incomplete_ids else _train_checks(spec):
        area = {"controls": "Controls & power", "chem": "Controls & power", "pigging": "Operability & maintenance",
                "size-change": "Network topology", "fluid": "Network topology"}.get(finding["rule"], "Isolation & safety")
        add(area, finding["rule"], "Action required", finding["message"], finding["where"],
            "Confirm the intended arrangement and record the engineering justification.",
            "Schematic train-order heuristic; not a calculation or proof of a functioning barrier.", finding["level"])

    _limit_checks(spec, entries, add)
    tags: dict[str, str] = {}
    for ref, _, item in entries:
        tagged_items = [(ref, item)] + [
            (f"{ref}/valves/{v['id']}", v) for v in item.get("internalValves", [])]
        if item.get("psv") and item.get("psvTag"):
            tagged_items.append((f"{ref}/psv", {"tag": item["psvTag"]}))
        for tagged_ref, tagged in tagged_items:
            tag = tagged.get("tag", "").strip()
            if tag:
                normal = tag.casefold()
                if normal in tags:
                    add("Identification & procurement", "dup-tag", "Action required",
                        f"Tag {tag!r} is also assigned to {tags[normal]}.", tagged_ref,
                        "Use unique engineering tags, including hosts, connections and internal valves.", level="error")
                tags[normal] = tagged_ref
        if not item.get("tag", "").strip():
            add("Identification & procurement", "missing-tag", "Not assessed",
                "No explicit engineering tag is recorded; automatic drawing tags are not a controlled tag register.", ref,
                "Confirm the engineering tag against the project register.")
        status = item.get("installationStatus", "Unspecified")
        if status not in ("New", "Existing"):
            add("Identification & procurement", "installation-status", "Action required",
                "Installation status is not classified as New or Existing.", ref,
                "Classify the object before relying on new-equipment costing totals.", level="warning")
        if status == "New":
            missing = [field for field in ("provider", "installationType", "rating") if not item.get(field, "").strip()]
            if missing:
                add("Identification & procurement", "new-equipment-data", "Action required",
                    "New equipment is missing: " + ", ".join(missing) + ".", ref,
                    "Complete procurement metadata or explicitly record a project-approved TBD.", level="warning")
        is_line = ref.startswith("connections/") or "/risers/" in ref or BY_ID.get(item.get("type"), {}).get("kind") == "link"
        if is_line:
            length = item.get("installedLengthKm", item.get("pKm"))
            if not _number(length) or length <= 0:
                add("Identification & procurement", "installed-length", "Not assessed",
                    "A positive installed length in km is not recorded.", ref,
                    "Enter an engineering length; do not measure the schematic or treat an unknown length as zero.")
    return out


def _limit_checks(spec: dict, equipment: list[tuple[str, str, dict]], add) -> None:
    layout = spec.get("designLimits", {})
    missing = [field["label"] for key, field in DESIGN_FIELDS.items() if key not in layout]
    if missing:
        add("Design basis", "missing-layout-limits", "Not assessed",
            "Layout limits are missing: " + ", ".join(missing) + ".",
            action="Enter the agreed layout design envelope in Edit design; specify service-specific requirements separately.")
    for ref, _, item in equipment:
        limits = item.get("designLimits", {})
        missing = [field["label"] for key, field in DESIGN_FIELDS.items() if key not in limits]
        if missing:
            add("Pressure & temperature", "item-limits-unverified", "Not assessed",
                "No item-specific declaration for: " + ", ".join(missing) + ".", ref,
                "Confirm applicability and enter item-specific limits from approved datasheets.",
                "Inherited layout defaults are not independent evidence of equipment capacity.")
        for key, value in limits.items():
            if key not in layout:
                continue
            below = value < layout[key]
            add("Pressure & temperature", "declared-limit-" + key,
                "Action required" if below else "Screened",
                f"Declared {DESIGN_FIELDS[key]['label']}: item {value:g}; layout {layout[key]:g}.", ref,
                "Reconcile the lower item limit with the layout basis; do not assume HIPPS/PSV symbols resolve the difference."
                if below else "Verify the declared value against certified equipment data.",
                "Numeric declaration comparison only; no derating, load cases or certified capacity check.",
                "warning" if below else "info")


def _network_checks(spec: dict, equipment: list[tuple[str, str, dict]], add) -> None:
    reference_ids = {ref: item.get("id") or f"host_{tid}" for ref, tid, item in equipment}
    by_id = {reference_ids[ref]: item for ref, _, item in equipment}
    graph: dict[str, set[str]] = {item_id: set() for item_id in by_id}
    used_ports: dict[tuple[str, str], list[str]] = defaultdict(list)

    def edge(a, b):
        a, b = reference_ids.get(a, a), reference_ids.get(b, b)
        if a in graph and b in graph and a != b:
            graph[a].add(b)
            graph[b].add(a)

    for index, connection in enumerate(spec.get("connections", [])):
        ref = f"connections/{index}"
        a, b = connection.get("from"), connection.get("to")
        for endpoint, item_id in (("from", a), ("to", b)):
            if item_id not in by_id:
                add("Network topology", "missing-endpoint", "Action required",
                    f"{endpoint.title()} endpoint {item_id!r} does not identify existing equipment.", ref,
                    "Reconnect or remove the dangling connection.", level="error")
                continue
            item, port = by_id[item_id], connection.get(endpoint + "Port")
            if not port:
                add("Network topology", "implicit-port", "Not assessed",
                    f"{endpoint.title()} port on {item_id} is selected automatically by the renderer.", ref,
                    "Record an explicit port before qualifying the connection interface.")
                continue
            used_ports[(item_id, port)].append(ref)
            if item.get("type") in HOST_IDS:
                match = re.fullmatch(r"J-(\d+)", port)
                if match and int(match[1]) >= len(item.get("slots", ["J1", "J2"])):
                    add("Risers & host interface", "missing-host-slot", "Action required",
                        f"Host {item_id} has no slot {port}.", ref,
                        "Select an existing host slot or update the host definition.", level="error")
            else:
                if item.get("type") in ("riser_base", "riser_skid", "custom_element") and (
                        "riserPorts" in item or "riserDetail" in item) and port not in riser_port_ids(item):
                    add("Network topology", "missing-port", "Action required",
                        f"Port {port} is not defined on {item_id}.", ref,
                        "Select an existing hub or define the intended interface.", level="error")
                lane = effective_port_lane(item, port)
                if lane in ("P", "S", "U") and lane != connection.get("lane", "P"):
                    add("Network topology", "port-lane", "Action required",
                        f"Port {item_id}/{port} is on lane {lane}, but the connection uses {connection.get('lane', 'P')}.",
                        ref, "Use compatible service ports at both ends.", level="error")
        if a == b and a in by_id:
            add("Network topology", "self-connection", "Action required",
                "Connection returns to the same equipment.", ref,
                "Confirm the intended endpoints; internal routing belongs inside the equipment.", level="warning")
        else:
            edge(a, b)
        service = CONNECTION_TYPES.get(connection.get("connectionType"), {})
        lane = service.get("lane", "S" if service.get("fluid") == "chemical" else "P")
        if service and lane != connection.get("lane", "P"):
            add("Network topology", "service-lane", "Action required",
                f"Connection service expects lane {lane}, not {connection.get('lane', 'P')}.", ref,
                "Reconcile connection service and port lanes.", level="error")
        if connection.get("psv") and connection.get("kind") != "riser":
            add("Isolation & safety", "psv-placement", "Action required",
                "The drawing PSV option is enabled on a non-riser connection.", ref,
                "Correct the physical classification; confirm the real relief connection and discharge separately.", level="warning")

    train_map = dict(trains(spec))
    for row in implicit_rows(spec).to_dict("records"):
        train = train_map[row["Train"]]
        chain = train.get("chain", [])
        if row["Kind"] == "Inline train path":
            edge(row["From"], row["To"])
        elif chain and row["Kind"] == "Branch tie-in":
            edge(row["From"], chain[0].get("id"))
        elif chain and row["Kind"] == "Branch rejoin":
            edge(chain[-1].get("id"), row["To"])
        elif chain and row["Kind"].startswith("Preset riser"):
            edge(row["From"], chain[0].get("id"))

    for ref, _, item in equipment:
        item_id = reference_ids[ref]
        for index, riser in enumerate(item.get("risers", [])):
            port = f"J-{riser.get('slot', 0)}"
            used_ports[(item_id, port)].append(f"{ref}/risers/{index}")
    for (item_id, port), references in used_ports.items():
        if len(references) > 1:
            add("Network topology", "port-occupancy", "Action required",
                f"Port {item_id}/{port} is used by {len(references)} connections.", item_id,
                "Confirm a real multiway interface or assign distinct hubs/host slots.",
                ", ".join(references), "warning")

    functional = {item_id for item_id, item in by_id.items()
                  if (BY_ID.get(item.get("type"), {}).get("category") != "Protection & ancillaries"
                      or item.get("type") == "end_termination")
                  and item.get("type") not in ("suction_pile", "protection_frame")}
    for item_id in sorted(functional):
        if not graph[item_id]:
            add("Network topology", "unconnected-equipment", "Action required",
                "Equipment has no declared external connection or schematic train tie.", item_id,
                "Connect it or document that it is intentionally standalone/future equipment.", level="warning")
    remaining = set(functional)
    components = []
    while remaining:
        pending, visited = [min(remaining)], set()
        while pending:
            current = pending.pop()
            if current not in visited:
                visited.add(current)
                pending.extend(graph[current] - visited)
        components.append(sorted(visited & functional))
        remaining -= visited
    if len(components) > 1:
        add("Network topology", "network-islands", "Action required",
            f"The declared network has {len(components)} disconnected equipment groups.",
            action="Confirm separate systems are intentional or add the missing connections.",
            evidence=" | ".join(", ".join(group) for group in components), level="warning")
    elif functional and not any(not graph[item_id] for item_id in functional):
        add("Network topology", "declared-connectivity", "Screened",
            "Equipment belongs to one connected group of declared links.",
            evidence="All services combined, including schematic ties; this does not prove process continuity or source-to-host flow.")
    add("Network topology", "interface-qualification", "Not assessed",
        "Port existence/geometry, bore/flange classes, flow direction and per-service source-to-destination continuity are not fully established by the equipment graph.",
        action="Verify detailed interface drawings, internal routing, valve lineup and each process/control path.")
