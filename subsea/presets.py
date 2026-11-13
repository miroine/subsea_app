"""Ready-made generic field layouts (all names, sizes and lengths are placeholders)."""
from __future__ import annotations

import copy

TIEBACK = {
    "title": "Two-template tieback to a fixed platform",
    "subtitle": "Subsea production system – general arrangement (schematic)",
    "source": "Indicative concept layout; sizes, lengths and tags are placeholders",
    "host": {
        "type": "jacket",
        "slots": ["R1", "R2"],
        "activeSlot": 0,
        "risers": [
            {"lane": "P", "slot": 0, "style": "rigid", "label": 'Production riser, 8"', "color": "red", "dx": 4, "ldx": 24},
            {"lane": "U", "slot": 0, "style": "static", "label": "Static umbilical riser", "color": "yellow", "dx": 12},
        ],
    },
    "lanes": {"S": False, "U": False},
    "gap": 28,
    "chain": [
        {"id": "sp0", "type": "spool", "label": ""},
        {"id": "plem", "type": "plem", "label": "PLEM", "sizeIn": '12"', "sizeOut": '8"'},
        {"id": "sp1", "type": "spool", "label": "Spool"},
        {"id": "sdu", "type": "sdu", "label": "SDU"},
        {"id": "l1", "type": "pipeline_pip", "w": 230, "pId": 12, "pKm": 20, "sKm": 20, "sId": 3, "uKm": 24, "pWrap": 30},
        {"id": "e1", "type": "esdv"},
        {"id": "pt1", "type": "pt_sensor"},
        {"id": "sp2", "type": "spool", "label": 'Spool, 12"', "w": 78},
        {"id": "t1", "type": "template", "label": "Template A", "wells": 4, "hipps": True, "wellStart": 1},
        {"id": "sp3", "type": "spool", "label": 'Spool, 12"', "w": 56},
        {"id": "l2", "type": "pipeline_pip", "w": 60, "vertical": True, "pId": 12, "pKm": 6, "sKm": 6, "sId": 3, "uKm": 6},
        {"id": "sp4", "type": "spool", "label": 'Spool, 12"', "w": 56},
        {"id": "t2", "type": "template", "label": "Template B", "wells": 4, "hipps": True, "wellStart": 5},
    ],
    "zones": [
        {"from": "sp0", "to": "sdu", "label": "Safety zone", "edges": "right", "fromHost": True},
        {"from": "sp2", "to": "sp2", "label": "Protected zone", "edges": "both"},
        {"from": "sp4", "to": "sp4", "label": "Protected zone", "edges": "both"},
    ],
    "notes": [
        "All sizes are internal diameters unless stated.",
        "Tags and line numbers are generated automatically.",
        "Distances are not to scale.",
    ],
    "showLegend": True,
    "showTitleBlock": True,
    "titleBlock": {"drawing": "Subsea layout – general arrangement", "rev": "A", "docNo": "SSL-0001"},
}

SINGLE_JACKUP = {
    "title": "Single 4-slot template tie-in to a jackup",
    "subtitle": "Illustrative subsea tie-in and elevated jackup host",
    "source": "Generic concept; dimensions, duties and tags require project engineering",
    "host": {"id": "jackup", "type": "jackup", "label": "Jackup", "slots": ["Production", "Service", "Control"],
             "activeSlot": 0, "showJTubes": True, "jTubeSide": "right",
             "risers": [{"lane": "P", "slot": 0, "style": "rigid", "label": "Production riser"},
                        {"lane": "S", "slot": 1, "style": "rigid", "label": "Service riser"},
                        {"lane": "U", "slot": 2, "style": "static", "label": "Control umbilical"}]},
    "lanes": {"S": True, "U": True}, "gap": 32, "animate": False, "showLegend": True,
    "chain": [
        {"id": "ssiv", "type": "ssiv", "tag": "XV-101"},
        {"id": "sdu", "type": "sdu", "label": "SDU"},
        {"id": "flowline", "type": "pipeline_pip", "w": 260},
        {"id": "template", "type": "template", "label": "4-slot template", "wells": 4,
         "wellStart": 1, "treeType": "vxt", "hipps": False},
    ],
    "notes": [
        "Single four-slot template; all geometry and tags are illustrative, not to scale.",
        "Lengths, sizes and equipment ratings are intentionally unspecified.",
        "Confirm the jackup's intended drilling, well-test or production duty and receiving facilities.",
        "Riser support, temporary services, pressure protection and well barriers require independent engineering.",
    ],
}

SINGLE_FPSO = {
    "title": "Single template tied back to FPSO",
    "host": {"type": "fpso", "slots": ["Turret"], "activeSlot": 0,
             "risers": [{"lane": "P", "slot": 0, "style": "lazywave", "label": 'Flexible riser 8"', "color": "red", "ldx": 40},
                        {"lane": "U", "slot": 0, "style": "static", "label": "Dynamic umbilical", "color": "yellow", "dx": 14}]},
    "lanes": {"S": False, "U": False},
    "chain": [
        {"id": "ssiv", "type": "ssiv"},
        {"id": "plet", "type": "plet"},
        {"id": "uta", "type": "uta", "lane": "U"},
        {"id": "sdu", "type": "sdu"},
        {"id": "l1", "type": "pipeline_pip", "pId": 12, "pKm": 18, "sKm": 18, "sId": 3, "uKm": 18},
        {"id": "tpl", "type": "template", "label": "Template A", "wells": 6, "hipps": False},
    ],
    "zones": [{"from": "ssiv", "to": "sdu", "label": "Safety zone", "edges": "right", "fromHost": True}],
}

PROCESSING = {
    "title": "Subsea processing station",
    "host": {"type": "tieback", "label": "Existing\ninfrastructure"},
    "gap": 10,
    "chain": [
        {"id": "m1", "type": "manifold", "label": "Production manifold", "slots": 4},
        {"id": "v1", "type": "valve_gate"},
        {"id": "sep", "type": "separator", "label": "Gas / liquid separator"},
        {"id": "mpfm", "type": "mpfm"},
        {"id": "pump", "type": "mpp", "label": "Booster pump"},
        {"id": "chk", "type": "valve_check"},
        {"id": "hx", "type": "hx", "label": "Gas cooler"},
        {"id": "l1", "type": "pipeline_rigid", "pId": 14, "pKm": 30, "sKm": 30, "sId": 4, "uKm": 30},
        {"id": "plet", "type": "plet", "label": "PLET"},
    ],
}

WATER_INJECTION = {
    "title": "Water injection with raw seawater pump",
    "host": {"type": "tieback", "label": "Seawater\nintake"},
    "lanes": {"S": False, "U": True},
    "gap": 10,
    "chain": [
        {"id": "srp", "type": "srp", "label": "SRP"},
        {"id": "esdv", "type": "esdv"},
        {"id": "l1", "type": "pipeline_flex", "pType": "Water injection flowline", "pId": 10, "pKm": 4},
        {"id": "mf", "type": "manifold", "label": "WI manifold", "slots": 4},
        {"id": "w1", "type": "satellite_well", "label": "WI-1"},
    ],
}

NETWORK_FPSO = {
    "title": "Branched production network: manifolds, water injection and gas lift",
    "subtitle": "Daisy-chained manifolds with injection and gas-lift branches tied to an FPSO",
    "source": "Indicative concept layout; all values are placeholders",
    "host": {"type": "fpso", "slots": ["Turret"], "activeSlot": 0, "risers": [
        {"lane": "P", "slot": 0, "style": "lazywave", "label": 'Flexible riser, 10"', "color": "red", "ldx": 40},
        {"lane": "U", "slot": 0, "style": "static", "label": "Dynamic umbilical", "color": "yellow", "dx": 14}]},
    "lanes": {"S": False, "U": False},
    "chain": [
        {"id": "rb", "type": "riser_base", "label": "Riser base"},
        {"id": "sdu", "type": "sdu"},
        {"id": "l1", "type": "pipeline_pip", "pId": 10, "pKm": 12, "sKm": 12, "sId": 3, "uKm": 14, "w": 200},
        {"id": "m1", "type": "manifold", "label": "Manifold M1", "slots": 4},
        {"id": "l2", "type": "pipeline_flex", "pId": 10, "pKm": 4, "w": 110},
        {"id": "m2", "type": "manifold", "label": "Manifold M2", "slots": 4},
        {"id": "l3", "type": "pipeline_flex", "pId": 10, "pKm": 5, "w": 120},
        {"id": "m3", "type": "manifold", "label": "Manifold M3", "slots": 6},
    ],
    "branches": [
        {"name": "Water injection", "fluid": "water", "from": {"item": "m2", "side": "down", "label": "WI tie-in"}, "lanes": {"S": False, "U": False},
         "chain": [
             {"id": "wv1", "type": "valve_gate"},
             {"id": "wl1", "type": "pipeline_flex", "pId": 8, "pKm": 3, "w": 120},
             {"id": "wm", "type": "manifold", "label": "WI manifold", "slots": 4},
             {"id": "ww", "type": "satellite_well", "label": "WI-1"}]},
        {"name": "Gas lift", "fluid": "gaslift", "from": {"item": "rb", "side": "up", "label": "GL supply"}, "dy": 230, "lanes": {"S": False, "U": False},
         "chain": [
             {"id": "gv1", "type": "valve_check"},
             {"id": "gl1", "type": "pipeline_flex", "pId": 4, "pKm": 2, "w": 120},
             {"id": "glm", "type": "gl_manifold", "label": "Gas-lift manifold"}]},
    ],
    "notes": ["Branches inherit tie-in position from the parent item.", "Line styles show the fluid; see legend."],
}

COMPRESSION_HUB = {
    "title": "Subsea compression hub with remote power supply",
    "subtitle": "Two hosts: satellite fields feeding a compression station; floating wind providing power",
    "source": "Indicative concept layout; all values are placeholders",
    "fluid": "gas",
    "host": {"type": "tieback", "label": "Satellite\nfields"},
    "gap": 10,
    "lanes": {"S": True, "U": True},
    "chain": [
        {"id": "m1", "type": "manifold", "label": "Inlet manifold", "slots": 4},
        {"id": "v1", "type": "valve_gate"},
        {"id": "sep", "type": "separator", "label": "Inlet separator"},
        {"id": "cs", "type": "compression_station", "label": "Compression station"},
        {"id": "pt", "type": "pt_sensor"},
        {"id": "fm", "type": "mpfm"},
        {"id": "l1", "type": "pipeline_rigid", "pId": 20, "pKm": 60, "sKm": 60, "sId": 4, "uKm": 60, "w": 240},
        {"id": "rb", "type": "riser_base"},
    ],
    "branches": [
        {"name": "Power supply", "fluid": "power", "host": {"type": "wind", "label": "Floating wind", "risers": [{"lane": "P", "slot": 0, "style": "flex", "label": "Dynamic cable", "ldx": 12}]}, "lanes": {"S": False, "U": False},
         "dy": 380, "gap": 20,
         "chain": [
             {"id": "pc", "type": "cable_power", "w": 260, "pLabel": "Dynamic + static power cable, 25 km"},
             {"id": "pct", "type": "pct", "lane": "P"},
             {"id": "tx", "type": "transformer", "lane": "P"},
             {"id": "swg", "type": "switchgear", "lane": "P"},
             {"id": "vsd", "type": "vsd", "lane": "P"}]},
    ],
    "notes": ["Hosts, trains and tie-ins are independent and can be added in the Network tab."],
}

LOOP_PARALLEL = {
    "title": "Looped and parallel flowlines with a mirrored return train",
    "subtitle": "Rejoining loop, 2x parallel lines, right-to-left train",
    "themeName": "consulting",
    "host": {"type": "platform", "slots": ["P1"], "activeSlot": 0,
             "risers": [{"lane": "P", "slot": 0, "style": "rigid", "label": "Riser", "color": "red"}]},
    "chain": [
        {"type": "pipeline_rigid", "id": "pl_a", "w": 220, "pKm": 12, "pId": 12, "pCount": 2},
        {"type": "plet", "id": "plet_a"},
        {"type": "pipeline_rigid", "id": "pl_b", "w": 220, "pKm": 8, "pId": 12},
        {"type": "plet", "id": "plet_b"},
        {"type": "pipeline_rigid", "id": "pl_c", "w": 200, "pKm": 6, "pId": 12},
        {"type": "manifold", "id": "mf_a", "label": "Manifold"},
    ],
    "branches": [
        {"name": "Bypass loop", "fluid": "production", "lanes": {"S": False, "U": False},
         "from": {"item": "plet_a", "side": "down", "label": "Loop tie-in"}, "dy": 200,
         "chain": [{"type": "pipeline_rigid", "id": "pl_loop", "w": 272, "pKm": 9, "pId": 10}],
         "to": {"item": "plet_b", "side": "up", "label": "Rejoin"}},
        {"name": "Water injection (right-to-left)", "fluid": "water", "mirror": True,
         "lanes": {"S": False, "U": False},
         "from": {"item": "mf_a", "side": "down", "label": "WI tie-in"}, "dy": 380,
         "chain": [{"type": "pipeline_rigid", "id": "pl_wi", "w": 340, "pKm": 5, "pId": 8},
                   {"type": "plet", "id": "plet_wi"}]},
    ],
    "animate": False,
    "notes": ["Loop rejoins the main line downstream; production flows towards the host.",
              "The water train is mirrored: flow animation runs away from the tie-in."],
}

SINGLE_LINE = {
    "title": "Electrical single-line diagram",
    "subtitle": "Topside to subsea power distribution",
    "themeName": "mono",
    "host": {"type": "onshore", "slots": ["GRID"], "activeSlot": 0, "risers": []},
    "fluid": "power",
    "lanes": {"S": False, "U": False},
    "showSeabed": False,
    "showLegend": False,
    "chain": [
        {"type": "sld_generator", "id": "g1", "label": "G1"},
        {"type": "sld_breaker", "id": "cb1", "label": "CB1"},
        {"type": "sld_busbar", "id": "bb1", "label": "11 kV bus"},
        {"type": "sld_disconnector", "id": "ds1", "label": "DS1"},
        {"type": "sld_ct_vt", "id": "ct1", "label": "CT"},
        {"type": "sld_fuse", "id": "f1", "label": "F1"},
        {"type": "sld_breaker", "id": "cb2", "label": "CB2"},
        {"type": "transformer", "id": "tx1", "label": "TX1", "lane": "P"},
        {"type": "sld_motor", "id": "m1", "label": "M1"},
        {"type": "sld_earthing", "id": "pe1", "label": "PE"},
    ],
    "notes": ["Single-line schematic - protection and metering omitted."],
}


def _concept(title: str, chain: list[dict], connections: list[dict], notes: list[str]) -> dict:
    return {
        "title": title, "subtitle": "Generic North Sea-style concept - not an as-built field drawing",
        "source": "Illustrative architecture patterns; no operator-specific field configuration is represented",
        "freeform": True, "host": None, "chain": chain, "connections": connections,
        "showLegend": True, "showGrid": True, "animate": False, "flow": "forward",
        "notes": notes + ["Schematic only: sizes, distances, duties and protection require project engineering."],
    }


SEPARATION_CONCEPT = _concept(
    "Subsea separation with gas export and liquid boosting",
    [
        {"id": "host", "type": "jacket", "x": 20, "y": 120, "slots": ["Gas", "Oil", "WI"]},
        {"id": "gas_plet", "type": "plet", "x": 300, "y": 30},
        {"id": "oil_plet", "type": "plet", "x": 300, "y": 230},
        {"id": "sep", "type": "separator", "x": 570, "y": 130,
         "portConfig": {"mode": "additional", "lane": "P", "inlets": 0, "outlets": 1},
         "portOverrides": {"P-left": {"lane": "P", "connectionType": "multiphase"},
                           "P-right": {"lane": "P", "connectionType": "gas", "label": "Gas outlet"},
                           "P-out-1": {"lane": "P", "connectionType": "oil", "label": "Liquid outlet"}}},
        {"id": "boost", "type": "mpp", "x": 470, "y": 310},
        {"id": "template", "type": "template", "x": 900, "y": 130, "wells": 4, "hipps": True, "treeType": "hxt"},
    ],
    [
        {"from": "template", "to": "sep", "fromPort": "P-left", "toPort": "P-left", "lane": "P", "connectionType": "multiphase"},
        {"from": "sep", "to": "gas_plet", "fromPort": "P-right", "toPort": "P-right", "lane": "P", "connectionType": "gas"},
        {"from": "sep", "to": "boost", "fromPort": "P-out-1", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
        {"from": "boost", "to": "oil_plet", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
        {"from": "gas_plet", "to": "host", "fromPort": "P-left", "toPort": "J-0", "lane": "P", "kind": "riser", "connectionType": "gas"},
        {"from": "oil_plet", "to": "host", "fromPort": "P-left", "toPort": "J-1", "lane": "P", "kind": "riser", "connectionType": "oil"},
    ], ["Gas and liquid outlets are independent example services; separator performance is not calculated."],
)

DAISY_CHAIN_CONCEPT = _concept(
    "Daisy-chain production with a shared service line",
    [
        {"id": "host", "type": "jacket", "x": 20, "y": 150, "slots": ["Production", "Service"]},
        {"id": "prod", "type": "plet", "x": 300, "y": 150},
        {"id": "chem", "type": "plet", "x": 300, "y": 390, "label": "Service PLET",
         "portOverrides": {"S-left": {"lane": "S", "connectionType": "chemical"},
                           "S-right": {"lane": "S", "connectionType": "chemical"}}},
        {"id": "a", "type": "template", "x": 570, "y": 150, "label": "Template A", "wells": 2, "hipps": False, "treeType": "vxt"},
        {"id": "b", "type": "template", "x": 970, "y": 150, "label": "Template B", "wells": 2, "hipps": False, "treeType": "vxt"},
        {"id": "c", "type": "template", "x": 1370, "y": 150, "label": "Template C", "wells": 2, "hipps": False, "treeType": "vxt"},
    ],
    [
        {"from": "c", "to": "b", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "multiphase"},
        {"from": "b", "to": "a", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "multiphase"},
        {"from": "a", "to": "prod", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "multiphase"},
        {"from": "prod", "to": "host", "fromPort": "P-left", "toPort": "J-0", "lane": "P", "kind": "riser", "connectionType": "multiphase"},
        {"from": "host", "to": "chem", "fromPort": "J-1", "toPort": "S-left", "lane": "S", "kind": "riser", "connectionType": "chemical"},
        {"from": "chem", "to": "a", "fromPort": "S-right", "toPort": "S-left", "lane": "S", "connectionType": "chemical"},
        {"from": "a", "to": "b", "fromPort": "S-right", "toPort": "S-left", "lane": "S", "connectionType": "chemical"},
        {"from": "b", "to": "c", "fromPort": "S-right", "toPort": "S-left", "lane": "S", "connectionType": "chemical"},
    ], ["Production returns through successive template headers; service supply runs in the opposite direction."],
)

OIL_WATER_CONCEPT = _concept(
    "Oil production and independent water-injection system",
    [
        {"id": "host", "type": "fpso", "x": 30, "y": 60, "slots": ["Oil", "Water", "Control"]},
        {"id": "oil", "type": "plet", "x": 390, "y": 100, "label": "Oil PLET"},
        {"id": "water", "type": "plet", "x": 390, "y": 370, "label": "Water-injection PLET",
         "portOverrides": {"P-left": {"lane": "P", "connectionType": "water_injection"},
                           "P-right": {"lane": "P", "connectionType": "water_injection"}}},
        {"id": "prod", "type": "template", "x": 760, "y": 100, "wells": 4, "hipps": True, "treeType": "hxt", "label": "Production"},
        {"id": "inj", "type": "manifold", "x": 760, "y": 440, "slots": 4, "label": "Injection manifold",
         "portOverrides": {"P-left": {"lane": "P", "connectionType": "water_injection"}}},
        {"id": "sdu", "type": "sdu", "x": 620, "y": 670},
    ],
    [
        {"from": "prod", "to": "oil", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
        {"from": "oil", "to": "host", "fromPort": "P-left", "toPort": "J-0", "lane": "P", "kind": "riser", "style": "flex", "connectionType": "oil"},
        {"from": "host", "to": "water", "fromPort": "J-1", "toPort": "P-left", "lane": "P", "kind": "riser", "style": "flex", "connectionType": "water_injection"},
        {"from": "water", "to": "inj", "fromPort": "P-right", "toPort": "P-left", "lane": "P", "connectionType": "water_injection"},
        {"from": "host", "to": "sdu", "fromPort": "J-2", "toPort": "U-left", "lane": "U", "kind": "riser", "style": "flex", "connectionType": "umbilical_dynamic"},
        {"from": "sdu", "to": "prod", "fromPort": "U-right", "toPort": "U-left", "lane": "U", "connectionType": "umbilical_static"},
    ], ["Blue water injection remains on the process lane, separate from orange chemical/service supply."],
)

HEATING_CONCEPT = _concept(
    "Long heated tieback with electrical power and MEG service",
    [
        {"id": "host", "type": "jacket", "x": 20, "y": 130, "slots": ["Production", "MEG", "Power"]},
        {"id": "plet", "type": "plet", "x": 330, "y": 130},
        {"id": "deh", "type": "deh", "x": 610, "y": 130, "label": "Flowline heating",
         "portConfig": {"mode": "additional", "lane": "P", "inlets": 1, "outlets": 0},
         "portOverrides": {"P-in-1": {"lane": "P", "connectionType": "power", "label": "Power input"}}},
        {"id": "template", "type": "template", "x": 1030, "y": 130, "wells": 4, "hipps": True, "treeType": "hxt"},
        {"id": "power", "type": "transformer", "x": 610, "y": 440, "lane": "P"},
        {"id": "chem", "type": "cip", "x": 350, "y": 620, "lane": "S"},
    ],
    [
        {"from": "template", "to": "deh", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "multiphase"},
        {"from": "deh", "to": "plet", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "multiphase"},
        {"from": "plet", "to": "host", "fromPort": "P-left", "toPort": "J-0", "lane": "P", "kind": "riser", "connectionType": "multiphase"},
        {"from": "host", "to": "power", "fromPort": "J-2", "toPort": "P-left", "lane": "P", "kind": "riser", "connectionType": "power"},
        {"from": "power", "to": "deh", "fromPort": "P-right", "toPort": "P-in-1", "lane": "P", "connectionType": "power"},
        {"from": "host", "to": "chem", "fromPort": "J-1", "toPort": "S-left", "lane": "S", "kind": "riser", "connectionType": "chemical"},
        {"from": "chem", "to": "template", "fromPort": "S-right", "toPort": "S-left", "lane": "S", "connectionType": "chemical"},
    ], ["DEH and MEG illustrate flow-assurance architecture, not electrical or thermal sizing.",
        "Power attachment points are conceptual; specify a dedicated power connector for a detailed design."],
)

COMPRESSION_CONCEPT = _concept(
    "Subsea gas compression hub and satellite manifold",
    [
        {"id": "host", "type": "semisub", "x": 20, "y": 100, "slots": ["Gas", "Power"]},
        {"id": "base", "type": "riser_skid", "x": 330, "y": 100},
        {"id": "comp", "type": "wgc", "x": 630, "y": 100},
        {"id": "cool", "type": "hx", "x": 850, "y": 100},
        {"id": "manifold", "type": "manifold", "x": 1100, "y": 100, "slots": 4},
        {"id": "sat", "type": "satellite_well", "x": 1380, "y": 100},
    ],
    [
        {"from": "sat", "to": "manifold", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "gas"},
        {"from": "manifold", "to": "cool", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "gas"},
        {"from": "cool", "to": "comp", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "gas"},
        {"from": "comp", "to": "base", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "gas"},
        {"from": "base", "to": "host", "fromPort": "P-left", "toPort": "J-0", "lane": "P", "kind": "riser", "style": "flex", "connectionType": "gas"},
    ], ["Generic compression architecture with inlet conditioning; recycle, shutdown and utility detail are omitted."],
)

SATELLITE_CONCEPT = _concept(
    "Brownfield satellite tie-in with chemical support",
    [
        {"id": "host", "type": "tieback", "x": 20, "y": 120, "label": "Existing field"},
        {"id": "plet", "type": "plet", "x": 310, "y": 120},
        {"id": "manifold", "type": "manifold", "x": 630, "y": 120, "slots": 2,
         "portConfig": {"mode": "additional", "lane": "P", "inlets": 0, "outlets": 1}},
        {"id": "well1", "type": "satellite_well", "x": 1000, "y": 20},
        {"id": "well2", "type": "satellite_well", "x": 1000, "y": 330},
    ],
    [
        {"from": "well1", "to": "manifold", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
        {"from": "well2", "to": "manifold", "fromPort": "P-left", "toPort": "P-out-1", "lane": "P", "connectionType": "oil"},
        {"from": "manifold", "to": "plet", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
        {"from": "plet", "to": "host", "fromPort": "P-left", "toPort": "P-right", "lane": "P", "connectionType": "oil"},
    ], ["Generic existing-infrastructure tie-in; verify receiving-system capacity and isolation independently."],
)

PRESETS = {
    "Two-template tieback to platform": TIEBACK,
    "Branched network: manifolds + injection + gas lift": NETWORK_FPSO,
    "Compression hub with remote power": COMPRESSION_HUB,
    "Loops, parallel lines and mirrored train": LOOP_PARALLEL,
    "Electrical single-line diagram": SINGLE_LINE,
    "Single template to FPSO": SINGLE_FPSO,
    "Single 4-slot template to jackup": SINGLE_JACKUP,
    "Subsea processing station": PROCESSING,
    "Water injection (SRP + manifold)": WATER_INJECTION,
    "North Sea concept: separation and boosting": SEPARATION_CONCEPT,
    "North Sea concept: daisy-chain templates": DAISY_CHAIN_CONCEPT,
    "North Sea concept: oil and water injection": OIL_WATER_CONCEPT,
    "North Sea concept: heated tieback and MEG": HEATING_CONCEPT,
    "North Sea concept: subsea gas compression": COMPRESSION_CONCEPT,
    "North Sea concept: brownfield satellites": SATELLITE_CONCEPT,
    "Blank – jacket only": {"title": "New layout", "host": {"type": "jacket", "slots": ["J1"], "activeSlot": 0, "risers": [{"lane": "P", "slot": 0, "style": "rigid", "label": "Riser", "color": "red"}]}, "chain": []},
    "Blank canvas – draw your own": {
        "title": "New subsea layout",
        "freeform": True,
        "host": None,
        "chain": [],
        "showLegend": False,
        "showGrid": True,
        "animate": False,
    },
}


def get_preset(name: str) -> dict:
    return copy.deepcopy(PRESETS[name])
