"""Bidirectional Streamlit drawing component."""
from pathlib import Path

import streamlit.components.v1 as components

editor = components.declare_component("subsea_editor", path=str(Path(__file__).parent / "component"))
