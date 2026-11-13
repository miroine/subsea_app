import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from subsea.spec import *
from subsea.html import build_html
from subsea.presets import PRESETS, get_preset
from subsea.catalog import CATALOG

def test_roundtrip_all_presets():
    for name in PRESETS:
        s = get_preset(name)
        df = chain_to_df(s["chain"])
        back, problems = df_to_chain(df)
        assert not problems, (name, problems)
        assert back == s["chain"], name
        assert validate(s) == [], (name, validate(s))

def test_blank_canvas():
    s = get_preset("Blank canvas – draw your own")
    assert s["freeform"] and s["host"] is None and not s["chain"]
    assert validate(s) == []

def test_independent_hosts():
    s = get_preset("Blank canvas – draw your own")
    s["freeform"] = False
    s["chain"] = [
        {"type": "fpso", "id": "vessel", "slots": ["A", "B"], "x": 200, "y": 120},
        {"type": "jacket", "id": "platform", "slots": ["J1"]},
    ]
    assert validate(s) == []
    back, problems = df_to_chain(chain_to_df(s["chain"]))
    assert not problems, problems
    assert back == s["chain"]

def test_blank_canvas_symbol_library():
    html = build_html(get_preset("Blank canvas – draw your own"))
    assert 'id="palette"' in html
    assert "dragstart" in html and "function placeSymbol" in html
    assert 'id="b_palette"' in html
    assert 'id="b_fullscreen"' in html
    assert 'id="palette-close"' in html
    assert 'requestFullscreen()' in html

def test_preset_symbol_library():
    html = build_html(get_preset("Two-template tieback to platform"))
    assert 'id="palette"' in html
    assert "placeSymbol(button.dataset.type)" in html

def test_drawing_connection_and_edit_controls():
    html = build_html(get_preset("Blank canvas – draw your own"))
    for marker in ('id="b_connect"', 'id="b_copy"', 'id="b_delete"',
                   "function connectionPath", "st.spec.connections", "function removeSelected",
                   "function copySelected", "e.key === 'Delete'",
                   "connect-candidate", "Start the drag on a green-highlighted symbol.",
                   "Drag from a green-highlighted symbol to another.",
                   "svg.setPointerCapture(e.pointerId)",
                   "function finishConnection"):
        assert marker in html, marker

def test_edit_ops():
    ch = get_preset(next(iter(PRESETS)))["chain"]
    ch2 = insert_item(ch, "valve_gate", "plem", label="X")
    assert ch2[2]["type"] == "valve_gate" and ch2[2]["label"] == "X"
    ids = [c["id"] for c in ch2]; assert len(ids) == len(set(ids))
    ch3 = move_item(ch2, ch2[2]["id"], -1); assert ch3[1]["type"] == "valve_gate"
    assert len(remove_item(ch3, ch3[1]["id"])) == len(ch)

def test_bad_json_and_dupes():
    import pandas as pd
    df = pd.DataFrame([{"type": "spool", "id": "a", "props": "{bad"}, {"type": "spool", "id": "a"}, {"type": None}])
    chain, problems = df_to_chain(df)
    assert [c["id"] for c in chain] == ["a", "a_2"] and problems

def test_validate_flags_unknown():
    s = get_preset("Blank – jacket only"); s["chain"] = [{"type": "nope", "id": "z"}]; s["zones"] = [{"from": "q", "label": "L"}]
    assert len(validate(s)) == 2

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
