#!/usr/bin/env bash
# Edge cases from alexar76/mcp-tool-set-digest#1 (bcrypto0's four cases, CrawlCheck's depth edges) through the three
# reference implementations of this monorepo. Usage: run.sh <aicom checkout> <work dir>. Writes the inputs into the work
# dir, builds the Go program there and prints one line per case and reader.
set -u
M="$1/mcp-tool-set-digest"; W="$2"; mkdir -p "$W"; cd "$W"
python3 - <<'PY'
def nest(n): return "[" * n + "0" + "]" * n
cases = {
 "contract-509": '[{"name":"t","inputSchema":{"x":%s}}]' % nest(509),
 "contract-510": '[{"name":"t","inputSchema":{"x":%s}}]' % nest(510),
 "contract-2000": '[{"name":"t","inputSchema":{"x":%s}}]' % nest(2000),
 "contract-100000": '[{"name":"t","inputSchema":{"x":%s}}]' % nest(100000),
 "extras-510": '[{"name":"t","x":%s}]' % nest(510),
 "extras-511": '[{"name":"t","x":%s}]' % nest(511),
 "extras-100000": '[{"name":"t","x":%s}]' % nest(100000),
 "wrapped-contract-509": '{"tools":[{"name":"t","inputSchema":{"x":%s}}]}' % nest(509),
 "description-1e400": '[{"name":"t","description":1e400}]',
 "extra-1e400": '[{"name":"t","x":1e400}]',
 "repeated-description": '[{"name":"t","description":"a","description":"b"}]',
 "tools-twice": '{"tools":[{"name":"a"}],"tools":[{"name":"b"}]}',
 "tools-next-to-result": '{"tools":[{"name":"a"}],"result":{"tools":[{"name":"b"}]}}',
}
for k, v in cases.items(): open(k + ".json", "w").write(v)
PY
(cd "$M/implementations/go" && GOFLAGS=-mod=mod go build -o "$W/gotsd" .)
for f in contract-509 contract-510 contract-2000 contract-100000 extras-510 extras-511 extras-100000 wrapped-contract-509 description-1e400 extra-1e400 repeated-description tools-twice tools-next-to-result; do
  printf '%-22s py %s\n' "$f" "$(python3 -I "$M/implementations/python/tool_set_digest.py" < $f.json 2>&1 | tail -1 | cut -c1-120)"
  printf '%-22s js %s\n' "" "$(node "$M/implementations/javascript/tool-set-digest.mjs" < $f.json 2>&1 | grep -E '^\{|Error' | head -1 | cut -c1-120)"
  printf '%-22s go %s\n' "" "$(./gotsd < $f.json 2>&1 | tail -1 | cut -c1-120)"
done
