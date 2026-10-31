const test = require('node:test');
const assert = require('node:assert/strict');
const merge = require('./index.cjs');
const payload = JSON.parse('{"__proto__":{"isAdmin":true},"constructor":{"prototype":{"polluted":true}},"prototype":{"polluted":true}}');
function safe(value) {
 assert.equal(Object.getPrototypeOf(value), Object.prototype);
 assert.equal(value.isAdmin, undefined);
 for (const key of ['__proto__','constructor','prototype']) assert.equal(Object.hasOwn(value,key),false);
 assert.equal({}.polluted,undefined);
}
test('source and target poison keys cannot mutate returned prototypes', () => {
 for (const target of [Object.create(null), {}, null, {session:null}, JSON.parse('{"__proto__":{}}')]) {
  safe(merge(target,payload));
  safe(merge(payload,target || {}));
  safe(merge({session:target}, {session:payload}).session);
 }
});
test('array cloning, symbols, custom merge and all preserve the upstream API', () => {
 const s=Symbol('x');const a={x:{a:1},arr:[{a:1}],[s]:{b:2}};
 const result=merge(a,{x:{b:2},arr:[2]});
 assert.deepEqual(result.x,{a:1,b:2});assert.deepEqual(result.arr,[{a:1},2]);assert.notEqual(result.x,a.x);assert.deepEqual(result[s],{b:2});
 assert.deepEqual(merge.all([{a:1},{b:2}]),{a:1,b:2});
 assert.deepEqual(merge({a:[1]},{a:[2]},{arrayMerge:(_,src)=>src}),{a:[2]});
 assert.deepEqual(merge({x:{a:1}},{x:{b:2}},{customMerge:key=>key==='x'?()=>({custom:true}):undefined}),{x:{custom:true}});
});
