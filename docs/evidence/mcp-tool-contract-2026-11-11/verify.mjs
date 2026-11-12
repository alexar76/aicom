// Fixture runner. Uses only Node standard library and reads only the shipped inputs.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const load = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const {archive, captures, cases} = load('vectors.json');

// The fixture inputs have unique JSON object keys and contain only valid UTF-16 strings.
// Sort object keys recursively. A sort of whole arrays here would change enum and tuple bytes.
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  assert(typeof value !== 'number' || Number.isFinite(value), 'non-finite JSON number');
  return JSON.stringify(value);
}

function toolMap(tools) {
  const map = new Map();
  for (const tool of tools) {
    assert(typeof tool.name === 'string' && tool.name.length && !map.has(tool.name), 'fixture expects unique tool names');
    map.set(tool.name, tool);
  }
  return map;
}

function triple(tool) {
  return {name: tool.name, description: tool.description, inputSchema: tool.inputSchema};
}

function projection(tool, includeOutput) {
  const core = triple(tool);
  return includeOutput && Object.hasOwn(tool, 'outputSchema') ? {...core, outputSchema: tool.outputSchema} : core;
}

function digest(map, includeOutput) {
  const entries = [...map.keys()].sort().map((name) => projection(map.get(name), includeOutput));
  return `sha256-${createHash('sha256').update(canonical(entries)).digest('base64')}`;
}

function compare(before, after) {
  if (!before.complete || !after.complete || before.nextCursor || after.nextCursor) {
    return {comparable: false, reason: 'incomplete-list'};
  }
  if (canonical(before.scope) !== canonical(after.scope)) {
    return {comparable: false, reason: 'scope-mismatch'};
  }
  const old = toolMap(before.tools);
  const now = toolMap(after.tools);
  const removed = [...old.keys()].filter((name) => !now.has(name)).sort();
  const added = [...now.keys()].filter((name) => !old.has(name)).sort();
  const shared = [...now.keys()].filter((name) => old.has(name)).sort();
  const changed = (field) => shared.filter((name) => canonical(field(old.get(name))) !== canonical(field(now.get(name))));
  return {
    comparable: true,
    tripleDigestChanged: digest(old, false) !== digest(now, false),
    mtlToolSetDigestChanged: digest(old, true) !== digest(now, true),
    added,
    removed,
    tripleChanged: changed(triple),
    outputSchemaChanged: changed((tool) => tool.outputSchema ?? null),
    effectiveReadOnlyChanged: changed((tool) => tool.annotations?.readOnlyHint ?? false),
  };
}

function capture(name) {
  const snapshot = captures[name];
  assert(snapshot, `missing capture ${name}`);
  return snapshot.file ? {...snapshot, tools: load(snapshot.file)} : snapshot;
}

function removeAt(document, pointer) {
  const path = pointer.slice(1).split('/');
  const key = path.pop();
  const parent = path.reduce((node, part) => node[part], document);
  assert(Object.hasOwn(parent, key), pointer);
  const value = parent[key];
  delete parent[key];
  return value;
}

function verifyRealChanges(before, after) {
  for (const check of archive.checks) {
    const old = structuredClone(before.get(check.tool));
    const now = structuredClone(after.get(check.tool));
    for (const pointer of check.changed ?? check.otherChanged) {
      assert.notDeepEqual(removeAt(old, pointer), removeAt(now, pointer), `${check.tool} ${pointer}`);
    }
    if (check.classification === 'enum-narrowed') {
      const beforeValues = removeAt(old, check.enumPath);
      const afterValues = removeAt(now, check.enumPath);
      assert.deepEqual(beforeValues.filter((value) => !afterValues.includes(value)), check.removedValues);
      assert.deepEqual(afterValues, beforeValues.filter((value) => !check.removedValues.includes(value)));
    } else if (check.classification === 'optional-parameter-added') {
      const pointer = `/inputSchema/properties/${check.addedProperty}`;
      assert(!Object.hasOwn(old.inputSchema.properties, check.addedProperty));
      assert(!(now.inputSchema.required ?? []).includes(check.addedProperty));
      const property = removeAt(now, pointer);
      assert.equal(property.type, check.type);
      assert.equal(property.default, check.default);
    } else {
      assert.equal(check.classification, 'description-only');
    }
    assert.deepEqual(old, now, `${check.tool} contains a change beyond the stated classification`);
  }
}

const before = toolMap(capture('observed-before').tools);
const after = toolMap(capture('observed-after').tools);
assert.equal(before.size, archive.expectedObservedCount);
assert.equal(after.size, archive.expectedObservedCount);
assert.equal(digest(before, true), archive.beforeDigest);
assert.equal(digest(after, true), archive.afterDigest);
verifyRealChanges(before, after);
for (const vector of cases) {
  assert.deepEqual(compare(capture(vector.before), capture(vector.after)), vector.expected, vector.id);
  console.log(`PASS ${vector.id}`);
}
console.log(`PASS ${archive.checks.length} observed change classifications and both archived MTL/1 digests`);
