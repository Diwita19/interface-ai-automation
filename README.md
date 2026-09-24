# Computer-Use Automation System

This project turns a workflow discovered through a browser into a reusable automation capability. The demonstration retrieves a member's savings balance from a synthetic credit-union application.

Gemini observes the live UI and proposes individual actions. After discovery succeeds, a compiler produces a typed capability containing the actions, runtime inputs, checkpoints, and output rules. Replay follows that capability without model decisions. When manual review is required, the operator takes over the same browser session and returns control after verification.

All account lookups use browser interactions. The automation does not read the application's data dictionary or call a business API.

## What is implemented

- Gemini discovery through Playwright, with a 12-action limit.
- Versioned capabilities with parameterized inputs and verified outputs.
- Replay with planner and Gemini SDK imports blocked.
- Separate outcomes for successful retrieval, missing members, and execution failures.
- Bounded waits for UI readiness and bounded retries for selected Gemini server errors.
- Same-session human review with ownership tracking and verified resume.
- Sanitized discovery logs, structured verification errors, and DOM failure snapshots.

The implemented workflow is savings-balance retrieval. [REPORT.md](REPORT.md) describes the architecture, trade-offs, and proposed extensions for desktop applications and multiple institutions.

## Setup

The demonstrated environment is Windows PowerShell, Conda, and Python 3.12. Browser runs open a visible Chromium window, so a desktop session is required.

```powershell
git clone https://github.com/Diwita19/interface-ai-automation.git
cd interface-ai-automation

conda create -n interface-ai python=3.12 -y
conda activate interface-ai

python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pip check
```

If the environment already exists, activate it and continue with installation. The requirements file pins direct dependencies; it is not a complete transitive lockfile.

### Gemini configuration

Live discovery requires a Gemini API key. Create a local `.env` file in the project root:

```dotenv
GEMINI_API_KEY=replace_with_your_own_key
GEMINI_MODEL=gemini-2.5-flash
```

The recorded discovery used `gemini-2.5-flash`. Provider access, quotas, and charges depend on the account. Existing environment variables take precedence over `.env`.

The `.env` file is excluded from Git. Compilation and replay require no Gemini credentials or live model service.

## Start the application

In the first terminal:

```powershell
conda activate interface-ai
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "0"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The application runs at http://127.0.0.1:8000/.

Leave this terminal running. Use a second terminal in the repository root, with `interface-ai` activated, for automation commands.

Restart the server after changing fixture settings. Use one server process because review sessions are stored in memory.

## Replay the saved capability

Run the capability from the latest successful discovery:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.discovery-333ac195.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

Expected result: `passed`, eight completed steps, and exit code `0`.

This capability was discovered using member `10002` and successfully replayed using member `10001`. The wrapper blocks planner and Gemini SDK imports and removes Gemini environment credentials from the replay process.

| Synthetic member | Savings balance | Currency |
| --- | --- | --- |
| `10001` | `1250.50` | USD |
| `10002` | `987.65` | USD |

The optional `--expected-balance` argument is a test assertion. It is not a workflow input supplied to the replay engine.

## Discover and compile a capability

Keep the server in normal mode with review disabled:

```powershell
python -m automation.discovery_demo --member-id 10002 --goal "Retrieve the member's savings account balance." --entry-point "http://127.0.0.1:8000/" --report-dir evidence
$LASTEXITCODE
```

Discovery observes the page, requests a typed action, validates it, and executes it. It allows at most 12 actions, with a 15-second pause between successive planning steps.

The goal accepts the supported retrieve/get/find phrasings for the member's savings account balance. The entry point must be the approved application's root URL. The verifier and compiler currently support this workflow only.

A successful run prints a `record_path` and a `discovery_log_path`. Use the exact record path to compile:

```powershell
$discoveryRecord = "runs/discovery-REPLACE_WITH_PRINTED_RUN_ID.json"

python -m automation.compile_capability --record $discoveryRecord --output capabilities/get_savings_balance.new.json --evidence-output evidence/discovery-new.sanitized.json
$LASTEXITCODE
```

After compilation succeeds:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.new.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

The compiler refuses to overwrite existing output files. Choose new filenames for subsequent compilations.

Compilation requires the original discovery record. The sanitized summary and diagnostic log are review evidence, not compilation inputs.

### Discovery diagnostics and provider errors

Discovery records stage transitions, timings, sanitized page paths, proposed actions, and model-request attempts. Failed runs retain the completed-step count and identify the failing phase and step. A sanitized DOM snapshot is captured when a page is available.

Gemini HTTP errors `500`, `502`, `503`, and `504` receive at most three application-level attempts, with delays of 5 and 10 seconds. Each attempt has a configured 30-second request timeout, and SDK retries are disabled to avoid nested retry loops. Other API errors are reported without application-level retries.

Retries apply to model requests. They do not repeat browser actions.

Controlled tests verified recovery from a simulated `503` on the second attempt and a structured stop after three simulated `503` responses. The latest live discovery completed all eight model requests on their first attempt; it did not need retries.

## Test outcomes and failures

These commands use the default capability, `capabilities/get_savings_balance.v1.json`. Keep the server in normal mode with review disabled.

```powershell
# A correctly formatted member ID that does not exist.
python -m automation.replay_without_model --member-id 99999 --report-dir evidence

# An intentionally incorrect expected balance.
python -m automation.replay_without_model --member-id 10002 --expected-balance 1250.50 --report-dir evidence

# An invalid member ID.
python -m automation.replay_without_model --member-id abc --report-dir evidence

# Run the five-case evaluation.
python -m automation.evaluate_replay
$LASTEXITCODE
```

| Status | Meaning |
| --- | --- |
| `passed` | Execution and verification succeeded. |
| `not_found` | The application reported that the member does not exist. |
| `failed` | Validation, execution, or verification failed. |

An ordinary missing-member result exits with code `0`. Supplying an expected balance makes a missing-member result fail that assertion. Failed runs exit with a nonzero code.

The five-case evaluation passed. It checks statuses, outputs, exit codes, saved-output redaction, event persistence, and the absence of unexpected handoff events. This evaluation uses the default capability; the latest compiled capability was separately verified with the explicit replay command above.

### UI fixtures

Stop the server, change `DEMO_UI_VARIANT`, and restart it to exercise a fixture. Keep review disabled.

| Variant | Application behavior | Expected replay behavior |
| --- | --- | --- |
| `normal` | Displays the usual savings link. | Complete successfully |
| `delayed_link` | Inserts the link after 2 seconds. | Wait and continue |
| `late_link` | Inserts the link after 15 seconds. | Stop when the target wait expires |
| `renamed_link` | Changes the label to “Open savings”. | Report a missing target |
| `duplicate_link` | Displays two matching savings links. | Report an ambiguous target |

The recorded delayed-link run recovered after a 1.843-second wait. The late-link run stopped after a 5.007-second wait. These are observations from individual runs, not performance guarantees.

Checkpoint failures identify the failed check, execution phase, step where applicable, and safe expected/observed descriptions. A separate test changed the final success heading to a nonexistent heading. Replay completed the eight actions, then correctly failed final checkpoint verification and saved a DOM snapshot.

## Human review

Restart the application with review enabled:

```powershell
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "1"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The recorded handoff demonstration used this capability:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.discovery-1d44ea2b.json --member-id 10002 --expected-balance 987.65 --report-dir evidence --handoff-timeout 180
$LASTEXITCODE
```

When the terminal displays `HUMAN CONTROL`:

1. In the browser opened by replay, check **I have reviewed this request**.
2. Select **Confirm review**.
3. Return to the terminal and enter `resume`.

Replay verifies the captured acknowledgement and submission, the expected page, and the member identity before restoring automation ownership.

Enter `cancel` to stop. The handoff expires when its configured time limit is reached. The default is 180 seconds; supported values are 1–600 seconds.

This is a synthetic acknowledgement, not authorization for a financial transaction. The implementation handles this known review gate. Other unexpected conditions produce a failure report.

## Evidence

[evidence/README.md](evidence/README.md) maps the selected records to their demonstrations.

| Demonstration | Evidence file |
| --- | --- |
| Latest live discovery, including request attempts | `evidence/discovery-log-333ac195c071424c875e77210b2c731d.json` |
| Compiled discovery summary | `evidence/discovery-333ac195c071424c875e77210b2c731d.sanitized.json` |
| Latest example capability | `evidence/get_savings_balance.discovery-333ac195.json` |
| Model-free replay for another member | `evidence/replay-d778e5df0e134308831059e4657e3939.json` |
| Human takeover and verified resume | `evidence/replay-126efdce178343809a0246aec252e6cb.json` |
| Delayed-target recovery | `evidence/replay-510f6cb6140641ecb849e92bbfefa37d.json` |
| Bounded target failure | `evidence/replay-f064f004d13e4bff84d585b4fda32a47.json` |
| Final checkpoint mismatch | `evidence/replay-ff8295e1eace4962b511186e31dd58b1.json` |
| Five-case evaluation | `evidence/evaluation-replay.json` |
| Injected discovery failure with retained step history | `evidence/discovery-log-2d84be79e55d462cb94ecda21e974f43.json` |

The latest example capability is a byte-for-byte copy of `capabilities/get_savings_balance.discovery-333ac195.json`.

The handoff and checkpoint-mismatch demonstrations used the earlier `discovery-1d44ea2b` capability. The readiness fixtures are retained from earlier runs. These records demonstrate their stated behaviors without implying that every test used the latest artifact.

The injected discovery failure used a mocked planner: one fill action succeeded, then the second planner call raised an exception. It made no Gemini request. The live discovery and simulated provider-retry tests are separate checks.

## Safety and data handling

The browser policy restricts automation to the approved origin, routes, controls, and read fields. Financial writes are outside the workflow. During human review, a temporary permission allows one scoped form submission.

Raw discovery records remain in the ignored `runs/` directory. They contain synthetic paths and values needed by compilation. Observations sent to Gemini can contain synthetic values, so this demonstration must not be used with real customer data.

Published discovery evidence uses templated member paths and redacted output values. Action-purpose descriptions are static descriptions, not recorded model reasoning. A source SHA-256 links a capability and summary to the original record; it does not independently prove execution.

DOM snapshots retain approved static labels and structure while excluding attributes, tokens, scripts, and unknown text. This sanitizer covers the demo's main document, not arbitrary application surfaces.

Saved replay reports redact extracted outputs. Replay console output displays synthetic results; discovery console output redacts them. Secrets and raw discovery records are excluded from Git.

## Project structure

All Python modules below are under `automation/` unless otherwise stated.

| Modules or directory | Responsibility |
| --- | --- |
| `discovery_demo.py`, `planner.py`, `observer.py` | Model-driven discovery |
| `discovery_logging.py`, `model_errors.py` | Discovery diagnostics and provider-error details |
| `contracts.py`, `capability.py`, `compile_capability.py` | Typed actions and capability compilation |
| `replay.py`, `executor.py`, `verification.py`, `business_outcomes.py` | Execution, verification, and outcomes |
| `policy.py`, `network_guard.py` | Action and browser-request restrictions |
| `session_control.py`, `handoff.py` | Ownership transfer and verified resume |
| `run_reporting.py`, `failure_evidence.py` | Reports and sanitized snapshots |
| `demo_app/` | Synthetic application and review UI |
| `capabilities/` | Reusable artifacts |
| `evidence/` | Demonstration and evaluation records |

See [REPORT.md](REPORT.md) for design decisions and limitations.