# Evidence

This index identifies the principal demonstrations and their supporting files. Commands and setup instructions are in the [root README](../README.md).

The records come from several runs. Capability names are listed where relevant so that results are not attributed to an artifact that was not used.

## Latest discovery and replay

The latest live discovery used member 10002. Its compiled capability was replayed for member 10001, returning the expected balance with model imports blocked.

| Record | File |
| --- | --- |
| Live discovery stages and model attempts | [Discovery log](discovery-log-333ac195c071424c875e77210b2c731d.json) |
| Sanitized compilation summary | [Discovery summary](discovery-333ac195c071424c875e77210b2c731d.sanitized.json) |
| Reusable capability copy | [Example capability](get_savings_balance.discovery-333ac195.json) |
| Successful replay for member 10001 | [Replay report](replay-d778e5df0e134308831059e4657e3939.json) |

The example capability is a byte-for-byte copy of `capabilities/get_savings_balance.discovery-333ac195.json`.

All eight model requests in this live discovery succeeded on their first attempt. No provider retry was needed.

## Human review

[Human takeover and resume report](replay-126efdce178343809a0246aec252e6cb.json)

This run used `capabilities/get_savings_balance.discovery-1d44ea2b.json` for member 10002. It records transfer to human ownership, acknowledgement and submission, the resume request, verification, and the return to automation. All eight replay steps completed successfully.

## Verification failure

| Record | File |
| --- | --- |
| Deliberately incorrect final heading | [Failure report](replay-ff8295e1eace4962b511186e31dd58b1.json) |
| Associated page observation | [Sanitized DOM](failure-dom-4596f151d737440bbb57e130478435cb.json) |

The test fixture copied the `discovery-1d44ea2b` capability and changed only its final success heading. Replay completed the eight actions, then failed the `checkpoint_heading` check during `final_checkpoint` verification. Exit code 1 was expected.

The modified fixture belongs under ignored `runs/`; it is not a reusable production capability.

## Discovery failure diagnostics

| Record | File |
| --- | --- |
| Retained stages and first completed action | [Discovery log](discovery-log-2d84be79e55d462cb94ecda21e974f43.json) |
| Structured failure result | [Failure report](discovery-failure-7b65f21eab0744bbbeb58aaddf84b91a.json) |
| Associated page observation | [Sanitized DOM](failure-dom-30a3e85cc6844d3b8eb899985e3b07f6.json) |

This controlled test mocked the planner. It returned a valid fill action on the first call and raised an exception on the second. Discovery retained the completed first step, identified planning at step 2 as the failure location, and captured the page before cleanup.

No Gemini request was made in this test. Exit code 1 was expected.

## Readiness and target failures

These records are retained from earlier fixture runs.

| Demonstration | File |
| --- | --- |
| Recovery after a delayed savings link appeared | [Recovery report](replay-510f6cb6140641ecb849e92bbfefa37d.json) |
| Failure when the link appeared beyond the wait limit | [Target failure report](replay-f064f004d13e4bff84d585b4fda32a47.json) |
| Associated failure observation | [Sanitized DOM](failure-dom-8539e52a66194d12b54c8f7bcd1911b1.json) |

The recorded waits were 1.843 seconds for recovery and 5.007 seconds for bounded failure. These timings describe individual runs.

## Five-case evaluation

[Evaluation summary](evaluation-replay.json)

The evaluation passed all five cases:

- Original member.
- Different member.
- Member not found.
- Incorrect expected balance.
- Invalid member format.

It uses the default `capabilities/get_savings_balance.v1.json` capability. The summary names the individual reports through each case's `report_file` field. Those reports and any referenced failure snapshots should be retained together.

The evaluator checks statuses, outputs, exit codes, saved-output redaction, event persistence, and the absence of unexpected handoff events.

## Gemini retry checks

Separate mocked tests verified that:

- A simulated HTTP 503 followed by a valid response succeeds on attempt 2.
- Three simulated HTTP 503 responses stop after attempt 3 and produce a structured `model_provider_error`.

These checks were run in the terminal. They are not live-provider recovery records, and the latest successful live discovery did not require retries.

## Data handling and interpretation

Raw discovery records remain in ignored `runs/` because compilation requires their original synthetic paths and values. Sanitized summaries and diagnostic logs are not compilation inputs.

Published discovery metadata uses templated member paths and redacted output values. Action-purpose descriptions are static, not recorded model reasoning. Source hashes link artifacts to source bytes but do not independently prove execution.

Saved replay outputs are redacted. DOM snapshots preserve approved static labels and structure while excluding attributes, tokens, and unknown text. These protections are specific to the synthetic demo.

Earlier evidence files may remain in this directory. The sections above identify the principal records for the updated submission.