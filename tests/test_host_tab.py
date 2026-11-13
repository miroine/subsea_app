"""Host tab follows independent drawn hosts and their explicit riser connections."""
import copy
import logging
import os
from pathlib import Path
import tempfile

from streamlit.testing.v1 import AppTest


SPEC = {"freeform": True, "host": None,
        "chain": [{"id": "jacket_1", "type": "jacket", "slots": ["Production", "Umbilical"],
                   "showJTubes": True, "jTubeSide": "right", "x": 100, "y": 0},
                  {"id": "fpso_1", "type": "fpso", "slots": ["A", "B", "C"], "x": 400, "y": 0},
                  {"id": "base", "type": "riser_base", "x": 600, "y": 150}],
        "connections": [{"from": "base", "fromPort": "P-left", "to": "jacket_1", "toPort": "J-0",
                         "lane": "P", "kind": "riser", "style": "flex", "label": "Production",
                         "waypoints": [{"x": 300, "y": 250}], "width": 3}]}


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def select(app, label):
    return next(widget for widget in app.selectbox if widget.label == label)


def run():
    old_path = os.environ.get("SUBSEA_CASES_PATH")
    old_logging = logging.root.manager.disable
    with tempfile.TemporaryDirectory(prefix="subsea-host-tab-") as directory:
        os.environ["SUBSEA_CASES_PATH"] = str(Path(directory) / "cases.sqlite3")
        logging.disable(logging.WARNING)
        try:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.session_state.spec = copy.deepcopy(SPEC)
            app.session_state.ver += 1
            app.run()
            assert not app.exception
            assert select(app, "Design host").value == "jacket_1"
            assert select(app, "Host").value == "jacket"
            assert next(widget for widget in app.text_input if widget.label == "Slot / riser labels (comma separated)").value == "Production, Umbilical"
            assert app.session_state.spec["host"] is None
            select(app, "Design host").set_value("fpso_1").run()
            assert select(app, "Host").value == "fpso"
            assert next(widget for widget in app.text_input if widget.label == "Slot / riser labels (comma separated)").value == "A, B, C"
            select(app, "Design host").set_value("jacket_1").run()
            baseline = copy.deepcopy(app.session_state.spec)
            key = f"host_connections_main_jacket_1_{app.session_state.ver}"
            app.session_state[key] = {"edited_rows": {0: {"label": "Edited production", "style": "rigid", "Host port": "J-1"}},
                                      "added_rows": [], "deleted_rows": []}
            button(app, "Apply host connections").click().run()
            assert not app.exception and not app.error
            line = app.session_state.spec["connections"][0]
            assert line["label"] == "Edited production" and line["style"] == "rigid" and line["toPort"] == "J-1"
            assert line["waypoints"] == SPEC["connections"][0]["waypoints"]
            button(app, "Undo host connections").click().run()
            assert app.session_state.spec == baseline
            # A viewer update/selection chooses the host that is actually selected.
            app.session_state.selected_element = "fpso_1"
            app.session_state.spec["chain"][1]["slots"] = ["Changed"]
            app.session_state.ver += 1
            app.run()
            assert select(app, "Design host").value == "fpso_1"
            assert next(widget for widget in app.text_input if widget.label == "Slot / riser labels (comma separated)").value == "Changed"
            assert app.session_state.spec["host"] is None
            # A manual host selection must survive Apply/Discard revisions even
            # when a different host remains selected in the drawing.
            select(app, "Design host").set_value("jacket_1").run()
            key = f"host_connections_main_jacket_1_{app.session_state.ver}"
            app.session_state[key] = {"edited_rows": {0: {"label": "Discard me"}},
                                      "added_rows": [], "deleted_rows": []}
            button(app, "Discard host connection edits").click().run()
            assert select(app, "Design host").value == "jacket_1"
            assert app.session_state.spec["connections"][0]["label"] == "Production"
            key = f"host_connections_main_jacket_1_{app.session_state.ver}"
            app.session_state[key] = {"edited_rows": {0: {"label": "Must not apply", "Host port": "U-right"}},
                                      "added_rows": [], "deleted_rows": []}
            baseline = copy.deepcopy(app.session_state.spec)
            button(app, "Apply host connections").click().run()
            assert app.error and app.session_state.spec == baseline
            button(app, "Discard host connection edits").click().run()
            slots = next(widget for widget in app.text_input if widget.label == "Slot / riser labels (comma separated)")
            slots.set_value("").run()
            assert app.error and app.session_state.spec["chain"][0]["slots"] == ["Production", "Umbilical"]
            app.session_state.ver += 1
            app.run()
            # Hosts in another train and reversed connection directions are
            # resolved independently of the main train.
            branch = {"name": "Second host", "host": None,
                      "chain": [{"id": "branch_host", "type": "platform", "slots": ["Service"]}]}
            app.session_state.spec["branches"] = [branch]
            app.session_state.spec["connections"].append({
                "from": "branch_host", "fromPort": "J-0", "to": "base", "toPort": "S-right",
                "lane": "S", "label": "Service", "kind": "riser",
            })
            app.session_state.selected_element = None
            app.session_state.ver += 1
            app.run()
            select(app, "Editing train").set_value("b1").run()
            assert select(app, "Design host").value == "branch_host"
            assert select(app, "Host").value == "platform"
            key = f"host_connections_b1_branch_host_{app.session_state.ver}"
            app.session_state[key] = {"edited_rows": {0: {"label": "Branch service"}},
                                      "added_rows": [], "deleted_rows": []}
            button(app, "Apply host connections").click().run()
            assert not app.exception and not app.error
            assert app.session_state.spec["connections"][1]["label"] == "Branch service"
            assert app.session_state.spec["connections"][1]["fromPort"] == "J-0"
            assert app.session_state.spec["branches"][0]["host"] is None
            button(app, "Undo host connections").click().run()
            assert app.session_state.spec["connections"][1]["label"] == "Service"
            app.session_state.spec["branches"][0]["chain"] = []
            app.session_state.spec["connections"].pop()
            app.session_state.ver += 1
            app.run()
            assert not app.exception
            assert not any(widget.label == "Design host" for widget in app.selectbox)
            assert app.session_state.spec["branches"][0]["host"] is None
        finally:
            logging.disable(old_logging)
            if old_path is None:
                os.environ.pop("SUBSEA_CASES_PATH", None)
            else:
                os.environ["SUBSEA_CASES_PATH"] = old_path
    print("PASS: actual independent hosts, selection, slots and explicit risers synchronize; connection edits preserve bends and support undo")


if __name__ == "__main__":
    run()
