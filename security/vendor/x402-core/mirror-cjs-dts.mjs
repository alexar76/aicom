import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
async function walk(dir) { for (const entry of await readdir(dir, {withFileTypes:true})) { const src=path.join(dir,entry.name); if(entry.isDirectory()) await walk(src); else if(src.endsWith('.d.mts')) { const target=src.replace('dist/esm/','dist/cjs/').replace(/\.d\.mts$/,'.d.ts'); await mkdir(path.dirname(target),{recursive:true}); await writeFile(target,(await readFile(src,'utf8')).replaceAll('.d.mts','.d.ts').replaceAll('.mjs','.js')); } } }
await walk('dist/esm');
