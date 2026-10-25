# Local x402 Zod 4 migration

Upstream: https://github.com/x402-foundation/x402/tree/ced627cdd93a7785e20243fef12bf97552759151/typescript/packages/core

Source revision: `ced627cdd93a7785e20243fef12bf97552759151` (the 2.28.0 release). All 20 runtime sources match the npm 2.28.0 source maps byte for byte before the changes below. Apache-2.0 license retained.

Local version: `2.28.0+aimarket.zod4.1`. Changes: Zod 4.6.7; explicit string key schemas for records; Zod 4 type parameter order; bounded payment alternatives (64), facilitator capabilities and signer lists (1024). Cryptographic/payment encoding code is unchanged. Both ESM/CJS and declarations are rebuilt from checked-in source with `npm ci --ignore-scripts && npm run build`. The resulting archive is copied into each consuming package's vendor directory by `security/vendor/build.mjs`; installs need no lifecycle patches.
