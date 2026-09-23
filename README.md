# Computer-Use Automation System

A small computer-use system for a synthetic credit-union application: Gemini discovers a savings-balance workflow through the live browser UI; a compiler creates a typed capability; replay executes that capability without model decisions. A known review gate supports human takeover of the same browser session.

The implemented surface is a local FastAPI HTML application. It contains synthetic data only. Automation uses Playwright UI interactions, not application API calls or access to the application's data dictionary.

## Setup

The demonstrated environment is Windows PowerShell with Conda and Python 3.12. Run commands from the repository root. A visible desktop is needed because browser runs are headed.

```powershell
conda create -n interface-ai python=3.12 -y
conda activate interface-ai
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pip check
```

Skip environment creation if `interface-ai` already exists. The requirements pin six direct dependencies; they are not a complete transitive lockfile.

For live discovery, create a local `.env` containing your own Gemini configuration:

```dotenv
GEMINI_API_KEY=replace_with_your_own_key
GEMINI_MODEL=gemini-2.5-flash
```

The named model was used in the recorded demonstration. Live discovery requires provider access and is subject to the account's availability, quota, and pricing. Existing environment variables take precedence over `.env`. Never commit the real key. Compilation and replay require no live model service.

## Start the target application

In one terminal, activate the environment and run:

```powershell
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "0"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Leave it running. Use a second terminal in the same project, with `interface-ai` activated, for the following commands. Restart the server after changing fixture environment variables. Use one server process: review sessions are held in memory.

## Replay without a live model

Replay the capability produced by the latest demonstrated discovery:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.discovery-054181a6.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

Expected: `passed`, eight executed steps, the declared outputs, and exit code `0`. This wrapper reports blocked planner/Gemini imports and removed Gemini environment credentials. The optional expected balance is a test assertion, not an input to replay or discovery.

The latest discovery used member `10002`; this replay used `10001`, demonstrating parameter reuse. Synthetic balances are `1250.50` for `10001` and `987.65` for `10002`.

## Discover, compile, and replay a new capability

```powershell
python -m automation.discovery_demo --member-id 10002 --goal "Retrieve the member's savings account balance." --entry-point "http://127.0.0.1:8000/"
$LASTEXITCODE
```

Discovery makes real Gemini requests, pauses 15 seconds between requests, and stops after at most 12 actions. A successful run prints its `record_path`. Goals are intentionally restricted to the supported retrieve/get/find phrasings for the member's savings account balance. The entry point must be the policy-approved root page. This is not an arbitrary-workflow agent.

Set the following variable to the exact `record_path` printed by that successful run:

```powershell
$discoveryRecord = "runs/discovery-REPLACE_WITH_PRINTED_RUN_ID.json"
python -m automation.compile_capability --record $discoveryRecord --output capabilities/get_savings_balance.new.json --evidence-output evidence/discovery-new.sanitized.json
$LASTEXITCODE
```

Only after compilation succeeds:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.new.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

Compiler destinations must be new filenames; existing files are not overwritten. The original discovery record is the compilation input. Its sanitized derivative is evidence and cannot be used as compilation input.

## Outcomes and injected failures

The following commands use the existing default capability, `capabilities/get_savings_balance.v1.json`:

```powershell
# Known business outcome: no such member. Omit an expected balance.
python -m automation.replay_without_model --member-id 99999 --report-dir evidence

# Intentional test assertion failure.
python -m automation.replay_without_model --member-id 10002 --expected-balance 1250.50 --report-dir evidence

# Invalid runtime input.
python -m automation.replay_without_model --member-id abc --report-dir evidence

# Existing five-case evaluation, with the normal server running.
python -m automation.evaluate_replay
```

Replay distinguishes `passed`, `not_found`, and `failed`. A supplied expected balance makes a not-found result fail the fixture assertion. CLI failures return nonzero status; ordinary not-found is a business outcome. Reports redact output values; replay console output intentionally shows synthetic results.

To inject a UI condition, stop the server, change `DEMO_UI_VARIANT`, and restart it with the same Uvicorn command. Keep review disabled for these tests.

| Variant | Behavior | Expected replay behavior |
| --- | --- | --- |
| `normal` | Ordinary link | Success |
| `delayed_link` | Link inserted after 2 seconds | Readiness wait and recovery |
| `late_link` | Link inserted after 15 seconds | Target-not-found after bounded waiting |
| `renamed_link` | Link becomes “Open savings” | Saved “View savings” target is not found |
| `duplicate_link` | Two matching links | Ambiguous-target failure |

The demonstrated delayed-link run recovered in 1.843 seconds; the late-link run failed after a 5.007-second target wait. These are individual observations, not performance guarantees. Failure reports reference a sanitized DOM snapshot when capture succeeds; pre-browser failures report why no snapshot is available.

## Human takeover

Restart the target with:

```powershell
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "1"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Run replay in the other terminal:

```powershell
python -m automation.replay_without_model --member-id 10002 --expected-balance 987.65 --report-dir evidence --handoff-timeout 180
```

At the review screen, check the acknowledgement and select **Confirm review** in the existing browser. Type `resume` in the terminal. The system verifies captured review actions and the expected page/member identity before restoring automation ownership. Type `cancel` to stop; inactivity expires the handoff. The supported timeout range is 1–600 whole seconds.

This is a synthetic acknowledgement, not authorization for a financial transaction. Human takeover is implemented for this known review gate; other unexpected conditions stop with a failure rather than invoking a general operator workflow.

## Evidence and data handling

| Demonstration | Evidence file |
| --- | --- |
| Fresh Gemini discovery | `evidence/discovery-054181a6079c4655972c901b3dc13ebc.sanitized.json` |
| Replay for a different member, after UI changes | `evidence/replay-dff94ddfe614433382fb132182d963c1.json` |
| Human takeover and resume, after UI changes | `evidence/replay-e140457458d2465aa0534289f059fd34.json` |
| Transient readiness recovery | `evidence/replay-510f6cb6140641ecb849e92bbfefa37d.json` |
| Bounded target failure | `evidence/replay-f064f004d13e4bff84d585b4fda32a47.json` |
| Associated replay failure observation | `evidence/failure-dom-8539e52a66194d12b54c8f7bcd1911b1.json` |
| Final five-case evaluation | `evidence/evaluation-replay.json` |
| Injected discovery failure; no model request | `evidence/discovery-failure-6b0c343683514916b6017459d02e77cd.json` |
| Associated discovery failure observation | `evidence/failure-dom-1bf413666a3a425eb05dc8ecf4db0186.json` |

The reusable capability is `capabilities/get_savings_balance.discovery-054181a6.json`. Include an identical copy under `evidence/` when packaging the submission.

After the UI changes, normal replay, human takeover and resume, and all five evaluation cases passed. The evaluation checks statuses, outputs, exit codes, saved-output redaction, event persistence, and absence of unexpected handoff events.

The discovery failure test deliberately injected a planner exception after the browser opened and the page was observed. It verified structured failure reporting and sanitized DOM capture before browser cleanup, without making a Gemini request. This test is separate from the genuine successful Gemini discovery.

Raw discovery records in ignored `runs/` retain synthetic paths and values required by compilation. Discovery sends page observations to Gemini; it is not a real-PII processing pipeline. Sanitized discovery evidence removes concrete member paths and output values. Its descriptions are static action-purpose summaries, not recorded model explanations. The source SHA-256 links the derivative and capability to the original record; it is not independent proof of execution.

DOM failure evidence retains approved static labels and structure, excludes attributes and unknown text, and omits scripts, templates, and embedded surfaces. It is specific to this demo, not a general financial-data sanitizer. Review tokens are kept in live session state and excluded from these snapshots.

Saved replay reports redact extracted output values. Replay console output displays synthetic values for demonstration; discovery console output redacts them. Secrets and raw discovery records must remain excluded from the public repository.

## Code map and design

- `discovery_demo.py`, `planner.py`, `observer.py`: bounded model-driven discovery.
- `contracts.py`, `capability.py`, `compile_capability.py`: typed actions and reusable artifact compilation.
- `replay.py`, `executor.py`, `business_outcomes.py`: execution, checkpoints, and outcomes.
- `policy.py`, `network_guard.py`: UI and browser request restrictions.
- `session_control.py`, `handoff.py`, `demo_app/review.py`: session ownership and review.
- `run_reporting.py`, `failure_evidence.py`: structured reports and sanitized observations.

See [REPORT.md](REPORT.md) for trade-offs, safety limits, and proposed desktop/multi-tenant extensions.