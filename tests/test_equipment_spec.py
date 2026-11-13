"""Equipment specification tests: python tests\\test_equipment_spec.py."""
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from subsea.bom import equipment_list
from subsea.equipment import (
    DESIGN_FIELDS, customization_errors, design_limit_errors, effective_design_limits,
    parse_design_limits, removed_port_errors,
)
from subsea.spec import chain_to_df, df_to_chain, validate


def test_limit_validation_and_inheritance():
    defaults = {"pressureBar": 345, "temperatureC": 120, "waterDepthM": 1500, "flowM3Day": 5000}
    item = {"id": "base", "type": "riser_base", "designLimits": {"pressureBar": 450, "temperatureC": -10}}
    assert effective_design_limits({"designLimits": defaults}, item) == {**defaults, "pressureBar": 450, "temperatureC": -10}
    assert parse_design_limits({"pressureBar": "345", "temperatureC": "-20", "waterDepthM": "", "flowM3Day": "1000"}) == {
        "pressureBar": 345.0, "temperatureC": -20.0, "flowM3Day": 1000.0,
    }
    assert parse_design_limits({"pressureBar": ""}) == {}
    for limits in ({"pressureBar": 0}, {"waterDepthM": -1}, {"temperatureC": -274},
                   {"flowM3Day": math.inf}, {"pressureBar": math.nan}, {"unknown": 1},
                   {"flowM3Day": True}, {"pressureBar": None}):
        assert design_limit_errors(limits, "Test"), limits
    for text in ("bad", "nan", "inf", "0", "-1"):
        try:
            parse_design_limits({"pressureBar": text})
        except ValueError:
            pass
        else:
            raise AssertionError(text)
    assert design_limit_errors({"temperatureC": -273.15, "waterDepthM": 0}, "Test") == []


def test_ports_and_connected_port_removal():
    base = {"id": "base", "type": "riser_base",
            "portConfig": {"mode": "replace", "lane": "P", "inlets": 2, "outlets": 3}}
    spec = {"freeform": True, "chain": [base],
            "connections": [{"from": "base", "fromPort": "P-out-2", "to": "other", "toPort": "P-left"}]}
    assert customization_errors(base) == []
    assert removed_port_errors(spec, base) == []
    for count in (0, 1, 2):
        changed = {**base, "portConfig": {**base["portConfig"], "outlets": count}}
        assert removed_port_errors(spec, changed)
    changed = {**base}
    changed.pop("portConfig")
    assert removed_port_errors(spec, changed)
    for value in (-1, 25, 1.5, True):
        changed = {**base, "portConfig": {**base["portConfig"], "inlets": value}}
        assert customization_errors(changed)
    for mode in ("additional", "replace"):
        for count in (0, 1, 24):
            changed = {**base, "portConfig": {**base["portConfig"], "mode": mode, "inlets": count}}
            assert customization_errors(changed) == []


def test_optional_riser_service_ports():
    for type_id in ("riser_base", "riser_skid"):
        base = {"id": "base", "type": type_id, "servicePorts": True, "umbilicalPorts": True}
        assert customization_errors(base) == []
        for field, lane in (("servicePorts", "S"), ("umbilicalPorts", "U")):
            assert customization_errors({**base, field: "yes"})
            spec = {"connections": [{"from": "base", "fromPort": f"{lane}-right", "lane": lane}]}
            assert removed_port_errors(spec, base) == []
            assert removed_port_errors(spec, {**base, field: False})
            custom = {**base, field: False, "portConfig": {
                "mode": "replace", "lane": lane, "inlets": 1, "outlets": 1,
            }}
            assert removed_port_errors(spec, custom) == []


def test_spec_table_json_and_csv_roundtrip():
    spec = {
        "freeform": True, "host": None,
        "designLimits": {"pressureBar": 345, "temperatureC": 120, "waterDepthM": 1000, "flowM3Day": 5000},
        "chain": [
            {"id": "skid", "type": "riser_skid", "designLimits": {"pressureBar": 450},
             "portConfig": {"mode": "replace", "lane": "P", "inlets": 2, "outlets": 3}},
            {"id": "template", "type": "template", "wells": 6, "hipps": False, "treeType": "hxt",
             "portConfig": {"mode": "additional", "lane": "P", "inlets": 1, "outlets": 2}},
        ],
    }
    assert validate(spec) == [], validate(spec)
    restored = json.loads(json.dumps(spec))
    restored["chain"], errors = df_to_chain(chain_to_df(restored["chain"]))
    assert errors == [] and restored == spec
    bom = equipment_list(spec)
    assert bom.iloc[0]["Design pressure (bar)"] == 450
    assert bom.iloc[1]["Design pressure (bar)"] == 345
    assert bom.iloc[1]["Xmas tree type"] == "hxt"
    assert not bom.iloc[1]["HIPPS"]
    assert bom.iloc[0]["Configured outlets"] == 3
    assert all(field["label"] in bom.to_csv(index=False) for field in DESIGN_FIELDS.values())
    spec["chain"][1]["treeType"] = "invalid"
    spec["designLimits"]["pressureBar"] = -1
    assert len(validate(spec)) >= 2


if __name__ == "__main__":
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            print("PASS:", name)
