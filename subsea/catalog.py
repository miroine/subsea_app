"""Equipment catalogue: single source of truth for ids, names, categories and notes.

Every `id` here must have a drawing implementation in static/engine.js
(checked by tests/check_catalog.js).  `kind` is one of:
  host  - topside / shore / tie-in, as a train host or independent symbol
  node  - equipment sitting in the flow path (left -> right)
  link  - a pipeline / cable section between two nodes
"""

CATEGORIES = [
    "Hosts & topsides",
    "Wells & trees",
    "Structures",
    "Connections",
    "Flow control & metering",
    "Processing & boosting",
    "Controls & power",
    "Protection & ancillaries",
    "Lines (links)",
]

# (id, name, category, kind, description)
_ROWS = [
    # ---- Hosts -----------------------------------------------------------
    ("jacket", "Fixed jacket platform", "Hosts & topsides", "host", "Piled steel jacket with deck; risers clamped to the legs (J-tubes / riser slots)."),
    ("platform", "Compliant / small fixed platform", "Hosts & topsides", "host", "Lighter fixed or unmanned wellhead platform with riser slots."),
    ("fpso", "FPSO", "Hosts & topsides", "host", "Floating production, storage and offloading vessel, turret moored."),
    ("semisub", "Semi-submersible", "Hosts & topsides", "host", "Column-stabilised floating production unit."),
    ("tlp", "Tension-leg platform", "Hosts & topsides", "host", "Floater held by vertical tendons; top-tensioned or flexible risers."),
    ("spar", "Spar", "Hosts & topsides", "host", "Deep-draft cylindrical floating hull."),
    ("wind", "Offshore wind / power hub", "Hosts & topsides", "host", "Floating wind turbine or offshore substation supplying a subsea power cable."),
    ("hrt", "Hybrid riser tower", "Hosts & topsides", "host", "Free-standing riser tower with buoyancy can and flexible jumpers to the host."),
    ("onshore", "Onshore terminal", "Hosts & topsides", "host", "Shore facility with landfall; lines start on the seabed at the shore approach."),
    ("tieback", "Existing infrastructure tie-in", "Hosts & topsides", "host", "Tie-in to an existing subsea line, manifold or template."),
    # ---- Wells & trees ---------------------------------------------------
    ("satellite_well", "Satellite well", "Wells & trees", "node", "Single well tied back to the flowline via a jumper (production branch with valve)."),
    ("vxt", "Vertical Xmas tree (VXT)", "Wells & trees", "node", "Conventional tree: master / wing / swab valves stacked on the tubing hanger."),
    ("hxt", "Horizontal Xmas tree (HXT)", "Wells & trees", "node", "Horizontal tree: tubing hanger inside the tree body, side outlets."),
    ("wellhead", "Subsea wellhead", "Wells & trees", "node", "High-pressure wellhead housing and conductor, base of the tree."),
    # ---- Structures ------------------------------------------------------
    ("custom_element", "Custom element (draw your own)", "Structures", "node", "Blank editable equipment: draw shapes, text, pipes, valves and connectable hubs; import reusable layout templates."),
    ("template", "Drilling / production template", "Structures", "node", "Multi-slot template with header, branch valves, optional HIPPS and N wells."),
    ("manifold", "Production manifold", "Structures", "node", "Header with branch valves and hubs for jumper tie-ins from satellite wells."),
    ("plem", "PLEM", "Structures", "node", "Pipeline end manifold: valved tie-in point at a pipeline end."),
    ("plet", "PLET", "Structures", "node", "Pipeline end termination: single hub on a mudmat at a pipeline end."),
    ("ilt", "In-line tee (ILT)", "Structures", "node", "Tee in the pipeline giving a future tie-in branch."),
    ("ils", "In-line sled (ILS)", "Structures", "node", "Sled in the pipeline carrying valves / hubs."),
    ("fta", "Flowline termination assembly", "Structures", "node", "Termination of a flowline at a tree or manifold, with connector."),
    ("riser_skid", "Riser connection skid", "Structures", "node", "Skid-mounted riser connection assembly with configurable inlet and outlet hubs."),
    ("suction_pile", "Suction pile / anchor", "Structures", "node", "Foundation / anchor for structures or mooring."),
    ("protection_frame", "Protection frame", "Structures", "node", "Trawl-proof / dropped-object protection structure over a subsea asset."),
    # ---- Connections -----------------------------------------------------
    ("spool", "Tie-in spool", "Connections", "node", "Short rigid spool between two hubs, hatched; sized in inches ID."),
    ("jumper_rigid", "Rigid jumper (M / W / Z)", "Connections", "node", "Rigid jumper with expansion bends between two hubs."),
    ("jumper_flex", "Flexible jumper", "Connections", "node", "Flexible jumper used for large misalignment or cost."),
    ("hub_conn", "Hub / mechanical connector", "Connections", "node", "Collet connector, clamp hub or flanged connection."),
    # ---- Flow control ----------------------------------------------------
    ("valve_gate", "Gate valve", "Flow control & metering", "node", "Isolation valve, actuated by ROV or hydraulics."),
    ("valve_ball", "Ball valve", "Flow control & metering", "node", "Full-bore ball valve, pigging compatible."),
    ("valve_check", "Check valve", "Flow control & metering", "node", "One-way valve, e.g. on chemical injection or water injection lines."),
    ("choke", "Production choke", "Flow control & metering", "node", "Variable choke for rate control (tree or manifold)."),
    ("esdv", "ESD valve", "Flow control & metering", "node", "Fail-safe-closed emergency shutdown valve with actuator."),
    ("ssiv", "Subsea isolation valve (SSIV)", "Flow control & metering", "node", "Riser-base isolation valve for hydrocarbon inventory."),
    ("valve_control", "Control valve", "Flow control & metering", "node", "Modulating control valve with actuator."),
    ("valve_xov", "Crossover valve", "Flow control & metering", "node", "Crossover isolation between annulus / production paths."),
    ("hipps", "HIPPS", "Flow control & metering", "node", "High-integrity pressure protection system: dual valves with PT voting."),
    ("pig_launcher", "Subsea pig launcher", "Flow control & metering", "node", "Pig launcher module installed on a PLEM or manifold."),
    ("pig_receiver", "Subsea pig receiver", "Flow control & metering", "node", "Pig receiver / catcher module."),
    ("mpfm", "Multiphase flow meter", "Flow control & metering", "node", "Venturi-based multiphase meter."),
    ("sand_detector", "Sand detector", "Flow control & metering", "node", "Acoustic sand detector clamped on the line."),
    ("pt_sensor", "Pressure transmitter (PT)", "Flow control & metering", "node", "Pressure sensing point."),
    ("tt_sensor", "Temperature transmitter (TT)", "Flow control & metering", "node", "Temperature sensing point."),
    ("civ", "Chemical injection valve", "Flow control & metering", "node", "Chemical injection point (MEG, inhibitor) fed from a service line."),
    # ---- Processing ------------------------------------------------------
    ("mpp", "Multiphase pump", "Processing & boosting", "node", "Subsea multiphase booster pump (helico-axial / twin-screw)."),
    ("wgc", "Wet-gas compressor", "Processing & boosting", "node", "Subsea wet-gas compressor module."),
    ("separator", "Subsea separator", "Processing & boosting", "node", "Gas / liquid or oil / water separation vessel."),
    ("srp", "Raw seawater injection pump", "Processing & boosting", "node", "Seabed pump taking in seawater for injection."),
    ("hx", "Subsea cooler / heat exchanger", "Processing & boosting", "node", "Seawater-cooled heat exchanger for gas or fluid."),
    ("water_treat", "Water treatment module", "Processing & boosting", "node", "Filtration / sulphate removal / de-oiling module."),
    ("storage_tank", "Subsea storage tank", "Processing & boosting", "node", "Chemical or fluid storage."),
    ("gl_manifold", "Gas-lift manifold", "Processing & boosting", "node", "Distribution of lift gas to wells."),
    # ---- Controls & power ------------------------------------------------
    ("sdu", "Subsea distribution unit (SDU)", "Controls & power", "node", "Distributes hydraulics / chemicals / electrics from the umbilical to wells; opens the service and umbilical lanes."),
    ("uta", "Umbilical termination assembly (UTA)", "Controls & power", "node", "Termination of the umbilical at the subsea end."),
    ("suta", "Subsea UTA (SUTA)", "Controls & power", "node", "Subsea umbilical termination with distribution."),
    ("scm", "Subsea control module (SCM)", "Controls & power", "node", "Electro-hydraulic control module on the tree or manifold."),
    ("efl", "Electrical flying lead (EFL)", "Controls & power", "node", "ROV-installed electrical / signal flying lead."),
    ("cip", "Chemical injection skid", "Controls & power", "node", "Subsea chemical injection pump / metering skid."),
    ("hpu", "Subsea hydraulic power unit", "Controls & power", "node", "Local hydraulic power generation."),
    ("transformer", "Subsea transformer", "Controls & power", "node", "Step-down / step-up power transformer."),
    ("vsd", "Subsea variable speed drive", "Controls & power", "node", "Variable speed drive for pumps and compressors."),
    ("switchgear", "Subsea switchgear", "Controls & power", "node", "Power distribution and protection."),
    ("power_hub", "Power / electrical hub", "Controls & power", "node", "Wet-mate electrical hub for power cables."),
    # ---- Protection ------------------------------------------------------
    ("mattress", "Concrete mattress", "Protection & ancillaries", "node", "Mattress cover for crossings and free-span protection."),
    ("rockdump", "Rock dump", "Protection & ancillaries", "node", "Rock berm cover for burial or crossing protection."),
    ("crossing", "Crossing / existing line", "Protection & ancillaries", "node", "Third-party pipeline or cable crossing with support."),
    ("buoyancy", "Buoyancy modules", "Protection & ancillaries", "node", "Distributed buoyancy for lazy-wave risers / jumpers."),
    ("bend_stiffener", "Bend stiffener / restrictor", "Protection & ancillaries", "node", "Limits curvature at hang-off or termination."),
    ("anode", "Sacrificial anodes", "Protection & ancillaries", "node", "Cathodic protection."),
    ("trawl_guard", "Trawl guard / cover", "Protection & ancillaries", "node", "Fishing-gear overtrawl protection."),
    ("pipe_support", "Pipe support / sleeper", "Protection & ancillaries", "node", "Free-span or crossing support."),
    ("end_termination", "End cap / blind", "Protection & ancillaries", "node", "Blanked end for a future extension."),
    ("riser_base", "Riser base", "Structures", "node", "Riser-base structure: SSIV, isolation and gas-lift injection point."),
    ("wye_tee", "Wye / tee piece", "Connections", "node", "Y or T piece for branching a flowline."),
    ("flex_joint", "Flex joint / bellows", "Connections", "node", "Flexible element accommodating angular movement or expansion."),
    ("deh", "Direct electrical heating (DEH)", "Processing & boosting", "node", "Electrical heating of a flowline section for hydrate / wax control."),
    ("hydrate_skid", "Hydrate remediation skid", "Processing & boosting", "node", "Depressurisation / MEG skid for hydrate plug removal."),
    ("compression_station", "Subsea compression station", "Processing & boosting", "node", "Compression train with isolation valves in a protected frame."),
    ("accumulator", "Hydraulic accumulator", "Controls & power", "node", "Stored hydraulic energy for valve actuation."),
    ("leak_detector", "Leak detector", "Flow control & metering", "node", "Acoustic or hydrocarbon leak detection."),
    ("pct", "Power cable termination", "Controls & power", "node", "Termination of a power cable at the subsea end; opens the umbilical lane."),
    ("fibre_hub", "Fibre-optic hub", "Controls & power", "node", "Optical distribution hub."),
    # ---- Electrical single-line --------------------------------------------
    ("sld_breaker", "Circuit breaker (SLD)", "Controls & power", "node", "Single-line symbol: circuit breaker."),
    ("sld_disconnector", "Disconnector / isolator (SLD)", "Controls & power", "node", "Single-line symbol: disconnector with open blade."),
    ("sld_fuse", "Fuse (SLD)", "Controls & power", "node", "Single-line symbol: fuse."),
    ("sld_motor", "Motor (SLD)", "Controls & power", "node", "Single-line symbol: motor."),
    ("sld_generator", "Generator (SLD)", "Controls & power", "node", "Single-line symbol: generator."),
    ("sld_ct_vt", "Current / voltage transformer (SLD)", "Controls & power", "node", "Single-line symbol: instrument transformer."),
    ("sld_earthing", "Earthing (SLD)", "Controls & power", "node", "Single-line symbol: protective earth."),
    ("sld_busbar", "Busbar (SLD)", "Controls & power", "node", "Single-line symbol: busbar."),
    ("junction_box", "Junction box", "Controls & power", "node", "Electrical / optical junction box."),
    # ---- Lines -----------------------------------------------------------
    ("pipeline_rigid", "Rigid pipeline", "Lines (links)", "link", "Carbon steel / CRA rigid flowline."),
    ("pipeline_pip", "Pipe-in-pipe", "Lines (links)", "link", "Insulated rigid pipe-in-pipe flowline."),
    ("pipeline_flex", "Flexible flowline", "Lines (links)", "link", "Unbonded flexible pipe (dashed)."),
    ("pipeline_bundle", "Pipeline bundle", "Lines (links)", "link", "Towed bundle carrying production, service and controls."),
    ("cable_power", "Power cable", "Lines (links)", "link", "Subsea power cable (blue)."),
]

CATALOG = [
    {"id": i, "name": n, "category": c, "kind": k, "desc": d} for (i, n, c, k, d) in _ROWS
]

NODE_IDS = [e["id"] for e in CATALOG if e["kind"] == "node"]
LINK_IDS = [e["id"] for e in CATALOG if e["kind"] == "link"]
HOST_IDS = [e["id"] for e in CATALOG if e["kind"] == "host"]
BY_ID = {e["id"]: e for e in CATALOG}


# automatic tag prefixes (shared by the JS engine and the equipment list)
TAGS = {
    "valve_gate": "HV", "valve_ball": "HV", "valve_check": "NRV", "choke": "CHK", "esdv": "XV", "ssiv": "XV",
    "valve_control": "FCV", "valve_xov": "XOV", "mpp": "P", "srp": "P", "wgc": "K", "separator": "V", "hx": "E",
    "mpfm": "FT", "pt_sensor": "PT", "tt_sensor": "TT", "sand_detector": "SD",
}
