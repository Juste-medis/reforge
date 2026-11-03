// Compile an OpenSCAD file with OpenSCAD itself (its WASM build) and write the STL it renders.
// Usage: node scad2stl.mjs model.scad out.stl   → prints {"ms":…,"bytes":…,"messages":[…warnings and errors…]}
import { createOpenSCAD } from "openscad-wasm-prebuilt";
import { readFileSync, writeFileSync } from "node:fs";

const [src, out] = process.argv.slice(2);
const messages = [];
const openscad = await createOpenSCAD({ print: () => {}, printErr: (m) => messages.push(m) });
const t0 = performance.now();
const stl = await openscad.renderToStl(readFileSync(src, "utf8"));
writeFileSync(out, stl);
console.log(JSON.stringify({ ms: Math.round(performance.now() - t0), bytes: stl.length,
                             messages: messages.filter((m) => /WARNING|ERROR/.test(m)) }));
