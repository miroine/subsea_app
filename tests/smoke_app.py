"""Run app.py against a stubbed `streamlit` to catch NameErrors / type errors in every tab.
Streamlit itself is not installed in this sandbox, so this is a best-effort smoke test."""
import sys, types, pathlib, runpy
from unittest.mock import MagicMock
import pandas as pd
root = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(root))

class SS(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v

st = MagicMock(name="st"); st.session_state = SS()
def cols(spec, *a, **k):
    n = spec if isinstance(spec, int) else len(spec); return [st] * n
st.columns.side_effect = cols
st.tabs.side_effect = lambda labels: [st] * len(labels)
st.data_editor.side_effect = lambda df, **k: df
def _sel(label, options, index=0, **k):
    key = k.get("key"); opts = list(options)
    if key and st.session_state.get(key) in opts: return st.session_state[key]
    return opts[index if index is not None else 0]
st.selectbox.side_effect = _sel
st.text_input.side_effect = lambda label, value="", **k: value
st.text_area.side_effect = lambda label, value="", **k: value
st.checkbox.side_effect = lambda label, value=False, **k: value
st.select_slider.side_effect = lambda label, options, value=None, **k: value if value is not None else list(options)[0]
st.slider.side_effect = lambda label, lo, hi, value=None, **k: value if value is not None else lo
st.number_input.side_effect = lambda label, lo=0, hi=1, value=0, **k: value
st.color_picker.side_effect = lambda label, value, **k: value
st.multiselect.side_effect = lambda label, options, default=None, **k: default or []
st.button.return_value = False; st.form_submit_button.return_value = False
st.file_uploader.return_value = None
st.rerun.side_effect = RuntimeError("rerun")
html_calls = []
comp = MagicMock(); comp.html.side_effect = lambda h, **k: html_calls.append((len(h), k))
comp.declare_component.return_value.side_effect = lambda **k: html_calls.append((len(k["html"]), k))
sys.modules["streamlit"] = st
sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
sys.modules["streamlit.components.v1"] = comp
st.components = types.SimpleNamespace(v1=comp)
from subsea.presets import PRESETS, get_preset
n = 0
for name in PRESETS:
    for active in (["main", "b1", "b2"] if "network" in name.lower() or "hub" in name.lower() else ["main"]):
        st.session_state.clear(); st.session_state.update(spec=get_preset(name), loaded_preset=name, ver=0, active_train=active)
        html_calls.clear(); runpy.run_path(str(root / "app.py")); n += 1
        assert len(html_calls) >= 2, (name, active)
print(f"app ran cleanly for {n} preset/train combinations")
