import sys, pathlib, copy, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from subsea.presets import PRESETS, get_preset
from subsea.spec import validate, add_branch, remove_branch, trains, all_ids
from subsea.checks import run_checks
from subsea.bom import equipment_list, totals

def test_all_presets_valid():
    for n in PRESETS:
        assert validate(get_preset(n)) == [], (n, validate(get_preset(n)))

def test_single_four_slot_jackup_preset():
    name = "Single 4-slot template to jackup"
    spec = get_preset(name)
    assert spec["host"]["type"] == "jackup"
    assert [(r["lane"], r["slot"]) for r in spec["host"]["risers"]] == [("P", 0), ("S", 1), ("U", 2)]
    template = [item for item in spec["chain"] if item["type"] == "template"]
    assert len(template) == 1 and template[0]["wells"] == 4
    inventory = equipment_list(spec)
    assert totals(inventory)["wells"] == 4
    assert inventory.loc[inventory["Type"] == "template", "Qty"].sum() == 1
    assert inventory.loc[inventory["Type"] == "pipeline_pip", ["Size (in)", "Length (km)"]].isna().all().all()
    spec["chain"][-1]["wells"] = 6
    assert get_preset(name)["chain"][-1]["wells"] == 4

def test_branch_ops_and_validation():
    s = get_preset("Branched network: manifolds + injection + gas lift")
    assert len(trains(s)) == 3
    bid = add_branch(s, "m3", "up", "co2", "CO2")
    assert bid == "b3" and validate(s) == []
    s["branches"][0]["from"]["item"] = "nope"
    assert any("tie-in item" in m for m in validate(s))
    s2 = get_preset("Branched network: manifolds + injection + gas lift")
    s2["branches"][0]["chain"][0]["id"] = "m1"          # duplicate across trains
    assert any("duplicate id" in m for m in validate(s2))
    s3 = get_preset("Branched network: manifolds + injection + gas lift")
    remove_branch(s3, "b1"); assert len(trains(s3)) == 2 and validate(s3) == []

def test_checks_fire():
    s = get_preset("Blank – jacket only")
    s["chain"] = [{"id": "a", "type": "spool"}, {"id": "l", "type": "pipeline_rigid", "pKm": 30, "pId": 12},
                  {"id": "l2", "type": "pipeline_rigid", "pKm": 5, "pId": 10}, {"id": "p", "type": "mpp"}, {"id": "c", "type": "civ"}]
    s["lanes"] = {"S": False, "U": False}
    rules = {f["rule"] for f in run_checks(s)}
    assert {"isolation-start", "isolation-end", "ssiv", "pigging", "size-change", "rotating", "chem"} <= rules, rules

def test_concept_review_never_treats_missing_evidence_as_approval():
    spec = {"freeform": True, "chain": [{"id": "a", "type": "plet"}, {"id": "b", "type": "plet"}],
            "connections": [{"from": "a", "fromPort": "P-right", "to": "b", "toPort": "P-left", "lane": "P"}]}
    before = copy.deepcopy(spec)
    findings = run_checks(spec)
    assert spec == before
    by_rule = {f["rule"]: f for f in findings}
    assert by_rule["declared-connectivity"]["status"] == "Screened"
    for rule in ("basis", "barriers", "hydraulics", "mechanical", "risers", "seabed",
                 "controls", "pressure-qualification", "interface-qualification", "missing-layout-limits"):
        assert by_rule[rule]["status"] == "Not assessed", rule
    assert not {"isolation-start", "isolation-end", "rotating", "size-change"} & set(by_rule), \
        "Freeform equipment-list order must not imply a process path"
    assert all({"category", "status", "level", "rule", "where", "message", "action", "evidence"} <= f.keys() for f in findings)
    empty = run_checks({"freeform": True, "chain": []})
    assert any(f["rule"] == "empty-design" for f in empty)
    assert not any(f["status"] == "Screened" for f in empty)


def test_concept_review_connections_slots_and_islands():
    spec = {"freeform": True, "chain": [
        {"id": "host", "type": "jacket", "slots": ["Production"]},
        {"id": "a", "type": "plet"}, {"id": "b", "type": "plet"},
        {"id": "cover", "type": "trawl_guard"}],
        "connections": [
            {"from": "host", "fromPort": "J-0", "to": "a", "toPort": "P-left", "lane": "P"},
            {"from": "host", "fromPort": "J-0", "to": "a", "toPort": "P-right", "lane": "P"},
            {"from": "a", "to": "missing", "lane": "P"}]}
    findings = run_checks(spec)
    assert any(f["rule"] == "missing-endpoint" and f["level"] == "error" for f in findings)
    assert any(f["rule"] == "port-occupancy" and "J-0" in f["message"] for f in findings)
    assert any(f["rule"] == "network-islands" for f in findings)
    disconnected = {f["where"] for f in findings if f["rule"] == "unconnected-equipment"}
    assert disconnected == {"b"}, disconnected
    assert "cover" not in disconnected
    spec["connections"] = [{"from": "a", "fromPort": "P-left", "to": "b",
                            "toPort": "P-right", "lane": "P", "connectionType": "umbilical_static"}]
    rules = {f["rule"] for f in run_checks(spec)}
    assert "service-lane" in rules
    spec["connections"][0]["toPort"] = "U-right"
    assert any(f["level"] == "error" and "lane" in f["message"].lower() for f in run_checks(spec))
    schematic = {"host": {"id": "host", "type": "jacket", "slots": ["J1"],
                           "risers": [{"slot": 0, "lane": "P"}]},
                 "chain": [{"id": "a", "type": "plet"}, {"id": "b", "type": "plet"}],
                 "branches": [{"from": {"item": "b"}, "chain": [{"id": "c", "type": "plet"}]}]}
    findings = run_checks(schematic)
    assert not any(f["rule"] in ("network-islands", "unconnected-equipment") for f in findings)
    assert any(f["rule"] == "declared-connectivity" for f in findings)
    schematic["host"]["risers"][0]["slot"] = -1
    assert any(f["rule"] == "spec-invalid" and "slot" in f["message"] for f in run_checks(schematic))


def test_concept_review_declared_limits_and_bad_data():
    limits = {"pressureBar": 345, "temperatureC": 120, "waterDepthM": 1000, "flowM3Day": 5000}
    spec = {"freeform": True, "designLimits": limits, "chain": [
        {"id": "a", "type": "plet", "designLimits": {**limits, "pressureBar": 200}},
        {"id": "b", "type": "plet", "rating": "10 K psi"}]}
    findings = run_checks(spec)
    pressure = next(f for f in findings if f["rule"] == "declared-limit-pressureBar")
    assert pressure["status"] == "Action required" and "200" in pressure["message"] and "345" in pressure["message"]
    assert any(f["rule"] == "declared-limit-temperatureC" and f["status"] == "Screened" for f in findings)
    assert any(f["rule"] == "item-limits-unverified" and f["where"] == "main/chain/1" for f in findings), \
        "Layout inheritance or a free-text rating must not count as equipment qualification"
    spec["chain"][0]["designLimits"]["pressureBar"] = 345
    assert next(f for f in run_checks(spec) if f["rule"] == "declared-limit-pressureBar")["status"] == "Screened"
    for field, value in (("pKm", float("nan")), ("pId", "ten"), ("tag", 123)):
        invalid = copy.deepcopy(spec)
        invalid["chain"][0][field] = value
        results = run_checks(invalid)
        assert any(f["rule"] == "spec-invalid" and f["level"] == "error" for f in results)
        assert any(f["rule"] == "screening-blocked" for f in results)


def test_concept_review_valves_and_procurement():
    spec = {"host": {"id": "host", "type": "jacket", "tag": "XV-101"},
            "chain": [{"id": "a", "type": "valve_gate"}, {"id": "b", "type": "valve_ball"},
                      {"id": "pump", "type": "mpp"},
                      {"id": "end", "type": "plet", "installationStatus": "New",
                       "internalValves": [{"id": "v", "pipe": "P-1", "kind": "check", "tag": " xv-101 "}]}]}
    findings = run_checks(spec)
    assert any(f["rule"] == "rotating" for f in findings), "Two upstream valves do not provide downstream isolation"
    assert any(f["rule"] == "dup-tag" and f["where"].endswith("/valves/v") for f in findings)
    assert any(f["rule"] == "new-equipment-data" for f in findings)
    spec["chain"] = [{"id": "a", "type": "plet"}, {"id": "b", "type": "plem"}]
    assert any(f["rule"] == "isolation-start" for f in run_checks(spec)), "A PLET/PLEM is not proof of isolation"
    spec["connections"] = [{"from": "a", "to": "b", "fromPort": "P-right", "toPort": "P-left",
                            "kind": "riser", "psv": True, "psvTag": "XV-101"}]
    assert any(f["rule"] == "dup-tag" and f["where"] == "connections/0/psv" for f in run_checks(spec))
    for name in PRESETS:
        results = run_checks(get_preset(name))
        assert results and all(f["status"] in ("Action required", "Not assessed", "Screened") for f in results), name


def test_review_excel_and_pdf_complete_checklists():
    from io import BytesIO
    from unittest.mock import patch
    import pandas as pd
    from openpyxl import load_workbook
    from subsea.review_export import review_excel, review_pdf

    report = pd.DataFrame([{
        "Design": "=SUM(1,2)", "Area": "Pressure & temperature <review>", "Status": status,
        "Severity": "warning" if status == "Action required" else "info",
        "Rule": f"CHECK-{index:03}", "Reference": f"main/chain/{index}",
        "Finding": f"FINDING-{index:03} " + "Confirm the declared equipment limit and project design basis. " * 35,
        "Required follow-up": f"FOLLOW-{index:03}", "Evidence / limitations": f"EVIDENCE-{index:03}",
    } for index, status in enumerate(("Action required", "Not assessed", "Screened") * 4)])
    before = report.copy(deep=True)
    workbook = load_workbook(BytesIO(review_excel(report)))
    assert workbook.sheetnames == ["Open checklist", "Full review", "Coverage", "Read me"]
    full = list(workbook["Full review"].values)
    assert list(full[0]) == ["Check #"] + list(report.columns)
    assert [row[0] for row in full[1:]] == list(range(1, len(report) + 1))
    assert [list(row[1:]) for row in full[1:]] == report.values.tolist()
    opened = list(workbook["Open checklist"].values)
    assert len(opened) == 1 + sum(report["Status"] != "Screened")
    assert all(row[opened[0].index("Status")] != "Screened" for row in opened[1:])
    coverage = list(workbook["Coverage"].values)
    assert list(coverage[0]) == ["Area", "Action required", "Not assessed", "Screened"]
    assert coverage[1][1:] == (4, 4, 4)
    assert all(cell.data_type != "f" for sheet in workbook for row in sheet for cell in row)
    with patch("reportlab.rl_config.pageCompression", 0):
        pdf = review_pdf(report)
    assert pdf.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type /Page\b", pdf)) > 1, "The complete checklist must paginate"
    for row in report.to_dict("records"):
        for field in ("Rule", "Required follow-up", "Evidence / limitations"):
            assert row[field].encode() in pdf, (field, row["Rule"])
    assert b"not engineering approval" in pdf
    pd.testing.assert_frame_equal(report, before)


def test_equipment_list():
    s = get_preset("Two-template tieback to platform")
    df = equipment_list(s); t = totals(df)
    assert t["wells"] == 8 and t["flowline_km"] == 26
    assert "XV-101" in set(df["Tag"]) and "PT-101" in set(df["Tag"])

def test_current_network_edits():
    from subsea.network import connection_rows, apply_connection_rows, implicit_rows
    from subsea.cases import CaseStore
    import tempfile
    spec = {"freeform": True, "chain": [{"id": "a", "type": "plet"}, {"id": "b", "type": "plet"}],
            "connections": [{"from": "a", "to": "b", "fromPort": "P-right", "toPort": "P-left",
                             "lane": "P", "kind": "riser", "waypoints": [{"x": 400, "y": 260}],
                             "rating": "10 K psi"}]}
    rows = connection_rows(spec).to_dict("records")
    assert rows[0]["From"] == "a" and rows[0]["To"] == "b"
    assert apply_connection_rows(spec, rows) == spec
    rows[0].update({"PSV": True, "PSV tag": "PSV-101", "PSV position (%)": 75, "Service": "gas"})
    updated = apply_connection_rows(spec, rows)
    assert updated["connections"][0]["psv"] is True
    assert updated["connections"][0]["psvPosition"] == 75
    assert updated["connections"][0]["waypoints"] == spec["connections"][0]["waypoints"]
    assert updated["connections"][0]["rating"] == "10 K psi"
    assert "psv" not in spec["connections"][0]
    with tempfile.TemporaryDirectory(prefix="subsea-network-") as directory:
        store = CaseStore(pathlib.Path(directory) / "cases.sqlite3")
        case_id, version = store.save("Riser PSV network", updated)
        assert connection_rows(store.load(case_id, version)).to_dict("records") == connection_rows(updated).to_dict("records")
    for column, value in (("From", "other"), ("PSV position (%)", -1), ("Kind", "jumper")):
        invalid = copy.deepcopy(rows)
        invalid[0][column] = value
        try:
            apply_connection_rows(spec, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted invalid {column}")
    assert implicit_rows(spec).empty
    preset = get_preset("Two-template tieback to platform")
    assert not implicit_rows(preset).empty
    assert any("Preset riser" in kind for kind in implicit_rows(preset)["Kind"])


def test_network_populates_loaded_design():
    import logging
    from streamlit.testing.v1 import AppTest
    previous_logging = logging.root.manager.disable
    logging.disable(logging.WARNING)
    try:
        app = AppTest.from_file(str(pathlib.Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        spec = {"freeform": True, "host": None, "chain": [
                    {"id": "a", "type": "plet", "x": 100, "y": 120},
                    {"id": "b", "type": "plet", "x": 500, "y": 260}],
                "connections": [{"from": "a", "to": "b", "fromPort": "P-right", "toPort": "P-left",
                                 "lane": "P", "kind": "riser", "waypoints": [{"x": 400, "y": 200}]}]}
        app.session_state.spec = copy.deepcopy(spec)
        app.session_state.ver += 1
        app.run()
        assert not app.exception
        review = next(table.value for table in app.dataframe if {"Rule", "Status", "Finding"} <= set(table.value.columns))
        assert "interface-qualification" in set(review["Rule"])
        assert "Not assessed" in set(review["Status"])
        assert any("Action required" == metric.label for metric in app.metric)
        next(widget for widget in app.selectbox if widget.label == "Review area").select("Network topology").run()
        assert not app.exception
        filtered = next(table.value for table in app.dataframe if {"Rule", "Status", "Finding"} <= set(table.value.columns))
        assert set(filtered["Area"]) == {"Network topology"}
        next(widget for widget in app.selectbox if widget.label == "Review area").select("All areas").run()
        key = f"network_connections_{app.session_state.ver}"
        app.session_state[key] = {"edited_rows": {0: {"PSV": True, "PSV tag": "PSV-202", "PSV position (%)": 30}},
                                  "added_rows": [], "deleted_rows": []}
        next(button for button in app.button if button.label == "Apply network connections").click().run()
        assert not app.exception and not app.error
        assert app.session_state.spec["connections"][0]["psvTag"] == "PSV-202"
        assert app.session_state.spec["connections"][0]["psvPosition"] == 30
        assert app.session_state.spec["connections"][0]["waypoints"] == spec["connections"][0]["waypoints"]
        next(button for button in app.button if button.label == "Undo network connections").click().run()
        assert app.session_state.spec["connections"] == spec["connections"]
        app.session_state.spec = {"freeform": True, "host": None, "chain": []}
        app.session_state.ver += 1
        app.run()
        assert not app.exception
        assert any("No explicit port-to-port" in caption.value for caption in app.caption)
    finally:
        logging.disable(previous_logging)

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)


def test_flow_mirror_rejoin_validation():
    from subsea.presets import PRESETS
    from subsea.spec import validate
    import copy
    sp = copy.deepcopy(PRESETS["Loops, parallel lines and mirrored train"])
    assert validate(sp) == []
    sp["branches"][0]["to"]["item"] = "nope"
    sp["branches"][1]["flow"] = "sideways"
    errs = validate(sp)
    assert any("rejoin item" in e for e in errs) and any("flow mode" in e for e in errs)
    print("ok test_flow_mirror_rejoin_validation")


if __name__ == "__main__":
    test_flow_mirror_rejoin_validation()
