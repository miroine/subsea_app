"""Connection service types shared by the viewer and Streamlit settings."""

CONNECTION_KINDS = {
    "": "Flowline / cable",
    "riser": "Riser",
    "jumper": "Jumper",
    "spool": "Spool",
}

RISER_STYLES = {
    "rigid": "Rigid - swept bend",
    "flex": "Flexible - catenary",
    "lazywave": "Flexible - lazy wave",
    "s_shape": "Flexible - S shape",
}

CONNECTION_TYPES = {
    "oil": {"label": "Oil", "fluid": "export", "color": "#00843D", "monoDash": ""},
    "gas": {"label": "Gas", "fluid": "gas", "color": "#D32F2F", "monoDash": "2 3"},
    "water_injection": {"label": "Water injection", "fluid": "water", "color": "#0077CC", "monoDash": "4 4"},
    "multiphase": {"label": "Multiphase", "fluid": "production", "color": "#7B2CBF", "monoDash": "8 3 2 3"},
    "service": {"label": "Service line", "lane": "S", "color": "#E87500", "dash": "9 3"},
    "umbilical_static": {"label": "Static umbilical", "lane": "U", "color": "#667085", "dash": "12 3 2 3"},
    "umbilical_dynamic": {"label": "Dynamic umbilical", "lane": "U", "color": "#E5B700", "dash": "5 3 1 3"},
    "gas_lift": {"label": "Gas lift", "fluid": "gaslift", "color": "#D32F2F", "dash": "10 3 2 3"},
    "chemical": {"label": "Chemical / MEG injection", "fluid": "chemical", "color": "#E87500", "dash": "5 2"},
    "export": {"label": "Export line", "fluid": "export", "color": "#00843D", "dash": "16 4"},
    "co2": {"label": "CO2", "fluid": "co2", "color": "#009FB7", "dash": "1 3"},
    "power": {"label": "Power cable", "fluid": "power", "color": "#8B4513", "dash": "6 2 1 2"},
}
