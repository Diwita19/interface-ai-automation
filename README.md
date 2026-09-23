# Computer-Use Automation System

This project demonstrates how an AI-discovered browser workflow can become a reusable automation capability. It uses a synthetic credit-union application to look up a member and retrieve their savings account balance.

Gemini explores the application through its live UI and proposes individual actions. A compiler turns the successful run into a typed, parameterized capability. That capability can then be replayed for another member without calling the model. If the application requires manual review, the operator can take over the same browser session and return control after completing the review.

The application contains synthetic data only. All account lookups happen through browser interactions.

## What the demo includes

- Live discovery using Gemini and Playwright.
- A versioned capability with input parameters, actions, checkpoints, and output rules.
- Model-free replay with identity and result verification.
- Separate handling for successful lookups, missing members, and execution failures.
- Bounded waiting for temporarily unavailable controls.
- Human review with session ownership tracking and verified resume.
- Structured run reports and sanitized DOM snapshots on failure.

The implemented workflow is savings-balance retrieval. Desktop support and reuse across institutions are covered in [REPORT.md](REPORT.md) as design extensions.

## Requirements and setup

The project was developed and tested on Windows using PowerShell, Conda, and Python 3.12. Browser runs open a visible Chromium window, so a desktop session is required.

Clone the repository and enter the project directory:

```powershell
git clone https://github.com/Diwita19/interface-ai-automation.git
cd interface-ai-automation
```

Create the environment and install dependencies:

```powershell
conda create -n interface-ai python=3.12 -y
conda activate interface-ai
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pip check
```

If the environment already exists, activate it and continue with installation. `requirements.txt` pins the six direct dependencies; it does not lock every transitive dependency.

### Gemini configuration

Live discovery requires a Gemini API key. Create a `.env` file in the project root:

```dotenv
GEMINI_API_KEY=replace_with_your_own_key
GEMINI_MODEL=gemini-2.5-flash
```

The recorded discovery used `gemini-2.5-flash`. Model access, quotas, and charges depend on the provider account. Existing environment variables take precedence over `.env`.

The `.env` file is excluded from Git. Compilation and replay do not require a Gemini key or a live model service.

## Start the application

Run the application in one terminal:

```powershell
conda activate interface-ai
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "0"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to view the application.

Keep this terminal running and use a second terminal for automation commands. Activate `interface-ai` in that terminal as well. Restart the server whenever you change a fixture setting.

Use a single server process because the demo stores review sessions in memory.

## Run the saved capability

The repository includes a capability from a successful discovery run. Replay it without a live model:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.discovery-054181a6.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

A successful run completes eight steps, returns the account fields, and exits with code `0`. The wrapper blocks planner and Gemini SDK imports and removes Gemini environment credentials from the replay process.

This capability was discovered using member `10002` and then replayed using member `10001`.

| Synthetic member | Savings balance |
| --- | --- |
| `10001` | `1250.50` |
| `10002` | `987.65` |

`--expected-balance` is an optional test assertion. It is not supplied to the replay engine as a workflow input.

## Discover and compile a new workflow

With the application running in normal mode and review disabled, start discovery:

```powershell
python -m automation.discovery_demo --member-id 10002 --goal "Retrieve the member's savings account balance." --entry-point "http://127.0.0.1:8000/"
$LASTEXITCODE
```

Discovery observes the page, requests an action from Gemini, validates it, and executes it. The loop allows up to 12 actions and pauses 15 seconds between model requests.

The goal input currently accepts the supported retrieve/get/find phrasings for the member's savings account balance. The entry point must be the approved application's root URL. These limits match the implemented verifier and compiler.

When discovery succeeds, it prints a `record_path`. Use that exact path below:

```powershell
$discoveryRecord = "runs/discovery-REPLACE_WITH_PRINTED_RUN_ID.json"

python -m automation.compile_capability --record $discoveryRecord --output capabilities/get_savings_balance.new.json --evidence-output evidence/discovery-new.sanitized.json
$LASTEXITCODE
```

After compilation succeeds, replay the new capability for another member:

```powershell
python -m automation.replay_without_model --capability capabilities/get_savings_balance.new.json --member-id 10001 --expected-balance 1250.50 --report-dir evidence
$LASTEXITCODE
```

The compiler creates both a capability and a sanitized discovery summary. It refuses to overwrite existing output files, so choose new filenames when repeating this process.

Compilation requires the original discovery record. The sanitized summary is intended for review and cannot replace that input.

## Test outcomes and failures

The following commands use the default capability at `capabilities/get_savings_balance.v1.json`. Run them with the server in normal mode and review disabled.

```powershell
# A valid member ID that does not exist.
python -m automation.replay_without_model --member-id 99999 --report-dir evidence

# An intentionally incorrect expected balance.
python -m automation.replay_without_model --member-id 10002 --expected-balance 1250.50 --report-dir evidence

# An invalid member ID.
python -m automation.replay_without_model --member-id abc --report-dir evidence

# Run the five-case evaluation.
python -m automation.evaluate_replay
```

Replay returns one of three statuses:

| Status | Meaning |
| --- | --- |
| `passed` | The workflow completed and its checks passed. |
| `not_found` | The application reported that the member does not exist. |
| `failed` | Validation, execution, or verification failed. |

A missing member is a business outcome. If the test also supplies an expected balance, however, the missing member fails that assertion. Execution failures return a nonzero process exit code.

### UI fixtures

To test a UI condition, stop the server, change `DEMO_UI_VARIANT`, and restart it. Keep `DEMO_REQUIRE_REVIEW` set to `"0"` for these cases.

| Variant | Application behavior | Expected replay result |
| --- | --- | --- |
| `normal` | Displays the usual savings link. | Success |
| `delayed_link` | Inserts the link after 2 seconds. | Wait, recover, and continue |
| `late_link` | Inserts the link after 15 seconds. | Stop when the bounded target wait expires |
| `renamed_link` | Changes the label to “Open savings”. | Target not found |
| `duplicate_link` | Displays two matching savings links. | Ambiguous target |

In the recorded tests, the delayed link recovered after 1.843 seconds of waiting. The late-link case stopped after 5.007 seconds. These timings describe those individual runs.

Failures include structured diagnostics and a reference to a sanitized DOM snapshot when capture succeeds. Failures before browser creation explain why no page snapshot is available.

## Human review

Enable the review gate by restarting the server with:

```powershell
$env:DEMO_UI_VARIANT = "normal"
$env:DEMO_REQUIRE_REVIEW = "1"
python -m uvicorn demo_app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Start replay in the second terminal:

```powershell
python -m automation.replay_without_model --member-id 10002 --expected-balance 987.65 --report-dir evidence --handoff-timeout 180
```

When the terminal displays `HUMAN CONTROL`:

1. In the browser opened by replay, check **I have reviewed this request**.
2. Select **Confirm review**.
3. Return to the terminal and enter `resume`.

Replay checks the captured acknowledgement and submission, then verifies the expected page and member identity before continuing.

Enter `cancel` to stop the run. The handoff expires if it is not completed within the configured time. The default is 180 seconds; supported values are 1–600 seconds.

The review is a synthetic acknowledgement, not a financial transaction. This handoff handles the application's known review gate. Other unexpected conditions produce a failure report.

## Evidence and verification

The `evidence/` directory contains the selected discovery, replay, and failure records.

| Demonstration | Evidence file |
| --- | --- |
| Genuine Gemini discovery | `evidence/discovery-054181a6079c4655972c901b3dc13ebc.sanitized.json` |
| Example capability | `evidence/get_savings_balance.example.json` |
| Replay for another member after UI changes | `evidence/replay-dff94ddfe614433382fb132182d963c1.json` |
| Human takeover and resume after UI changes | `evidence/replay-e140457458d2465aa0534289f059fd34.json` |
| Recovery from a delayed target | `evidence/replay-510f6cb6140641ecb849e92bbfefa37d.json` |
| Bounded target failure | `evidence/replay-f064f004d13e4bff84d585b4fda32a47.json` |
| Replay failure snapshot | `evidence/failure-dom-8539e52a66194d12b54c8f7bcd1911b1.json` |
| Five-case evaluation | `evidence/evaluation-replay.json` |
| Injected discovery failure | `evidence/discovery-failure-6b0c343683514916b6017459d02e77cd.json` |
| Discovery failure snapshot | `evidence/failure-dom-1bf413666a3a425eb05dc8ecf4db0186.json` |

The example capability is an identical copy of `capabilities/get_savings_balance.discovery-054181a6.json`.

After the UI changes, normal replay, human takeover, and all five evaluation cases passed. The evaluation checks statuses, outputs, exit codes, saved-output redaction, event persistence, and the absence of unexpected handoff events.

The discovery failure test injected a planner exception after the browser opened and the page was observed. It confirmed that discovery saves a sanitized snapshot before browser cleanup and reports the failure. That test made no Gemini request; the successful discovery was a separate, genuine model-driven run.

## Safety and data handling

The browser policy limits automation to the local application's approved routes, controls, and read fields. Financial writes are outside the supported workflow. During human review, a temporary permission allows one scoped form submission.

Raw discovery records remain in the ignored `runs/` directory. They contain synthetic member paths and values needed by the compiler. Page observations sent to Gemini can also contain synthetic values, so this demo must not be used with real customer data.

Published discovery summaries replace member paths with templates and redact output values. Their action descriptions are static summaries, not recorded model explanations. A source SHA-256 links the capability and summary to the original record; it does not independently prove execution.

Failure snapshots preserve approved static labels and page structure while omitting attributes, tokens, scripts, and unknown text. This sanitizer is designed for the demo's main document and does not cover every possible application surface.

Saved replay reports redact extracted values. Replay console output shows synthetic results for inspection; discovery console output redacts them. Secrets and raw discovery records are excluded from the public repository.

## Project structure

| Location | Responsibility |
| --- | --- |
| `automation/discovery_demo.py`, `planner.py`, `observer.py` | Model-driven discovery |
| `automation/contracts.py`, `capability.py`, `compile_capability.py` | Action contracts and capability compilation |
| `automation/replay.py`, `executor.py`, `business_outcomes.py` | Replay, verification, and outcome handling |
| `automation/policy.py`, `network_guard.py` | Action and browser-request restrictions |
| `automation/session_control.py`, `handoff.py` | Ownership transfer and resume |
| `automation/run_reporting.py`, `failure_evidence.py` | Reports and sanitized snapshots |
| `demo_app/` | Synthetic application, review sessions, and shared UI |
| `capabilities/` | Saved reusable capabilities |
| `evidence/` | Selected demonstration and evaluation records |

See [REPORT.md](REPORT.md) for the architecture, implementation trade-offs, and proposed extensions for legacy applications and multiple institutions.