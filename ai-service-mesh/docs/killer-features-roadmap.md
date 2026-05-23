# Killer Features Roadmap (Ecosystem)

AI Service Mesh is the **umbrella product**. These killer features ship in sibling packages and plug into the mesh.

| Product | Killer feature | Status in monorepo | Mesh integration |
|---------|----------------|-------------------|------------------|
| **aimarket-hub** | Zero-Trust Agent Discovery | Hub search + SSRF-hardened federation | `MESH_HUB_URL` federated discovery |
| **aimarket-plugins** | TEE Escrow | Plugin scaffold + simulated TEE | Replace `EscrowLedger` with plugin client |
| **aimarket-widget** | 1-Click Agent Embed | `aimarket.js` embed | Dashboard embeds widget for consumer sites |
| **aicom** | Auto-Mesh Pipeline | Factory pipeline | Mesh orchestrator calls factory agents |

## Phase 1 (this folder — v0.1)

- [x] Mesh API with discovery → verify → escrow → invoke → settle
- [x] Activity dashboard (React)
- [x] Security hardening (CORS, SSRF, tokens, rate limit)
- [x] Unit tests + Locust load harness
- [x] Documentation

## Phase 2

- [ ] Wire `aimarket-plugins` TEE escrow for real holds/releases
- [ ] Signed invocation receipts (provenance plugin)
- [ ] mTLS between mesh and agent endpoints

## Phase 3

- [ ] Extract to standalone Git repository
- [ ] Public SDK (`@aimarket/mesh-client`)
- [ ] Multi-tenant org isolation

## Phase 4 (UI)

- [ ] Embed `aimarket-widget` in dashboard for 1-click consumer flows
- [ ] aicom Admin tab: "Mesh runs" linked to activity feed
