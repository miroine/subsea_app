(function (root) {
  'use strict';
  let library;
  async function loadLibrary() {
    if (!library) library = (async () => {
      if (!root.DecompressionStream) throw new Error('3D requires a modern browser with DecompressionStream and WebGL2.');
      const payload = JSON.parse(document.getElementById('three-library').textContent);
      const unpack = async (text) => {
        const bytes = Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
        return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
      };
      const core = URL.createObjectURL(new Blob([await unpack(payload.core)], { type: 'text/javascript' }));
      const source = (await unpack(payload.module)).replaceAll("'./three.core.js'", JSON.stringify(core));
      const module = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      root.addEventListener('unload', () => { URL.revokeObjectURL(core); URL.revokeObjectURL(module); }, { once: true });
      return import(module);
    })();
    try { return await library; }
    catch (error) { library = null; throw error; }
  }
  const families = {};
  const register = (family, ids) => ids.split(' ').forEach((id) => { families[id] = family; });
  register('jacket', 'jacket platform');
  register('jackup', 'jackup');
  register('floating', 'fpso semisub tlp spar');
  register('tower', 'wind hrt');
  register('terminal', 'onshore tieback');
  register('tree', 'satellite_well vxt hxt wellhead');
  register('frame', 'template manifold plem plet ilt ils fta riser_skid riser_base gl_manifold compression_station hydrate_skid protection_frame trawl_guard');
  register('connector', 'hub_conn end_termination wye_tee flex_joint bend_stiffener');
  register('pipe', 'spool jumper_rigid jumper_flex pipeline_rigid pipeline_pip pipeline_flex pipeline_bundle cable_power efl');
  register('valve', 'valve_gate valve_ball valve_check choke esdv ssiv valve_control valve_xov hipps civ');
  register('instrument', 'mpfm sand_detector pt_sensor tt_sensor leak_detector');
  register('pump', 'mpp srp wgc cip');
  register('vessel', 'separator storage_tank accumulator hpu');
  register('cooler', 'hx deh water_treat');
  register('control', 'sdu uta suta scm transformer vsd switchgear power_hub pct fibre_hub junction_box');
  register('foundation', 'suction_pile pipe_support anode buoyancy');
  register('seabed', 'mattress rockdump crossing');
  register('pig', 'pig_launcher pig_receiver');
  register('electrical', 'sld_breaker sld_disconnector sld_fuse sld_motor sld_generator sld_ct_vt sld_earthing sld_busbar');
  register('custom', 'custom_element');
  const UNIT = .08;
  async function create(options) {
    const T = await loadLibrary(), container = options.container;
    const renderer = new T.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(root.devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = T.SRGBColorSpace;
    renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.45;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    const canvas = renderer.domElement;
    canvas.setAttribute('aria-label', '3D seabed, equipment and animated flow'); canvas.setAttribute('tabindex', '0');
    container.appendChild(canvas);
    const $ = (s) => container.querySelector(s), info = $('#scene3d-info'), errorBox = $('#scene3d-error');
    const scene = new T.Scene(); scene.background = new T.Color('#34383d'); scene.fog = new T.FogExp2('#34383d', .002);
    const camera = new T.PerspectiveCamera(45, 1, .05, 20000);
    const stage = new T.Group(), environment = new T.Group(), editing = new T.Group();
    editing.userData.editorOnly = true;
    scene.add(stage, environment, editing, new T.HemisphereLight('#f2f4f6', '#555555', 2.4));
    const sun = new T.DirectionalLight('#ffffff', 3.4);
    sun.position.set(40, 110, -30); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
    scene.add(sun, sun.target);
    const fill = new T.DirectionalLight('#dde2e8', 1.2); fill.position.set(-60, 40, 60); scene.add(fill);
    const geometries = {
      box: new T.BoxGeometry(1, 1, 1), cylinder: new T.CylinderGeometry(1, 1, 1, 16),
      sphere: new T.SphereGeometry(1, 16, 10), torus: new T.TorusGeometry(1, .12, 8, 24),
    };
    const materials = new Map(), owned = new Set();
    const mat = (color, metal = .45) => {
      const key = `${color}/${metal}`;
      if (!materials.has(key)) materials.set(key, new T.MeshStandardMaterial({ color, metalness: metal, roughness: .48 }));
      return materials.get(key);
    };
    const steel = mat('#99abb0', .82), dark = mat('#24363f', .65), paint = mat('#f2c51c', .25), red = mat('#c23e36');
    const yellow = paint, topside = mat('#c9cecf', .25), whitePipe = mat('#e3e5e4', .25);
    const guideMaterial = new T.MeshStandardMaterial({ color: '#a7adb3', metalness: .3, roughness: .55,
      transparent: true, opacity: .3, depthWrite: false });
    materials.set('j-tube-wall', guideMaterial);
    const mesh = (parent, kind, x, y, z, sx, sy, sz, material, name) => {
      const part = new T.Mesh(geometries[kind], material);
      part.position.set(x, y, z); part.scale.set(Math.max(sx, .001), Math.max(sy, .001), Math.max(sz, .001));
      part.castShadow = true; part.receiveShadow = true; part.name = name;
      parent.add(part); return part;
    };
    const box = (g, x, y, z, w, h, d, m = paint, name = 'Painted equipment housing') => mesh(g, 'box', x, y, z, w, h, d, m, name);
    const cyl = (g, x, y, z, r, h, m = steel, name = 'Machined cylinder') => mesh(g, 'cylinder', x, y, z, r, h, r, m, name);
    const ball = (g, x, y, z, r, m = steel, name = 'Pressure vessel end') => mesh(g, 'sphere', x, y, z, r, r, r, m, name);
    const beam = (g, a, b, radius = .07, material = steel, name = 'Structural member') => {
      const first = new T.Vector3(...a), last = new T.Vector3(...b), v = last.clone().sub(first);
      const mid = first.clone().add(last).multiplyScalar(.5);
      const part = cyl(g, mid.x, mid.y, mid.z, radius, v.length(), material, name);
      if (v.length()) part.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), v.normalize());
      return part;
    };
    function flange(g, x, y, z, radius = .32, axis = new T.Vector3(1, 0, 0)) {
      const assembly = new T.Group(); assembly.position.set(x, y, z);
      assembly.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), axis.clone().normalize()); g.add(assembly);
      cyl(assembly, 0, 0, 0, radius, .12, steel, 'Bolted hub flange');
      cyl(assembly, 0, .09, 0, radius * .68, .1, dark, 'Flange gasket and collar');
      for (let i = 0; i < 8; i++) {
        const angle = i * Math.PI / 4;
        cyl(assembly, Math.cos(angle) * radius * .81, .08, Math.sin(angle) * radius * .81, radius * .085, .15, dark, 'Hub flange stud and nut');
      }
    }
    function valve(g, x, y, z, kind = 'gate', angle = 0, size = 1, closed = false) {
      const v = new T.Group(); v.name = `${kind} valve assembly`; v.position.set(x, y, z); v.rotation.y = angle; v.scale.setScalar(size); g.add(v);
      beam(v, [-.7, 0, 0], [.7, 0, 0], .2, steel, 'Valve flow bore');
      if (kind === 'ball') ball(v, 0, .02, 0, .38, closed ? red : paint, 'Ball valve pressure body');
      else box(v, 0, .02, 0, .58, .55, .45, closed ? red : paint, `${kind} valve pressure body`);
      flange(v, -.64, 0, 0); flange(v, .64, 0, 0);
      cyl(v, 0, .47, 0, .11, .55, steel, 'Valve stem and bonnet');
      if (['esdv', 'ssiv', 'control', 'choke', 'psv'].includes(kind)) {
        cyl(v, 0, .9, 0, .3, .55, paint, 'Hydraulic actuator / spring housing');
        box(v, .32, .85, 0, .2, .25, .22, dark, 'Actuator hydraulic connection');
        if (kind === 'psv') beam(v, [0, .6, 0], [0, .6, .6], .12, steel, 'Relief branch');
      } else if (kind === 'check') cyl(v, 0, .42, 0, .22, .16, dark, 'Check valve inspection cap');
      else {
        mesh(v, 'torus', 0, .83, 0, .28, .28, .28, dark, 'Valve handwheel').rotation.x = Math.PI / 2;
        beam(v, [-.26, .83, 0], [.26, .83, 0], .03, dark, 'Handwheel spoke');
        beam(v, [0, .83, -.26], [0, .83, .26], .03, dark, 'Handwheel spoke');
      }
      return v;
    }
    function skid(g, w, d, cage = true, foundation = paint) {
      box(g, 0, .12, 0, w, .24, d, foundation, 'Mudmat / skid foundation');
      for (const z of [-d * .4, d * .4]) box(g, 0, .35, z, w, .24, .18, paint, 'Skid support rail');
      for (let i = -1; i <= 1; i++) box(g, i * w * .35, .36, 0, .14, .2, d, paint, 'Skid cross member');
      if (cage) {
        for (const x of [-w / 2, w / 2]) for (const z of [-d / 2, d / 2]) {
          beam(g, [x, .3, z], [x, 2.8, z], .09, paint, 'Protection frame corner post');
          ball(g, x, 2.9, z, .14, dark, 'ROV lifting / guide point');
        }
        for (const z of [-d / 2, d / 2]) beam(g, [-w / 2, 2.8, z], [w / 2, 2.8, z], .09, paint, 'Protection top rail');
        for (const x of [-w / 2, w / 2]) beam(g, [x, 2.8, -d / 2], [x, 2.8, d / 2], .09, paint, 'Protection end rail');
      }
    }
    function protectiveHood(g, w, d, bays, height = 3.4, foundation = true) {
      const gold = paint;
      if (foundation) skid(g, w, d, false, gold);
      for (const x of [-w * .4, w * .4]) for (const z of [-d * .36, d * .36]) {
        box(g, x, height / 2, z, .16, height, .16, gold, 'Protection hood upright');
        const outline = new T.Shape();
        outline.moveTo(0, 0); outline.lineTo(Math.sign(x) * w * .18, 0); outline.lineTo(0, height - .4); outline.closePath();
        const plate = new T.Mesh(new T.ExtrudeGeometry(outline, { depth: .07, bevelEnabled: false }), gold);
        plate.position.set(x, .3, z); plate.name = 'Sloped protective gusset'; plate.castShadow = true; g.add(plate);
      }
      for (let i = 0; i < bays; i++) {
        const x = w * .8 * ((i + .5) / bays - .5);
        box(g, x, height, 0, w * .8 / bays * .93, .12, d * .76, gold, 'Protection roof panel');
        for (const z of [-d * .3, d * .3]) box(g, x, height + .12, z, w * .8 / bays * .88, .1, .08, dark, 'Roof lifting / stiffener rail');
      }
      for (const z of [-d * .38, d * .38]) box(g, 0, height - .15, z, w * .85, .15, .12, gold, 'Hood roof edge beam');
    }
    function tree(g, x, z, variant = 'vxt') {
      const t = new T.Group(); t.position.set(x, 0, z); g.add(t);
      cyl(t, 0, .45, 0, .48, .9, dark, 'Wellhead / conductor housing');
      cyl(t, 0, 1.5, 0, .26, 1.7, steel, 'Tree production bore');
      box(t, 0, 1.5, 0, .8, .7, .7, paint, `${variant} tree valve block`);
      if (variant === 'hxt') {
        beam(t, [-.7, 1.5, 0], [.7, 1.5, 0], .35, paint, 'Horizontal tree valve block');
        flange(t, -.7, 1.5, 0, .42); flange(t, .7, 1.5, 0, .42);
      }
      valve(t, .5, 1.55, 0, 'ssiv', 0, .65); valve(t, 0, 2.35, .28, 'gate', Math.PI / 2, .55);
      box(t, -.65, 1.55, 0, .5, .65, .45, paint, 'Tree control module');
      cyl(t, 0, 2.75, 0, .34, .18, steel, 'Swab cap / ROV interface');
    }
    function vessel(g, length, radius, vertical = false) {
      const body = cyl(g, 0, vertical ? radius + length / 2 : 1.5, 0, radius, length, steel, 'Pressure vessel shell');
      if (!vertical) body.rotation.z = Math.PI / 2;
      for (const sign of [-1, 1]) ball(g, vertical ? 0 : sign * length / 2,
        vertical ? radius + length / 2 + sign * length / 2 : 1.5, 0, radius, steel, 'Dished vessel head');
      if (!vertical) for (const sign of [-1, 1]) box(g, sign * length * .32, .7, 0, .3, 1.1, radius * 1.8, dark, 'Vessel saddle support');
      beam(g, [0, 1.5, 0], [0, 2.8, 0], .12, steel, 'Vessel process nozzle'); flange(g, 0, 2.8, 0, .26, new T.Vector3(0, 1, 0));
    }
    function guardrails(g, width, depth, height, material = yellow) {
      for (const z of [-depth / 2, depth / 2]) {
        for (const y of [height + .8, height + 1.25]) beam(g, [-width / 2, y, z], [width / 2, y, z], .035, material, 'Topside guardrail');
        for (let i = 0; i <= 10; i++) beam(g, [width * (i / 10 - .5), height + .25, z],
          [width * (i / 10 - .5), height + 1.25, z], .035, topside, 'Guardrail stanchion');
      }
      for (const x of [-width / 2, width / 2]) {
        for (const y of [height + .8, height + 1.25]) beam(g, [x, y, -depth / 2], [x, y, depth / 2], .035, material, 'Topside guardrail');
        for (let i = 0; i <= 8; i++) beam(g, [x, height + .25, depth * (i / 8 - .5)],
          [x, height + 1.25, depth * (i / 8 - .5)], .035, topside, 'Guardrail stanchion');
      }
    }
    function crane(g, base, tip, height) {
      cyl(g, base.x, height + .9, base.z, .38, 1.3, yellow, 'Crane pedestal');
      box(g, base.x - .45, height + 1.35, base.z, .8, .9, .8, topside, 'Crane operator cabin');
      box(g, base.x - .45, height + 1.55, base.z + .41, .65, .3, .03, dark, 'Crane cabin window');
      for (const z of [-.22, .22]) for (const y of [-.22, .22]) {
        const offset = new T.Vector3(0, y, z);
        beam(g, base.clone().add(offset).toArray(), tip.clone().add(offset.clone().multiplyScalar(.5)).toArray(), .04, topside, 'Crane lattice chord');
      }
      for (let i = 0; i < 10; i++) for (const z of [-.22, .22]) {
        const a = base.clone().lerp(tip, i / 10), b = base.clone().lerp(tip, (i + 1) / 10);
        const sizeA = .22 * (1 - i / 20), sizeB = .22 * (1 - (i + 1) / 20);
        beam(g, [a.x, a.y - sizeA, a.z + z * sizeA / .22], [b.x, b.y + sizeB, b.z + z * sizeB / .22], .025, topside, 'Crane lattice diagonal');
        beam(g, [a.x, a.y - sizeA, a.z + z * sizeA / .22], [a.x, a.y + sizeA, a.z + z * sizeA / .22], .025, topside, 'Crane lattice cross member');
      }
      beam(g, tip.toArray(), [tip.x, height + 3, tip.z], .012, dark, 'Crane hoist wire');
      mesh(g, 'torus', tip.x, height + 2.85, tip.z, .13, .13, .13, steel, 'Crane lifting hook');
    }
    function shipHull(g, length, breadth, depth, deck) {
      const stations = [[-.5, .72], [-.46, 1], [-.32, 1], [.2, 1], [.36, .86], [.46, .4], [.5, .015]];
      const section = [[0, -.5], [-.28, -.5], [-.85, -.4], [-1, -.2], [-1, .2], [-.85, .4], [-.28, .5], [0, .5]];
      const vertices = [], indices = [];
      for (const [x, spread] of stations) for (const [y, z] of section) vertices.push(x * length, deck + y * depth, z * breadth * spread);
      const count = section.length;
      for (let i = 0; i < stations.length - 1; i++) for (let j = 0; j < count; j++) {
        const a = i * count + j, b = a + count, d = i * count + (j + 1) % count, c = d + count;
        indices.push(a, b, d, b, c, d);
      }
      for (let j = 1; j < count - 1; j++) {
        indices.push(0, j, j + 1);
        const end = (stations.length - 1) * count;
        indices.push(end, end + j + 1, end + j);
      }
      const geometry = new T.BufferGeometry();
      geometry.setAttribute('position', new T.Float32BufferAttribute(vertices, 3));
      geometry.setIndex(indices); geometry.computeVertexNormals();
      const hull = new T.Mesh(geometry, red); hull.name = 'FPSO shaped hull';
      hull.castShadow = true; hull.receiveShadow = true; g.add(hull);
      const outline = new T.Shape();
      stations.forEach(([x, spread], i) => outline[i ? 'lineTo' : 'moveTo'](x * length, -breadth * spread / 2));
      [...stations].reverse().forEach(([x, spread]) => outline.lineTo(x * length, breadth * spread / 2));
      outline.closePath();
      const plate = new T.Mesh(new T.ShapeGeometry(outline).rotateX(-Math.PI / 2), topside);
      plate.position.y = deck + .025; plate.name = 'FPSO shaped main deck'; plate.receiveShadow = true; g.add(plate);
      const perimeter = [...stations.map(([x, spread]) => [x * length, -breadth * spread * .48]),
        ...[...stations].reverse().map(([x, spread]) => [x * length, breadth * spread * .48])];
      for (let i = 0; i < perimeter.length; i++) {
        const [x, z] = perimeter[i], [xx, zz] = perimeter[(i + 1) % perimeter.length];
        for (const y of [deck + .5, deck + .95]) beam(g, [x, y, z], [xx, y, zz], .025, topside, 'FPSO deck guardrail');
        const posts = Math.max(1, Math.ceil(Math.hypot(xx - x, zz - z) / 1.2));
        for (let post = 0; post < posts; post++) {
          const px = x + (xx - x) * post / posts, pz = z + (zz - z) * post / posts;
          beam(g, [px, deck + .05, pz], [px, deck + .95, pz], .025, topside, 'FPSO rail stanchion');
        }
      }
    }
    function model(node) {
      const g = new T.Group(), family = families[node.type] || (node.customSymbol ? 'custom-symbol' : null);
      if (!family) throw new Error(`No 3D equipment definition for ${node.type}.`);
      const w = Math.max(node.box.width * UNIT, 1.2), d = Math.max(node.box.height * UNIT, 1.2);
      g.userData = { equipmentId: node.id, family, type: node.type }; g.name = node.name;
      let pipeHeight = family === 'pipe' && !node.schematic ? .65 : 1.2, height = 3;
      if (['frame', 'custom'].includes(family)) {
        if (['template', 'plet'].includes(node.type)) {
          protectiveHood(g, w * .92, d * .82, node.type === 'plet' ? 2 : Math.max(2, Math.min(6, Number(node.item.wells ?? 4))));
          height = 3.6;
        } else if (node.type === 'plem') {
          const bore = node.pipes.find((p) => p.lane === 'P');
          const center = bore ? world(bore.points[0]).lerp(world(bore.points.at(-1)), .5)
            .sub(world({ x: node.box.cx, y: node.box.cy }, 0)) : new T.Vector3(0, pipeHeight, 0);
          const skidDepth = Math.min(d * .82, w * .38);
          for (const z of [-skidDepth / 2, skidDepth / 2]) {
            box(g, center.x, .18, center.z + z, w * .86, .3, .28, yellow, 'PLEM skid runner');
            box(g, center.x, .4, center.z + z * .8, w * .78, .2, .18, yellow, 'PLEM longitudinal support');
          }
          for (const x of [-w * .32, 0, w * .32]) box(g, center.x + x, .38, center.z, .25, .2, skidDepth, yellow, 'PLEM skid cross member');
          for (const x of [-.45, .45]) {
            box(g, center.x + x, pipeHeight + .65, center.z, .22, 1.05, 1.05, yellow, 'PLEM central pipe clamp');
            for (const z of [-.48, .48]) beam(g, [center.x + x, .48, center.z + z],
              [center.x + x, pipeHeight + .65, center.z + z], .08, yellow, 'PLEM clamp support');
            for (const z of [-.42, .42]) cyl(g, center.x + x, pipeHeight + 1.23, center.z + z, .055, .16, dark, 'PLEM clamp bolt');
          }
          box(g, center.x, pipeHeight + .65, center.z, .65, .76, .85, yellow, 'PLEM central pressure housing');
          height = pipeHeight + 1.6;
        } else if (family === 'frame') protectiveHood(g, w * .92, d * .82, Math.max(1, Math.min(4, Math.ceil(w / 4))));
        else skid(g, w * .92, d * .82, false);
        if (['template', 'manifold'].includes(node.type)) {
          const count = Math.max(0, Math.min(24, Number(node.item.wells ?? node.item.slots ?? 4)));
          for (let i = 0; i < count; i++) {
            const x = -w * .35 + w * .7 * (i + .5) / Math.max(count, 1);
            if (node.type === 'template') tree(g, x, d * .25, node.item.treeType || 'vxt');
            else valve(g, x, 1.2, d * .15, 'gate', Math.PI / 2, .6);
          }
        }
        if (['compression_station', 'hydrate_skid', 'gl_manifold'].includes(node.type)) vessel(g, w * .5, Math.min(d * .18, .6));
      } else if (family === 'jacket') {
        height = Math.max(12, Math.min(30, d * 1.5)); pipeHeight = height + .45;
        const width = Math.max(w, 4), depth = Math.max(w * .8, 4);
        g.userData.deckWidth = width; g.userData.deckDepth = depth;
        const legPoint = (x, z, y) => [x * width * .4 * (1 - .28 * y / height), y, z * depth * .4 * (1 - .28 * y / height)];
        for (const x of [-1, 1]) for (const z of [-1, 1]) {
          beam(g, legPoint(x, z, 0), legPoint(x, z, height), .22, yellow, 'Jacket leg / pile');
          const foot = legPoint(x, z, 0);
          cyl(g, foot[0], .1, foot[2], .42, .5, yellow, 'Pile foundation sleeve');
        }
        for (let level = 0; level < 4; level++) {
          const low = level * height / 4, high = (level + 1) * height / 4;
          for (const z of [-1, 1]) {
            beam(g, legPoint(-1, z, low), legPoint(1, z, high), .1, yellow, 'Jacket diagonal brace');
            beam(g, legPoint(1, z, low), legPoint(-1, z, high), .1, yellow, 'Jacket cross brace');
            beam(g, legPoint(-1, z, high), legPoint(1, z, high), .12, yellow, 'Jacket horizontal brace');
          }
          for (const x of [-1, 1]) {
            beam(g, legPoint(x, -1, low), legPoint(x, 1, high), .1, yellow, 'Jacket side brace');
            beam(g, legPoint(x, 1, low), legPoint(x, -1, high), .1, yellow, 'Jacket side brace');
            beam(g, legPoint(x, -1, high), legPoint(x, 1, high), .12, yellow, 'Jacket horizontal brace');
          }
        }
        box(g, 0, height, 0, width * 1.35, .5, depth * 1.3, topside, 'Platform deck');
        guardrails(g, width * 1.35, depth * 1.3, height);
        for (const x of [-width * .34, width * .15]) {
          box(g, x, height + 1.35, -depth * .45, width * .28, 2.2, depth * .22, topside, 'Topside process module');
          box(g, x, height + 2.5, -depth * .45, width * .31, .15, depth * .25, topside, 'Topside module roof');
          for (let i = -1; i <= 1; i++) box(g, x + i * width * .07, height + 1.6, -depth * .335,
            width * .045, .4, .03, dark, 'Topside module window');
          box(g, x, height + .8, -depth * .335, width * .05, 1, .05, steel, 'Topside access door');
        }
        const process = new T.Group(); process.position.set(-width * .18, height + .25, depth * .49); g.add(process);
        vessel(process, width * .33, .35);
        box(process, 0, .25, 0, width * .45, .4, depth * .22, topside, 'Topside process skid');
        cyl(g, width * .08, height + 3.2, -depth * .45, .35, 5.8, topside, 'Tall process tower');
        for (let i = 0; i < 4; i++) cyl(g, width * .08, height + 1.5 + i * 1.3, -depth * .45, .48, .12, steel, 'Process tower collar');
        crane(g, new T.Vector3(width * .48, height + 1.7, depth * .42),
          new T.Vector3(width * 1.05, height + 8.5, depth * .42), height);
      } else if (family === 'jackup') {
        height = Math.max(12, Math.min(28, d)); pipeHeight = height + .45;
        const width = Math.max(w * .7, 5), depth = width * .72;
        g.userData.deckWidth = width; g.userData.deckDepth = depth;
        const legs = [[-width * .4, -depth * .32], [width * .4, -depth * .32], [0, depth * .42]];
        g.userData.legCenters = legs;
        for (const [x, z] of legs) {
          cyl(g, x, .22, z, width * .085, .45, dark, 'Jackup spudcan');
          const chords = [[-.32, -.2], [.32, -.2], [0, .35]], top = height + 5.5;
          for (const [dx, dz] of chords) beam(g, [x + dx, .4, z + dz], [x + dx, top, z + dz], .075, yellow, 'Jackup leg chord');
          for (let level = 0; level < 10; level++) for (let face = 0; face < 3; face++) {
            const a = chords[face], b = chords[(face + 1) % 3], low = .4 + level * (top - .4) / 10, high = .4 + (level + 1) * (top - .4) / 10;
            beam(g, [x + a[0], low, z + a[1]], [x + b[0], high, z + b[1]], .03, topside, 'Jackup leg diagonal');
            beam(g, [x + b[0], low, z + b[1]], [x + a[0], high, z + a[1]], .03, topside, 'Jackup leg cross brace');
          }
          box(g, x, height + .7, z, 1, 1.6, 1, topside, 'Jackup jacking house');
        }
        box(g, 0, height - .35, 0, width * 1.1, 1.2, depth * 1.15, topside, 'Jackup elevated hull');
        guardrails(g, width * 1.1, depth * 1.15, height + .25);
        box(g, -width * .24, height + 1.7, -depth * .12, width * .25, 2.7, depth * .42, whitePipe, 'Jackup accommodation');
        for (let i = 0; i < 4; i++) box(g, -width * .33 + i * width * .06, height + 2.25, depth * .095,
          width * .035, .4, .04, dark, 'Jackup bridge window');
        box(g, width * .52, height + .55, depth * .1, width * .65, .5, depth * .42, steel, 'Jackup drilling cantilever');
        const derrickX = width * .68, derrickZ = depth * .1;
        const point = (x, z, level) => [derrickX + x * width * (.12 - .085 * level), height + .85 + level * 8.5,
          derrickZ + z * width * (.12 - .085 * level)];
        for (const x of [-1, 1]) for (const z of [-1, 1]) beam(g, point(x, z, 0), point(x, z, 1), .07, topside, 'Jackup derrick chord');
        for (let level = 0; level < 7; level++) for (const side of [-1, 1]) {
          beam(g, point(-1, side, level / 7), point(1, side, (level + 1) / 7), .035, steel, 'Jackup derrick lattice');
          beam(g, point(side, -1, level / 7), point(side, 1, (level + 1) / 7), .035, steel, 'Jackup derrick lattice');
        }
        crane(g, new T.Vector3(-width * .4, height + 1.7, depth * .36),
          new T.Vector3(-width * .7, height + 6, depth * .36), height);
      } else if (['floating', 'tower'].includes(family)) {
        height = 16; pipeHeight = height;
        g.userData.deckWidth = Math.max(w, 4); g.userData.deckDepth = Math.max(w * .8, 3);
        if (node.type === 'fpso') {
          const breadth = Math.max(w * .21, 2.5), hullDepth = Math.max(w * .085, 1.5), radius = Math.max(.65, w * .045);
          const ship = new T.Group(); ship.name = 'FPSO vessel'; ship.scale.x = node.mirrored ? -1 : 1; g.add(ship);
          g.userData.deckDepth = breadth; g.userData.turretRadius = radius;
          g.userData.turretX = w * .24 * ship.scale.x;
          const turretBottom = height - hullDepth - .7;
          pipeHeight = height + .45;
          shipHull(ship, w, breadth, hullDepth, height);
          for (let i = 0; i < 4; i++) {
            const x = (i - 2) * w * .15;
            box(ship, x, height + 1.2, 0, w * .115, 2.1, breadth * .65, topside, 'FPSO process module');
            for (const y of [height + .35, height + 1.3, height + 2.35]) {
              box(ship, x, y, 0, w * .125, .1, breadth * .71, steel, 'FPSO process access platform');
            }
            for (const z of [-breadth * .24, breadth * .24]) {
              cyl(ship, x, height + 2.7, z, .24, 1.4, steel, 'FPSO vertical process vessel');
              for (let tier = 0; tier < 2; tier++) beam(ship, [x - w * .05, height + .8 + tier * .7, z],
                [x + w * .05, height + .8 + tier * .7, z], .06, whitePipe, 'FPSO module process piping');
            }
          }
          for (const z of [-breadth * .37, breadth * .37]) for (let run = 0; run < 3; run++) {
            beam(ship, [-w * .38, height + .45 + run * .2, z], [w * .22, height + .45 + run * .2, z],
              .055, whitePipe, 'FPSO longitudinal pipe rack');
          }
          box(ship, w * .34, height + 2.1, 0, w * .12, 4, breadth * .75, whitePipe, 'FPSO accommodation');
          box(ship, w * .34, height + 4.25, 0, w * .15, .65, breadth * .9, whitePipe, 'FPSO navigation bridge');
          for (const side of [-1, 1]) for (let row = 0; row < 4; row++) for (let column = 0; column < 4; column++) {
            box(ship, w * (.295 + column * .03), height + .9 + row * .9, side * breadth * .38,
              w * .013, .3, .04, dark, 'FPSO accommodation window');
          }
          box(ship, w * .418, height + 4.3, 0, .04, .35, breadth * .75, dark, 'FPSO bridge front glazing');
          for (const side of [-1, 1]) box(ship, w * .34, height + 4.3, side * breadth * .455, w * .13, .35, .04, dark, 'FPSO bridge side glazing');
          beam(ship, [w * .34, height + 4.6, 0], [w * .34, height + 6.7, 0], .045, steel, 'FPSO radar mast');
          beam(ship, [w * .31, height + 6.3, 0], [w * .37, height + 6.3, 0], .035, whitePipe, 'FPSO radar scanner');
          const helideck = cyl(ship, w * .34, height + 3.2, -breadth * .9, breadth * .37, .16, mat('#436559', .1), 'FPSO helideck');
          helideck.geometry = new T.CylinderGeometry(1, 1, 1, 8);
          for (const x of [-.15, .15]) box(ship, w * .34 + x * breadth, height + 3.29, -breadth * .9,
            .05, .02, breadth * .38, whitePipe, 'Helideck H marking');
          box(ship, w * .34, height + 3.29, -breadth * .9, breadth * .3, .02, .05, whitePipe, 'Helideck H marking');
          for (const x of [w * .27, w * .41]) beam(ship, [x, height + .2, -breadth * .32],
            [x, height + 3.1, -breadth * .9], .07, steel, 'FPSO helideck support');
          for (const x of [-w * .17, w * .1]) {
            cyl(ship, x, height + 3.5, -breadth * .18, .19, 2.8, topside, 'FPSO exhaust stack');
            cyl(ship, x, height + 4.95, -breadth * .18, .22, .2, dark, 'FPSO stack outlet');
          }
          crane(ship, new T.Vector3(-w * .39, height + 1.7, breadth * .3),
            new T.Vector3(-w * .48, height + 7.5, breadth * .6), height);
          cyl(ship, w * .24, height - hullDepth / 2 - .35, 0, radius, hullDepth + .7, steel, 'Turret and riser porch');
          cyl(ship, w * .24, height + .3, 0, radius * .7, .6, steel, 'FPSO turret topside header');
          for (const y of [turretBottom, height - hullDepth, height + .1]) {
            cyl(ship, w * .24, y, 0, radius * 1.08, .14, topside, 'FPSO turret collar');
          }
          for (let i = 0; i < 6; i++) {
            const angle = i * Math.PI / 3, start = new T.Vector3(w * .24, turretBottom + .2, 0);
            const end = start.clone().add(new T.Vector3(Math.cos(angle) * w * .9, -start.y + .4, Math.sin(angle) * w * .9));
            const curve = new T.CurvePath();
            curve.add(new T.CubicBezierCurve3(start, start.clone().lerp(end, .2).setY(start.y * .4),
              end.clone().lerp(start, .2).setY(.4), end));
            pipe(ship, curve, '#60676b', .035, 'none', { equipmentId: node.id, name: 'FPSO catenary mooring' });
            box(ship, end.x, .2, end.z, .65, .4, .65, dark, 'FPSO mooring anchor');
          }
        } else if (node.type === 'spar' || node.type === 'hrt') {
          cyl(g, 0, height / 2, 0, Math.max(w * .24, 1), height, paint, 'Buoyancy tower / spar hull');
          box(g, 0, height, 0, w, .6, Math.max(w, 3), steel, 'Tower topside deck');
        } else {
          for (const x of [-w * .35, w * .35]) for (const z of [-w * .35, w * .35]) cyl(g, x, height * .6, z, .8, height * .6, steel, 'Floating platform column');
          box(g, 0, height, 0, w, .6, Math.max(w, 4), paint, 'Floating unit deck');
          for (const x of [-w * .35, w * .35]) beam(g, [x, 3, -w * .35], [x, 3, w * .35], .55, dark, 'Submerged pontoon');
        }
        if (node.type !== 'fpso') for (const sign of [-1, 1]) beam(g, [sign * w * .4, height * .55, 0], [sign * w * 1.1, 0, w], .05, dark, 'Schematic mooring / tendon');
        if (node.type === 'wind') {
          beam(g, [0, height, 0], [0, height + 10, 0], .22, steel, 'Wind turbine tower');
          ball(g, 0, height + 10, 0, .4, paint, 'Turbine nacelle');
          for (let i = 0; i < 3; i++) {
            const a = i * Math.PI * 2 / 3;
            beam(g, [0, height + 10, 0], [Math.cos(a) * 5, height + 10 + Math.sin(a) * 5, 0], .13, steel, 'Rotor blade');
          }
        }
      } else if (family === 'tree') { skid(g, Math.max(w, 2.5), Math.max(d, 2.5), false); tree(g, 0, 0, node.item.treeType || node.type); }
      else if (family === 'valve') {
        skid(g, w, Math.min(d, 2.5), false);
        if (!node.valves.length) valve(g, 0, 1.2, 0, node.type.replace('valve_', ''), 0, Math.max(.65, Math.min(w / 2, 1.4)), !!node.item.closed);
      } else if (family === 'pump') {
        skid(g, w, Math.min(d, 4), false);
        cyl(g, 0, 1.4, 0, .55, w * .58, paint, node.type === 'wgc' ? 'Compressor casing' : 'Pump motor housing').rotation.z = Math.PI / 2;
        for (let i = 0; i < 7; i++) cyl(g, (i - 3) * w * .065, 1.4, 0, .61, .07, dark, 'Motor cooling / casing ring').rotation.z = Math.PI / 2;
        ball(g, w * .34, 1.4, 0, .65, steel, 'Pump volute / compressor end');
      } else if (family === 'vessel' || family === 'pig') {
        skid(g, w, Math.max(d, 2.5), false);
        vessel(g, w * .65, Math.max(.3, Math.min(d * .2, 1.3)), node.type === 'accumulator' || node.type === 'storage_tank');
        if (family === 'pig') { flange(g, w * .36, 1.5, 0, .7); valve(g, -w * .3, 1.5, 0, 'gate', 0, .8); }
      } else if (family === 'cooler') {
        skid(g, w, Math.max(d, 2.2), false);
        for (let i = 0; i < 8; i++) beam(g, [-w * .4, 1 + i * .11, -d * .25], [w * .4, 1 + i * .11, d * .25], .06, steel, 'Heat-exchange tube / treatment cartridge');
        for (const x of [-w * .43, w * .43]) box(g, x, 1.4, 0, .2, 1.2, d * .7, paint, 'Tube header plate');
      } else if (['control', 'electrical', 'terminal', 'custom-symbol'].includes(family)) {
        skid(g, w, Math.max(d, 2.2), false);
        box(g, 0, 1.2, 0, w * .7, 1.7, Math.max(d * .5, .8), family === 'terminal' ? topside : paint, 'Sealed module enclosure');
        box(g, 0, 2.12, 0, w * .76, .12, Math.max(d * .55, .9), steel, 'Removable bolted module lid');
        for (const sign of [-1, 1]) for (let i = 0; i < 4; i++) {
          cyl(g, (i - 1.5) * w * .16, 2.22, sign * d * .22, .05, .13, dark, 'Cover securing bolt');
          flange(g, (i - 1.5) * w * .16, 1, sign * d * .3, .15, new T.Vector3(0, 0, sign));
        }
        if (family === 'electrical') cyl(g, 0, 2.6, 0, .22, .7, steel, `${node.type} electrical interface`);
        if (node.type === 'transformer') for (let i = 0; i < 10; i++) {
          box(g, (i - 4.5) * w * .07, 1.2, d * .3, .08, 1.5, .3, steel, 'Transformer cooling fin');
        }
      } else if (family === 'instrument') {
        beam(g, [-w / 2, 1.2, 0], [w / 2, 1.2, 0], .2, steel, 'Instrument flow tube');
        box(g, 0, 1.55, 0, .6, .5, .55, paint, 'Sensor transmitter head');
        cyl(g, 0, 2, 0, .16, .3, dark, 'Wet-mate sensor connector');
      } else if (family === 'connector') {
        beam(g, [-w * .4, 1.2, 0], [w * .4, 1.2, 0], .23, steel, 'Connector flow bore');
        flange(g, -.2, 1.2, 0, .5); flange(g, .2, 1.2, 0, .5);
        if (node.type === 'wye_tee') beam(g, [0, 1.2, 0], [0, 1.2, 1.2], .2, steel, 'Tee branch');
      } else if (family === 'foundation') {
        if (node.type === 'suction_pile') {
          cyl(g, 0, 1.2, 0, Math.max(w * .3, .5), 2.4, steel, 'Suction caisson');
          cyl(g, 0, 2.45, 0, Math.max(w * .3, .5), .12, paint, 'Suction pile lid');
        } else if (node.type === 'buoyancy') {
          for (let i = -2; i <= 2; i++) cyl(g, i * w * .18, 1, 0, .4, .7, paint, 'Buoyancy module').rotation.z = Math.PI / 2;
        } else box(g, 0, .45, 0, w, .9, Math.max(d, 1), node.type === 'anode' ? steel : mat('#888d7c'), 'Support sleeper / sacrificial anode');
      } else if (family === 'seabed') {
        for (let x = 0; x < 5; x++) for (let z = 0; z < 3; z++) box(g, (x - 2) * w / 5, .22, (z - 1) * d / 3, w / 5 * .9, node.type === 'rockdump' ? .3 + .15 * Math.sin(x + z) : .35, d / 3 * .9, mat('#7c826f', .05), 'Concrete mattress block / rock protection');
      } else if (family === 'pipe' && !node.pipes.length) {
        if (!node.pipes.some((p) => p.anchors3D?.length))
          beam(g, [-w / 2, pipeHeight, 0], [w / 2, pipeHeight, 0], node.type === 'cable_power' || node.type === 'efl' ? .08 : .2, dark, 'Flowline / flying lead');
        flange(g, -w / 2, pipeHeight, 0); flange(g, w / 2, pipeHeight, 0);
      }
      if (['tree', 'valve', 'pump', 'vessel', 'cooler', 'control', 'pig', 'instrument'].includes(family)) {
        const top = new T.Box3().setFromObject(g).max.y;
        height = Math.max(3.4, top + .35);
        protectiveHood(g, w * .84, Math.max(1.5, Math.min(d * .8, w)), Math.max(1, Math.min(4, Math.ceil(w / 4))), height, false);
      }
      g.position.set(node.box.cx * UNIT, 0, node.box.cy * UNIT);
      g.userData.pipeHeight = pipeHeight; g.userData.height = height;
      return g;
    }
    let data, signature = '', active = false, request = 0, last = 0, phase = 0, mode = 'orbit', drag = null, contextLost = false;
    let models = new Map(), flows = [], labels = [], selection = null, renderedRoutes = [], selectedId = null;
    let editingIndex = null, connectionHandles = [];
    let equipmentRoutes = [], selectedRouteKey = null, selectedAnchor = -1, routePreview = null;
    let target = new T.Vector3(), radius = 60, phi = .9, theta = .6, fitted = false, labelVisible = false;
    const raycaster = new T.Raycaster(), pointer = new T.Vector2(), ground = new T.Plane(new T.Vector3(0, 1, 0), 0);
    function label(parent, text, x, y, z, width = 5) {
      const image = document.createElement('canvas'); image.width = 512; image.height = 96;
      const context = image.getContext('2d');
      context.fillStyle = '#092f40dc'; context.fillRect(0, 0, 512, 96);
      context.font = 'bold 28px Arial'; context.textAlign = 'center'; context.fillStyle = '#edfaff';
      let caption = String(text);
      if (context.measureText(caption).width > 480) {
        while (caption.length && context.measureText(caption + '...').width > 480) caption = caption.slice(0, -1);
        caption += '...';
      }
      context.fillText(caption, 256, 59);
      const texture = new T.CanvasTexture(image); texture.colorSpace = T.SRGBColorSpace;
      const material = new T.SpriteMaterial({ map: texture, depthTest: false, sizeAttenuation: false }); owned.add(material);
      const scale = Math.max(.15, Math.min(width * .03, .27));
      const sprite = new T.Sprite(material); sprite.position.set(x, y, z); sprite.scale.set(scale, scale * 96 / 512, 1);
      sprite.visible = labelVisible; sprite.name = 'Equipment label'; sprite.userData.caption = caption;
      parent.add(sprite); labels.push(sprite); return sprite;
    }
    function disposeOwned(group) {
      group.traverse((part) => {
        if (part.geometry && !Object.values(geometries).includes(part.geometry)) part.geometry.dispose();
        if (owned.has(part.material)) { part.material.map?.dispose(); part.material.dispose(); owned.delete(part.material); }
      });
      group.clear();
    }
    const world = (p, y = 1.2) => new T.Vector3(p.x * UNIT, y, p.y * UNIT);
    const anchorWorld = (p) => world(p, p.elevation3D ?? .65);
    const anchorData = (p) => ({ x: p.x / UNIT, y: p.z / UNIT, elevation3D: p.y });
    const routeAnchors = (route) => {
      const anchors = routePreview?.routeKey === route.routeKey ? routePreview.anchors : route.waypoints ?? [];
      if (!Array.isArray(anchors) || anchors.some((p) => !p || !Number.isFinite(p.x) || !Number.isFinite(p.y)
        || p.elevation3D !== undefined && !Number.isFinite(p.elevation3D))) throw new Error('Invalid 3D anchor coordinates: use finite numbers.');
      return anchors;
    };
    const lineRoutes = () => [...renderedRoutes, ...equipmentRoutes];
    function borePoint(node, point, height, lane) {
      const position = world(point, height);
      if (node.type === 'plem' && lane === 'P') {
        const bore = node.pipes.find((p) => p.lane === 'P');
        if (bore) {
          const a = world(bore.points[0], height), vector = world(bore.points.at(-1), height).sub(a);
          if (vector.lengthSq()) {
            const along = Math.max(0, Math.min(1, position.clone().sub(a).dot(vector) / vector.lengthSq()));
            position.y += .65 * Math.sin(Math.PI * along) ** 2;
          }
        }
      }
      return position;
    }
    function roundedCurve(points, bend) {
      const clean = [];
      for (const p of points) {
        if (clean.length && p.distanceTo(clean.at(-1)) < .0001) continue;
        if (clean.length > 1) {
          const a = clean.at(-1).clone().sub(clean.at(-2)).normalize(), b = p.clone().sub(clean.at(-1)).normalize();
          if (a.dot(b) > .99999) clean.pop();
        }
        clean.push(p);
      }
      const curve = new T.CurvePath();
      if (clean.length < 2) return curve;
      let current = clean[0];
      for (let i = 1; i < clean.length - 1; i++) {
        const p = clean[i], before = p.clone().sub(clean[i - 1]), after = clean[i + 1].clone().sub(p);
        const trim = Math.min(bend, before.length() * .35, after.length() * .35);
        before.normalize(); after.normalize();
        if (Math.abs(before.dot(after)) > .99999) {
          curve.add(new T.LineCurve3(current, p)); current = p; continue;
        }
        const a = p.clone().addScaledVector(before, -trim), b = p.clone().addScaledVector(after, trim);
        if (current.distanceTo(a) > .0001) curve.add(new T.LineCurve3(current, a));
        curve.add(new T.QuadraticBezierCurve3(a, p, b)); current = b;
      }
      if (current.distanceTo(clean.at(-1)) > .0001) curve.add(new T.LineCurve3(current, clean.at(-1)));
      return curve;
    }
    function reverseCurve(curve) {
      const reversed = new T.CurvePath();
      for (const c of [...curve.curves].reverse()) {
        if (c.isLineCurve3) reversed.add(new T.LineCurve3(c.v2, c.v1));
        else if (c.isCubicBezierCurve3) reversed.add(new T.CubicBezierCurve3(c.v3, c.v2, c.v1, c.v0));
        else reversed.add(new T.QuadraticBezierCurve3(c.v2, c.v1, c.v0));
      }
      return reversed;
    }
    function jTubeCurve(deck, side, bend) {
      const curve = new T.CurvePath(), floor = Math.min(.65, deck.y / 2);
      bend = Math.min(bend, deck.y - floor);
      const start = new T.Vector3(deck.x, floor + bend, deck.z), mouth = new T.Vector3(deck.x + side * bend, floor, deck.z);
      curve.add(new T.LineCurve3(deck, start));
      curve.add(new T.CubicBezierCurve3(start, start.clone().add(new T.Vector3(0, -bend * .55228475, 0)),
        mouth.clone().add(new T.Vector3(-side * bend * .55228475, 0, 0)), mouth));
      return { curve, mouth };
    }
    function hostPorts(node, g) {
      const host = node.ports.filter((p) => p.hostSlot);
      const named = host.filter((p) => /^J-(\d+)$/.test(p.id));
      const slotNumber = (p) => {
        const match = /^J-(\d+)$/.exec(p.id);
        if (match) return +match[1];
        const nearest = named.reduce((best, candidate) => !best || Math.hypot(candidate.x - p.x, candidate.y - p.y)
          < Math.hypot(best.x - p.x, best.y - p.y) ? candidate : best, null);
        return nearest ? +/^J-(\d+)$/.exec(nearest.id)[1] : ['P-right', 'S-right', 'U-right'].indexOf(p.id);
      };
      const slots = [...new Set(host.map(slotNumber))].sort((a, b) => a - b), result = new Map(), physical = new Map();
      const factor = g.userData.scale3D, width = g.userData.deckWidth, depth = g.userData.deckDepth,
        side = (node.item.jTubeSide === 'right' ? 1 : -1) * (node.mirrored ? -1 : 1);
      for (const p of host) {
        const slot = slotNumber(p);
        if (!physical.has(slot)) {
          const z = (g.userData.turretRadius ? g.userData.turretRadius * 1.1 : depth * .5)
            * ((slots.indexOf(slot) + .5) / slots.length - .5);
          const localDeck = new T.Vector3(g.userData.turretX ?? side * width * .34, g.userData.pipeHeight, z);
          const deck = localDeck.clone().add(g.position), bend = Math.min(factor, width * .1, g.userData.pipeHeight * .08);
          const guide = jTubeCurve(deck, side, bend);
          const attachment = { host: true, deck, point: deck, mouth: guide.mouth, curve: guide.curve,
            normal: new T.Vector3(side, 0, 0), slot, scale3D: factor };
          physical.set(slot, attachment);
          if (node.item.showJTubes) {
            const local = jTubeCurve(localDeck, side, bend);
            pipe(g, local.curve, '#a7adb3', .18 * factor, 'none', { equipmentId: node.id, name: 'Riser guide / J-tube' }, guideMaterial);
            flange(g, localDeck.x, localDeck.y, localDeck.z, .27 * factor, new T.Vector3(0, 1, 0));
            flange(g, local.mouth.x, local.mouth.y, local.mouth.z, .27 * factor, new T.Vector3(side, 0, 0));
            if (['jacket', 'jackup'].includes(g.userData.family)) for (let level = 1; level <= 3; level++) {
              const t = level / 4, y = g.userData.height * t;
              const leg = g.userData.legCenters?.reduce((best, p) => !best || Math.hypot(p[0] - localDeck.x, p[1] - z)
                < Math.hypot(best[0] - localDeck.x, best[1] - z) ? p : best, null);
              beam(g, [localDeck.x, y, z], leg ? [leg[0], y, leg[1]] : [side * width * (.4 - .112 * t), y,
                (z < 0 ? -1 : 1) * depth * (.4 - .112 * t)], .05 * factor, steel, 'J-tube jacket support bracket');
            }
          } else flange(g, localDeck.x, localDeck.y, localDeck.z, .25 * factor, new T.Vector3(0, 1, 0));
        }
        result.set(p.id, physical.get(slot));
      }
      g.userData.attachments = result;
    }
    function endpoint(id, portId, fallback, openHeight = .65) {
      const node = data.nodes.find((n) => n.id === id), g = models.get(id);
      const port = node?.ports.find((p) => p.id === portId) || node?.ports.find((p) => Math.hypot(p.x - fallback.x, p.y - fallback.y) < .1);
      const attached = g?.userData.attachments?.get(port?.id);
      if (attached) return attached;
      return { point: g?.userData.ports?.get(port?.id)?.clone() || world(fallback, g?.userData.pipeHeight ?? openHeight),
        normal: port?.axis === 'y' ? new T.Vector3(0, 0, port.direction) : new T.Vector3(port?.direction || 1, 0, 0) };
    }
    function floorCurve(start, end, waypoints, startNormal, endNormal) {
      const a = start.clone().setY(.65), b = end.clone().setY(.65);
      const stub = a.clone().addScaledVector(startNormal, .9), approach = b.clone().addScaledVector(endNormal, .9);
      const middle = waypoints?.length ? waypoints.map(anchorWorld)
        : [new T.Vector3(stub.x, .65, approach.z)];
      return roundedCurve([start, a, stub, ...middle, approach, b, end], .45);
    }
    function routeCurve(route) {
      const a = endpoint(route.from, route.fromPort, route.points[0], route.implicit ? 1.2 : .65),
        b = endpoint(route.to, route.toPort, route.points.at(-1), route.implicit ? 1.2 : .65);
      const curve = new T.CurvePath();
      if (a.host && b.host) {
        a.curve.curves.forEach((c) => curve.add(c));
        floorCurve(a.mouth, b.mouth, route.waypoints, a.normal, b.normal).curves.forEach((c) => curve.add(c));
        reverseCurve(b.curve).curves.forEach((c) => curve.add(c));
      } else if (a.host || b.host) {
        const host = a.host ? a : b, target = a.host ? b : a;
        const node = data.nodes.find((n) => n.id === (a.host ? route.from : route.to));
        const style = route.style || 'rigid';
        if (style !== 'rigid' && !['jacket', 'jackup'].includes(families[node.type]) && !node.item.showJTubes && !route.waypoints?.length) {
          const deck = host.deck, end = target.point, direction = end.clone().sub(deck).setY(0), length = direction.length();
          direction.normalize();
          const height = deck.y - end.y;
          const first = deck.clone().setY(end.y + height * .25), last = end.clone().addScaledVector(target.normal, Math.min(length * .25, 5));
          if (style === 'lazywave' || style === 's_shape') {
            const sag = deck.clone().lerp(end, .38).setY(end.y + height * (style === 'lazywave' ? .12 : .55));
            curve.add(new T.CubicBezierCurve3(deck, first, sag.clone().addScaledVector(direction, -length * .12), sag));
            if (style === 'lazywave') {
              const crest = deck.clone().lerp(end, .68).setY(end.y + height * .32);
              curve.add(new T.CubicBezierCurve3(sag, sag.clone().addScaledVector(direction, length * .12),
                crest.clone().addScaledVector(direction, -length * .1), crest));
              curve.add(new T.CubicBezierCurve3(crest, crest.clone().addScaledVector(direction, length * .12), last, end));
            } else curve.add(new T.CubicBezierCurve3(sag, sag.clone().addScaledVector(direction, length * .15), last, end));
          } else curve.add(new T.CubicBezierCurve3(deck, first, last, end));
        } else {
          host.curve.curves.forEach((c) => curve.add(c));
          const waypoints = a.host ? route.waypoints : route.waypoints ? [...route.waypoints].reverse() : undefined;
          floorCurve(host.mouth, target.point, waypoints, host.normal, target.normal).curves.forEach((c) => curve.add(c));
        }
        return { curve: a.host ? curve : reverseCurve(curve), a, b };
      } else if (route.autoBridge) {
        roundedCurve([a.point, ...(route.waypoints || []).map(anchorWorld), b.point], .4).curves.forEach((c) => curve.add(c));
      } else if (!route.implicit && (route.style === 'flex' || route.waypoints?.length)) {
        floorCurve(a.point, b.point, route.waypoints, a.normal, b.normal).curves.forEach((c) => curve.add(c));
      } else {
        const points = route.points.map((p) => world(p, route.implicit ? 1.2 : .65));
        if (route.implicit) {
          const routed = route.waypoints?.length ? [a.point, ...route.waypoints.map(anchorWorld), b.point] : points;
          routed[0] = a.point; routed[routed.length - 1] = b.point;
          roundedCurve(routed, .4).curves.forEach((c) => curve.add(c));
        } else {
          const floorA = points[0], floorB = points.at(-1);
          roundedCurve([a.point, floorA, ...points.slice(1, -1), floorB, b.point], .4).curves.forEach((c) => curve.add(c));
        }
      }
      return { curve, a, b };
    }
    function pipe(parent, shape, color, radius, flow = 'none', owner = {}, material = mat(color)) {
      const curve = Array.isArray(shape) ? roundedCurve(shape, radius * 3) : shape;
      if (!curve.curves.length) return null;
      const assembly = new T.Group(); assembly.name = owner.name || 'Connected piping / cable'; assembly.userData = owner; parent.add(assembly);
      for (const segment of curve.curves) {
        const tube = new T.Mesh(new T.TubeGeometry(segment, segment.isLineCurve3 ? 1 : 32, radius, 12, false), material);
        tube.castShadow = !material.transparent; tube.receiveShadow = true; assembly.add(tube);
      }
      if (flow !== 'none') {
        const particles = [];
        for (let i = 0; i < 5; i++) {
          const p = mesh(assembly, 'sphere', 0, 0, 0, radius * 1.25, radius * 1.25, radius * 1.25, mat('#bff5ff', .1), 'Schematic flow pulse');
          p.castShadow = false; p.userData = owner; p.position.copy(curve.getPointAt(i / 5)); particles.push(p);
        }
        flows.push({ curve, particles, reverse: flow === 'reverse', length: curve.getLength(), connectionIndex: owner.connectionIndex,
          externalRoute: !!owner.externalRoute });
      }
      return curve;
    }
    function makeEnvironment() {
      disposeOwned(environment);
      const bounds = new T.Box3().setFromObject(stage), center = bounds.isEmpty() ? new T.Vector3() : bounds.getCenter(new T.Vector3());
      const size = bounds.isEmpty() ? new T.Vector3(50, 0, 50) : bounds.getSize(new T.Vector3());
      const extent = Math.max(size.x, size.z, 30) + 80;
      const image = document.createElement('canvas'); image.width = image.height = 256;
      const context = image.getContext('2d'), pixels = context.createImageData(256, 256);
      let seed = 38219;
      const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
      for (let i = 0; i < pixels.data.length; i += 4) {
        const value = 108 + random() * 14;
        pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value; pixels.data[i + 3] = 255;
      }
      context.putImageData(pixels, 0, 0);
      const texture = new T.CanvasTexture(image); texture.wrapS = texture.wrapT = T.RepeatWrapping; texture.repeat.set(extent / 8, extent / 8);
      const material = new T.MeshStandardMaterial({ map: texture, roughness: .98, color: '#34383c' }); owned.add(material);
      const corridors = renderedRoutes.flatMap((route) => {
        const points = route.curve.getPoints(24);
        return points.slice(1).map((b, i) => ({ a: points[i], b }));
      });
      const amplitude = Math.max(4, Math.min(15, extent * .055));
      const elevation = (x, z) => {
        let clearance = Infinity;
        for (const node of data.nodes) {
          const factor = models.get(node.id).userData.scale3D;
          const dx = Math.max(0, Math.abs(x - node.box.cx * UNIT) - node.box.width * UNIT * factor * .6 - 1),
            dz = Math.max(0, Math.abs(z - node.box.cy * UNIT) - node.box.height * UNIT * factor * .6 - 1);
          clearance = Math.min(clearance, Math.hypot(dx, dz));
        }
        for (const { a, b } of corridors) {
          const dx = b.x - a.x, dz = b.z - a.z, length = dx * dx + dz * dz;
          const t = length ? Math.max(0, Math.min(1, ((x - a.x) * dx + (z - a.z) * dz) / length)) : 0;
          clearance = Math.min(clearance, Math.max(0, Math.hypot(x - a.x - t * dx, z - a.z - t * dz) - 1));
        }
        const u = Math.min(1, clearance / 6), blend = u * u * (3 - 2 * u);
        const lx = (x - center.x) / extent, lz = (z - center.z) / extent;
        const channel = Math.exp(-(((lz - .18 * Math.sin(lx * 7)) / .13) ** 2));
        const relief = .25 + .12 * Math.sin(lx * 15 + lz * 7) + .1 * Math.cos(lz * 19) + .65 * channel;
        return -.2 - amplitude * relief * blend;
      };
      const plane = new T.PlaneGeometry(extent, extent, 96, 96), positions = plane.attributes.position;
      for (let i = 0; i < positions.count; i++) positions.setZ(i, elevation(center.x + positions.getX(i), center.z - positions.getY(i)));
      plane.computeVertexNormals();
      const seabed = new T.Mesh(plane, material); seabed.rotation.x = -Math.PI / 2; seabed.position.set(center.x, 0, center.z); seabed.receiveShadow = true; seabed.name = 'Illustrative NCS seabed'; environment.add(seabed);
      const dust = new Float32Array(500 * 3);
      for (let i = 0; i < dust.length; i += 3) { dust[i] = center.x + (random() - .5) * extent; dust[i + 1] = random() * 25; dust[i + 2] = center.z + (random() - .5) * extent; }
      const geometry = new T.BufferGeometry(); geometry.setAttribute('position', new T.BufferAttribute(dust, 3));
      const dustMat = new T.PointsMaterial({ color: '#aaaaaa', size: .09, transparent: true, opacity: .15 }); owned.add(dustMat);
      const specks = new T.Points(geometry, dustMat); specks.name = 'Suspended underwater sediment'; environment.add(specks);
      sun.target.position.copy(center); sun.position.set(center.x + 40, 110, center.z - 30);
      const shadow = Math.max(extent / 2, 40); Object.assign(sun.shadow.camera, { left: -shadow, right: shadow, top: shadow, bottom: -shadow, far: 500 }); sun.shadow.camera.updateProjectionMatrix();
    }
    function rebuild() {
      selection?.material.dispose();
      disposeOwned(stage); models.clear(); flows = []; labels = []; selection = null; drag = null; renderedRoutes = [];
      for (const node of data.nodes) {
        const factor = node.scale3D === undefined ? 1 : node.scale3D;
        if (!Number.isFinite(factor) || factor < .01) throw new Error(`Invalid 3D size for ${node.id}: use at least 1%.`);
        const g = model(node); models.set(node.id, g); stage.add(g);
        const height = g.userData.pipeHeight;
        g.userData.pipePaths = []; g.userData.ports = new Map();
        for (const route of node.pipes) {
          const material = node.type === 'plem' && route.lane === 'P' ? whitePipe : mat(route.color);
          const points = route.points.map((p) => borePoint(node, p, height, route.lane).sub(g.position));
          const radius = Math.max(.045, Math.min(route.width * UNIT, .14));
          const curve = families[node.type] === 'pipe' && route.anchors3D?.length ? roundedCurve(points, radius * 3)
            : pipe(g, points, route.color, radius, route.flow, { equipmentId: node.id,
              ...(families[node.type] === 'pipe' ? { routeKey: route.routeKey } : {}) }, material);
          if (curve) g.userData.pipePaths.push({ id: route.id, curve, color: material.color });
        }
        for (const hub of node.ports) {
          if (hub.hostSlot) continue;
          const point = borePoint(node, hub, hub.tubeMouth ? .65 : height, hub.lane);
          g.userData.ports.set(hub.id, point);
          const p = point.clone().sub(g.position);
          const axis = hub.axis === 'y' ? new T.Vector3(0, 0, hub.direction) : new T.Vector3(hub.direction, 0, 0);
          flange(g, p.x, p.y, p.z, .22, axis);
        }
        for (const v of node.valves) {
          const lane = node.pipes.find((p) => p.id === v.pipe)?.lane;
          const p = borePoint(node, v.point, height, lane).sub(g.position);
          const assembly = valve(g, p.x, p.y, p.z, v.kind, -v.angle, node.item.riserDetail ? .45 : .65, v.closed);
          if (node.type === 'plem') {
            const before = { x: v.point.x - Math.cos(v.angle) * .1, y: v.point.y - Math.sin(v.angle) * .1 },
              after = { x: v.point.x + Math.cos(v.angle) * .1, y: v.point.y + Math.sin(v.angle) * .1 };
            const tangent = borePoint(node, after, height, lane).sub(borePoint(node, before, height, lane)).normalize();
            assembly.quaternion.setFromUnitVectors(new T.Vector3(1, 0, 0), tangent);
          }
        }
        if (node.item.riserDetail) for (const shape of node.item.riserDetail.shapes || []) {
          const origin = node.detailOrigin;
          const position = world({ x: origin.x + shape.x * origin.scaleX, y: origin.y + shape.y * origin.scaleY }, .7).sub(g.position);
          const width = (shape.width || 0) * origin.scaleX * UNIT, depth = (shape.height || 0) * origin.scaleY * UNIT;
          const color = shape.fill && shape.fill !== 'none' ? shape.fill : shape.stroke || '#667e85';
          if (shape.kind === 'rect') box(g, position.x + width / 2, .65, position.z + depth / 2,
            Math.abs(width), .5, Math.abs(depth), mat(color), 'Custom drawn rectangular assembly');
          else if (shape.kind === 'ellipse') {
            const part = cyl(g, position.x + width / 2, .8, position.z + depth / 2, 1, 1.2, mat(color), 'Custom drawn cylindrical assembly');
            part.scale.x = Math.abs(width) / 2; part.scale.z = Math.abs(depth) / 2;
          } else if (shape.kind === 'line') {
            const end = world({ x: origin.x + shape.x2 * origin.scaleX, y: origin.y + shape.y2 * origin.scaleY }, .7).sub(g.position);
            beam(g, position.toArray(), end.toArray(), .04, mat(color), 'Decorative custom line (not a connection)');
          } else label(g, shape.text, position.x, 3.2, position.z, Math.max(shape.fontSize * .15, 2));
        }
        g.userData.scale3D = factor;
        for (const child of g.children) {
          child.position.multiplyScalar(factor); child.scale.multiplyScalar(factor);
        }
        for (const point of g.userData.ports.values()) point.sub(g.position).multiplyScalar(factor).add(g.position);
        for (const key of ['height', 'pipeHeight', 'deckWidth', 'deckDepth', 'turretX', 'turretRadius']) {
          if (g.userData[key] !== undefined) g.userData[key] *= factor;
        }
        if (g.userData.legCenters) g.userData.legCenters = g.userData.legCenters.map((p) => p.map((v) => v * factor));
        if (node.topside) hostPorts(node, g);
        label(g, [node.item.tag, node.item.label ?? node.name].filter(Boolean).join(' / '), 0, g.userData.height + 1.5, 0, Math.max(3.5, Math.min(node.box.width * UNIT * factor, 9)));
      }
      renderExternalRoutes();
      for (const zone of data.zones) {
        const a = world({ x: zone.left, y: zone.y }, .15), b = world({ x: zone.right, y: zone.y }, .15);
        beam(stage, a.toArray(), b.toArray(), .025, mat('#acd9e0', .1), 'Schematic zone boundary');
        label(stage, zone.label, (a.x + b.x) / 2, .9, a.z, 6);
      }
      makeEnvironment(); highlight(data.selected);
      if (!fitted) fit();
      refreshConnectionHandles();
    }
    function renderExternalRoutes() {
      for (const group of [...stage.children]) if (group.userData.externalRoute) {
        disposeOwned(group); stage.remove(group);
      }
      flows = flows.filter((flow) => !flow.externalRoute); renderedRoutes = []; equipmentRoutes = [];
      for (const original of data.routes) {
        const route = { ...original, waypoints: routeAnchors(original) };
        const { curve, a, b } = routeCurve(route);
        pipe(stage, curve, route.color, Math.max(.045, Math.min(route.width * UNIT, a.host || b.host ? .11 : .14)), route.flow,
          { connectionIndex: route.index, routeKey: route.routeKey, externalRoute: true });
        renderedRoutes.push({ routeKey: route.routeKey, waypoints: route.waypoints, index: route.index, style: route.style || 'rigid', curve, from: a.point, to: b.point,
          anchorStart: a.host ? a.mouth : a.point, anchorEnd: b.host ? b.mouth : b.point,
          label: `${route.from || 'Open end'} -> ${route.to || 'Open end'} / ${route.lane || 'P'}`,
          fromId: route.from, toId: route.to, fromPort: route.fromPort, toPort: route.toPort,
          lane: route.lane, autoBridge: !!route.autoBridge });
        if (route.psv && route.kind === 'riser') {
          const host = a.host ? a : b.host ? b : null;
          const p = host ? host.deck : curve.getPointAt((route.psvPosition ?? 50) / 100);
          const psv = valve(stage, p.x, p.y, p.z, 'psv', 0, .5 * (host?.scale3D ?? 1));
          psv.userData.externalRoute = true;
        }
      }
      for (const node of data.nodes.filter((n) => families[n.type] === 'pipe')) {
        const g = models.get(node.id);
        const hasAnchors = node.pipes.some((p) => routeAnchors({ routeKey: p.routeKey, waypoints: p.anchors3D }).length);
        for (const part of g.children) {
          if (part.name === 'Flowline / flying lead') part.visible = !hasAnchors;
          if (part.userData.routeKey) {
            const source = node.pipes.find((p) => p.routeKey === part.userData.routeKey);
            part.visible = !routeAnchors({ routeKey: source.routeKey, waypoints: source.anchors3D }).length;
          }
        }
        for (const source of node.pipes) {
          const path = g.userData.pipePaths.find((p) => p.id === source.id);
          if (!path) continue;
          const points = path.curve.getPoints(32).map((p) => p.multiplyScalar(g.userData.scale3D).add(g.position));
          const waypoints = routeAnchors({ routeKey: source.routeKey, waypoints: source.anchors3D });
          const curve = roundedCurve(waypoints.length ? [points[0], ...waypoints.map(anchorWorld), points.at(-1)] : points, .4);
          if (waypoints.length) pipe(stage, curve, source.color, Math.max(.045, Math.min(source.width * UNIT, .14)) * g.userData.scale3D, source.flow,
            { routeKey: source.routeKey, externalRoute: true });
          equipmentRoutes.push({ routeKey: source.routeKey, waypoints, curve, from: points[0], to: points.at(-1),
            anchorStart: points[0], anchorEnd: points.at(-1), lane: source.lane, equipmentId: node.id,
            label: `${node.item.tag || node.id} / ${source.lane} / ${source.id}` });
        }
      }
    }
    function highlight(id) {
      selectedId = id;
      if (selection) { stage.remove(selection); selection.geometry.dispose(); selection.material.dispose(); selection = null; }
      const selected = models.get(id);
      $('#scene3d-focus').disabled = !selected;
      if (selected) { selection = new T.BoxHelper(selected, '#8edfff'); selection.name = '3D selection outline'; stage.add(selection); }
      const node = data.nodes.find((n) => n.id === id);
      info.textContent = node ? `${node.item.tag || node.id} | ${node.name} | ${node.item.provider || 'Provider unspecified'} | ${node.item.rating || 'Rating unspecified'} | Procedural, NOT TO SCALE`
        : `${data.nodes.length} equipment | ${data.routes.length} routes | Illustrative NCS scene, NOT TO SCALE. Orbit: drag; pan: right-drag; zoom: wheel.`;
    }
    function cameraUpdate() {
      camera.position.set(target.x + radius * Math.sin(phi) * Math.sin(theta), target.y + radius * Math.cos(phi), target.z + radius * Math.sin(phi) * Math.cos(theta));
      camera.near = Math.max(.00001, Math.min(.05, radius * .001));
      camera.far = Math.max(500, radius + camera.position.distanceTo(stage.position) + 500);
      camera.updateProjectionMatrix();
      scene.fog.density = Math.min(.002, .14 / Math.max(radius, .1));
      camera.lookAt(target); camera.updateMatrixWorld();
      sizeConnectionHandles();
    }
    function fit(object = stage) {
      const bounds = new T.Box3().setFromObject(object);
      if (bounds.isEmpty()) { target.set(0, 1, 0); radius = 45; }
      else {
        target.copy(bounds.getCenter(new T.Vector3()));
        const fov = Math.min(camera.fov * Math.PI / 180, 2 * Math.atan(Math.tan(camera.fov * Math.PI / 360) * camera.aspect));
        radius = Math.max(bounds.getSize(new T.Vector3()).length() / 2, .15) / Math.sin(fov / 2) * 1.1;
      }
      fitted = true; cameraUpdate();
    }
    function zoom(factor, anchor) {
      if (!Number.isFinite(factor) || factor <= 0 || !Number.isFinite(radius * factor)) throw new Error('Invalid 3D zoom factor.');
      const next = Math.max(.0001, radius * factor), ratio = next / radius;
      if (anchor) target.lerp(anchor, 1 - ratio);
      radius = next; cameraUpdate();
    }
    function resize() {
      const w = Math.max(container.clientWidth, 1), h = Math.max(container.clientHeight, 1);
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); cameraUpdate();
      positionAnchorPanel();
    }
    const observer = new ResizeObserver(resize); observer.observe(container);
    function frame(now) {
      if (!active) return;
      // The first RAF timestamp can precede initialization within that same frame.
      const elapsed = Math.max(0, Math.min((now - last) / 1000, .05)); last = now;
      if (data?.animate) phase += elapsed * (data.speed || 1);
      for (const flow of flows) flow.particles.forEach((p, i) => {
        p.visible = !!data?.animate;
        const at = (phase * 3 / Math.max(flow.length, 3) + i / flow.particles.length) % 1;
        p.position.copy(flow.curve.getPointAt(flow.reverse ? 1 - at : at));
      });
      selection?.update(); renderer.render(scene, camera); request = requestAnimationFrame(frame);
    }
    function ray(event) {
      const box = canvas.getBoundingClientRect();
      pointer.set((event.clientX - box.left) / box.width * 2 - 1, 1 - (event.clientY - box.top) / box.height * 2);
      raycaster.setFromCamera(pointer, camera);
    }
    function screenPoint(point) {
      const p = point.clone().project(camera);
      return { x: (p.x + 1) * container.clientWidth / 2, y: (1 - p.y) * container.clientHeight / 2, z: p.z };
    }
    function handleMaterial(color) {
      const key = 'handle:' + color;
      if (!materials.has(key)) materials.set(key, new T.MeshBasicMaterial({ color, depthTest: false, depthWrite: false }));
      return materials.get(key);
    }
    function refreshConnectionHandles() {
      disposeOwned(editing); connectionHandles = [];
      editing.visible = mode === 'connect' || mode === 'anchor-mode';
      $('#scene3d-anchors').hidden = mode !== 'anchor-mode';
      fillAnchorPanel();
      if (!editing.visible) return;
      const add = (point, descriptor) => {
        const color = descriptor.kind === 'insert' ? '#65ff92' : descriptor.lane === 'S' ? '#ff9900' : descriptor.lane === 'U' ? '#a1b4cb' : descriptor.lane === 'any' ? '#ffffff' : '#b25bff';
        const mesh = new T.Mesh(descriptor.kind === 'bend' ? geometries.box : geometries.torus, handleMaterial(color));
        mesh.userData.baseMaterial = mesh.material;
        mesh.position.copy(point); mesh.renderOrder = 20;
        editing.add(mesh); connectionHandles.push({ ...descriptor, point: point.clone(), mesh });
      };
      if (mode === 'connect') for (const node of data.nodes) for (const port of node.ports) {
        if (port.hostSlot && !port.id.startsWith('J-')) continue;
        add(endpoint(node.id, port.id, port).point, { kind: 'port', id: node.id, port: port.id, lane: port.lane, label: port.label || port.id });
      }
      for (const route of lineRoutes()) {
        if (mode === 'connect' && !Number.isInteger(route.index) || mode === 'anchor-mode' && route.routeKey !== selectedRouteKey) continue;
        if (route.waypoints?.length) route.waypoints.forEach((p, index) =>
          add(anchorWorld(p), { kind: 'bend', routeKey: route.routeKey, index: route.index, waypointIndex: index, lane: route.lane }));
        else if (mode === 'connect') add(route.curve.curves.length ? route.curve.getPointAt(.5) : route.from,
          { kind: 'bend', routeKey: route.routeKey, index: route.index, waypointIndex: 0, lane: route.lane });
        if (mode === 'anchor-mode') {
          const points = [route.anchorStart, ...(route.waypoints || []).map(anchorWorld), route.anchorEnd];
          for (let i = 0; i < points.length - 1; i++) add(points[i].clone().lerp(points[i + 1], .5),
            { kind: 'insert', routeKey: route.routeKey, index: route.index, waypointIndex: i, lane: route.lane });
        }
        if (mode === 'connect' && route.index === editingIndex) for (const end of ['from', 'to'])
          add(route[end], { kind: 'endpoint', index: route.index, end, lane: route.lane });
      }
      sizeConnectionHandles();
    }
    function fillAnchorPanel() {
      if (mode !== 'anchor-mode') return;
      positionAnchorPanel();
      const routes = lineRoutes(), list = $('#scene3d-route');
      if (!routes.some((r) => r.routeKey === selectedRouteKey)) { selectedRouteKey = routes[0]?.routeKey || null; selectedAnchor = -1; }
      list.replaceChildren(...routes.map((r) => new Option(r.label, r.routeKey, false, r.routeKey === selectedRouteKey)));
      const route = routes.find((r) => r.routeKey === selectedRouteKey), anchors = route?.waypoints || [];
      selectedAnchor = anchors.length ? Math.max(0, Math.min(selectedAnchor, anchors.length - 1)) : -1;
      const select = $('#scene3d-anchor');
      select.replaceChildren(...(anchors.length ? anchors.map((p, i) => new Option(`Anchor ${i + 1}`, String(i), false, i === selectedAnchor))
        : [new Option('No anchors', '-1')]));
      select.disabled = !anchors.length;
      for (const [id, field, fallback] of [['x', 'x', 0], ['y', 'y', 0], ['height', 'elevation3D', .65]]) {
        const input = $('#scene3d-anchor-' + id);
        input.disabled = selectedAnchor < 0; input.value = selectedAnchor < 0 ? '' : anchors[selectedAnchor][field] ?? fallback;
      }
      $('#scene3d-anchor-add').disabled = !route;
      $('#scene3d-anchor-remove').disabled = selectedAnchor < 0;
    }
    function positionAnchorPanel() {
      if (mode !== 'anchor-mode') return;
      const tools = $('.scene3d-tools'), panel = $('#scene3d-anchors'), top = tools.offsetTop + tools.offsetHeight + 10;
      panel.style.top = top + 'px'; panel.style.maxHeight = Math.max(80, container.clientHeight - top - 75) + 'px';
    }
    function commitAnchors(routeKey, anchors, selection) {
      try {
        const route = lineRoutes().find((r) => r.routeKey === routeKey);
        if (Number.isInteger(route?.index)) editingIndex = route.index;
        options.editRoute({ routeKey, anchors });
        selectedRouteKey = routeKey; selectedAnchor = selection;
        sync(options.getData()); refreshConnectionHandles();
        errorBox.textContent = ''; info.textContent = `Route saved with ${anchors.length} anchor point(s). Endpoints remain attached.`;
      } catch (error) { errorBox.textContent = 'Route unchanged: ' + error.message; }
    }
    function selectRoute(routeKey) {
      const route = lineRoutes().find((r) => r.routeKey === routeKey);
      if (!route) return;
      selectedRouteKey = routeKey; selectedAnchor = -1;
      editingIndex = Number.isInteger(route.index) ? route.index : null;
      if (editingIndex !== null) options.selectConnection(editingIndex);
      refreshConnectionHandles();
    }
    $('#scene3d-route').onchange = (event) => selectRoute(event.target.value);
    $('#scene3d-anchor').onchange = (event) => { selectedAnchor = Number(event.target.value); fillAnchorPanel(); };
    $('#scene3d-anchor-add').onclick = () => {
      const route = lineRoutes().find((r) => r.routeKey === selectedRouteKey);
      if (!route) return;
      const anchors = [...(route.waypoints || [])], index = selectedAnchor < 0 ? anchors.length : selectedAnchor + 1;
      const points = [route.anchorStart, ...anchors.map(anchorWorld), route.anchorEnd];
      anchors.splice(index, 0, anchorData(points[index].clone().lerp(points[index + 1], .5)));
      commitAnchors(route.routeKey, anchors, index);
    };
    $('#scene3d-anchor-remove').onclick = () => {
      const route = lineRoutes().find((r) => r.routeKey === selectedRouteKey);
      if (!route || selectedAnchor < 0) return;
      const anchors = [...route.waypoints]; anchors.splice(selectedAnchor, 1);
      commitAnchors(route.routeKey, anchors, Math.min(selectedAnchor, anchors.length - 1));
    };
    for (const id of ['x', 'y', 'height']) $('#scene3d-anchor-' + id).onchange = () => {
      const route = lineRoutes().find((r) => r.routeKey === selectedRouteKey);
      if (!route || selectedAnchor < 0) return;
      const anchors = route.waypoints.map((p) => ({ ...p }));
      anchors[selectedAnchor] = { x: $('#scene3d-anchor-x').valueAsNumber, y: $('#scene3d-anchor-y').valueAsNumber,
        elevation3D: $('#scene3d-anchor-height').valueAsNumber };
      commitAnchors(route.routeKey, anchors, selectedAnchor);
    };
    function sizeConnectionHandles() {
      const forward = new T.Vector3(); camera.getWorldDirection(forward);
      for (const h of connectionHandles) {
        const depth = h.point.clone().sub(camera.position).dot(forward);
        const size = Math.max(.001, depth * 2 * Math.tan(camera.fov * Math.PI / 360) / container.clientHeight * 7);
        h.mesh.scale.setScalar(size * (h.kind === 'bend' ? 1.5 : 1));
        h.mesh.quaternion.copy(camera.quaternion);
        h.mesh.visible = depth > camera.near;
      }
    }
    function nearestHandle(event, predicate = () => true) {
      const box = canvas.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
      return connectionHandles.filter(predicate).map((handle) => {
        const p = screenPoint(handle.point);
        return { handle, distance: p.z >= -1 && p.z <= 1 ? Math.hypot(p.x - x, p.y - y) : Infinity };
      }).filter((h) => h.distance <= 18).sort((a, b) => a.distance - b.distance || (a.handle.kind === 'endpoint' ? -1 : 1))[0]?.handle;
    }
    function beginConnectionDrag(handle, event) {
      errorBox.textContent = '';
      const route = lineRoutes().find((r) => handle.routeKey ? r.routeKey === handle.routeKey : Number.isInteger(handle.index) && r.index === handle.index);
      const other = handle.end === 'from' ? 'to' : 'from';
      drag = { kind: 'connection', handle, originalRoutes: data.routes,
        originalAnchors: [...(route?.waypoints || [])],
        startX: event.clientX, startY: event.clientY, moved: false,
        source: handle.kind === 'port' ? handle : route ? { id: route[other + 'Id'], port: route[other + 'Port'], lane: route.lane } : null,
        point: handle.point.clone(), target: null };
      if (handle.kind === 'bend' || handle.kind === 'insert') {
        selectedRouteKey = handle.routeKey; selectedAnchor = handle.waypointIndex;
        if (mode === 'anchor-mode' && handle.kind === 'bend') fillAnchorPanel();
      }
      info.textContent = handle.kind === 'bend' || handle.kind === 'insert' ? 'Drag to reshape the route. Release to save; Escape cancels.'
        : 'Drop on a matching port: purple P, orange S, gray U; white host ports accept any lane. Escape cancels.';
    }
    function previewConnection(event) {
      const current = drag, h = current.handle;
      current.moved ||= Math.hypot(event.clientX - current.startX, event.clientY - current.startY) > 3;
      ray(event);
      if (h.kind === 'bend' || h.kind === 'insert') {
        const p = raycaster.ray.intersectPlane(new T.Plane(new T.Vector3(0, 1, 0), -h.point.y), new T.Vector3());
        if (!p) return;
        p.y = h.point.y;
        current.point.copy(p);
        const anchors = [...current.originalAnchors];
        if (h.kind === 'insert') anchors.splice(h.waypointIndex, 0, anchorData(p));
        else anchors[h.waypointIndex] = anchorData(p);
        routePreview = { routeKey: h.routeKey, anchors };
        h.mesh.position.copy(p); renderExternalRoutes();
      } else {
        if (current.target) current.target.mesh.material = current.target.mesh.userData.baseMaterial;
        const nearest = nearestHandle(event, (p) => p.kind === 'port' && p.id !== current.source.id);
        current.target = nearest && (current.source.lane === 'any' || nearest.lane === 'any' || nearest.lane === current.source.lane) ? nearest : null;
        if (current.target) current.target.mesh.material = handleMaterial('#65ff92');
        const p = current.target?.point || raycaster.ray.intersectPlane(ground, new T.Vector3());
        if (!p) return;
        current.point.copy(p);
        const old = editing.getObjectByName('Connection drag preview');
        if (old) { old.geometry.dispose(); editing.remove(old); }
        const origin = h.kind === 'port' ? h.point : endpoint(current.source.id, current.source.port, { x: 0, y: 0 }).point;
        const line = new T.Line(new T.BufferGeometry().setFromPoints([origin, p]), handleMaterial(current.target ? '#65ff92' : '#ffffff'));
        line.name = 'Connection drag preview'; line.renderOrder = 21; editing.add(line);
        info.textContent = current.target ? `Release to connect ${current.source.lane} to ${current.target.id} / ${current.target.label}.`
          : 'No matching port in range. Drop on P-to-P, S-to-S or U-to-U; zoom in to separate close ports.';
      }
    }
    function endConnection(cancel) {
      const current = drag, h = current.handle; drag = null;
      const anchors = routePreview?.anchors; routePreview = null;
      data.routes = current.originalRoutes; renderExternalRoutes(); refreshConnectionHandles();
      if (cancel || !current.moved && h.kind !== 'insert') { info.textContent = 'Route unchanged.'; return; }
      if (h.kind === 'bend' || h.kind === 'insert') {
        commitAnchors(h.routeKey, anchors || [...current.originalAnchors.slice(0, h.waypointIndex), anchorData(h.point),
          ...current.originalAnchors.slice(h.waypointIndex)], h.waypointIndex);
        return;
      }
      try {
        let edit;
        if (!current.target) { info.textContent = 'No connection made: drop on a matching port of another element. The original route is unchanged.'; return; }
        else if (h.kind === 'endpoint') edit = { index: h.index, [h.end]: current.target.id, [h.end + 'Port']: current.target.port };
        else edit = { from: h.id, fromPort: h.port, to: current.target.id, toPort: current.target.port };
        editingIndex = options.editConnection(edit);
        sync(options.getData()); refreshConnectionHandles();
        info.textContent = 'Connected and saved. Drag a square to bend the line; select a line to move its endpoint. Attached lines follow equipment.';
        errorBox.textContent = '';
      } catch (error) {
        errorBox.textContent = 'Connection unchanged: ' + error.message;
      }
    }
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    canvas.addEventListener('pointerdown', (event) => {
      canvas.focus(); ray(event);
      const handle = ['connect', 'anchor-mode'].includes(mode) && event.button === 0 && nearestHandle(event);
      if (handle) {
        beginConnectionDrag(handle, event); canvas.setPointerCapture(event.pointerId); event.preventDefault(); return;
      }
      const hit = raycaster.intersectObjects(stage.children, true).find((h) => h.object !== selection);
      let item = hit?.object;
      while (item && !item.userData.equipmentId && item.userData.connectionIndex === undefined && !item.userData.routeKey) item = item.parent;
      if (event.button === 0 && mode === 'anchor-mode' && item?.userData.routeKey) {
        selectRoute(item.userData.routeKey);
        info.textContent = 'Line selected. Add an anchor, drag a square, or choose an anchor to edit its coordinates or remove it.';
      } else if (event.button === 0 && item?.userData.equipmentId) {
        options.select(item.userData.equipmentId); highlight(item.userData.equipmentId);
        editingIndex = null; refreshConnectionHandles();
        if (mode === 'move') {
          const start = raycaster.ray.intersectPlane(ground, new T.Vector3()), group = models.get(item.userData.equipmentId);
          if (start && group) drag = { kind: 'move', id: item.userData.equipmentId, start, original: group.position.clone(), dx: 0, dz: 0,
            ports: [...group.userData.ports].map(([id, point]) => [id, point.clone()]),
            attachments: [...new Set(group.userData.attachments?.values() || [])].map((attachment) => ({
              attachment, deck: attachment.deck.clone(), bend: Math.abs(attachment.mouth.x - attachment.deck.x),
            })) };
        }
      } else if (event.button === 0 && item?.userData.connectionIndex !== undefined) {
        options.selectConnection(item.userData.connectionIndex);
        editingIndex = item.userData.connectionIndex; refreshConnectionHandles();
        if (mode === 'connect' && !data.routes.find((r) => r.index === editingIndex)?.waypoints?.length) {
          const bend = connectionHandles.find((h) => h.kind === 'bend' && h.index === editingIndex);
          if (bend) beginConnectionDrag(bend, event);
        }
      }
      if (!drag) drag = { kind: event.button === 2 ? 'pan' : 'orbit', x: event.clientX, y: event.clientY, theta, phi, target: target.clone() };
      canvas.setPointerCapture(event.pointerId); event.preventDefault();
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!drag) {
        const handle = ['connect', 'anchor-mode'].includes(mode) && nearestHandle(event);
        canvas.style.cursor = handle ? 'crosshair' : '';
        if (handle) info.textContent = handle.kind === 'port' ? `${handle.id} / ${handle.label} (${handle.lane}). Drag onto a matching port on another element.`
          : handle.kind === 'bend' ? 'Drag this square to reshape the route. Escape cancels.'
            : handle.kind === 'insert' ? 'Click or drag this green ring to insert an anchor between its neighbours.' : 'Drag this endpoint onto a matching port to reconnect.';
        return;
      }
      if (drag.kind === 'connection') { previewConnection(event); return; }
      if (drag.kind === 'move') {
        ray(event); const p = raycaster.ray.intersectPlane(ground, new T.Vector3());
        if (p) {
          drag.dx = p.x - drag.start.x; drag.dz = p.z - drag.start.z;
          previewMove(drag, drag.dx, drag.dz);
          info.textContent = 'Moving on the seabed plane; attached routes follow. Release to save; Escape cancels.';
        }
      } else if (drag.kind === 'pan') {
        const right = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 0), up = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
        target.copy(drag.target).addScaledVector(right, -(event.clientX - drag.x) * radius / container.clientHeight).addScaledVector(up, (event.clientY - drag.y) * radius / container.clientHeight);
      } else {
        theta = drag.theta - (event.clientX - drag.x) * .008;
        phi = Math.max(.08, Math.min(Math.PI / 2 - .04, drag.phi - (event.clientY - drag.y) * .008));
      }
      cameraUpdate();
    });
    function previewMove(current, dx, dz) {
      const group = models.get(current.id), delta = new T.Vector3(dx, 0, dz);
      group.position.copy(current.original).add(delta);
      for (const [id, point] of current.ports) group.userData.ports.get(id).copy(point).add(delta);
      for (const { attachment, deck, bend } of current.attachments) {
        attachment.deck.copy(deck).add(delta);
        const guide = jTubeCurve(attachment.deck, attachment.normal.x, bend);
        attachment.curve = guide.curve; attachment.mouth = guide.mouth;
      }
      renderExternalRoutes();
    }
    function endMove(cancel = false) {
      if (drag?.kind === 'connection') { endConnection(cancel); return; }
      const current = drag; drag = null;
      if (current?.kind !== 'move') return;
      previewMove(current, 0, 0);
      if (!cancel && (current.dx || current.dz)) options.move(current.id, current.dx / UNIT, current.dz / UNIT);
      sync(options.getData()); highlight(current.id);
    }
    canvas.addEventListener('pointerup', (event) => { if (drag?.kind === 'connection') previewConnection(event); endMove(); });
    canvas.addEventListener('pointercancel', () => endMove(true));
    canvas.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); endMove(true); }
      if (mode === 'anchor-mode' && !drag && ['Delete', 'Backspace'].includes(e.key)) {
        e.stopPropagation(); e.preventDefault(); $('#scene3d-anchor-remove').click();
      }
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault(); ray(e);
      const hit = raycaster.intersectObjects(stage.children, true).find((h) => h.object.isMesh && h.object.name !== 'Schematic flow pulse');
      const anchor = hit?.point || raycaster.ray.intersectPlane(ground, new T.Vector3());
      zoom(Math.exp(Math.max(-1, Math.min(1, e.deltaY * .001))), anchor);
    }, { passive: false });
    canvas.addEventListener('webglcontextlost', (event) => { event.preventDefault(); contextLost = true; active = false; cancelAnimationFrame(request); errorBox.textContent = '3D graphics context lost. Return to 2D; reload the viewer to restore 3D.'; });
    for (const key of ['orbit', 'move', 'connect', 'anchor-mode']) $('#scene3d-' + key).onclick = () => {
      endMove(true); mode = key;
      for (const name of ['orbit', 'move', 'connect', 'anchor-mode']) { const b = $('#scene3d-' + name); b.classList.toggle('on', name === mode); b.setAttribute('aria-pressed', String(name === mode)); }
      refreshConnectionHandles();
      info.textContent = mode === 'anchor-mode' ? 'Select any line or choose it in the anchor editor. Add, drag, edit or remove anchors; green rings insert between existing points. Escape cancels a drag.'
        : mode === 'connect' ? 'Drag a colored end onto a matching equipment port: P purple, S orange, U gray. Drag square handles to bend saved lines. Select a saved line to reconnect an endpoint. Top view and zoom help with close ports.'
        : mode === 'move' ? 'Drag equipment on the seabed plane. Changes save to the same 2D design. Add equipment and edit internals in 2D.' : 'Drag to orbit; right-drag to pan; wheel to zoom. Click equipment to inspect.';
    };
    $('#scene3d-top').onclick = () => { phi = .08; cameraUpdate(); };
    $('#scene3d-focus').onclick = () => { const selected = models.get(selectedId); if (selected) fit(selected); };
    $('#scene3d-labels').onclick = () => { labelVisible = !labelVisible; labels.forEach((s) => { s.visible = labelVisible; }); $('#scene3d-labels').setAttribute('aria-pressed', String(labelVisible)); };
    function sync(next) {
      data = next;
      const key = JSON.stringify([data.nodes, data.routes, data.zones]);
      if (key !== signature) { rebuild(); signature = key; }
      else highlight(data.selected);
    }
    function modelBounds(group) {
      group.updateWorldMatrix(true, true);
      const bounds = new T.Box3();
      group.traverse((part) => {
        if (!part.isMesh) return;
        if (!part.geometry.boundingBox) part.geometry.computeBoundingBox();
        bounds.union(part.geometry.boundingBox.clone().applyMatrix4(part.matrixWorld));
      });
      return bounds;
    }
    function svgSnapshot(title = 'Subsea layout') {
      if (contextLost) throw new Error('The graphics context was lost; reload before exporting.');
      cameraUpdate(); scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
      const size = renderer.getSize(new T.Vector2()), faces = [];
      const escape = (text) => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
      const planes = [(v) => v.w + v.x, (v) => v.w - v.x, (v) => v.w + v.y,
        (v) => v.w - v.y, (v) => v.w + v.z, (v) => v.w - v.z];
      const clip = (vertices) => {
        for (const distance of planes) {
          const result = [];
          for (let i = 0; i < vertices.length; i++) {
            const a = vertices[i], b = vertices[(i + 1) % vertices.length], da = distance(a), db = distance(b);
            if (da >= 0) result.push(a);
            if ((da >= 0) !== (db >= 0)) result.push(a.clone().lerp(b, da / (da - db)));
          }
          vertices = result;
          if (!vertices.length) break;
        }
        return vertices;
      };
      const project = (v) => [(v.x / v.w + 1) * size.x / 2, (1 - v.y / v.w) * size.y / 2];
      const point = (v) => project(v).map((n) => n.toFixed(2)).join(' ');
      const depth = (vertices) => vertices.reduce((sum, v) => sum + v.z / v.w, 0) / vertices.length;
      const light = sun.position.clone().sub(sun.target.position).normalize();
      const projection = new T.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      scene.traverse((part) => {
        let background = false;
        for (let parent = part; parent; parent = parent.parent) {
          if (!parent.visible) return;
          if (parent.userData.editorOnly) return;
          if (parent === environment) background = true;
        }
        if (part.name === '3D selection outline' || part.name === 'Schematic flow pulse') return;
        if (part.isSprite && part.userData.caption) {
          const position = new T.Vector4(...part.getWorldPosition(new T.Vector3()).toArray(), 1).applyMatrix4(projection);
          if (planes.every((d) => d(position) >= 0)) {
            const [x, y] = project(position);
            faces.push({ layer: 2, depth: 0, svg: `<text x="${x.toFixed(2)}" y="${y.toFixed(2)}" text-anchor="middle" font-family="Arial,sans-serif" font-size="14" fill="#ffffff">${escape(part.userData.caption)}</text>` });
          }
          return;
        }
        if (!part.isMesh && !part.isLine) return;
        if (!part.geometry || Array.isArray(part.material)) throw new Error('Unsupported geometry/material in SVG export.');
        const positions = part.geometry.attributes.position, indices = part.geometry.index;
        const matrix = new T.Matrix4().multiplyMatrices(projection, part.matrixWorld);
        const vertex = (i) => {
          const p = new T.Vector3().fromBufferAttribute(positions, indices ? indices.getX(i) : i);
          return new T.Vector4(p.x, p.y, p.z, 1).applyMatrix4(matrix);
        };
        const length = indices ? indices.count : positions.count;
        const opacity = part.material.transparent ? part.material.opacity : 1;
        if (part.isMesh) {
          const reflected = part.matrixWorld.determinant() < 0;
          for (let i = 0; i < length; i += 3) {
            const worldPoints = [0, 1, 2].map((j) => new T.Vector3().fromBufferAttribute(positions,
              indices ? indices.getX(i + j) : i + j).applyMatrix4(part.matrixWorld));
            const normal = worldPoints[1].clone().sub(worldPoints[0]).cross(worldPoints[2].clone().sub(worldPoints[0])).normalize();
            if (reflected) normal.negate();
            if (part.material.side === T.FrontSide && normal.dot(camera.position.clone().sub(worldPoints[0])) <= 0) continue;
            const polygon = clip([vertex(i), vertex(i + 1), vertex(i + 2)]);
            if (polygon.length < 3) continue;
            const color = '#' + part.material.color.clone().multiplyScalar(.55 + .45 * Math.max(0, normal.dot(light))).getHexString();
            faces.push({ layer: background ? 0 : 1, depth: depth(polygon), svg: `<path d="M${polygon.map(point).join('L')}Z" fill="${color}" stroke="${color}" stroke-width="0.15" opacity="${opacity}"/>` });
          }
        } else {
          const step = part.isLineSegments ? 2 : 1;
          for (let i = 0; i + 1 < length; i += step) {
            let a = vertex(i), b = vertex(i + 1), visible = true;
            for (const distance of planes) {
              const da = distance(a), db = distance(b);
              if (da < 0 && db < 0) { visible = false; break; }
              if ((da < 0) !== (db < 0)) {
                const crossing = a.clone().lerp(b, da / (da - db));
                if (da < 0) a = crossing; else b = crossing;
              }
            }
            if (visible) faces.push({ layer: background ? 0 : 1, depth: depth([a, b]), svg: `<path d="M${point(a)}L${point(b)}" fill="none" stroke="#${part.material.color.getHexString()}" stroke-width="0.6" opacity="${opacity}"/>` });
          }
        }
      });
      // Terrain stays below every model; average-depth sorting must not paint it over long pipes.
      faces.sort((a, b) => a.layer - b.layer || b.depth - a.depth);
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${size.x}" height="${size.y}" viewBox="0 0 ${size.x} ${size.y}"><title>${escape(title)} - static 3D projection</title><desc>Vector meshes and lines from the current camera. Zoom in a browser or vector editor. Open the companion HTML for interactive 3D rotation. Lighting is simplified; textures, shadows and animated particles are not embedded.</desc><rect width="100%" height="100%" fill="#${scene.background.getHexString()}"/>${faces.map((f) => f.svg).join('')}</svg>`;
    }
    let restoredView = false;
    function restoreView(view) {
      if (!Array.isArray(view.target) || view.target.length !== 3 || !view.target.every(Number.isFinite)
        || ![view.radius, view.phi, view.theta].every(Number.isFinite) || view.radius <= 0 || view.phi <= 0 || view.phi >= Math.PI) {
        throw new Error('Invalid saved 3D camera.');
      }
      target.fromArray(view.target); radius = view.radius; phi = view.phi; theta = view.theta;
      labelVisible = view.labels === true; labels.forEach((s) => { s.visible = labelVisible; });
      $('#scene3d-labels').setAttribute('aria-pressed', String(labelVisible)); cameraUpdate();
    }
    root.addEventListener('unload', () => {
      active = false; cancelAnimationFrame(request); observer.disconnect(); disposeOwned(stage); disposeOwned(environment); disposeOwned(editing);
      Object.values(geometries).forEach((g) => g.dispose()); materials.forEach((m) => m.dispose()); renderer.dispose();
    }, { once: true });
    return {
      show() { if (contextLost) throw new Error('The graphics context was lost; reload the viewer.'); resize(); sync(options.getData());
        if (options.initialView && !restoredView) { restoreView(options.initialView); restoredView = true; }
        active = true; last = performance.now(); cancelAnimationFrame(request); request = requestAnimationFrame(frame); },
      hide() { endMove(true); active = false; cancelAnimationFrame(request); },
      sync, fit, zoom, svgSnapshot,
      viewState() { return { target: target.toArray(), radius, phi, theta, labels: labelVisible }; },
      snapshot() {
        const visible = editing.visible;
        try {
          editing.visible = false; renderer.render(scene, camera);
          return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('3D image capture failed.')), 'image/png'));
        } finally { editing.visible = visible; }
      },
      diagnostics() {
        const seabed = environment.children.find((c) => c.name === 'Illustrative NCS seabed');
        return { active, phase, speed: data?.speed, camera: camera.position.toArray(), target: target.toArray(), radius, fov: camera.fov,
          connectionHandles: connectionHandles.map(({ mesh, point, ...h }) => ({ ...h, point: mesh.position.toArray(), screen: screenPoint(mesh.position) })),
          equipmentRoutes: equipmentRoutes.map((r) => ({ routeKey: r.routeKey, equipmentId: r.equipmentId, lane: r.lane,
            from: r.from.toArray(), to: r.to.toArray(), points: r.curve.getPoints(64).map((p) => p.toArray()), anchors: r.waypoints })),
          seabedColor: seabed?.material.color.toArray(), seabedGrid: environment.children.some((c) => c.name === 'Gray seabed grid'),
          terrainRange: seabed ? Array.from(seabed.geometry.attributes.position.array).filter((_, i) => i % 3 === 2)
            .reduce((range, height) => [Math.min(range[0], height), Math.max(range[1], height)], [Infinity, -Infinity]) : [],
          contours: environment.children.find((c) => c.name === 'Illustrative bathymetry contours')?.geometry.attributes.position.count || 0,
          routes: renderedRoutes.map((r) => ({ routeKey: r.routeKey, anchors: r.waypoints, index: r.index, style: r.style, from: r.from.toArray(), to: r.to.toArray(),
            fromId: r.fromId, toId: r.toId, fromPort: r.fromPort, toPort: r.toPort, lane: r.lane, autoBridge: r.autoBridge,
            points: r.curve.getPoints(64).map((p) => p.toArray()) })),
          psvs: stage.children.filter((c) => c.name === 'psv valve assembly').map((g) => g.position.toArray()),
          models: [...models].map(([id, g]) => {
          const ship = g.getObjectByName('FPSO vessel'), hull = ship?.getObjectByName('FPSO shaped hull');
          return { id, type: g.userData.type, family: g.userData.family, parts: g.children.length,
          scale3D: g.userData.scale3D, bounds: (() => { const b = modelBounds(g); return { min: b.min.toArray(), max: b.max.toArray() }; })(), pipeHeight: g.userData.pipeHeight,
          vessel: ship ? {
            hullVertices: Array.from(hull.geometry.attributes.position.array), hullColor: hull.material.color.toArray(),
            processModules: ship.children.filter((c) => c.name === 'FPSO process module').length,
            windows: ship.children.filter((c) => c.name === 'FPSO accommodation window').length,
            helidecks: ship.children.filter((c) => c.name === 'FPSO helideck').length,
            craneMembers: ship.children.filter((c) => c.name.startsWith('Crane lattice')).length,
            moorings: ship.children.filter((c) => c.name === 'FPSO catenary mooring').length,
            turret: g.localToWorld(new T.Vector3(g.userData.turretX, g.userData.pipeHeight, 0)).toArray(),
            turretRadius: g.userData.turretRadius,
          } : null,
          spudcans: g.children.filter((c) => c.name === 'Jackup spudcan').length,
          legCenters: g.userData.legCenters,
          pipes: g.children.filter((c) => c.name === 'Connected piping / cable').length,
          valves: g.children.filter((c) => c.name.endsWith('valve assembly')).length,
          customShapes: g.children.filter((c) => c.name.startsWith('Custom drawn')).length,
          roofPanels: g.children.filter((c) => c.name === 'Protection roof panel').length,
          roofColors: g.children.filter((c) => c.name === 'Protection roof panel').map((c) => c.material.color.toArray()),
          gussets: g.children.filter((c) => c.name === 'Sloped protective gusset').length,
          topsideModules: g.children.filter((c) => c.name === 'Topside process module').length,
          craneMembers: g.children.filter((c) => c.name.startsWith('Crane lattice')).length,
          clamps: g.children.filter((c) => c.name === 'PLEM central pipe clamp').length,
          structure: g.children.filter((c) => c.name.startsWith('Jacket ') || c.name.startsWith('Jackup leg')).map((c) => ({
            name: c.name, color: c.material.color.toArray(),
            ends: [-.5, .5].map((y) => c.localToWorld(new T.Vector3(0, y, 0)).toArray()),
          })),
          ports: [...g.userData.ports].map(([id, p]) => ({ id, point: p.toArray() })),
          pipePaths: g.userData.pipePaths.map((p) => ({
            id: p.id, color: p.color.toArray(), points: p.curve.getPoints(32).map((point) => point.multiplyScalar(g.userData.scale3D).add(g.position).toArray()),
          })),
          deckWidth: g.userData.deckWidth, deckDepth: g.userData.deckDepth,
          attachments: g.userData.attachments ? [...g.userData.attachments].map(([id, a]) => ({
            id, deck: a.deck.toArray(), mouth: a.mouth.toArray() })) : [],
          guides: g.children.filter((c) => c.name === 'Riser guide / J-tube').length,
          brackets: g.children.filter((c) => c.name === 'J-tube jacket support bracket').length,
          position: g.position.toArray(), screen: (() => { const p = g.position.clone().add(new T.Vector3(0, 1.2, 0)).project(camera); return { x: (p.x + 1) * container.clientWidth / 2, y: (1 - p.y) * container.clientHeight / 2 }; })() }; }),
          flows: flows.map((f) => ({ connectionIndex: f.connectionIndex, reverse: f.reverse, points: f.particles.map((p) => p.position.toArray()), visible: f.particles.some((p) => p.visible) })),
          drawCalls: renderer.info.render.calls };
      },
    };
  }
  root.Subsea3D = { create, families, unit: UNIT };
})(window);
