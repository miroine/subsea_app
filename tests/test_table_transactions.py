"""Batch train-table edits, explicit commits, discards and guarded undo."""
import copy
import logging
import os
from pathlib import Path
import tempfile

from streamlit.testing.v1 import AppTest

from subsea.presets import get_preset


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def edit(app, prefix, rows=None, added=None, deleted=None):
    key = f"{prefix}_{app.session_state.ver}"
    app.session_state[key] = {"edited_rows": rows or {}, "added_rows": added or [], "deleted_rows": deleted or []}


def run():
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    with tempfile.TemporaryDirectory(prefix="subsea-table-transactions-") as directory:
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state.spec = get_preset("Two-template tieback to platform")
            app.session_state.spec["host"]["id"] = "host_main"
            app.session_state.spec["host"]["risers"][0]["width"] = 4.5
            app.session_state.spec["host"]["risers"][0]["lx"] = 123
            app.session_state.ver += 1
            app.run()
            baseline = copy.deepcopy(app.session_state.spec)
            edit(app, "chain_main", {0: {"label": "Bulk label", "props": '{"tag":"CUSTOM-101"}'},
                                    1: {"label": "Second bulk label"}})
            # Even a server rerun must not commit an unapplied draft.
            app.run()
            assert app.session_state.spec == baseline
            edit(app, "chain_main", {0: {"label": "Bulk label", "props": '{"tag":"CUSTOM-101"}'},
                                    1: {"label": "Second bulk label"}})
            button(app, "Apply equipment chain").click().run()
            assert not app.exception and not app.error
            assert app.session_state.spec["chain"][0]["label"] == "Bulk label"
            assert app.session_state.spec["chain"][1]["label"] == "Second bulk label"
            assert app.session_state.spec["chain"][0]["tag"] == "CUSTOM-101"
            assert not button(app, "Undo equipment chain").disabled
            button(app, "Undo equipment chain").click().run()
            assert app.session_state.spec == baseline
            assert button(app, "Undo equipment chain").disabled
            edit(app, "chain_main", {0: {"label": "Discard me"}})
            button(app, "Discard chain edits").click().run()
            assert app.session_state.spec == baseline
            edit(app, "chain_main", {0: {"props": "{broken"}})
            button(app, "Apply equipment chain").click().run()
            assert app.error and not app.exception
            assert app.session_state.spec == baseline
            button(app, "Discard chain edits").click().run()
            # Risers are also staged, including preservation of non-table fields.
            baseline = copy.deepcopy(app.session_state.spec)
            edit(app, "risers_main", {0: {"label": "Riser batch", "style": "flex"},
                                     1: {"label": "Umbilical batch"}})
            app.run()
            assert app.session_state.spec == baseline
            edit(app, "risers_main", {0: {"label": "Riser batch", "style": "flex"},
                                     1: {"label": "Umbilical batch"}})
            button(app, "Apply risers").click().run()
            assert not app.exception and not app.error
            assert app.session_state.spec["host"]["risers"][0]["label"] == "Riser batch"
            assert app.session_state.spec["host"]["risers"][0]["width"] == 4.5
            assert app.session_state.spec["host"]["risers"][0]["lx"] == 123
            assert not button(app, "Undo risers").disabled
            button(app, "Undo risers").click().run()
            assert app.session_state.spec == baseline
            edit(app, "risers_main", {0: {"label": "Discard riser"}})
            button(app, "Discard riser edits").click().run()
            assert app.session_state.spec == baseline
            # A zero-row riser table remains editable with typed columns.
            app.session_state.spec["host"]["risers"] = []
            app.session_state.ver += 1
            app.run()
            edit(app, "risers_main", added=[{"lane": "P", "slot": 0, "style": "rigid", "label": "New riser"}])
            button(app, "Apply risers").click().run()
            assert not app.exception and not app.error
            assert app.session_state.spec["host"]["risers"][0]["label"] == "New riser"
            button(app, "Undo risers").click().run()
            assert app.session_state.spec["host"]["risers"] == []
            # Zone and inventory forms have the same guarded undo behaviour.
            baseline = copy.deepcopy(app.session_state.spec)
            edit(app, "zones", {0: {"label": "New zone label"}})
            button(app, "Apply zones").click().run()
            assert not app.exception and not app.error
            button(app, "Undo zones").click().run()
            assert app.session_state.spec == baseline
            # Locate the existing version-keyed inventory editor.
            inventory_key = f"all_equipment_table_{app.session_state.ver}"
            app.session_state[inventory_key] = {"edited_rows": {0: {"Label": "Inventory batch"}},
                                               "added_rows": [], "deleted_rows": []}
            button(app, "Apply all equipment settings").click().run()
            assert not app.exception and not app.error
            assert not button(app, "Undo equipment table").disabled
            button(app, "Undo equipment table").click().run()
            assert app.session_state.spec == baseline
            edit(app, "chain_main", {0: {"label": "Applied before new edit"}})
            button(app, "Apply equipment chain").click().run()
            app.session_state.spec["chain"][0]["x"] = 999
            app.run()
            assert button(app, "Undo equipment chain").disabled
            assert app.session_state.spec["chain"][0]["x"] == 999
        finally:
            logging.disable(old_logging)
            if old_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = old_path
    print("PASS: train table drafts, bulk apply/discard, invalid-input atomicity, riser/zone/inventory undo and newer-edit protection")


if __name__ == "__main__":
    run()
