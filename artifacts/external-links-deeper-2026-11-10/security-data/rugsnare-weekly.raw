# MCP Drift Watch - weekly report

**Run:** 2026-11-09 · pinned baselines from `audits/watch-list.json` (advance a pin deliberately, via PR, when you accept a new contract). Method: pin -> install latest -> `rugsnare diff`.

**Total findings since baselines: 300**

| server | package | pinned -> latest | findings | status |
|---|---|---|---|---|
| chrome-devtools | chrome-devtools-mcp | 1.8.0 -> 1.12.0 | 32 | ok |
| azure-devops | @azure-devops/mcp | 2.5.0 -> 2.11.0 | 119 | ok |
| currents | @currents/mcp | 2.3.3 -> 2.7.0 | 51 | ok |
| hostinger | hostinger-api-mcp | 2.4.0 -> 3.32.1 | 47 | ok |
| notion | @notionhq/notion-mcp-server | 2.4.1 -> 2.6.1 | 1 | ok |
| heroku | @heroku/mcp-server | 1.2.5 -> 1.2.13 | 33 | ok |
| context7 | @upstash/context7-mcp | 4.0.4 -> 4.6.0 | 1 | ok |
| sentry | @sentry/mcp-server | 0.42.0 -> 0.49.0 | 0 | clean |
| launchdarkly | @launchdarkly/mcp-server | 0.7.0 -> 0.7.2 | 16 | ok |

Full audit with receipts: [npm-top-mcp-drift-2026-10.md](npm-top-mcp-drift-2026-10.md). Tool: [rugsnare](https://www.npmjs.com/package/rugsnare).

## chrome-devtools - drift excerpt

```
  [DRIFT] click (BREAKING) 38eefa12b8a62af9 -> 72d90b680c02beca
  [DRIFT] close_page (BREAKING) 161f1a531c5872ab -> e0c79a064e8e058d
  [DRIFT] drag (BREAKING) 78d1b3bcd9cbc0a0 -> 1f3a955c724cefb9
  [DRIFT] emulate (BREAKING) d2bb928bb6fca78b -> 35a3fb981a6672b1
  [DRIFT] evaluate_script (BREAKING) 90d58912d3d3c247 -> 58317b4306b12215
  [DRIFT] fill (BREAKING) 8f837aa7a360751f -> 1bc52b3383722f66
  [DRIFT] fill_form (BREAKING) ef50c7f542cd4389 -> 9ae5d0c1d87e42f7
  [DRIFT] get_console_message (BREAKING) 019a3f407867c64f -> 5091333efe4f0a6e
  [NEW ] get_css_styles 90be291984b99e7a
  [DRIFT] get_network_request (BREAKING) a31511f518c67413 -> e94d61b5fd22450f
  [DRIFT] handle_dialog (BREAKING) 56a9fa19b4d3bc5e -> 2a4fceda79f47828
  [DRIFT] hover (BREAKING) 0b9ee38135e20e89 -> bb129337c3f8ff10
```

## azure-devops - drift excerpt

```
  [DRIFT] core_list_project_teams (ANNOTATION) 7a520cf0f4d8cdb6 -> 7a520cf0f4d8cdb6
  [DRIFT] core_list_projects (ANNOTATION) 1b46d421cb4d1998 -> 1b46d421cb4d1998
  [DRIFT] core_get_identity_ids (ANNOTATION) 946ecb63377c97d7 -> 946ecb63377c97d7
  [NEW ] work 8901a5976504428a
  [NEW ] work_iteration_write 3044855da2bfc590
  [NEW ] work_capacity_write 26a8f4073f925f2a
  [NEW ] pipelines_build ee28e600be80ff39
  [NEW ] pipelines_build_log 32d892b420e0959d
  [NEW ] pipelines_definition 7243ce37950dc9f1
  [NEW ] pipelines_run fe259e7d1ffefed9
  [NEW ] pipelines_artifact 56988ef13f597c2e
  [NEW ] pipelines_write cf73a0e774264de4
```

## currents - drift excerpt

```
  [DRIFT] currents-list-actions (BREAKING) 75bcb5c277076c4d -> bc48eca464642f65
  [DRIFT] currents-create-action (BREAKING) f1b1edd894a7099b -> e3f867a764d4cb14
  [DRIFT] currents-get-action (BREAKING) e46fc5be47051043 -> e72c3dcdf8ec975e
  [DRIFT] currents-update-action (BREAKING) 09bdf0604251f8b6 -> c7031b96c602a810
  [DRIFT] currents-delete-action (BREAKING) df52ca10adfbb6d5 -> d54671541f73c216
  [DRIFT] currents-enable-action (BREAKING) e231575cef6fe4e1 -> c4a8fb6533ca98fa
  [DRIFT] currents-disable-action (BREAKING) 67284654b2e0d000 -> af42d34594c62a10
  [DRIFT] currents-list-affected-tests (BREAKING) bb74c6df47c56c16 -> 5145b8c06295e012
  [DRIFT] currents-get-affected-test-executions (BREAKING) c4b39c1ca203a511 -> 82e70a030f795f2c
  [NEW ] currents-get-action-executions 7b3325c7ebb570fb
  [DRIFT] currents-get-projects (NOTATION) 7d7c201bd43eb51e -> f3b4d0b3ed72ef99
  [DRIFT] currents-get-project (BREAKING) f47876b3693cb117 -> 37de59aa9c384264
```

## hostinger - drift excerpt

```
  [DRIFT] (identity) (IDENTITY)
  [NEW ] audit-hosting/SKILL.md (resource) 721bd0a5b0db0549
  [NEW ] connect-domain/SKILL.md (resource) fb06ea81ec871578
  [NEW ] deploy-to-hosting/SKILL.md (resource) 5f0ed3a42707c09d
  [DRIFT] hostinger-headless/SKILL.md (resource) a58a5d028a799a8a -> a58a5d028a799a8a
  [NEW ] hostinger-headless/connect/SKILL.md (resource) e9083a01dbddfbb8
  [NEW ] hostinger-headless/connect/bootstrap.mjs (resource) b44166da80115afd
  [NEW ] hostinger-headless/connect/launch.mjs (resource) 9bf2122178fc711a
  [NEW ] hostinger-headless/connect/launch.sh (resource) 4301d2ca698549b5
  [NEW ] hostinger-headless/connect/tools/antigravity.md (resource) 16e46cad0defcd81
  [NEW ] hostinger-headless/connect/tools/claude-code.md (resource) a265d426b926b01d
  [NEW ] hostinger-headless/connect/tools/codex.md (resource) 24ee36b9b0a7d83c
```

## notion - drift excerpt

```
  [DRIFT] (identity) (IDENTITY)
```

## heroku - drift excerpt

```
  [DRIFT] list_apps (LOOSENED) ece815b5aa8564e1 -> b79f04decf65996c
  [DRIFT] get_app_info (LOOSENED) 35dab0520d88276d -> eaf6e2824a792635
  [DRIFT] create_app (LOOSENED) d3562895736705cd -> f8d8a7033c52e4f4
  [DRIFT] rename_app (LOOSENED) a62b015cff2c4548 -> d8a1f3089e2c38d4
  [DRIFT] maintenance_on (LOOSENED) 0769ff6fae6a743e -> b5e6fd9687b83925
  [DRIFT] maintenance_off (LOOSENED) d0c1d0f6cc7ccd2d -> 0b3a2d6dd9ceca0d
  [DRIFT] get_app_logs (LOOSENED) 213d2848b1d5b3a5 -> ae834d7e3a619c36
  [DRIFT] list_private_spaces (LOOSENED) 36e63fce5ccbf8af -> 04e76cfe86561d0e
  [DRIFT] list_teams (LOOSENED) dca82d220f77c0c7 -> 411a6d3a4717f519
  [DRIFT] list_addons (LOOSENED) f1881fb4d6acccad -> 8028b561960b72c6
  [DRIFT] get_addon_info (LOOSENED) d2b27b0c58eb0d28 -> 0d6b9ab1f5edd583
  [DRIFT] create_addon (LOOSENED) 905b74fcbd1a31e6 -> 19da0d9d8c6e3e9a
```

## context7 - drift excerpt

```
  [DRIFT] query-docs (EXPANDED) 219df2124ef8c1a3 -> 001cabe9b73dae93
```

## launchdarkly - drift excerpt

```
  [DRIFT] get-audit-log-entries (EXPANDED) b94f0dedfd785cac -> 43f3761b2bac4d76
  [DRIFT] create-feature-flag (EXPANDED) 0dd921a1c28c610b -> 413a9da09106d59a
  [NEW ] list-metrics 295e42ca0f080a2d
  [NEW ] create-metric 64173c079ac0e990
  [NEW ] get-metric 84cdf6706dc6e59f
  [NEW ] update-metric cbb97ce6b198835c
  [NEW ] list-experiments 10bae8ce998e8e15
  [NEW ] create-experiment 6d74b501ac332500
  [NEW ] get-experiment b3a9d494411a9390
  [NEW ] update-experiment dce3158562c35b16
  [NEW ] create-experiment-iteration 706dcef8a4e5cbc6
  [NEW ] list-experiments-any-environment 0937f7eec2db3ce7
```
