Subject: Tavily x402 Advanced Search returns HTTP 402 after a funded Base USDC authorization

Hi Tavily Support,

We are integrating your x402 Advanced Search endpoint into ARGUS. On 2026-11-14 at 14:51:59 UTC, `POST https://x402.tavily.com/search` returned a valid x402 v2 quote for 10,000 atoms of native USDC on Base. We used the x402 SDK flow from your documentation to send one authorization for that exact quote. The signed request returned HTTP 402 with `Verification error` and no payment receipt. The wallet held 6.779115 USDC. Base block 57388035 showed the authorization nonce unused after the deadline, no matching authorization event, and an unchanged balance.

- Network: `eip155:8453`
- USDC contract: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- Quoted recipient: `0xd39a4D48C7AB6672E3A728ab8a50c2512dB6c4a5`
- Authorization nonce: `0x03aff57bfb1375dd521fe3aef59e02f621150968081389db1ed263b41380d78b`
- Authorization deadline: `2026-11-14T14:52:59Z`

Could you look up the request by timestamp, quoted recipient, or nonce and share the specific reason your verifier rejected it? If the Base path requires a field or header beyond the documented SDK flow, please point us to that requirement.
