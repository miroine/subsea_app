"""Case persistence, inventory editing and comparison: python tests\\test_cases.py."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import sqlite3
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subsea.cases import CaseStore, apply_equipment_rows, compare_designs, equipment_rows
from subsea.presets import get_preset


def run():
    with tempfile.TemporaryDirectory(prefix="subsea-cases-") as directory:
        path = Path(directory) / "cases.sqlite3"
        store = CaseStore(path)
        assert store.list_cases() == [] and not path.exists()
        spec = get_preset("North Sea concept: oil and water injection")
        case_id, number = store.save("Oil case", spec, "Base")
        assert number == 1
        spec["title"] = "Updated oil case"
        assert store.load(case_id, 1)["title"] != spec["title"]
        assert store.save("Oil case", spec, "Updated", case_id)[1] == 2
        assert CaseStore(path).load(case_id, 2) == spec
        duplicate, _ = store.duplicate(case_id, 1, "Independent copy")
        store.delete(case_id, 2)
        assert store.save("Oil case", spec, "After deletion", case_id)[1] == 3
        with ThreadPoolExecutor(max_workers=4) as executor:
            numbers = list(executor.map(lambda n: CaseStore(path).save("Oil case", spec, str(n), case_id)[1], range(8)))
        assert len(set(numbers)) == 8
        store.delete(case_id)
        assert store.load(duplicate, 1)["title"] != spec["title"]
        try:
            store.load(case_id, 1)
            raise AssertionError("Deleted case loaded")
        except ValueError:
            pass
        store.delete(duplicate, 1)
        assert not store.list_cases()
        try:
            store.save("Invalid", {"value": float("nan")})
            raise AssertionError("Invalid snapshot accepted")
        except ValueError:
            pass
        assert not store.list_cases()
        broken = Path(directory) / "broken.sqlite3"
        broken.write_text("not a SQLite database", encoding="utf-8")
        try:
            CaseStore(broken).list_cases()
            raise AssertionError("Storage failure was hidden")
        except sqlite3.DatabaseError:
            pass
        broken.unlink()
        print("PASS: durable snapshots, independent copies, deletes, monotonic versions and concurrent saving")

    original = get_preset("North Sea concept: oil and water injection")
    original["overrides"] = {"water": {"dx": 20, "scale": 1.4, "label": "Adjusted water PLET"}}
    rows = equipment_rows(original)
    assert len(rows) == len(original["chain"])
    assert apply_equipment_rows(original, rows) == original
    water = next(row for row in rows if row["Id"] == "water")
    assert water["Size (%)"] == 140 and water["Offset X"] == 20
    water["Label"] = "New water label"
    water["Offset Y"] = 70
    props = json.loads(water["Properties (JSON)"])
    props["designLimits"] = {"pressureBar": 400}
    water["Properties (JSON)"] = json.dumps(props)
    updated = apply_equipment_rows(original, rows)
    assert updated["overrides"]["water"]["label"] == "New water label"
    assert next(item for item in updated["chain"] if item["id"] == "water")["designLimits"]["pressureBar"] == 400
    assert updated["connections"] == original["connections"]
    assert compare_designs(original, original) == []
    changes = compare_designs(original, updated)
    assert {row["Object"] for row in changes} == {"Equipment/water"}
    assert any("pressureBar" in row["Field"] for row in changes)
    bad = copy.deepcopy(rows)
    bad[0]["Size (%)"] = float("nan")
    try:
        apply_equipment_rows(original, bad)
        raise AssertionError("Invalid scale accepted")
    except ValueError:
        pass
    old = copy.deepcopy(original)
    new = copy.deepcopy(original)
    new["chain"].pop()
    new["connections"][0]["width"] = 7
    new["themeName"] = "mono"
    changes = compare_designs(old, new)
    assert any(row["Change"] == "Removed" for row in changes)
    assert any(row["Object"].startswith("Connection/") and row["Field"] == "width" for row in changes)
    assert any(row["Object"] == "Settings/Layout" for row in changes)
    reordered = copy.deepcopy(original)
    reordered["chain"].reverse()
    assert any(row["Field"] == "_order" for row in compare_designs(original, reordered))
    anonymous_hosts = {"host": {"type": "jacket"}, "chain": [],
                       "branches": [{"host": {"type": "fpso"}, "chain": []}]}
    assert [row["Id"] for row in equipment_rows(anonymous_hosts)] == ["host_1", "host_2"]
    assert "id" not in anonymous_hosts["host"]
    host_rows = equipment_rows(anonymous_hosts)
    host_rows[0]["Label"] = "First host"
    edited_hosts = apply_equipment_rows(anonymous_hosts, host_rows)
    assert edited_hosts["overrides"]["host_1"]["label"] == "First host"
    print("PASS: all-equipment edits preserve unchanged symbols/connections; field-level comparisons include metadata")
    test_inventory_form()


def test_inventory_form():
    from streamlit.testing.v1 import AppTest
    with tempfile.TemporaryDirectory(prefix="subsea-inventory-form-") as directory:
        previous_path = os.environ.get("SUBSEA_CASES_PATH")
        previous_logging = logging.root.manager.disable
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state[f"all_equipment_table_{app.session_state.ver}"] = {
                "edited_rows": {0: {"Label": "Inventory form edit", "Size (%)": 135, "Offset X": 42}},
                "added_rows": [], "deleted_rows": [],
            }
            next(button for button in app.button if button.label == "Apply all equipment settings").click().run()
            assert not app.exception, [error.message for error in app.exception]
            assert not app.error, [error.value for error in app.error]
            assert app.session_state.spec["overrides"]["host_1"] == {
                "label": "Inventory form edit", "scale": 1.35, "dx": 42, "dy": 0, "hidden": False,
            }
        finally:
            logging.disable(previous_logging)
            if previous_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = previous_path
    print("PASS: actual Streamlit inventory form accepts edited widget rows and persists host label/size/position")


if __name__ == "__main__":
    run()
