/* Subsea layout engine – pure SVG, no dependencies.
 * Public API (window.Subsea):
 *   build(spec)      -> {defs, content, meta}     (string based, DOM free)
 *   mount(el, spec, catalog)                      (interactive viewer)
 *   mountCatalog(el, catalog, opts)               (symbol gallery)
 *   ids()            -> {node:[], link:[], host:[]}
 */
(function (root) {
  'use strict';

  /* ------------------------------------------------------------------ theme */
  const SANS = "Arial,'Helvetica Neue',Helvetica,sans-serif";
  const SERIF = "Georgia,'Times New Roman',serif";
  const THEMES = {
    consulting: { label: 'Consulting – deep navy', layout: 'slide', red: '#2251FF', green: '#00A9F4', yellow: '#00B3A4', ink: '#051C2C', mute: '#5B6B7B', blue: '#1F40E6', zone: '#8A99A8', umb: '#6B7F99', paper: '#FFFFFF', soft: '#E6ECF3', font: SANS, serif: SERIF, fs: 10, dash: {}, fluids: { production: '#2251FF', water: '#0D8FE0', gas: '#00B3A4', gaslift: '#6B4EFF', export: '#051C2C', chemical: '#7C8DA6', co2: '#D6336C', power: '#E5A100' } },
    mono: { label: 'Engineering – monochrome', layout: 'sheet', red: '#111111', green: '#111111', yellow: '#111111', ink: '#111111', mute: '#555555', blue: '#111111', zone: '#555555', paper: '#FFFFFF', soft: '#E4E4E4', font: SANS, serif: SERIF, fs: 10, dash: { S: '9 3', U: '12 3 2 3' }, fluids: {}, fluidDash: { water: '4 4', gas: '1.5 3', gaslift: '10 3 2 3', export: '16 4', chemical: '5 2', co2: '1 3', power: '6 2 1 2' } },
    blueprint: { label: 'Blueprint', layout: 'sheet', red: '#6FD0FF', green: '#9FE3B4', yellow: '#FFD166', ink: '#EAF3FB', mute: '#9DB7CE', blue: '#9DB7FF', zone: '#7FA0BD', umb: '#B9C6FF', paper: '#0B2A4A', soft: '#143C66', font: SANS, serif: SERIF, fs: 10, dash: {}, fluids: { production: '#6FD0FF', water: '#4D9BFF', gas: '#7BE0C3', gaslift: '#C3A6FF', export: '#EAF3FB', chemical: '#9DB7CE', co2: '#FF8FB1', power: '#FFD166' } },
    classic: { label: 'Classic colour', layout: 'sheet', red: '#E4002B', green: '#78BE20', yellow: '#F2B100', ink: '#1F2328', mute: '#6E7378', blue: '#1F4FB4', zone: '#8A8F94', paper: '#FFFFFF', soft: '#E8E8E8', font: SANS, serif: SERIF, fs: 10, dash: {}, fluids: { production: '#E4002B', water: '#1F78D1', gas: '#F28C00', gaslift: '#8E44AD', export: '#1F2328', chemical: '#7F8C8D', co2: '#D6336C', power: '#F2B100' } },
  };
  const BASE = THEMES.consulting;
  let T = Object.assign({}, BASE);

  /* ------------------------------------------------------------- primitives */
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const A = (o) => Object.keys(o).filter((k) => o[k] !== undefined && o[k] !== null)
    .map((k) => `${k}="${esc(o[k])}"`).join(' ');
  const num = (v, d) => (v === undefined || v === null || v === '' || isNaN(+v) ? d : +v);

  let MIRROR = false, CUR_SPEC = {};
  let INTERNAL_DRAW = null;
  function internalPipeAttributes(options) {
    if (!INTERNAL_DRAW || !options.flow) return {};
    const lane = options.flow;
    INTERNAL_DRAW.counts[lane] = (INTERNAL_DRAW.counts[lane] || 0) + 1;
    const id = options.pipeId || `${lane}-${INTERNAL_DRAW.counts[lane]}`;
    INTERNAL_DRAW.pipes.push({ id, lane });
    return { 'data-internal-pipe': id, 'data-pipe-lane': lane };
  }
  let CUR_FLOW = { P: { mode: 'fwd', d: 1.6 }, S: { mode: 'fwd', d: 3.2 }, U: { mode: 'fwd', d: 4.5 } };
  const FLOWD = { production: 1.5, water: 2, gas: 1, gaslift: 1.2, export: 1.4, chemical: 3, co2: 1.8, power: 3.5 };
  function flowOverlay(tag, attrs, lane, w) {
    const f = CUR_FLOW[lane];
    if (!f || f.mode === 'none') return '';
    return `<${tag} ${A(attrs)} class="flow${f.mode === 'rev' ? ' rev' : ''}" stroke="${T.paper}" stroke-width="${Math.max(1, (w || 2) * 0.5).toFixed(2)}" style="--d:${f.d}s"/>`;
  }
  const line = (x1, y1, x2, y2, o = {}) => `<line ${A({ x1, y1, x2, y2, stroke: o.c || T.ink, 'stroke-width': o.w || 1.2, 'stroke-dasharray': o.dash, 'stroke-linecap': o.cap, 'data-flow-lane': o.flow || o.pipeLane,
    ...(x1 !== x2 || y1 !== y2 ? internalPipeAttributes(o) : {}) })}/>`
    + (o.flow ? flowOverlay('line', { x1, y1, x2, y2 }, o.flow, o.w || 1.2) : '');
  const rect = (x, y, w, h, o = {}) => `<rect ${A({ x, y, width: w, height: h, rx: o.rx, fill: o.fill || 'none', stroke: o.c === undefined ? T.ink : o.c, 'stroke-width': o.w || 1.2, 'stroke-dasharray': o.dash })}/>`;
  const circ = (x, y, r, o = {}) => `<circle ${A({ cx: x, cy: y, r, fill: o.fill || 'none', stroke: o.c === undefined ? T.ink : o.c, 'stroke-width': o.w || 1.2, 'stroke-dasharray': o.dash })}/>`;
  const path = (d, o = {}) => `<path ${A({ d, fill: o.fill || 'none', stroke: o.c === undefined ? T.ink : o.c, 'stroke-width': o.w || 1.2, 'stroke-dasharray': o.dash, 'stroke-linecap': o.cap || 'round', 'stroke-linejoin': 'round', 'data-flow-lane': o.flow || o.pipeLane, ...internalPipeAttributes(o) })}/>`
    + (o.flow ? flowOverlay('path', { d }, o.flow, o.w || 1.2) : '');
  const grp = (inner, tf) => `<g${tf ? ` transform="${tf}"` : ''}>${inner}</g>`;
  const internalPipeGuide = (x1, y1, x2, y2, lane = 'P') => INTERNAL_DRAW
    ? `<path d="M${x1} ${y1}L${x2} ${y2}" fill="none" stroke="none" pointer-events="none" ${A(internalPipeAttributes({ flow: lane }))}/>` : '';

  function txt(x, y, s, o = {}) {
    const lines = String(s).split('\n');
    const fs = o.size || T.fs;
    const lh = fs * 1.2;
    const yy = o.va === 'bottom' ? y - (lines.length - 1) * lh : y;
    const rotT = o.rot ? `rotate(${o.rot} ${x} ${yy})` : '';
    const tfm = MIRROR ? `translate(${2 * x} 0) scale(-1 1) ${rotT}` : rotT;
    const rot = tfm ? ` transform="${tfm}"` : '';
    const anc = o.anchor;
    const tsp = lines.map((l, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : lh}">${esc(l)}</tspan>`).join('');
    return `<text x="${x}" y="${yy}" font-size="${fs}" font-weight="${o.bold ? 600 : 400}" fill="${o.c || T.ink}" text-anchor="${anc || 'middle'}"${o.italic ? ' font-style="italic"' : ''}${rot} ${o.font ? ` font-family="${esc(o.font)}"` : ''} style="paint-order:stroke;stroke:${T.paper};stroke-width:${o.halo === false ? 0 : 3}px;stroke-linejoin:round">${tsp}</text>`;
  }

  function elementLabel(x, y, text, item, options = {}) {
    const style = item.labelStyle || {};
    const fonts = { sans: SANS, serif: SERIF, mono: "'Courier New',monospace" };
    const polished = CUR_SPEC.professionalAppearance === true;
    const scale = polished ? componentScale((CUR_SPEC.overrides || {})[item.id] || {}) : 1;
    const labelOptions = {
      ...options, size: style.size || (polished ? Math.max(9, Math.min(12, options.size || 10)) / scale : options.size),
      font: fonts[style.font] || (polished ? SANS : options.font),
      c: polished ? T.ink : options.c,
      anchor: style.anchor && style.anchor !== 'auto' ? style.anchor : options.anchor,
      bold: style.weight && style.weight !== 'auto' ? style.weight === 'bold' : polished || options.bold,
      italic: style.italic === undefined ? options.italic : style.italic,
      rot: num(options.rot, 0) + num(style.rotation, 0),
    };
    const xx = x + num(style.dx, 0), yy = y + num(style.dy, 0);
    let svg = txt(xx, yy, text, labelOptions);
    if (polished && item.tag && !SENSORS.has(item.type) && !LINK[item.type]) {
      const labelSize = labelOptions.size || T.fs;
      const lines = String(text).split('\n').length;
      const tagSize = 7.5 / scale;
      const tagY = yy - (options.va === 'bottom' ? (lines - 1) * labelSize * 1.2 : 0) - tagSize - 3 / scale;
      svg += `<g class="equipment-tag">${txt(xx, tagY, item.tag,
        { size: tagSize, font: SANS, c: T.mute, anchor: labelOptions.anchor, rot: labelOptions.rot })}</g>`;
    }
    return `<g class="element-label">${svg}</g>`;
  }

  /* wrap a string into lines of roughly `max` characters */
  function wrap(s, max) {
    const out = []; let cur = '';
    String(s).split(' ').forEach((w) => {
      if ((cur + ' ' + w).trim().length > max && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
    });
    if (cur) out.push(cur);
    return out.join('\n');
  }

  /* ---------------------------------------------------------------- symbols */
  /* ISO 10628 style valves, flow left->right, actuator pointing up (rot 0). */
  const springActuator = (h, fc) => rect(-6, -h - 14, 12, 8, { fill: T.paper, w: 1 })
    + path(`M-4 ${-h - 10}l1.6 -2 l1.6 4 l1.6 -4 l1.6 4 l1.6 -4 l1.6 2`, { w: 0.8 })
    + (fc ? txt(9, -h - 8, fc, { size: 6, anchor: 'start', halo: false, c: T.mute }) : '');
  function valve(x, y, o = {}) {
    const s = o.s || 6.5, h = s * 0.85, kind = o.kind || 'gate';
    const f = o.closed ? T.ink : T.paper;
    let g = '';
    const bow = (fill) => path(`M${-s} ${-h}L0 0L${-s} ${h}Z M${s} ${-h}L0 0L${s} ${h}Z`, { fill, w: 1.1 });
    const stem = (len) => line(0, 0, 0, -h - len, { w: 0.9 });
    const rov = () => stem(4) + line(-3, -h - 4, 3, -h - 4, { w: 1.2 });
    switch (kind) {
      case 'ball': g = bow(f) + circ(0, 0, 2.8, { fill: T.ink, w: 0.8 }) + rov(); break;
      case 'check': g = path(`M${-s} ${-h}L${s * 0.6} 0L${-s} ${h}Z`, { fill: f, w: 1.1 }) + line(s * 0.6, -h, s * 0.6, h, { w: 1.8 }); break;
      case 'choke': g = bow(T.paper) + path(`M0 0L${s} ${-h}L${s} ${h}Z`, { fill: T.ink, w: 0.6 }) + stem(5)
        + line(-s - 1, h + 3, s + 1, -h - 3, { w: 0.9 }) + path(`M${s + 1} ${-h - 3}l-4 0.5 l2.5 2.5Z`, { fill: T.ink, w: 0.6 }); break;
      case 'esdv': g = bow(f) + stem(5) + springActuator(h - 0.5, 'FC'); break;
      case 'ssiv': g = bow(f) + stem(5) + springActuator(h - 0.5, 'FC') + rect(-s - 3, -h - 16, 2 * s + 6, 2 * h + 19, { dash: '2 2', w: 0.7 }); break;
      case 'control': g = bow(f) + stem(3) + path(`M-5 ${-h - 3}a5 5 0 0 1 10 0Z`, { fill: T.paper, w: 1 }); break;
      case 'psv': g = line(0, 0, 0, -8) + path('M-6 -8H6L0 -18Z', { fill: f, w: 1.1 })
        + path('M0 -18V-22L-4 -24L4 -27L-4 -30L4 -33M0 -18H12V-26', { w: 1.1 }); break;
      case 'xov': g = bow(f) + rov() + line(-3, 3, 3, -3, { w: 0.9 }) + line(-3, -3, 3, 3, { w: 0.9 }); break;
      default: g = bow(f) + rov();
    }
    const transform = `translate(${x} ${y})${o.rot ? ` rotate(${o.rot})` : ''}`;
    if (INTERNAL_DRAW) {
      INTERNAL_DRAW.valves += 1;
      return `<g class="default-internal-valve" data-default-valve="valve-${INTERNAL_DRAW.valves}" data-valve-kind="${esc(kind)}" data-valve-closed="${!!o.closed}" transform="${transform}">${g}</g>`;
    }
    return grp(g, transform);
  }

  /* ISO flange / connector: two parallel heavy ticks */
  function conn(x, y, rot = 0, big = false) {
    const k = big ? 1.35 : 1;
    return grp(line(-1.9, -5.5 * k, -1.9, 5.5 * k, { w: 1.6, cap: 'butt' }) + line(1.9, -5.5 * k, 1.9, 5.5 * k, { w: 1.6, cap: 'butt' }),
      `translate(${x} ${y})${rot ? ` rotate(${rot})` : ''}`);
  }

  const hatch = (x, y, w, h, o = {}) => rect(x, y, w, h, Object.assign({ fill: 'url(#hatch)' }, o));
  const hub = (x, y) => circ(x, y, 3.6, { fill: T.paper, w: 1.2 });

  /* ------------------------------------------------------- lane line styles */
  const LANE_W = { P: 2.4, S: 1.8, U: 1.5 };
  let CUR_P = { c: null, dash: undefined };
  const PC = () => CUR_P.c || T.red;
  const FLUIDS = { production: 'Production', water: 'Water injection', gas: 'Gas', gaslift: 'Gas lift', export: 'Export', chemical: 'Chemical / MEG', co2: 'CO2', power: 'Power cable' };
  let CONNECTION_TYPES = {};
  const FLUID_TYPES = { production: 'multiphase', gas: 'gas', water: 'water_injection', export: 'oil', gaslift: 'gas_lift', chemical: 'chemical', co2: 'co2', power: 'power' };
  const serviceLane = (service) => service.lane || (service.fluid === 'chemical' ? 'S' : 'P');
  let EQUIPMENT_OPTIONS = { designFields: {}, treeTypes: {}, maxPorts: 24 };
  function internalValveErrors(item, pipeIds) {
    if (item.internalValves === undefined) return [];
    if (!Array.isArray(item.internalValves) || item.internalValves.length > EQUIPMENT_OPTIONS.maxInternalValves)
      return [`Use a list of at most ${EQUIPMENT_OPTIONS.maxInternalValves} internal valves.`];
    const errors = [], used = new Set();
    for (const entry of item.internalValves) {
      if (!entry || typeof entry !== 'object' || Array.isArray(entry)) { errors.push('Each valve must be an object.'); continue; }
      if (typeof entry.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(entry.id) || used.has(entry.id))
        errors.push('Valve IDs must be unique and use letters, numbers, underscores or hyphens.');
      used.add(entry.id);
      if (!pipeIds.has(entry.pipe)) errors.push(`Valve ${entry.id}: internal pipe ${entry.pipe || '(blank)'} is not available. Review its pipe after changing the equipment topology.`);
      const kind = entry.kind === undefined ? 'gate' : entry.kind;
      if (typeof kind !== 'string' || !Object.hasOwn(EQUIPMENT_OPTIONS.valveTypes, kind)) errors.push(`Valve ${entry.id}: unknown type.`);
      const position = entry.position === undefined ? 50 : entry.position;
      if (typeof position !== 'number' || !Number.isFinite(position) || position < 0 || position > 100)
        errors.push(`Valve ${entry.id}: position must be 0 to 100 percent.`);
      if (entry.closed !== undefined && typeof entry.closed !== 'boolean') errors.push(`Valve ${entry.id}: closed must be true or false.`);
      for (const field of ['tag', 'label', 'provider', 'rating'])
        if (entry[field] !== undefined && typeof entry[field] !== 'string') errors.push(`Valve ${entry.id}: ${field} must be text.`);
    }
    return errors;
  }
  function serviceStyle(type = { color: T.green }) {
    return {
      c: CUR_SPEC.themeName === 'mono' ? '#111111' : type.color,
      dash: CUR_SPEC.themeName === 'mono' ? (type.monoDash === undefined ? type.dash : type.monoDash) : type.dash,
    };
  }
  function assignedPortService(item, portId) {
    if (item?.riserDetail) {
      const hub = item.riserDetail.hubs.find((hub) => hub.id === portId);
      if (hub) return root.SubseaRiserDetail.services()[hub.service].connectionType;
    }
    const assigned = item?.portOverrides?.[portId]?.connectionType;
    if (assigned) return assigned;
    const services = new Set((item?.internalRoutes || [])
      .filter((route) => route.from === portId || route.to === portId).map((route) => route.connectionType));
    if (item?.bundleServiceInlet && portId === 'U-left') {
      return services.size === 1 && ['umbilical_static', 'umbilical_dynamic'].includes([...services][0])
        ? [...services][0] : 'umbilical_static';
    }
    return services.size === 1 ? [...services][0] : '';
  }
  function connectionAppearance(connection, spec) {
    let portType = '';
    for (const end of ['from', 'to']) {
      const item = [spec, ...(spec.branches || [])].flatMap((tr) => tr.chain || []).find((it) => it.id === connection[end]);
      portType = portType || assignedPortService(item, connection[end + 'Port']);
    }
    const type = CONNECTION_TYPES[connection.connectionType || portType];
    if (type) return { label: type.label, ...serviceStyle(type) };
    const train = [spec, ...(spec.branches || [])].find((train) =>
      (train.host && train.host.id === connection.from) || (train.chain || []).some((item) => item.id === connection.from)) || spec;
    if (connection.lane === 'S') return { label: 'Service line', ...serviceStyle(CONNECTION_TYPES.service) };
    if (connection.lane === 'U') return { label: 'Static umbilical', ...serviceStyle(CONNECTION_TYPES.umbilical_static) };
    return { label: FLUIDS[train.fluid || 'production'] || 'Production', ...fluidStyle(train.fluid || 'production') };
  }
  function fluidStyle(f) {
    const type = CONNECTION_TYPES[FLUID_TYPES[f]];
    const style = type ? serviceStyle(type) : { c: (T.fluids && T.fluids[f]) || T.red, dash: T.fluidDash && T.fluidDash[f] };
    const custom = CUR_SPEC.theme || {};
    if (custom.fluids && custom.fluids[f]) style.c = custom.fluids[f];
    else if (f === 'production' && custom.red) style.c = custom.red;
    return style;
  }
  const laneColor = (l) => {
    if (l === 'P') return PC();
    const custom = CUR_SPEC.theme || {};
    return l === 'U' ? (custom.umb || custom.yellow || serviceStyle(CONNECTION_TYPES.umbilical_static).c)
      : (custom.green || serviceStyle(CONNECTION_TYPES.service).c);
  };
  function seg(c, lane, x1, x2, o = {}) {
    const y = c.L[lane];
    if (x2 <= x1) return '';
    return line(x1, y, x2, y, { c: o.c || laneColor(lane), w: o.w || LANE_W[lane], dash: o.dash || (lane === 'P' ? CUR_P.dash : T.dash && T.dash[lane]), flow: lane });
  }

  /* ============================================================ NODE DEFS === */
  const NODE = {};
  const DESC = {}; // filled by catalog

  /* helper for in-line valve-like nodes on P */
  function inlineNode(w, fn) {
    return { uses: 'P', w: () => w, draw: (c, n) => { const y = c.L.P, x = c.x, cx = x + w / 2; return seg(c, 'P', x, x + w) + fn(c, n, x, y, cx); } };
  }
  const tag = (cx, y, s, n) => (n.label !== undefined ? n.label : s) ? elementLabel(cx, y, n.label !== undefined ? n.label : s, n, { size: 8.5, c: T.mute }) : '';

  ['gate:valve_gate:Gate', 'ball:valve_ball:Ball', 'check:valve_check:Check', 'choke:choke:Choke', 'esdv:esdv:ESDV', 'ssiv:ssiv:SSIV', 'control:valve_control:CV', 'xov:valve_xov:XOV'].forEach((s) => {
    const [kind, id, lab] = s.split(':');
    NODE[id] = inlineNode(40, (c, n, x, y, cx) => valve(cx, y, { kind, closed: n.closed }) + conn(x + 4, y) + conn(x + 36, y) + tag(cx, y - (kind === 'esdv' || kind === 'ssiv' ? 28 : 18), '', n));
  });

  NODE.hub_conn = inlineNode(26, (c, n, x, y, cx) => conn(cx, y, 0, true) + tag(cx, y - 14, '', n));

  NODE.spool = {
    uses: 'P', w: (n) => num(n.w, 62),
    draw(c, n) {
      const { x } = c, y = c.L.P, w = NODE.spool.w(n);
      const lab = n.label !== undefined ? n.label : ('Spool' + (n.size ? `, ${n.size}` : ''));
      return seg(c, 'P', x, x + w) + hatch(x + 11, y - 5, w - 22, 10, { w: 1 }) + conn(x + 7, y) + conn(x + w - 7, y)
        + (lab ? elementLabel(x + w / 2, y - 11, lab, n, { size: 8.5, bold: true }) : '');
    },
  };

  NODE.jumper_rigid = {
    uses: 'P', w: () => 84,
    draw(c, n) {
      const { x } = c, y = c.L.P;
      return seg(c, 'P', x, x + 10) + seg(c, 'P', x + 74, x + 84) + conn(x + 10, y) + conn(x + 74, y)
        + path(`M${x + 10} ${y}H${x + 20}V${y - 22}H${x + 34}V${y}H${x + 50}V${y - 22}H${x + 64}V${y}H${x + 74}`, { c: PC(), w: 2.2, flow: 'P' })
        + elementLabel(x + 42, y - 30, n.label !== undefined ? n.label : 'Rigid jumper', n, { size: 8.5, bold: true });
    },
  };
  NODE.jumper_flex = {
    uses: 'P', w: () => 84,
    draw(c, n) {
      const { x } = c, y = c.L.P;
      return seg(c, 'P', x, x + 10) + seg(c, 'P', x + 74, x + 84) + conn(x + 10, y) + conn(x + 74, y)
        + path(`M${x + 10} ${y}C${x + 18} ${y - 34} ${x + 36} ${y - 34} ${x + 42} ${y - 12}S${x + 66} ${y + 10} ${x + 74} ${y}`, { c: PC(), w: 2.2, dash: '9 3', flow: 'P' })
        + elementLabel(x + 42, y - 30, n.label !== undefined ? n.label : 'Flexible jumper', n, { size: 8.5, bold: true });
    },
  };

  NODE.plem = {
    uses: 'P', w: (n) => num(n.w, 140),
    draw(c, n) {
      const { x } = c, y = c.L.P, w = NODE.plem.w(n);
      const blue = T.ink;
      return rect(x, y - 36, w, 72, { dash: '3 3', w: 1 })
        + seg(c, 'P', x, x + w)
        + conn(x + 8, y) + conn(x + w - 8, y)
        + rect(x + 20, y - 24, 9, 5, { fill: blue, c: blue }) + rect(x + 20, y + 19, 9, 5, { fill: blue, c: blue })
        + line(x + 24.5, y - 19, x + 24.5, y - 5, { w: 1 }) + line(x + 24.5, y + 5, x + 24.5, y + 19, { w: 1 })
        + valve(x + 24.5, y, { kind: 'gate', rot: 90, s: 5.5 })
        + valve(x + w * 0.62, y, { kind: n.valve || 'gate' })
        + txt(x + w * 0.5, y - 12, `${n.sizeIn || '10"'} ID`, { size: 8.5, bold: true })
        + txt(x + w * 0.28, y + 24, `${n.sizeOut || '8"'} ID`, { size: 8.5, bold: true })
        + elementLabel(x + w / 2, y - 42, n.label !== undefined ? n.label : 'PLEM', n, { size: 11, bold: true });
    },
  };

  NODE.plet = {
    uses: 'P', w: () => 76,
    draw(c, n) {
      const { x } = c, lanes = n.pletPorts || 'PSU';
      const y = c.L[lanes[0]];
      const bottom = lanes === 'PSU' ? Math.max(y + 22, c.L.S + 12, c.L.U + 18) : y + 22;
      const ports = equipmentPortLayout(c, n, 76, 'P');
      const piping = [...lanes].map((lane) =>
        ['left', 'right'].map((side) => {
          const port = ports.find((port) => port.id === `${lane}-${side}`);
          if (!port) return '';
          const style = port.connectionType ? serviceStyle(CONNECTION_TYPES[port.connectionType])
            : { c: laneColor(port.lane), dash: port.lane === 'P' ? CUR_P.dash : T.dash && T.dash[port.lane] };
          return `<g class="plet-port-section" data-section="${port.id}">`
            + line(side === 'left' ? x : x + 36, c.L[lane], side === 'left' ? x + 36 : x + 72,
              c.L[lane], { ...style, w: LANE_W[port.lane], flow: port.lane })
            + (port.standard ? conn(port.x, port.y) : '') + '</g>';
        }).join('')).join('');
      return '<g class="plet-frame">' + rect(x + 4, y - 22, 68, bottom - y + 22, { dash: '3 3', w: 1 }) + '</g>'
        + piping + (lanes === 'U' ? hub(x + 42, y) : valve(x + 42, y))
        + rect(x + 10, bottom - 7, 56, 5, { fill: T.soft, w: 0.8 })
        + elementLabel(x + 38, y - 28, n.label !== undefined ? n.label : 'PLET', n, { size: 10.5, bold: true });
    },
  };

  NODE.ilt = {
    uses: 'P', w: () => 44,
    draw(c, n) {
      const { x } = c, y = c.L.P, cx = x + 22;
      return seg(c, 'P', x, x + 44) + seg(c, 'P', cx, cx, {}) + line(cx, y, cx, y - 26, { c: PC(), w: 2.2, flow: 'P' }) + valve(cx, y - 14, { rot: 90, s: 5 }) + hub(cx, y - 29) + conn(cx, y - 26, 90)
        + elementLabel(cx, y - 42, n.label !== undefined ? n.label : 'ILT', n, { size: 9, bold: true });
    },
  };
  NODE.ils = {
    uses: 'P', w: () => 80,
    draw(c, n) {
      const { x } = c, y = c.L.P;
      return rect(x + 6, y - 16, 68, 32, { dash: '4 2', w: 1 }) + seg(c, 'P', x, x + 80) + conn(x + 8, y) + valve(x + 30, y) + valve(x + 52, y) + conn(x + 72, y)
        + hatch(x + 8, y + 20, 64, 4, { w: 0.8 }) + elementLabel(x + 40, y - 22, n.label !== undefined ? n.label : 'ILS', n, { size: 9.5, bold: true });
    },
  };
  NODE.fta = {
    uses: 'P', w: () => 72,
    draw(c, n) {
      const { x } = c, y = c.L.P;
      return rect(x + 18, y - 14, 48, 28, { dash: '3 3', w: 1 }) + seg(c, 'P', x, x + 72) + conn(x + 12, y) + valve(x + 42, y) + hub(x + 66, y)
        + elementLabel(x + 42, y - 20, n.label !== undefined ? n.label : 'FTA', n, { size: 9.5, bold: true });
    },
  };

  /* HIPPS: dashed box, two valves in series, three PTs */
  function hippsSvg(c, x, y, w, label, item = {}) {
    return rect(x, y - 24, w, 48, { dash: '3 3', w: 1 }) + seg(c, 'P', x, x + w)
      + valve(x + w * 0.28, y, { kind: 'esdv' }) + valve(x + w * 0.72, y, { kind: 'esdv' })
      + [0.18, 0.5, 0.82].map((f) => line(x + w * f, y, x + w * f, y + 14, { w: 0.9 }) + circ(x + w * f, y + 17, 3, { fill: T.paper, w: 0.9 })).join('')
      + (label === '' ? '' : elementLabel(x + w / 2, y - 29, label || 'HIPPS', item, { size: 9.5, bold: true }));
  }
  NODE.hipps = { uses: 'P', w: () => 96, draw: (c, n) => hippsSvg(c, c.x + 2, c.L.P, 92, n.label, n) };

  /* ---- manifold & template share the header/branch geometry ---- */
  const COLW = 50, HW = 60, PAD = 10;
  function headerStructure(c, n, mode) {
    const { x, L } = c, y = L.P;
    const count = num(n[mode === 'template' ? 'wells' : 'slots'], 4);
    const cols = Math.max(1, Math.ceil(count / 2));
    const hipps = mode === 'template' && n.hipps !== false;
    const hw = hipps ? HW : 0;
    const w = PAD + hw + cols * COLW + PAD + 4;
    const lowest = c.act.U ? L.U : c.act.S ? L.S : y;
    const top = y - 48, bot = lowest + 26;
    let s = rect(x, top, w, bot - top, { dash: '3 3', w: 1 });
    // lanes inside
    s += seg(c, 'P', x, x + w, { w: mode === 'manifold' ? 3 : 2.2 });
    ['S', 'U'].forEach((l) => { if (c.act[l]) s += seg(c, l, x, x + w) + conn(x, L[l]) + conn(x + w, L[l]); });
    s += conn(x, y) + conn(x + w, y);
    if (hipps) s += `<g class="template-hipps">${hippsSvg(c, x + PAD, y, hw - 4, n.hippsLabel)}</g>`;
    const first = num(n.wellStart, 1);
    const wellTop = y - 92, wellBot = bot + 18;
    const wdash = '3 3';
    for (let i = 0; i < cols; i++) {
      const cx = x + PAD + hw + (i + 0.5) * COLW;
      [0, 1].forEach((row) => {
        const k = i * 2 + row;
        if (k >= count) return;
        const up = row === 0;
        const ey = up ? wellTop + 22 : wellBot;
        s += line(cx, y, cx, ey, { c: PC(), w: 2.2, flow: 'P' });
        s += valve(cx, up ? y - 30 : bot - 8, { rot: 90, s: 5.5 });
        if (mode === 'template') {
          s += rect(cx - 20, up ? wellTop : wellBot, 40, 22, { dash: wdash, w: 1 });
          s += txt(cx, (up ? wellTop : wellBot) + (n.treeType ? 32 : 14.5), `Well ${first + k}`, { size: 9.5 });
          if (n.treeType && NODE[n.treeType]) {
            const treeY = (up ? wellTop : wellBot) + 21;
            const tree = genShape(GEN[n.treeType], c, { label: '' }, -31, 0, 62);
            s += `<g class="template-tree" data-tree-type="${esc(n.treeType)}" transform="translate(${cx} ${treeY}) scale(.32)">${tree}</g>`;
            s += txt(cx, (up ? wellTop : wellBot) + 43, n.treeType.toUpperCase(), { size: 7, c: T.mute });
          } else if (n.trees) s += txt(cx + 25, (up ? wellTop : wellBot) + 14.5, n.trees, { size: 7, c: T.mute, anchor: 'start' });
        } else {
          s += hub(cx, ey);
        }
      });
      if (i < cols - 1) s += valve(cx + COLW / 2, y, { s: 5.5 });
    }
    s += valve(x + w - 12, y, { s: 5.5 });
    const lab = n.label !== undefined ? n.label : (mode === 'template' ? 'Template' : 'Manifold');
    s += elementLabel(x + w / 2, (mode === 'template' ? wellTop : top) - 12, lab, n, { size: mode === 'template' ? 14 : 11, bold: true, va: 'bottom' });
    return s;
  }
  NODE.template = { uses: 'PSU', w: (n) => PAD + (n.hipps === false ? 0 : HW) + Math.max(1, Math.ceil(num(n.wells, 4) / 2)) * COLW + PAD + 4, draw: (c, n) => headerStructure(c, n, 'template') };
  NODE.manifold = { uses: 'P', w: (n) => PAD + Math.ceil(num(n.slots, 4) / 2) * COLW + PAD + 4, draw: (c, n) => headerStructure(c, n, 'manifold') };

  NODE.satellite_well = {
    uses: 'P', w: () => 76,
    draw(c, n) {
      const { x } = c, y = c.L.P, cx = x + 38;
      return seg(c, 'P', x, x + 76) + conn(x + 4, y) + conn(x + 72, y) + line(cx, y, cx, y - 40, { c: PC(), w: 2.2, flow: 'P' }) + valve(cx, y - 22, { rot: 90, s: 5.5 })
        + rect(cx - 20, y - 62, 40, 22, { dash: '3 3', w: 1 }) + elementLabel(cx, y - 47.5, n.label !== undefined ? n.label : 'Well', n, { size: 9.5 });
    },
  };

  function riserFrameBottom(c, item, width, minimum) {
    return Math.max(minimum, ...equipmentPortLayout(c, item, width, 'P')
      .filter((port) => port.custom).map((port) => port.y + 16));
  }

  function riserAuxiliaryLines(c, item, width) {
    const ports = equipmentPortLayout(c, item, width, 'P');
    return [['S', item.servicePorts], ['U', item.umbilicalPorts]]
      .filter(([, enabled]) => enabled).map(([lane]) => {
        const port = ports.find((port) => port.id === `${lane}-left` || port.id === `${lane}-right`);
        return port ? line(c.x + 10, port.y, c.x + width - 10, port.y,
          { c: laneColor(lane), w: LANE_W[lane], dash: T.dash && T.dash[lane], flow: lane }) : '';
      }).join('');
  }

  function riserHubCounts(item) {
    if (item.riserPorts) return item.riserPorts;
    const counts = Object.fromEntries([['P', true], ['S', item.servicePorts], ['U', item.umbilicalPorts]]
      .map(([lane, enabled]) => [lane, { inlets: enabled ? 1 : 0, outlets: enabled ? 1 : 0 }]));
    const config = item.portConfig;
    if (config) for (const side of ['inlets', 'outlets']) {
      counts[config.lane][side] = config[side]
        + (config.mode === 'additional' ? Math.max(counts[config.lane][side], config[side] > 0 ? 1 : 0) : 0);
    }
    return counts;
  }

  function internalRoutingErrors(item, ports) {
    if (!Array.isArray(item.internalRoutes) || item.internalRoutes.length > 144) return ['Use at most 144 internal routes.'];
    const ids = new Set(ports.map((port) => port.id)), routes = new Map(), errors = [];
    if (item.bundleServiceInlet) {
      if (!ids.has('U-left') || !ids.has('S-right') || ports.find((port) => port.id === 'U-left').lane !== 'U') {
        errors.push('Bundled inlet requires U-compatible U-left and S-right chemical/service ports.');
      }
      ids.add('S-left');
    }
    for (const route of item.internalRoutes) {
      if (!route || typeof route !== 'object' || typeof route.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(route.id)
        || routes.has(route.id) || typeof route.from !== 'string' || typeof route.to !== 'string'
        || !CONNECTION_TYPES[route.connectionType]) {
        errors.push('Each route needs a unique ID, From, To and valid fluid/service.'); continue;
      }
      routes.set(route.id, route);
    }
    if (errors.length) return errors;
    for (const route of routes.values()) {
      if (!ids.has(route.to)) errors.push(`Route ${route.id}: missing outlet ${route.to}.`);
      if (route.from.startsWith('@')) {
        const trunk = routes.get(route.from.slice(1));
        if (!trunk || trunk === route || !ids.has(trunk.from) || !ids.has(trunk.to)) {
          errors.push(`Route ${route.id}: junction must reference a direct port-to-port route.`);
        }
      } else if (!ids.has(route.from)) errors.push(`Route ${route.id}: missing inlet ${route.from}.`);
      if (route.from === route.to) errors.push(`Route ${route.id}: endpoints must differ.`);
    }
    return errors;
  }

  function riserInternalPiping(c, item, width, auxiliaryOnly = false) {
    const ports = equipmentPortLayout(c, item, width, 'P'), byId = new Map(ports.map((port) => [port.id, port]));
    const middle = c.x + width / 2;
    if (item.bundleServiceInlet && byId.has('U-left')) {
      byId.set('S-left', { x: middle, y: byId.get('U-left').y, bundled: true });
    }
    const routes = item.internalRoutes === undefined ? (auxiliaryOnly ? ['S', 'U'] : ['P', 'S', 'U']).flatMap((lane) =>
      byId.has(`${lane}-left`) && byId.has(`${lane}-right`)
        ? [{ id: lane, from: `${lane}-left`, to: `${lane}-right`,
          connectionType: lane === 'S' ? 'chemical' : lane === 'U' ? 'umbilical_static' : 'multiphase' }] : [])
      : item.internalRoutes;
    const errors = internalRoutingErrors({ ...item, internalRoutes: routes }, ports);
    if (errors.length) throw new Error(`${item.id}: ${errors.join(' ')}`);
    const bundleStyle = serviceStyle(CONNECTION_TYPES[byId.get('U-left')?.connectionType] || CONNECTION_TYPES.umbilical_static);
    const bundled = item.bundleServiceInlet ? '<g class="bundled-inlet">'
      + path(`M${byId.get('U-left').x} ${byId.get('U-left').y}H${middle}`, { ...bundleStyle, w: 1.8, flow: 'U' })
      + circ(middle, byId.get('U-left').y, 2.5, { fill: bundleStyle.c, c: bundleStyle.c }) + '</g>' : '';
    return bundled + routes.map((route) => {
      const trunk = route.from.startsWith('@') ? routes.find((entry) => entry.id === route.from.slice(1)) : null;
      const source = trunk ? { x: middle, y: byId.get(trunk.from).y } : byId.get(route.from);
      const target = byId.get(route.to), style = serviceStyle(CONNECTION_TYPES[route.connectionType]);
      return `<g class="internal-route" data-route="${esc(route.id)}">`
        + path(`M${source.x} ${source.y}H${middle}V${target.y}H${target.x}`,
          { ...style, w: 1.8, flow: serviceLane(CONNECTION_TYPES[route.connectionType]), pipeId: `route-${route.id}` })
        + (trunk ? circ(source.x, source.y, 2.5, { fill: style.c, c: style.c }) : '')
        + '</g>';
    }).join('');
  }

  NODE.custom_element = {
    uses: '', w: (n) => num(n.w, 200),
    draw(c, n) {
      const w = NODE.custom_element.w(n);
      return root.SubseaRiserDetail.draw(n.riserDetail || root.SubseaRiserDetail.blank().riserDetail, c, w,
        { rect, path, circ, ink: T.ink, mono: CUR_SPEC.themeName === 'mono' })
        + elementLabel(c.x + w / 2, c.L.P - 44, n.label ?? 'Custom element', n, { size: 10.5, bold: true });
    },
  };
  NODE.riser_base = {
    uses: 'P', w: (n) => num(n.w, n.riserDetail ? 200 : 124),
    draw(c, n) {
      const { x } = c, y = c.L.P, w = NODE.riser_base.w(n);
      if (n.riserDetail) return root.SubseaRiserDetail.draw(n.riserDetail, c, w, { rect, path, circ, ink: T.ink, mono: CUR_SPEC.themeName === 'mono' })
        + elementLabel(x + w / 2, y - 44, n.label ?? 'Riser base', n, { size: 10.5, bold: true });
      const custom = n.portConfig && n.portConfig.mode === 'replace' && n.portConfig.lane === 'P';
      const bottom = riserFrameBottom(c, n, w, y + 36);
      const customPiping = n.riserPorts || n.internalRoutes !== undefined;
      return '<g class="riser-frame">' + rect(x + 4, y - 36, w - 8, bottom - y + 36, { dash: '3 3', w: 1 }) + '</g>' + (customPiping ? riserInternalPiping(c, n, w) : seg(c, 'P', x, x + w)
        + (n.bundleServiceInlet ? riserInternalPiping(c, n, w, true) : riserAuxiliaryLines(c, n, w))
        + (custom ? '' : conn(x + 10, y) + conn(x + w - 10, y))
        + valve(x + 36, y, { kind: 'ssiv' }) + valve(x + 70, y, { kind: 'gate' })
        + (custom ? '' : internalPipeGuide(x + 86, y, x + 86, y - 24, 'S') + line(x + 86, y, x + 86, y - 24, { c: laneColor('S'), w: 1.8 }) + valve(x + 86, y - 14, { kind: 'check', rot: 90, s: 4.5 }) + hub(x + 86, y - 27) + txt(x + 96, y - 24, 'GL', { size: 7.5, anchor: 'start', c: T.mute })))
        + elementLabel(x + w / 2, y - 42, n.label !== undefined ? n.label : 'Riser base', n, { size: 10.5, bold: true });
    },
  };
  NODE.riser_skid = {
    uses: 'P', w: (n) => num(n.w, n.riserDetail ? 200 : 140),
    draw(c, n) {
      const { x } = c, y = c.L.P, w = NODE.riser_skid.w(n);
      if (n.riserDetail) return root.SubseaRiserDetail.draw(n.riserDetail, c, w, { rect, path, circ, ink: T.ink, mono: CUR_SPEC.themeName === 'mono' })
        + elementLabel(x + w / 2, y - 44, n.label ?? 'Riser skid', n, { size: 10.5, bold: true });
      const custom = n.portConfig && n.portConfig.mode === 'replace' && n.portConfig.lane === 'P';
      const bottom = riserFrameBottom(c, n, w, y + 28);
      return '<g class="riser-frame">' + rect(x + 5, y - 28, w - 10, bottom - y + 28, { dash: '4 3', w: 1.2 }) + '</g>'
        + hatch(x + 5, bottom + 2, w - 10, 8, { w: 1.2 })
        + line(x + 16, bottom, x + 16, bottom + 2) + line(x + w - 16, bottom, x + w - 16, bottom + 2)
        + (n.riserPorts || n.internalRoutes !== undefined ? riserInternalPiping(c, n, w)
          : seg(c, 'P', x, x + w) + (custom ? '' : conn(x + 10, y) + conn(x + w - 10, y))
        + (n.bundleServiceInlet ? riserInternalPiping(c, n, w, true) : riserAuxiliaryLines(c, n, w))
        + valve(x + w * .35, y, { kind: 'ssiv' }) + valve(x + w * .7, y))
        + elementLabel(x + w / 2, y - 36, n.label !== undefined ? n.label : 'Riser skid', n, { size: 10.5, bold: true });
    },
  };

  /* ---- SDU: opens service + umbilical lanes ---- */
  NODE.sdu = {
    uses: 'SU', w: () => 46, open: () => ['S', 'U'], openX: () => 0,
    draw(c, n) {
      const { x, L } = c, yu = L.U, ys = L.S;
      let s = seg(c, 'U', x, x + 46);
      s += path(`M${x + 23} ${yu - 8}V${ys}H${x + 46}`, { c: T.green, w: LANE_W.S, flow: 'S' });
      s += hatch(x + 8, yu - 8, 30, 16, { w: 1.2 }) + conn(x + 4, yu) + conn(x + 42, yu);
      s += elementLabel(x + 23, yu + 22, n.label !== undefined ? n.label : 'SDU', n, { size: 9, bold: true });
      return s;
    },
  };

  /* ---- generic shapes (data driven) ---- */
  const GEN = {
    uta: { shape: 'hatch', abbr: 'UTA', lane: 'U', w: 46, h: 20, opens: true },
    suta: { shape: 'hatch', abbr: 'SUTA', lane: 'U', w: 52, h: 22, opens: true },
    scm: { shape: 'scm', abbr: 'SCM', lane: 'U', w: 40 },
    efl: { shape: 'efl', abbr: 'EFL', lane: 'U', w: 60 },
    cip: { shape: 'box', abbr: 'CIP', lane: 'S', w: 52, h: 22 },
    hpu: { shape: 'box', abbr: 'HPU', lane: 'S', w: 52, h: 22 },
    transformer: { shape: 'transformer', abbr: 'TX', lane: 'U', w: 56 },
    vsd: { shape: 'box', abbr: 'VSD', lane: 'U', w: 50, h: 24 },
    switchgear: { shape: 'switchgear', abbr: 'SWG', lane: 'U', w: 56, h: 24 },
    power_hub: { shape: 'hatch', abbr: 'EH', lane: 'U', w: 46, h: 20, opens: true },
    pt_sensor: { shape: 'sensor', abbr: 'PT', lane: 'P', w: 28 },
    tt_sensor: { shape: 'sensor', abbr: 'TT', lane: 'P', w: 28 },
    sand_detector: { shape: 'sensor', abbr: 'SD', lane: 'P', w: 32 },
    civ: { shape: 'civ', abbr: 'CIV', lane: 'P', w: 44 },
    sld_breaker: { shape: 'sld_breaker', abbr: 'CB', lane: 'P', w: 40 },
    sld_disconnector: { shape: 'sld_disc', abbr: 'DS', lane: 'P', w: 40 },
    sld_fuse: { shape: 'sld_fuse', abbr: 'F', lane: 'P', w: 36 },
    sld_motor: { shape: 'sld_rot', abbr: 'M', lane: 'P', w: 46 },
    sld_generator: { shape: 'sld_rot', abbr: 'G', lane: 'P', w: 46 },
    sld_ct_vt: { shape: 'sld_ct', abbr: 'CT', lane: 'P', w: 36 },
    sld_earthing: { shape: 'sld_earth', abbr: 'PE', lane: 'P', w: 34 },
    sld_busbar: { shape: 'sld_bus', abbr: 'BB', lane: 'P', w: 90 },
    mpfm: { shape: 'mpfm', abbr: 'MPFM', lane: 'P', w: 60 },
    pig_launcher: { shape: 'pig', abbr: 'Pig launcher', lane: 'P', w: 92, dir: 1 },
    pig_receiver: { shape: 'pig', abbr: 'Pig receiver', lane: 'P', w: 92, dir: -1 },
    mpp: { shape: 'pump', abbr: 'MPP', lane: 'P', w: 84 },
    srp: { shape: 'pump', abbr: 'SRP', lane: 'P', w: 84 },
    wgc: { shape: 'compressor', abbr: 'WGC', lane: 'P', w: 84 },
    separator: { shape: 'separator', abbr: 'Separator', lane: 'P', w: 110 },
    hx: { shape: 'hx', abbr: 'Cooler', lane: 'P', w: 84 },
    water_treat: { shape: 'dashbox', abbr: 'Water treatment', lane: 'P', w: 100, h: 40 },
    storage_tank: { shape: 'tank', abbr: 'Storage', lane: 'S', w: 70 },
    gl_manifold: { shape: 'dashbox', abbr: 'GL manifold', lane: 'S', w: 90, h: 30 },
    vxt: { shape: 'tree_v', abbr: 'VXT', lane: 'P', w: 62 },
    hxt: { shape: 'tree_h', abbr: 'HXT', lane: 'P', w: 62 },
    wellhead: { shape: 'wellhead', abbr: 'Wellhead', lane: 'P', w: 62 },
    suction_pile: { shape: 'pile', abbr: 'Suction pile', lane: 'P', w: 60 },
    protection_frame: { shape: 'frame', abbr: 'Protection', lane: 'P', w: 90 },
    mattress: { shape: 'mattress', abbr: 'Mattress', lane: 'P', w: 70 },
    rockdump: { shape: 'mound', abbr: 'Rock dump', lane: 'P', w: 90 },
    crossing: { shape: 'crossing', abbr: 'Crossing', lane: 'P', w: 60 },
    buoyancy: { shape: 'buoy', abbr: 'Buoyancy', lane: 'P', w: 90 },
    bend_stiffener: { shape: 'taper', abbr: 'Bend stiffener', lane: 'P', w: 70 },
    anode: { shape: 'anodes', abbr: 'Anodes', lane: 'P', w: 60 },
    trawl_guard: { shape: 'arch', abbr: 'Trawl guard', lane: 'P', w: 84 },
    pipe_support: { shape: 'support', abbr: 'Support', lane: 'P', w: 44 },
    end_termination: { shape: 'endcap', abbr: 'End cap', lane: 'P', w: 40 },
    wye_tee: { shape: 'wye', abbr: 'Wye / tee', lane: 'P', w: 56 },
    deh: { shape: 'heater', abbr: 'DEH', lane: 'P', w: 90 },
    hydrate_skid: { shape: 'dashbox', abbr: 'Hydrate remediation', lane: 'P', w: 130, h: 36 },
    accumulator: { shape: 'tank', abbr: 'ACC', lane: 'S', w: 60 },
    flex_joint: { shape: 'bellows', abbr: 'Flex joint', lane: 'P', w: 56 },
    leak_detector: { shape: 'sensor', abbr: 'LD', lane: 'P', w: 28 },
    compression_station: { shape: 'station', abbr: 'Compression station', lane: 'P', w: 150 },
    pct: { shape: 'hatch', abbr: 'PCT', lane: 'U', w: 46, h: 20, opens: true },
    fibre_hub: { shape: 'hatch', abbr: 'FO hub', lane: 'U', w: 50, h: 20, opens: true },
    junction_box: { shape: 'hatch', abbr: 'JB', lane: 'U', w: 46, h: 20, opens: true },
  };

  function genShape(def, c, n, x, y, w) {
    const cx = x + w / 2, ab = n.label !== undefined ? n.label : def.abbr, h = def.h || 22;
    const lc = laneColor(def.lane);
    const above = (s, dy = 0) => (s ? elementLabel(cx, y - dy, s, n, { size: 8.5, bold: true }) : '');
    switch (def.shape) {
      case 'box': return rect(cx - w / 2 + 4, y - h / 2, w - 8, h, { fill: T.paper }) + above(ab, h / 2 + 4) + txt(cx, y + 3, def.abbr, { size: 8, c: T.mute });
      case 'hatch': return hatch(cx - 15, y - h / 2, 30, h) + conn(x + 4, y) + conn(x + w - 4, y) + elementLabel(cx, y + h / 2 + 11, ab, n, { size: 9, bold: true });
      case 'dashbox': return rect(x + 4, y - h / 2, w - 8, h, { dash: '3 3', fill: T.paper, w: 1 }) + elementLabel(cx, y + 3, ab, n, { size: 9, bold: true });
      case 'scm': return rect(cx - 12, y - 30, 24, 16, { fill: T.paper }) + line(cx, y - 14, cx, y, { w: 1.2 }) + circ(cx, y, 2.4, { fill: T.ink }) + elementLabel(cx, y - 20, ab, n, { size: 8, bold: true });
      case 'efl': return path(`M${x + 2} ${y}C${x + 14} ${y - 16} ${x + 24} ${y + 16} ${x + 36} ${y}S${x + 52} ${y - 10} ${x + w - 2} ${y}`, { c: T.blue, w: 1.6, dash: '5 2' }) + elementLabel(cx, y - 16, ab, n, { size: 8.5, bold: true });
      case 'transformer': return circ(cx - 7, y, 10, { fill: T.paper }) + circ(cx + 7, y, 10, { fill: T.paper }) + elementLabel(cx, y + 24, ab, n, { size: 8.5, bold: true });
      case 'switchgear': return rect(cx - 22, y - h / 2, 44, h, { fill: T.paper }) + line(cx - 10, y + 6, cx, y - 6, { w: 1.2 }) + circ(cx - 10, y + 6, 1.6, { fill: T.ink }) + circ(cx + 10, y + 6, 1.6, { fill: T.ink }) + elementLabel(cx, y + h / 2 + 11, ab, n, { size: 8.5, bold: true });
      case 'sensor': return line(cx, y, cx, y - 14, { w: 0.9 }) + circ(cx, y - 22, 8, { fill: T.paper, w: 1 }) + line(cx - 8, y - 22, cx + 8, y - 22, { w: 0.6 }) + txt(cx, y - 23.5, def.abbr, { size: 6.2, bold: true, halo: false }) + txt(cx, y - 17, n._num || '', { size: 5.6, halo: false })
        + (n.label ? elementLabel(cx, y - 36, n.label, n, { size: 8.5 }) : '');
      case 'sld_breaker': return rect(cx - 8, y - 8, 16, 16, { fill: T.paper, w: 1.3 }) + line(cx - 8, y - 8, cx + 8, y + 8, { w: 1.2 }) + line(cx - 8, y + 8, cx + 8, y - 8, { w: 1.2 }) + elementLabel(cx, y - 14, ab, n, { size: 8.5, bold: true });
      case 'sld_disc': return circ(cx - 9, y, 1.8, { fill: T.ink }) + circ(cx + 9, y, 1.8, { fill: T.ink }) + line(cx - 9, y, cx + 6, y - 12, { w: 1.4 }) + elementLabel(cx, y - 18, ab, n, { size: 8.5, bold: true });
      case 'sld_fuse': return rect(cx - 10, y - 4, 20, 8, { fill: T.paper, w: 1.2 }) + line(cx - 10, y, cx + 10, y, { w: 0.8 }) + elementLabel(cx, y - 10, ab, n, { size: 8.5, bold: true });
      case 'sld_rot': return circ(cx, y, 14, { fill: T.paper, w: 1.3 }) + txt(cx, y + 4, def.abbr, { size: 11, bold: true, halo: false }) + elementLabel(cx, y - 20, n.label !== undefined ? n.label : def.abbr + '-' + (n._num || ''), n, { size: 8.5, bold: true });
      case 'sld_ct': return circ(cx, y, 7, { fill: T.paper, w: 1.2 }) + elementLabel(cx, y - 14, ab, n, { size: 8, bold: true });
      case 'sld_earth': return line(cx, y, cx, y + 14, { w: 1.2 }) + line(cx - 9, y + 14, cx + 9, y + 14, { w: 1.4 }) + line(cx - 6, y + 18, cx + 6, y + 18, { w: 1.2 }) + line(cx - 3, y + 22, cx + 3, y + 22, { w: 1 }) + elementLabel(cx, y - 8, ab, n, { size: 8, bold: true });
      case 'sld_bus': return line(x + 2, y, x + w - 2, y, { w: 5, c: T.ink }) + elementLabel(cx, y - 10, ab, n, { size: 8.5, bold: true });
      case 'civ': return internalPipeGuide(cx, y, cx, y - 22, 'S') + line(cx, y, cx, y - 22, { c: T.green, w: 1.9 }) + valve(cx, y - 12, { kind: 'check', rot: 90, s: 4.5 }) + conn(cx, y - 22, 90) + elementLabel(cx, y - 32, ab, n, { size: 8.5, bold: true });
      case 'mpfm': return path(`M${x + 8} ${y - 6}L${cx - 10} ${y - 6}L${cx - 4} ${y - 3}H${cx + 4}L${cx + 10} ${y - 6}H${x + w - 8}M${x + 8} ${y + 6}L${cx - 10} ${y + 6}L${cx - 4} ${y + 3}H${cx + 4}L${cx + 10} ${y + 6}H${x + w - 8}`, { w: 1.2 }) + line(cx, y - 3, cx, y - 15, { w: 1 }) + circ(cx, y - 20, 5.5, { fill: T.paper, w: 1 }) + elementLabel(cx, y + 20, ab, n, { size: 8.5, bold: true }) + conn(x + 6, y) + conn(x + w - 6, y);
      case 'pig': return rect(x + 10, y - 9, w - 20, 18, { fill: T.paper }) + circ(cx, y, 4, { fill: T.ink }) + path(`M${x + 14} ${y}h6M${x + w - 14} ${y}h-6`, { w: 1 }) + conn(x + 6, y) + conn(x + w - 6, y) + elementLabel(cx, y - 15, ab, n, { size: 8.5, bold: true });
      case 'pump': return circ(cx, y, 14, { fill: T.paper, w: 1.2 }) + path(`M${cx - 6} ${y - 8}L${cx + 9} ${y}L${cx - 6} ${y + 8}Z`, { fill: T.ink, w: 0.8 }) + conn(x + 6, y) + conn(x + w - 6, y) + line(cx, y - 14, cx, y - 24, { w: 1.4 }) + rect(cx - 10, y - 36, 20, 12, { fill: T.paper, w: 1.1 }) + txt(cx, y - 27.5, 'M', { size: 8, bold: true, halo: false }) + elementLabel(cx, y - 42, ab, n, { size: 9, bold: true });
      case 'compressor': return circ(cx, y, 14, { fill: T.paper, w: 1.2 }) + path(`M${cx - 10} ${y - 9}L${cx + 10} ${y - 4}M${cx - 10} ${y + 9}L${cx + 10} ${y + 4}`, { w: 1.4 }) + conn(x + 6, y) + conn(x + w - 6, y) + line(cx, y - 14, cx, y - 24, { w: 1.4 }) + rect(cx - 10, y - 36, 20, 12, { fill: T.paper, w: 1.1 }) + txt(cx, y - 27.5, 'M', { size: 8, bold: true, halo: false }) + elementLabel(cx, y - 42, ab, n, { size: 9, bold: true });
      case 'separator': return path(`M${x + 24} ${y - 16}H${x + w - 24}Q${x + w - 6} ${y - 16} ${x + w - 6} ${y}Q${x + w - 6} ${y + 16} ${x + w - 24} ${y + 16}H${x + 24}Q${x + 6} ${y + 16} ${x + 6} ${y}Q${x + 6} ${y - 16} ${x + 24} ${y - 16}Z`, { fill: T.paper, w: 1.3 }) + line(cx - 4, y - 16, cx - 4, y + 2, { w: 0.9 }) + line(cx - 24, y + 5, cx + 30, y + 5, { w: 0.7, dash: '4 2' }) + txt(cx + 30, y + 12, 'NLL', { size: 5.5, anchor: 'start', halo: false, c: T.mute }) + conn(x + 3, y) + conn(x + w - 3, y) + line(cx + 22, y - 16, cx + 22, y - 28, { w: 1.6, c: PC() }) + line(cx - 24, y + 16, cx - 24, y + 28, { w: 1.6, c: T.blue }) + path(`M${cx - 20} ${y + 16}l-4 7h8Z`, { fill: T.paper, w: 0.9 }) + path(`M${cx + 20} ${y + 16}l-4 7h8Z`, { fill: T.paper, w: 0.9 }) + elementLabel(cx, y - 33, ab, n, { size: 9, bold: true });
      case 'hx': return circ(cx, y, 15, { fill: T.paper, w: 1.2 }) + path(`M${cx - 13} ${y}l4 -8 l5 16 l5 -16 l5 16 l5 -16 l4 8`, { w: 1 }) + conn(x + 6, y) + conn(x + w - 6, y) + line(x + 6, y, cx - 15, y, { w: 1 }) + elementLabel(cx, y - 21, ab, n, { size: 9, bold: true });
      case 'tank': return path(`M${cx - 22} ${y - 10}Q${cx - 22} ${y - 20} ${cx} ${y - 20}Q${cx + 22} ${y - 20} ${cx + 22} ${y - 10}V${y + 10}Q${cx + 22} ${y + 20} ${cx} ${y + 20}Q${cx - 22} ${y + 20} ${cx - 22} ${y + 10}Z`, { fill: T.paper, w: 1.3 }) + line(cx - 22, y, cx + 22, y, { w: 0.7, dash: '4 2' }) + line(cx - 26, y, cx - 22, y, { w: 1.2 }) + elementLabel(cx, y + 32, ab, n, { size: 9, bold: true });
      case 'tree_v': return internalPipeGuide(cx, y, cx, y - 54) + rect(cx - 7, y - 54, 14, 54, { fill: T.paper, w: 1.1 }) + [0, 1, 2].map((i) => valve(cx, y - 12 - i * 14, { rot: 90, s: 4.5 })).join('') + line(cx, y, cx, y + 2) + elementLabel(cx, y - 60, ab, n, { size: 9, bold: true });
      case 'tree_h': return internalPipeGuide(cx, y, cx, y - 50) + internalPipeGuide(cx + 7, y - 24, cx + 22, y - 24) + rect(cx - 7, y - 50, 14, 50, { fill: T.paper, w: 1.1 }) + line(cx + 7, y - 24, cx + 22, y - 24, { w: 1.4 }) + valve(cx + 15, y - 24, { s: 4 }) + valve(cx, y - 40, { rot: 90, s: 4.5 }) + valve(cx, y - 10, { rot: 90, s: 4.5 }) + elementLabel(cx, y - 56, ab, n, { size: 9, bold: true });
      case 'wellhead': return rect(cx - 12, y - 6, 24, 18, { fill: T.paper, w: 1.1 }) + line(cx, y + 12, cx, y + 32, { w: 3 }) + rect(cx - 6, y - 22, 12, 16, { fill: T.soft, w: 1 }) + elementLabel(cx, y - 28, ab, n, { size: 9, bold: true });
      case 'pile': return rect(cx - 12, y + 6, 24, 32, { fill: 'url(#hatch)', w: 1 }) + path(`M${cx - 12} ${y + 6}a12 4 0 0 1 24 0`, { w: 1 }) + elementLabel(cx, y - 12, ab, n, { size: 8.5, bold: true });
      case 'frame': return rect(x + 4, y - 22, w - 8, 44, { dash: '5 3', w: 1.2 }) + line(x + 4, y - 22, x + w - 4, y + 22, { w: 0.6, c: T.mute }) + line(x + w - 4, y - 22, x + 4, y + 22, { w: 0.6, c: T.mute }) + elementLabel(cx, y - 28, ab, n, { size: 9, bold: true });
      case 'mattress': return hatch(x + 4, y + 7, w - 8, 6, { w: 0.9 }) + elementLabel(cx, y - 10, ab, n, { size: 8.5, bold: true });
      case 'mound': return path(`M${x + 4} ${y + 14}L${cx - 14} ${y + 6}H${cx + 14}L${x + w - 4} ${y + 14}Z`, { fill: T.soft, w: 1 }) + [0, 1, 2, 3, 4].map((i) => circ(cx - 16 + i * 8, y + 10.5, 1.3, { fill: T.ink, w: 0.5 })).join('') + elementLabel(cx, y - 10, ab, n, { size: 8.5, bold: true });
      case 'crossing': return line(cx, y - 34, cx, y + 34, { c: T.mute, w: 4 }) + line(cx, y - 34, cx, y + 34, { c: T.paper, w: 1.6 }) + hatch(cx - 12, y + 3, 24, 5, { w: 0.8 }) + elementLabel(cx, y - 40, ab, n, { size: 8.5, bold: true });
      case 'buoy': return [0, 1, 2, 3].map((i) => circ(x + 14 + i * ((w - 28) / 3), y - 7, 6, { fill: '#f6c64d', w: 1 })).join('') + elementLabel(cx, y - 22, ab, n, { size: 8.5, bold: true });
      case 'taper': return path(`M${x + 6} ${y - 8}L${x + w - 6} ${y - 2}V${y + 2}L${x + 6} ${y + 8}Z`, { fill: T.soft, w: 1 }) + elementLabel(cx, y - 16, ab, n, { size: 8.5, bold: true });
      case 'anodes': return [0, 1, 2].map((i) => rect(x + 8 + i * 17, y - 5, 12, 10, { fill: T.soft, w: 1 })).join('') + elementLabel(cx, y - 12, ab, n, { size: 8.5, bold: true });
      case 'arch': return path(`M${x + 6} ${y + 8}Q${cx} ${y - 26} ${x + w - 6} ${y + 8}`, { dash: '5 3', w: 1.3 }) + elementLabel(cx, y - 24, ab, n, { size: 8.5, bold: true });
      case 'support': return path(`M${cx - 10} ${y + 16}L${cx} ${y + 4}L${cx + 10} ${y + 16}Z`, { fill: T.soft, w: 1 }) + elementLabel(cx, y - 8, ab, n, { size: 8.5, bold: true });
      case 'endcap': return line(x + w - 12, y - 10, x + w - 12, y + 10, { w: 3 }) + elementLabel(cx, y - 14, ab, n, { size: 8.5, bold: true });
      case 'wye': return line(cx - 4, y, cx + 20, y - 26, { c: PC(), w: 2.2, flow: 'P' }) + hub(cx + 22, y - 29) + conn(x + 6, y) + conn(x + w - 6, y) + elementLabel(cx, y + 18, ab, n, { size: 8.5, bold: true });
      case 'heater': return rect(x + 8, y - 13, w - 16, 26, { fill: T.paper, w: 1.2 }) + path(`M${x + 14} ${y}l5 -8 l6 16 l6 -16 l6 16 l6 -16 l6 16 l6 -16 l5 8`, { w: 1.2 }) + conn(x + 4, y) + conn(x + w - 4, y) + elementLabel(cx, y - 19, ab, n, { size: 9, bold: true });
      case 'bellows': return rect(cx - 15, y - 7, 30, 14, { fill: T.paper, w: 0.01, c: T.paper }) + path(`M${cx - 15} ${y}l3 -8 l4 16 l4 -16 l4 16 l4 -16 l4 16 l4 -16 l4 8`, { w: 1.2 }) + elementLabel(cx, y - 14, ab, n, { size: 8.5, bold: true });
      case 'station': return rect(x + 4, y - 30, w - 8, 60, { dash: '3 3', fill: T.paper, w: 1 }) + line(x + 4, y, x + w - 4, y, { c: PC(), w: 2.2, flow: 'P' }) + conn(x + 14, y) + circ(cx, y, 14, { fill: T.paper, w: 1.2 }) + path(`M${cx - 10} ${y - 9}L${cx + 10} ${y - 4}M${cx - 10} ${y + 9}L${cx + 10} ${y + 4}`, { w: 1.3 }) + valve(x + 34, y, { s: 5.5 }) + valve(x + w - 34, y, { s: 5.5 }) + conn(x + w - 14, y) + line(cx, y - 14, cx, y - 22, { w: 1.3 }) + elementLabel(cx, y - 34, ab, n, { size: 9, bold: true });
      default: return rect(cx - 15, y - 10, 30, 20) + elementLabel(cx, y + 3, ab, n, { size: 8 });
    }
  }

  function genNode(def) {
    return {
      uses: def.lane, w: (n) => num(n.w, def.w),
      open: def.opens ? () => [def.lane] : undefined, openX: () => 0,
      draw(c, n) {
        const w = num(n.w, def.w), x = c.x;
        let base = '';
        if (def.shape !== 'efl') {
          if (def.opens && !c.act[def.lane]) base = seg(c, def.lane, x + w / 2, x + w);
          else if (c.act[def.lane] || def.lane === 'P') base = seg(c, def.lane, x, x + (def.shape === 'endcap' ? w - 12 : w));
        }
        return base + genShape(def, c, n, x, c.L[def.lane], w);
      },
    };
  }
  Object.keys(GEN).forEach((k) => { NODE[k] = genNode(GEN[k]); });
  // custom symbols added at runtime go through the same path
  function registerCustom(list) {
    (list || []).forEach((cs) => {
      if (!cs || !cs.id) return;
      GEN[cs.id] = { shape: cs.shape || 'box', abbr: cs.abbr || cs.id, lane: cs.lane || 'P', w: cs.w || 60, h: cs.h || 22 };
      NODE[cs.id] = genNode(GEN[cs.id]);
    });
  }

  /* ============================================================ LINK DEFS === */
  const LINK = {
    pipeline_rigid: { pStyle: 'rigid', pType: 'Rigid Pipeline' },
    pipeline_pip: { pStyle: 'pip', pType: 'Rigid Pipeline, Pipe in Pipe' },
    pipeline_flex: { pStyle: 'flex', pType: 'Flexible Flowline' },
    pipeline_bundle: { pStyle: 'bundle', pType: 'Pipeline Bundle' },
    cable_power: { pStyle: 'none', pType: '' },
  };

  function linkWidth(n) {
    if (n.w) return +n.w;
    const km = num(n.pKm, num(n.sKm, num(n.uKm, 3)));
    return Math.max(56, Math.min(360, Math.round(46 + 11 * km)));
  }
  function linkLabels(n, def) {
    const pType = n.pType !== undefined ? n.pType : def.pType;
    const p = n.label !== undefined ? n.label : n.pLabel !== undefined ? n.pLabel
      : [pType, n.pId ? `${n.pId}" ID` : '', n.pKm ? `${n.pKm}km` : ''].filter(Boolean).join(', ');
    const s = n.sLabel !== undefined ? n.sLabel
      : (n.sKm || n.sId) ? `Service Line, ${n.sKm ? n.sKm + 'km' : ''}${n.sId ? ` ${n.sId}" ID` : ''}`.replace(/,\s*$/, '') : '';
    const u = n.uLabel !== undefined ? n.uLabel : (n.uKm ? `Umbilical, ${n.uKm}km` : '');
    return { p, s, u };
  }
  function parallel(x1, x2, y, n, o) {
    if (n <= 1) return line(x1, y, x2, y, o);
    let s = '';
    for (let i = 0; i < n; i++) { const off = (i - (n - 1) / 2) * (o.sp || 6); s += path(`M${x1} ${y}L${x1 + 9} ${y + off}H${x2 - 9}L${x2} ${y}`, o); }
    return s;
  }
  function drawLink(c, n, def) {
    const { x, L } = c, w = linkWidth(n), lab = linkLabels(n, def);
    const thickness = num(n.lineWidth, num(CUR_SPEC.connectionWidth, 2.2));
    const style = n.pStyle || def.pStyle;
    const np = Math.max(1, Math.min(4, num(n.pCount, 1))), ns = Math.max(1, Math.min(4, num(n.sCount, 1))), nu = Math.max(1, Math.min(4, num(n.uCount, 1)));
    let s = '';
    if (style !== 'none') {
      const col = n.pColor || PC();
      if (style === 'flex') s += parallel(x, x + w, L.P, np, { c: col, w: thickness, dash: '10 3', flow: 'P' });
      else if (style === 'bundle') s += line(x, L.P, x + w, L.P, { c: col, w: thickness * 2.3, flow: 'P' }) + line(x, L.P, x + w, L.P, { c: T.paper, w: thickness * .6 });
      else s += parallel(x, x + w, L.P, np, { c: col, w: thickness, dash: CUR_P.dash, flow: 'P' });
    } else if (def === LINK.cable_power) {
      s += parallel(x, x + w, L.P, np, { c: PC(), w: thickness, dash: '7 3', flow: 'P' });
    }
    if (c.act.S) s += ns > 1 ? parallel(x, x + w, L.S, ns, { c: laneColor('S'), w: LANE_W.S, dash: T.dash && T.dash.S, flow: 'S', sp: 4 }) : seg(c, 'S', x, x + w);
    if (c.act.U) s += nu > 1 ? parallel(x, x + w, L.U, nu, { c: n.uColor || laneColor('U'), w: LANE_W.U, dash: T.dash && T.dash.U, flow: 'U', sp: 4 }) : seg(c, 'U', x, x + w, n.uColor ? { c: n.uColor } : {});
    if (CUR_SPEC.flowArrows !== false && CUR_FLOW.P.mode !== 'none' && style !== 'none' && w >= 80) {
      const ax = x + w * 0.5, d = CUR_FLOW.P.mode === 'rev' ? -1 : 1;
      s += path(`M${ax - 4.5 * d} ${L.P - 5}L${ax + 4.5 * d} ${L.P}L${ax - 4.5 * d} ${L.P + 5}Z`, { fill: PC(), c: T.paper, w: 0.9 });
    }
    if (n._lineNo && w >= 100) s += txt(x + w / 2, L.P + 12 + (np > 1 ? 4 * np : 0), n._lineNo, { size: 7.5, italic: true, c: T.mute });
    if (lab.p) {
      const vertical = n.vertical !== undefined ? n.vertical : w < 112;
      const fs = 9, ptxt = np > 1 && n.pLabel === undefined ? `${np}x ${lab.p}` : lab.p;
      if (vertical) s += elementLabel(x + w / 2 + 3, L.P - 9, ptxt, n, { rot: -90, anchor: 'start', size: fs, bold: false });
      else {
        const left = w > 170;
        s += elementLabel(left ? x + 6 : x + w / 2, L.P - 8 - (np > 1 ? 3 * np : 0), wrap(ptxt, num(n.pWrap, Math.floor((w - 12) / 5.2))), n, { anchor: left ? 'start' : 'middle', size: fs, va: 'bottom' });
      }
    }
    if (lab.s && c.act.S) s += elementLabel(w > 150 ? x + 6 : x + w / 2, L.S - 5, lab.s, n, { anchor: w > 150 ? 'start' : 'middle', size: 9 });
    if (lab.u && c.act.U) s += elementLabel(w > 150 ? x + 6 : x + w / 2, L.U + 14, lab.u, n, { anchor: w > 150 ? 'start' : 'middle', size: 9 });
    return s;
  }

  /* ================================================================ HOSTS === */
  const HOSTS = {};
  const lerp = (a, b, t) => a + (b - a) * t;
  const slotsOf = (hs) => Array.isArray(hs.slots) ? hs.slots : ['J1', 'J2'];

  function slotHeader(hs, x0, y, gap) {
    const act = hs.activeSlot !== undefined ? hs.activeSlot : slotsOf(hs).length - 1;
    return slotsOf(hs).map((s, i) => txt(x0 + i * gap, y, s, { size: 11, bold: true, c: i === act ? T.red : T.ink })).join('');
  }

  function jacketDraw(o, bays, H, wTop, wBase, deckW) {
    const { x, top, spec } = o;
    let s = '';
    const dh = 22;
    const cxl = x + 70;
    const topY = top + dh;
    const legAt = (t) => [lerp(cxl - wTop / 2, cxl - wBase / 2, t), lerp(cxl + wTop / 2, cxl + wBase / 2, t)];
    // rear lattice (perspective)
    const off = 14;
    for (let i = 0; i <= bays; i++) {
      const t = i / bays, y = topY + t * (H - dh), [l, r] = legAt(t);
      s += line(l + off, y - 6, r + off, y - 6, { w: 0.7, c: T.mute });
    }
    s += line(legAt(0)[0] + off, topY - 6, legAt(1)[0] + off, top + H - 6, { w: 0.7, c: T.mute }) + line(legAt(0)[1] + off, topY - 6, legAt(1)[1] + off, top + H - 6, { w: 0.7, c: T.mute });
    // front lattice
    for (let i = 0; i < bays; i++) {
      const t0 = i / bays, t1 = (i + 1) / bays, y0 = topY + t0 * (H - dh), y1 = topY + t1 * (H - dh);
      const [l0, r0] = legAt(t0), [l1, r1] = legAt(t1);
      s += line(l0, y0, r1, y1, { w: 0.9 }) + line(r0, y0, l1, y1, { w: 0.9 });
    }
    for (let i = 0; i <= bays; i++) { const t = i / bays, y = topY + t * (H - dh), [l, r] = legAt(t); s += line(l, y, r, y, { w: 1.1 }); }
    s += line(legAt(0)[0], topY, legAt(1)[0], top + H, { w: 2 }) + line(legAt(0)[1], topY, legAt(1)[1], top + H, { w: 2 });
    // base plates
    s += rect(legAt(1)[0] - 6, top + H - 3, 12, 6, { fill: T.soft, w: 1 }) + rect(legAt(1)[1] - 6, top + H - 3, 12, 6, { fill: T.soft, w: 1 });
    // deck
    deckW = Math.max(deckW, slotsOf(spec).length * 26 + 16);
    s += rect(cxl - deckW / 2, top, deckW, dh, { fill: T.paper, w: 1.4 });
    const gap = 26, sx = cxl - ((slotsOf(spec).length - 1) * gap) / 2 - 4;
    if (!spec.showJTubes) s += slotHeader(spec, sx, top + 15, gap);
    const anchors = slotsOf(spec).map((_, i) => ({ x: sx + i * gap, y: top + dh }));
    return { svg: s, w: Math.max(cxl + wBase / 2 + 24 - x, cxl + deckW / 2 - x), anchors };
  }
  HOSTS.jacket = { h: 245, draw: (o) => jacketDraw(o, 5, 245, 56, 112, 112) };
  HOSTS.platform = { h: 175, draw: (o) => jacketDraw(o, 3, 175, 40, 78, 84) };

  function waterLine(x, w, y) { return path(`M${x} ${y}` + Array.from({ length: Math.ceil(w / 16) }, () => 'q4 -4 8 0 q4 4 8 0').join(' '), { c: '#6aa5d8', w: 1.1 }); }

  HOSTS.fpso = {
    h: 235,
    draw({ x, top, spec }) {
      const wl = top + 70;
      let s = waterLine(x, 190, wl);
      s += path(`M${x + 6} ${wl - 30}H${x + 168}L${x + 188} ${wl - 18}L${x + 168} ${wl + 24}H${x + 22}Q${x + 6} ${wl + 24} ${x + 6} ${wl + 6}Z`, { fill: T.paper, w: 1.6 });
      s += rect(x + 24, wl - 52, 42, 22, { fill: T.paper }) + rect(x + 72, wl - 46, 30, 16, { fill: T.paper }) + line(x + 140, wl - 30, x + 140, wl - 66, { w: 1.4 }) + path(`M${x + 140} ${wl - 66}q4 -6 0 -10`, { c: PC(), w: 1.2 });
      s += circ(x + 120, wl - 2, 8, { fill: T.paper });
      s += slotHeader(spec, x + 114, wl - 14, 0);
      const anchors = slotsOf(spec).map((_, i) => ({ x: x + 120 + (i - (slotsOf(spec).length - 1) / 2) * 12, y: wl + 24 }));
      return { svg: s, w: 200, anchors };
    },
  };
  HOSTS.semisub = {
    h: 235,
    draw({ x, top, spec }) {
      const wl = top + 70;
      let s = waterLine(x - 6, 200, wl);
      s += rect(x + 10, wl - 44, 150, 20, { fill: T.paper, w: 1.5 }) + [0, 1].map((i) => rect(x + 30 + i * 90, wl - 24, 20, 56, { fill: T.paper })).join('') + rect(x + 10, wl + 32, 150, 14, { rx: 7, fill: T.paper, w: 1.4 });
      s += slotHeader(spec, x + 85, wl - 30, 0);
      const anchors = slotsOf(spec).map((_, i) => ({ x: x + 76 + i * 16, y: wl + 46 }));
      return { svg: s, w: 190, anchors };
    },
  };
  HOSTS.tlp = {
    h: 245,
    draw({ x, top, spec, L }) {
      const wl = top + 60, sb = top + 245;
      let s = waterLine(x - 6, 200, wl);
      s += rect(x + 10, wl - 40, 150, 18, { fill: T.paper, w: 1.5 }) + [0, 1].map((i) => rect(x + 20 + i * 110, wl - 22, 20, 58, { fill: T.paper })).join('') + rect(x + 20, wl + 36, 130, 10, { fill: T.paper });
      [30, 140].forEach((tx) => { s += line(x + tx, wl + 46, x + tx, sb, { w: 1.3, dash: '2 2' }); });
      s += slotHeader(spec, x + 85, wl - 26, 0);
      const anchors = slotsOf(spec).map((_, i) => ({ x: x + 70 + i * 16, y: wl + 46 }));
      return { svg: s, w: 190, anchors };
    },
  };
  HOSTS.spar = {
    h: 245,
    draw({ x, top, spec }) {
      const wl = top + 60;
      let s = waterLine(x - 6, 190, wl);
      s += rect(x + 50, wl - 36, 70, 14, { fill: T.paper }) + rect(x + 62, wl - 22, 46, 150, { rx: 4, fill: T.paper, w: 1.6 }) + line(x + 62, wl + 70, x + 108, wl + 70, { w: 0.8, dash: '3 3' });
      s += slotHeader(spec, x + 85, wl - 26, 0);
      const anchors = slotsOf(spec).map((_, i) => ({ x: x + 76 + i * 14, y: wl + 128 }));
      return { svg: s, w: 170, anchors };
    },
  };
  HOSTS.wind = {
    h: 235,
    draw({ x, top, spec }) {
      const wl = top + 110;
      let s = waterLine(x - 6, 170, wl);
      s += line(x + 80, top + 24, x + 80, wl, { w: 3 }) + path(`M${x + 80} ${top + 24}L${x + 80} ${top - 14}M${x + 80} ${top + 24}L${x + 56} ${top + 38}M${x + 80} ${top + 24}L${x + 104} ${top + 38}`, { w: 2 })
        + circ(x + 80, top + 24, 4, { fill: T.paper }) + path(`M${x + 62} ${wl}L${x + 98} ${wl}L${x + 92} ${wl + 34}L${x + 68} ${wl + 34}Z`, { fill: T.paper, w: 1.4 })
        + elementLabel(x + 94, top + 60, spec.label === undefined ? 'Wind / power hub' : spec.label, spec, { size: 9, bold: true, anchor: 'start', halo: false });
      return { svg: s, w: 170, anchors: [{ x: x + 80, y: wl + 34 }] };
    },
  };
  HOSTS.hrt = {
    h: 240,
    draw({ x, top, spec }) {
      let s = rect(x + 52, top + 40, 22, 36, { rx: 5, fill: T.paper, w: 1.4 }) + line(x + 63, top + 76, x + 63, top + 240, { w: 2.6 }) + rect(x + 52, top + 228, 22, 12, { fill: T.soft, w: 1 })
        + elementLabel(x + 63, top + 32, spec.label === undefined ? 'HRT' : spec.label, spec, { size: 9.5, bold: true }) + path(`M${x + 74} ${top + 50}C${x + 110} ${top + 40} ${x + 110} ${top + 10} ${x + 140} ${top + 8}`, { dash: '9 3', w: 1.4 }) + txt(x + 142, top + 12, 'to FPU', { size: 8.5, anchor: 'start', c: T.mute });
      return { svg: s, w: 110, anchors: [{ x: x + 63, y: top + 200 }] };
    },
  };
  HOSTS.onshore = {
    h: 150, noRisers: true,
    draw({ x, top, L, spec }) {
      const sb = L.U + 16, y0 = top;
      let s = path(`M${x} ${y0 + 30}H${x + 70}L${x + 130} ${sb}H${x}Z`, { fill: T.soft, w: 1.3 });
      s += rect(x + 8, y0 + 4, 40, 26, { fill: T.paper }) + rect(x + 52, y0 + 14, 14, 16, { fill: T.paper }) + rect(x + 20, y0 - 18, 6, 22, { fill: T.paper });
      s += elementLabel(x + 30, y0 + 48, spec.label === undefined ? 'Onshore\nterminal' : spec.label, spec, { size: 9, bold: true });
      return { svg: s, w: 130, anchors: [] };
    },
  };
  HOSTS.tieback = {
    h: 120, noRisers: true,
    draw({ x, top, spec, L }) {
      const lab = spec.label === undefined ? 'Existing\ninfrastructure' : spec.label;
      const y = L.P;
      return { svg: rect(x + 6, y - 30, 80, 60, { dash: '4 3', w: 1.2 }) + elementLabel(x + 46, y - 4, lab, spec, { size: 9.5, bold: true }) + conn(x + 92, y), w: 100, anchors: [] };
    },
  };

  /* ------------------------------------------------------------------ risers */
  function riserPath(ax, ay, ex, ey, style) {
    const yb = Math.max(ay + 20, ey - 55);
    if (style === 's_shape') {
      const dx = ex - ax, dy = ey - ay;
      return `M${ax} ${ay}C${ax} ${ay + dy * .7} ${ax + dx * .8} ${ay + dy * .3} ${ax + dx * .5} ${ay + dy * .5}`
        + `S${ex} ${ey - dy * .7} ${ex} ${ey}`;
    }
    if (style === 'flex' || style === 'lazywave') {
      const dy = ey - ay;
      return `M${ax} ${ay}C${ax} ${ay + dy * 0.5} ${ax + 70} ${ay + dy * 0.3} ${ax + 60} ${ay + dy * 0.62}S${ex - 50} ${ey} ${ex} ${ey}`;
    }
    const c2x = ax + (ex - ax) * 0.5;
    return `M${ax} ${ay}V${yb}C${ax} ${yb + 45} ${c2x} ${ey} ${Math.min(ex, c2x + 70)} ${ey}H${ex}`;
  }

  /* ================================================================== BUILD === */
  const TAGS = { valve_gate: 'HV', valve_ball: 'HV', valve_check: 'NRV', choke: 'CHK', esdv: 'XV', ssiv: 'XV', valve_control: 'FCV', valve_xov: 'XOV', mpp: 'P', srp: 'P', wgc: 'K', separator: 'V', hx: 'E', mpfm: 'FT', pt_sensor: 'PT', tt_sensor: 'TT', sand_detector: 'SD' };
  const SENSORS = new Set(['pt_sensor', 'tt_sensor', 'sand_detector']);
  const TAGDY = { separator: 40, mpfm: 34, hx: 26, mpp: 24, srp: 24, wgc: 24 };
  const cx0 = (c, w) => c.x + w / 2;

  function componentScale(override) {
    const scale = num(override.scale, 1);
    return Number.isFinite(scale) && scale > 0 ? scale : 1;
  }

  function componentTransform(c, override, x, y) {
    const scale = componentScale(override);
    return `translate(${x + (override.dx || 0)} ${y + (override.dy || 0)})`
      + (scale === 1 ? '' : ` translate(${c.x} ${c.L.P}) scale(${scale}) translate(${-c.x} ${-c.L.P})`);
  }

  function equipmentPortLayout(c, item, width, uses) {
    if (item.riserDetail) return root.SubseaRiserDetail.ports(item, c, width);
    if (item.type === 'custom_element') return [];
    const end = item.type === 'plet' ? 72 : width;
    const riser = item.type === 'riser_base' || item.type === 'riser_skid';
    if (riser) uses += (item.servicePorts ? 'S' : '') + (item.umbilicalPorts ? 'U' : '');
    const config = item.portConfig, ports = [];
    if (config && (!['P', 'S', 'U'].includes(config.lane) || !['additional', 'replace'].includes(config.mode)
      || !['inlets', 'outlets'].every((side) => Number.isInteger(config[side]) && config[side] >= 0 && config[side] <= EQUIPMENT_OPTIONS.maxPorts))) {
      throw new Error(`Invalid inlet/outlet port configuration on ${item.id}. Counts must be whole numbers from 0 to ${EQUIPMENT_OPTIONS.maxPorts}.`);
    }
    // Keep optional pairs clear of every custom hub row, including process hubs.
    const customBottom = config ? c.L[config.lane]
      + Math.max(0, Math.max(config.inlets, config.outlets) - (config.mode === 'replace' ? 1 : 0)) * 26 : c.L.P;
    const serviceY = Math.max(c.L.S, customBottom + 26);
    const umbilicalY = Math.max(c.L.U, (item.servicePorts ? serviceY : customBottom) + 26);
    if (riser && item.riserPorts) {
      let row = c.L.P;
      for (const lane of ['P', 'S', 'U']) {
        const counts = item.riserPorts[lane];
        if (!counts || !['inlets', 'outlets'].every((side) => Number.isInteger(counts[side])
          && counts[side] >= 0 && counts[side] <= EQUIPMENT_OPTIONS.maxPorts)) throw new Error('Invalid independent service hub counts.');
        for (const [side, short, boundary, direction] of [['inlets', 'in', 'left', -1], ['outlets', 'out', 'right', 1]]) {
          for (let index = 0; index < counts[side]; index++) ports.push({
            id: index === 0 ? `${lane}-${boundary}` : `${lane}-${short}-${index}`, lane,
            x: direction < 0 ? c.x + 10 : c.x + end - 10, y: row + index * 26,
            direction, label: `${lane} ${short === 'in' ? 'inlet' : 'outlet'} ${index + 1}`,
            custom: true, internal: true, edgeX: direction < 0 ? c.x + 28 : c.x + end - 28,
            edgeY: row + index * 26,
          });
        }
        row += Math.max(counts.inlets, counts.outlets) * 26;
      }
    }
    ['P', 'S', 'U'].filter((lane) => !(riser && item.riserPorts) && (item.type === 'plet' ? (item.pletPorts || 'PSU').includes(lane) : uses.includes(lane))).forEach((lane) => {
      if (config && config.mode === 'replace' && config.lane === lane) return;
      const y = riser && lane !== 'P' ? (lane === 'S' ? serviceY : umbilicalY) : c.L[lane];
      const internal = riser && (lane !== 'P' || item.internalRoutes !== undefined);
      [['left', c.x, -1], ['right', c.x + end, 1]].forEach(([side, x, direction]) =>
        ports.push({ id: `${lane}-${side}`, lane, x: internal ? x - direction * 10 : x,
          y, direction, label: riser && lane !== 'P' ? `${lane} ${side === 'left' ? 'in' : 'out'}` : `${lane} ${side}`,
          ...(internal ? { custom: true, internal: true, edgeX: x - direction * 28, edgeY: y } : {}),
          ...(item.type === 'plet' ? { standard: true } : {}) }));
    });
    if (config && !(riser && item.riserPorts)) {
      const lane = config.lane;
      const internal = item.type === 'riser_base' || item.type === 'riser_skid';
      [['inlets', 'in', 'left', -1], ['outlets', 'out', 'right', 1]].forEach(([side, short, boundary, direction]) => {
        const edgeX = direction < 0 ? c.x : c.x + end;
        const count = config[side];
        for (let index = 0; index < count; index++) {
          const first = config.mode === 'replace' && index === 0;
          const number = config.mode === 'replace' ? index : index + 1;
          ports.push({
            id: first ? `${lane}-${boundary}` : `${lane}-${short}-${number}`, lane,
            x: internal ? edgeX - direction * 10 : edgeX + (first ? 0 : direction * 30),
            y: c.L[lane] + (first ? 0 : number * 26),
            direction, label: `${short === 'in' ? 'Inlet' : 'Outlet'} ${index + 1}`, custom: true,
            internal, edgeX: internal ? edgeX - direction * 28 : edgeX, edgeY: c.L[lane],
          });
        }
      });
    }
    return ports.filter((port) => !(riser && item.bundleServiceInlet && port.id === 'S-left')).map((port) => {
      const settings = (item.portOverrides || {})[port.id] || {};
      const connectionType = assignedPortService(item, port.id);
      const service = CONNECTION_TYPES[connectionType];
      const lane = item.type === 'plet' && service ? serviceLane(service) : (settings.lane || port.lane);
      return { ...port, lane,
        connectionType: connectionType || (riser && item.bundleServiceInlet && port.id === 'U-left' ? 'umbilical_static' : ''),
        label: settings.label || (riser && item.bundleServiceInlet && port.id === 'U-left'
          ? 'U + chemical inlet' : port.label),
        custom: port.custom || (riser && item.internalRoutes !== undefined) || !!settings.connectionType || (item.type === 'plet' && !!(settings.label || settings.lane)), edgeX: port.edgeX ?? port.x,
        edgeY: port.edgeY ?? port.y };
    });
  }

  function connectionPorts(c, item, width, uses) {
    return equipmentPortLayout(c, item, width, uses).map((port) => {
      const vertical = port.axis === 'y';
      const hardware = port.detail ? `<g class="custom-hub" data-hub="${esc(port.id)}">`
        + conn(port.x, port.y, vertical ? 90 : 0)
        + txt(port.x + (vertical ? 0 : port.direction * 8), port.y + (vertical ? port.direction * 12 : -7),
          port.label, { size: 7, anchor: vertical ? 'middle' : port.direction < 0 ? 'end' : 'start', c: T.mute }) + '</g>'
        : port.standard && port.custom
        ? txt(port.x - port.direction * 8, port.y - 7, port.label, {
          size: 7, anchor: port.direction < 0 ? 'start' : 'end',
          c: port.connectionType ? serviceStyle(CONNECTION_TYPES[port.connectionType]).c : laneColor(port.lane) })
        : port.custom
        ? `<g class="${port.standard ? 'lane-hub' : 'custom-hub'}" data-hub="${port.id}">`
          + (item.riserPorts || item.internalRoutes !== undefined
            || (item.bundleServiceInlet && ['S-right', 'U-left', 'U-right'].includes(port.id)) ? ''
            : path(`M${port.edgeX} ${port.edgeY}V${port.y}H${port.x}`, { c: port.connectionType ? serviceStyle(CONNECTION_TYPES[port.connectionType]).c : laneColor(port.lane), w: 1.8, pipeLane: port.lane }))
          + conn(port.x, port.y)
          + txt(port.x + port.direction * (port.internal ? -8 : 8), port.y - 7, port.label, {
            size: 7, anchor: (port.direction < 0) !== !!port.internal ? 'end' : 'start' }) + '</g>' : '';
      return hardware + `<g class="connection-port" data-port="${port.id}" data-lane="${port.lane}" data-axis="${port.axis || 'x'}" data-connection-type="${esc(port.connectionType)}" data-direction="${port.direction}" data-label="${esc(port.label)}" data-x="${port.x}" data-y="${port.y}">`
        + `<title>${esc(port.label)}: ${port.lane}${port.connectionType ? ' / ' + esc(CONNECTION_TYPES[port.connectionType].label) : ''} connection</title><circle cx="${port.x}" cy="${port.y}" r="11" fill="transparent" class="port-hit"/>`
        + `<circle cx="${port.x}" cy="${port.y}" r="5" fill="#fff" stroke="#00A878" stroke-width="2" vector-effect="non-scaling-stroke"/></g>`;
    }).join('');
  }

  function hostSymbol(type, item, x, L, act) {
    const host = HOSTS[type];
    const drawing = host.draw({ x, top: L.U + 16 - host.h, spec: item, L });
    if (['jacket', 'platform', 'fpso', 'semisub', 'tlp', 'spar'].includes(type) && item.label) {
      drawing.svg += elementLabel(x + drawing.w / 2, L.U + 16 - host.h - 18, item.label, item, { size: 11, bold: true });
    }
    if (CUR_SPEC.professionalAppearance && item.tag && !drawing.svg.includes('class="equipment-tag"')) {
      const scale = componentScale((CUR_SPEC.overrides || {})[item.id] || {});
      drawing.svg += `<g class="equipment-tag">${txt(x + drawing.w / 2, L.U + 16 - host.h - 8,
        item.tag, { size: 7.5 / scale, font: SANS, c: T.mute })}</g>`;
    }
    if (item.showJTubes && ['jacket', 'platform'].includes(type)) {
      const direction = item.jTubeSide === 'right' ? 1 : -1;
      const count = drawing.anchors.length, spacing = Math.min(8, 40 / Math.max(1, count - 1));
      const center = x + 70, seabed = L.U + 16;
      const top = seabed - host.h + 22;
      const baseHalf = type === 'jacket' ? 56 : 39;
      drawing.anchors = drawing.anchors.map((deck, index) => {
        const vertical = center + (index - (count - 1) / 2) * spacing;
        const bottom = seabed - 8 - (direction < 0 ? count - 1 - index : index) * spacing;
        const mouth = { x: center + direction * (baseHalf + 18), y: bottom, direction };
        const bendTop = seabed - Math.min(90, host.h * .4) - count * spacing;
        const d = `M${vertical} ${top}V${bendTop}`
          + `C${vertical} ${bottom - 18} ${vertical + direction * 24} ${bottom} ${mouth.x} ${bottom}`;
        drawing.svg += `<g class="j-tube-guide" data-tube="${index}">`
          + `<path class="j-tube-wall" d="${d}" fill="none" stroke="${T.ink}" stroke-width="6" stroke-linejoin="round"/>`
          + `<path class="j-tube-bore" d="${d}" fill="none" stroke="${T.paper}" stroke-width="4.4" stroke-linejoin="round"/>`
          + `<g class="j-tube-pulled"></g></g>`;
        return mouth;
      });
      if (drawing.anchors.length && direction > 0) drawing.w = Math.max(drawing.w, drawing.anchors[0].x - x + 14);
    }
    const ports = ['P', 'S', 'U'].filter(() => drawing.anchors.length || host.noRisers).map((lane, index) => {
      const anchor = drawing.anchors[Math.min(index, drawing.anchors.length - 1)];
      const point = anchor || { x: x + (type === 'tieback' ? 92 : drawing.w), y: L[lane] };
      return `<g class="connection-port${anchor ? ' legacy-host-port' : ''}" data-port="${lane}-right" data-lane="${lane}" data-x="${point.x}" data-y="${point.y}"${anchor ? ' data-host-slot="true"' : ''}>`
        + `<title>${lane} host connection</title><circle cx="${point.x}" cy="${point.y}" r="11" fill="transparent" class="port-hit"/>`
        + `<circle cx="${point.x}" cy="${point.y}" r="5" fill="#fff" stroke="#00A878" stroke-width="2" vector-effect="non-scaling-stroke"/></g>`;
    }).join('');
    const tubes = drawing.anchors.map((point, index) => {
      const label = slotsOf(item)[index] || `J${index + 1}`;
      return `<g class="connection-port j-tube-port" data-port="J-${index}" data-lane="any" data-host-slot="true"${point.direction ? ` data-direction="${point.direction}" data-tube-mouth="true"` : ''} data-label="${esc(label)}" data-x="${point.x}" data-y="${point.y}">`
        + `<title>J-tube ${esc(label)}: drag a riser here</title>`
        + `<circle cx="${point.x}" cy="${point.y}" r="11" fill="transparent" class="port-hit"/>`
        + `<circle cx="${point.x}" cy="${point.y}" r="5" fill="#fff" stroke="#00A878" stroke-width="2" vector-effect="non-scaling-stroke"/>`
        + txt(point.x + (point.direction || 0) * 7, point.y + (point.direction ? -4 : 21), label,
          { size: point.direction ? 7 : 9, bold: true, anchor: point.direction === -1 ? 'end' : point.direction === 1 ? 'start' : 'middle' }) + '</g>';
    }).join('');
    return { ...drawing, svg: drawing.svg + ports + tubes };
  }

  function defsSvg() {
    const css = `.flow{display:none;fill:none;stroke-linecap:round;pointer-events:none}svg.anim .flow{display:inline;stroke-dasharray:1 11;animation:flowdash calc(var(--d,1.6s)/var(--spd,1)) linear infinite}svg.anim .flow.rev{animation-direction:reverse}@keyframes flowdash{to{stroke-dashoffset:-12}}`;
    const polished = CUR_SPEC.professionalAppearance === true;
    return `<defs><style>${css}</style><pattern id="hatch" width="${polished ? 6 : 4}" height="${polished ? 6 : 4}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="${polished ? 6 : 4}" height="${polished ? 6 : 4}" fill="${T.paper}"/><line x1="0" y1="0" x2="0" y2="${polished ? 6 : 4}" stroke="${polished ? T.mute : T.ink}" stroke-width="${polished ? .65 : 1.3}"/></pattern>`
      + `<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${T.zone}"/></marker></defs>`;
  }

  function buildTrain(spec, tr, sh, L) {
    const ox = 0;
    const seabed = L.U + 16;
    const hs = tr.host || null;
    const host = hs ? (HOSTS[hs.type] || HOSTS.jacket) : { h: 0, noRisers: true };
    const hostId = hs && (hs.id || `host_${tr.id || 'main'}`);
    const hostOverride = sh.ov[hostId] || {};
    const hostSpec = Object.assign({}, hs, hostOverride.label === undefined ? {} : { label: hostOverride.label });
    const hostAct = { P: true, S: !(tr.lanes && tr.lanes.S === false), U: !(tr.lanes && tr.lanes.U === false) };
    const hi = hs ? hostSymbol(hs.type, hostSpec, 0, L, hostAct) : { svg: '', w: 0, anchors: [] };
    let cursor = hi.w + num(tr.gap, hs ? 40 : 0);
    const ov = sh.ov;
    const act = { P: true, S: !(tr.lanes && tr.lanes.S === false), U: !(tr.lanes && tr.lanes.U === false) };
    const laneStart = { P: cursor, S: act.S ? cursor : null, U: act.U ? cursor : null };
    const layers = { lanes: '', nodes: '' };
    (tr.chain || []).forEach((raw, idx) => {
      const it = Object.assign({}, raw);
      const id = it.id || `${it.type}_${idx}`;
      it.id = id;
      const o = ov[id] || {};
      if (o.label !== undefined) it.label = o.label;
      if (o.hidden) { sh.meta[id] = { x: ox + cursor, w: 0, type: it.type, hidden: true, train: tr.id }; return; }
      const c = { x: cursor, L, act: Object.assign({}, act), idx };
      for (const connection of spec.connections || []) {
        if (connection.from === id || connection.to === id) c.act[connection.lane || 'P'] = true;
      }
      const lk = LINK[it.type], nd = it.lane && GEN[it.type] ? genNode(Object.assign({}, GEN[it.type], { lane: it.lane })) : NODE[it.type];
      let w, svg, kind, internalPipes = [];
      if (lk) {
        kind = 'link'; w = linkWidth(it);
        if (spec.lineNumbers !== false && (it.pId || it.pKm) && (it.pStyle || lk.pStyle) !== 'none') {
          sh.lineCount += 1;
          it._lineNo = `${it.pId ? it.pId + '"-' : ''}P-${String(100 + sh.lineCount).padStart(3, '0')}${spec.lineClass ? '-' + spec.lineClass : ''}`;
        }
        svg = drawLink(c, it, lk) + connectionPorts(c, it, w, 'PSU');
        const baseX = hi.w + 100 + (idx % 4) * 300;
        const baseY = 120 + Math.floor(idx / 4) * 220;
        const fx = spec.freeform ? (it.x === undefined ? baseX : it.x) - cursor : 0;
        const fy = spec.freeform ? (it.y === undefined ? baseY : it.y) - L.P : 0;
        const tf = ` transform="${componentTransform(c, o, fx, fy)}"`;
        const pos = spec.freeform ? ` data-canvas-x="${it.x === undefined ? baseX : it.x}" data-canvas-y="${it.y === undefined ? baseY : it.y}"` : '';
        layers.lanes += `<g class="el link" data-id="${esc(id)}" data-type="${esc(it.type)}"${pos}${tf}>${svg}</g>`;
      } else if (nd || HOSTS[it.type]) {
        if (HOSTS[it.type]) {
          const drawing = hostSymbol(it.type, it, cursor, L, act);
          kind = 'host'; w = drawing.w; svg = drawing.svg;
        } else {
          kind = 'node'; w = nd.w(it);
          const pre = TAGS[it.type];
          if (spec.professionalAppearance && SENSORS.has(it.type) && it.tag) {
            const number = new RegExp(`^${pre}-(\\d+)$`).exec(it.tag);
            if (number) it._num = number[1];
          }
          if (pre && spec.autoTag !== false && it.tag === undefined) { sh.tagCount[pre] = (sh.tagCount[pre] || 100) + 1; it._num = sh.tagCount[pre]; if (!SENSORS.has(it.type)) it.tag = `${pre}-${it._num}`; }
          const previousFluid = CUR_P;
          const inletType = it.type !== 'plet' && (it.portOverrides || {})['P-left']?.connectionType;
          if (inletType) CUR_P = serviceStyle(CONNECTION_TYPES[inletType]);
          const previousDraw = INTERNAL_DRAW;
          const trace = { counts: {}, pipes: [], valves: 0 };
          INTERNAL_DRAW = trace;
          try {
            svg = nd.draw(c, it);
            CUR_P = previousFluid;
            const uses = it.type === 'plet' ? (it.pletPorts || 'PSU') : (nd.uses || 'P');
            svg += connectionPorts(c, it, w, uses);
            internalPipes = trace.pipes;
          } finally {
            INTERNAL_DRAW = previousDraw;
            CUR_P = previousFluid;
          }
          if (it.tag && !(spec.professionalAppearance && svg.includes('class="equipment-tag"'))) {
            svg += `<g class="equipment-tag">${txt(cx0(c, w), c.L.P + (TAGDY[it.type] || 22), it.tag, { size: 7.5, bold: true })}</g>`;
          }
          const uses = it.type === 'plet' ? (it.pletPorts || 'PSU') : (nd.uses || 'P');
          const customRiser = ['riser_base', 'riser_skid'].includes(it.type) && (it.riserDetail || it.riserPorts || it.internalRoutes !== undefined || it.bundleServiceInlet);
          if (!spec.freeform && !customRiser) ['P', 'S', 'U'].forEach((l) => { if (act[l] && !uses.includes(l)) layers.lanes += seg(c, l, cursor, cursor + w); });
        }
        const baseX = hi.w + 100 + (idx % 4) * 300;
        const baseY = 120 + Math.floor(idx / 4) * 220;
        const independent = spec.freeform || !!HOSTS[it.type];
        const fx = independent ? (it.x === undefined ? baseX : it.x) - cursor : 0;
        const fy = independent ? (it.y === undefined ? baseY : it.y) - L.P : 0;
        const tf = componentTransform(c, o, fx, fy);
        const pos = spec.freeform ? ` data-canvas-x="${it.x === undefined ? baseX : it.x}" data-canvas-y="${it.y === undefined ? baseY : it.y}"` : '';
        layers.nodes += `<g class="el node" data-id="${esc(id)}" data-type="${esc(it.type)}"${pos}${tf ? ` transform="${tf}"` : ''}>${svg}</g>`;
        (nd && nd.open ? nd.open(it) : []).forEach((l) => { if (!act[l]) { act[l] = true; laneStart[l] = cursor + (nd.openX ? nd.openX(it) : 0); } });
        (nd && nd.close ? nd.close(it) : []).forEach((l) => { act[l] = false; });
      } else { sh.meta[id] = { x: ox + cursor, w: 0, type: it.type, unknown: true, train: tr.id }; return; }
      sh.meta[id] = { x: ox + cursor, w, type: it.type, kind, train: tr.id, internalPipes };
      cursor += w;
    });
    const endX = cursor;

    let risers = '';
    if (hs && !host.noRisers && !hostOverride.hidden) {
      (hs.risers || []).forEach((r, index) => {
        const a = hi.anchors[Math.min(num(r.slot, 0), hi.anchors.length - 1)];
        if (!a) return;
        const lane = r.lane || 'P';
        const ex = laneStart[lane] !== null && laneStart[lane] !== undefined ? laneStart[lane] : laneStart.P;
        const col = r.color === 'yellow' ? T.yellow : r.color === 'red' ? PC() : r.color === 'green' ? T.green : r.color === 'blue' ? T.blue : (lane === 'U' ? T.yellow : laneColor(lane));
        const flex = r.style === 'flex' || r.style === 'lazywave';
        const route = riserPath(a.x + num(r.dx, 0), a.y, ex, L[lane], r.style);
        risers += `<g data-riser-host="${esc(hostId)}" data-riser-index="${index}" data-ax="${a.x + num(r.dx, 0)}" data-ay="${a.y}" data-ex="${ex}" data-ey="${L[lane]}" data-style="${esc(r.style || '')}">`
          + `<path class="legacy-riser-hit" d="${route}" fill="none" stroke="transparent" stroke-width="12" pointer-events="stroke"/>`
          + path(route, { c: col, w: num(r.width, lane === 'P' ? 2.2 : 1.9), dash: flex ? '10 3' : (lane === 'P' ? CUR_P.dash : T.dash && T.dash[lane]), cap: 'butt', flow: lane }) + '</g>';
        if (r.label) {
          const lx = r.lx !== undefined ? r.lx : (lane === 'U' ? (a.x + ex) / 2 + 20 : a.x + num(r.ldx, 7));
          const ly = r.ly !== undefined ? r.ly : (lane === 'U' ? L[lane] + 18 : a.y + (L.P - a.y) * 0.38);
          risers += txt(lx, ly, r.label, { size: 8.5, bold: true, c: col, anchor: lane === 'U' ? 'middle' : 'start' });
        }
      });
    }
    const sea = tr._main && spec.showSeabed ? line(hi.w - 10, seabed + 2, endX + 20, seabed + 2, { c: '#b59f72', w: 1.4, dash: '8 4' }) + txt(endX + 24, seabed + 6, 'Seabed', { size: 8.5, c: '#b59f72', anchor: 'start' }) : '';
    const hostSvg = hs && !hostOverride.hidden
      ? `<g class="host el node" data-id="${esc(hostId)}" data-type="${esc(hs.type)}" transform="${componentTransform({ x: 0, L }, hostOverride, 0, 0)}">${hi.svg}</g>` : '';
    return { inner: `${sea}${layers.lanes}${risers}${hostSvg}${layers.nodes}`, endX, hostW: hi.w };
  }

  function flowFor(tr, spec) {
    const fl = tr.fluid || 'production';
    const m = tr.flow || spec.flow || 'auto';
    const base = m === 'none' ? 'none' : m === 'forward' ? 'fwd' : m === 'reverse' ? 'rev' : (fl === 'production' ? 'rev' : 'fwd');
    const d = FLOWD[fl] || 1.6;
    return { P: { mode: base, d }, S: { mode: m === 'none' ? 'none' : 'fwd', d: 3.2 }, U: { mode: m === 'none' ? 'none' : 'fwd', d: 4.5 } };
  }

  function build(spec) {
    T = Object.assign({}, THEMES[spec.themeName] || THEMES.consulting, spec.theme || {});
    registerCustom(spec.customSymbols);
    const lg = num(spec.laneGap, 34);
    const L = { P: 0, S: lg, U: lg + 16 };
    const trains = [{ id: 'main', _main: true, host: spec.host, chain: spec.chain, lanes: spec.lanes, gap: spec.gap, fluid: spec.fluid }]
      .concat((spec.branches || []).map((b, i) => Object.assign({ id: `b${i + 1}` }, b)));
    CUR_SPEC = spec;
    const sh = { tagCount: {}, lineCount: 0, ov: spec.overrides || {}, meta: {}, trainInfo: {}, fluids: [] };
    let body = '', conns = '', prevY = 0;
    const rejoin = [];
    trains.forEach((tr, ti) => {
      const fl = tr.fluid || 'production';
      if (!sh.fluids.includes(fl)) sh.fluids.push(fl);
      CUR_P = fluidStyle(fl);
      CUR_FLOW = flowFor(tr, spec);
      MIRROR = !!tr.mirror;
      const r = buildTrain(spec, tr, sh, L);
      const W = r.endX + 20, mir = MIRROR;
      const offset = (spec.trainOffsets || {})[tr.id] || {};
      let ox = num(offset.dx, 0), oy = num(offset.dy, 0);
      const f = tr.from, pm = f && sh.meta[f.item];
      if (pm) {
        const pi = sh.trainInfo[pm.train], side = f.side === 'up' ? -1 : 1;
        const px = pm.x + pm.w / 2 + num(f.dx, 0), py = pi.oy + L.P;
        oy = pi.oy + side * num(tr.dy, 240) + num(offset.dy, 0);
        ox = (tr.host ? num(tr.x, px + (mir ? -60 - W : 60)) : (mir ? px - 44 - W : px + 44)) + num(offset.dx, 0);
        const by = oy + L.P, rr = 8, ex = mir ? ox + W : ox, sg = mir ? -1 : 1;
        const cm = flowFor({ fluid: fl, flow: tr.flow }, spec);
        CUR_FLOW = cm; MIRROR = false;
        conns += path(`M${px} ${py}V${by - side * rr}Q${px} ${by} ${px + sg * rr} ${by}H${ex}`, { c: CUR_P.c, w: 2.4, dash: CUR_P.dash, flow: 'P' })
          + circ(px, py, 2.8, { fill: CUR_P.c, c: CUR_P.c, w: 0.5 });
        if (f.valve !== false) conns += valve(px, (py + by) / 2, { rot: 90, s: 5.5 });
        if (f.label) conns += txt(px + 8, (py + by) / 2 - 8, f.label, { size: 8.5, anchor: 'start', c: T.mute });
      } else if (ti > 0) { oy = prevY + num(tr.dy, 360) + num(offset.dy, 0); ox = num(tr.x, 0) + num(offset.dx, 0); }
      prevY = oy;
      sh.trainInfo[tr.id] = { ox, oy, hostW: r.hostW, endX: r.endX, W, mir };
      Object.keys(sh.meta).forEach((k) => { const m = sh.meta[k]; if (m.train === tr.id && !m._abs) { m.x = mir ? ox + W - (m.x + m.w) : ox + m.x; m._abs = true; } });
      body += `<g class="train${mir ? ' mir' : ''}" data-train="${esc(tr.id)}" data-mir="${mir ? 1 : 0}" transform="translate(${mir ? ox + W : ox} ${oy})${mir ? ' scale(-1 1)' : ''}">${r.inner}</g>`;
      if (tr.to) rejoin.push({ tr, fl, mir, ox, oy, W, endX: r.endX });
    });
    MIRROR = false;
    rejoin.forEach((j) => {
      const t = j.tr.to, tm = sh.meta[t.item];
      if (!tm) return;
      CUR_P = fluidStyle(j.fl);
      CUR_FLOW = flowFor({ fluid: j.fl, flow: t.flow || j.tr.flow }, spec);
      const ti = sh.trainInfo[tm.train], side = t.side === 'up' ? -1 : 1;
      const sx = j.mir ? j.ox : j.ox + j.endX, sy = j.oy + L.P;
      const tx = tm.x + tm.w / 2 + num(t.dx, 0), ty = ti.oy + L.P, r2 = 8;
      const dir = tx >= sx ? 1 : -1;
      const pd = `M${sx} ${sy}H${tx - dir * r2}Q${tx} ${sy} ${tx} ${sy + (ty > sy ? r2 : -r2)}V${ty}`;
      conns += path(pd, { c: CUR_P.c, w: 2.4, dash: CUR_P.dash, flow: 'P' }) + circ(tx, ty, 2.8, { fill: CUR_P.c, c: CUR_P.c, w: 0.5 });
      if (t.valve !== false) conns += valve(tx, (sy + ty) / 2, { rot: 90, s: 5.5 });
      if (t.label) conns += txt(tx + 8, (sy + ty) / 2 - 8, t.label, { size: 8.5, anchor: 'start', c: T.mute });
    });
    CUR_FLOW = { P: { mode: 'fwd', d: 1.6 }, S: { mode: 'fwd', d: 3.2 }, U: { mode: 'fwd', d: 4.5 } };

    const zoneGeometry = {};
    (spec.zones || []).forEach((z, index) => {
      if (z.distanceM !== undefined) return;
      if (spec.freeform) return;
      const m1 = sh.meta[z.from], m2 = sh.meta[z.to || z.from];
      if (!m1 || !m2) return;
      const ti = sh.trainInfo[m1.train], zy = ti.oy + L.P - num(spec.zoneY, 56);
      let x1 = z.fromHost ? (ti.mir ? ti.ox + ti.W - ti.hostW : ti.ox + ti.hostW) : m1.x, x2 = m2.x + m2.w;
      if (ti.mir) { x1 = z.fromHost ? x1 : m1.x + m1.w; x2 = m2.x; }
      if (x1 > x2) { const t = x1; x1 = x2; x2 = t; }
      zoneGeometry[index] = { left: x1, right: x2, y: zy, bottom: ti.oy + L.U + 44 };
    });
    CUR_P = fluidStyle('production');
    return { defs: defsSvg(), content: '<g id="design-zones"></g>' + conns + body, meta: sh.meta, fluids: sh.fluids, L, zoneGeometry };
  }

  /* ============================================================== DECOR ===== */
  function legend(x, y, fluids, connections, spec) {
    const t8 = { size: 8.5, anchor: 'start', halo: false };
    const rows = (fluids && fluids.length ? fluids : ['production']).map((f) => ({ label: (FLUIDS[f] || f) + ' line', lane: 'P', st: fluidStyle(f) }))
      .concat([{ label: 'Service / chemical line', lane: 'S', st: { c: laneColor('S'), dash: T.dash && T.dash.S } },
        { label: 'Static umbilical', lane: 'U', st: { c: laneColor('U'), dash: T.dash && T.dash.U } },
        { label: 'Dynamic umbilical', lane: 'U', st: serviceStyle(CONNECTION_TYPES.umbilical_dynamic) }]);
    [...new Set((connections || []).map((connection) => connection.connectionType).filter(Boolean))].forEach((type) => {
      const style = connectionAppearance({ connectionType: type }, spec);
      rows.push({ label: style.label, lane: 'P', st: style });
    });
    let s = txt(x, y, 'LEGEND', { size: 8.5, bold: true, anchor: 'start', c: T.mute, halo: false }) + line(x, y + 4, x + 330, y + 4, { c: T.zone, w: 0.6 });
    rows.forEach((r, i) => {
      const yy = y + 18 + i * 14;
      const col = r.riser ? T.yellow : r.st ? r.st.c : laneColor(r.lane);
      const dash = r.riser ? undefined : r.st ? r.st.dash : (T.dash && T.dash[r.lane]);
      s += line(x, yy, x + 34, yy, { c: col, w: r.lane === 'P' ? 2.4 : 1.8, dash }) + txt(x + 42, yy + 3, r.label, t8);
    });
    const yi = y + 18 + rows.length * 14;
    s += circ(x + 15, yi, 6.5, { fill: T.paper, w: 1 }) + line(x + 8.5, yi, x + 21.5, yi, { w: 0.6 }) + txt(x + 42, yi + 3, 'Instrument (ISA bubble)', t8);
    const x2 = x + 190;
    s += valve(x2 + 12, y + 20, { s: 5.5 }) + txt(x2 + 30, y + 23, 'Gate valve', t8);
    s += valve(x2 + 12, y + 50, { kind: 'esdv', s: 5.5 }) + txt(x2 + 30, y + 53, 'Fail-closed actuated valve', t8);
    s += conn(x2 + 12, y + 68) + txt(x2 + 30, y + 71, 'ISO flange / hub', t8);
    s += hatch(x2 + 2, y + 79, 20, 8, { w: 1 }) + txt(x2 + 30, y + 87, 'Spool / SDU / UTA', t8);
    s += rect(x2 + 2, y + 93, 20, 7, { dash: '3 3', w: 1 }) + txt(x2 + 30, y + 100, 'Subsea structure', t8);
    return { svg: s, h: Math.max(yi - y + 22, 112) };
  }
  function notesBlock(x, y, notes) {
    if (!notes || !notes.length) return '';
    let s = txt(x, y, 'NOTES', { size: 8.5, bold: true, anchor: 'start', c: T.mute, halo: false }) + line(x, y + 4, x + 330, y + 4, { c: T.zone, w: 0.6 });
    notes.slice(0, 6).forEach((n, i) => { s += txt(x, y + 18 + i * 12.5, `${i + 1}.  ${n}`, { size: 8.5, anchor: 'start', halo: false }); });
    return s;
  }
  function titleBlock(x, y, spec) {
    const tb = Object.assign({ project: spec.title || 'Subsea field layout', drawing: 'Subsea layout – general arrangement', docNo: '', rev: 'A', sheet: '1 of 1', by: '', checked: '', date: new Date().toISOString().slice(0, 10), scale: 'NTS' }, spec.titleBlock || {});
    const w = 380, r = 21, h = r * 4;
    let s = rect(x, y, w, h, { w: 1.4 });
    for (let i = 1; i < 4; i++) s += line(x, y + i * r, x + w, y + i * r, { w: 0.7 });
    [[2, 190], [2, 285], [3, 190], [3, 285]].forEach(([row, cx]) => { s += line(x + cx, y + row * r, x + cx, y + (row + 1) * r, { w: 0.7 }); });
    const cell = (cx, row, k, v, bold) => txt(x + cx + 6, y + row * r + 8, k, { size: 5.8, anchor: 'start', c: T.mute, halo: false }) + txt(x + cx + 6, y + row * r + 17, v || '–', { size: bold ? 10.5 : 8.5, bold, anchor: 'start', halo: false });
    s += cell(0, 0, 'PROJECT', tb.project, true) + cell(0, 1, 'DRAWING', tb.drawing);
    s += cell(0, 2, 'DOCUMENT NO.', tb.docNo) + cell(190, 2, 'REV', tb.rev) + cell(285, 2, 'SHEET', tb.sheet);
    s += cell(0, 3, 'DRAWN / CHECKED', [tb.by, tb.checked].filter(Boolean).join(' / ')) + cell(190, 3, 'DATE', tb.date) + cell(285, 3, 'SCALE', tb.scale);
    return s;
  }
  function sheetFrame(x, y, w, h) {
    let s = rect(x, y, w, h, { w: 1.6 }) + rect(x + 8, y + 8, w - 16, h - 16, { w: 0.6 });
    const nc = Math.max(4, Math.round(w / 230)), nr = Math.max(3, Math.round(h / 170));
    for (let i = 0; i < nc; i++) {
      const cx = x + 8 + ((i + 0.5) * (w - 16)) / nc;
      s += txt(cx, y + 6.5, String(i + 1), { size: 6.5, c: T.mute, halo: false }) + txt(cx, y + h - 2, String(i + 1), { size: 6.5, c: T.mute, halo: false });
      if (i) { const lx = x + 8 + (i * (w - 16)) / nc; s += line(lx, y, lx, y + 8, { w: 0.6 }) + line(lx, y + h - 8, lx, y + h, { w: 0.6 }); }
    }
    for (let j = 0; j < nr; j++) {
      const cy = y + 8 + ((j + 0.5) * (h - 16)) / nr + 2.5, ch = String.fromCharCode(65 + j);
      s += txt(x + 4, cy, ch, { size: 6.5, c: T.mute, halo: false }) + txt(x + w - 4, cy, ch, { size: 6.5, c: T.mute, halo: false });
      if (j) { const ly = y + 8 + (j * (h - 16)) / nr; s += line(x, ly, x + 8, ly, { w: 0.6 }) + line(x + w - 8, ly, x + w, ly, { w: 0.6 }); }
    }
    return s;
  }

  /* ============================================================ INTERACTION === */
  function mount(el, spec, catalog) {
    const standaloneTemplate = document.documentElement.cloneNode(true);
    const initialView = JSON.parse(document.getElementById('initial-view').textContent);
    const byId = {}; (catalog || []).forEach((e) => { byId[e.id] = e; });
    const st = { spec: JSON.parse(JSON.stringify(spec)), sel: null };
    st.spec.overrides = st.spec.overrides || {};
    function assignHostIds() {
      const usedIds = new Set([st.spec, ...(st.spec.branches || [])].flatMap((train) =>
        [...(train.chain || []).map((item) => item.id), ...(train.host && train.host.id ? [train.host.id] : [])]));
      [st.spec, ...(st.spec.branches || [])].forEach((train, index) => {
        if (!train.host || train.host.id) return;
        let id = `host_${index + 1}`;
        while (usedIds.has(id)) id += '_host';
        train.host.id = id;
        usedIds.add(id);
      });
    }
    assignHostIds();
    const svg = el.querySelector('#svg');
    const insp = el.querySelector('#insp');
    const tip = el.querySelector('#tip');
    const palette = el.querySelector('#palette');
    const paletteList = el.querySelector('#palette-list');
    const paletteSearch = el.querySelector('#palette-search');
    const paletteCategory = el.querySelector('#palette-category');
    let vb = null, grid = !!spec.showGrid;
    let pendingType = null;
    let connectMode = false, connectStart = null, selectedConnection = null, selectedZone = null;
    let detailEditor = null, detailEditorId = null;
    let viewer3D = null, loading3D = null, wants3D = false;
    const zoneLayouts = new Map();
    const selectedIds = new Set();
    let layoutUndo = null, layoutAfter = '';
    let appearanceUndo = null, appearanceAfter = '';
    let updatePalette = () => {};
    let changeTimer;
    function notifyChange() {
      clearTimeout(changeTimer);
      changeTimer = setTimeout(() => {
        if (layoutUndo && JSON.stringify(st.spec) !== layoutAfter) {
          layoutUndo = null; el.querySelector('#b_undo_layout').disabled = true;
        }
        if (appearanceUndo && JSON.stringify(st.spec) !== appearanceAfter) {
          appearanceUndo = null; el.querySelector('#b_undo_improve').disabled = true;
        }
        if (!drag && !connectStart) window.dispatchEvent(new CustomEvent('subsea-change'));
      }, 100);
    }

    if (palette) {
      const entries = (catalog || []).filter((entry) => ['node', 'link', 'host'].includes(entry.kind))
        .concat((st.spec.customSymbols || []).map((symbol) => ({
          id: symbol.id, name: symbol.name || symbol.abbr || symbol.id,
          category: 'Custom', desc: 'Custom equipment symbol', kind: 'node',
        })));
      const categories = [...new Set(entries.map((entry) => entry.category || 'Other'))].sort();
      categories.forEach((category) => {
        const option = document.createElement('option');
        option.value = category; option.textContent = category;
        paletteCategory.appendChild(option);
      });
      updatePalette = function renderPalette() {
        const query = paletteSearch.value.trim().toLowerCase();
        const category = paletteCategory.value;
        const shown = entries.filter((entry) => (!category || (entry.category || 'Other') === category)
          && (!query || `${entry.name} ${entry.id} ${entry.desc || ''}`.toLowerCase().includes(query)));
        paletteList.innerHTML = shown.length ? shown.map((entry) =>
          `<button class="palette-item${pendingType === entry.id ? ' active' : ''}" draggable="true" data-type="${esc(entry.id)}">${esc(entry.name)}<small>${esc(entry.category || 'Custom')}</small></button>`
        ).join('') : '<div id="palette-empty">No matching symbols.</div>';
      }
      updatePalette();
      paletteSearch.addEventListener('input', updatePalette);
      paletteCategory.addEventListener('change', updatePalette);
      paletteList.addEventListener('click', (e) => {
        const button = e.target.closest('.palette-item');
        if (!button) return;
        if (!st.spec.freeform && !HOSTS[button.dataset.type]) {
          placeSymbol(button.dataset.type);
          return;
        }
        pendingType = button.dataset.type;
        svg.classList.add('placement');
        updatePalette();
      });
      paletteList.addEventListener('dragstart', (e) => {
        const button = e.target.closest('.palette-item');
        if (!button) return;
        pendingType = button.dataset.type;
        if (!st.spec.freeform) svg.classList.add('drop-target');
        e.dataTransfer.setData('text/plain', pendingType);
        e.dataTransfer.effectAllowed = 'copy';
      });
    }

    function placeSymbol(type, point) {
      selectedZone = null;
      const used = new Set([st.spec, ...(st.spec.branches || [])].flatMap((train) =>
        [...(train.chain || []).map((item) => item.id), ...(train.host ? [train.host.id] : [])]));
      let n = 1, id = `${type}_${n}`;
      while (used.has(id)) { n += 1; id = `${type}_${n}`; }
      st.spec.chain = st.spec.chain || [];
      if (st.spec.freeform || HOSTS[type]) {
        st.spec.chain.push({ type, id, installationStatus: 'New', x: Math.round(point.x), y: Math.round(point.y) });
      } else {
        st.spec.chain.push({ type, id, installationStatus: 'New' });
      }
      if (type === 'custom_element') Object.assign(st.spec.chain.at(-1), root.SubseaRiserDetail.blank());
      st.sel = id;
      selectedIds.clear(); selectedIds.add(id);
      pendingType = null;
      svg.classList.remove('placement', 'drop-target');
      render(st.spec.freeform || !!point);
      if (point && !st.spec.freeform) {
        const placed = svg.querySelector(`.el[data-id="${CSS.escape(id)}"]`);
        if (!placed) throw new Error(`Could not find newly placed symbol ${id}`);
        const bounds = placed.getBBox();
        const center = svg.createSVGPoint();
        center.x = bounds.x + bounds.width / 2;
        center.y = bounds.y + bounds.height / 2;
        const current = canvasPoint(placed, center.x, center.y);
        const override = st.spec.overrides[id] || (st.spec.overrides[id] = {});
        override.dx = Math.round(point.x - current.x);
        override.dy = Math.round(point.y - current.y);
        render(true);
      }
      fillInsp();
      updatePalette();
    }

    function findItem(id) {
      for (const train of [st.spec, ...(st.spec.branches || [])]) {
        if (train.host && train.host.id === id) return { item: train.host, train, host: true, chain: train.chain || (train.chain = []), index: -1 };
      }
      for (const chain of [st.spec.chain || [], ...(st.spec.branches || []).map((branch) => branch.chain || [])]) {
        const index = chain.findIndex((item) => item.id === id);
        if (index >= 0) return { chain, index, item: chain[index] };
      }
      return null;
    }

    function removeSelected() {
      if (selectedZone !== null) {
        st.spec.zones.splice(selectedZone, 1);
        selectedZone = null;
      } else if (selectedConnection !== null) {
        (st.spec.connections || []).splice(selectedConnection, 1);
        selectedConnection = null;
      } else if (st.sel) {
        const ids = selectedIds.size ? [...selectedIds] : [st.sel];
        for (const id of ids) {
          const found = findItem(id);
          if (!found) continue;
          if (found.host) found.train.host = null;
          else found.chain.splice(found.index, 1);
          st.spec.connections = (st.spec.connections || []).filter((connection) => connection.from !== id && connection.to !== id);
          st.spec.zones = (st.spec.zones || []).filter((zone) => zone.from !== id && zone.to !== id);
          delete st.spec.overrides[id];
        }
        st.sel = null; selectedIds.clear();
      } else return;
      render(true);
      fillInsp();
      updateSelectionControls();
    }

    function copySelected() {
      if (!st.sel || selectedConnection !== null) return;
      const found = findItem(st.sel);
      if (!found) return;
      const source = found.item, copy = JSON.parse(JSON.stringify(source));
      const used = new Set([st.spec, ...(st.spec.branches || [])].flatMap((train) =>
        [...(train.chain || []).map((item) => item.id), ...(train.host ? [train.host.id] : [])]));
      const stem = source.id || source.type;
      let n = 2;
      while (used.has(`${stem}_${n}`)) n += 1;
      copy.id = `${stem}_${n}`;
      copy.installationStatus = 'New';
      (copy.risers || []).forEach((riser) => { riser.installationStatus = 'New'; });
      if (source.tag !== undefined) delete copy.tag;
      const sourceOverride = st.spec.overrides[st.sel] || {};
      if (st.spec.freeform) {
        copy.x = num(source.x, 100) + 32;
        copy.y = num(source.y, 120) + 32;
        found.chain.push(copy);
        st.spec.overrides[copy.id] = Object.assign({}, sourceOverride);
      } else {
        if (found.host) found.chain.push(copy);
        else found.chain.splice(found.index + 1, 0, copy);
        st.spec.overrides[copy.id] = Object.assign({}, sourceOverride, {
          dx: num(sourceOverride.dx, 0) + 32, dy: num(sourceOverride.dy, 0) + 32,
        });
      }
      if (found.host) {
        delete copy.risers;
        const element = svg.querySelector(`.el[data-id="${CSS.escape(source.id)}"]`);
        const point = canvasPoint(element, 0, st.build.L.P);
        const train = element.closest('.train');
        const local = svg.createSVGPoint();
        local.x = point.x; local.y = point.y;
        const position = local.matrixTransform(train.getScreenCTM().inverse().multiply(svg.getScreenCTM()));
        copy.x = position.x + 32; copy.y = position.y + 32;
        st.spec.overrides[copy.id] = { ...sourceOverride, dx: 0, dy: 0 };
      }
      st.sel = copy.id;
      selectedIds.clear(); selectedIds.add(copy.id);
      render(true);
      fillInsp();
      updateSelectionControls();
    }

    function canvasPoint(itemElement, x, y) {
      const point = svg.createSVGPoint();
      point.x = x; point.y = y;
      // Remove the root viewBox/viewport transform: connectors use drawing units.
      return point.matrixTransform(svg.getScreenCTM().inverse().multiply(itemElement.getScreenCTM()));
    }

    function captureElements(ids) {
      return ids.map((id) => {
        const element = svg.querySelector(`.el[data-id="${CSS.escape(id)}"]`);
        const transform = element.transform.baseVal.consolidate();
        const matrix = transform ? transform.matrix : svg.createSVGMatrix();
        const box = element.getBBox(), a = canvasPoint(element, box.x, box.y), b = canvasPoint(element, box.x + box.width, box.y + box.height);
        return { id, element, matrix: { a: matrix.a, b: matrix.b, c: matrix.c, d: matrix.d, e: matrix.e, f: matrix.f },
          dx: num(st.spec.overrides[id]?.dx, 0), dy: num(st.spec.overrides[id]?.dy, 0),
          inv: element.closest('.train.mir') ? -1 : 1,
          box: { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) } };
      });
    }

    function moveElements(members, dx, dy, commit) {
      for (const member of members) {
        const m = member.matrix, x = dx * member.inv;
        member.element.setAttribute('transform', `matrix(${m.a} ${m.b} ${m.c} ${m.d} ${m.e + x} ${m.f + dy})`);
        if (commit) {
          const override = st.spec.overrides[member.id] || (st.spec.overrides[member.id] = {});
          override.dx = member.dx + x; override.dy = member.dy + dy;
        }
      }
    }

    function portsFor(itemElement, lane) {
      return Array.from(itemElement.querySelectorAll('.connection-port'))
        .filter((port) => !lane || lane === 'any' || port.dataset.lane === lane || port.dataset.lane === 'any')
        .map((port) => {
          const point = canvasPoint(itemElement, +port.dataset.x, +port.dataset.y);
          const direction = port.dataset.direction ? +port.dataset.direction : port.dataset.port.endsWith('left') ? -1 : 1;
          return {
            id: port.dataset.port, lane: port.dataset.lane, x: point.x, y: point.y,
            hostSlot: port.dataset.hostSlot === 'true', label: port.dataset.label,
            tubeMouth: port.dataset.tubeMouth === 'true',
            connectionType: port.dataset.connectionType || '',
            axis: port.dataset.axis || 'x',
            direction: port.dataset.axis !== 'y' && itemElement.closest('.train.mir') ? -direction : direction,
          };
        });
    }

    function nearestPort(itemElement, point, lane, portId) {
      const ports = portsFor(itemElement, lane).filter((port) => portId || !port.hostSlot || port.id.startsWith('J-'));
      if (portId) return ports.find((port) => port.id === portId) || null;
      return ports.reduce((best, port) => !best || Math.hypot(port.x - point.x, port.y - point.y)
        < Math.hypot(best.x - point.x, best.y - point.y) ? port : best, null);
    }

    function connectionEnds(connection, from, to) {
      const lane = connection.lane || 'P';
      // Older PLETs stored process-lane lines even when assigned chemical service.
      // Retain explicit attachments; new/reconnected endpoints still require matching lanes.
      const endpointPorts = (element, portId) => portsFor(element,
        portId && element.dataset.type === 'plet' ? null : lane);
      let best = null, distance = Infinity;
      for (const a of endpointPorts(from, connection.fromPort)) {
        if (connection.fromPort && a.id !== connection.fromPort) continue;
        for (const b of endpointPorts(to, connection.toPort)) {
          if (connection.toPort && b.id !== connection.toPort) continue;
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < distance) { best = { from: a, to: b }; distance = d; }
        }
      }
      return best;
    }

    function connectionPath(from, to) {
      if (from.hostSlot || to.hostSlot) return riserConnectionPath(from, to, 'rigid');
      if (from.axis === 'y' || to.axis === 'y') {
        const stub = (p) => ({ x: p.x + (p.axis === 'y' ? 0 : p.direction * 20),
          y: p.y + (p.axis === 'y' ? p.direction * 20 : 0) });
        const a = stub(from), b = stub(to);
        return `M${from.x} ${from.y}L${a.x} ${a.y}H${b.x}V${b.y}L${to.x} ${to.y}`;
      }
      const facing = from.direction && to.direction && from.direction !== to.direction
        && (to.x - from.x) * from.direction >= 0;
      if (from.direction && to.direction && !facing) {
        const ax = from.x + from.direction * 20, bx = to.x + to.direction * 20;
        const y = Math.max(from.y, to.y) + 60;
        return `M${from.x} ${from.y}H${ax}V${y}H${bx}V${to.y}H${to.x}`;
      }
      const midX = (from.x + to.x) / 2;
      return `M${from.x} ${from.y}H${midX}V${to.y}H${to.x}`;
    }

    function routedPath(connection, ends) {
      if (connection.waypoints && connection.waypoints.length) {
        if (connection.kind === 'riser') return curvedRiserRoute(connection, ends);
        return `M${ends.from.x} ${ends.from.y}` + connection.waypoints.map((p) => `L${p.x} ${p.y}`).join('')
          + `L${ends.to.x} ${ends.to.y}`;
      }
      if (connection.kind === 'riser' && connection.riserCurve === 'sweep' && ends.from.hostSlot) {
        return riserPath(ends.from.x, ends.from.y, ends.to.x, ends.to.y, connection.style);
      }
      return connection.kind === 'riser'
        ? riserConnectionPath(ends.from, ends.to, connection.style) : connectionPath(ends.from, ends.to);
    }

    function curvedRiserRoute(connection, ends) {
      const points = [ends.from, ...connection.waypoints, ends.to];
      let d = `M${points[0].x} ${points[0].y}`;
      if (!['flex', 'lazywave', 's_shape'].includes(connection.style)) {
        for (let index = 1; index < points.length - 1; index++) {
          const a = points[index - 1], b = points[index], c = points[index + 1];
          const before = Math.hypot(b.x - a.x, b.y - a.y), after = Math.hypot(c.x - b.x, c.y - b.y);
          const radius = Math.min(24, before / 3, after / 3);
          if (!radius) { d += `L${b.x} ${b.y}`; continue; }
          d += `L${b.x + (a.x - b.x) * radius / before} ${b.y + (a.y - b.y) * radius / before}`
            + `Q${b.x} ${b.y} ${b.x + (c.x - b.x) * radius / after} ${b.y + (c.y - b.y) * radius / after}`;
        }
        return d + `L${ends.to.x} ${ends.to.y}`;
      }
      for (let index = 0; index < points.length - 1; index++) {
        const a = points[Math.max(0, index - 1)], b = points[index], c = points[index + 1],
          next = points[Math.min(points.length - 1, index + 2)];
        d += `C${b.x + (c.x - a.x) / 6} ${b.y + (c.y - a.y) / 6}`
          + ` ${c.x - (next.x - b.x) / 6} ${c.y - (next.y - b.y) / 6} ${c.x} ${c.y}`;
      }
      return d;
    }

    function defaultBend(index) {
      const line = svg.querySelector(`#connection-line-${index}`);
      const p = line.getPointAtLength(line.getTotalLength() / 2);
      return { x: p.x, y: p.y };
    }

    function riserConnectionPath(from, to, style) {
      const hostAtStart = from.hostSlot || (!to.hostSlot && from.y <= to.y);
      const host = hostAtStart ? from : to, equipment = hostAtStart ? to : from;
      if (host.tubeMouth && !['lazywave', 's_shape'].includes(style)) {
        const reach = 40 * host.direction;
        return hostAtStart
          ? `M${host.x} ${host.y}C${host.x + reach} ${host.y} ${equipment.x - equipment.direction * 30} ${equipment.y} ${equipment.x} ${equipment.y}`
          : `M${equipment.x} ${equipment.y}C${equipment.x - equipment.direction * 30} ${equipment.y} ${host.x + reach} ${host.y} ${host.x} ${host.y}`;
      }
      if (style === 'lazywave' || style === 's_shape') {
        const route = riserPath(host.x, host.y, equipment.x, equipment.y, style);
        if (hostAtStart) return route;
        // Reverse the SVG path without changing its shape or flow direction.
        const dx = equipment.x - host.x, dy = equipment.y - host.y;
        if (style === 's_shape') {
          return `M${equipment.x} ${equipment.y}C${equipment.x} ${equipment.y - dy * .7}`
            + ` ${host.x + dx * .2} ${host.y + dy * .7} ${host.x + dx * .5} ${host.y + dy * .5}`
            + `S${host.x} ${host.y + dy * .7} ${host.x} ${host.y}`;
        }
        return `M${equipment.x} ${equipment.y}C${equipment.x - 50} ${equipment.y}`
          + ` ${host.x + 50} ${host.y + dy * .94} ${host.x + 60} ${host.y + dy * .62}`
          + `C${host.x + 70} ${host.y + dy * .3} ${host.x} ${host.y + dy * .5} ${host.x} ${host.y}`;
      }
      const bendY = Math.max(host.y + 20, equipment.y - 20);
      const c1 = { x: host.x, y: bendY };
      const c2 = { x: host.x + (equipment.x - host.x) / 2, y: equipment.y };
      if (style === 'flex') {
        return `M${from.x} ${from.y}C${hostAtStart ? c1.x : c2.x} ${hostAtStart ? c1.y : c2.y} ${hostAtStart ? c2.x : c1.x} ${hostAtStart ? c2.y : c1.y} ${to.x} ${to.y}`;
      }
      return hostAtStart
        ? `M${host.x} ${host.y}V${bendY}Q${host.x} ${equipment.y} ${c2.x} ${equipment.y}H${equipment.x}`
        : `M${equipment.x} ${equipment.y}H${c2.x}Q${host.x} ${equipment.y} ${host.x} ${bendY}V${host.y}`;
    }

    function finishConnection(targetId, targetPort) {
      if (!connectStart || !targetId || targetId === connectStart.id) return false;
      const connections = st.spec.connections || (st.spec.connections = []);
      const exists = connections.some((item) => item.from === connectStart.id && item.to === targetId
        && (item.fromPort || connectStart.port.id) === connectStart.port.id
        && (item.toPort || targetPort.id) === targetPort.id);
      if (!exists) {
        const riser = connectStart.port.hostSlot || targetPort.hostSlot;
        connections.push({
          installationStatus: 'New',
          from: connectStart.id, to: targetId, fromPort: connectStart.port.id,
          toPort: targetPort.id, lane: connectStart.port.lane === 'any' ? (targetPort.lane === 'any' ? 'P' : targetPort.lane) : connectStart.port.lane,
          ...(riser ? { kind: 'riser', style: 'rigid' } : {}),
          ...((connectStart.port.connectionType || targetPort.connectionType) ? { connectionType: connectStart.port.connectionType || targetPort.connectionType } : {}),
        });
        selectedConnection = connections.length - 1;
        st.sel = null; selectedIds.clear();
      }
      connectStart = null;
      const preview = svg.querySelector('#connection-preview');
      if (preview) preview.setAttribute('d', '');
      render(true);
      highlight();
      fillInsp();
      const status = el.querySelector('#connect-status');
      if (status) status.textContent = exists ? 'That connection already exists. Drag from another highlighted symbol or cancel.' : 'Connection added. Drag from another highlighted symbol or cancel.';
      return true;
    }

    function renderFreeformZones(elements) {
      const layer = svg.querySelector('#design-zones');
      const controls = svg.querySelector('#zone-controls');
      layer.innerHTML = ''; controls.innerHTML = ''; zoneLayouts.clear();
      const bounds = (element) => {
        const box = element.querySelector('.hit').getBBox();
        const corners = [[box.x, box.y], [box.x + box.width, box.y],
          [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
          .map(([x, y]) => canvasPoint(element, x, y));
        return { left: Math.min(...corners.map((p) => p.x)), right: Math.max(...corners.map((p) => p.x)),
          top: Math.min(...corners.map((p) => p.y)), bottom: Math.max(...corners.map((p) => p.y)) };
      };
      for (const [index, zone] of (st.spec.zones || []).entries()) {
        const distanceZone = Number.isFinite(zone.distanceM) && zone.distanceM > 0;
        let from = elements.get(zone.from);
        const to = distanceZone ? from : elements.get(zone.to || zone.from);
        const free = zone.placement === 'free';
        if (!free && (!from || !to)) continue;
        let hostStart = false;
        if (!free && zone.fromHost) {
          const train = from.closest('.train');
          const host = Array.from(train.querySelectorAll('.el')).find((element) => HOSTS[element.dataset.type]);
          if (host) { from = host; hostStart = true; }
        }
        const a = free ? { left: 0, right: 0, top: 0, bottom: 0 } : bounds(from), b = free ? a : bounds(to);
        let left = Math.min(a.left, b.left), right = Math.max(a.right, b.right);
        if (hostStart && a.right <= b.left) left = a.right;
        else if (hostStart && a.left >= b.right) right = a.left;
        if (distanceZone && !free) {
          left = zone.distanceDirection === 'left' ? a.left - 140 : a.right;
          right = left + 140;
        }
        const anchorBase = { left, right, y: Math.min(a.top, b.top) - num(st.spec.zoneY, 56), bottom: Math.max(a.bottom, b.bottom) + 20 };
        const base = free ? { left: 0, right: 0, y: 0, bottom: 0 }
          : !zone.placement && !distanceZone && !st.spec.freeform && st.build.zoneGeometry[index]
            ? st.build.zoneGeometry[index]
            : anchorBase;
        left = base.left + num(zone.leftOffset, 0); right = base.right + num(zone.rightOffset, 0);
        const y = base.y + num(zone.yOffset, 0), bottom = base.bottom + num(zone.bottomOffset, 0);
        const edges = zone.edges || 'both', arrows = zone.arrows || 'both';
        const labelX = (left + right) / 2 + num(zone.labelDx, 0), labelY = y + 3.5 + num(zone.labelDy, 0);
        zoneLayouts.set(index, { left, right, y, bottom, base, anchorBase, labelX, labelY });
        const unit = zone.distanceUnit || 'm', value = unit === 'km' ? zone.distanceM / 1000 : zone.distanceM;
        const label = distanceZone ? `${zone.label ? zone.label + ' - ' : ''}${value} ${unit} (NOT TO SCALE)` : zone.label || 'Zone';
        const markers = (arrows === 'both' || arrows === 'left' ? ' marker-start="url(#arr)"' : '')
          + (arrows === 'both' || arrows === 'right' ? ' marker-end="url(#arr)"' : '');
        layer.insertAdjacentHTML('beforeend', `<g class="design-zone${distanceZone ? ' distance-zone' : ''}" data-zone="${index}">`
          + line(left, y, right, y, { c: T.zone, w: 1.1 }).replace('/>', ` class="zone-span"${markers}/>`)
          + `<g class="zone-label">${txt(labelX, labelY, label, { size: 10, bold: true, c: T.mute })}</g>`
          + (edges === 'both' || edges === 'left' ? line(left, y - 10, left, bottom, { c: T.zone, w: 1, dash: '4 3' }) : '')
          + (edges === 'both' || edges === 'right' ? line(right, y - 10, right, bottom, { c: T.zone, w: 1, dash: '4 3' }) : '') + '</g>');
        const hit = (x1, y1, x2, y2, part, title) =>
          `<line data-zone="${index}" data-zone-part="${part}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="transparent" stroke-width="12" pointer-events="stroke"><title>${title}</title></line>`;
        const targets = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        targets.setAttribute('class', 'zone-hit-targets');
        layer.querySelector(`[data-zone="${index}"]`).appendChild(targets);
        targets.insertAdjacentHTML('beforeend', hit(left, y, right, y, 'height', 'Drag to change arrow height; click to edit zone')
          + (edges === 'both' || edges === 'left' ? hit(left, y - 10, left, bottom, 'left', 'Drag left boundary') : '')
          + (edges === 'both' || edges === 'right' ? hit(right, y - 10, right, bottom, 'right', 'Drag right boundary') : ''));
        const box = layer.querySelector(`[data-zone="${index}"] .zone-label`).getBBox();
        targets.insertAdjacentHTML('beforeend', `<rect data-zone="${index}" data-zone-part="label" x="${box.x - 3}" y="${box.y - 3}" width="${box.width + 6}" height="${box.height + 6}" fill="transparent" pointer-events="all"><title>Drag label; click to edit zone</title></rect>`);
      }
      const layout = zoneLayouts.get(selectedZone);
      if (layout && !connectMode) {
        const { left, right, y, bottom } = layout;
        for (const [part, x, atY, title] of [['left', left, y, 'Left boundary'], ['right', right, y, 'Right boundary'],
          ['height', (left + right) / 2, y - 18, 'Arrow height'], ['bottom', right, bottom, 'Dashed boundary depth']]) {
          controls.insertAdjacentHTML('beforeend', `<circle class="zone-handle" data-zone="${selectedZone}" data-zone-part="${part}" cx="${x}" cy="${atY}" r="5"><title>${title}: drag to adjust</title></circle>`);
        }
      }
    }

    function editableZone(zone, layout) {
      if (zone.placement) return { ...zone };
      return { ...zone, placement: 'anchored', leftOffset: layout.left - layout.anchorBase.left,
        rightOffset: layout.right - layout.anchorBase.right, yOffset: layout.y - layout.anchorBase.y,
        bottomOffset: layout.bottom - layout.anchorBase.bottom };
    }

    function addZone() {
      connectMode = false; connectStart = null;
      pendingType = null;
      svg.classList.remove('connecting', 'placement', 'drop-target');
      updatePalette();
      if ($('#b_connect')) { $('#b_connect').classList.remove('on'); $('#b_connect').textContent = 'Connect'; $('#b_connect').setAttribute('aria-pressed', 'false'); }
      const zones = st.spec.zones || (st.spec.zones = []);
      const zone = { label: 'Zone ' + (zones.length + 1), edges: 'both' };
      if (st.sel) Object.assign(zone, { placement: 'anchored', from: st.sel, yOffset: -zones.length * 25 });
      else {
        const x = vb[0] + vb[2] * .35, y = vb[1] + vb[3] * .25 - zones.length * 28;
        Object.assign(zone, { placement: 'free', leftOffset: x, rightOffset: x + 240, yOffset: y, bottomOffset: y + 160 });
      }
      zones.push(zone); selectedZone = zones.length - 1;
      st.sel = null; selectedIds.clear(); selectedConnection = null;
      render(true); fillInsp();
      $('#connect-status').textContent = 'Zone added. Drag blue handles for boundaries/height, drag the label, or enter exact values in the zone editor. Changes save automatically.';
    }

    function fillZoneInspector() {
      const zone = st.spec.zones[selectedZone], layout = zoneLayouts.get(selectedZone);
      if (!zone || !layout) { selectedZone = null; insp.style.display = 'none'; return; }
      insp.style.display = 'block';
      const ids = [...svg.querySelectorAll('.el[data-id]')].map((element) => element.dataset.id);
      const options = (values, current) => values.map(([value, name]) =>
        `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(name)}</option>`).join('');
      const input = (id, label, value, type = 'number') =>
        `<label for="z_${id}">${label}</label><input id="z_${id}" type="${type}" value="${esc(value)}"${type === 'number' ? ' step="any"' : ''}>`;
      const unit = zone.distanceUnit || 'm', factor = unit === 'km' ? 1000 : 1;
      insp.innerHTML = `<b>Zone / distance</b><p>Changes save automatically. Drag boundaries, arrow or label on the drawing. Drawing positions are not metres.</p>
        <label for="z_select">Annotation</label><select id="z_select">${options(st.spec.zones.map((z, i) => [String(i), z.label || 'Zone ' + (i + 1)]), String(selectedZone))}</select>`
        + input('label', 'Label (LC1, LC2, Fortified zone...)', zone.label || '', 'text')
        + `<label for="z_placement">Placement</label><select id="z_placement">${options([['free', 'Anywhere on drawing'], ['anchored', 'Follow equipment']], zone.placement === 'free' ? 'free' : 'anchored')}</select>`
        + (zone.placement === 'free' ? '' : `<label for="z_from">Start item</label><select id="z_from">${options(ids.map((id) => [id, id]), zone.from)}</select>
          <label for="z_to">End item (ignored with distance)</label><select id="z_to">${options([['', 'Start item only'], ...ids.map((id) => [id, id])], zone.to || '')}</select>
          <label for="z_direction">Distance direction</label><select id="z_direction">${options([['right', 'Right'], ['left', 'Left']], zone.distanceDirection || 'right')}</select>
          <label><input id="z_host" type="checkbox"${zone.fromHost ? ' checked' : ''}${zone.distanceM ? ' disabled' : ''}> Start at host (without distance)</label>`)
        + input('distance', 'Engineering distance (optional)', zone.distanceM ? zone.distanceM / factor : '')
        + `<label for="z_unit">Distance unit</label><select id="z_unit">${options([['m', 'Metres'], ['km', 'Kilometres']], unit)}</select>`
        + `<label for="z_edges">Dashed boundaries</label><select id="z_edges">${options(['both', 'left', 'right', 'none'].map((v) => [v, v]), zone.edges || 'both')}</select>`
        + `<label for="z_arrows">Arrowheads</label><select id="z_arrows">${options(['both', 'left', 'right', 'none'].map((v) => [v, v]), zone.arrows || 'both')}</select>`
        + input('left', 'Left boundary X', layout.left) + input('right', 'Right boundary X', layout.right)
        + input('y', 'Arrow Y (smaller = higher)', layout.y) + input('bottom', 'Dashed boundary bottom Y', layout.bottom)
        + input('labelDx', 'Label horizontal offset', num(zone.labelDx, 0)) + input('labelDy', 'Label vertical offset', num(zone.labelDy, 0))
        + '<p id="z_error" role="alert" style="color:#b42318"></p><button id="z_add">+ Another zone</button> <button id="z_delete">Delete zone</button>';
      const field = (name) => insp.querySelector('#z_' + name);
      field('select').onchange = () => { selectedZone = +field('select').value; renderConnections(); fillInsp(); };
      field('add').onclick = addZone; field('delete').onclick = removeSelected;
      insp.querySelectorAll('input,select:not(#z_select)').forEach((control) => {
        control.onchange = () => {
          const error = field('error');
          const currentLayout = zoneLayouts.get(selectedZone), current = editableZone(st.spec.zones[selectedZone], currentLayout);
          const numbers = ['left', 'right', 'y', 'bottom', 'labelDx', 'labelDy'];
          if (numbers.some((key) => field(key).value.trim() === '' || !Number.isFinite(+field(key).value))) {
            error.textContent = 'Drawing positions must be finite numbers.'; return;
          }
          if (+field('right').value - +field('left').value < 10 || +field('bottom').value <= +field('y').value) {
            error.textContent = 'Right boundary must be at least 10 drawing units after left; bottom must be below the arrow.'; return;
          }
          const distance = field('distance').value.trim();
          if (distance && (!Number.isFinite(+distance * factor) || +distance <= 0)) { error.textContent = 'Distance must be a positive finite number.'; return; }
          const next = { ...current, label: field('label').value, distanceUnit: field('unit').value,
            edges: field('edges').value, arrows: field('arrows').value,
            labelDx: +field('labelDx').value, labelDy: +field('labelDy').value };
          if (distance) next.distanceM = +distance * factor;
          else delete next.distanceM;
          const placementChanged = field('placement').value !== (current.placement === 'free' ? 'free' : 'anchored');
          if (placementChanged) {
            if (field('placement').value === 'anchored' && !ids.length) { error.textContent = 'Add equipment before anchoring a zone.'; return; }
            next.placement = field('placement').value;
            if (next.placement === 'anchored') next.from = ids[0];
            delete next.fromHost;
            for (const key of ['leftOffset', 'rightOffset', 'yOffset', 'bottomOffset']) delete next[key];
            st.spec.zones[selectedZone] = next; renderConnections();
          } else {
            if (field('from')) {
              next.from = field('from').value; next.to = field('to').value; next.distanceDirection = field('direction').value;
              if (field('host').checked && !distance) next.fromHost = true;
              else delete next.fromHost;
            }
            st.spec.zones[selectedZone] = next;
          }
          if (next.placement === 'free') { delete next.from; delete next.to; delete next.fromHost; }
          const base = placementChanged ? zoneLayouts.get(selectedZone).base
            : current.placement === 'free' ? currentLayout.base : currentLayout.anchorBase;
          if (placementChanged || ['z_left', 'z_right', 'z_y', 'z_bottom'].includes(control.id)) {
            next.leftOffset = +field('left').value - base.left; next.rightOffset = +field('right').value - base.right;
            next.yOffset = +field('y').value - base.y; next.bottomOffset = +field('bottom').value - base.bottom;
          }
          error.textContent = '';
          render(true);
          if (control.tagName === 'SELECT' || control.type === 'checkbox') fillInsp();
          else {
            const updated = zoneLayouts.get(selectedZone);
            for (const [key, value] of Object.entries({ left: updated.left, right: updated.right, y: updated.y, bottom: updated.bottom })) field(key).value = value;
            if (field('host')) { field('host').checked = !!next.fromHost; field('host').disabled = !!next.distanceM; }
            field('select').selectedOptions[0].textContent = next.label || 'Zone ' + (selectedZone + 1);
          }
        };
      });
    }

    function internalPipes(element) {
      return new Map(Array.from(element.querySelectorAll('[data-internal-pipe]'))
        .filter((pipe) => pipe.getTotalLength() > 0).map((pipe) => [pipe.dataset.internalPipe, pipe]));
    }

    function internalPipePoint(element, pipe, fraction) {
      const point = pipe.getPointAtLength(pipe.getTotalLength() * fraction);
      const local = svg.createSVGPoint(); local.x = point.x; local.y = point.y;
      return local.matrixTransform(element.getCTM().inverse().multiply(pipe.getCTM()));
    }

    function internalValveOptions(element) {
      if (!element) return { pipes: [], defaults: [] };
      const pipes = internalPipes(element);
      const defaults = Array.from(element.querySelectorAll('.default-internal-valve')).map((marker) => {
        const origin = svg.createSVGPoint();
        const location = origin.matrixTransform(element.getCTM().inverse().multiply(marker.getCTM()));
        let closest = { distance: Infinity, pipe: '', position: 50 };
        for (const [id, pipe] of pipes) {
          for (let percent = 0; percent <= 100; percent++) {
            const point = internalPipePoint(element, pipe, percent / 100);
            const distance = Math.hypot(point.x - location.x, point.y - location.y);
            if (distance < closest.distance) closest = { distance, pipe: id, position: percent };
          }
        }
        return { id: marker.dataset.defaultValve, pipe: closest.pipe, position: closest.position,
          kind: marker.dataset.valveKind, closed: marker.dataset.valveClosed === 'true',
          tag: '', label: '', provider: '', rating: '' };
      });
      return { pipes: [...pipes].map(([id, pipe]) => ({ id, lane: pipe.dataset.pipeLane })), defaults };
    }

    function renderInternalValves(elements) {
      for (const [id, element] of elements) {
        element.querySelectorAll('.custom-internal-valves,.internal-valve-error').forEach((group) => group.remove());
        const item = findItem(id)?.item;
        if (!item) continue;
        const custom = item.internalValves !== undefined;
        element.querySelectorAll('.default-internal-valve').forEach((marker) => {
          if (custom) marker.style.display = 'none';
          else marker.style.removeProperty('display');
        });
        if (!custom) continue;
        const pipes = internalPipes(element);
        const errors = internalValveErrors(item, new Set(pipes.keys()));
        if (errors.length) {
          const box = element.querySelector('.hit').getBBox();
          element.insertAdjacentHTML('beforeend', `<g class="internal-valve-error">${txt(box.x, box.y - 8,
            errors.join('\n'), { size: 9, anchor: 'start', c: '#D32F2F' })}</g>`);
          continue;
        }
        let markup = '';
        const previousMirror = MIRROR, matrix = element.getCTM();
        MIRROR = matrix.a * matrix.d - matrix.b * matrix.c < 0;
        try {
          for (const entry of item.internalValves) {
            const pipe = pipes.get(entry.pipe), fraction = num(entry.position, 50) / 100;
            const point = internalPipePoint(element, pipe, fraction);
            const before = internalPipePoint(element, pipe, Math.max(0, fraction - .001));
            const after = internalPipePoint(element, pipe, Math.min(1, fraction + .001));
            const angle = Math.atan2(after.y - before.y, after.x - before.x) * 180 / Math.PI;
            const details = [entry.tag, entry.label, EQUIPMENT_OPTIONS.valveTypes[entry.kind || 'gate'],
              entry.closed ? 'Closed' : 'Open', entry.provider, entry.rating].filter(Boolean).join(' | ');
            const detailScale = item.riserDetail ? NODE[item.type].w(item) / item.riserDetail.width : 1;
            const glyph = valve(0, 0, { kind: entry.kind || 'gate', closed: entry.closed, rot: angle,
              s: item.riserDetail ? 5.5 : undefined });
            markup += `<g class="custom-internal-valve" data-valve-id="${esc(entry.id)}" data-pipe="${esc(entry.pipe)}" data-position="${num(entry.position, 50)}" data-kind="${esc(entry.kind || 'gate')}" data-closed="${!!entry.closed}" transform="translate(${point.x} ${point.y})">`
              + `<title>${esc(details)}</title>` + (item.riserDetail ? `<g transform="scale(${detailScale})">${glyph}</g>` : glyph)
              + (entry.tag || entry.label ? txt(0, -38 * detailScale, [entry.tag, entry.label].filter(Boolean).join('\n'),
                { size: 7.5 * detailScale, c: T.mute }) : '') + '</g>';
          }
        } finally {
          MIRROR = previousMirror;
        }
        element.insertAdjacentHTML('beforeend', `<g class="custom-internal-valves" pointer-events="none">${markup}</g>`);
      }
    }

    function renderRiserPSV(group, route, item, color, topside = null, key = '') {
      if (!item.psv || !route) return;
      const length = route.getTotalLength();
      const distance = topside ? (topside.atStart ? 0 : length)
        : length * Math.max(0, Math.min(100, num(item.psvPosition, 50))) / 100;
      let point = route.getPointAtLength(distance);
      if (topside) {
        const match = /^J-(\d+)$/.exec(topside.port || '');
        const tubes = topside.host.querySelectorAll('.j-tube-guide');
        const slot = match ? +match[1] : Math.min(['P-right', 'S-right', 'U-right'].indexOf(topside.port), tubes.length - 1);
        const bore = topside.host.querySelector(`.j-tube-guide[data-tube="${slot}"] .j-tube-bore`);
        if (bore) {
          const deck = bore.getPointAtLength(0), anchor = svg.createSVGPoint();
          anchor.x = deck.x; anchor.y = deck.y;
          point = anchor.matrixTransform(group.getScreenCTM().inverse().multiply(bore.getScreenCTM()));
        }
      }
      const before = route.getPointAtLength(Math.max(0, distance - 1));
      const after = route.getPointAtLength(Math.min(length, distance + 1));
      const angle = topside ? 0 : Math.atan2(after.y - before.y, after.x - before.x) * 180 / Math.PI;
      const annotations = svg.querySelector('#riser-annotations');
      const placement = annotations.getScreenCTM().inverse().multiply(group.getScreenCTM()).translate(point.x, point.y);
      annotations.insertAdjacentHTML('beforeend', `<g class="riser-psv" data-psv-key="${esc(key)}" pointer-events="none" transform="matrix(${placement.a} ${placement.b} ${placement.c} ${placement.d} ${placement.e} ${placement.f})">`
        + `<title>${esc(item.psvTag || 'PSV')} - schematic pressure safety valve${topside ? ' at topside riser termination' : ''}</title>`
        + `<g class="riser-psv-symbol" transform="rotate(${angle}) scale(0.45)"><path d="M0 0V-12M-6 -12L6 -12L0 -22ZM0 -22V-27L-4 -29L4 -32L-4 -35L4 -38M0 -22H14V-30" fill="${T.paper}" stroke="${color}" stroke-width="1.5"/></g>`
        + txt(9, -7, item.psvTag || 'PSV', { size: 6.5, c: color, anchor: 'start' }) + '</g>');
    }

    function renderConnections() {
      notifyChange();
      const layer = svg.querySelector('#connections');
      if (!layer) return;
      svg.querySelector('#riser-annotations').innerHTML = '';
      const controls = svg.querySelector('#route-controls');
      controls.innerHTML = '';
      const elements = new Map(Array.from(svg.querySelectorAll('#content .el')).map((item) => [item.dataset.id, item]));
      renderInternalValves(elements);
      renderFreeformZones(elements);
      svg.querySelectorAll('.j-tube-pulled').forEach((group) => { group.innerHTML = ''; });
      const pullThrough = (host, portId, appearance, width) => {
        const match = /^J-(\d+)$/.exec(portId || '');
        if (!match) return;
        const guide = host.querySelector(`.j-tube-guide[data-tube="${match[1]}"]`);
        if (!guide) return;
        const d = guide.querySelector('.j-tube-bore').getAttribute('d');
        guide.querySelector('.j-tube-pulled').insertAdjacentHTML('beforeend',
          `<path class="j-tube-riser" d="${d}" fill="none" stroke="${appearance.c}" stroke-width="${Math.min(width, 4)}"${appearance.dash ? ` stroke-dasharray="${appearance.dash}"` : ''} pointer-events="none"/>`);
      };
      svg.querySelectorAll('[data-riser-host]').forEach((riser) => {
        const host = elements.get(riser.dataset.riserHost);
        if (!host) return;
        const point = svg.createSVGPoint();
        point.x = +riser.dataset.ax; point.y = +riser.dataset.ay;
        const position = point.matrixTransform(riser.getScreenCTM().inverse().multiply(host.getScreenCTM()));
        riser.querySelectorAll(':scope > path').forEach((path) => path.setAttribute('d',
          riserPath(position.x, position.y, +riser.dataset.ex, +riser.dataset.ey, riser.dataset.style)));
        const legacy = riser.querySelector('path:not(.legacy-riser-hit)');
        const hostItem = findItem(riser.dataset.riserHost)?.item;
        const preset = hostItem?.risers?.[+riser.dataset.riserIndex];
        if (preset) renderRiserPSV(riser, legacy, preset, legacy?.getAttribute('stroke') || T.ink,
          { host, port: `J-${num(preset.slot, 0)}`, atStart: true }, `${riser.dataset.riserHost}:${riser.dataset.riserIndex}`);
        if (legacy && preset) pullThrough(host, `J-${num(preset.slot, 0)}`,
          { c: legacy.getAttribute('stroke'), dash: legacy.getAttribute('stroke-dasharray') }, +legacy.getAttribute('stroke-width'));
      });
      layer.innerHTML = '';
      (st.spec.connections || []).forEach((connection, index) => {
        const from = elements.get(connection.from), to = elements.get(connection.to);
        if (!from || !to) return;
        const ends = connectionEnds(connection, from, to);
        if (!ends) return;
        const d = routedPath(connection, ends);
        const appearance = connectionAppearance(connection, st.spec);
        const dash = appearance.dash || (connection.kind === 'riser' && connection.style === 'flex' ? '10 3' : '');
        const width = num(connection.width, connection.kind === 'riser' ? 2.5 : num(st.spec.connectionWidth, 2.5));
        pullThrough(from, connection.fromPort, appearance, width);
        pullThrough(to, connection.toPort, appearance, width);
        layer.insertAdjacentHTML('beforeend', `<defs><path id="connection-flow-route-${index}" d="${d}" fill="none"/></defs>`);
        layer.insertAdjacentHTML('beforeend', `<g class="connection${selectedConnection === index ? ' sel' : ''}" data-connection="${index}"><title>${esc(appearance.label)}${connection.label ? ': ' + esc(connection.label) : ''}</title><path class="connection-hit" d="${d}" fill="none" stroke="transparent" stroke-width="${Math.max(12, width + 8)}" pointer-events="stroke"/><path id="connection-line-${index}" d="${d}" fill="none" stroke="${appearance.c}" stroke-width="${width}"${dash ? ` stroke-dasharray="${dash}"` : ''} pointer-events="stroke"/></g>`);
        const group = layer.lastElementChild;
        const train = [st.spec, ...(st.spec.branches || [])].find((tr) =>
          (tr.host && tr.host.id === connection.from) || (tr.chain || []).some((it) => it.id === connection.from)) || st.spec;
        const flow = connection.flow && connection.flow !== 'auto' ? connection.flow : st.spec.flow || 'auto';
        let reverse = flow === 'reverse';
        if (flow === 'auto') {
          const towardsHost = flowFor(train, st.spec)[connection.lane || 'P'].mode === 'rev';
          const fromHost = !!HOSTS[from.dataset.type], toHost = !!HOSTS[to.dataset.type];
          reverse = fromHost !== toHost
            ? (towardsHost ? fromHost : toHost)
            : (towardsHost ? ends.from.x < ends.to.x : ends.from.x > ends.to.x);
        }
        if (flow !== 'none') {
          group.insertAdjacentHTML('beforeend', `<use href="#connection-flow-route-${index}" class="flow connection-flow${reverse ? ' rev' : ''}" fill="none" stroke="${T.paper}" stroke-width="${Math.max(1, width * .55)}" style="--d:1.6s" pointer-events="none"/>`);
          const route = group.querySelector(`#connection-line-${index}`), length = route.getTotalLength();
          if (st.spec.flowArrows !== false && length > 24) {
            const mid = length / 2, p = route.getPointAtLength(mid), q = route.getPointAtLength(Math.min(length, mid + 1));
            const angle = Math.atan2(q.y - p.y, q.x - p.x) * 180 / Math.PI + (reverse ? 180 : 0);
            group.insertAdjacentHTML('beforeend', `<polygon class="flow-arrow" points="-6,-4 6,0 -6,4" fill="${appearance.c}" transform="translate(${p.x} ${p.y}) rotate(${angle})" pointer-events="none"/>`);
          }
        }
        if (connection.label) {
          const middle = layer.lastElementChild.querySelector('path:not(.connection-hit)');
          const point = middle.getPointAtLength(middle.getTotalLength() / 2);
          layer.lastElementChild.insertAdjacentHTML('beforeend', elementLabel(point.x, point.y - 7, connection.label, connection, { size: 9, c: appearance.c }));
        }
        if (connection.kind === 'riser') {
          const topside = ends.from.hostSlot ? { host: from, port: ends.from.id, atStart: true }
            : ends.to.hostSlot ? { host: to, port: ends.to.id, atStart: false } : null;
          renderRiserPSV(group, group.querySelector(`#connection-line-${index}`), connection, appearance.c, topside, `connection-${index}`);
        }
      });
      if (selectedConnection !== null) {
        const connection = (st.spec.connections || [])[selectedConnection];
        const from = connection && elements.get(connection.from), to = connection && elements.get(connection.to);
        const ends = from && to && connectionEnds(connection, from, to);
        if (ends) {
          for (const end of ['from', 'to']) {
            controls.insertAdjacentHTML('beforeend', `<circle class="route-handle route-end" data-end="${end}" cx="${ends[end].x}" cy="${ends[end].y}" r="7"><title>Drag to another matching port</title></circle>`);
          }
          (connection.waypoints || []).forEach((p, index) => {
            controls.insertAdjacentHTML('beforeend', `<circle class="route-handle route-bend" data-bend="${index}" cx="${p.x}" cy="${p.y}" r="7"><title>Drag bend; double-click to remove</title></circle>`);
          });
        }
      }
      layer.insertAdjacentHTML('beforeend', '<path id="connection-preview" d="" fill="none" stroke="#2251FF" stroke-width="2" stroke-dasharray="6 4" pointer-events="none"/>');
      renderSeaLevel();
    }

    function renderSeaLevel() {
      svg.querySelector('#sea-level')?.remove();
      const sea = st.spec.seaLevel;
      if (!sea || !sea.visible) return;
      const host = svg.querySelector(`.el[data-id="${CSS.escape(sea.host || '')}"]`);
      if (!host) return;
      const box = host.getBBox(), anchor = canvasPoint(host, box.x + box.width / 2, box.y);
      const y = anchor.y + num(sea.offset, 0);
      const boxes = Array.from(svg.querySelectorAll('#content .el')).map((g) => {
        const b = g.getBBox();
        return [canvasPoint(g, b.x, b.y).x, canvasPoint(g, b.x + b.width, b.y).x];
      }).flat();
      const x1 = Math.min(...boxes) - 40, x2 = Math.max(...boxes) + 40;
      svg.querySelector('#content').insertAdjacentHTML('afterbegin', `<g id="sea-level" pointer-events="none">${line(x1, y, x2, y, { c: T.blue, w: 1.4, dash: '12 4' })}${txt(x1, y - 6, 'Sea level', { anchor: 'start', size: 9, c: T.blue })}</g>`);
    }

    function updateSelectionControls() {
      const hasElement = !!st.sel && !!findItem(st.sel) && selectedConnection === null;
      if ($('#b_copy')) $('#b_copy').disabled = !hasElement || selectedIds.size > 1;
      if ($('#b_delete')) $('#b_delete').disabled = !st.sel && selectedConnection === null && selectedZone === null;
      if ($('#b_riser_detail')) {
        const type = findItem(st.sel)?.item.type;
        $('#b_riser_detail').disabled = !hasElement || selectedIds.size > 1 || !['riser_base', 'riser_skid', 'custom_element'].includes(type);
        $('#b_riser_detail').textContent = ['riser_base', 'riser_skid'].includes(type) ? 'Riser details' : 'Element designer';
        if (wants3D) $('#b_riser_detail').disabled = true;
      }
      for (const id of ['b_palette', 'b_connect', 'b_zone', 'b_custom_element', 'b_layout', 'b_grid', 'b_print']) {
        if ($('#' + id)) $('#' + id).disabled = wants3D;
      }
      $('#b_html').disabled = !wants3D;
    }

    function openRiserDetail() {
      const id = st.sel, found = id && findItem(id);
      if (!found || !['riser_base', 'riser_skid', 'custom_element'].includes(found.item.type)) return;
      const candidate = (layout, valves) => {
        const item = JSON.parse(JSON.stringify(findItem(id).item));
        Object.assign(item, { riserDetail: layout, internalValves: valves });
        for (const key of ['internalRoutes', 'riserPorts', 'portConfig', 'portOverrides', 'bundleServiceInlet']) delete item[key];
        return item;
      };
      const validateDetail = (layout, valves) => {
        const invalid = root.SubseaRiserDetail.errors(layout);
        if (invalid.length) return invalid;
        const item = candidate(layout, valves), ids = new Set(layout.hubs.map((h) => h.id));
        const messages = internalValveErrors(item, new Set(layout.routes.map((r) => 'route-' + r.id)));
        for (const connection of st.spec.connections || []) for (const end of ['from', 'to']) {
          if (connection[end] !== id || !connection[end + 'Port']) continue;
          const port = connection[end + 'Port'], hub = layout.hubs.find((h) => h.id === port);
          if (!ids.has(port)) messages.push(`Connected hub ${port} cannot be removed. Reconnect or delete its external line first.`);
          else if (root.SubseaRiserDetail.services()[hub.service].lane !== (connection.lane || 'P')) {
            messages.push(`Connected hub ${port} cannot change lane. Reconnect or delete its external line first.`);
          }
        }
        return messages;
      };
      const commitDetail = (layout, valves) => {
        const current = findItem(id).item, next = candidate(layout, valves);
        for (const key of Object.keys(current)) delete current[key];
        Object.assign(current, next); render(true); fillInsp();
      };
      if (!found.item.riserDetail) {
        const custom = found.item.type === 'custom_element';
        if (!custom && !root.confirm('Load the illustrated riser-base layout? This replaces internal piping, valves and hub settings. External connections remain protected.')) return;
        const reference = custom ? root.SubseaRiserDetail.blank() : root.SubseaRiserDetail.reference();
        const invalid = validateDetail(reference.riserDetail, reference.internalValves);
        if (invalid.length) { $('#connect-status').textContent = 'Detailed layout not loaded: ' + invalid.join(' '); return; }
        commitDetail(reference.riserDetail, reference.internalValves);
      }
      if (detailEditor) detailEditor.close();
      detailEditorId = id;
      detailEditor = root.SubseaRiserDetail.open({
        parent: el, item: findItem(id).item, valveTypes: EQUIPMENT_OPTIONS.valveTypes,
        validate: validateDetail, commit: commitDetail, download: save,
        hubMarkup: () => conn(0, 0),
        valveMarkup: (entry) => valve(0, 0, { kind: entry.kind || 'gate', closed: entry.closed, s: 5.5 }),
        onClose: () => { detailEditor = null; detailEditorId = null; $('#b_riser_detail')?.focus(); },
      });
    }

    function render(keepView) {
      const b = build(st.spec), sp = st.spec;
      st.build = b;
      svg.innerHTML = b.defs + `<rect id="bg" x="-5000" y="-5000" width="10000" height="10000" fill="${T.paper}"/>`
        + (grid ? gridSvg() : '') + `<g id="content" font-family="${esc(T.font)}"><g id="connections"></g>${b.content}</g><g id="decor" font-family="${esc(T.font)}"></g><g id="route-controls"></g><g id="zone-controls"></g><g id="riser-annotations" font-family="${esc(T.font)}" pointer-events="none"></g>`;
      el.style.background = T.paper; svg.style.background = T.paper; document.body.style.background = T.paper;
      svg.querySelectorAll('#content .el').forEach((g) => {
        const found = findItem(g.dataset.id);
        const limits = { ...(sp.designLimits || {}), ...((found && found.item.designLimits) || {}) };
        if (Object.keys(limits).length) {
          g.insertAdjacentHTML('afterbegin', `<title>${esc(Object.entries(limits).map(([key, value]) =>
            `${EQUIPMENT_OPTIONS.designFields[key] ? EQUIPMENT_OPTIONS.designFields[key].label : key}: ${value}`).join('; '))}</title>`);
        }
        const ports = g.querySelectorAll('.connection-port');
        ports.forEach((port) => { port.style.display = 'none'; });
        const r = g.getBBox();
        ports.forEach((port) => { port.style.removeProperty('display'); });
        const x = r.x + r.width / 2, y = r.y + r.height / 2;
        const width = Math.max(r.width, 16), height = Math.max(r.height, 16);
        g.insertAdjacentHTML('afterbegin', `<rect class="hit" x="${x - width / 2}" y="${y - height / 2}" width="${width}" height="${height}" fill="${T.paper}" fill-opacity="0" pointer-events="all"/>`);
      });
      renderConnections();
      const bb = svg.querySelector('#content').getBBox();
      const W = Math.max(bb.width, 760), x0 = bb.x, y0 = bb.y, y1 = bb.y + bb.height;
      let decor = '';
      const showLeg = sp.showLegend !== false, notes = sp.notes || [];
      const base = y1 + 40;
      let legH = 0;
      if (showLeg) { const lg = legend(x0 + 4, base, b.fluids, sp.connections, sp); decor += lg.svg; legH = lg.h; }
      decor += notesBlock(x0 + 400, base, notes);
      let yEnd = base + (showLeg ? legH : 0);
      if (T.layout === 'slide') {
        const title = wrap(sp.title || 'Subsea field layout', Math.floor(W / 11));
        const nl = title.split('\n').length;
        decor += txt(x0, y0 - 52, title, { size: 22, anchor: 'start', halo: false, font: T.serif, va: 'bottom', c: T.ink });
        if (sp.subtitle) decor += txt(x0, y0 - 34, sp.subtitle, { size: 11.5, anchor: 'start', halo: false, c: T.mute });
        decor += line(x0, y0 - 24, x0 + W, y0 - 24, { c: T.ink, w: 1.4 });
        const fy = yEnd + 14;
        decor += line(x0, fy, x0 + W, fy, { c: T.zone, w: 0.7 });
        decor += txt(x0, fy + 14, `Note: ${sp.footnote || 'Schematic – not to scale'}`, { size: 8, anchor: 'start', halo: false, c: T.mute });
        if (sp.source) decor += txt(x0, fy + 26, `Source: ${sp.source}`, { size: 8, anchor: 'start', halo: false, c: T.mute });
        void nl;
      } else if (sp.showTitleBlock !== false) {
        decor += titleBlock(Math.max(x0 + W - 380, (notes && notes.length) ? x0 + 400 + 350 : -1e9), base, sp);
      }
      svg.querySelector('#decor').innerHTML = decor;
      const all = svg.querySelector('#decor').getBBox();
      const fx = Math.min(bb.x, all.width ? all.x : bb.x), fy2 = Math.min(bb.y, all.height ? all.y : bb.y);
      const fw = Math.max(bb.x + bb.width, all.x + all.width) - fx, fh = Math.max(bb.y + bb.height, all.y + all.height) - fy2;
      let box = [fx - 30, fy2 - 30, fw + 60, fh + 60];
      if (T.layout === 'sheet') {
        svg.querySelector('#decor').insertAdjacentHTML('beforeend', sheetFrame(box[0], box[1], box[2], box[3]));
        box = [box[0] - 14, box[1] - 14, box[2] + 28, box[3] + 28];
      }
      st.fit = box;
      if (!keepView || !vb) vb = st.fit.slice();
      applyVb();
      highlight();
      updateSelectionControls();
      st.build = b;
    }
    const rectFrame = (bb, yEnd) => '';
    function gridSvg() {
      return `<g opacity=".35">${Array.from({ length: 120 }, (_, i) => line(-400 + i * 20, -600, -400 + i * 20, 900, { c: '#e3e6ea', w: 0.5 })).join('')}${Array.from({ length: 75 }, (_, i) => line(-400, -600 + i * 20, 2000, -600 + i * 20, { c: '#e3e6ea', w: 0.5 })).join('')}</g>`;
    }
    const applyVb = () => svg.setAttribute('viewBox', vb.join(' '));

    /* pan / zoom / drag */
    let drag = null;
    const pt = (e) => { const r = svg.getBoundingClientRect(); const s = Math.max(vb[2] / r.width, vb[3] / r.height); const ox = (r.width - vb[2] / s) / 2, oy = (r.height - vb[3] / s) / 2; return { x: vb[0] + (e.clientX - r.left - ox) * s, y: vb[1] + (e.clientY - r.top - oy) * s, s }; };
    svg.addEventListener('pointerdown', (e) => {
      const zoneControl = e.target.closest('[data-zone-part]');
      if (zoneControl && !connectMode && !pendingType) {
        selectedZone = +zoneControl.dataset.zone;
        st.sel = null; selectedIds.clear(); selectedConnection = null;
        const p = pt(e), zone = st.spec.zones[selectedZone];
        drag = { mode: 'zone', index: selectedZone, part: zoneControl.dataset.zonePart,
          sx: p.x, sy: p.y, original: { ...zone }, start: editableZone(zone, zoneLayouts.get(selectedZone)),
          layout: { ...zoneLayouts.get(selectedZone) } };
        renderConnections(); fillInsp(); updateSelectionControls();
        svg.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
      selectedZone = null;
      const legacyRiser = e.target.closest('[data-riser-host]');
      if (legacyRiser && !connectMode) {
        const found = findItem(legacyRiser.dataset.riserHost);
        const index = +legacyRiser.dataset.riserIndex, original = found.item.risers[index];
        const lane = original.lane || 'P', point = canvasPoint(legacyRiser, +legacyRiser.dataset.ex, +legacyRiser.dataset.ey);
        const candidates = found.chain.flatMap((item) => {
          const element = svg.querySelector(`.el[data-id="${CSS.escape(item.id)}"]`);
          return element ? portsFor(element, lane).map((port) => ({ id: item.id, port })) : [];
        }).sort((a, b) => Math.hypot(a.port.x - point.x, a.port.y - point.y) - Math.hypot(b.port.x - point.x, b.port.y - point.y));
        if (!candidates.length) {
          $('#connect-status').textContent = 'This preset riser has no equipment port to attach to. Add equipment before editing its route.';
          return;
        }
        const connection = { installationStatus: original.installationStatus || 'Unspecified',
          provider: original.provider || '', installationType: original.installationType || '', rating: original.rating || '',
          ...(original.installedLengthKm !== undefined ? { installedLengthKm: original.installedLengthKm } : {}),
          psv: original.psv || false, psvTag: original.psvTag || '', psvPosition: num(original.psvPosition, 50),
          from: found.item.id, fromPort: `J-${Math.max(0, Math.min(num(original.slot, 0), (found.item.slots || ['J1', 'J2']).length - 1))}`,
          to: candidates[0].id, toPort: candidates[0].port.id, lane, kind: 'riser',
          style: ['flex', 'lazywave'].includes(original.style) ? 'flex' : 'rigid', label: original.label || '',
          riserCurve: 'sweep', width: num(original.width, lane === 'P' ? 2.2 : 1.9) };
        found.item.risers.splice(index, 1);
        const connections = st.spec.connections || (st.spec.connections = []);
        connections.push(connection); selectedConnection = connections.length - 1;
        st.sel = null; selectedIds.clear();
        render(true); fillInsp();
        $('#connect-status').textContent = 'Preset riser is now editable: drag the line or handles. Ends remain attached to equipment.';
        e.preventDefault(); return;
      }
      const handle = e.target.closest('.route-handle');
      if (handle && selectedConnection !== null && !connectMode) {
        const p = pt(e), connection = st.spec.connections[selectedConnection];
        drag = { mode: handle.dataset.end ? 'endpoint' : 'bend', index: selectedConnection,
          end: handle.dataset.end, bend: +handle.dataset.bend, sx: p.x, sy: p.y,
          originalWaypoints: connection.waypoints ? JSON.parse(JSON.stringify(connection.waypoints)) : null };
        if (drag.end) {
          svg.classList.add('connecting');
          svg.querySelectorAll('.el').forEach((g) => g.classList.add('connect-candidate'));
        }
        svg.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
      const connection = e.target.closest('.connection');
      if (connection && !connectMode) {
        const alreadySelected = selectedConnection === +connection.dataset.connection;
        selectedConnection = +connection.dataset.connection;
        st.sel = null; selectedIds.clear();
        const p = pt(e), item = st.spec.connections[selectedConnection];
        drag = { mode: 'route', index: selectedConnection, sx: p.x, sy: p.y,
          originalWaypoints: item.waypoints ? JSON.parse(JSON.stringify(item.waypoints)) : null,
          points: JSON.parse(JSON.stringify(item.waypoints && item.waypoints.length ? item.waypoints : [defaultBend(selectedConnection)])) };
        if (!alreadySelected) renderConnections();
        highlight();
        fillInsp();
        svg.setPointerCapture(e.pointerId);
        return;
      }
      const t = e.target.closest('.el');
      const p = pt(e);
      if (connectMode) {
        if (t) {
          const handle = e.target.closest('.connection-port');
          const port = nearestPort(t, p, null, handle ? handle.dataset.port : null);
          if (!port) return;
          connectStart = { id: t.dataset.id, point: port, port };
          const preview = svg.querySelector('#connection-preview');
          if (preview) preview.setAttribute('d', connectionPath(connectStart.point, p));
          const status = el.querySelector('#connect-status');
          if (status) status.textContent = `Dragging ${port.label || port.id} from ${t.dataset.id}. Drop on a green equipment port or labelled J-tube.`;
          highlight();
          svg.setPointerCapture(e.pointerId);
        } else {
          const status = el.querySelector('#connect-status');
          if (status) status.textContent = 'Start the drag on a green-highlighted symbol.';
        }
        e.preventDefault();
        return;
      }
      if (pendingType && (st.spec.freeform || HOSTS[pendingType])) {
        placeSymbol(pendingType, p);
        e.preventDefault();
        return;
      }
      if (t && (t.classList.contains('node') || st.spec.freeform || st.spec.overrides[t.dataset.id]
        || e.shiftKey || e.ctrlKey || e.metaKey || selectedIds.has(t.dataset.id))) {
        if (e.shiftKey || e.ctrlKey || e.metaKey) {
          if (!selectedIds.size && st.sel) selectedIds.add(st.sel);
          if (selectedIds.has(t.dataset.id)) selectedIds.delete(t.dataset.id);
          else selectedIds.add(t.dataset.id);
          st.sel = selectedIds.values().next().value || null; selectedConnection = null;
          renderConnections(); highlight(); fillInsp(); e.preventDefault(); return;
        }
        if (selectedIds.size > 1 && selectedIds.has(t.dataset.id)) {
          drag = { mode: 'group', sx: p.x, sy: p.y, members: captureElements([...selectedIds]) };
          svg.setPointerCapture(e.pointerId); e.preventDefault(); return;
        }
        select(t.dataset.id);
        const o = st.spec.overrides[t.dataset.id] || {};
        const mg = t.closest('.train.mir'), transform = t.transform.baseVal.consolidate();
        drag = {
          mode: 'node', inv: mg ? -1 : 1, id: t.dataset.id, sx: p.x, sy: p.y,
          dx: o.dx || 0, dy: o.dy || 0, baseX: transform ? transform.matrix.e : 0,
          baseY: transform ? transform.matrix.f : 0,
          scale: transform ? transform.matrix.a : 1,
          itemX: num(t.dataset.canvasX, 0), itemY: num(t.dataset.canvasY, 0), el: t, moved: false,
        };
      } else if (t) { select(t.dataset.id); drag = null; } else {
        select(null); drag = { mode: 'pan', sx: e.clientX, sy: e.clientY, vb: vb.slice(), s: p.s };
      }
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener('pointermove', (e) => {
      if (drag && drag.mode === 'zone') {
        const p = pt(e), dx = p.x - drag.sx, dy = p.y - drag.sy, original = drag.start;
        const zone = { ...original }, layout = drag.layout;
        st.spec.zones[drag.index] = zone;
        if (drag.part === 'left') zone.leftOffset = num(original.leftOffset, 0) + Math.min(dx, layout.right - layout.left - 10);
        else if (drag.part === 'right') zone.rightOffset = num(original.rightOffset, 0) + Math.max(dx, layout.left - layout.right + 10);
        else if (drag.part === 'height') zone.yOffset = num(original.yOffset, 0) + Math.min(dy, layout.bottom - layout.y - 10);
        else if (drag.part === 'bottom') zone.bottomOffset = num(original.bottomOffset, 0) + Math.max(dy, layout.y - layout.bottom + 10);
        else if (drag.part === 'label') {
          zone.labelDx = num(original.labelDx, 0) + dx; zone.labelDy = num(original.labelDy, 0) + dy;
        }
        drag.moved = Math.hypot(dx, dy) > 1;
        renderConnections();
      } else if (connectStart && connectMode) {
        svg.querySelector('#connection-preview').setAttribute('d', connectionPath(connectStart.point, pt(e)));
      } else if (drag && ['route', 'bend', 'endpoint'].includes(drag.mode)) {
        const p = pt(e), connection = st.spec.connections[drag.index];
        if (drag.mode === 'endpoint') {
          const fixedId = connection[drag.end === 'from' ? 'to' : 'from'];
          const fixed = svg.querySelector(`.el[data-id="${CSS.escape(fixedId)}"]`);
          const end = nearestPort(fixed, p, connection.lane || 'P', connection[(drag.end === 'from' ? 'to' : 'from') + 'Port']);
          svg.querySelector('#connection-preview').setAttribute('d', `M${end.x} ${end.y}L${p.x} ${p.y}`);
        } else {
          if (drag.mode === 'bend') connection.waypoints[drag.bend] = { x: p.x, y: p.y };
          else if (Math.hypot(p.x - drag.sx, p.y - drag.sy) > 2) {
            connection.waypoints = drag.points.map((q) => ({ x: q.x + p.x - drag.sx, y: q.y + p.y - drag.sy }));
          }
          renderConnections();
        }
        drag.moved = true;
      } else if (drag && drag.mode === 'group') {
        const p = pt(e);
        drag.delta = { x: p.x - drag.sx, y: p.y - drag.sy };
        moveElements(drag.members, drag.delta.x, drag.delta.y, false);
        drag.moved = true; renderConnections();
      } else if (drag && drag.mode === 'pan') { vb[0] = drag.vb[0] - (e.clientX - drag.sx) * drag.s; vb[1] = drag.vb[1] - (e.clientY - drag.sy) * drag.s; applyVb(); }
      else if (drag && drag.mode === 'node') {
        const p = pt(e), moveX = Math.round((drag.inv || 1) * (p.x - drag.sx)), moveY = Math.round(p.y - drag.sy);
        const dx = drag.dx + moveX, dy = drag.dy + moveY;
        drag.el.setAttribute('transform', `matrix(${drag.scale} 0 0 ${drag.scale} ${drag.baseX + moveX} ${drag.baseY + moveY})`);
        drag.cur = { dx, dy }; drag.delta = { x: moveX, y: moveY }; drag.moved = true;
        renderConnections();
      } else showTip(e);
    });
    svg.addEventListener('pointerup', (e) => {
      if (drag && drag.mode === 'zone') {
        const changed = drag.moved;
        if (!changed) st.spec.zones[drag.index] = drag.original;
        drag = null;
        if (changed) render(true);
        fillInsp(); return;
      }
      if (drag && ['route', 'bend', 'endpoint', 'group'].includes(drag.mode)) {
        if (drag.mode === 'group' && drag.moved) {
          moveElements(drag.members, drag.delta.x, drag.delta.y, true);
          // Interior routing moves only when both attached symbols move together.
          for (const connection of st.spec.connections || []) {
            if (selectedIds.has(connection.from) && selectedIds.has(connection.to) && connection.waypoints) {
              connection.waypoints = connection.waypoints.map((p) => ({ x: p.x + drag.delta.x, y: p.y + drag.delta.y }));
            }
          }
        }
        if (drag.mode === 'endpoint') {
          const hit = document.elementFromPoint(e.clientX, e.clientY), target = hit && hit.closest('.el');
          const connection = st.spec.connections[drag.index], other = drag.end === 'from' ? 'to' : 'from';
          const handle = hit && hit.closest('.connection-port');
          const port = target && nearestPort(target, pt(e), connection.lane || 'P', handle ? handle.dataset.port : null);
          if (port && target.dataset.id !== connection[other]) {
            connection[drag.end] = target.dataset.id; connection[drag.end + 'Port'] = port.id;
            const from = svg.querySelector(`.el[data-id="${CSS.escape(connection.from)}"]`);
            const to = svg.querySelector(`.el[data-id="${CSS.escape(connection.to)}"]`);
            const ends = connectionEnds(connection, from, to);
            if (!connection.kind && (ends.from.hostSlot || ends.to.hostSlot)) { connection.kind = 'riser'; connection.style = connection.style || 'rigid'; }
            $('#connect-status').textContent = 'Connection endpoint updated.';
          } else $('#connect-status').textContent = 'Endpoint unchanged: drop on a matching port of another symbol.';
          svg.classList.toggle('connecting', connectMode);
        }
        const changed = drag.moved || drag.mode === 'endpoint';
        drag = null;
        if (changed) render(true);
        fillInsp(); return;
      }
      if (connectStart && connectMode) {
        const hit = document.elementFromPoint(e.clientX, e.clientY);
        const target = hit && hit.closest ? hit.closest('.el') : null;
        const handle = hit && hit.closest ? hit.closest('.connection-port') : null;
        const port = target ? nearestPort(target, pt(e), connectStart.port.lane, handle ? handle.dataset.port : null) : null;
        if (target && target.dataset.id !== connectStart.id && port) finishConnection(target.dataset.id, port);
        else {
          connectStart = null;
          const preview = svg.querySelector('#connection-preview');
          if (preview) preview.setAttribute('d', '');
          const status = el.querySelector('#connect-status');
          if (status) status.textContent = 'No connection made. Drop on a matching green port on another symbol.';
          highlight();
        }
        return;
      }
      if (drag && drag.mode === 'node' && drag.moved) {
        if (st.spec.freeform && !findItem(drag.id).host) {
          const item = findItem(drag.id);
          if (item) {
            item.item.x = drag.itemX + drag.cur.dx;
            item.item.y = drag.itemY + drag.cur.dy;
            const o = st.spec.overrides[drag.id];
            if (o) { delete o.dx; delete o.dy; }
            render(true);
          }
        } else {
          const o = st.spec.overrides[drag.id] || (st.spec.overrides[drag.id] = {});
          Object.assign(o, drag.cur);
          render(true);
        }
        fillInsp();
      }
      drag = null;
    });
    svg.addEventListener('pointercancel', () => {
      if (drag && drag.mode === 'zone') st.spec.zones[drag.index] = drag.original;
      if (drag && drag.mode === 'group') moveElements(drag.members, 0, 0, false);
      if (drag && ['route', 'bend'].includes(drag.mode)) {
        const connection = st.spec.connections[drag.index];
        if (drag.originalWaypoints) connection.waypoints = drag.originalWaypoints;
        else delete connection.waypoints;
      }
      connectStart = null; drag = null;
      svg.classList.toggle('connecting', connectMode);
      const preview = svg.querySelector('#connection-preview');
      if (preview) preview.setAttribute('d', '');
      renderConnections();
      highlight();
    });
    svg.addEventListener('dblclick', (e) => {
      const target = document.elementFromPoint(e.clientX, e.clientY);
      const bend = target && target.closest('.route-bend'), group = target && target.closest('.connection');
      if (bend && selectedConnection !== null) {
        st.spec.connections[selectedConnection].waypoints.splice(+bend.dataset.bend, 1);
      } else if (group && !connectMode) {
        selectedConnection = +group.dataset.connection; st.sel = null; selectedIds.clear();
        const connection = st.spec.connections[selectedConnection], p = pt(e);
        const points = connection.waypoints || (connection.waypoints = []);
        const line = svg.querySelector(`#connection-line-${selectedConnection}`);
        // Insert in path order, not click order, so multiple bends do not zigzag.
        const length = line.getTotalLength();
        const along = (point) => {
          let best = 0, distance = Infinity;
          for (let i = 0; i <= 200; i++) {
            const q = line.getPointAtLength(length * i / 200), d = Math.hypot(q.x - point.x, q.y - point.y);
            if (d < distance) { distance = d; best = i; }
          }
          return best;
        };
        const at = along(p), index = points.findIndex((q) => along(q) > at);
        points.splice(index < 0 ? points.length : index, 0, { x: p.x, y: p.y });
      } else return;
      render(true); fillInsp(); e.preventDefault();
    });
    svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
    {
      svg.addEventListener('dragover', (e) => { e.preventDefault(); svg.classList.add('drop-target'); });
      svg.addEventListener('dragleave', (e) => { if (!svg.contains(e.relatedTarget)) svg.classList.remove('drop-target'); });
      svg.addEventListener('drop', (e) => {
        e.preventDefault();
        const type = e.dataTransfer.getData('text/plain');
        if ((type && (catalog || []).some((entry) => entry.id === type && ['node', 'link', 'host'].includes(entry.kind)))
          || (type && (st.spec.customSymbols || []).some((symbol) => symbol.id === type))) {
          placeSymbol(type, pt(e));
        } else {
          svg.classList.remove('drop-target');
        }
      });
    }
    svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const p = pt(e), f = e.deltaY < 0 ? 0.88 : 1.14;
      vb = [p.x - (p.x - vb[0]) * f, p.y - (p.y - vb[1]) * f, vb[2] * f, vb[3] * f]; applyVb();
    }, { passive: false });

    function showTip(e) {
      const t = e.target.closest('.el');
      if (!t) { tip.style.display = 'none'; return; }
      const m = byId[t.dataset.type] || { name: t.dataset.type, desc: '' };
      tip.innerHTML = `<b>${esc(m.name)}</b><br>${esc(m.category || '')}<br><span>${esc(m.desc || '')}</span>`;
      const r = el.getBoundingClientRect();
      tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 270) + 'px'; tip.style.top = (e.clientY - r.top + 14) + 'px'; tip.style.display = 'block';
    }

    /* selection + inspector */
    function select(id) {
      selectedZone = null;
      st.sel = id; selectedIds.clear(); if (id) selectedIds.add(id);
      selectedConnection = null; renderConnections(); highlight(); fillInsp();
    }
    function highlight() {
      notifyChange();
      svg.querySelectorAll('.el').forEach((g) => {
        g.classList.toggle('sel', selectedIds.has(g.dataset.id) || g.dataset.id === st.sel);
        g.classList.toggle('connect-source', !!connectStart && g.dataset.id === connectStart.id);
        g.classList.toggle('connect-candidate', connectMode && (!connectStart || g.dataset.id !== connectStart.id));
        g.querySelectorAll('.connection-port').forEach((port) => {
          port.classList.toggle('port-unavailable', !!connectStart && connectStart.port.lane !== 'any'
            && port.dataset.lane !== 'any' && port.dataset.lane !== connectStart.port.lane);
          port.classList.toggle('port-source', !!connectStart && g.dataset.id === connectStart.id && port.dataset.port === connectStart.port.id);
        });
      });
      svg.querySelectorAll('.connection').forEach((g) => { g.classList.toggle('sel', +g.dataset.connection === selectedConnection); });
      updateSelectionControls();
    }
    function internalValveEditor(item) {
      const element = svg.querySelector(`.el[data-id="${CSS.escape(item.id)}"]`);
      const options = internalValveOptions(element);
      if (!options.pipes.length && item.internalValves === undefined) return;
      insp.querySelector('#i_valve_section').insertAdjacentHTML('beforeend', `<details id="i_internal_valves" open><summary>Internal valves</summary>`
        + '<p>Add an internal valve, then choose its pipe, type and position. Valid changes update the drawing automatically when you leave a field.</p>'
        + '<button id="i_valve_add">Add internal valve</button>'
        + `<label>Customize internal valves (replace defaults) <input id="i_valves_custom" type="checkbox"${item.internalValves !== undefined ? ' checked' : ''}></label>`
        + '<small>Position: 0% = pipe start, 50% = middle, 100% = end. P = process, S = service, U = umbilical. Adding/removing valves does not change ports or piping. An empty customized list removes all built-in valves. Provider and rating are unverified metadata; valve state does not simulate flow.</small>'
        + '<div id="i_valve_rows"></div>'
        + '<button id="i_valve_restore">Restore symbol valve defaults</button>'
        + '<div id="i_valve_error" role="alert" style="color:#D32F2F"></div></details>');
      const custom = insp.querySelector('#i_valves_custom'), rows = insp.querySelector('#i_valve_rows');
      const errorBox = insp.querySelector('#i_valve_error');
      const addRow = (entry) => {
        const row = document.createElement('div'); row.className = 'internal-valve-row';
        const choices = options.pipes.map((pipe) => `<option value="${esc(pipe.id)}"${entry.pipe === pipe.id ? ' selected' : ''}>${esc(pipe.id)} (${esc(pipe.lane)})</option>`).join('');
        row.innerHTML = `<label>Valve ID <input class="valve-id" required value="${esc(entry.id || '')}" pattern="[A-Za-z0-9_\\-]+"></label>`
          + `<label>Internal pipe <select class="valve-pipe">${options.pipes.some((pipe) => pipe.id === entry.pipe) ? '' : `<option value="${esc(entry.pipe || '')}">Choose pipe${entry.pipe ? ' (missing: ' + esc(entry.pipe) + ')' : ''}</option>`}${choices}</select></label>`
          + `<label>Type <select class="valve-kind">${Object.entries(EQUIPMENT_OPTIONS.valveTypes).map(([id, label]) =>
            `<option value="${id}"${(entry.kind || 'gate') === id ? ' selected' : ''}>${esc(label)}</option>`).join('')}</select></label>`
          + `<label>Position (%) <input class="valve-position" type="number" min="0" max="100" step="any" required value="${num(entry.position, 50)}"></label>`
          + `<label>Closed <input class="valve-closed" type="checkbox"${entry.closed ? ' checked' : ''}></label>`
          + ['tag', 'label', 'provider', 'rating'].map((key) => `<label>${key === 'rating' ? 'Pressure rating (with units)' : key} <input class="valve-${key}" value="${esc(entry[key] || '')}"></label>`).join('')
          + '<button class="valve-remove">Remove valve</button><hr>';
        row.querySelectorAll('input,select').forEach((input) => { input.onchange = () => { custom.checked = true; saveValves(); }; });
        row.querySelector('.valve-remove').onclick = () => { row.remove(); custom.checked = true; saveValves(); };
        rows.appendChild(row);
      };
      for (const entry of Array.isArray(item.internalValves) ? item.internalValves : options.defaults) addRow(entry);
      insp.querySelector('#i_valve_add').onclick = () => {
        if (rows.children.length >= EQUIPMENT_OPTIONS.maxInternalValves) {
          errorBox.textContent = `Use at most ${EQUIPMENT_OPTIONS.maxInternalValves} valves.`; return;
        }
        const used = new Set(Array.from(rows.querySelectorAll('.valve-id')).map((input) => input.value));
        let index = 1; while (used.has(`valve_${index}`)) index++;
        const pipes = internalValveOptions(svg.querySelector(`.el[data-id="${CSS.escape(item.id)}"]`)).pipes;
        addRow({ id: `valve_${index}`, pipe: pipes[0]?.id || '', kind: 'gate', position: 50 });
        custom.checked = true;
        saveValves();
      };
      const saveValves = () => {
        errorBox.textContent = '';
        const candidate = { ...item };
        if (custom.checked) {
          const invalid = Array.from(rows.querySelectorAll('input')).find((input) => !input.checkValidity());
          if (invalid) { errorBox.textContent = 'Valve changes not saved: correct the highlighted field.'; invalid.reportValidity(); return; }
          candidate.internalValves = Array.from(rows.children).map((row) => ({
            id: row.querySelector('.valve-id').value.trim(), pipe: row.querySelector('.valve-pipe').value,
            kind: row.querySelector('.valve-kind').value, position: row.querySelector('.valve-position').valueAsNumber,
            closed: row.querySelector('.valve-closed').checked,
            ...Object.fromEntries(['tag', 'label', 'provider', 'rating'].map((key) => [key, row.querySelector(`.valve-${key}`).value])),
          }));
        } else delete candidate.internalValves;
        const currentOptions = internalValveOptions(svg.querySelector(`.el[data-id="${CSS.escape(item.id)}"]`));
        const errors = internalValveErrors(candidate, new Set(currentOptions.pipes.map((pipe) => pipe.id)));
        if (errors.length) { errorBox.textContent = errors.join(' '); return; }
        if (candidate.internalValves === undefined) delete item.internalValves;
        else item.internalValves = candidate.internalValves;
        render(true);
      };
      custom.onchange = () => {
        saveValves();
        if (!custom.checked && !errorBox.textContent) fillInsp();
      };
      insp.querySelector('#i_valve_restore').onclick = () => {
        delete item.internalValves; render(true); fillInsp();
        insp.querySelector('#i_internal_valves').open = true;
      };
    }

    function installationControls(item) {
      return '<details open><summary>Installation tags</summary>'
        + `<label>Status <select id="i_installationStatus">${['Unspecified', 'Existing', 'New'].map((status) =>
          `<option${(item.installationStatus || 'Unspecified') === status ? ' selected' : ''}>${status}</option>`).join('')}</select></label>`
        + ['provider', 'installationType', 'rating'].map((key) =>
          `<label>${{ provider: 'Provider', installationType: 'Installation type', rating: 'Rating (e.g. 10 K psi)' }[key]} <input id="i_${key}" value="${esc(item[key] || '')}"></label>`).join('')
        + `<label>Installed length (km) <input id="i_installedLengthKm" type="number" min="0" step="any" value="${item.installedLengthKm === undefined ? '' : esc(item.installedLengthKm)}"></label></details>`;
    }

    function bindInstallation(item) {
      ['installationStatus', 'provider', 'installationType', 'rating', 'installedLengthKm'].forEach((key) => {
        insp.querySelector(`#i_${key}`).onchange = (event) => {
          if (!event.target.reportValidity()) return;
          if (key === 'installedLengthKm') {
            if (event.target.value === '') delete item[key];
            else item[key] = event.target.valueAsNumber;
          } else item[key] = event.target.value;
          render(true);
        };
      });
    }

    function labelStyleControls(item) {
      const style = item.labelStyle || {};
      const select = (field, title, choices) => `<label>${title} <select id="i_label_${field}">`
        + Object.entries(choices).map(([value, name]) =>
          `<option value="${value}"${(style[field] || 'auto') === value ? ' selected' : ''}>${name}</option>`).join('') + '</select></label>';
      return '<details><summary>Label font and placement</summary>'
        + select('font', 'Font', { auto: 'Theme default', sans: 'Arial / sans serif', serif: 'Georgia / serif', mono: 'Courier New / monospace' })
        + `<label>Font size (0 = automatic) <input id="i_label_size" type="number" min="0" max="72" step="0.5" required value="${num(style.size, 0)}"></label>`
        + select('weight', 'Weight', { auto: 'Symbol default', normal: 'Normal', bold: 'Bold' })
        + `<label>Italic <input id="i_label_italic" type="checkbox"${style.italic ? ' checked' : ''}></label>`
        + `<label>Label dx <input id="i_label_dx" type="number" step="any" required value="${num(style.dx, 0)}"></label>`
        + `<label>Label dy <input id="i_label_dy" type="number" step="any" required value="${num(style.dy, 0)}"></label>`
        + `<label>Additional rotation (degrees) <input id="i_label_rotation" type="number" min="-180" max="180" step="any" required value="${num(style.rotation, 0)}"></label>`
        + select('anchor', 'Alignment', { auto: 'Symbol default', start: 'Left', middle: 'Center', end: 'Right' })
        + '<small>Offsets move the label only, right/down in symbol coordinates. Font sizes scale with the symbol.</small>'
        + '<button id="i_label_reset">Reset label style</button></details>';
    }

    function bindLabelStyle(item) {
      const controls = Array.from(insp.querySelectorAll('[id^="i_label_"]')).filter((control) => control.id !== 'i_label_reset');
      controls.forEach((control) => { control.onchange = () => {
        if (controls.some((input) => !input.reportValidity())) return;
        item.labelStyle = Object.fromEntries(controls.map((input) => [
          input.id.slice('i_label_'.length),
          input.type === 'checkbox' ? input.checked : input.type === 'number' ? input.valueAsNumber : input.value,
        ]));
        render(true);
      }; });
      insp.querySelector('#i_label_reset').onclick = () => {
        delete item.labelStyle; render(true); fillInsp();
      };
    }

    function fillInsp() {
      if (selectedZone !== null) { fillZoneInspector(); return; }
      if (selectedIds.size > 1) {
        insp.style.display = 'block';
        insp.innerHTML = `<b>${selectedIds.size} elements selected</b><p>Drag any selected element to move the block. Shift-click to add/remove an element.</p><button id="i_group_delete">Delete selected</button>`;
        insp.querySelector('#i_group_delete').onclick = removeSelected;
        return;
      }
      if (selectedConnection !== null) {
        const connection = (st.spec.connections || [])[selectedConnection];
        if (!connection) { selectedConnection = null; insp.style.display = 'none'; return; }
        insp.style.display = 'block';
        const from = svg.querySelector(`.el[data-id="${CSS.escape(connection.from)}"]`);
        const to = svg.querySelector(`.el[data-id="${CSS.escape(connection.to)}"]`);
        const ends = from && to ? connectionEnds(connection, from, to) : null;
        const hostAtStart = ends && ends.from.hostSlot;
        const hostElement = ends && (hostAtStart ? from : ends.to.hostSlot ? to : null);
        const tubes = hostElement ? Array.from(hostElement.querySelectorAll('.j-tube-port')) : [];
        const selectedPort = hostAtStart ? connection.fromPort : connection.toPort;
        insp.innerHTML = `<b>${esc(EQUIPMENT_OPTIONS.connectionKinds[connection.kind] || 'Connection')}</b><br><small>${esc(connection.from || '')} → ${esc(connection.to || '')}</small>`
          + `<label>Physical connection <select id="i_connection_kind">${Object.entries(EQUIPMENT_OPTIONS.connectionKinds).map(([id, label]) =>
            `<option value="${id}"${(connection.kind || '') === id ? ' selected' : ''}>${esc(label)}</option>`).join('')}</select></label>`
          + `<label>Connection type <select id="i_connection_type"><option value="">Automatic (ports / train fluid)</option>${Object.entries(CONNECTION_TYPES).map(([id, type]) =>
            `<option value="${id}"${connection.connectionType === id ? ' selected' : ''}>${esc(type.label)}</option>`).join('')}</select></label>`
          + `<label>Connection label <input id="i_connection_label" value="${esc(connection.label || '')}"></label>`
          + labelStyleControls(connection)
          + installationControls(connection)
          + `<label>Line thickness (drawing units) <input id="i_connection_width" type="number" required min="0.5" max="20" step="0.5" value="${num(connection.width, connection.kind === 'riser' ? 2.5 : num(st.spec.connectionWidth, 2.5))}"></label>`
          + '<button id="i_default_width">Use default thickness</button>'
          + `<label>Flow direction <select id="i_connection_flow">${['auto', 'forward', 'reverse', 'none'].map((value) => `<option value="${value}"${(connection.flow || 'auto') === value ? ' selected' : ''}>${value}</option>`).join('')}</select></label>`
          + '<p>Drag the line to move its bends; drag blue handles to edit bends or reconnect ends. Double-click a line to add a bend, or a bend to remove it.</p><button id="i_add_bend">Add bend</button> <button id="i_auto_route">Auto route</button>'
          + '<small>Type changes service/style, not the attachment ports.</small>'
          + `<label>Riser shape <select id="i_riser_style">${Object.entries(EQUIPMENT_OPTIONS.riserStyles).map(([id, label]) =>
            `<option value="${id}"${(EQUIPMENT_OPTIONS.riserStyles[connection.style] ? connection.style : 'rigid') === id ? ' selected' : ''}>${esc(label)}</option>`).join('')}</select></label>`
          + '<small>Choosing a riser shape classifies the connection as a riser. Manual bends are retained and rounded; Auto route clears them.</small>'
          + `<label>Add PSV to riser <input id="i_psv" type="checkbox"${connection.psv ? ' checked' : ''}></label>`
          + `<label>PSV tag <input id="i_psv_tag" value="${esc(connection.psvTag || '')}"></label>`
          + (hostElement ? '<small>PSV is fixed at the topside riser termination, at deck level when J-tubes are shown.</small>' : '')
          + `<label>PSV position (%; non-host risers only) <input id="i_psv_position" type="number" min="0" max="100" step="any" required${hostElement ? ' disabled' : ''} value="${num(connection.psvPosition, 50)}"></label>`
          + (tubes.length ? `<label>Host J-tube <select id="i_jtube">${tubes.map((port) =>
            `<option value="${esc(port.dataset.port)}"${selectedPort === port.dataset.port ? ' selected' : ''}>${esc(port.dataset.label)}</option>`).join('')}</select></label>` : '')
          + `<br><button id="i_delete">Delete ${connection.kind === 'riser' ? 'riser' : 'connection'}</button>`;
        bindLabelStyle(connection);
        bindInstallation(connection);
        insp.querySelector('#i_psv').onchange = (event) => {
          connection.psv = event.target.checked;
          if (connection.psv) { connection.kind = 'riser'; connection.style = connection.style || 'rigid'; }
          render(true); fillInsp();
        };
        insp.querySelector('#i_psv_tag').onchange = (event) => {
          connection.psvTag = event.target.value; render(true); fillInsp();
        };
        insp.querySelector('#i_psv_position').onchange = (event) => {
          if (!event.target.reportValidity()) return;
          connection.psvPosition = event.target.valueAsNumber; render(true); fillInsp();
        };
        insp.querySelector('#i_connection_type').onchange = (event) => {
          if (event.target.value) connection.connectionType = event.target.value;
          else delete connection.connectionType;
          render(true); fillInsp();
        };
        insp.querySelector('#i_connection_kind').onchange = (event) => {
          if (event.target.value) {
            connection.kind = event.target.value;
            if (connection.kind === 'riser') connection.style = connection.style || 'rigid';
          }
          else delete connection.kind;
          render(true); fillInsp();
        };
        insp.querySelector('#i_connection_label').onchange = (event) => {
          connection.label = event.target.value;
          render(true); fillInsp();
        };
        insp.querySelector('#i_connection_width').onchange = (event) => {
          if (!event.target.reportValidity() || !Number.isFinite(event.target.valueAsNumber)) return;
          connection.width = event.target.valueAsNumber; render(true); fillInsp();
        };
        insp.querySelector('#i_default_width').onclick = () => { delete connection.width; render(true); fillInsp(); };
        insp.querySelector('#i_connection_flow').onchange = (event) => {
          connection.flow = event.target.value; render(true); fillInsp();
        };
        insp.querySelector('#i_add_bend').onclick = () => {
          (connection.waypoints || (connection.waypoints = [])).push(defaultBend(selectedConnection)); render(true); fillInsp();
        };
        insp.querySelector('#i_auto_route').onclick = () => {
          delete connection.waypoints; render(true); fillInsp();
        };
        const style = insp.querySelector('#i_riser_style');
        if (style) style.onchange = () => {
          connection.kind = 'riser'; connection.style = style.value;
          render(true); fillInsp();
        };
        const tube = insp.querySelector('#i_jtube');
        if (tube) tube.onchange = () => {
          connection[hostAtStart ? 'fromPort' : 'toPort'] = tube.value;
          connection.kind = 'riser'; connection.style = connection.style || 'rigid';
          render(true); fillInsp();
        };
        insp.querySelector('#i_delete').onclick = removeSelected;
        return;
      }
      if (!st.sel) { insp.style.display = 'none'; return; }
      const found = findItem(st.sel);
      if (!found) { insp.style.display = 'none'; return; }
      const item = found.item;
      const m = byId[item.type] || { name: item.type };
      const o = st.spec.overrides[st.sel] || {};
      insp.style.display = 'block';
      insp.innerHTML = `<b>${esc(m.name)}</b> <small>${esc(st.sel)}</small>`
        + '<p><small>Changes update automatically when you leave a field. Save a case version to keep your work.</small></p>'
        + '<div id="i_valve_section"></div>'
        + `<label>Label <input id="i_lab" value="${esc(o.label !== undefined ? o.label : (item.label || ''))}"></label>`
        + labelStyleControls(item)
        + installationControls(item)
        + (LINK[item.type] ? `<label>Flowline thickness <input id="i_line_width" type="number" required min="0.5" max="20" step="0.5" value="${num(item.lineWidth, num(st.spec.connectionWidth, 2.2))}"></label>` : '')
        + `<label>Component size (%) <input id="i_scale" type="number" min="1" step="any" value="${Math.round(componentScale(o) * 10000) / 100}"></label>`
        + `<div class="size-actions"><button id="i_smaller" title="Shrink selected component">Smaller</button><button id="i_larger" title="Enlarge selected component">Larger</button><button id="i_size_reset" title="Restore original component size">100%</button></div>`
        + (!st.spec.freeform ? `<label>dx <input id="i_dx" type="number" value="${o.dx || 0}"> dy <input id="i_dy" type="number" value="${o.dy || 0}"></label>` : '')
        + `<button id="i_copy">Copy</button> <button id="i_delete">Delete</button>`
        + `<button id="i_hide">Hide</button> <button id="i_reset">Reset</button>`;
      const equipment = !HOSTS[item.type] && !LINK[item.type];
      bindLabelStyle(item);
      bindInstallation(item);
      internalValveEditor(item);
      const currentPorts = equipment ? Array.from(svg.querySelector(`.el[data-id="${CSS.escape(st.sel)}"]`).querySelectorAll('.connection-port')) : [];
      const config = item.portConfig || { mode: 'additional', lane: 'P', inlets: 0, outlets: 0 };
      const riser = ['riser_base', 'riser_skid'].includes(item.type) && !item.riserDetail;
      const counts = riser ? riserHubCounts(item) : null;
      const limits = item.designLimits || {}, defaults = st.spec.designLimits || {};
      insp.insertAdjacentHTML('beforeend', '<hr><b>Element options</b>'
        + (riser ? `<label>Independent process / service / umbilical hubs <input id="i_independent_hubs" type="checkbox"${item.riserPorts ? ' checked' : ''}></label>`
          + '<div id="i_independent_counts">' + ['P', 'S', 'U'].map((lane) =>
            `<b>${lane === 'P' ? 'Process' : lane === 'S' ? 'Chemical / service' : 'Umbilical'}</b>`
            + ['inlets', 'outlets'].map((side) => `<label>${side} <input id="i_count_${lane}_${side}" type="number" min="0" max="${EQUIPMENT_OPTIONS.maxPorts}" step="1" required value="${counts[lane][side]}"></label>`).join('')).join('')
          + '</div><small>Independent counts replace legacy pair toggles and single-lane counts; existing connections remain protected.</small>' : '')
        + (item.type === 'plet' ? `<label>PLET standard ports <select id="i_plet_ports">${Object.entries({
          PSU: 'Process + service + umbilical (3 pairs)', P: 'Process only (1 inlet + 1 outlet)',
          S: 'Service / chemical only (1 inlet + 1 outlet)', U: 'Umbilical only (1 inlet + 1 outlet)',
        }).map(([value, label]) => `<option value="${value}"${(item.pletPorts || 'PSU') === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label><small>Custom hubs below add to these standard ports. Disable customization for exactly one pair.</small>` : '')
        + (['riser_base', 'riser_skid'].includes(item.type) && !item.riserDetail
          ? `<label>Include chemical / service connections <input id="i_service_ports" type="checkbox"${item.servicePorts ? ' checked' : ''}></label>`
            + `<label>Include umbilical connections <input id="i_umbilical_ports" type="checkbox"${item.umbilicalPorts ? ' checked' : ''}></label>`
            + `<label>Bundle S inlet into U inlet (one umbilical riser) <input id="i_bundle_service" type="checkbox"${item.bundleServiceInlet ? ' checked' : ''}></label>`
            + '<small>Hides S-left and brings chemical service to an internal U-left junction. Connect U-left to one J-tube with an umbilical riser. Disconnect existing S-left lines first. Bundled services are not fluid mixing.</small>'
            + '<small>Adds S and/or U inlet/outlet pairs alongside process ports. Connected ports cannot be disabled.</small>' : '')
        + (HOSTS[item.type] ? `<label>Available J-tubes <input id="i_jtube_count" type="number" min="0" max="${EQUIPMENT_OPTIONS.maxPorts}" step="1" required value="${slotsOf(item).length}"></label>` : '')
        + (['jacket', 'platform'].includes(item.type) ? `<label>Draw J-tubes with pulled-in risers <input id="i_show_jtubes" type="checkbox"${item.showJTubes ? ' checked' : ''}></label><small>Draws guide-tube walls and the attached riser inside, up to deck level. Schematic only, not a clearance or bend-radius check.</small>` : '')
        + (['jacket', 'platform'].includes(item.type) ? `<label>J-tube seabed exit <select id="i_jtube_side"><option value="left"${item.jTubeSide !== 'right' ? ' selected' : ''}>Left</option><option value="right"${item.jTubeSide === 'right' ? ' selected' : ''}>Right</option></select></label>` : '')
        + (item.type === 'template' ? `<label>Include HIPPS <input id="i_hipps" type="checkbox"${item.hipps !== false ? ' checked' : ''}></label>`
          + `<label>Well count <input id="i_wells" type="number" min="0" max="24" step="1" required value="${num(item.wells, 4)}"></label>`
          + `<label>Xmas tree type <select id="i_tree"><option value="">Existing well slots</option>${Object.entries(EQUIPMENT_OPTIONS.treeTypes).map(([id, name]) =>
            `<option value="${id}"${item.treeType === id ? ' selected' : ''}>${esc(name)}</option>`).join('')}</select></label>` : '')
        + (equipment && !item.riserDetail ? `<label>Customize hubs <input id="i_ports_enabled" type="checkbox"${item.portConfig ? ' checked' : ''}></label>`
          + `<label>Port mode <select id="i_port_mode"><option value="additional"${config.mode === 'additional' ? ' selected' : ''}>Additional hubs</option><option value="replace"${config.mode === 'replace' ? ' selected' : ''}>Total hubs on lane</option></select></label>`
          + `<label>Port lane <select id="i_port_lane">${['P', 'S', 'U'].map((lane) => `<option${config.lane === lane ? ' selected' : ''}>${lane}</option>`).join('')}</select></label>`
          + `<label>Inlet connections <input id="i_inlets" type="number" min="0" max="${EQUIPMENT_OPTIONS.maxPorts}" step="1" required value="${config.inlets}"></label>`
          + `<label>Outlet connections <input id="i_outlets" type="number" min="0" max="${EQUIPMENT_OPTIONS.maxPorts}" step="1" required value="${config.outlets}"></label>`
          + '<small>Count changes automatically update hubs and enable customization. Additional keeps existing ports. To remove unused custom hubs, uncheck Customize without changing counts.</small>' : '')
        + '<p><b>Maximum design limits</b><br><small>Blank inherits the layout default. User specifications, not engineering verification.</small></p>'
        + Object.entries(EQUIPMENT_OPTIONS.designFields).map(([key, field]) =>
          `<label>${esc(field.label)} <input id="i_limit_${key}" type="number" step="any" min="${field.minimum}" value="${limits[key] === undefined ? '' : limits[key]}" placeholder="${defaults[key] === undefined ? 'Not specified' : 'Default: ' + defaults[key]}"></label>`).join('')
        + '<div id="i_equipment_error" role="alert" style="color:#b42318"></div>');
      if (riser) {
        const independent = insp.querySelector('#i_independent_hubs');
        const updateCounts = () => {
          insp.querySelector('#i_independent_counts').style.display = independent.checked ? '' : 'none';
          for (const input of insp.querySelectorAll('#i_independent_counts input')) input.disabled = !independent.checked;
          for (const id of ['i_service_ports', 'i_umbilical_ports', 'i_ports_enabled', 'i_port_mode', 'i_port_lane', 'i_inlets', 'i_outlets']) {
            insp.querySelector('#' + id).disabled = independent.checked;
          }
        };
        independent.onchange = updateCounts; updateCounts();
        const defaultRoutes = () => ['P', 'S', 'U'].flatMap((lane) =>
          (currentPorts.some((port) => port.dataset.port === `${lane}-left`) || (lane === 'S' && item.bundleServiceInlet))
            && currentPorts.some((port) => port.dataset.port === `${lane}-right`)
            ? [{ id: lane, from: `${lane}-left`, to: `${lane}-right`,
              connectionType: lane === 'P' ? 'multiphase' : lane === 'S' ? 'chemical' : 'umbilical_static' }] : []);
        insp.insertAdjacentHTML('beforeend',
          '<hr><button id="i_furb_example">Load FURB starting layout</button><small>Applies immediately: gas/umbilical through-lines and a chemical take-off. Existing hubs and external lines are retained; missing FURB ports are added.</small>'
          + `<label>Custom internal piping (replace default lines) <input id="i_custom_piping" type="checkbox"${item.internalRoutes !== undefined ? ' checked' : ''}></label>`
          + '<div id="i_routes"><div id="i_route_rows"></div><button id="i_add_route">Add internal route</button>'
          + '<small>From/To use port IDs. For a chemical take-off, first add an umbilical route named umb (U-left to U-right), then add a chemical route from @umb to S-right. A junction is a schematic take-off, not mixing all umbilical services. Empty routes remove all default piping. Complete each route to save it automatically; invalid drafts leave the drawing unchanged.</small>'
          + `<datalist id="i_route_ports">${currentPorts.map((port) => `<option value="${esc(port.dataset.port)}"></option>`).join('')}${item.bundleServiceInlet ? '<option value="S-left"></option>' : ''}</datalist>`
          + '<datalist id="i_route_sources"></datalist></div>');
        const routedPorts = new Set((item.internalRoutes || defaultRoutes()).flatMap((route) => [route.from, route.to]));
        const unusedPorts = currentPorts.filter((port) => !routedPorts.has(port.dataset.port));
        if (unusedPorts.length) {
          insp.querySelector('#i_routes').insertAdjacentHTML('beforeend',
            '<hr><b>Connect an unused hub to an internal line</b>'
            + '<small>Added hubs are not automatically piped internally. This adds a branch without changing external connections (for example P outlet 2 to process).</small>'
            + `<label>Hub <select id="i_internal_hub">${unusedPorts.map((port) =>
              `<option value="${esc(port.dataset.port)}">${esc(port.dataset.label)} (${esc(port.dataset.port)})</option>`).join('')}</select></label>`
            + '<label>Internal line <select id="i_internal_trunk"></select></label>'
            + '<button id="i_connect_internal_hub">Connect hub to internal line</button>');
        }
        const refreshRouteSources = () => {
          const sources = [...currentPorts.map((port) => port.dataset.port), ...(item.bundleServiceInlet ? ['S-left'] : []),
            ...Array.from(insp.querySelectorAll('.route-id')).map((input) => '@' + input.value.trim())];
          insp.querySelector('#i_route_sources').innerHTML = sources.filter((source) => source !== '@')
            .map((source) => `<option value="${esc(source)}"></option>`).join('');
          const trunks = insp.querySelector('#i_internal_trunk');
          if (trunks) {
            const previous = trunks.value, ids = new Set(currentPorts.map((port) => port.dataset.port));
            if (item.bundleServiceInlet) ids.add('S-left');
            trunks.innerHTML = Array.from(insp.querySelectorAll('.internal-route-row')).filter((row) =>
              ids.has(row.querySelector('.route-from').value) && ids.has(row.querySelector('.route-to').value))
              .map((row) => {
                const id = row.querySelector('.route-id').value.trim();
                return `<option value="${esc(id)}">${esc(id)}: ${esc(row.querySelector('.route-from').value)} → ${esc(row.querySelector('.route-to').value)}</option>`;
              }).join('');
            if (Array.from(trunks.options).some((option) => option.value === previous)) trunks.value = previous;
          }
        };
        const addRow = (route) => {
          const row = document.createElement('div'); row.className = 'internal-route-row';
          row.innerHTML = `<label>Route ID <input class="route-id" value="${esc(route.id)}"></label>`
            + `<label>From port / @route junction <input class="route-from" list="i_route_sources" value="${esc(route.from)}"></label>`
            + `<label>To port <input class="route-to" list="i_route_ports" value="${esc(route.to)}"></label>`
            + `<label>Fluid / service <select class="route-service">${Object.entries(CONNECTION_TYPES).map(([id, type]) =>
              `<option value="${id}"${route.connectionType === id ? ' selected' : ''}>${esc(type.label)}</option>`).join('')}</select></label>`
            + '<button class="remove-route">Remove route</button>';
          row.querySelector('.route-id').oninput = refreshRouteSources;
          row.querySelector('.route-from').oninput = refreshRouteSources;
          row.querySelector('.route-to').oninput = refreshRouteSources;
          row.querySelector('.remove-route').onclick = () => { row.remove(); refreshRouteSources(); saveOptions(); };
          insp.querySelector('#i_route_rows').appendChild(row);
          refreshRouteSources();
        };
        for (const route of item.internalRoutes === undefined ? defaultRoutes() : item.internalRoutes) addRow(route);
        const connectHub = insp.querySelector('#i_connect_internal_hub');
        if (connectHub) connectHub.onclick = () => {
          const errorBox = insp.querySelector('#i_equipment_error');
          errorBox.textContent = '';
          const rows = Array.from(insp.querySelectorAll('.internal-route-row'));
          const portId = insp.querySelector('#i_internal_hub').value;
          const trunkId = insp.querySelector('#i_internal_trunk').value;
          const trunk = rows.find((row) => row.querySelector('.route-id').value.trim() === trunkId);
          if (!trunk) { errorBox.textContent = 'Choose a direct port-to-port internal line.'; return; }
          if (rows.some((row) => ['.route-from', '.route-to'].some((field) => row.querySelector(field).value === portId))) {
            errorBox.textContent = 'This hub is already internally routed. Edit or remove its existing route first.'; return;
          }
          const service = trunk.querySelector('.route-service').value;
          const port = currentPorts.find((port) => port.dataset.port === portId);
          if (!port || port.dataset.lane !== serviceLane(CONNECTION_TYPES[service])) {
            errorBox.textContent = 'The hub and internal line must use the same service lane.'; return;
          }
          const ids = new Set(rows.map((row) => row.querySelector('.route-id').value.trim()));
          const stem = `branch_${portId}`;
          let id = stem, suffix = 2;
          while (ids.has(id)) id = `${stem}_${suffix++}`;
          addRow({ id, from: '@' + trunkId, to: portId, connectionType: service });
          saveOptions();
        };
        insp.querySelector('#i_add_route').onclick = () => addRow({
          id: `route_${Date.now()}`, from: '', to: '', connectionType: 'chemical',
        });
        const toggleRoutes = () => { insp.querySelector('#i_routes').style.display = insp.querySelector('#i_custom_piping').checked ? '' : 'none'; };
        insp.querySelector('#i_custom_piping').onchange = () => {
          if (insp.querySelector('#i_custom_piping').checked && item.internalRoutes === undefined) {
            insp.querySelector('#i_route_rows').innerHTML = '';
            for (const route of defaultRoutes()) addRow(route);
          }
          toggleRoutes();
        };
        toggleRoutes();
        insp.querySelector('#i_furb_example').onclick = () => {
          independent.checked = true; updateCounts();
          for (const lane of ['P', 'S', 'U']) for (const side of ['inlets', 'outlets']) {
            insp.querySelector(`#i_count_${lane}_${side}`).value = Math.max(
              EQUIPMENT_OPTIONS.furb.riserPorts[lane][side], riserHubCounts(item)[lane][side]);
          }
          insp.querySelector('#i_custom_piping').checked = true; toggleRoutes();
          insp.querySelector('#i_route_rows').innerHTML = '';
          for (const route of EQUIPMENT_OPTIONS.furb.internalRoutes) addRow(route);
          saveOptions();
          const errorBox = insp.querySelector('#i_equipment_error');
          if (errorBox.textContent) errorBox.scrollIntoView({ block: 'center' });
        };
      }
      if (currentPorts.length && !item.riserDetail) {
        insp.insertAdjacentHTML('beforeend', '<hr><b>Individual inlet / outlet</b>'
          + `<label>Port <select id="i_port_id">${currentPorts.map((p) => `<option value="${esc(p.dataset.port)}">${esc(p.dataset.port)} - ${item.type === 'plet' ? (p.dataset.direction === '-1' ? 'Inlet (left)' : 'Outlet (right)') + ' - ' : ''}${esc(p.dataset.label)}</option>`).join('')}</select></label>`
          + '<label>Port label <input id="i_port_label"></label>'
          + '<label>Compatible lane <select id="i_port_compatible"><option>P</option><option>S</option><option>U</option></select></label>'
          + `<label>Fluid / service <select id="i_port_service"><option value="">Automatic</option>${Object.entries(CONNECTION_TYPES).map(([id, type]) => `<option value="${id}">${esc(type.label)}</option>`).join('')}</select></label>`
          + '<small>P: process fluids; S: service/chemical; U: umbilical. Assigned fluid/service automatically sets PLET compatibility. Configure both inlet and outlet; disconnect incompatible lines before changing service.</small>'
          + '<div id="i_port_error" role="alert" style="color:#b42318"></div>');
        const portSelect = insp.querySelector('#i_port_id');
        const showPort = () => {
          const port = currentPorts.find((p) => p.dataset.port === portSelect.value);
          const settings = (item.portOverrides || {})[portSelect.value] || {};
          insp.querySelector('#i_port_label').value = settings.label || port.dataset.label;
          insp.querySelector('#i_port_compatible').value = port.dataset.lane;
          insp.querySelector('#i_port_service').value = settings.connectionType || '';
          insp.querySelector('#i_port_compatible').disabled = item.type === 'plet'
            && !!CONNECTION_TYPES[settings.connectionType];
        };
        portSelect.onchange = showPort; showPort();
        if (item.type === 'plet') insp.querySelector('#i_port_service').onchange = (event) => {
          const service = CONNECTION_TYPES[event.target.value];
          insp.querySelector('#i_port_compatible').disabled = !!service;
          if (service) insp.querySelector('#i_port_compatible').value = serviceLane(service);
        };
        const savePort = (event) => {
          insp.querySelector('#i_port_error').textContent = '';
          const id = portSelect.value, requestedLane = insp.querySelector('#i_port_compatible').value;
          const service = CONNECTION_TYPES[insp.querySelector('#i_port_service').value];
          const lane = item.type === 'plet' && service ? serviceLane(service) : requestedLane;
          if (item.bundleServiceInlet && id === 'U-left'
            && (lane !== 'U' || !['', 'umbilical_static', 'umbilical_dynamic'].includes(insp.querySelector('#i_port_service').value))) {
            insp.querySelector('#i_port_error').textContent = 'The bundled inlet must remain U-compatible and use Automatic, Static umbilical or Dynamic umbilical.'; return;
          }
          if ((st.spec.connections || []).some((connection) => ['from', 'to'].some((end) =>
            connection[end] === item.id && connection[end + 'Port'] === id
              && (connection.lane || 'P') !== lane))) {
            insp.querySelector('#i_port_error').textContent = 'This port is connected. Reconnect or delete its connection before changing lane.'; return;
          }
          (item.portOverrides || (item.portOverrides = {}))[id] = {
            label: insp.querySelector('#i_port_label').value, lane,
            connectionType: insp.querySelector('#i_port_service').value,
          };
          render(true);
          if (event.target.tagName === 'SELECT') {
            fillInsp();
            insp.querySelector('#i_port_id').value = id;
            insp.querySelector('#i_port_id').onchange();
          }
        };
        for (const id of ['i_port_label', 'i_port_compatible', 'i_port_service']) {
          insp.querySelector('#' + id).addEventListener('change', savePort);
        }
      }
      const sid = st.sel;
      const upd = () => {
        if (st.sel !== sid) return;
        const oo = st.spec.overrides[sid] || (st.spec.overrides[sid] = {});
        oo.label = insp.querySelector('#i_lab').value;
        if (!st.spec.freeform) { oo.dx = +insp.querySelector('#i_dx').value; oo.dy = +insp.querySelector('#i_dy').value; }
        render(true);
      };
      insp.querySelector('#i_lab').onchange = upd;
      const lineWidth = insp.querySelector('#i_line_width');
      if (lineWidth) lineWidth.onchange = () => {
        if (!lineWidth.reportValidity() || !Number.isFinite(lineWidth.valueAsNumber)) return;
        item.lineWidth = lineWidth.valueAsNumber; render(true); fillInsp();
      };
      const saveOptions = (event) => {
        const errorBox = insp.querySelector('#i_equipment_error');
        errorBox.textContent = '';
        const invalid = Array.from(insp.querySelectorAll('input[type="number"]')).find((input) => !input.disabled && !input.checkValidity());
        if (invalid) { errorBox.textContent = 'Element changes not saved: correct the highlighted number.'; invalid.reportValidity(); return; }
        const candidate = JSON.parse(JSON.stringify(item));
        if (['riser_base', 'riser_skid'].includes(item.type) && !item.riserDetail) {
          candidate.servicePorts = insp.querySelector('#i_service_ports').checked;
          candidate.umbilicalPorts = insp.querySelector('#i_umbilical_ports').checked;
          candidate.bundleServiceInlet = insp.querySelector('#i_bundle_service').checked;
          if (insp.querySelector('#i_independent_hubs').checked) {
            candidate.riserPorts = Object.fromEntries(['P', 'S', 'U'].map((lane) => [lane,
              Object.fromEntries(['inlets', 'outlets'].map((side) => [side, insp.querySelector(`#i_count_${lane}_${side}`).valueAsNumber]))]));
            delete candidate.portConfig;
          } else delete candidate.riserPorts;
          if (insp.querySelector('#i_custom_piping').checked) {
            candidate.internalRoutes = Array.from(insp.querySelectorAll('.internal-route-row')).map((row) => ({
              id: row.querySelector('.route-id').value.trim(), from: row.querySelector('.route-from').value.trim(),
              to: row.querySelector('.route-to').value.trim(), connectionType: row.querySelector('.route-service').value,
            }));
          } else delete candidate.internalRoutes;
        }
        if (item.type === 'plet') candidate.pletPorts = insp.querySelector('#i_plet_ports').value;
        if (HOSTS[item.type]) {
          if (['jacket', 'platform'].includes(item.type)) {
            candidate.showJTubes = insp.querySelector('#i_show_jtubes').checked;
            candidate.jTubeSide = insp.querySelector('#i_jtube_side').value;
          }
          const count = insp.querySelector('#i_jtube_count').valueAsNumber;
          candidate.slots = Array.from({ length: count }, (_, index) => slotsOf(item)[index] || `J${index + 1}`);
          const removed = (st.spec.connections || []).some((connection) => ['from', 'to'].some((end) =>
            connection[end] === sid && /^J-\d+$/.test(connection[end + 'Port'] || '') && +connection[end + 'Port'].slice(2) >= count));
          if (removed || (item.risers || []).some((r) => num(r.slot, 0) >= count)) {
            errorBox.textContent = 'A removed J-tube is connected. Reconnect or delete its riser before reducing the count.'; return;
          }
        }
        if (item.type === 'template') {
          candidate.hipps = insp.querySelector('#i_hipps').checked;
          candidate.wells = insp.querySelector('#i_wells').valueAsNumber;
          candidate.treeType = insp.querySelector('#i_tree').value;
          if (!candidate.treeType) delete candidate.treeType;
        }
        if (equipment && !item.riserDetail) {
          const inlets = insp.querySelector('#i_inlets').valueAsNumber;
          const outlets = insp.querySelector('#i_outlets').valueAsNumber;
          const previous = item.portConfig || { inlets: 0, outlets: 0 };
          const countsChanged = inlets !== previous.inlets || outlets !== previous.outlets;
          if (candidate.riserPorts) {
            if (!Object.values(candidate.riserPorts).every((counts) => Object.values(counts).every(Number.isInteger))) {
              errorBox.textContent = 'Independent inlet/outlet counts must be whole numbers.'; return;
            }
          } else if (insp.querySelector('#i_ports_enabled').checked || (countsChanged && (inlets > 0 || outlets > 0))) {
            candidate.portConfig = {
              mode: insp.querySelector('#i_port_mode').value, lane: insp.querySelector('#i_port_lane').value,
              inlets, outlets,
            };
            if (!Number.isInteger(candidate.portConfig.inlets) || !Number.isInteger(candidate.portConfig.outlets)) {
              errorBox.textContent = 'Inlet and outlet counts must be whole numbers.'; return;
            }
          } else delete candidate.portConfig;
          const nd = candidate.lane && GEN[candidate.type] ? genNode({ ...GEN[candidate.type], lane: candidate.lane }) : NODE[candidate.type];
          const candidatePorts = equipmentPortLayout({ x: 0, L: st.build.L, act: { P: true, S: true, U: true } }, candidate, nd.w(candidate), nd.uses || 'P');
          const allowed = new Set(candidatePorts.map((port) => port.id));
          if (candidate.bundleServiceInlet && (!allowed.has('U-left') || !allowed.has('S-right')
            || candidatePorts.find((port) => port.id === 'U-left').lane !== 'U')) {
            errorBox.textContent = 'Bundled inlet requires U-compatible U-left and S-right chemical/service ports. Enable the service/umbilical pairs or set independent counts.'; return;
          }
          if (candidate.bundleServiceInlet
            && !['', 'umbilical_static', 'umbilical_dynamic'].includes(candidate.portOverrides?.['U-left']?.connectionType || '')) {
            errorBox.textContent = 'Set the U-left port service to Automatic, Static umbilical or Dynamic umbilical before bundling.'; return;
          }
          if (candidate.internalRoutes !== undefined) {
            const routeErrors = internalRoutingErrors(candidate, candidatePorts);
            if (routeErrors.length) { errorBox.textContent = routeErrors.join(' '); return; }
          }
          for (const connection of st.spec.connections || []) {
            for (const end of ['from', 'to']) {
              if (connection[end] === sid && connection[end + 'Port'] && !allowed.has(connection[end + 'Port'])) {
                errorBox.textContent = `Port ${connection[end + 'Port']} is connected. Reconnect or delete its connection before removing this port.`; return;
              }
            }
          }
          if (candidate.internalValves !== undefined) {
            const proposed = JSON.parse(JSON.stringify(st.spec));
            const proposedItem = [proposed, ...(proposed.branches || [])].flatMap((train) => train.chain || []).find((entry) => entry.id === candidate.id);
            Object.assign(proposedItem, candidate);
            for (const key of Object.keys(proposedItem)) if (!(key in candidate)) delete proposedItem[key];
            const prospective = build(proposed).meta[candidate.id];
            const errors = internalValveErrors(candidate, new Set((prospective?.internalPipes || []).map((pipe) => pipe.id)));
            if (errors.length) { errorBox.textContent = errors.join(' '); return; }
          }
        }
        candidate.designLimits = {};
        for (const [key, field] of Object.entries(EQUIPMENT_OPTIONS.designFields)) {
          const input = insp.querySelector(`#i_limit_${key}`);
          if (input.value !== '') {
            const value = input.valueAsNumber;
            if (!Number.isFinite(value) || value < field.minimum || (field.exclusive && value === field.minimum)) {
              errorBox.textContent = `${field.label} must be ${field.exclusive ? 'greater than' : 'at least'} ${field.minimum}.`; return;
            }
            candidate.designLimits[key] = value;
          }
        }
        Object.keys(item).forEach((key) => delete item[key]);
        Object.assign(item, candidate);
        render(true);
        if (!event || event.target.type === 'checkbox' || event.target.tagName === 'SELECT') {
          fillInsp();
        } else {
          currentPorts.splice(0, currentPorts.length, ...svg.querySelectorAll(`.el[data-id="${CSS.escape(sid)}"] .connection-port`));
          const portSelect = insp.querySelector('#i_port_id');
          if (portSelect) {
            const previous = portSelect.value;
            portSelect.innerHTML = currentPorts.map((port) =>
              `<option value="${esc(port.dataset.port)}">${esc(port.dataset.port)} - ${esc(port.dataset.label)}</option>`).join('');
            if (currentPorts.some((port) => port.dataset.port === previous)) portSelect.value = previous;
            if (currentPorts.length) portSelect.onchange();
          }
          const enabled = insp.querySelector('#i_ports_enabled');
          if (enabled) enabled.checked = !!item.portConfig;
          const pipes = internalValveOptions(svg.querySelector(`.el[data-id="${CSS.escape(sid)}"]`)).pipes;
          for (const select of insp.querySelectorAll('.valve-pipe')) {
            const previous = select.value;
            select.innerHTML = pipes.map((pipe) =>
              `<option value="${esc(pipe.id)}">${esc(pipe.id)} (${esc(pipe.lane)})</option>`).join('');
            if (!pipes.some((pipe) => pipe.id === previous)) select.add(new Option(`Missing: ${previous}`, previous));
            select.value = previous;
          }
          const routePorts = insp.querySelector('#i_route_ports');
          if (routePorts) routePorts.innerHTML = currentPorts.map((port) =>
            `<option value="${esc(port.dataset.port)}"></option>`).join('');
        }
      };
      for (const input of insp.querySelectorAll(
        '#i_independent_hubs, #i_independent_counts input, #i_plet_ports, #i_service_ports, #i_umbilical_ports, '
        + '#i_bundle_service, #i_jtube_count, #i_show_jtubes, #i_jtube_side, #i_hipps, #i_wells, #i_tree, '
        + '#i_ports_enabled, #i_port_mode, #i_port_lane, #i_inlets, #i_outlets, [id^="i_limit_"], #i_custom_piping')) {
        input.addEventListener('change', saveOptions);
      }
      insp.querySelector('#i_route_rows')?.addEventListener('change', saveOptions);
      const resize = (percent) => {
        const input = insp.querySelector('#i_scale');
        input.value = percent;
        if (!input.reportValidity()) return;
        const oo = st.spec.overrides[sid] || (st.spec.overrides[sid] = {});
        oo.scale = input.valueAsNumber / 100;
        render(true);
        fillInsp();
      };
      insp.querySelector('#i_scale').onchange = (e) => resize(e.target.value);
      insp.querySelector('#i_smaller').onclick = () => resize(Math.max(1, Math.round(componentScale(o) * 10000) / 100 - 10));
      insp.querySelector('#i_larger').onclick = () => resize(Math.round(componentScale(o) * 10000) / 100 + 10);
      insp.querySelector('#i_size_reset').onclick = () => resize(100);
      if (!st.spec.freeform) { insp.querySelector('#i_dx').onchange = upd; insp.querySelector('#i_dy').onchange = upd; }
      insp.querySelector('#i_copy').onclick = copySelected;
      insp.querySelector('#i_delete').onclick = removeSelected;
      insp.querySelector('#i_hide').onclick = () => { (st.spec.overrides[sid] || (st.spec.overrides[sid] = {})).hidden = true; st.sel = null; selectedIds.clear(); render(true); fillInsp(); };
      insp.querySelector('#i_reset').onclick = () => { delete st.spec.overrides[sid]; render(true); fillInsp(); };
    }

    /* toolbar */
    const $ = (id) => el.querySelector(id);
    new ResizeObserver(() => {
      el.style.setProperty('--toolbar-height', `${$('#bar').getBoundingClientRect().height}px`);
    }).observe($('#bar'));
    $('#b_fit').onclick = () => { if (wants3D && viewer3D) viewer3D.fit(); else { render(true); vb = st.fit.slice(); applyVb(); } };
    $('#b_layout').onclick = () => {
      const previous = JSON.parse(JSON.stringify(st.spec));
      const translations = new Map();
      const routes = (st.spec.connections || []).map((connection) => {
        const from = svg.querySelector(`.el[data-id="${CSS.escape(connection.from)}"]`);
        const to = svg.querySelector(`.el[data-id="${CSS.escape(connection.to)}"]`);
        return { connection, ends: from && to && connectionEnds(connection, from, to) };
      });
      let units;
      if (st.spec.freeform) {
        const trains = [st.spec, ...(st.spec.branches || [])];
        const positionedAnnotations = (st.spec.zones || []).some((zone) => zone.placement === 'free');
        const implicitPaths = trains.some((train) => train.from || train.to || (train.host?.risers || []).length);
        if (routes.some(({ ends }) => !ends)) {
          render(false); fillInsp();
          $('#connect-status').textContent = 'Automatic spacing skipped: reveal or reconnect hidden/missing connection endpoints first. Fitted the view without moving equipment.';
          return;
        }
        if (positionedAnnotations || implicitPaths) {
          render(false); fillInsp();
          $('#connect-status').textContent = 'Drawing fitted without moving equipment: freely positioned zones or preset paths keep this composition intact. Use dragging to adjust it; Best layout does not redraw engineered routes.';
          return;
        }
        const members = captureElements(Array.from(svg.querySelectorAll('#content .el')).map((g) => g.dataset.id));
        const parents = new Map(members.map((member) => [member.id, member.id]));
        const find = (id) => {
          while (parents.get(id) !== id) id = parents.get(id);
          return id;
        };
        const join = (a, b) => {
          if (parents.has(a) && parents.has(b)) parents.set(find(a), find(b));
        };
        for (const connection of st.spec.connections || []) join(connection.from, connection.to);
        for (const zone of st.spec.zones || []) {
          if (!(zone.distanceM > 0)) join(zone.from, zone.to);
          if (zone.fromHost && parents.has(zone.from)) {
            const train = svg.querySelector(`.el[data-id="${CSS.escape(zone.from)}"]`).closest('.train');
            const host = Array.from(train.querySelectorAll('.el')).find((element) => HOSTS[element.dataset.type]);
            if (host) join(zone.from, host.dataset.id);
          }
        }
        const groups = new Map();
        const includeBox = (unit, box) => {
          const right = Math.max(unit.box.x + unit.box.width, box.x + box.width);
          const bottom = Math.max(unit.box.y + unit.box.height, box.y + box.height);
          unit.box.x = Math.min(unit.box.x, box.x); unit.box.y = Math.min(unit.box.y, box.y);
          unit.box.width = right - unit.box.x; unit.box.height = bottom - unit.box.y;
        };
        for (const member of members) {
          const key = find(member.id);
          if (!groups.has(key)) groups.set(key, { members: [], box: { ...member.box } });
          const unit = groups.get(key);
          unit.members.push(member); includeBox(unit, member.box);
        }
        const includeDrawing = (unit, element) => {
          if (!unit || !element) return;
          const box = element.getBBox(), a = canvasPoint(element, box.x, box.y),
            b = canvasPoint(element, box.x + box.width, box.y + box.height);
          includeBox(unit, { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
            width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) });
        };
        (st.spec.connections || []).forEach((connection, index) => {
          if (parents.has(connection.from)) includeDrawing(groups.get(find(connection.from)),
            svg.querySelector(`.connection[data-connection="${index}"]`));
        });
        (st.spec.zones || []).forEach((zone, index) => {
          if (parents.has(zone.from)) includeDrawing(groups.get(find(zone.from)),
            svg.querySelector(`.design-zone[data-zone="${index}"]`));
        });
        units = Array.from(groups.values());
        if (units.length < 2) {
          render(false); fillInsp();
          $('#connect-status').textContent = 'Connected layout kept intact; fitted the view without moving equipment or reshaping piping.';
          return;
        }
      } else {
        // Keep preset inline piping and legacy risers intact by spacing complete trains.
        units = Array.from(svg.querySelectorAll('#content .train')).map((g) => {
          const b = g.getBBox(), a = canvasPoint(g, b.x, b.y), z = canvasPoint(g, b.x + b.width, b.y + b.height);
          return { train: g.dataset.train, box: { x: Math.min(a.x, z.x), y: Math.min(a.y, z.y), width: Math.abs(z.x - a.x), height: Math.abs(z.y - a.y) } };
        });
      }
      const rows = [];
      units.sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x).forEach((unit) => {
        let row = rows.find((r) => Math.abs(r.y - unit.box.y) < 120);
        if (!row) { row = { y: unit.box.y, units: [] }; rows.push(row); }
        row.units.push(unit);
      });
      let y = 80;
      for (const row of rows) {
        let x = 80, height = 0;
        for (const unit of row.units.sort((a, b) => a.box.x - b.box.x)) {
          let dx = x - unit.box.x, dy = y - unit.box.y;
          if (unit.train) {
            const g = svg.querySelector(`.train[data-train="${CSS.escape(unit.train)}"]`), b = g.getBBox();
            const a = canvasPoint(g, b.x, b.y), z = canvasPoint(g, b.x + b.width, b.y + b.height);
            dx = x - Math.min(a.x, z.x); dy = y - Math.min(a.y, z.y);
            const old = (st.spec.trainOffsets || {})[unit.train] || {};
            (st.spec.trainOffsets || (st.spec.trainOffsets = {}))[unit.train] = { dx: num(old.dx, 0) + dx, dy: num(old.dy, 0) + dy };
            render(true);
          } else {
            // Avoid accumulating SVG coordinate round-off on repeated layout.
            if (Math.abs(dx) < .001) dx = 0;
            if (Math.abs(dy) < .001) dy = 0;
            if (dx || dy) moveElements(unit.members, dx, dy, true);
            for (const member of unit.members) translations.set(member.id, { x: dx, y: dy });
          }
          x += unit.box.width + 90; height = Math.max(height, unit.box.height);
        }
        y += height + 100;
      }
      render(true);
      for (const { connection, ends } of routes) {
        if (!ends || !connection.waypoints) continue;
        if (st.spec.freeform) {
          const delta = translations.get(connection.from);
          if (delta && (delta.x || delta.y)) connection.waypoints = connection.waypoints.map((p) =>
            ({ x: p.x + delta.x, y: p.y + delta.y }));
          continue;
        }
        const from = svg.querySelector(`.el[data-id="${CSS.escape(connection.from)}"]`);
        const to = svg.querySelector(`.el[data-id="${CSS.escape(connection.to)}"]`);
        const next = connectionEnds(connection, from, to);
        const a = { x: next.from.x - ends.from.x, y: next.from.y - ends.from.y };
        const b = { x: next.to.x - ends.to.x, y: next.to.y - ends.to.y };
        connection.waypoints = connection.waypoints.map((p, index, points) => {
          const fraction = (index + 1) / (points.length + 1);
          return { x: p.x + a.x * (1 - fraction) + b.x * fraction, y: p.y + a.y * (1 - fraction) + b.y * fraction };
        });
      }
      render(false); fillInsp();
      const after = JSON.stringify(st.spec);
      if (after !== JSON.stringify(previous)) {
        layoutUndo = previous; layoutAfter = after; $('#b_undo_layout').disabled = false;
      }
      $('#connect-status').textContent = st.spec.freeform ? 'Disconnected blocks spaced apart. Connected equipment, pipe bends and anchored zones retain their geometry. Undo layout restores the previous design.'
        : 'Preset flowpaths spaced as intact blocks to preserve inline piping. Undo layout restores the previous design.';
    };
    $('#b_undo_layout').onclick = () => {
      if (!layoutUndo) return;
      if (JSON.stringify(st.spec) !== layoutAfter) {
        layoutUndo = null; $('#b_undo_layout').disabled = true;
        $('#connect-status').textContent = 'Layout undo is unavailable after another design edit.'; return;
      }
      st.spec = layoutUndo; layoutUndo = null; $('#b_undo_layout').disabled = true;
      render(false); fillInsp();
    };
    $('#b_improve').onclick = () => {
      const previous = JSON.parse(JSON.stringify(st.spec));
      const items = [st.spec, ...(st.spec.branches || [])].flatMap((train) =>
        [...(train.host ? [train.host] : []), ...(train.chain || [])]);
      const usedTags = new Set(items.map((item) => item.tag).filter(Boolean));
      const prefixes = { template: 'TPL', manifold: 'MAN', plet: 'PLET', plem: 'PLEM',
        riser_base: 'RB', riser_skid: 'RS', pig_receiver: 'PR', pig_launcher: 'PL',
        sdu: 'SDU', uta: 'UTA', suta: 'SUTA', spool: 'SP', jumper_rigid: 'JMP', jumper_flex: 'JMP' };
      let added = 0;
      for (const item of items) {
        if (LINK[item.type] || item.tag !== undefined || st.spec.autoTag === false) continue;
        const prefix = TAGS[item.type] || prefixes[item.type] || (HOSTS[item.type] ? 'HOST' : 'EQ');
        let number = 101;
        while (usedTags.has(`${prefix}-${number}`)) number += 1;
        item.tag = `${prefix}-${number}`; usedTags.add(item.tag); added += 1;
      }
      if (st.spec.professionalAppearance && !added) {
        $('#connect-status').textContent = 'Professional appearance is already applied. Individual label controls remain available.'; return;
      }
      appearanceUndo = previous;
      st.spec.professionalAppearance = true;
      render(true); fillInsp();
      appearanceAfter = JSON.stringify(st.spec);
      $('#b_undo_improve').disabled = false;
      $('#connect-status').textContent = `Appearance improved: consistent captions, subtle hatching and ${added} missing equipment tags. Equipment positions, routes, service colours and custom label settings are unchanged.`;
    };
    $('#b_undo_improve').onclick = () => {
      if (!appearanceUndo) return;
      if (JSON.stringify(st.spec) !== appearanceAfter) {
        appearanceUndo = null; $('#b_undo_improve').disabled = true;
        $('#connect-status').textContent = 'Appearance undo is unavailable after another design edit.'; return;
      }
      st.spec = appearanceUndo; appearanceUndo = null;
      $('#b_undo_improve').disabled = true;
      render(true); fillInsp();
      $('#connect-status').textContent = 'Previous appearance restored. Equipment and connection geometry are unchanged.';
    };
    $('#b_in').onclick = () => { if (wants3D && viewer3D) { viewer3D.zoom(.8); return; } const cx = vb[0] + vb[2] / 2, cy = vb[1] + vb[3] / 2; vb = [cx - vb[2] * 0.4, cy - vb[3] * 0.4, vb[2] * 0.8, vb[3] * 0.8]; applyVb(); };
    $('#b_out').onclick = () => { if (wants3D && viewer3D) { viewer3D.zoom(1.25); return; } const cx = vb[0] + vb[2] / 2, cy = vb[1] + vb[3] / 2; vb = [cx - vb[2] * 0.625, cy - vb[3] * 0.625, vb[2] * 1.25, vb[3] * 1.25]; applyVb(); };
    const setGridButton = () => {
      $('#b_grid').classList.toggle('on', grid);
      $('#b_grid').setAttribute('aria-pressed', String(grid));
    };
    setGridButton();
    $('#b_grid').onclick = () => { grid = !grid; st.spec.showGrid = grid; setGridButton(); render(true); };
    if ($('#b_connect')) $('#b_connect').onclick = () => {
      connectMode = !connectMode;
      connectStart = null;
      svg.classList.toggle('connecting', connectMode);
      const preview = svg.querySelector('#connection-preview');
      if (preview) preview.setAttribute('d', '');
      $('#b_connect').classList.toggle('on', connectMode);
      $('#b_connect').setAttribute('aria-pressed', String(connectMode));
      $('#b_connect').textContent = connectMode ? 'Cancel connect' : 'Connect';
      const status = $('#connect-status');
      if (status) status.textContent = connectMode ? 'Drag from a green-highlighted symbol to another.' : '';
      highlight();
    };
    if ($('#b_copy')) $('#b_copy').onclick = copySelected;
    if ($('#b_zone')) $('#b_zone').onclick = addZone;
    if ($('#b_riser_detail')) $('#b_riser_detail').onclick = openRiserDetail;
    if ($('#b_custom_element')) $('#b_custom_element').onclick = () => {
      placeSymbol('custom_element', { x: vb[0] + vb[2] / 2, y: vb[1] + vb[3] / 2 });
      openRiserDetail();
    };
    if ($('#b_delete')) $('#b_delete').onclick = removeSelected;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && connectMode) {
        connectMode = false; connectStart = null;
        svg.classList.remove('connecting');
        const preview = svg.querySelector('#connection-preview');
        if (preview) preview.setAttribute('d', '');
        if ($('#b_connect')) { $('#b_connect').classList.remove('on'); $('#b_connect').textContent = 'Connect'; $('#b_connect').setAttribute('aria-pressed', 'false'); }
        if ($('#connect-status')) $('#connect-status').textContent = '';
        highlight();
      }
      if ((e.key === 'Delete' || e.key === 'Backspace')
        && !e.target.closest('input,textarea,select,[contenteditable="true"]')
        && (st.sel || selectedConnection !== null || selectedZone !== null)) {
        e.preventDefault();
        removeSelected();
      }
    });
    if ($('#b_palette') && palette) $('#b_palette').onclick = () => {
      palette.classList.toggle('open');
      $('#b_palette').classList.toggle('on', palette.classList.contains('open'));
      $('#b_palette').setAttribute('aria-expanded', String(palette.classList.contains('open')));
    };
    if ($('#palette-close') && palette) $('#palette-close').onclick = () => {
      palette.classList.remove('open');
      if ($('#b_palette')) { $('#b_palette').classList.remove('on'); $('#b_palette').setAttribute('aria-expanded', 'false'); }
    };
    if ($('#b_fullscreen')) {
      const fullButton = $('#b_fullscreen');
      const fullError = $('#fullscreen-error');
      const syncFullscreen = () => {
        const active = document.fullscreenElement === el;
        fullButton.textContent = active ? 'Exit full screen' : 'Full screen';
        fullButton.classList.toggle('on', active);
        fullError.style.display = 'none';
        requestAnimationFrame(() => { if (vb) applyVb(); });
      };
      fullButton.onclick = async () => {
        fullError.style.display = 'none';
        try {
          if (document.fullscreenElement === el) await document.exitFullscreen();
          else await el.requestFullscreen();
        } catch (error) {
          fullError.textContent = `Full screen unavailable: ${error.message}`;
          fullError.style.display = 'inline';
        }
      };
      document.addEventListener('fullscreenchange', syncFullscreen);
      document.addEventListener('fullscreenerror', () => {
        fullError.textContent = 'Full screen is blocked by the browser or embedding page.';
        fullError.style.display = 'inline';
      });
    }
    const setAnim = (on) => {
      svg.classList.toggle('anim', !!on);
      const b = $('#b_flow');
      if (b) { b.classList.toggle('on', !!on); b.setAttribute('aria-pressed', String(!!on)); }
    };
    const setSpd = (v) => { svg.style.setProperty('--spd', String(v)); };
    st.spec.animate = st.spec.animate !== undefined ? st.spec.animate : false;
    setSpd(num(st.spec.animSpeed, 1));
    if ($('#b_flow')) $('#b_flow').onclick = () => { st.spec.animate = !svg.classList.contains('anim'); setAnim(st.spec.animate); notifyChange(); };
    if ($('#b_spd')) { $('#b_spd').value = String(num(st.spec.animSpeed, 1)); $('#b_spd').oninput = (e) => { st.spec.animSpeed = parseFloat(e.target.value); setSpd(st.spec.animSpeed); notifyChange(); }; }
    st.setAnim = setAnim; setAnim(st.spec.animate);
    $('#b_reset').onclick = () => { st.spec.overrides = {}; render(true); fillInsp(); };
    const clean = () => {
      const c = svg.cloneNode(true);
      c.querySelectorAll('.sel').forEach((g) => g.classList.remove('sel'));
      c.querySelectorAll('.hit').forEach((h) => h.remove());
      c.querySelectorAll('.connection-port,.connection-hit,.legacy-riser-hit,.route-handle,#connection-preview,#zone-controls,.zone-hit-targets').forEach((h) => h.remove());
      const f = st.fit;
      c.setAttribute('viewBox', f.join(' ')); c.setAttribute('width', f[2]); c.setAttribute('height', f[3]);
      c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      const bg = c.querySelector('#bg'); if (bg) { bg.setAttribute('x', f[0]); bg.setAttribute('y', f[1]); bg.setAttribute('width', f[2]); bg.setAttribute('height', f[3]); }
      return new XMLSerializer().serializeToString(c);
    };
    const save = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); };
    const base = () => (st.spec.title || 'subsea_layout').replace(/[^a-z0-9]+/gi, '_');
    $('#b_svg').onclick = () => {
      try {
        if (wants3D && !viewer3D) throw new Error('Wait for the 3D view to finish loading.');
        save(new Blob([wants3D ? viewer3D.svgSnapshot(st.spec.title) : clean()], { type: 'image/svg+xml' }), base() + (wants3D ? '_3D' : '') + '.svg');
      } catch (error) { $('#connect-status').textContent = 'SVG export failed: ' + error.message; }
    };
    $('#b_html').onclick = () => {
      try {
        if (!viewer3D) throw new Error('Wait for the 3D view to finish loading.');
        const page = standaloneTemplate.cloneNode(true);
        const json = (value) => JSON.stringify(value).replaceAll('<', '\\u003c');
        page.querySelector('#design-spec').textContent = json(st.spec);
        page.querySelector('#initial-view').textContent = json({ mode: '3d', ...viewer3D.viewState() });
        save(new Blob(['<!DOCTYPE html>\n' + page.outerHTML], { type: 'text/html' }), base() + '_3D.html');
      } catch (error) { $('#connect-status').textContent = '3D HTML export failed: ' + error.message; }
    };
    $('#b_json').onclick = () => save(new Blob([JSON.stringify(st.spec, null, 2)], { type: 'application/json' }), base() + '.json');
    $('#b_png').onclick = async () => {
      if (wants3D && viewer3D) {
        try { save(await viewer3D.snapshot(), base() + '_3D.png'); }
        catch (error) { $('#connect-status').textContent = '3D export failed: ' + error.message; }
        return;
      }
      const f = st.fit, k = 2.5, img = new Image();
      img.onload = () => { const cv = document.createElement('canvas'); cv.width = f[2] * k; cv.height = f[3] * k; const cx = cv.getContext('2d'); cx.fillStyle = T.paper; cx.fillRect(0, 0, cv.width, cv.height); cx.drawImage(img, 0, 0, cv.width, cv.height); cv.toBlob((b) => save(b, base() + '.png')); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(clean());
    };
    $('#b_print').onclick = () => { try { window.print(); } catch (e) { /* sandboxed */ } };

    render(false);
    st.getScene3D = () => {
      const sample = (path) => {
        const length = path.getTotalLength(), count = Math.max(2, Math.min(64, Math.ceil(length / 8)));
        return Array.from({ length: count + 1 }, (_, i) => {
          const p = path.getPointAtLength(length * i / count), q = canvasPoint(path, p.x, p.y);
          return { x: q.x, y: q.y };
        });
      };
      const direction = (path) => {
        const flow = path.nextElementSibling;
        if (flow?.classList.contains('flow')) return flow.classList.contains('rev') ? 'reverse' : 'forward';
        return 'none';
      };
      const nodes = Array.from(svg.querySelectorAll('#content .el')).map((element) => {
        const id = element.dataset.id, source = findItem(id)?.item;
        if (!source) return null;
        const item = JSON.parse(JSON.stringify(source)), override = st.spec.overrides[id] || {};
        if (override.label !== undefined) item.label = override.label;
        const box = element.querySelector('.hit').getBBox(), a = canvasPoint(element, box.x, box.y),
          b = canvasPoint(element, box.x + box.width, box.y + box.height);
        const pipes = internalPipes(element), pipeData = [...pipes].map(([id, path]) => ({
          id, lane: path.dataset.pipeLane, points: sample(path),
          color: !path.getAttribute('stroke') || path.getAttribute('stroke') === 'none' ? laneColor(path.dataset.pipeLane) : path.getAttribute('stroke'),
          width: num(path.getAttribute('stroke-width'), 1.8), flow: direction(path),
        }));
        element.querySelectorAll('path,line').forEach((path) => {
          if (!path.hasAttribute('data-internal-pipe') && path.hasAttribute('data-flow-lane') && path.getTotalLength()) {
            pipeData.push({ id: 'line-' + pipeData.length, lane: path.dataset.flowLane, points: sample(path), color: path.getAttribute('stroke') || T.ink,
              width: num(path.getAttribute('stroke-width'), 1.8), flow: direction(path) });
          }
        });
        const valves = (item.internalValves !== undefined ? item.internalValves : internalValveOptions(element).defaults)
          .filter((v) => pipes.has(v.pipe)).map((v) => {
            const path = pipes.get(v.pipe), length = path.getTotalLength(), along = length * num(v.position, 50) / 100;
            const at = path.getPointAtLength(along), p = canvasPoint(path, at.x, at.y);
            const before = path.getPointAtLength(Math.max(0, along - .1)), after = path.getPointAtLength(Math.min(length, along + .1));
            const first = canvasPoint(path, before.x, before.y), last = canvasPoint(path, after.x, after.y);
            return { ...v, kind: v.kind || 'gate', point: { x: p.x, y: p.y }, angle: Math.atan2(last.y - first.y, last.x - first.x) };
          });
        let detailOrigin;
        const detail = element.querySelector('.riser-detail-body');
        if (detail) {
          const p = canvasPoint(detail, 0, 0), x = canvasPoint(detail, 1, 0), y = canvasPoint(detail, 0, 1);
          detailOrigin = { x: p.x, y: p.y, scaleX: x.x - p.x, scaleY: y.y - p.y };
        }
        const ports = portsFor(element).map((port) => {
          if (!port.tubeMouth) return port;
          const bore = element.querySelector(`.j-tube-guide[data-tube="${/^J-(\d+)$/.exec(port.id)?.[1]}"] .j-tube-bore`);
          if (!bore) return port;
          const p = bore.getPointAtLength(0), top = canvasPoint(bore, p.x, p.y);
          return { ...port, topsidePoint: { x: top.x, y: top.y } };
        });
        const topside = ports.find((p) => p.topsidePoint)?.topsidePoint || ports.find((p) => p.hostSlot && !p.tubeMouth);
        const train = element.closest('.train');
        const nominalPorts = st.spec.freeform ? [] : Array.from(element.querySelectorAll('.connection-port')).map((port) => {
          const point = canvasPoint(train, +port.dataset.x, +port.dataset.y);
          return { id: port.dataset.port, lane: port.dataset.lane, x: point.x, y: point.y };
        });
        return { id, type: item.type, name: byId[item.type]?.name || item.type, item,
          mirrored: !!element.closest('.train.mir'), schematic: !st.spec.freeform,
          train: train.dataset.train, chainIndex: findItem(id).index, nominalPorts,
          customSymbol: (st.spec.customSymbols || []).find((symbol) => symbol.id === item.type),
          box: { cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) },
          ports, pipes: pipeData, valves, detailOrigin, topside };
      }).filter(Boolean);
      const routes = [];
      const psvPoint = (key) => {
        const marker = svg.querySelector(`.riser-psv[data-psv-key="${CSS.escape(key)}"]`);
        if (!marker) return null;
        const p = canvasPoint(marker, 0, 0);
        return { x: p.x, y: p.y };
      };
      (st.spec.connections || []).forEach((connection, index) => {
        const group = svg.querySelector(`.connection[data-connection="${index}"]`), path = group?.querySelector(`#connection-line-${index}`);
        if (!path) return;
        const ends = connectionEnds(connection, svg.querySelector(`.el[data-id="${CSS.escape(connection.from)}"]`),
          svg.querySelector(`.el[data-id="${CSS.escape(connection.to)}"]`));
        const flow = group.querySelector('.connection-flow');
        routes.push({ index, from: connection.from, to: connection.to, kind: connection.kind, psv: !!connection.psv,
          fromPort: ends.from.id, toPort: ends.to.id, style: connection.style || 'rigid',
          waypoints: connection.waypoints,
          psvPoint: psvPoint(`connection-${index}`), psvPosition: num(connection.psvPosition, 50),
          points: sample(path), color: path.getAttribute('stroke'), width: num(path.getAttribute('stroke-width'), 2),
          flow: flow ? flow.classList.contains('rev') ? 'reverse' : 'forward' : 'none' });
      });
      const atPort = (p, lane, excluded) => nodes.filter((n) => n.id !== excluded).flatMap((n) =>
        (n.schematic ? n.nominalPorts : n.ports).filter((port) => !lane || port.lane === lane).map((port) => ({
          node: n.id, port: port.id, distance: Math.hypot(port.x - p.x, port.y - p.y),
        }))).filter((match) => match.distance < .1).sort((a, b) => a.distance - b.distance)[0];
      svg.querySelectorAll('[data-riser-host]').forEach((group) => {
        const path = group.querySelector('path:not(.legacy-riser-hit):not(.flow)');
        if (!path || !path.getTotalLength()) return;
        const points = sample(path), from = group.dataset.riserHost;
        const preset = findItem(from)?.item.risers?.[+group.dataset.riserIndex];
        const to = atPort(points.at(-1), preset?.lane || 'P', from);
        routes.push({ from, to: to?.node, toPort: to?.port, kind: 'riser', points, color: path.getAttribute('stroke'),
          fromPort: `J-${num(preset?.slot, 0)}`, psv: !!preset?.psv, psvPoint: psvPoint(`${from}:${group.dataset.riserIndex}`),
          style: preset?.style || 'rigid',
          width: num(path.getAttribute('stroke-width'), 2), flow: direction(path) });
      });
      svg.querySelectorAll('#content path,#content line').forEach((path) => {
        if (path.closest('.el,.connection,[data-riser-host]') || !path.hasAttribute('data-flow-lane') || !path.getTotalLength()) return;
        const points = sample(path);
        const from = atPort(points[0], path.dataset.flowLane), to = atPort(points.at(-1), path.dataset.flowLane);
        routes.push({ from: from?.node, fromPort: from?.port, to: to?.node, toPort: to?.port, implicit: true, points, color: path.getAttribute('stroke'),
          width: num(path.getAttribute('stroke-width'), 2), flow: direction(path) });
      });
      if (!st.spec.freeform) {
        const pipeAt = (node, port) => node.pipes.find((pipe) => pipe.lane === port.lane
          && [pipe.points[0], pipe.points.at(-1)].some((p) => Math.hypot(p.x - port.x, p.y - port.y) < .1));
        for (const train of new Set(nodes.map((n) => n.train))) {
          const chain = nodes.filter((n) => n.train === train && n.chainIndex >= 0).sort((a, b) => a.chainIndex - b.chainIndex);
          for (let i = 1; i < chain.length; i++) for (const lane of ['P', 'S', 'U']) {
            const a = chain[i - 1], b = chain[i], fromPort = `${lane}-right`, toPort = `${lane}-left`;
            const nominalA = a.nominalPorts.find((p) => p.id === fromPort), nominalB = b.nominalPorts.find((p) => p.id === toPort);
            if (!nominalA || !nominalB) continue;
            const margin = [a, b].reduce((max, n) => Math.max(max,
              ['riser_base', 'riser_skid'].includes(n.type) ? 10 : n.type === 'plet' ? 4 : 0), 0);
            if (Math.abs(nominalA.y - nominalB.y) > .1 || Math.abs(nominalA.x - nominalB.x) > margin + .1) continue;
            const from = a.ports.find((p) => p.id === fromPort), to = b.ports.find((p) => p.id === toPort);
            const appearance = from && pipeAt(a, from);
            if (!appearance || !to || !pipeAt(b, to)) continue;
            if (routes.some((r) => r.from === a.id && r.fromPort === fromPort && r.to === b.id && r.toPort === toPort
              || r.from === b.id && r.fromPort === toPort && r.to === a.id && r.toPort === fromPort)) continue;
            routes.push({ from: a.id, fromPort, to: b.id, toPort, lane, autoBridge: true, implicit: true,
              points: [{ x: from.x, y: from.y }, { x: to.x, y: to.y }],
              color: appearance.color, width: appearance.width, flow: appearance.flow });
          }
        }
      }
      return { nodes, routes, zones: [...zoneLayouts].map(([index, geometry]) => ({
        ...geometry, label: st.spec.zones[index].label || 'Zone',
      })), selected: st.sel, animate: !!st.spec.animate, speed: num(st.spec.animSpeed, 1) };
    };
    st.move3DEquipment = (id, dx, dy) => {
      if (!Number.isFinite(dx) || !Number.isFinite(dy) || !findItem(id)) throw new Error('Invalid 3D equipment movement.');
      moveElements(captureElements([id]), dx, dy, true); render(true); select(id);
    };
    const viewButtons = () => {
      for (const [id, pressed] of [['b_2d', !wants3D], ['b_3d', wants3D]]) {
        $('#' + id).classList.toggle('on', pressed); $('#' + id).setAttribute('aria-pressed', String(pressed));
      }
      updateSelectionControls();
    };
    $('#b_2d').onclick = () => {
      wants3D = false; viewer3D?.hide(); $('#scene3d').hidden = true; svg.style.visibility = '';
      viewButtons(); $('#connect-status').textContent = '2D design restored. 3D position edits are retained.';
    };
    $('#b_3d').onclick = async () => {
      wants3D = true; $('#scene3d').hidden = false; svg.style.visibility = 'hidden'; viewButtons();
      $('#scene3d-error').textContent = ''; $('#scene3d-info').textContent = 'Loading local 3D renderer...';
      palette.classList.remove('open'); $('#b_palette').classList.remove('on'); $('#b_palette').setAttribute('aria-expanded', 'false');
      pendingType = null; svg.classList.remove('placement', 'drop-target'); updatePalette();
      if (connectMode) $('#b_connect').onclick();
      if (detailEditor) detailEditor.close();
      try {
        if (!viewer3D) {
          if (!loading3D) loading3D = root.Subsea3D.create({
            container: $('#scene3d'), getData: st.getScene3D, select, move: st.move3DEquipment,
            initialView: initialView.mode === '3d' ? initialView : null,
            selectConnection: (index) => { if (!Number.isInteger(index)) return; st.sel = null; selectedIds.clear(); selectedZone = null; selectedConnection = index; renderConnections(); highlight(); fillInsp(); },
          });
          viewer3D = await loading3D; st.scene3D = viewer3D;
        }
        if (wants3D) viewer3D.show();
      } catch (error) {
        loading3D = null; wants3D = false; viewer3D?.hide(); svg.style.visibility = ''; viewButtons();
        $('#scene3d-error').textContent = '3D unavailable: ' + error.message + ' Select 2D design to continue.';
        $('#connect-status').textContent = '3D failed to initialize; the 2D design has not been changed.';
      }
    };
    root.addEventListener('subsea-change', () => {
      if (wants3D && viewer3D) {
        try { viewer3D.sync(st.getScene3D()); }
        catch (error) { $('#scene3d-error').textContent = '3D update failed: ' + error.message; }
      }
    });
    st.getSelectedConnection = () => selectedConnection;
    st.getSelectedIds = () => [...selectedIds];
    st.getInternalValveOptions = () => internalValveOptions(st.sel && svg.querySelector(`.el[data-id="${CSS.escape(st.sel)}"]`));
    st.getSelectedPorts = () => {
      const element = st.sel && svg.querySelector(`.el[data-id="${CSS.escape(st.sel)}"]`);
      return element ? Array.from(element.querySelectorAll('.connection-port')).filter((p) => !p.classList.contains('legacy-host-port')).map((p) => ({
        id: p.dataset.port, label: p.dataset.label || p.dataset.port, lane: p.dataset.lane,
        connectionType: findItem(st.sel)?.item.portOverrides?.[p.dataset.port]?.connectionType || '',
      })) : [];
    };
    st.replaceSpec = (next) => {
      st.spec = JSON.parse(JSON.stringify(next));
      st.spec.overrides = st.spec.overrides || {};
      assignHostIds();
      if (st.sel && (!findItem(st.sel) || st.spec.overrides[st.sel]?.hidden)) st.sel = null;
      for (const id of selectedIds) if (!findItem(id) || st.spec.overrides[id]?.hidden) selectedIds.delete(id);
      if (selectedConnection !== null && !(st.spec.connections || [])[selectedConnection]) selectedConnection = null;
      if (selectedZone !== null && !(st.spec.zones || [])[selectedZone]) selectedZone = null;
      grid = !!st.spec.showGrid;
      setGridButton();
      render(true);
      fillInsp();
      if (detailEditor) detailEditor.sync(findItem(detailEditorId)?.item);
      setAnim(st.spec.animate);
      setSpd(num(st.spec.animSpeed, 1));
    };
    root.__subsea = st;
    if (initialView.mode === '3d') $('#b_3d').click();
    return st;
  }

  /* ============================================================ CATALOG ===== */
  function mountCatalog(el, catalog) {
    const CW = 300, CH = 200, G = 12;
    const COLS = Math.max(1, Math.floor(((el.clientWidth || 1200) - 8) / (CW + G)));
    T = Object.assign({}, BASE);
    let s = '';
    catalog.forEach((e, i) => {
      const cx = (i % COLS) * (CW + G), cy = Math.floor(i / COLS) * (CH + G);
      let inner = '';
      const L = { P: 0, S: 34, U: 50 };
      if (e.kind === 'node' && NODE[e.id]) {
        const nd = NODE[e.id], n = { id: e.id }, w = nd.w(n), uses = nd.uses || 'P';
        const act = { P: true, S: uses.includes('S') || e.id === 'sdu', U: uses.includes('U') || e.id === 'sdu' };
        const c = { x: 0, L, act };
        inner = ['P', 'S', 'U'].map((l) => (act[l] ? seg(c, l, -24, w + 24) : '')).join('') + nd.draw(c, n);
      } else if (e.kind === 'link') {
        const def = LINK[e.id], n = { pKm: 8, w: 220 };
        inner = drawLink({ x: 0, L, act: { P: true, S: false, U: false } }, n, def);
      } else if (HOSTS[e.id]) {
        const h = HOSTS[e.id];
        inner = h.draw({ x: 0, top: 0, spec: { slots: ['A', 'B'] }, L: { P: h.h - 40, S: h.h - 6, U: h.h + 10 } }).svg;
      }
      s += `<g transform="translate(${cx} ${cy})"><rect width="${CW}" height="${CH}" rx="8" fill="#fff" stroke="#d7dbe0"/>`
        + `<text x="12" y="20" font-size="11.5" font-weight="600" fill="${T.ink}">${esc(e.name)}</text>`
        + `<text x="${CW - 12}" y="20" font-size="8.5" text-anchor="end" fill="${T.mute}">${esc(e.id)}</text>`
        + `<g class="fit" data-cw="${CW}" data-ch="${CH}">${inner}</g>`
        + `<text font-size="8.5" fill="${T.mute}">${wrap(e.desc, 56).split('\n').slice(0, 2).map((l, k) => `<tspan x="12" y="${CH - 20 + k * 11}">${esc(l)}</tspan>`).join('')}</text></g>`;
    });
    const rows = Math.ceil(catalog.length / COLS), W = COLS * (CW + G), H = rows * (CH + G);
    const svg = el.querySelector('#svg');
    svg.setAttribute('viewBox', `-4 -4 ${W + 8} ${H + 8}`);
    svg.style.flex = 'none'; svg.style.height = ((el.clientWidth || 1200) * (H + 8)) / (W + 8) + 'px'; svg.style.cursor = 'default';
    document.body.style.overflowY = 'auto';
    svg.innerHTML = defsSvg() + `<g font-family="${esc(T.font)}">${s}</g>`;
    svg.querySelectorAll('g.fit').forEach((g) => {
      const bb = g.getBBox(); if (!bb.width) return;
      const aw = CW - 28, ah = CH - 74, k = Math.min(aw / bb.width, ah / bb.height, 1.5);
      g.setAttribute('transform', `translate(${CW / 2 - (bb.x + bb.width / 2) * k} ${32 + ah / 2 + 4 - (bb.y + bb.height / 2) * k}) scale(${k})`);
    });
  }

  root.Subsea = {
    build, mount, mountCatalog,
    setTags: (m) => { Object.keys(TAGS).forEach((k) => delete TAGS[k]); Object.assign(TAGS, m); },
    setConnectionTypes: (types) => { CONNECTION_TYPES = types; },
    setEquipmentOptions: (options) => { EQUIPMENT_OPTIONS = options; if (options.riserDetail) root.SubseaRiserDetail.configure(options.riserDetail); },
    ids: () => ({ node: Object.keys(NODE), link: Object.keys(LINK), host: Object.keys(HOSTS) }),
  };
})(typeof window !== 'undefined' ? window : globalThis);
