// Business-rule checks against the exact source embedded in the n8n workflow.
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const assert = require('node:assert/strict');
const source = readFileSync(`${__dirname}/quote.js`, 'utf8');
const run = body => JSON.parse(JSON.stringify(runInNewContext(
  `(function () { ${source} })()`, {$input: {first: () => ({json: {body}})}})[0].json));
let checks = 0;
for (const body of [null, {}, {items: []}, {items: [{sku:'MUG-BLUE', quantity:0}]},
  {items: [{sku:'MUG-BLUE', quantity:1.5}]}, {items: [{sku:'MUG-BLUE', quantity:'1'}]},
  {items: [{sku:'MUG-BLUE', quantity:101}]},
  {items: [{sku:'MUG-BLUE', quantity:60},{sku:'MUG-BLUE',quantity:60}]},
  {items: [{sku:'MUG-BLUE', quantity:1}], url: 'https://example.com'},
  {items: [{sku:'__proto__', quantity:1}]}]) {
  assert.equal(run(body).statusCode, 422); checks++;
}
const ready = run({items:[{sku:'BEANS-250',quantity:2},{sku:'MUG-BLUE',quantity:1}]}).body;
assert.equal(ready.subtotal_minor,3430);
assert.equal(ready.status,'ready');
assert.equal(ready.grand_total_minor,null);
assert.equal(ready.demo,true);
assert.equal(ready.reservation_created,false); checks++;
const duplicate = run({items:[{sku:'MUG-BLUE',quantity:2},{sku:'MUG-BLUE',quantity:2}]}).body;
assert.equal(duplicate.status,'insufficient_stock');
assert.equal(duplicate.lines.length,1);
assert.equal(duplicate.subtotal_minor,3400); checks++;
const unknown = run({items:[{sku:'UNKNOWN',quantity:1},{sku:'MUG-BLUE',quantity:1}]}).body;
assert.equal(unknown.status,'unknown_items');
assert.equal(unknown.subtotal_minor,null); checks++;
assert.equal(run({items:[{sku:'FILTER-100',quantity:1}]}).body.can_fulfill,false); checks++;
const workflow = JSON.parse(readFileSync(`${__dirname}/workflow.json`,'utf8'));
assert.equal(workflow.nodes.find(n=>n.type==='n8n-nodes-base.code').parameters.jsCode,source);
console.log(`PASS: ${checks} business-rule scenarios; workflow embeds the tested source`);
