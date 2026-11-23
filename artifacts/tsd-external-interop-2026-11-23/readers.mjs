import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const [vectorsPath, crawlcheckPath, addonPath] = process.argv.slice(2);
const { vectors } = JSON.parse(readFileSync(vectorsPath, 'utf8'));
const { toolSetDigest } = await import(pathToFileURL(crawlcheckPath));
const { toolSetDigestsFromPages } = await import(pathToFileURL(addonPath));

async function run(reader) {
  return Object.fromEntries(await Promise.all(vectors.map(async ({ id, tools }) => {
    try {
      return [id, await reader(tools)];
    } catch (error) {
      return [id, { parser_error: error.name }];
    }
  })));
}

process.stdout.write(JSON.stringify({
  'crawlcheck-javascript': await run((raw) => toolSetDigest(JSON.parse(raw))),
  'addon-declaration': await run((raw) => toolSetDigestsFromPages([raw])),
}));
