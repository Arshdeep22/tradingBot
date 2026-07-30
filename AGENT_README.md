# Autonomous Optimizer Agent — Quick Guide

A self-improving trading-bot agent. Every iteration it runs a backtest, asks an LLM
(SAP AI Core / Claude) to diagnose problems and propose code changes, applies the
changes on `main`, re-runs the backtest, and reverts if things get worse.

## Prerequisites

- Python 3.12
- Windows PowerShell
- `pip install -r requirements.txt`
- SAP AI Core credentials (already baked into `run_agent.ps1`)

## Run the agent

```powershell
powershell -ExecutionPolicy Bypass -File .\run_agent.ps1
```

Live logs stream to the console **and** `logs/agent_<timestamp>.log`.
Press **Ctrl+C** to stop.

Tail logs from a second terminal:

```powershell
Get-Content logs/agent_*.log -Wait -Tail 30
```

## Dashboard

Streamlit dashboard runs separately:

```powershell
streamlit run dashboard/app.py
```

Then open http://localhost:8501. The **🤖 Agent Monitor** page auto-refreshes from
`autonomous_optimizer/context/session_state.json`.

## What each log line means

| Log line                                       | Meaning                                       |
| ---------------------------------------------- | --------------------------------------------- |
| `[Iteration N] Phase A/B/C`                    | Start of a new iteration                      |
| `[analyzer] LLM PROMPT (...)`                  | Input sent to root-cause LLM                  |
| `[analyzer] LLM REPLY (...)`                   | Model's root-cause verdict                    |
| `[strategist] LLM PROMPT/REPLY`                | Picks hypothesis + target files               |
| `Coder: hypothesis '...' targets N file(s)`    | Files the coder will read                     |
| `READ  path (N bytes, M lines)`                | File successfully read                        |
| `READ  path DOES NOT EXIST — ... HALLUCINATE`  | LLM asked for a non-existent path             |
| `[coder] LLM PROMPT (max_tokens=16384)`        | Coder LLM call (full-file rewrite)            |
| `PROPOSED path X -> Y lines (+/-Z)`            | Change validated, ready to apply              |
| `Git snapshot @ <sha>`                         | Pre-change checkpoint on `main`               |
| `WROTE path (N bytes)`                         | Change written to disk                        |
| `Diff summary: ...`                            | `git diff --stat` of the applied change       |
| `Post-change Tier 1 failed ... — reverting`    | Change made backtest worse → hard reset       |

## Change the model

Edit `$env:AICORE_MODEL` in `run_agent.ps1`. To see all deployed models:

```powershell
py -3.12 list_deployments.py
```

Recommended: `anthropic--claude-4.7-opus` (best throughput). `claude-4.8-opus`
is available but heavily rate-limited.

## Important behavior

- **Agent commits directly to `main`.** Every code change is either committed on
  success or `git reset --hard` reverted on failure (`config.py::agent_branch`).
- **Tracked files survive reverts; untracked ones do NOT.** If you add helper
  files, `git add` and commit them or they'll be wiped by the next revert.
- **Session state** lives at `autonomous_optimizer/context/session_state.json`.
  Delete it to reset iteration counter, memory, and phase.
- **Sub-processes force UTF-8 + `errors='replace'`** so binary output (charts,
  PNGs) doesn't crash the backtest reader.

## Known limitation

`historical_trainer.runner` currently doesn't emit
`reports/training/latest_backtest_result.json`, so every proposed change fails
Tier-1 validation and gets reverted. Fix the historical trainer output path first
if you want the agent to actually converge on a better strategy.

## Key files

```
run_agent.ps1                            # entry point
autonomous_optimizer/
  __main__.py                            # python -m autonomous_optimizer
  agent.py                               # main iteration loop
  config.py                              # tunables (thresholds, model, branch)
  code_editor.py                         # safe file writes (UTF-8, syntax check)
  backtest_runner.py                     # subprocess wrapper for tier1/tier2
  git_ops.py                             # snapshot + revert
  llm/
    client.py                            # LLM call w/ retries + fence stripping
    analyzer.py                          # root-cause verdict
    strategist.py                        # hypothesis + target_files
    coder.py                             # full-file rewrites
    critic.py, reflector.py, observer.py # gates + context builders
core/llm_advisor.py                      # SAP AI Core auth + chat