"""Subsea field layout designer – Streamlit shell around a JavaScript/SVG engine.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json
import copy
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from subsea.bom import equipment_list, summary, totals
from subsea.installation import (STATUSES, TAG_FIELDS, apply_installation_rows, costing_excel,
                                 costing_notes, costing_pdf, installation_list, new_installation_summary)
from subsea.catalog import BY_ID, CATALOG, CATEGORIES, HOST_IDS, LINK_IDS, NODE_IDS
from subsea.checks import run_checks
from subsea.review_export import review_excel, review_pdf
from subsea.connections import CONNECTION_KINDS, CONNECTION_TYPES, RISER_STYLES
from subsea.network import EDIT_FIELDS, apply_connection_rows, connection_rows, implicit_rows
from subsea.valves import VALVE_TYPES, VALVE_COLUMNS, internal_valve_errors, valve_rows
from subsea.equipment import (DESIGN_FIELDS, TREE_TYPES, MAX_PORTS, customization_errors,
                              effective_design_limits, parse_design_limits, removed_port_errors,
                              riser_hub_counts, riser_port_ids, furb_configuration, connect_internal_hub)
from subsea.html import build_html
from subsea.viewer import editor
from subsea.cases import equipment_rows, apply_equipment_rows
from subsea.cases_ui import render_cases, render_comparison
from subsea.presets import PRESETS, get_preset
from subsea.riser_detail import blank_element_configuration
from subsea.spec import (CUSTOM_SHAPES, FLUIDS, add_branch, all_ids, chain_to_df, df_to_chain, get_train, insert_item,
                         move_item, remove_branch, remove_item, trains, type_label, validate)

st.set_page_config(page_title="Subsea Layout Designer", page_icon="🛢️", layout="wide")
st.markdown("""
<style>
html, body, .stApp {font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;}
.stApp {background:#F3F6FA; color:#051C2C;}
.block-container {padding-top: 2.8rem !important; padding-bottom:2rem; max-width: 1800px;}
header[data-testid="stHeader"] {background: transparent;}
.hero {background:#051C2C; color:#fff; margin:0 0 .4rem; padding:1rem 1.4rem; border-left:4px solid #2251FF; border-radius:6px; display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;}
.hero .kicker {font-size:.65rem; letter-spacing:.14em; text-transform:uppercase; color:#7FB2FF; margin-bottom:.25rem;}
.hero h1 {font-family:Arial,sans-serif; font-weight:600; font-size:1.45rem; line-height:1.2; margin:0; color:#fff; padding:0;}
.hero p {color:#B8C4D2; margin:0; font-size:.82rem;}
.workspace-status {display:flex; flex-wrap:wrap; gap:.5rem 1.4rem; padding:.4rem .1rem; color:#5B6B7B; font-size:.78rem;}
.workspace-status strong {color:#051C2C;}
h2, h3 {font-family:Arial,sans-serif; font-weight:600; color:#051C2C;}
h2 {font-size:1.2rem;} h3 {font-size:1.05rem;}
[data-testid="stSidebar"] {background:#F3F6FA; border-right:1px solid #D5DCE4;}
[data-testid="stSidebar"] h1 {font-size:1.1rem; font-family:Arial,sans-serif; font-weight:700;}
.stTabs [data-baseweb="tab-list"] {gap:.3rem; border-bottom:1px solid #D5DCE4; overflow-x:auto;}
.stTabs [data-baseweb="tab"] {padding:.55rem .85rem; font-size:.85rem; color:#5B6B7B; border-radius:5px 5px 0 0; white-space:nowrap;}
.stTabs [aria-selected="true"] {color:#051C2C; background:#E7EDFA; font-weight:600;}
[data-baseweb="tab-panel"] {padding-top:1rem;}
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {border-radius:5px; border:1px solid #B8C4D2; background:#fff; color:#051C2C; font-size:.82rem; min-height:2.35rem;}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {background:#E7EDFA; color:#051C2C; border-color:#2251FF;}
button[kind^="primary"] {background:#2251FF; color:#fff; border-color:#2251FF;}
button:focus-visible, summary:focus-visible {outline:3px solid #2251FF; outline-offset:2px;}
[data-testid="stForm"], [data-testid="stExpander"] {background:#fff; border:1px solid #D5DCE4; border-radius:6px;}
[data-baseweb="input"], [data-baseweb="select"] > div, textarea {border-radius:5px !important;}
.stCaption, [data-testid="stCaptionContainer"] {color:#5B6B7B;}
iframe {border:1px solid #D5DCE4; border-radius:6px; background:#fff;}
@media(max-width:768px) {.block-container {padding-left:1rem; padding-right:1rem;} .hero {padding:.8rem 1rem;} .hero h1 {font-size:1.2rem;} .hero p {display:none;} .stTabs [data-baseweb="tab"] {padding:.5rem .65rem;}}
</style>
<div class="hero">
  <div><div class="kicker">Engineering workspace</div><h1>Subsea Layout Designer</h1></div>
  <p>Draw &amp; connect &nbsp; / &nbsp; Configure &nbsp; / &nbsp; Review &nbsp; / &nbsp; Save &amp; export</p>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------- state
if "spec" not in st.session_state:
    first = "Blank canvas – draw your own"
    st.session_state.spec = get_preset(first)
    st.session_state.loaded_preset = first
    st.session_state.ver = 0
spec: dict = st.session_state.spec


def bump():
    st.session_state.ver += 1


def selected_settings_changed(scope: str, values: dict) -> bool:
    previous = st.session_state.get("selected_settings_snapshot")
    if not previous or previous["scope"] != scope:
        st.session_state.selected_settings_snapshot = {"scope": scope, "values": copy.deepcopy(values)}
        return False
    return previous["values"] != values


def apply_table_update(candidate: dict, scope: str):
    current = st.session_state.spec
    previous_errors = validate(current)
    new_errors = [error for error in validate(candidate) if error not in previous_errors]
    if new_errors:
        st.error("Cannot apply table: " + " ".join(new_errors))
        return
    if candidate == current:
        bump()
        st.rerun()
    st.session_state.table_undo = {
        "scope": scope, "before": copy.deepcopy(current), "after": copy.deepcopy(candidate),
    }
    st.session_state.spec = candidate
    for key in list(st.session_state):
        if key.startswith(("hs_", "ha_", "ht_", "hl_", "fluid_", "lS_", "lU_")):
            del st.session_state[key]
    bump()
    st.rerun()


def table_undo_button(scope: str, label: str):
    undo = st.session_state.get("table_undo")
    available = bool(undo and undo["scope"] == scope and undo["after"] == st.session_state.spec)
    if st.button(label, key=f"undo_table_{scope}", disabled=not available,
                 help="Undo the last applied table change. Unavailable after another design edit, to avoid overwriting newer work."):
        previous = copy.deepcopy(undo["before"])
        st.session_state.pop("table_undo", None)
        st.session_state.spec = previous
        for key in list(st.session_state):
            if key.startswith(("hs_", "ha_", "ht_", "hl_", "fluid_", "lS_", "lU_")):
                del st.session_state[key]
        bump()
        st.rerun()


def design_limit_inputs(limits: dict, scope: str, key_prefix: str = "") -> dict:
    columns = st.columns(4)
    return {
        key: columns[index].text_input(
            f"{scope} {field['label']}", str(limits[key]) if key in limits else "",
            help="Leave blank to inherit the layout value (or remain unspecified).",
            key=f"{key_prefix}_limit_{key}" if key_prefix else None,
        )
        for index, (key, field) in enumerate(DESIGN_FIELDS.items())
    }


def label_style_inputs(item: dict, key_prefix: str = "") -> dict:
    style = item.get("labelStyle", {})
    with st.expander("Label font and placement"):
        st.caption("Offsets and rotation adjust the existing label position, not the equipment or connection. Size 0 keeps the symbol default; positive offsets move right/down in the symbol's coordinates.")
        a, b, c = st.columns(3)
        fonts = {"auto": "Theme default", "sans": "Arial / sans serif",
                 "serif": "Georgia / serif", "mono": "Courier New / monospace"}
        font = a.selectbox("Label font", list(fonts), index=list(fonts).index(style.get("font", "auto")), format_func=fonts.get, key=f"{key_prefix}_font" if key_prefix else None)
        size = b.number_input("Label font size (0 = automatic)", 0.0, 72.0, float(style.get("size", 0)), key=f"{key_prefix}_font_size" if key_prefix else None)
        weights = {"auto": "Symbol default", "normal": "Normal", "bold": "Bold"}
        weight = c.selectbox("Label weight", list(weights), index=list(weights).index(style.get("weight", "auto")), format_func=weights.get, key=f"{key_prefix}_weight" if key_prefix else None)
        a, b, c = st.columns(3)
        dx = a.number_input("Label horizontal offset", value=float(style.get("dx", 0)), key=f"{key_prefix}_label_dx" if key_prefix else None)
        dy = b.number_input("Label vertical offset", value=float(style.get("dy", 0)), key=f"{key_prefix}_label_dy" if key_prefix else None)
        rotation = c.number_input("Label rotation (degrees)", -180.0, 180.0, float(style.get("rotation", 0)), key=f"{key_prefix}_rotation" if key_prefix else None)
        anchors = {"auto": "Symbol default", "start": "Left aligned", "middle": "Centered", "end": "Right aligned"}
        anchor = st.selectbox("Label alignment", list(anchors), index=list(anchors).index(style.get("anchor", "auto")), format_func=anchors.get, key=f"{key_prefix}_anchor" if key_prefix else None)
        italic = st.checkbox("Italic label", bool(style.get("italic", False)), key=f"{key_prefix}_italic" if key_prefix else None)
        reset = st.checkbox("Reset label font and placement to defaults", key=f"{key_prefix}_reset_style" if key_prefix else None)
    return {} if reset else dict(font=font, size=size, weight=weight, dx=dx, dy=dy,
                                 rotation=rotation, anchor=anchor, italic=italic)


def installation_inputs(item: dict, key_prefix: str = "") -> dict:
    st.markdown("**Installation tags**")
    columns = st.columns(4)
    status = item.get("installationStatus", "Unspecified")
    return {
        "installationStatus": columns[0].selectbox("Installation status", STATUSES,
                                                   index=STATUSES.index(status) if status in STATUSES else 0,
                                                   key=f"{key_prefix}_status" if key_prefix else None),
        "provider": columns[1].text_input("Provider", item.get("provider", ""), key=f"{key_prefix}_provider" if key_prefix else None),
        "installationType": columns[2].text_input("Installation type", item.get("installationType", ""), key=f"{key_prefix}_installation_type" if key_prefix else None),
        "rating": columns[3].text_input("Rating", item.get("rating", ""), placeholder="10 K psi", key=f"{key_prefix}_rating" if key_prefix else None),
    }


def load_spec(new: dict):
    if not isinstance(new, dict) or not isinstance(new.get("chain", []), list):
        raise ValueError("A design must be a JSON object with an equipment chain list.")
    st.session_state.pop("table_undo", None)
    st.session_state.spec = new
    st.session_state.document_id = st.session_state.get("document_id", 0) + 1
    st.session_state.viewer_ack = 0
    st.session_state.selected_element = None
    st.session_state.selected_elements = []
    st.session_state.selected_ports = []
    st.session_state.internal_valve_options = {}
    st.session_state.selected_connection = None
    st.session_state.pop("active_train", None)
    st.session_state.pop("comparison", None)
    for key in ("viewer_grid", "viewer_animate", "viewer_speed", "viewer_theme"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith(("hs_", "ha_", "ht_", "hl_", "fluid_", "lS_", "lU_", "flow_", "mir_", "gap_",
                           "nm_", "fi_", "fs_", "fx_", "fy_", "fv_", "fl_", "hx_", "hy_", "rj_", "ri_", "rs_", "rx_", "rl_", "design_host_")) or key == "freeform_host":
            del st.session_state[key]
    bump()
    st.rerun()


def change_host_presence(train_id: str, widget_key: str, document_id: int, revision: int):
    # Ignore checkbox callbacks queued before a newer drawing/preset arrived.
    if document_id != st.session_state.get("document_id", 0) or revision != st.session_state.ver:
        return
    train = get_train(st.session_state.spec, train_id)
    if st.session_state[widget_key] and not train.get("host"):
        train["host"] = {"type": "jacket", "slots": ["J1", "J2"], "risers": [], "installationStatus": "New"}
    elif not st.session_state[widget_key]:
        host_id = (train.get("host") or {}).get("id")
        train["host"] = None
        if host_id:
            st.session_state.spec["connections"] = [
                connection for connection in st.session_state.spec.get("connections", [])
                if host_id not in (connection.get("from"), connection.get("to"))
            ]
    bump()

def receive_drawing():
    event = st.session_state.get("drawing_editor")
    if not isinstance(event, dict) or event.get("documentId") != st.session_state.get("document_id", 0):
        return
    if event.get("sequence", 0) <= st.session_state.get("viewer_ack", 0):
        return
    st.session_state.viewer_ack = event["sequence"]
    incoming = event.get("spec")
    if not isinstance(incoming, dict):
        st.session_state.viewer_error = "The drawing returned an invalid design."
        return
    st.session_state.spec = incoming
    st.session_state.selected_element = event.get("selected")
    st.session_state.selected_elements = event.get("selectedIds", [])
    st.session_state.selected_ports = event.get("selectedPorts", [])
    st.session_state.internal_valve_options = event.get("internalValveOptions", {})
    st.session_state.selected_connection = next(
        (index for index in range(len(incoming.get("connections", []))) if index == event.get("selectedConnection")),
        None,
    )
    st.session_state.viewer_grid = bool(incoming.get("showGrid", False))
    st.session_state.viewer_animate = bool(incoming.get("animate", False))
    st.session_state.viewer_speed = incoming.get("animSpeed", 1)
    st.session_state.viewer_theme = incoming.get("themeName", "consulting")
    bump()
    for tid, train in trains(incoming):
        if (train.get("host") or {}).get("id") == event.get("selected") or any(
            item.get("id") == event.get("selected") for item in train.get("chain", [])
        ):
            st.session_state.active_train = tid
    for key in list(st.session_state):
        if key.startswith(("hs_", "ha_", "ht_", "hl_", "fluid_", "lS_", "lU_")) or key == "freeform_host":
            del st.session_state[key]


# ------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("Design setup")
    st.caption("Start or load a drawing here. Save versions and export files in Save & export below the canvas.")
    if st.button("New blank design", use_container_width=True,
                 help="Replaces the working drawing. Save a case version or download JSON first."):
        st.session_state.pop("case_id", None)
        st.session_state.pop("case_version", None)
        st.session_state.loaded_preset = "Blank canvas – draw your own"
        load_spec(get_preset(st.session_state.loaded_preset))
    with st.expander("Templates & import", expanded=True):
        with st.form("load_template"):
            preset = st.selectbox("Preset", list(PRESETS), index=list(PRESETS).index(st.session_state.loaded_preset))
            st.caption("Loading a template replaces the drawing. Selecting a name alone does not change it.")
            if st.form_submit_button("Load template", use_container_width=True, type="primary"):
                st.session_state.pop("case_id", None)
                st.session_state.pop("case_version", None)
                st.session_state.loaded_preset = preset
                load_spec(get_preset(preset))
        uploaded = st.file_uploader("Load spec (.json)", type="json", key=f"up_{st.session_state.ver}",
                                   help="Replaces the working drawing. Save your current work first.")
        if uploaded is not None:
            try:
                imported = json.loads(uploaded.getvalue().decode("utf-8"))
                if not isinstance(imported, dict) or not isinstance(imported.get("chain", []), list):
                    raise ValueError("A design must be a JSON object with an equipment chain list.")
                st.session_state.pop("case_id", None)
                st.session_state.pop("case_version", None)
                load_spec(imported)
            except (ValueError, UnicodeDecodeError) as e:
                st.error(f"Not a valid spec file: {e}")

    with st.expander("Drawing appearance"):
        themes = {"consulting": "Consulting – deep navy (slide)", "mono": "Engineering – monochrome (sheet)",
                  "blueprint": "Blueprint (sheet)", "classic": "Classic colour (sheet)"}
        spec["themeName"] = st.selectbox("Theme", list(themes), index=list(themes).index(spec.get("themeName", "consulting")) if spec.get("themeName", "consulting") in themes else 0,
                                         format_func=lambda k: themes[k], key="viewer_theme")
        spec["showLegend"] = st.checkbox("Legend", spec.get("showLegend", True))
        spec["showTitleBlock"] = st.checkbox("Title block (sheet themes)", spec.get("showTitleBlock", True))
        spec["autoTag"] = st.checkbox("Auto tag numbers (HV-101…)", spec.get("autoTag", True))
        spec["lineNumbers"] = st.checkbox("Line numbers", spec.get("lineNumbers", True))
        spec["showSeabed"] = st.checkbox("Seabed line", spec.get("showSeabed", False))
        spec["connectionWidth"] = st.number_input("Default connection thickness", min_value=0.5, max_value=20.0,
                                                 value=float(spec.get("connectionWidth", 2.5)), step=0.5,
                                                 help="Drawing units; individual connections can override this.")
    with st.expander("Drawing title & notes"):
        spec["title"] = st.text_area("Title (action title)", spec.get("title", ""), height=70)
        spec["subtitle"] = st.text_input("Subtitle", spec.get("subtitle", ""))
        spec["source"] = st.text_input("Source", spec.get("source", ""))
        notes_txt = st.text_area("Notes (one per line)", "\n".join(spec.get("notes", [])), height=90)
        spec["notes"] = [n.strip() for n in notes_txt.splitlines() if n.strip()]
    with st.expander("View & flow animation"):
        st.caption("These controls mirror Grid and Flow in the drawing toolbar.")
        spec["showGrid"] = st.checkbox("Grid", spec.get("showGrid", False), key="viewer_grid")
        height = st.slider("Viewer height (px)", 400, 1100, 720, step=20)
        spec["animate"] = st.checkbox("Animate flow", spec.get("animate", False), key="viewer_animate")
        spec["animSpeed"] = st.select_slider("Speed", [step / 4 for step in range(1, 13)],
                                           value=spec.get("animSpeed", 1), key="viewer_speed")
        spec["flowArrows"] = st.checkbox("Direction arrows", spec.get("flowArrows", True))
        spec["flow"] = st.selectbox("Direction (all trains)", ["auto", "forward", "reverse", "none"],
                                    index=["auto", "forward", "reverse", "none"].index(spec.get("flow", "auto")),
                                    help="auto: production flows towards the host, other fluids away from it")
    with st.expander("Sea level"):
        sea = spec.setdefault("seaLevel", {})
        sea["visible"] = st.checkbox("Show sea level", bool(sea.get("visible", False)))
        hosts = {
            element["id"]: element.get("label") or f"{type_label(element['type'])} ({element['id']})"
            for _, train in trains(spec)
            for element in ([train["host"]] if train.get("host") else []) + train.get("chain", [])
            if element.get("type") in HOST_IDS and element.get("id")
        }
        if hosts:
            choices = list(hosts)
            sea["host"] = st.selectbox("Sea-level host", choices,
                                       index=choices.index(sea.get("host")) if sea.get("host") in choices else 0,
                                       format_func=lambda value: hosts[value])
            sea["offset"] = st.number_input("Sea-level offset", value=float(sea.get("offset", 0)), step=5.0,
                                            help="Drawing units below the top of the selected host; negative moves upwards. Follows host movement/resizing.")
        elif sea["visible"]:
            st.info("Place a host from the symbol library to anchor sea level.")
    with st.expander("Override line colours"):
        ov = st.checkbox("Use custom colours", bool(spec.get("theme")))
        if ov:
            theme = spec.setdefault("theme", {})
            t1, t2, t3 = st.columns(3)
            theme["red"] = t1.color_picker("Production", theme.get("red", "#2251FF"))
            theme["green"] = t2.color_picker("Service", theme.get("green", "#00A9F4"))
            theme["yellow"] = t3.color_picker("Umbilical", theme.get("yellow", "#00B3A4"))
        else:
            spec.pop("theme", None)
    tb = spec.setdefault("titleBlock", {})
    with st.expander("Title block (sheet themes)"):
        tb["project"] = st.text_input("Project", tb.get("project", ""))
        tb["drawing"] = st.text_input("Drawing", tb.get("drawing", "Subsea layout – general arrangement"))
        tb["docNo"] = st.text_input("Document no.", tb.get("docNo", ""))
        tb["rev"] = st.text_input("Revision", tb.get("rev", "A"))
        tb["by"] = st.text_input("Drawn by", tb.get("by", ""))
        tb["checked"] = st.text_input("Checked by", tb.get("checked", ""))

# --------------------------------------------------------- diagram placeholder
# filled at the end of the script so it always reflects this run's edits
diagram = st.container()
train_names = {tid: ("Main train" if tid == "main" else f"{tid} · {tr.get('name', 'Branch')}") for tid, tr in trains(spec)}
if st.session_state.get("active_train") not in train_names:
    st.session_state.active_train = "main"
edit_workspace, review_workspace, save_workspace, reference_workspace = st.tabs(
    ["Edit design", "Review design", "Save & export", "Symbol reference"])
with edit_workspace:
    st.caption("Select an item in the drawing, then open Selected item. Selected-item settings update automatically when you leave a field. Bulk tables still use their own Apply button.")
    active = st.selectbox("Editing train", list(train_names), format_func=lambda k: train_names[k], key="active_train")
    selected_panel, tab_chain, tab_host, tab_net, tab_zones, inventory_panel, tab_add, tab_design = st.tabs(
        ["Selected item", "Equipment chain", "Host & risers", "Network", "Zones", "All equipment", "Add equipment", "Design specification"])
with review_workspace:
    st.caption("Review advisory checks and quantities, or compare the working drawing with a saved version.")
    tab_chk, tab_bom, tab_compare = st.tabs(["Design checks", "Equipment list", "Compare designs"])
with save_workspace:
    st.caption("Save a local case version or download a portable design. The drawing toolbar also offers SVG, PNG and Print; in 3D view, use 3D HTML for an offline viewer with orbit, pan and zoom.")
    tab_cases, tab_json = st.tabs(["Saved cases", "Spec JSON"])
tab_cat = reference_workspace
tr = get_train(spec, active)
chain = tr.setdefault("chain", [])
taken = all_ids(spec, exclude_train=active)
every_id = all_ids(spec)

with selected_panel:
    for key, value in st.session_state.pop("selected_widget_updates", {}).items():
        st.session_state[key] = value
    for key in st.session_state.pop("selected_widget_resets", []):
        st.session_state.pop(key, None)
    st.subheader("Selected item settings")
    st.caption("Automatic updates: finish editing a field or table cell to update the drawing. Invalid changes are not saved. Save a case version for a durable copy.")
    selected = st.session_state.get("selected_element")
    selected_item = None
    for _, train in trains(spec):
        for item in ([train["host"]] if train.get("host") else []) + train.get("chain", []):
            if selected and item.get("id") == selected:
                selected_item = item
                break
    connection_index = st.session_state.get("selected_connection")
    connections = spec.get("connections", [])
    settings_model = {
        "document": st.session_state.get("document_id", 0), "selected": selected,
        "item": selected_item, "override": spec.get("overrides", {}).get(selected, {}),
        "connection_index": connection_index,
        "connection": connections[connection_index]
        if isinstance(connection_index, int) and 0 <= connection_index < len(connections) else None,
    }
    if st.session_state.get("selected_settings_model") != settings_model:
        st.session_state.selected_edit_revision = st.session_state.get("selected_edit_revision", 0) + 1
        st.session_state.selected_settings_model = copy.deepcopy(settings_model)
    if isinstance(connection_index, int) and 0 <= connection_index < len(connections):
        connection = connections[connection_index]
        st.caption(f"Connection: {connection.get('from')} → {connection.get('to')}")
        edit_key = f"connection_{st.session_state.get('document_id', 0)}_{connection_index}_{st.session_state.get('selected_edit_revision', 0)}"
        with st.container():
            installation = installation_inputs(connection, edit_key)
            choices = [""] + list(CONNECTION_TYPES)
            kind_choices = list(CONNECTION_KINDS)
            connection_kind = st.selectbox("Physical connection", kind_choices,
                                            index=kind_choices.index(connection.get("kind", ""))
                                            if connection.get("kind", "") in kind_choices else 0,
                                            format_func=lambda value: CONNECTION_KINDS[value], key=f"{edit_key}_kind")
            current_type = connection.get("connectionType", "")
            connection_type = st.selectbox("Connection type", choices,
                                           index=choices.index(current_type) if current_type in choices else 0,
                                           format_func=lambda value: CONNECTION_TYPES[value]["label"] if value else "Automatic (ports / train fluid)", key=f"{edit_key}_type")
            connection_label = st.text_input("Connection label", connection.get("label", ""), key=f"{edit_key}_label")
            connection_label_style = label_style_inputs(connection, edit_key)
            inherit_width = st.checkbox("Use default connection thickness", "width" not in connection, key=f"{edit_key}_inherit_width")
            default_width = 2.5 if connection.get("kind") == "riser" else spec.get("connectionWidth", 2.5)
            connection_width = st.number_input("Connection thickness", min_value=0.5, max_value=20.0,
                                                value=float(connection.get("width", default_width)), step=0.5, key=f"{edit_key}_width")
            flow_choices = ["auto", "forward", "reverse", "none"]
            connection_flow = st.selectbox("Connection flow direction", flow_choices,
                                             index=flow_choices.index(connection.get("flow", "auto")), key=f"{edit_key}_flow")
            st.caption("Service type changes the line style, not the equipment ports it attaches to.")
            riser_styles = list(RISER_STYLES)
            riser_style = st.selectbox("Riser shape", riser_styles,
                                      index=riser_styles.index(connection.get("style", "rigid"))
                                      if connection.get("style", "rigid") in riser_styles else 0,
                                      format_func=lambda value: RISER_STYLES[value], key=f"{edit_key}_riser_style")
            st.caption("Choose Riser above to apply the shape. Existing manual bends are kept and rounded. Use Auto route in the drawing only when you want to clear manual bends.")
            psv = st.checkbox("Add PSV to riser", bool(connection.get("psv", False)), key=f"{edit_key}_psv")
            psv_tag = st.text_input("PSV tag", connection.get("psvTag", ""), key=f"{edit_key}_psv_tag")
            topside_psv = any(
                element.get("type") in HOST_IDS and element.get("type") not in ("onshore", "tieback")
                and element.get("id") in (connection.get("from"), connection.get("to"))
                for _, train in trains(spec)
                for element in ([train["host"]] if train.get("host") else []) + train.get("chain", [])
            )
            if topside_psv:
                st.caption("PSV is fixed at the topside riser termination, at deck level when J-tubes are shown.")
            psv_position = st.number_input("PSV position (%)", 0.0, 100.0,
                                           float(connection.get("psvPosition", 50)),
                                           disabled=topside_psv,
                                           help="Only used for risers without a topside host. Host-connected PSVs stay at the topside termination.",
                                           key=f"{edit_key}_psv_position")
            edit_values = dict(
                installation=installation, kind=connection_kind, service=connection_type,
                label=connection_label, label_style=connection_label_style, inherit_width=inherit_width,
                width=connection_width, flow=connection_flow, style=riser_style,
                psv=psv, psv_tag=psv_tag, psv_position=psv_position,
            )
            if selected_settings_changed(edit_key, edit_values):
                if psv and connection_kind != "riser":
                    connection_kind = "riser"
                    edit_values["kind"] = connection_kind
                    st.session_state.selected_widget_updates = {f"{edit_key}_kind": connection_kind}
                connection.update(psv=psv, psvTag=psv_tag, psvPosition=psv_position)
                connection.update(installation)
                if connection_kind:
                    connection["kind"] = connection_kind
                else:
                    connection.pop("kind", None)
                if connection_type:
                    connection["connectionType"] = connection_type
                else:
                    connection.pop("connectionType", None)
                connection["label"] = connection_label
                connection["labelStyle"] = connection_label_style
                if inherit_width:
                    connection.pop("width", None)
                else:
                    connection["width"] = connection_width
                connection["flow"] = connection_flow
                if connection.get("kind") == "riser":
                    connection["style"] = riser_style
                st.session_state.selected_settings_snapshot = {"scope": edit_key, "values": copy.deepcopy(edit_values)}
                st.session_state.selected_settings_model = copy.deepcopy(settings_model)
                if not connection_label_style:
                    st.session_state.selected_widget_resets = [
                        key for key in st.session_state if key.startswith(edit_key + "_")
                    ]
                    st.session_state.pop("selected_settings_snapshot", None)
                bump()
                st.rerun()
    elif len(st.session_state.get("selected_elements", [])) > 1:
        st.caption("Multiple elements selected. Drag a selected element in the drawing to move the block; Shift-click adds/removes elements.")
    elif selected_item is None:
        st.info("Select equipment or a connection in the drawing to edit its settings here. To start drawing, open Symbols, place equipment, then use Connect to attach ports.")
        st.caption("Working changes stay in this session. Use Save & export to save a case version or download a durable backup.")
    else:
        item = selected_item
        st.caption(f"{type_label(item['type'])} — {selected}")
        edit_key = f"element_{st.session_state.get('document_id', 0)}_{selected}_{st.session_state.get('selected_edit_revision', 0)}"
        override = spec.get("overrides", {}).get(selected, {})
        customize_valves = False
        if item["type"] not in HOST_IDS and item["type"] not in LINK_IDS:
            customize_valves = st.checkbox(
                "Customize internal valves (replace defaults)", "internalValves" in item,
                key=f"{edit_key}_custom_valves")
            st.caption("Enable to show the valve table immediately. You can also use Add internal valve at the top of the drawing's selected-equipment panel.")
        with st.container():
            specific = {}
            valve_options = {}
            pipe_ids = []
            if item["type"] not in HOST_IDS and item["type"] not in LINK_IDS:
                with st.expander("Internal valves", expanded=True):
                    st.caption("Choose an internal pipe and a position: 0% = start, 50% = middle, 100% = end. P = process, S = service, U = umbilical. Completed, valid table edits update automatically. An empty customized table removes all built-in valves; untick customization to restore defaults. Valve state is illustrative; it does not simulate flow.")
                    valve_options = st.session_state.get("internal_valve_options", {})
                    pipe_ids = [pipe["id"] for pipe in valve_options.get("pipes", [])]
                    if customize_valves:
                        if not pipe_ids:
                            st.caption("Select this element in the drawing to discover its current internal pipe IDs. Existing valve pipe IDs are retained.")
                        initial_valves = valve_rows(item.get("internalValves", valve_options.get("defaults", [])))
                        valve_df = pd.DataFrame(initial_valves, columns=VALVE_COLUMNS)
                        for column in ("id", "pipe", "kind", "tag", "label", "provider", "rating"):
                            valve_df[column] = valve_df[column].fillna("").astype("string")
                        valve_df["closed"] = valve_df["closed"].fillna(False).astype(bool)
                        valve_df["position"] = pd.to_numeric(valve_df["position"], errors="coerce")
                        edited_valves = st.data_editor(
                            valve_df, key=f"internal_valves_{selected}_{st.session_state.ver}",
                            hide_index=True, num_rows="dynamic", use_container_width=True,
                            column_config={
                                "id": st.column_config.TextColumn("Valve ID", required=True),
                                "pipe": (st.column_config.SelectboxColumn("Internal pipe", options=pipe_ids, required=True)
                                         if pipe_ids else st.column_config.TextColumn("Internal pipe ID", required=True)),
                                "kind": st.column_config.SelectboxColumn("Valve type", options=list(VALVE_TYPES), required=True),
                                "position": st.column_config.NumberColumn("Position (%)", min_value=0, max_value=100, required=True),
                                "closed": st.column_config.CheckboxColumn("Closed"),
                                "rating": st.column_config.TextColumn("Pressure rating (with units)"),
                            })
                        specific["internalValves"] = [
                            {key: (False if key == "closed" else None if key == "position" else "")
                             if pd.isna(value) else value for key, value in row.items()}
                            for row in edited_valves.to_dict("records")
                        ]
                    else:
                        specific["internalValves"] = None
            installation = installation_inputs(item, edit_key)
            p1, p2, p3, p4 = st.columns(4)
            label = p1.text_input("Element label", override.get("label", item.get("label", "")), key=f"{edit_key}_label")
            scale = p2.number_input("Element size (%)", min_value=1.0, value=float(override.get("scale", 1) * 100), key=f"{edit_key}_scale")
            dx = p3.number_input("Horizontal offset", value=float(override.get("dx", 0)), key=f"{edit_key}_dx")
            dy = p4.number_input("Vertical offset", value=float(override.get("dy", 0)), key=f"{edit_key}_dy")
            label_style = label_style_inputs(item, edit_key)
            independent_riser = False
            load_furb = False
            connect_hub = False
            internal_hub_options = ([], {})
            if item["type"] in ("riser_base", "riser_skid", "custom_element"):
                st.info("Use **Element designer** (or **Riser details** for a riser) in the drawing toolbar. Draw shapes, text, pipes/crossovers and valves; move hubs to any edge. Custom elements start blank. Edits save automatically; download/load layout JSON to reuse templates.")
            if item["type"] in ("riser_base", "riser_skid") and not item.get("riserDetail"):
                load_furb = st.button("Load FURB starting layout", key=f"{edit_key}_load_furb")
                st.caption("Loads FURB immediately: gas and umbilical through-lines with a chemical take-off. Existing hub counts and external lines are retained; missing FURB ports are added.")
                independent_riser = st.checkbox("Independent process / service / umbilical hubs", "riserPorts" in item, key=f"{edit_key}_independent")
                st.caption("Enabling independent hubs or custom piping reveals its editor immediately.")
                if independent_riser:
                    counts = riser_hub_counts(item)
                    if any(value > MAX_PORTS for count in counts.values() for value in count.values()):
                        st.warning(f"Legacy additional hubs exceed the {MAX_PORTS}-port independent limit. Reduce the counts before applying; connected-port removal remains blocked.")
                    specific["riserPorts"] = {}
                    for lane, name in (("P", "Process"), ("S", "Chemical / service"), ("U", "Umbilical")):
                        columns = st.columns(2)
                        specific["riserPorts"][lane] = {
                            side: columns[index].number_input(f"{name} {side}", 0, max(MAX_PORTS, counts[lane][side]), counts[lane][side], key=f"{edit_key}_{lane}_{side}")
                            for index, side in enumerate(("inlets", "outlets"))
                        }
                    specific["portConfig"] = None
                else:
                    specific["riserPorts"] = None
                specific["servicePorts"] = st.checkbox("Include chemical / service connections", item.get("servicePorts", False), key=f"{edit_key}_service_ports")
                specific["umbilicalPorts"] = st.checkbox("Include umbilical connections", item.get("umbilicalPorts", False), key=f"{edit_key}_umbilical_ports")
                specific["bundleServiceInlet"] = st.checkbox(
                    "Bundle S inlet into U inlet (one umbilical riser)", item.get("bundleServiceInlet", False), key=f"{edit_key}_bundle")
                st.caption("Bundling hides S-left and brings its chemical service to an internal junction on U-left. Connect U-left to one host J-tube using an umbilical riser. S-right remains separate; disconnect any S-left line before bundling. This represents services carried together, not fluid mixing.")
                st.caption("Independent counts override the legacy pair toggles and single-lane hub controls. Each service can have its own inlet/outlet count. Connected ports cannot be removed.")
            if item["type"] == "plet":
                plet_modes = {"PSU": "Process + service + umbilical (3 pairs)",
                              "P": "Process only (1 inlet + 1 outlet)",
                              "S": "Service / chemical only (1 inlet + 1 outlet)",
                              "U": "Umbilical only (1 inlet + 1 outlet)"}
                specific["pletPorts"] = st.selectbox(
                    "PLET standard ports", list(plet_modes),
                    index=list(plet_modes).index(item.get("pletPorts", "PSU")),
                    format_func=plet_modes.get,
                    key=f"{edit_key}_plet_ports",
                )
                st.caption("For exactly one inlet and one outlet, choose a single-service option and disable Customize inlet/outlet hubs. Custom hubs add to the selected standard ports.")
                st.caption("Assign Chemical / MEG or Service to each PLET port to connect it to orange S ports; umbilical services connect to U. Assigned service sets PLET compatibility automatically. Disconnect an existing incompatible line before changing its service.")
            if item["type"] in LINK_IDS:
                specific["lineWidth"] = st.number_input("Flowline thickness", min_value=0.5, max_value=20.0,
                                                        value=float(item.get("lineWidth", spec.get("connectionWidth", 2.2))), step=0.5, key=f"{edit_key}_line_width")
            if item["type"] in HOST_IDS:
                if item["type"] in ("jacket", "platform", "jackup"):
                    specific["showJTubes"] = st.checkbox("Draw J-tubes with pulled-in risers", item.get("showJTubes", False), key=f"{edit_key}_show_jtubes")
                    specific["jTubeSide"] = st.selectbox("J-tube seabed exit", ["left", "right"],
                                                        index=1 if item.get("jTubeSide") == "right" else 0, key=f"{edit_key}_jtube_side")
                    st.caption("Draws curved guide tubes with attached risers running inside to deck level. Schematic only; not a clearance or bend-radius check.")
                count = st.number_input("Available J-tubes", min_value=0, max_value=MAX_PORTS,
                                        value=len(item.get("slots", ["J1", "J2"])), step=1,
                                        help="Names below are kept in order; increasing the count generates new J labels.", key=f"{edit_key}_jtube_count")
                tubes = st.text_input("J-tube labels", ", ".join(item.get("slots", ["J1", "J2"])), key=f"{edit_key}_jtube_labels")
                names = [tube.strip() for tube in tubes.split(",") if tube.strip()]
                if count == len(item.get("slots", ["J1", "J2"])) and len(names) != count:
                    count = len(names)
                specific["slots"] = [names[index] if index < len(names) else f"J{index + 1}" for index in range(count)]
            elif item["type"] in ("template", "manifold"):
                field = "wells" if item["type"] == "template" else "slots"
                specific[field] = st.number_input("Wells" if field == "wells" else "Manifold slots",
                                                  min_value=0, max_value=24, value=int(item.get(field, 4)), key=f"{edit_key}_slots")
            if item["type"] == "template":
                specific["hipps"] = st.checkbox("Include HIPPS", item.get("hipps", True), key=f"{edit_key}_hipps")
                tree_choices = [""] + list(TREE_TYPES)
                tree = item.get("treeType", "")
                specific["treeType"] = st.selectbox("Xmas tree type", tree_choices,
                                                  index=tree_choices.index(tree) if tree in tree_choices else 0,
                                                  format_func=lambda value: TREE_TYPES[value] if value else "Existing well slots", key=f"{edit_key}_tree")
            if item["type"] not in HOST_IDS + LINK_IDS and not independent_riser and not item.get("riserDetail"):
                configured_ports = item.get("portConfig", {})
                enable_ports = st.checkbox("Customize inlet/outlet hubs", bool(configured_ports), key=f"{edit_key}_custom_ports")
                port_columns = st.columns(4)
                port_mode = port_columns[0].selectbox("Port count mode", ["additional", "replace"],
                                                     index=1 if configured_ports.get("mode") == "replace" else 0,
                                                     format_func=lambda mode: "Additional hubs" if mode == "additional" else "Total hubs on lane", key=f"{edit_key}_port_mode")
                port_lane = port_columns[1].selectbox("Hub lane", ["P", "S", "U"],
                                                     index=["P", "S", "U"].index(configured_ports.get("lane", "P")), key=f"{edit_key}_port_lane")
                inlet_count = port_columns[2].number_input("Inlet connections", 0, MAX_PORTS, int(configured_ports.get("inlets", 0)), key=f"{edit_key}_inlets")
                outlet_count = port_columns[3].number_input("Outlet connections", 0, MAX_PORTS, int(configured_ports.get("outlets", 0)), key=f"{edit_key}_outlets")
                counts_changed = (inlet_count, outlet_count) != (
                    configured_ports.get("inlets", 0), configured_ports.get("outlets", 0))
                use_ports = enable_ports or (counts_changed and (inlet_count > 0 or outlet_count > 0))
                specific["portConfig"] = {"mode": port_mode, "lane": port_lane, "inlets": inlet_count, "outlets": outlet_count} if use_ports else None
                st.caption("Count changes update hubs automatically and enable customization. Additional hubs keeps existing ports; Total hubs sets the count on the selected lane. Uncheck Customize to remove unused custom hubs. Connected hubs cannot be removed until disconnected.")
            if item["type"] not in HOST_IDS + LINK_IDS and not item.get("riserDetail"):
                selected_ports = st.session_state.get("selected_ports", [])
                if selected_ports:
                    st.markdown("**Individual inlet / outlet fluids**")
                    port_table = st.data_editor(
                        pd.DataFrame([{
                            "Port": port["id"],
                            "Label": item.get("portOverrides", {}).get(port["id"], {}).get("label", port["label"]),
                            "Lane": item.get("portOverrides", {}).get(port["id"], {}).get("lane", port["lane"]),
                            "Fluid / service": item.get("portOverrides", {}).get(port["id"], {}).get(
                                "connectionType", port.get("connectionType") or ""),
                        } for port in selected_ports]),
                        key=f"port_settings_{selected}_{st.session_state.ver}", hide_index=True,
                        disabled=["Port"], column_config={
                            "Lane": st.column_config.SelectboxColumn(options=["P", "S", "U"], required=True),
                            "Fluid / service": st.column_config.SelectboxColumn(options=[""] + list(CONNECTION_TYPES)),
                        },
                    )
                    specific["portOverrides"] = {
                        row["Port"]: {"label": row["Label"], "lane": row["Lane"],
                                      "connectionType": row["Fluid / service"] if pd.notna(row["Fluid / service"]) else ""}
                        for row in port_table.to_dict("records")
                    }
                    st.caption("P = process, S = service/chemical, U = umbilical. Match lanes at both ends; fluid/service determines the connection colour. On PLETs, an assigned fluid/service automatically determines compatibility and overrides the Lane column.")
            if item["type"] in ("riser_base", "riser_skid") and not item.get("riserDetail"):
                custom_piping = st.checkbox("Custom internal piping (replace default lines)", "internalRoutes" in item, key=f"{edit_key}_custom_piping")
                if custom_piping:
                    routing_item = {**item, **specific}
                    for field in ("portConfig", "riserPorts"):
                        if routing_item.get(field) is None:
                            routing_item.pop(field, None)
                    ports = sorted(riser_port_ids(routing_item, include_bundled=True))
                    initial_routes = item.get("internalRoutes", [
                        {"id": lane, "from": f"{lane}-left", "to": f"{lane}-right",
                         "connectionType": service}
                        for lane, service in (("P", "multiphase"), ("S", "chemical"), ("U", "umbilical_static"))
                        if f"{lane}-left" in ports and f"{lane}-right" in ports
                    ])
                    route_table = st.data_editor(
                        pd.DataFrame(initial_routes, columns=["id", "from", "to", "connectionType"]),
                        key=f"internal_routes_{selected}_{st.session_state.ver}", hide_index=True, num_rows="dynamic",
                        column_config={
                            "id": st.column_config.TextColumn("Route ID", required=True),
                            "from": st.column_config.TextColumn("From port / @route junction", required=True),
                            "to": st.column_config.SelectboxColumn("To port", options=ports, required=True),
                            "connectionType": st.column_config.SelectboxColumn(
                                "Fluid / service", options=list(CONNECTION_TYPES), required=True),
                        },
                    )
                    specific["internalRoutes"] = route_table.fillna("").to_dict("records")
                    routed_ports = {route.get(end) for route in initial_routes for end in ("from", "to")}
                    unrouted = [port for port in ports if port not in routed_ports]
                    trunks = {route["id"]: route for route in initial_routes
                              if route.get("from") in ports and route.get("to") in ports}
                    internal_hub_options = (unrouted, trunks)
                    st.caption("Ports: " + ", ".join(ports))
                    if specific["bundleServiceInlet"]:
                        st.caption("Bundled S-left is an internal chemical junction on U-left, not an external port. Keep a chemical route S-left -> S-right or a take-off from an umbilical route.")
                    st.caption("Example: route 'umb' connects U-left to U-right (umbilical_static). Add 'chem' from @umb to S-right (chemical) for an internal take-off. Delete all rows for no internal piping. Junctions are schematic take-offs, not mixing every umbilical service.")
                else:
                    specific["internalRoutes"] = None
            st.markdown("**Element maximum design limits**")
            limit_values = design_limit_inputs(item.get("designLimits", {}), "Element", edit_key)
            st.caption("Blank fields inherit layout defaults. Limits are user specifications, not verified equipment capacities.")
            inherited_limits = effective_design_limits(spec, item)
            if inherited_limits:
                st.caption("Currently effective: " + "; ".join(
                    f"{DESIGN_FIELDS[key]['label']}: {value:g}" for key, value in inherited_limits.items() if key in DESIGN_FIELDS
                ))
            properties = {key: value for key, value in item.items() if key not in ("id", "type", "label")}
            properties.pop("designLimits", None)
            properties.pop("labelStyle", None)
            for key in specific:
                properties.pop(key, None)
            st.caption("Element properties: adjust wells, dimensions, coordinates, J-tube slots or other symbol-specific options below.")
            properties_text = st.text_area("Element properties (JSON)", json.dumps(properties, indent=2), height=180, key=f"{edit_key}_properties")
            with st.container():
                if item["type"] in ("riser_base", "riser_skid") and not item.get("riserDetail"):
                    unrouted, trunks = internal_hub_options
                    st.markdown("**Connect an unused hub to an internal line**")
                    st.caption("An added hub is not automatically piped internally. This adds a branch without changing external connections. Use the same service lane; for example P outlet 2 to process.")
                    hub_port = st.selectbox("Hub to connect internally", unrouted or [""], disabled=not unrouted,
                                            key=f"internal_hub_{selected}_{st.session_state.ver}")
                    hub_trunk = st.selectbox("Internal line", list(trunks) or [""], disabled=not trunks,
                                             key=f"internal_trunk_{selected}_{st.session_state.ver}",
                                             format_func=lambda key: f"{key}: {trunks[key]['from']} -> {trunks[key]['to']}" if key else "No direct internal line")
                    connect_hub = st.button("Connect hub to internal line", disabled=not unrouted or not trunks, key=f"{edit_key}_connect_hub")
            edit_values = dict(
                specific=specific, installation=installation, label=label, scale=scale,
                dx=dx, dy=dy, label_style=label_style, limits=limit_values, properties=properties_text,
            )
            if selected_settings_changed(edit_key, edit_values) or load_furb or connect_hub:
                try:
                    updated = json.loads(properties_text)
                    if not isinstance(updated, dict):
                        raise ValueError("Element properties must be a JSON object.")
                    if any(key in updated for key in ("id", "type", "label")):
                        raise ValueError("Keep id, type and label outside the properties JSON.")
                    updated.update(specific)
                    updated.update(installation)
                    updated["labelStyle"] = label_style
                    for optional in ("portConfig", "treeType", "riserPorts", "internalRoutes", "internalValves"):
                        if optional in ("internalRoutes", "internalValves") and specific.get(optional) == []:
                            continue
                        if optional in specific and not updated.get(optional):
                            updated.pop(optional, None)
                    if load_furb:
                        updated.update(furb_configuration(item))
                        updated.pop("portConfig", None)
                    updated["designLimits"] = parse_design_limits(limit_values)
                    candidate = {**updated, "id": selected, "type": item["type"]}
                    if connect_hub:
                        updated["internalRoutes"] = connect_internal_hub(candidate, hub_port, hub_trunk)
                        candidate["internalRoutes"] = updated["internalRoutes"]
                    errors = customization_errors(candidate) + removed_port_errors(spec, candidate)
                    if "internalValves" in candidate and valve_options.get("pipes"):
                        errors += internal_valve_errors(candidate, set(pipe_ids))
                    if errors:
                        raise ValueError(" ".join(errors))
                    if item["type"] in HOST_IDS and "slots" in updated and (
                        not isinstance(updated["slots"], list)
                        or not all(isinstance(slot, str) and slot.strip() for slot in updated["slots"])
                    ):
                        raise ValueError("Host slots must be a list of names, for example [\"J1\", \"J2\"], or empty for no J-tubes.")
                except ValueError as error:
                    st.error(f"Changes not saved: {error}")
                else:
                    item_type = item["type"]
                    had_label = "label" in item
                    item.clear()
                    item.update(updated, id=selected, type=item_type)
                    new_override = spec.setdefault("overrides", {}).setdefault(selected, {})
                    new_override.update(scale=scale / 100, dx=dx, dy=dy)
                    if label or "label" in override or had_label:
                        new_override["label"] = label
                    st.session_state.selected_settings_snapshot = {"scope": edit_key, "values": copy.deepcopy(edit_values)}
                    settings_model["override"] = spec.get("overrides", {}).get(selected, {})
                    st.session_state.selected_settings_model = copy.deepcopy(settings_model)
                    st.session_state.selected_widget_updates = {
                        f"{edit_key}_custom_ports": bool(item.get("portConfig")),
                    }
                    if not item.get("portConfig"):
                        st.session_state.selected_widget_updates.update({
                            f"{edit_key}_inlets": 0, f"{edit_key}_outlets": 0,
                        })
                    if item_type in HOST_IDS:
                        st.session_state.selected_widget_updates.update({
                            f"{edit_key}_jtube_count": len(item["slots"]),
                            f"{edit_key}_jtube_labels": ", ".join(item["slots"]),
                        })
                    if load_furb or not label_style:
                        st.session_state.selected_widget_resets = [
                            key for key in st.session_state if key.startswith(edit_key + "_")
                        ]
                        st.session_state.pop("selected_settings_snapshot", None)
                    for key in list(st.session_state):
                        if key.startswith(("hs_", "ha_", "ht_", "hl_")):
                            del st.session_state[key]
                    bump()
                    st.rerun()

custom_ids = [c["id"] for c in spec.get("customSymbols", [])]
type_options = NODE_IDS + LINK_IDS + HOST_IDS + custom_ids
branches = spec.setdefault("branches", [])

with tab_design:
    st.subheader("Maximum design specification")
    st.caption("Layout defaults apply to all elements unless overridden. These are user-entered specification limits, not calculations, certified ratings or HIPPS sizing.")
    with st.form(f"design_limits_{st.session_state.ver}"):
        layout_limit_values = design_limit_inputs(spec.get("designLimits", {}), "Layout")
        if st.form_submit_button("Apply design specification"):
            try:
                limits = parse_design_limits(layout_limit_values)
            except ValueError as error:
                st.error(f"Cannot apply design specification: {error}")
            else:
                spec["designLimits"] = limits
                bump()
                st.rerun()
    design_rows = []
    for tid, train in trains(spec):
        for element in ([train["host"]] if train.get("host") else []) + train.get("chain", []):
            effective = effective_design_limits(spec, element)
            design_rows.append({"Train": tid, "Element": element.get("id", "Host"),
                                **{field["label"]: effective.get(key) for key, field in DESIGN_FIELDS.items()}})
    if design_rows:
        st.dataframe(pd.DataFrame(design_rows), use_container_width=True, hide_index=True)

# --------------------------------------------------------------------- network
with tab_net:
    st.subheader("Current design network")
    st.caption("Automatically populated from the working drawing, including created, imported and loaded designs. Endpoints are read-only here; reconnect ports in the canvas. Apply settings to update drawn connections.")
    current_equipment = pd.DataFrame(equipment_rows(spec))
    st.markdown("**Equipment and hosts**")
    st.dataframe(current_equipment.drop(columns=["Properties (JSON)"], errors="ignore"),
                 hide_index=True, use_container_width=True)
    st.markdown("**Drawn connections**")
    network_connections = connection_rows(spec)
    if not network_connections.empty:
        with st.form(f"network_connections_{st.session_state.ver}"):
            network_edits = st.data_editor(
                network_connections, key=f"network_connections_{st.session_state.ver}",
                hide_index=True, use_container_width=True,
                disabled=[column for column in network_connections.columns if column not in EDIT_FIELDS],
                column_config={
                    "Kind": st.column_config.SelectboxColumn(options=list(CONNECTION_KINDS)),
                    "Service": st.column_config.SelectboxColumn(options=[""] + list(CONNECTION_TYPES)),
                    "Shape": st.column_config.SelectboxColumn(options=list(RISER_STYLES) + ["static", "scr"]),
                    "PSV": st.column_config.CheckboxColumn(),
                    "PSV position (%)": st.column_config.NumberColumn(
                        min_value=0, max_value=100,
                        help="Only used without a topside host; host-connected PSVs are fixed at the topside termination."),
                })
            apply_network = st.form_submit_button("Apply network connections")
            discard_network = st.form_submit_button("Discard network edits")
        if discard_network:
            bump()
            st.rerun()
        if apply_network:
            try:
                candidate = apply_connection_rows(spec, network_edits.to_dict("records"))
            except ValueError as error:
                st.error(f"Cannot apply network connections: {error}")
            else:
                apply_table_update(candidate, "network_connections")
        table_undo_button("network_connections", "Undo network connections")
    else:
        st.caption("No explicit port-to-port connections yet. Use Connect in the drawing.")
    implicit = implicit_rows(spec)
    if not implicit.empty:
        st.markdown("**Preset risers and implicit train paths**")
        st.dataframe(implicit, hide_index=True, use_container_width=True)
        st.caption("These are not additional drawn connectors. Edit preset risers in Host & risers, and train paths below.")
    st.markdown("**Train settings**")
    network_scope = f"{active}_{st.session_state.get('document_id', 0)}_{st.session_state.ver}"
    st.caption("A train is one left-to-right flowpath. Branches tie into any item of another train (up or down) and "
               "carry their own fluid, lanes and optional host - use them for injection, gas lift, export, loops, power and second hosts.")
    n1, n2, n3 = st.columns(3)
    tr["fluid"] = n1.selectbox("Main line fluid", list(FLUIDS), index=list(FLUIDS).index(tr.get("fluid", "production")) if tr.get("fluid", "production") in FLUIDS else 0,
                               format_func=lambda k: FLUIDS[k], key=f"fluid_{network_scope}")
    lanes = tr.setdefault("lanes", {})
    lanes["S"] = n2.checkbox("Service line runs from the start", lanes.get("S", active == "main" and True), key=f"lS_{network_scope}")
    lanes["U"] = n2.checkbox("Umbilical runs from the start", lanes.get("U", active == "main" and True), key=f"lU_{network_scope}")
    tr["gap"] = int(n3.slider("Gap after host (px)", 0, 120, int(tr.get("gap", 40 if tr.get("host") else 0)), key=f"gap_{network_scope}"))
    m1, m2 = st.columns(2)
    tr["mirror"] = m1.checkbox("Mirror train (right-to-left)", bool(tr.get("mirror", False)), key=f"mir_{network_scope}")
    if not tr["mirror"]:
        tr.pop("mirror")
    fm = ["(follow global)", "forward", "reverse", "none"]
    sel = m2.selectbox("Flow direction for this train", fm, index=fm.index(tr["flow"]) if tr.get("flow") in fm else 0, key=f"flow_{network_scope}")
    if sel.startswith("("):
        tr.pop("flow", None)
    else:
        tr["flow"] = sel
    if active != "main":
        tr["name"] = st.text_input("Branch name", tr.get("name", "Branch"), key=f"nm_{network_scope}")
        f = tr.setdefault("from", {})
        if tr.get("host") is None:
            others = [i for i in every_id if i not in [c.get("id") for c in chain]]
            if others:
                f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
                cur = f.get("item") if f.get("item") in others else others[0]
                f["item"] = f1.selectbox("Tie into item", others, index=others.index(cur), key=f"fi_{network_scope}")
                f["side"] = f2.selectbox("Side", ["down", "up"], index=0 if f.get("side", "down") == "down" else 1, key=f"fs_{network_scope}")
                f["dx"] = int(f3.number_input("Offset dx", -300, 300, int(f.get("dx", 0)), key=f"fx_{network_scope}"))
                tr["dy"] = int(f4.number_input("Row spacing dy", 80, 700, int(tr.get("dy", 240)), step=10, key=f"fy_{network_scope}"))
                f["valve"] = st.checkbox("Isolation valve in tie-in", f.get("valve", True), key=f"fv_{network_scope}")
                f["label"] = st.text_input("Tie-in label", f.get("label", ""), key=f"fl_{network_scope}")
                if not f["label"]:
                    f.pop("label")
        else:
            tr["x"] = int(st.number_input("Host x position", 0, 2000, int(tr.get("x", 0)), key=f"hx_{network_scope}"))
            tr["dy"] = int(st.number_input("Row spacing dy", 80, 900, int(tr.get("dy", 360)), step=10, key=f"hy_{network_scope}"))
    if active != "main":
        tgt = [i for i in every_id if i not in [c.get("id") for c in chain]]
        rj = st.checkbox("Rejoin another train at the end (loop)", bool(tr.get("to")), key=f"rj_{network_scope}")
        if rj and tgt:
            to = tr.setdefault("to", {})
            cur = to.get("item") if to.get("item") in tgt else tgt[-1]
            r1, r2, r3 = st.columns([2, 1, 1])
            to["item"] = r1.selectbox("Rejoin at item", tgt, index=tgt.index(cur), key=f"ri_{network_scope}")
            to["side"] = r2.selectbox("Side", ["up", "down"], index=0 if to.get("side", "up") == "up" else 1, key=f"rs_{network_scope}")
            to["dx"] = int(r3.number_input("Offset dx", -300, 300, int(to.get("dx", 0)), key=f"rx_{network_scope}"))
            to["label"] = st.text_input("Rejoin label", to.get("label", ""), key=f"rl_{network_scope}")
            if not to["label"]:
                to.pop("label")
        else:
            tr.pop("to", None)
    st.markdown("**Add / remove branches**")
    b1, b2, b3, b4 = st.columns([2, 1, 1, 1])
    parent = b1.selectbox("New branch ties into", ["(independent train)"] + every_id, key="nb_parent")
    nfl = b2.selectbox("Fluid", list(FLUIDS), index=1, format_func=lambda k: FLUIDS[k], key="nb_fluid")
    nsd = b3.selectbox("Side", ["down", "up"], key="nb_side")
    if b4.button("＋ Add branch"):
        new_id = add_branch(spec, None if parent.startswith("(") else parent, nsd, nfl, name=FLUIDS[nfl])
        st.session_state.active_train = new_id
        bump(); st.rerun()
    if active != "main" and st.button("✕ Remove this branch"):
        remove_branch(spec, active)
        st.session_state.active_train = "main"
        bump(); st.rerun()
    st.dataframe(pd.DataFrame([{"Train": train_names[t], "Fluid": FLUIDS.get(x.get("fluid", "production")), "Items": len(x.get("chain", [])),
                                "Tie-in": (x.get("from") or {}).get("item", "-" if t == "main" else "independent"),
                                "Host": (x.get("host") or {}).get("type", "-")} for t, x in trains(spec)]), use_container_width=True, hide_index=True)

# ------------------------------------------------------------- equipment chain
with tab_chain:
    st.caption("Left → right along the flowpath. Links (pipeline_*) carry the line labels; "
               "`props` takes any extra JSON, e.g. {\"hipps\": false, \"wellStart\": 5, \"lane\": \"P\"}. Ids must be unique across the whole network.")
    with st.form(f"chain_settings_{active}_{st.session_state.ver}"):
        edited = st.data_editor(
            chain_to_df(chain), key=f"chain_{active}_{st.session_state.ver}", num_rows="dynamic", use_container_width=True,
            column_config={
                "type": st.column_config.SelectboxColumn("type", options=type_options, required=True, width="medium"),
                "id": st.column_config.TextColumn("id", help="Used by zones, tie-ins and drag-overrides"),
                "label": st.column_config.TextColumn("label", help="Empty text hides the default caption"),
                "w": st.column_config.NumberColumn("width px", min_value=20, max_value=600),
                "pCount": st.column_config.NumberColumn("parallel lines", min_value=1, max_value=4, help="Draw N parallel pipelines"),
                "pKm": st.column_config.NumberColumn("pipe km"), "pId": st.column_config.NumberColumn('pipe ID "'),
                "sKm": st.column_config.NumberColumn("service km"), "sId": st.column_config.NumberColumn('service ID "'),
                "uKm": st.column_config.NumberColumn("umb. km"),
                "wells": st.column_config.NumberColumn("wells", min_value=0, max_value=24),
                "slots": st.column_config.NumberColumn("slots", min_value=0, max_value=24),
                "props": st.column_config.TextColumn("props (JSON)", width="large"),
            })
        apply_chain = st.form_submit_button("Apply equipment chain")
        discard_chain = st.form_submit_button("Discard chain edits")
    if discard_chain:
        bump()
        st.rerun()
    if apply_chain:
        new_chain, problems = df_to_chain(edited, taken)
        if problems:
            st.error("Cannot apply equipment chain: " + " ".join(problems))
        else:
            candidate = copy.deepcopy(spec)
            existing_ids = set(all_ids(spec))
            for item in new_chain:
                if item["id"] not in existing_ids:
                    item.setdefault("installationStatus", "New")
            get_train(candidate, active)["chain"] = new_chain
            apply_table_update(candidate, f"chain_{active}")
    table_undo_button(f"chain_{active}", "Undo equipment chain")

    st.markdown("**Reorder / remove**")
    if chain:
        r1, r2, r3, r4 = st.columns([3, 1, 1, 1])
        pick = r1.selectbox("Item", [c["id"] for c in chain], label_visibility="collapsed",
                            format_func=lambda i: f"{i} – {type_label(next(c['type'] for c in chain if c['id'] == i))}")
        if r2.button("↑ Up"):
            tr["chain"] = move_item(chain, pick, -1); bump(); st.rerun()
        if r3.button("↓ Down"):
            tr["chain"] = move_item(chain, pick, +1); bump(); st.rerun()
        if r4.button("✕ Remove"):
            tr["chain"] = remove_item(chain, pick); bump(); st.rerun()

# ------------------------------------------------------------------ host/risers
with tab_host:
    train_host = tr.get("host")
    host_choices = {}
    if train_host is not None:
        host_choices[train_host.get("id") or "__train_host__"] = train_host
    host_choices.update({item["id"]: item for item in chain if item.get("type") in HOST_IDS})
    host = None
    host_scope = active
    if host_choices:
        selected_host = st.session_state.get("selected_element")
        previous_host = st.session_state.get(f"design_host_last_{active}")
        selection_event = (st.session_state.get("document_id", 0),
                           st.session_state.get("viewer_ack", 0), selected_host)
        new_selection = selection_event != st.session_state.get(f"design_host_selection_{active}")
        default_host = selected_host if new_selection and selected_host in host_choices else previous_host
        st.session_state[f"design_host_selection_{active}"] = selection_event
        if default_host not in host_choices:
            default_host = next(iter(host_choices))
        host_id = st.selectbox(
            "Design host", list(host_choices), index=list(host_choices).index(default_host),
            format_func=lambda key: f"{host_choices[key].get('label') or type_label(host_choices[key]['type'])} ({key if key != '__train_host__' else 'train source'})",
            key=f"design_host_{active}_{st.session_state.get('document_id', 0)}_{st.session_state.ver}")
        st.session_state[f"design_host_last_{active}"] = host_id
        host = host_choices[host_id]
        host_scope = active if host is train_host else f"{active}_{host_id}"
        st.caption("Editing the actual host in this train. Select another here, or click a host in the drawing.")
    else:
        st.info("No hosts in this train. Add a host from Symbols or enable a preset train source below.")
    host_key = f"hh_{active}_{st.session_state.get('document_id', 0)}_{st.session_state.ver}"
    with st.expander("Preset train source (separate from independently drawn hosts)"):
        st.checkbox("Include a host / source" if active == "main" else "This train has its own host / source",
                    train_host is not None, key=host_key, on_change=change_host_presence,
                    args=(active, host_key, st.session_state.get("document_id", 0), st.session_state.ver))
    if host is not None:
        h1, h2, h3 = st.columns(3)
        host["type"] = h1.selectbox("Host", HOST_IDS, index=HOST_IDS.index(host.get("type", "jacket")) if host.get("type") in HOST_IDS else 0,
                                    format_func=lambda i: BY_ID[i]["name"], key=f"ht_{host_scope}_{st.session_state.ver}")
        slots_txt = h2.text_input("Slot / riser labels (comma separated)", ", ".join(host.get("slots", ["J1", "J2"])), key=f"hs_{host_scope}_{st.session_state.ver}")
        candidate_host = {**host, "slots": [x.strip() for x in slots_txt.split(",") if x.strip()]}
        slot_errors = customization_errors(candidate_host) + removed_port_errors(spec, candidate_host)
        if slot_errors:
            st.error(" ".join(slot_errors))
        else:
            host["slots"] = candidate_host["slots"]
        last_slot = max(0, len(host.get("slots", ["J1", "J2"])) - 1)
        host["activeSlot"] = int(h3.number_input("Highlighted slot (0-based)", 0, last_slot,
                                               min(int(host.get("activeSlot", 0)), last_slot),
                                               key=f"ha_{host_scope}_{st.session_state.ver}"))
        if host["type"] in ("tieback", "wind", "hrt"):
            host["label"] = st.text_input("Host text", host.get("label", ""), key=f"hl_{host_scope}_{st.session_state.ver}")
        connected_rows = []
        for index, connection in enumerate(spec.get("connections", [])):
            end = "from" if connection.get("from") == host.get("id") else "to" if connection.get("to") == host.get("id") else None
            if not end:
                continue
            other = "to" if end == "from" else "from"
            connected_rows.append({
                "Connection": index, "Equipment": connection.get(other),
                "Equipment port": connection.get(other + "Port", ""),
                "Host port": connection.get(end + "Port", ""),
                "lane": connection.get("lane", "P"), "kind": connection.get("kind", ""),
                "style": connection.get("style", "rigid"), "label": connection.get("label", ""),
                "connectionType": connection.get("connectionType", ""),
            })
        st.markdown("**Drawn host connections / risers**")
        if connected_rows:
            connection_df = pd.DataFrame(connected_rows)
            host_ports = ([f"J-{index}" for index in range(len(host.get("slots", ["J1", "J2"])))]
                          if host["type"] not in ("onshore", "tieback") else [])
            if host_ports or host["type"] in ("onshore", "tieback"):
                host_ports += ["P-right", "S-right", "U-right"]
            with st.form(f"host_connections_{host_scope}_{st.session_state.ver}"):
                edited_connections = st.data_editor(
                    connection_df, key=f"host_connections_{host_scope}_{st.session_state.ver}",
                    hide_index=True, use_container_width=True,
                    disabled=["Connection", "Equipment", "Equipment port", "lane"],
                    column_config={
                        "Host port": st.column_config.SelectboxColumn(options=host_ports, required=True,
                            help="J-0 is the first named J-tube, J-1 the second."),
                        "kind": st.column_config.SelectboxColumn(options=list(CONNECTION_KINDS)),
                        "style": st.column_config.SelectboxColumn(options=list(RISER_STYLES) + ["static", "scr"]),
                        "connectionType": st.column_config.SelectboxColumn(options=[""] + list(CONNECTION_TYPES)),
                    })
                apply_connections = st.form_submit_button("Apply host connections")
                discard_connections = st.form_submit_button("Discard host connection edits")
            if discard_connections:
                bump()
                st.rerun()
            if apply_connections:
                candidate = copy.deepcopy(spec)
                connection_errors = []
                for original, row in zip(connected_rows, edited_connections.fillna("").to_dict("records")):
                    connection = candidate["connections"][original["Connection"]]
                    end = "from" if connection["from"] == host.get("id") else "to"
                    if row["Host port"] != original["Host port"]:
                        port = row["Host port"]
                        if port not in host_ports or (not port.startswith("J-") and port[0] != connection.get("lane", "P")):
                            connection_errors.append(f"Connection {original['Connection']}: choose an available host port matching its lane.")
                    for column in ("Host port", "kind", "style", "label", "connectionType"):
                        if row[column] != original[column]:
                            field = end + "Port" if column == "Host port" else column
                            if row[column] or column == "label":
                                connection[field] = row[column]
                            else:
                                connection.pop(field, None)
                if connection_errors:
                    st.error("Cannot apply host connections: " + " ".join(connection_errors))
                else:
                    apply_table_update(candidate, f"host_connections_{host_scope}")
            table_undo_button(f"host_connections_{host_scope}", "Undo host connections")
        else:
            st.caption("No drawn connections attached to this host. Use Connect in the drawing to attach a riser to a J-tube.")
        st.caption("J-tube mapping: " + (", ".join(f"J-{index}: {slot}" for index, slot in enumerate(host.get("slots", ["J1", "J2"]))) or "no J-tubes"))
    if host is not None and host is train_host:
        riser_columns = ["lane", "slot", "style", "label", "color", "dx", "ldx", "psv", "psvTag", "psvPosition"]
        riser_columns += list(dict.fromkeys(key for riser in host.get("risers", [])
                                            for key in riser if key not in riser_columns))
        risers = pd.DataFrame(host.get("risers", []), columns=riser_columns)
        for column in ("lane", "style", "label", "color"):
            risers[column] = risers[column].fillna("").astype("string")
        risers["psv"] = risers["psv"].fillna(False).astype(bool)
        risers["psvTag"] = risers["psvTag"].fillna("").astype("string")
        risers["psvPosition"] = pd.to_numeric(risers["psvPosition"], errors="coerce").fillna(50)
        st.caption("Risers: P = main line, S = service, U = umbilical. Ignored for onshore / tie-in hosts. PSVs are fixed at the topside termination; legacy position values are retained but no longer move the marker.")
        with st.form(f"riser_settings_{active}_{st.session_state.ver}"):
            r_ed = st.data_editor(risers, key=f"risers_{active}_{st.session_state.ver}", num_rows="dynamic", use_container_width=True, disabled=["psvPosition"], column_config={
                "lane": st.column_config.SelectboxColumn("lane", options=["P", "S", "U"], required=True),
                "slot": st.column_config.NumberColumn("slot", min_value=0, max_value=9, step=1),
                "style": st.column_config.SelectboxColumn("style", options=["rigid", "static", "scr", "flex", "lazywave"]),
                "color": st.column_config.SelectboxColumn("color", options=["red", "yellow", "green", "blue"]),
                "psv": st.column_config.CheckboxColumn("Add PSV"),
                "psvTag": st.column_config.TextColumn("PSV tag"),
                "psvPosition": st.column_config.NumberColumn("PSV position (%)", min_value=0, max_value=100,
                                                            help="Legacy metadata only; the PSV is fixed at the topside termination."),
                "dx": st.column_config.NumberColumn("dx px"), "ldx": st.column_config.NumberColumn("label dx px")})
            apply_risers = st.form_submit_button("Apply risers")
            discard_risers = st.form_submit_button("Discard riser edits")
        if discard_risers:
            bump()
            st.rerun()
        if apply_risers:
            candidate = copy.deepcopy(spec)
            records = r_ed.to_dict("records")
            incomplete = any(not row.get("lane") and any(pd.notna(value) and value != "" for value in row.values())
                             for row in records)
            if incomplete:
                st.error("Cannot apply risers: choose a lane for every non-empty row.")
            else:
                new_risers = [
                    {k: (int(v) if k == "slot" else v) for k, v in row.items() if pd.notna(v) and v != ""}
                    for row in records if pd.notna(row.get("lane")) and row.get("lane")]
                for index, riser in enumerate(new_risers):
                    if index >= len(host.get("risers", [])):
                        riser.setdefault("installationStatus", "New")
                get_train(candidate, active)["host"]["risers"] = new_risers
                apply_table_update(candidate, f"risers_{active}")
        table_undo_button(f"risers_{active}", "Undo risers")

# ------------------------------------------------------------------------ zones
with tab_zones:
    zone_settings = st.container()

# ------------------------------------------------------------------ add equipment
with tab_add:
    if spec.get("freeform"):
        st.caption("Add symbols to the blank canvas, then drag each symbol or line segment to arrange your drawing. Use the viewer grid, zoom and pan controls to position items.")
    a1, a2 = st.columns([2, 1])
    cat_filter = a1.selectbox("Category", CATEGORIES + ["Custom"], key="addcat")
    if cat_filter == "Custom":
        pool = custom_ids
    else:
        pool = [e["id"] for e in CATALOG if e["category"] == cat_filter]
    after = a2.selectbox("Insert after (in the train being edited)", ["(end)"] + [c["id"] for c in chain])
    if pool:
        with st.form("add_item"):
            t = st.selectbox("Equipment", pool, format_func=type_label)
            st.caption(BY_ID.get(t, {}).get("desc", ""))
            f1, f2, f3, f4 = st.columns(4)
            lab = f1.text_input("Label (optional)")
            wd = f2.number_input("Width px (0 = auto)", 0, 600, 0)
            nwells = f3.number_input("Wells / slots", 0, 24, 0)
            pkm = f4.number_input("Pipe km", 0.0, 500.0, 0.0)
            if st.form_submit_button("Add"):
                props = {"label": lab or None, "w": wd or None, "pKm": pkm or None}
                if t == "template":
                    props["wells"] = nwells or 4
                if t == "manifold":
                    props["slots"] = nwells or 4
                props.setdefault("installationStatus", "New")
                if t == "custom_element":
                    props.update(blank_element_configuration())
                tr["chain"] = insert_item(chain, t, None if after == "(end)" else after, taken, **props)
                bump(); st.rerun()
    else:
        st.info("No custom symbols yet – define one below.")
    with st.expander("Define custom equipment"):
        with st.form("custom_sym"):
            k1, k2, k3, k4 = st.columns(4)
            cid = k1.text_input("id (a-z, 0-9, _)")
            cshape = k2.selectbox("Symbol shape", CUSTOM_SHAPES)
            clane = k3.selectbox("Lane", ["P", "S", "U"])
            cabbr = k4.text_input("Abbreviation")
            cw = st.number_input("Width px", 20, 300, 70)
            if st.form_submit_button("Create") and cid.strip():
                cid = "".join(ch for ch in cid.strip().lower() if ch.isalnum() or ch == "_")
                if cid in BY_ID or cid in custom_ids:
                    st.error("That id already exists")
                else:
                    spec.setdefault("customSymbols", []).append(
                        {"id": cid, "shape": cshape, "lane": clane, "abbr": cabbr or cid.upper(), "w": int(cw)})
                    bump(); st.rerun()

# ---------------------------------------------------------------- design checks
with tab_chk:
    st.subheader("Concept-design screening")
    st.caption("Automatically reviews the current design without modifying it. No project standard, edition or acceptance "
               "criteria have been specified. This is not a compliance certificate, engineering approval or proof of a safe design.")
    findings = run_checks(spec)
    actions = sum(f["status"] == "Action required" for f in findings)
    unassessed = sum(f["status"] == "Not assessed" for f in findings)
    screened = sum(f["status"] == "Screened" for f in findings)
    errors = sum(f["level"] == "error" for f in findings)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Action required", actions)
    m2.metric("Not assessed", unassessed)
    m3.metric("Checks screened", screened)
    m4.metric("Data conflicts", errors)
    if actions:
        st.warning("Open actions require review. Missing engineering evidence remains Not assessed, not passed.")
    else:
        st.info("No automated action flags were raised. Engineering assessment gaps remain open; the design is not approved.")
    st.caption("Screened means only the stated data comparison or declared-connectivity check completed. "
               "Layout defaults, free-text ratings, equipment symbols and decorative 3D geometry are not certified equipment data.")
    report = pd.DataFrame([{
        "Design": spec.get("title", ""), "Area": f["category"], "Status": f["status"], "Severity": f["level"],
        "Rule": f["rule"], "Reference": f["where"], "Finding": f["message"],
        "Required follow-up": f["action"], "Evidence / limitations": f["evidence"],
    } for f in findings])
    by_area = report.groupby("Area")["Status"].value_counts().unstack(fill_value=0)
    st.markdown("**Review coverage**")
    st.dataframe(by_area, use_container_width=True)
    filter_area, filter_status = st.columns(2)
    area = filter_area.selectbox("Review area", ["All areas"] + sorted(report["Area"].unique().tolist()))
    statuses = filter_status.multiselect("Review status", ["Action required", "Not assessed", "Screened"],
                                        default=["Action required", "Not assessed"])
    visible = report.loc[report["Status"].isin(statuses)]
    if area != "All areas":
        visible = visible.loc[visible["Area"] == area]
    st.dataframe(visible.drop(columns=["Design"]), use_container_width=True, hide_index=True)
    csv_download, excel_download, pdf_download = st.columns(3)
    csv_download.download_button("Download full concept review (CSV)", report.to_csv(index=False).encode("utf-8-sig"),
                                 file_name="concept_design_review.csv", mime="text/csv")
    excel_download.download_button("Download full concept review (Excel)", review_excel(report),
                                   file_name="concept_design_review.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pdf_download.download_button("Download full concept review (PDF)", review_pdf(report),
                                 file_name="concept_design_review.pdf", mime="application/pdf")
    st.caption("Downloads include every result, regardless of the filters. Excel includes an Open checklist, Full review, "
               "Coverage and Read me sheets. PDF includes the full checklist and discipline coverage. Review evidence, calculations and "
               "discipline sign-off must be managed separately; schematic distances are never used as engineering clearances.")

# --------------------------------------------------------------- equipment list
with tab_bom:
    bom = equipment_list(spec)
    tot = totals(bom)
    q1, q2, q3 = st.columns(3)
    q1.metric("Items", tot["items"]); q2.metric("Wells", tot["wells"]); q3.metric("Flowline km", f"{tot['flowline_km']:g}")
    st.dataframe(bom, use_container_width=True, hide_index=True)
    st.markdown("**Summary by equipment type**")
    st.dataframe(summary(bom), use_container_width=True, hide_index=True)
    st.download_button("Download equipment list (CSV)", bom.to_csv(index=False).encode("utf-8-sig"), file_name="equipment_list.csv", mime="text/csv")
    st.subheader("Installation tags & costing export")
    inventory = installation_list(spec)
    st.caption("Tag equipment, hosts, preset risers and drawn connections. New additions default to New; untagged loaded items are Unspecified. Rating includes units, e.g. 10 K psi. Enter actual installed lengths, not drawing distances.")
    with st.form(f"installation_inventory_{st.session_state.ver}"):
        edited_inventory = st.data_editor(
            inventory, hide_index=True, use_container_width=True,
            disabled=[column for column in inventory.columns if column not in TAG_FIELDS],
            column_config={
                "Installation status": st.column_config.SelectboxColumn(options=list(STATUSES), required=True),
                "Installed length (km)": st.column_config.NumberColumn(min_value=0.0),
            },
        )
        if st.form_submit_button("Apply installation tags"):
            try:
                candidate = apply_installation_rows(spec, edited_inventory.to_dict("records"))
            except ValueError as error:
                st.error(f"Cannot apply installation tags: {error}")
            else:
                apply_table_update(candidate, "installation")
    table_undo_button("installation", "Undo installation tags")
    new_inventory = inventory.loc[inventory["Installation status"] == "New"]
    st.metric("New installation objects", int(new_inventory["Qty"].sum()))
    st.dataframe(new_installation_summary(inventory), hide_index=True, use_container_width=True)
    for note in costing_notes(inventory):
        st.warning(note)
    st.caption("Exports use applied tags only. Existing and Unspecified items are excluded.")
    xlsx_column, pdf_column = st.columns(2)
    xlsx_column.download_button("Download new installation (Excel)", costing_excel(inventory),
                                file_name="new_installation.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pdf_column.download_button("Download new installation (PDF)", costing_pdf(inventory),
                               file_name="new_installation.pdf", mime="application/pdf")

# --------------------------------------------------------------------- JSON tab
with tab_json:
    body = json.dumps(spec, indent=2, ensure_ascii=False)
    txt = st.text_area("Spec", body, height=380, key=f"json_{hash(body)}")
    j1, j2, j3 = st.columns(3)
    if j1.button("Apply JSON"):
        try:
            load_spec(json.loads(txt))
        except ValueError as e:
            st.error(f"Invalid JSON: {e}")
    j2.download_button("Download spec", body, file_name="subsea_layout.json", mime="application/json")
    j3.download_button("Download standalone HTML", build_html(spec), file_name="subsea_layout.html", mime="text/html")
    st.caption("Drawing edits and manual positions are synchronized automatically. Download the spec to keep a file backup.")

# ------------------------------------------------------------------ catalogue tab
with tab_cat:
    q1, q2 = st.columns([2, 1])
    cats = q1.multiselect("Categories", CATEGORIES, default=CATEGORIES[:2])
    search = q2.text_input("Search")
    shown = [e for e in CATALOG if e["category"] in cats and (not search or search.lower() in (e["name"] + e["id"] + e["desc"]).lower())]
    st.caption(f"{len(shown)} of {len(CATALOG)} symbols")
    if shown:
        components.html(build_html(None, "catalog", shown), height=820, scrolling=True)

# ------------------------------------------------------------------- the diagram
with inventory_panel:
    st.subheader("All drawn equipment settings")
    st.caption("Includes every train, host and placed symbol. Labels, size, offsets and hidden state reflect drawing overrides. Properties JSON includes coordinates, ports, J-tubes and design limits. Apply validates the complete design without resetting the view.")
    rows = equipment_rows(spec)
    if rows:
        with st.form(f"all_equipment_{st.session_state.ver}"):
            all_equipment = st.data_editor(
                pd.DataFrame(rows), key=f"all_equipment_table_{st.session_state.ver}",
                hide_index=True, use_container_width=True,
                disabled=["Id", "Train", "Role", "Type"],
                column_config={"Id": st.column_config.TextColumn(width=140),
                               "Train": st.column_config.TextColumn(width=80),
                               "Role": st.column_config.TextColumn(width=100),
                               "Type": st.column_config.TextColumn(width=130),
                               "Label": st.column_config.TextColumn(width=200),
                               "Size (%)": st.column_config.NumberColumn(min_value=1),
                               "Properties (JSON)": st.column_config.TextColumn(width="large")},
            )
            apply_inventory = st.form_submit_button("Apply all equipment settings")
            discard_inventory = st.form_submit_button("Discard equipment table edits")
            if discard_inventory:
                bump()
                st.rerun()
            if apply_inventory:
                try:
                    updated_spec = apply_equipment_rows(spec, all_equipment.to_dict("records"))
                except (ValueError, TypeError) as error:
                    st.error(f"Cannot apply equipment table: {error}")
                else:
                    hosts = [element["id"] for _, train in trains(updated_spec)
                             for element in ([train["host"]] if train.get("host") else []) + train.get("chain", [])
                             if element.get("type") in HOST_IDS and element.get("id")]
                    if hosts:
                        sea = updated_spec.setdefault("seaLevel", {})
                        sea.setdefault("host", hosts[0])
                        sea.setdefault("offset", 0.0)
                    apply_table_update(updated_spec, "inventory")
        table_undo_button("inventory", "Undo equipment table")
    else:
        st.caption("No equipment drawn yet. Add equipment or a host from Symbols.")

with zone_settings:
    st.info("Use **+ Zone** in the drawing toolbar. Drag the blue handles to adjust each boundary and arrow height; drag the label to position it. Click an arrow, label or dashed boundary to open its editor. All drawing edits save automatically.")
    st.caption("Select equipment before + Zone to anchor it, or add a zone anywhere without a selection. Use multiple zones for LC1, LC2 and Fortified zone. Enter distances in metres or kilometres in the drawing editor; they are labels, NOT TO SCALE. Save a case version to keep your design.")
    zone_ids = [item_id for item_id in all_ids(spec) if item_id]
    zone_ids += [(train.get("host") or {})["id"] for _, train in trains(spec)
                 if (train.get("host") or {}).get("id")]
    zone_positions = ("leftOffset", "rightOffset", "yOffset", "bottomOffset", "labelDx", "labelDy")
    z_df = pd.DataFrame(spec.get("zones", []), columns=[
        "from", "to", "label", "edges", "fromHost", "distanceM", "distanceDirection",
        "placement", "distanceUnit", "arrows", *zone_positions,
    ])
    for column in ("from", "to", "label", "edges", "placement", "distanceUnit", "arrows"):
        z_df[column] = z_df[column].fillna("").astype("string")
    z_df["fromHost"] = z_df["fromHost"].fillna(False).astype(bool)
    z_df["distanceM"] = pd.to_numeric(z_df["distanceM"], errors="coerce")
    z_df["distanceDirection"] = z_df["distanceDirection"].fillna("").astype("string")
    for column in zone_positions:
        z_df[column] = pd.to_numeric(z_df[column], errors="coerce")
    with st.expander("Advanced: zone table"), st.form(f"zone_settings_{st.session_state.ver}"):
        z_ed = st.data_editor(
            z_df, key=f"zones_{st.session_state.ver}", num_rows="dynamic", use_container_width=True,
            column_config={
                "from": st.column_config.SelectboxColumn("from item", options=zone_ids, help="Required unless placement is free."),
                "to": st.column_config.SelectboxColumn("to item", options=zone_ids),
                "label": st.column_config.TextColumn("zone label"),
                "edges": st.column_config.SelectboxColumn("dashed edges", options=["both", "left", "right", "none"]),
                "fromHost": st.column_config.CheckboxColumn("start at host"),
                "distanceM": st.column_config.NumberColumn("distance (m)", min_value=0.01,
                                                         help="Optional engineering distance, shown schematically, NOT TO SCALE."),
                "distanceDirection": st.column_config.SelectboxColumn("distance direction", options=["right", "left"]),
                "placement": st.column_config.SelectboxColumn("placement", options=["anchored", "free"]),
                "distanceUnit": st.column_config.SelectboxColumn("display unit", options=["m", "km"],
                                                                 help="distance (m) is always stored in metres; this changes only its display."),
                "arrows": st.column_config.SelectboxColumn("arrowheads", options=["both", "left", "right", "none"]),
                **{column: st.column_config.NumberColumn(column, help="Drawing units, not metres. Offsets from equipment bounds; absolute coordinates for free zones.")
                   for column in zone_positions},
            })
        apply_zones = st.form_submit_button("Apply zones")
        discard_zones = st.form_submit_button("Discard zone edits")
        if discard_zones:
            bump()
            st.rerun()
        if apply_zones:
            zones = []
            errors = []
            for index, row in enumerate(z_ed.to_dict("records"), start=1):
                zone = {key: value for key, value in row.items()
                        if pd.notna(value) and value != "" and not (key == "fromHost" and not value)}
                if not zone:
                    continue
                if not zone.get("from") and zone.get("placement") != "free":
                    errors.append(f"Zone row {index}: select a start item.")
                elif any(zone.get(key) and zone[key] not in zone_ids for key in ("from", "to")):
                    errors.append(f"Zone row {index}: select existing equipment.")
                else:
                    zones.append(zone)
            if errors:
                st.error("Cannot apply zones: " + " ".join(errors))
            else:
                candidate = copy.deepcopy(spec)
                candidate["zones"] = zones
                apply_table_update(candidate, "zones")
    table_undo_button("zones", "Undo zones")

with tab_cases:
    render_cases(spec, load_spec)
with tab_compare:
    render_comparison(spec)

with diagram:
    elements = [element for _, train in trains(spec)
                for element in ([train["host"]] if train.get("host") else []) + train.get("chain", [])]
    selection = st.session_state.get("selected_element")
    if isinstance(st.session_state.get("selected_connection"), int):
        selection = f"Connection {st.session_state.selected_connection + 1}"
    case_status = (f"Case version {st.session_state.get('case_version', '-')}"
                   if st.session_state.get("case_id") else "Working drawing")
    st.markdown(
        '<div class="workspace-status" aria-label="Drawing status">'
        f'<span><strong>{escape(case_status)}</strong> &middot; save a version to keep changes</span>'
        f'<span>{len(elements)} equipment items &middot; {len(spec.get("connections", []))} drawn connections &middot; {len(trains(spec))} {"train" if len(trains(spec)) == 1 else "trains"}</span>'
        f'<span>Selection: <strong>{escape(str(selection or "None"))}</strong></span></div>',
        unsafe_allow_html=True,
    )
    issues = validate(spec)
    for m in issues:
        st.warning(m)
    if st.session_state.get("viewer_error"):
        st.error(st.session_state.pop("viewer_error"))
    editor(spec=spec, html=build_html(spec), height=height,
           documentId=st.session_state.get("document_id", 0),
           ack=st.session_state.get("viewer_ack", 0),
           key="drawing_editor", on_change=receive_drawing, default=None)

# Include host defaults populated by the other settings panels.
st.session_state.selected_settings_model = copy.deepcopy(settings_model)

