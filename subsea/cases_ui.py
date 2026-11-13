"""Streamlit case library and saved-design comparison."""
import copy
import json
import sqlite3

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .cases import CaseStore, compare_designs
from .html import build_html


def render_cases(spec, load_spec):
    store = CaseStore()
    st.caption(f"Saved locally on this computer: {store.path}. Versions are snapshots, never overwritten. Download JSON for a portable backup.")
    try:
        cases = store.list_cases()
        names = {case["id"]: case["name"] for case in cases}
        active = st.session_state.get("case_id")
        if active:
            st.info(f"Working case: {names.get(active, 'Deleted case')} · loaded/saved version {st.session_state.get('case_version', '-')}")
        with st.form("save_case"):
            name = st.text_input("Case name", names.get(active, spec.get("title", "New case")))
            label = st.text_input("Version note", "")
            new_case = st.checkbox("Save as a new case", active is None)
            if st.form_submit_button("Save case version"):
                case_id, number = store.save(name, spec, label, None if new_case else active)
                st.session_state.case_id = case_id
                st.session_state.case_version = number
                st.session_state.saved_case = case_id
                st.session_state[f"saved_version_{case_id}"] = number
                st.session_state.case_message = f"Saved {name}: version {number}."
                st.rerun()
        if st.session_state.get("case_message"):
            st.success(st.session_state.pop("case_message"))
        if not cases:
            st.info("No saved cases yet. Save the current drawing above.")
            return
        selected = st.selectbox("Saved case", list(names), format_func=names.get, key="saved_case")
        versions = store.versions(selected)
        if not versions:
            st.warning("This case was removed in another session. Refresh the page.")
            return
        version_names = {row["number"]: f"v{row['number']} · {row['created']} · {row['label']}" for row in versions}
        number = st.selectbox("Saved version", list(version_names), format_func=version_names.get,
                              key=f"saved_version_{selected}")
        st.caption("Loading replaces the working drawing. Save unsaved work first.")
        if st.button("Load saved version"):
            loaded = store.load(selected, number)
            st.session_state.case_id = selected
            st.session_state.case_version = number
            load_spec(loaded)
        with st.form("duplicate_case"):
            duplicate_name = st.text_input("Duplicate case name", f"{names[selected]} - copy")
            if st.form_submit_button("Duplicate saved case"):
                _, duplicate_number = store.duplicate(selected, number, duplicate_name)
                st.session_state.case_message = f"Created {duplicate_name} as an independent case (v{duplicate_number})."
                st.rerun()
        with st.form("delete_case"):
            scope = st.selectbox("Delete scope", ["Selected version only", "Entire case and all versions"])
            confirm = st.checkbox("Confirm permanent deletion")
            if st.form_submit_button("Delete saved data"):
                if not confirm:
                    st.error("Confirm deletion before deleting saved data.")
                else:
                    store.delete(selected, number if scope == "Selected version only" else None)
                    if active == selected and (scope != "Selected version only" or number == st.session_state.get("case_version")):
                        st.session_state.pop("case_id", None)
                        st.session_state.pop("case_version", None)
                    st.session_state.case_message = "Saved data deleted. The working drawing was not changed."
                    st.rerun()
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        st.error(f"Case storage failed: {error}")


def render_comparison(spec):
    store = CaseStore()
    try:
        cases = store.list_cases()
        if not cases:
            st.info("Save at least one case version to compare it with the current drawing.")
            return
        options = {"current": "Current drawing"}
        refs = {}
        for case in cases:
            for version in store.versions(case["id"]):
                key = f"{case['id']}:{version['number']}"
                refs[key] = (case["id"], version["number"])
                options[key] = f"{case['name']} · v{version['number']} · {version['label']} [{case['id'][:6]}]"
        left, right = st.columns(2)
        a = left.selectbox("Left design", list(options), format_func=options.get, key="compare_left")
        b = right.selectbox("Right design", list(options), index=1, format_func=options.get, key="compare_right")
        if st.button("Compare designs"):
            st.session_state.comparison = copy.deepcopy({
                "left": spec if a == "current" else store.load(*refs[a]),
                "right": spec if b == "current" else store.load(*refs[b]),
                "left_name": options[a], "right_name": options[b],
            })
        comparison = st.session_state.get("comparison")
        if not comparison:
            return
        st.caption("Comparison is a snapshot. Preview edits are temporary and never change saved cases or the working drawing. Click Compare designs again to refresh.")
        columns = st.columns(2)
        for column, side in zip(columns, ("left", "right")):
            with column:
                st.markdown(f"**{comparison[side + '_name']}**")
                drawing = dict(comparison[side], animate=False)
                # Each preview has its own local editor state, never the main drawing bridge.
                components.html(build_html(drawing), height=510, scrolling=False)
        differences = compare_designs(comparison["left"], comparison["right"])
        if differences:
            st.caption(f"{len(differences)} differences (equipment matched by ID; connections by attachment endpoints).")
            table = pd.DataFrame(differences)
            st.dataframe(table, hide_index=True, use_container_width=True)
            st.download_button("Download comparison CSV", table.to_csv(index=False), "design_comparison.csv", "text/csv")
        else:
            st.success("The designs are identical.")
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        st.error(f"Comparison failed: {error}")
