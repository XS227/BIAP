# Mobile apps - Step 0 (locate), 2026-11-03

Task file: /tmp/fc378dd4-ad25-456d-95f2-f60628711df3.txt (the named /home/ubuntu/PROMPT_MOBILE_APPS.txt does not exist on the server).

| | BIAP Global | BIAP Iran |
|---|---|---|
| Project dir | `mobile-global/` | `mobile/` |
| Package id | `com.biap.global` | `com.biap.mobile` |
| Version on live/base-20261030 | 0.3.23 (versionCode 26) | 1.0.5 (versionCode 6) |
| Version this task starts from | 0.3.23 / 26 | **1.0.7 / 8** (see below) |
| API | `GLOBAL_API_BASE` = `https://biap.dadashi.no/global-api` (service `biap-global`, :8089?) | `API_BASE` = `https://biap.dadashi.no/api` (service `biap-fin`, uvicorn :8088, `~/biap-kiasha/XS227-BIAP/analysis`) |
| Branch / worktree | `feat/mobile-global-20261103` / `/home/ubuntu/biap-mobile-global-wt` | `feat/mobile-iran-20261103` / `/home/ubuntu/biap-mobile-iran-wt` |
| APK workflow | `biap-global-apk.yml` (debug-keystore signing, branch feat/biap-global), `publish-biap-global-apk.yml` | `expo-eas-build.yml` (EAS, `EXPO_TOKEN` secret, working dir `mobile`) |
| Last successful build | not yet identified | Expo EAS build run #10 = fb3bce3 (1.0.7), #9 = e38e9b9 (1.0.6) on `fix/iran-codal-evidence-20261028` |
| Local APKs | - | `~/biap-kiasha/iran-apk-1.0.6-preview`, `release-check-iran-1.0.7-20261028` |

## Findings
1. **Iran 1.0.7 is not on live/base-20261030.** It lives on `origin/fix/iran-codal-evidence-20261028` (4 commits: CODAL totals validation + Kiasha hold on incomplete evidence, evidence-PASS gate on the Kiasha card, five-issuer CODAL review screen, canonical issuer links). Base only has 1.0.5. To avoid shipping a downgrade I merged that branch into `feat/mobile-iran-20261103` (clean merge, no conflicts, touches `analysis/kiasha.py` + a test; branch only, nothing merged to a protected branch or deployed).
2. **"Build #161" was not found** in GitHub Actions runs (Expo EAS build runs only go to #10; no commit/doc message mentions it). Probably an EAS-side build number. Needs the owner to confirm what it refers to.
3. **`biap-ai-proxy` does not exist** on this server (no unit, no directory, no listener name match, no reference in the repo). Existing LLM code: `analysis/kiasha_ai.py` calls the Anthropic API directly using `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` from `.env.ai`. Item 1b (AI Company Analysis) depends on it. Earlier notes also record Anthropic credit exhaustion. I will not invent a proxy or put a key in the app.
4. Iran agents in `analysis/agents.py`: fundamental, risk, forecast, comparison, technical, flow (6 functions) + scenario via `scenario_engine.build_scenarios` in `kiasha.py` = the seven. Global has its own six and is kept separate.
5. Mock/demo code present: both apps have `demo-mode.ts`, `demo-trading.ts`, `paper-portfolio.ts`; Iran also has `src/demo/demo-data.ts`. Which screens render demo data in production paths is checked in Step 1a.
6. Production unit file `biap-fin.service` contains a plaintext admin bootstrap password in an `Environment=` line. It appeared in my tool output once while I read the unit. I did not copy it anywhere. Recommend rotating it and moving it to an EnvironmentFile (owner action, not touched).
7. `biap-performance-evaluator.service` is in `failed` state (not touched).
