#!/usr/bin/env node
'use strict';
// This name is held so `npx awr-verify` cannot fetch a stranger's package. It verifies
// nothing: exit 2 (usage) under the AWR §17 CLI contract, so no script reads it as "valid".
process.stderr.write(
  'awr-verify: this is a placeholder. Run the verifier with\n' +
  '  npx -p @alexar76/awr-verify awr-verify verify receipt.json\n'
);
process.exit(2);
