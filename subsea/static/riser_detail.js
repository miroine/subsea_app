(function (root) {
  'use strict';
  let definitions = { services: {}, reference: {} };
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const esc = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const serviceValid = (value) => typeof value === 'string' && Object.prototype.hasOwnProperty.call(definitions.services, value);
  const blank = () => copy(definitions.blank);
  function shapeErrors(layout) {
    const shapes = layout.shapes === undefined ? [] : layout.shapes, result = [], ids = new Set();
    if (!Array.isArray(shapes) || shapes.length > 144) return ['Use at most 144 shapes.'];
    for (const s of shapes) {
      if (!s || typeof s !== 'object') { result.push('Shapes must be objects.'); continue; }
      if (typeof s.id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(s.id) || ids.has(s.id)) result.push('Shapes need valid, unique IDs.');
      ids.add(s.id);
      if (!['rect', 'ellipse', 'line', 'text'].includes(s.kind)) { result.push('Unsupported shape kind.'); continue; }
      if (![['x', 'width'], ['y', 'height']].every(([a, d]) => finite(s[a]) && s[a] >= 0 && s[a] <= layout[d])) {
        result.push('Shape positions must be inside the frame.'); continue;
      }
      if (['rect', 'ellipse'].includes(s.kind)
        && ![['x', 'width'], ['y', 'height']].every(([a, d]) => finite(s[d]) && s[d] > 0 && s[a] + s[d] <= layout[d] + 1e-6)) {
        result.push('Shape dimensions must be positive and fit inside the frame.');
      }
      if (s.kind === 'line' && (![['x2', 'width'], ['y2', 'height']].every(([a, d]) => finite(s[a]) && s[a] >= 0 && s[a] <= layout[d])
        || (s.x2 === s.x && s.y2 === s.y))) result.push('Lines need a different endpoint inside the frame.');
      if (s.kind === 'text' && (typeof s.text !== 'string' || s.text.length > 2000 || !finite(s.fontSize) || s.fontSize < 4 || s.fontSize > 72)) {
        result.push('Text must be at most 2000 characters, with size 4-72 drawing units.');
      }
      for (const key of ['stroke', 'fill']) {
        const v = s[key] ?? (key === 'stroke' ? '#111111' : 'none');
        if (typeof v !== 'string' || !(/^#[0-9a-f]{6}$/i.test(v) || key === 'fill' && v === 'none')) result.push('Use six-digit hex colours; fill also allows none.');
      }
      if (!finite(s.strokeWidth ?? 1.5) || (s.strokeWidth ?? 1.5) < .2 || (s.strokeWidth ?? 1.5) > 12) result.push('Stroke width must be 0.2-12 drawing units.');
    }
    return result;
  }
  function shapeMarkup(s, mono = false) {
    const stroke = mono ? '#111111' : s.stroke ?? '#111111';
    const fill = (s.fill ?? 'none') === 'none' ? 'none' : mono ? '#ffffff' : s.fill;
    const style = `fill="${fill}" stroke="${stroke}" stroke-width="${s.strokeWidth ?? 1.5}"`;
    if (s.kind === 'rect') return `<rect x="${s.x}" y="${s.y}" width="${s.width}" height="${s.height}" ${style}/>`;
    if (s.kind === 'ellipse') return `<ellipse cx="${s.x + s.width / 2}" cy="${s.y + s.height / 2}" rx="${s.width / 2}" ry="${s.height / 2}" ${style}/>`;
    if (s.kind === 'line') return `<path d="M${s.x} ${s.y}L${s.x2} ${s.y2}" ${style}/>`;
    return `<text x="${s.x}" y="${s.y}" font-size="${s.fontSize}" fill="${stroke}" font-family="Arial,sans-serif" xml:space="preserve">${esc(s.text)}</text>`;
  }
  const endpoints = (layout) => new Map([
    ...layout.hubs.map((hub) => [hub.id, hub]),
    ...layout.junctions.map((node) => ['@' + node.id, node]),
  ]);
  function errors(layout) {
    if (!layout || typeof layout !== 'object' || Array.isArray(layout)
      || !['width', 'height'].every((key) => finite(layout[key]) && layout[key] >= 120 && layout[key] <= 1000)) {
      return ['Layout width and height must be 120-1000 finite drawing units.'];
    }
    const result = [];
    for (const [key, limit] of [['hubs', 64], ['junctions', 144], ['routes', 144]]) {
      if (!Array.isArray(layout[key]) || layout[key].length > limit) result.push(`Use at most ${limit} ${key}.`);
    }
    if (result.length) return result;
    if (layout.showFrame !== undefined && typeof layout.showFrame !== 'boolean') result.push('Show frame must be true or false.');
    result.push(...shapeErrors(layout));
    const pointValid = (point) => point && typeof point === 'object'
      && finite(point.x) && finite(point.y) && point.x >= 0 && point.x <= layout.width && point.y >= 0 && point.y <= layout.height;
    for (const key of ['hubs', 'junctions', 'routes']) {
      const ids = new Set();
      for (const entry of layout[key]) {
        const pattern = key === 'hubs' ? /^[PSU]-(left|right|in-\d+|out-\d+)$/ : /^[A-Za-z0-9_-]+$/;
        if (!entry || typeof entry !== 'object' || typeof entry.id !== 'string' || !pattern.test(entry.id) || ids.has(entry.id)) {
          result.push(`${key} need valid, unique IDs.`); continue;
        }
        ids.add(entry.id);
        if (entry.label !== undefined && typeof entry.label !== 'string') result.push('Labels must be text.');
        if (key !== 'routes' && !pointValid(entry)) result.push('Hubs and junctions must lie inside the frame.');
        if (key === 'hubs') {
          if (!['left', 'right', 'top', 'bottom'].includes(entry.side) || !serviceValid(entry.service)) {
            result.push('Each hub needs a side and service.');
          } else {
            const [axis, value] = { left: ['x', 0], right: ['x', layout.width], top: ['y', 0], bottom: ['y', layout.height] }[entry.side];
            if (Math.abs(entry[axis] - value) > 1e-6) result.push(`Hub ${entry.id} must lie on its selected frame edge.`);
          }
        }
      }
    }
    if (result.length) return result;
    const ends = endpoints(layout);
    for (const route of layout.routes) {
      if (!ends.has(route.from) || !ends.has(route.to) || route.from === route.to) result.push(`Route ${route.id} needs two different, existing endpoints.`);
      if (!serviceValid(route.service)) result.push(`Route ${route.id} needs a service.`);
      if (route.points !== undefined && (!Array.isArray(route.points) || route.points.length > 32 || !route.points.every(pointValid))) {
        result.push(`Route ${route.id} allows up to 32 bends inside the frame.`);
      } else if (ends.has(route.from) && ends.has(route.to)) {
        const points = [ends.get(route.from), ...(route.points || []), ends.get(route.to)];
        if (points.every((p) => p.x === points[0].x && p.y === points[0].y)) result.push(`Route ${route.id} has zero length.`);
      }
    }
    return result;
  }
  function routePoints(layout, route) {
    const ends = endpoints(layout), from = ends.get(route.from), to = ends.get(route.to);
    return [from, ...(route.points === undefined && from.x !== to.x && from.y !== to.y
      ? [{ x: to.x, y: from.y }] : route.points || []), to];
  }
  const pathData = (points) => points.map((point, i) => `${i ? 'L' : 'M'}${point.x} ${point.y}`).join('');
  function project(layout, route, point) {
    const points = routePoints(layout, route);
    const lengths = points.slice(1).map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
    const total = lengths.reduce((a, b) => a + b, 0);
    let along = 0, best = { distance: Infinity };
    lengths.forEach((length, i) => {
      const a = points[i], b = points[i + 1], dx = b.x - a.x, dy = b.y - a.y;
      const fraction = length ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / (length * length))) : 0;
      const at = { x: a.x + dx * fraction, y: a.y + dy * fraction };
      const distance = Math.hypot(point.x - at.x, point.y - at.y);
      if (distance < best.distance) best = { ...at, distance, index: i, position: total ? (along + length * fraction) / total * 100 : 0 };
      along += length;
    });
    return best;
  }
  function draw(layout, c, width, helpers) {
    const invalid = errors(layout);
    if (invalid.length) throw new Error(invalid.join(' '));
    const scale = width / layout.width;
    let body = helpers.rect(0, 0, layout.width, layout.height, { fill: layout.showFrame === false ? 'none' : '#FFFFCF',
      c: layout.showFrame === false ? 'none' : helpers.ink, w: 1 });
    for (const shape of layout.shapes || []) body += `<g class="detail-shape" data-detail-shape="${esc(shape.id)}">${shapeMarkup(shape, helpers.mono)}</g>`;
    for (const route of layout.routes) {
      const service = definitions.services[route.service];
      body += `<g class="detailed-internal-route" data-detail-route="${esc(route.id)}">`
        + helpers.path(pathData(routePoints(layout, route)), { c: helpers.mono ? '#111111' : service.color,
          w: service.width, dash: helpers.mono ? { production: '', meg: '8 3', chemical: '4 2', spare: '2 3' }[route.service] : '',
          flow: service.lane, pipeId: 'route-' + route.id }) + '</g>';
    }
    for (const node of layout.junctions) body += helpers.circ(node.x, node.y, 2, { fill: helpers.ink, c: helpers.ink, w: .5 });
    return `<g class="riser-detail-body" transform="translate(${c.x} ${c.L.P - 36}) scale(${scale})">${body}</g>`;
  }
  function ports(item, c, width) {
    const layout = item.riserDetail, scale = width / layout.width;
    return layout.hubs.map((hub) => {
      const service = definitions.services[hub.service];
      const vertical = ['top', 'bottom'].includes(hub.side);
      return { id: hub.id, x: c.x + hub.x * scale, y: c.L.P - 36 + hub.y * scale,
        label: hub.label ?? '', lane: service.lane,
        connectionType: service.connectionType,
        direction: ['left', 'top'].includes(hub.side) ? -1 : 1, axis: vertical ? 'y' : 'x',
        side: hub.side, custom: true, internal: true, detail: true };
    });
  }
  function open(options) {
    const overlay = document.createElement('div');
    overlay.className = 'riser-detail-editor'; overlay.setAttribute('role', 'dialog');
    const custom = options.item.type === 'custom_element';
    overlay.setAttribute('aria-modal', 'true'); overlay.setAttribute('aria-label', custom ? 'Custom element designer' : 'Detailed riser-base editor');
    overlay.innerHTML = `<div class="rd-toolbar"><b>${custom ? 'Custom element designer' : 'Detailed riser base'}</b>
      <button data-mode="select" class="on">Select / move</button><button data-mode="hub">+ Hub</button>
      <button data-mode="junction">+ Junction</button><button data-mode="pipe">Draw pipe / crossover</button>
      <button data-mode="valve">+ Valve</button>
      <button data-mode="rect">Rectangle</button><button data-mode="ellipse">Circle / ellipse</button>
      <button data-mode="line">Line</button><button data-mode="text">Text</button>
      <select id="rd-service" aria-label="New pipe or hub service">${Object.entries(definitions.services).map(([id, s]) => `<option value="${id}">${esc(s.label)}</option>`).join('')}</select>
      <select id="rd-kind" aria-label="New valve type">${Object.entries(options.valveTypes).map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join('')}</select>
      <button id="rd-fit">Fit</button><button id="rd-in" aria-label="Zoom in details">+</button><button id="rd-out" aria-label="Zoom out details">-</button><button id="rd-export">Download layout JSON</button>
      <label class="rd-upload">Load layout JSON<input id="rd-import" type="file" accept=".json,application/json"></label>
      <select id="rd-template" aria-label="Starting template"><option value="blank">Blank element</option><option value="riser">Illustrated riser</option></select><button id="rd-template-load">Use template</button>
      <button id="rd-close">Close</button></div>
      <p id="rd-status" role="status"></p><p id="rd-error" role="alert"></p>
      <div class="rd-workspace"><svg id="rd-svg" xmlns="http://www.w3.org/2000/svg"></svg><div id="rd-settings"></div></div>
      <p class="rd-footnote">Changes save automatically to the working design. Save a case version for permanent storage. Drawing units, NOT TO SCALE. Crossing lines connect only at a junction dot.</p>`;
    options.parent.appendChild(overlay);
    const $ = (selector) => overlay.querySelector(selector), svg = $('#rd-svg'), settings = $('#rd-settings');
    svg.setAttribute('tabindex', '0');
    let layout = copy(options.item.riserDetail), valves = copy(options.item.internalValves || []);
    let mode = 'select', selection = null, pending = null, drag = null, view;
    const snapshot = () => ({ layout: copy(layout), valves: copy(valves) });
    const find = (type, id) => (type === 'valve' ? valves : layout[type === 'hub' ? 'hubs' : type === 'junction' ? 'junctions' : type === 'shape' ? 'shapes' : 'routes'] || []).find((entry) => entry.id === id);
    const status = (message) => { $('#rd-status').textContent = message; };
    function commit(before, refresh = true) {
      let invalid = errors(layout);
      if (!invalid.length) invalid = options.validate(layout, valves);
      if (invalid.length) {
        layout = before.layout; valves = before.valves;
        pending = null;
        $('#rd-error').textContent = 'Changes not saved: ' + invalid.join(' ');
        render(); showSettings(); return false;
      }
      $('#rd-error').textContent = '';
      options.commit(copy(layout), copy(valves));
      render(); if (refresh) showSettings();
      return true;
    }
    const unique = (stem, entries) => {
      let number = 1;
      while (entries.some((entry) => entry.id === stem + number)) number++;
      return stem + number;
    };
    const at = (event) => {
      const p = svg.createSVGPoint(); p.x = event.clientX; p.y = event.clientY;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    };
    const inside = (p) => ({ x: Math.max(0, Math.min(layout.width, p.x)), y: Math.max(0, Math.min(layout.height, p.y)) });
    function onEdge(p, side) {
      p = inside(p);
      side = side || [['left', p.x], ['right', layout.width - p.x], ['top', p.y], ['bottom', layout.height - p.y]].sort((a, b) => a[1] - b[1])[0][0];
      if (side === 'left') p.x = 0;
      if (side === 'right') p.x = layout.width;
      if (side === 'top') p.y = 0;
      if (side === 'bottom') p.y = layout.height;
      return { ...p, side };
    }
    function split(route, p) {
      const projected = project(layout, route, p);
      if (projected.position < .1) return route.from;
      if (projected.position > 99.9) return route.to;
      const node = { id: unique('j', layout.junctions), x: projected.x, y: projected.y };
      const points = routePoints(layout, route), oldTo = route.to;
      const newRoute = { ...route, id: unique('pipe', layout.routes), from: '@' + node.id, to: oldTo,
        points: points.slice(projected.index + 1, -1).map(({ x, y }) => ({ x, y })) };
      route.to = '@' + node.id;
      route.points = points.slice(1, projected.index + 1).map(({ x, y }) => ({ x, y }));
      for (const v of valves.filter((entry) => entry.pipe === 'route-' + route.id)) {
        if (v.position <= projected.position) v.position = v.position / projected.position * 100;
        else { v.pipe = 'route-' + newRoute.id; v.position = (v.position - projected.position) / (100 - projected.position) * 100; }
      }
      layout.junctions.push(node); layout.routes.push(newRoute);
      return '@' + node.id;
    }
    function render() {
      const serviceOptions = definitions.services;
      let body = `<defs><pattern id="rd-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="#d7dce2" stroke-width=".4"/></pattern></defs>
        <rect x="-1000" y="-1000" width="4000" height="4000" fill="#fff"/>
        <rect x="0" y="0" width="${layout.width}" height="${layout.height}" fill="#FFFFCF" stroke="#111"/>
        <rect x="0" y="0" width="${layout.width}" height="${layout.height}" fill="url(#rd-grid)" pointer-events="none"/>`;
      for (const shape of layout.shapes || []) body += `<g data-rd-type="shape" data-rd-id="${esc(shape.id)}">${shape.kind === 'line'
        ? `<path d="M${shape.x} ${shape.y}L${shape.x2} ${shape.y2}" fill="none" stroke="transparent" stroke-width="12"/>` : ''}
        ${shapeMarkup(shape)}<title>${esc(shape.kind)}: ${esc(shape.text || shape.id)}</title></g>`;
      for (const route of layout.routes) {
        const d = pathData(routePoints(layout, route)), style = serviceOptions[route.service];
        body += `<g data-rd-type="pipe" data-rd-id="${esc(route.id)}"><path d="${d}" fill="none" stroke="transparent" stroke-width="12" pointer-events="stroke"/>
          <path id="rd-route-${esc(route.id)}" d="${d}" fill="none" stroke="${style.color}" stroke-width="${style.width}" pointer-events="none"/>
          <title>${esc(route.label || route.id)}: ${esc(style.label)}</title></g>`;
      }
      for (const hub of layout.hubs) {
        const vertical = ['top', 'bottom'].includes(hub.side), color = serviceOptions[hub.service].color;
        const offset = ['left', 'top'].includes(hub.side) ? -14 : 14;
        body += `<g data-rd-type="hub" data-rd-id="${esc(hub.id)}" transform="translate(${hub.x} ${hub.y})">
          <circle r="10" fill="transparent" pointer-events="all"/>
          <g transform="rotate(${vertical ? 90 : 0})">${options.hubMarkup()}</g>
          <text x="${vertical ? 0 : offset}" y="${vertical ? offset : -8}" font-size="9" fill="${color}" text-anchor="${vertical ? 'middle' : hub.side === 'left' ? 'end' : 'start'}">${esc(hub.label || '')}</text>
          <title>${esc(hub.id)}: ${esc(serviceOptions[hub.service].label)}</title></g>`;
      }
      for (const node of layout.junctions) {
        body += `<g data-rd-type="junction" data-rd-id="${esc(node.id)}"><circle cx="${node.x}" cy="${node.y}" r="8" fill="transparent"/>
          <circle cx="${node.x}" cy="${node.y}" r="2.5" fill="#111"/><title>${esc(node.label || node.id)}</title></g>`;
      }
      svg.innerHTML = body;
      for (const v of valves) {
        const route = layout.routes.find((entry) => 'route-' + entry.id === v.pipe), path = svg.querySelector('#rd-route-' + route.id);
        const length = path.getTotalLength(), along = length * (v.position ?? 50) / 100, p = path.getPointAtLength(along);
        const a = path.getPointAtLength(Math.max(0, along - .1)), b = path.getPointAtLength(Math.min(length, along + .1));
        svg.insertAdjacentHTML('beforeend', `<g data-rd-type="valve" data-rd-id="${esc(v.id)}" transform="translate(${p.x} ${p.y})">
          <circle r="11" fill="transparent"/><g transform="rotate(${Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI})">${options.valveMarkup(v)}</g>
          <text y="-38" text-anchor="middle" font-size="8">${esc([v.tag, v.label].filter(Boolean).join(' / '))}</text>
          <title>${esc(v.tag || v.id)}: ${esc(options.valveTypes[v.kind || 'gate'])} (${v.closed ? 'closed' : 'open'})</title></g>`);
      }
      if (selection?.type === 'pipe') {
        const route = find('pipe', selection.id);
        if (route) {
          const points = routePoints(layout, route).slice(1, -1);
          points.forEach((p, i) => svg.insertAdjacentHTML('beforeend',
            `<circle class="rd-bend" data-rd-bend="${i}" cx="${p.x}" cy="${p.y}" r="5" fill="#fff" stroke="#2251ff"><title>Drag bend; double-click to remove</title></circle>`));
        }
      }
      if (selection?.type === 'shape') {
        const s = find('shape', selection.id);
        if (s && s.kind !== 'text') svg.insertAdjacentHTML('beforeend',
          `<circle data-rd-resize="${esc(s.id)}" cx="${s.kind === 'line' ? s.x2 : s.x + s.width}" cy="${s.kind === 'line' ? s.y2 : s.y + s.height}" r="5" fill="#fff" stroke="#2251ff"><title>Drag to resize / move endpoint</title></circle>`);
      }
      if (pending) {
        const source = endpoints(layout).get(pending.from);
        svg.insertAdjacentHTML('beforeend', `<path d="${pathData([source, ...pending.points])}" fill="none" stroke="#2251ff" stroke-width="2" stroke-dasharray="4 3" pointer-events="none"/>`);
      }
      svg.setAttribute('viewBox', view.join(' '));
      if (selection) svg.querySelector(`[data-rd-type="${selection.type}"][data-rd-id="${selection.id}"]`)?.classList.add('rd-selected');
    }
    function deleteSelection() {
      if (!selection) return;
      const before = snapshot(), selected = selection;
      if (selected.type === 'pipe' && valves.some((v) => v.pipe === 'route-' + selected.id)) {
        $('#rd-error').textContent = 'Remove or move this pipe\'s valves before deleting it.'; return;
      }
      if (['hub', 'junction'].includes(selected.type) && layout.routes.some((r) =>
        [r.from, r.to].includes((selected.type === 'junction' ? '@' : '') + selected.id))) {
        $('#rd-error').textContent = 'Remove or reconnect the attached pipes before deleting this endpoint.'; return;
      }
      if (selected.type === 'valve') valves = valves.filter((v) => v.id !== selected.id);
      else {
        const key = selected.type === 'hub' ? 'hubs' : selected.type === 'junction' ? 'junctions' : selected.type === 'shape' ? 'shapes' : 'routes';
        layout[key] = layout[key].filter((entry) => entry.id !== selected.id);
      }
      selection = null;
      if (!commit(before)) { selection = selected; showSettings(); }
    }
    function showSettings() {
      if (!selection || !find(selection.type, selection.id)) {
        settings.innerHTML = `<h3>Editing tools</h3><p>Select a shape, text, hub, junction, pipe or valve to edit its details.</p><p><b>Shapes:</b> choose Rectangle, Circle / ellipse or Line, then drag to draw. Text: click to place, then edit its wording. Select and drag shapes to move; use the blue handle to resize, or enter exact drawing positions/dimensions. Shapes and decorative lines do not make network connections; use hubs and pipes.</p><p><b>Draw pipe / crossover:</b> click a hub, junction or existing pipe; click blank space for bends; finish on another endpoint or pipe.</p><p><b>+ Junction:</b> click an existing pipe to split it at a connected junction, or click blank space for a new junction.</p><p>Drag hubs to any frame edge. Drag junctions or the blue bends of a selected pipe. Drag valves along their pipe. Double-click a pipe to add a bend. Use +/- or the mouse wheel to zoom; drag blank space to pan.</p>
          <label><input id="rd-show-frame" type="checkbox"${layout.showFrame !== false ? ' checked' : ''}> Show enclosure in main drawing</label>
          <label>Frame width (drawing units)<input id="rd-width" type="number" min="120" max="1000" step="any" value="${layout.width}"></label>
          <label>Frame height (drawing units)<input id="rd-height" type="number" min="120" max="1000" step="any" value="${layout.height}"></label>`;
        $('#rd-show-frame').onchange = (event) => { const before = snapshot(); layout.showFrame = event.target.checked; commit(before); };
        for (const [key, axis] of [['width', 'x'], ['height', 'y']]) $('#rd-' + key).onchange = (event) => {
          const before = snapshot(), value = event.target.valueAsNumber;
          if (!finite(value) || value < 120 || value > 1000) { $('#rd-error').textContent = 'Frame dimensions must be 120-1000 drawing units.'; return; }
          const factor = value / layout[key];
          for (const p of [...layout.hubs, ...layout.junctions, ...layout.routes.flatMap((route) => route.points || [])]) p[axis] = Math.max(0, Math.min(value, p[axis] * factor));
          for (const shape of layout.shapes || []) {
            shape[axis] *= factor;
            if (['rect', 'ellipse'].includes(shape.kind)) shape[key] *= factor;
            if (shape.kind === 'line') shape[axis + '2'] *= factor;
          }
          layout[key] = value; if (commit(before)) fit();
        };
        return;
      }
      const { type, id } = selection, entry = find(type, id);
      const input = (key, label, value, kind = 'text') => `<label for="rd-field-${key}">${label}</label><input id="rd-field-${key}" data-field="${key}" type="${kind}" value="${esc(value)}"${kind === 'number' ? ' step="any"' : ''}>`;
      const select = (key, label, values, value) => `<label for="rd-field-${key}">${label}</label><select id="rd-field-${key}" data-field="${key}">${values.map(([v, text]) => `<option value="${esc(v)}"${v === value ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select>`;
      const services = Object.entries(definitions.services).map(([i, s]) => [i, s.label]);
      let markup = `<h3>${type === 'pipe' ? 'Internal pipe' : type[0].toUpperCase() + type.slice(1)}</h3><p>ID: <b>${esc(id)}</b></p>`;
      if (type === 'valve') {
        markup += select('pipe', 'Pipe', layout.routes.map((r) => ['route-' + r.id, r.label || r.id]), entry.pipe)
          + select('kind', 'Valve type', Object.entries(options.valveTypes), entry.kind || 'gate')
          + input('position', 'Position along pipe (%)', entry.position ?? 50, 'number')
          + `<label><input data-field="closed" type="checkbox"${entry.closed ? ' checked' : ''}> Closed</label>`
          + ['tag', 'label', 'provider', 'rating'].map((key) => input(key, key[0].toUpperCase() + key.slice(1), entry[key] || '')).join('');
      } else if (type === 'shape') {
        markup += `<p>${esc(entry.kind)} (decorative, not a connection)</p>`
          + input('x', 'Horizontal drawing position', entry.x, 'number') + input('y', 'Vertical drawing position', entry.y, 'number');
        if (['rect', 'ellipse'].includes(entry.kind)) markup += input('width', 'Width', entry.width, 'number') + input('height', 'Height', entry.height, 'number')
          + input('fill', 'Fill colour (#RRGGBB or none)', entry.fill ?? 'none');
        if (entry.kind === 'line') markup += input('x2', 'End X', entry.x2, 'number') + input('y2', 'End Y', entry.y2, 'number');
        if (entry.kind === 'text') markup += input('text', 'Text', entry.text) + input('fontSize', 'Font size', entry.fontSize, 'number');
        markup += input('stroke', entry.kind === 'text' ? 'Text colour (#RRGGBB)' : 'Outline colour (#RRGGBB)', entry.stroke ?? '#111111', 'color');
        if (entry.kind !== 'text') markup += input('strokeWidth', 'Stroke width', entry.strokeWidth ?? 1.5, 'number');
      } else {
        markup += input('label', 'Label', entry.label || '');
        if (type === 'pipe') markup += select('from', 'From', [...endpoints(layout).keys()].map((v) => [v, v]), entry.from)
          + select('to', 'To', [...endpoints(layout).keys()].map((v) => [v, v]), entry.to)
          + select('service', 'Service / colour', services, entry.service) + '<button id="rd-reverse">Reverse pipe direction</button>';
        else {
          if (type === 'hub') markup += select('side', 'Frame edge', ['left', 'right', 'top', 'bottom'].map((v) => [v, v]), entry.side)
            + select('service', 'Service / colour', services, entry.service);
          markup += input('x', 'Horizontal drawing position', entry.x, 'number') + input('y', 'Vertical drawing position', entry.y, 'number');
        }
      }
      settings.innerHTML = markup + '<button id="rd-delete">Delete selected</button><p>Edits save when you leave a field. IDs remain stable to preserve pipe/valve attachments.</p>';
      settings.querySelectorAll('[data-field]').forEach((control) => {
        control.onchange = () => {
          const before = snapshot(), key = control.dataset.field, current = find(type, id);
          current[key] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? control.valueAsNumber : control.value;
          if (type === 'hub' && key === 'side') Object.assign(current, onEdge(current, current.side));
          const refresh = control.tagName === 'SELECT' || control.type === 'checkbox';
          const saved = commit(before, refresh);
          if (refresh || !saved) settings.querySelector(`[data-field="${key}"]`)?.focus();
        };
      });
      $('#rd-delete').onclick = deleteSelection;
      if ($('#rd-reverse')) $('#rd-reverse').onclick = () => {
        const before = snapshot(), route = find('pipe', id);
        route.points = routePoints(layout, route).slice(1, -1).reverse().map(({ x, y }) => ({ x, y }));
        [route.from, route.to] = [route.to, route.from];
        valves.filter((v) => v.pipe === 'route-' + id).forEach((v) => { v.position = 100 - (v.position ?? 50); });
        commit(before);
      };
    }
    function setMode(next) {
      mode = next; pending = null;
      overlay.querySelectorAll('[data-mode]').forEach((button) => button.classList.toggle('on', button.dataset.mode === mode));
      status({ select: 'Select or drag a detail. All edits save automatically.', hub: 'Click near any frame edge to add a hub.',
        junction: 'Click a pipe to create a connected junction, or blank space for a free junction.',
        pipe: 'Click a hub/junction or pipe to start. Add bends in blank space, then finish on another endpoint or pipe.',
        valve: 'Click a pipe to place a valve. Choose its type above.',
        rect: 'Drag to draw a rectangle.', ellipse: 'Drag to draw a circle or ellipse.',
        line: 'Drag to draw a decorative line (not connected piping).', text: 'Click to place text, then edit it in the side panel.' }[mode]);
      render();
    }
    svg.addEventListener('pointerdown', (event) => {
      svg.focus({ preventScroll: true });
      const p = inside(at(event)), target = event.target.closest('[data-rd-type]');
      const before = snapshot();
      if (['rect', 'ellipse', 'line', 'text'].includes(mode)) {
        layout.shapes ||= [];
        const shape = { id: unique('shape', layout.shapes), kind: mode, ...p, stroke: '#111111', fill: 'none', strokeWidth: 1.5 };
        if (mode === 'text') { Object.assign(shape, { text: 'Text', fontSize: 14 }); }
        else if (mode === 'line') Object.assign(shape, { x2: p.x, y2: p.y });
        else Object.assign(shape, { width: 1, height: 1 });
        layout.shapes.push(shape); selection = { type: 'shape', id: shape.id };
        if (mode === 'text') {
          if (commit(before)) { setMode('select'); $('#rd-field-text').focus(); $('#rd-field-text').select(); }
        } else {
          drag = { before, type: 'create-shape', id: shape.id, start: p };
          svg.setPointerCapture(event.pointerId); render();
        }
        event.preventDefault(); return;
      }
      if (mode === 'hub') {
        const position = onEdge(p), service = $('#rd-service').value;
        const stem = definitions.services[service].lane + (position.side === 'right' ? '-out-' : '-in-');
        const hub = { id: unique(stem, layout.hubs), ...position, service, label: 'New hub' };
        layout.hubs.push(hub); selection = { type: 'hub', id: hub.id }; commit(before); return;
      }
      if (mode === 'junction') {
        let id;
        if (target?.dataset.rdType === 'pipe') id = split(find('pipe', target.dataset.rdId), p).replace(/^@/, '');
        else { id = unique('j', layout.junctions); layout.junctions.push({ id, ...p }); }
        selection = { type: 'junction', id }; commit(before); return;
      }
      if (mode === 'pipe') {
        let end = target && ['hub', 'junction'].includes(target.dataset.rdType)
          ? (target.dataset.rdType === 'junction' ? '@' : '') + target.dataset.rdId : null;
        if (target?.dataset.rdType === 'pipe') end = split(find('pipe', target.dataset.rdId), p);
        if (end) {
          if (pending && end !== pending.from) {
            const route = { id: unique('pipe', layout.routes), from: pending.from, to: end,
              points: pending.points, service: $('#rd-service').value };
            layout.routes.push(route); selection = { type: 'pipe', id: route.id }; pending = null; commit(before);
          } else {
            pending = { from: end, points: [] };
            if (commit(before, false)) status('Pipe started. Click blank space for bends, then another endpoint or pipe.');
          }
        } else if (pending) { pending.points.push(p); render(); }
        return;
      }
      if (mode === 'valve') {
        if (target?.dataset.rdType !== 'pipe') { status('Click on an internal pipe to place the valve.'); return; }
        const route = find('pipe', target.dataset.rdId);
        const v = { id: unique('v', valves), pipe: 'route-' + route.id, position: project(layout, route, p).position,
          kind: $('#rd-kind').value, closed: false, tag: '', label: '', provider: '', rating: '' };
        valves.push(v); selection = { type: 'valve', id: v.id }; commit(before); return;
      }
      const bend = event.target.closest('[data-rd-bend]'), resize = event.target.closest('[data-rd-resize]');
      if (resize) {
        selection = { type: 'shape', id: resize.dataset.rdResize };
        drag = { before, type: 'resize-shape', id: selection.id };
      } else if (bend && selection?.type === 'pipe') {
        const route = find('pipe', selection.id);
        route.points = routePoints(layout, route).slice(1, -1).map(({ x, y }) => ({ x, y }));
        drag = { before, type: 'bend', id: selection.id, index: +bend.dataset.rdBend };
      } else if (target) {
        selection = { type: target.dataset.rdType, id: target.dataset.rdId };
        if (selection.type !== 'pipe') drag = { before, ...selection, start: p };
      } else {
        selection = null;
        drag = { type: 'pan', before, view: view.slice(), sx: event.clientX, sy: event.clientY, scale: svg.getScreenCTM().a };
      }
      render(); showSettings();
      if (drag) svg.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    svg.addEventListener('pointermove', (event) => {
      if (!drag) return;
      if (drag.type === 'pan') {
        view[0] = drag.view[0] - (event.clientX - drag.sx) / drag.scale;
        view[1] = drag.view[1] - (event.clientY - drag.sy) / drag.scale;
        svg.setAttribute('viewBox', view.join(' ')); return;
      }
      const p = inside(at(event));
      if (['create-shape', 'resize-shape', 'shape'].includes(drag.type)) {
        const s = find('shape', drag.id);
        if (drag.type === 'create-shape') {
          if (s.kind === 'line') Object.assign(s, { x2: p.x, y2: p.y });
          else Object.assign(s, { x: Math.min(p.x, drag.start.x), y: Math.min(p.y, drag.start.y),
            width: Math.abs(p.x - drag.start.x), height: Math.abs(p.y - drag.start.y) });
        } else if (drag.type === 'resize-shape') {
          if (s.kind === 'line') Object.assign(s, { x2: p.x, y2: p.y });
          else Object.assign(s, { width: Math.max(.1, p.x - s.x), height: Math.max(.1, p.y - s.y) });
        } else {
          const original = drag.before.layout.shapes.find((s) => s.id === drag.id);
          const xs = [original.x, original.kind === 'line' ? original.x2 : original.x + (original.width || 0)];
          const ys = [original.y, original.kind === 'line' ? original.y2 : original.y + (original.height || 0)];
          const dx = Math.max(-Math.min(...xs), Math.min(layout.width - Math.max(...xs), p.x - drag.start.x));
          const dy = Math.max(-Math.min(...ys), Math.min(layout.height - Math.max(...ys), p.y - drag.start.y));
          Object.assign(s, { x: original.x + dx, y: original.y + dy });
          if (s.kind === 'line') Object.assign(s, { x2: original.x2 + dx, y2: original.y2 + dy });
        }
      } else if (drag.type === 'hub') Object.assign(find('hub', drag.id), onEdge(p));
      else if (drag.type === 'junction') Object.assign(find('junction', drag.id), p);
      else if (drag.type === 'bend') find('pipe', drag.id).points[drag.index] = p;
      else if (drag.type === 'valve') {
        const v = find('valve', drag.id), route = layout.routes.find((r) => 'route-' + r.id === v.pipe);
        v.position = project(layout, route, p).position;
      }
      drag.moved = true; render();
    });
    svg.addEventListener('pointerup', () => {
      if (!drag) return;
      const current = drag; drag = null;
      if (current.type === 'pan') return;
      if (current.type === 'create-shape') {
        if (current.moved && commit(current.before)) setMode('select');
        else {
          layout = current.before.layout; valves = current.before.valves; selection = null; render(); showSettings();
          if (!current.moved) $('#rd-error').textContent = 'Drag across the canvas to draw a shape.';
        }
      } else if (current.moved) commit(current.before);
      else { layout = current.before.layout; valves = current.before.valves; render(); showSettings(); }
    });
    svg.addEventListener('pointercancel', () => {
      if (drag) {
        layout = drag.before.layout; valves = drag.before.valves;
        if (drag.type === 'pan') view = drag.view;
        drag = null; render(); showSettings();
      }
    });
    svg.addEventListener('dblclick', (event) => {
      if (mode !== 'select') return;
      const before = snapshot(), bend = event.target.closest('[data-rd-bend]'), target = event.target.closest('[data-rd-type="pipe"]');
      if (bend && selection?.type === 'pipe') {
        const route = find('pipe', selection.id);
        route.points = routePoints(layout, route).slice(1, -1).map(({ x, y }) => ({ x, y }));
        route.points.splice(+bend.dataset.rdBend, 1);
      }
      else if (target) {
        const route = find('pipe', target.dataset.rdId), p = inside(at(event)), closest = project(layout, route, p);
        route.points = routePoints(layout, route).slice(1, -1).map(({ x, y }) => ({ x, y }));
        route.points.splice(closest.index, 0, p); selection = { type: 'pipe', id: route.id };
      } else return;
      commit(before);
    });
    svg.addEventListener('wheel', (event) => {
      event.preventDefault();
      const p = at(event), factor = event.deltaY < 0 ? .9 : 1.1;
      view = [p.x - (p.x - view[0]) * factor, p.y - (p.y - view[1]) * factor, view[2] * factor, view[3] * factor];
      svg.setAttribute('viewBox', view.join(' '));
    }, { passive: false });
    overlay.querySelectorAll('[data-mode]').forEach((button) => { button.onclick = () => setMode(button.dataset.mode); });
    const fit = () => { view = [-130, -30, layout.width + 310, layout.height + 80]; render(); };
    $('#rd-fit').onclick = fit;
    const zoom = (factor) => {
      const x = view[0] + view[2] / 2, y = view[1] + view[3] / 2;
      view = [x - view[2] * factor / 2, y - view[3] * factor / 2, view[2] * factor, view[3] * factor];
      svg.setAttribute('viewBox', view.join(' '));
    };
    $('#rd-in').onclick = () => zoom(.8); $('#rd-out').onclick = () => zoom(1.25);
    $('#rd-close').onclick = () => { overlay.remove(); options.onClose(); };
    overlay.addEventListener('keydown', (event) => {
      if (event.key === 'Tab') {
        const controls = [...overlay.querySelectorAll('button,input,select,textarea,[tabindex]')]
          .filter((control) => !control.disabled && control.getClientRects().length);
        const index = controls.indexOf(document.activeElement);
        if (index < 0 || (!event.shiftKey && index === controls.length - 1) || (event.shiftKey && index === 0)) {
          event.preventDefault(); controls[event.shiftKey ? controls.length - 1 : 0]?.focus();
        }
      }
      if (['Delete', 'Backspace', 'Escape'].includes(event.key)) event.stopPropagation();
      if (event.key === 'Escape') { event.preventDefault(); if (pending) setMode('select'); else $('#rd-close').click(); }
      if (['Delete', 'Backspace'].includes(event.key) && !event.target.closest('input,select,textarea')) { event.preventDefault(); deleteSelection(); }
    });
    $('#rd-export').onclick = () => options.download(new Blob([JSON.stringify({
      format: custom ? 'subsea-element-layout' : 'subsea-riser-detail', version: 1, riserDetail: layout, internalValves: valves,
    }, null, 2)], { type: 'application/json' }), custom ? 'custom_element_layout.json' : 'riser_base_layout.json');
    $('#rd-import').onchange = async (event) => {
      const file = event.target.files[0]; if (!file) return;
      event.target.value = '';
      if (file.size > 2000000) { $('#rd-error').textContent = 'Layout file must be smaller than 2 MB.'; return; }
      let data;
      try { data = JSON.parse(await file.text()); }
      catch (error) { if (!(error instanceof SyntaxError)) throw error; $('#rd-error').textContent = 'Invalid layout JSON: ' + error.message; return; }
      if (!data || !['subsea-riser-detail', 'subsea-element-layout'].includes(data.format) || data.version !== 1 || !Array.isArray(data.internalValves)) {
        $('#rd-error').textContent = 'Choose a version 1 subsea-element-layout or subsea-riser-detail file.'; return;
      }
      const invalid = errors(data.riserDetail);
      if (invalid.length) { $('#rd-error').textContent = invalid.join(' '); return; }
      if (!root.confirm('Replace this element\'s drawing and valves with the loaded layout?')) return;
      const before = snapshot(); layout = copy(data.riserDetail); valves = copy(data.internalValves); selection = null; pending = null;
      if (commit(before)) fit();
    };
    $('#rd-template-load').onclick = () => {
      if (!root.confirm('Replace this element\'s drawing and valves with the selected template? Connected hubs remain protected.')) return;
      const next = $('#rd-template').value === 'riser' ? copy(definitions.reference) : blank();
      const before = snapshot(); layout = next.riserDetail; valves = next.internalValves; selection = null; pending = null;
      if (commit(before)) fit();
    };
    fit(); setMode('select'); showSettings(); $('#rd-close').focus();
    return {
      sync(item) {
        if (!item?.riserDetail) { $('#rd-close').click(); return; }
        if (JSON.stringify([layout, valves]) !== JSON.stringify([item.riserDetail, item.internalValves || []])) {
          layout = copy(item.riserDetail); valves = copy(item.internalValves || []); pending = null; drag = null;
          if (selection && !find(selection.type, selection.id)) selection = null;
          render(); showSettings(); status('Editor updated from the current design.');
        }
      },
      close() { $('#rd-close').click(); },
    };
  }
  root.SubseaRiserDetail = { configure: (value) => { definitions = value; }, errors, draw, ports, open,
    reference: () => copy(definitions.reference), blank, services: () => definitions.services };
})(window);
