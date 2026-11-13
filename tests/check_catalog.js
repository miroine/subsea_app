// usage: node tests/check_catalog.js catalog.json   (catalog dumped from subsea.catalog)
const fs = require('fs'); require('../subsea/static/engine.js');
const cat = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ids = globalThis.Subsea.ids(); let bad = 0;
for (const e of cat) {
  const pool = e.kind === 'node' ? ids.node : e.kind === 'link' ? ids.link : ids.host;
  if (!pool.includes(e.id)) { console.log('MISSING in JS:', e.kind, e.id); bad++; }
}
const known = new Set(cat.map((e) => e.id));
for (const k of [...ids.node, ...ids.link, ...ids.host]) if (!known.has(k)) { console.log('MISSING in catalog:', k); bad++; }
console.log(bad ? 'FAIL' : `OK – ${cat.length} symbols consistent`); process.exit(bad ? 1 : 0);
