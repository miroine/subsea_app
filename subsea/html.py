"""Assemble the self-contained HTML page (engine + spec + catalogue).

Pure Python, no Streamlit import, so it can be tested and used standalone.
"""
from __future__ import annotations

import base64
import gzip
import json
from functools import lru_cache
from pathlib import Path

from .catalog import CATALOG, TAGS
from .connections import CONNECTION_KINDS, CONNECTION_TYPES, RISER_STYLES
from .equipment import DESIGN_FIELDS, TREE_TYPES, MAX_PORTS, furb_configuration
from .valves import VALVE_TYPES, MAX_INTERNAL_VALVES
from .riser_detail import DETAIL_SERVICES, blank_element_configuration, illustrated_riser_configuration

_STATIC = Path(__file__).parent / "static"


def _js_json(obj) -> str:
    # keep the payload safe inside an inline <script>
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")

@lru_cache(maxsize=1)
def _three_payload() -> str:
    return _js_json({key: base64.b64encode(gzip.compress(
        (_STATIC / "vendor" / filename).read_bytes(), mtime=0)).decode("ascii")
        for key, filename in (("core", "three.core.js"), ("module", "three.module.js"))})


def build_html(spec: dict | None = None, mode: str = "diagram", catalog: list | None = None) -> str:
    shell = (_STATIC / "shell.html").read_text(encoding="utf-8")
    engine = "\n".join((_STATIC / name).read_text(encoding="utf-8")
                       for name in ("riser_detail.js", "scene3d.js", "engine.js"))
    cat = CATALOG if catalog is None else catalog
    shell = shell.replace("/*__THREE_LIBRARY__*/{}", "{}" if mode == "catalog" else _three_payload())
    html = shell.replace("/*__ENGINE__*/", engine.replace("</script", "<\\/script"))
    html = html.replace("/*__SPEC__*/null", _js_json(spec or {}))
    html = html.replace("/*__CATALOG__*/[]", _js_json(cat))
    html = html.replace("/*__TAGS__*/{}", _js_json(TAGS))
    html = html.replace("/*__CONNECTION_TYPES__*/{}", _js_json(CONNECTION_TYPES))
    html = html.replace("/*__EQUIPMENT_OPTIONS__*/{}", _js_json({
        "designFields": DESIGN_FIELDS, "treeTypes": TREE_TYPES, "maxPorts": MAX_PORTS,
        "riserStyles": RISER_STYLES,
        "connectionKinds": CONNECTION_KINDS,
        "furb": furb_configuration(),
        "valveTypes": VALVE_TYPES, "maxInternalValves": MAX_INTERNAL_VALVES,
        "riserDetail": {"services": DETAIL_SERVICES, "reference": illustrated_riser_configuration(),
                        "blank": blank_element_configuration()},
    }))
    html = html.replace("__MODE__", mode)
    html = html.replace("__BAR_DISPLAY__", "display:none" if mode == "catalog" else "")
    return html
