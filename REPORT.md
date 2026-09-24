# Architecture

The system implements savings-balance retrieval against a local synthetic credit-union application. Gemini proposes one typed action from the current ARIA observation and successful action history. Python validates the proposal, and a policy-constrained Playwright executor performs it. Discovery ends when the outputs are verified, an error occurs, or the 12-action limit is reached.

Discovery, compilation, and replay are separate phases. The compiler turns a successful record into a reusable capability. Replay follows saved actions without model decisions; its isolation wrapper blocks planner and Gemini SDK imports and removes Gemini environment credentials. FastAPI provides the test application only. Automation uses rendered controls rather than application data access or business API calls.

Semantic locators reduce dependence on layout, but require usable accessibility semantics. The CLI accepts a goal and entry point while limiting both to the supported workflow. This deliberate scope matches the verifier and compiler.

# Artifact schema

A capability contains an ID and version, source run ID and SHA-256, typed inputs, ordered actions, before/after checkpoints, output definitions, and a final success checkpoint. Member IDs must contain five ASCII digits. Targets use exact labels, roles and names, or table row labels. Output rules check identity, literal values, and formats. Monetary amounts remain decimal-formatted strings.

The compiler replaces observed member paths with `{member_id}` templates. It checks step numbering, supported paths, output fields, and recorded values. Adjacent observations supply intermediate postconditions; known page headings and savings-account rules supply workflow-specific checks. This is a constrained compiler, not a general workflow synthesizer.

Serialization is checked by round-tripping the typed artifact. The source hash links the artifact to the original record; it does not establish authenticity or authorization. Sanitized discovery summaries and diagnostic logs are separate evidence and cannot replace the original compilation input.

# Determinism & error handling

Replay validates inputs and policy before navigation, then verifies URLs, headings, member identity, filled values, and outputs. Target resolution uses bounded waits and rejects ambiguity. Readiness recovery waits for a control without repeating a submitted action. Determinism refers to the saved decision path, not fixed execution timing.

Results distinguish success, a known member-not-found outcome, and failure. Target errors include structural resolution details. Verification errors identify the check, phase, applicable step, and safe expected/observed descriptions. Operation events preserve timing and completion or failure status. Discovery logs retain stage history, proposed actions, model attempts, completed-step counts, and failure context. Available pages are captured as sanitized DOM evidence before browser cleanup.

Gemini requests retry HTTP 500, 502, 503, and 504 up to three attempts, with 5- and 10-second delays. Requests have a configured 30-second timeout, and SDK retries are disabled to avoid nested retries. Other API errors stop without application-level retries. Exhaustion produces a structured provider error. Browser actions are not repeated by this mechanism.

The latest live discovery completed eight actions for member 10002, and its compiled capability replayed successfully for member 10001 with model imports blocked. All live model requests succeeded on their first attempt. Separate mocked tests verified recovery from a 503 and termination after three consecutive 503 responses; these do not demonstrate recovery during a live provider outage.

Other checks covered five evaluation cases, human resume, delayed-target recovery, bounded target failure, and a deliberately incorrect final heading. An injected planner failure after one successful action verified retained history and failure capture without a Gemini request. The evidence index identifies the artifacts used by each demonstration.

# Heterogeneity & multi-tenant

A proposed surface-adapter interface would expose observation, target resolution, action execution, checkpoint verification, and sanitized evidence capture. Flow order and output rules would remain independent of Playwright. Additional target types could support frame-scoped legacy pages, OS accessibility controls, and bounded visual anchors. Visual targeting would require window identity, scale, confidence thresholds, and postcondition checks. These adapters are not implemented.

For multiple institutions, a shared vendor capability would declare its product family, compatible versions, and target/checkpoint profile. A tenant binding would provide an approved origin, credential references, and reviewed locator or branding overrides. Overrides could not widen policy or change output semantics without review.

Preflight checks and fixture replays would identify incompatible bindings. Updates would preserve the previous approved version and require promotion before use. Browser contexts, credentials, evidence access, and ownership would be isolated per tenant. The current prototype is single-tenant and has no registry or distributed execution service.

# Escalation & handoff

The known manual-review screen triggers an intervention event containing the capability, goal, step, reason, timeout, and instructions. The existing browser and terminal provide the operator interface. Ownership moves from automation to human, then to stopped during resume verification, and back to automation only after the checks pass.

The system captures acknowledgement and submission events in the same session. Resume verifies those events and the expected page and member identity. Cancellation and timeout terminate the handoff, and cleanup revokes unused submission permission.

This implementation supports one review gate. A general operator service would need authenticated assignment, session references, sanitized observations, and an exclusive ownership lease. Current capture covers the known review controls, not every manual browser action. The terminal input thread is intended for a short-lived CLI.

# Safety

The baseline policy permits one origin, approved routes and query keys, GET requests, and specific fill/click/read targets. Browser contexts disable service workers and downloads. The guard blocks WebSockets and redirects and disables automatic retries for guarded browser requests. It is not an OS-level network sandbox and does not control the separate Gemini connection.

Human ownership temporarily permits one form-encoded main-frame POST to the designated member's review page with the expected Origin. Permission is consumed before sending. The server checks a member-bound session, expiry, Origin, content type, bounded body, exact fields, acknowledgement, and CSRF token. Sessions last 600 seconds; handoff defaults to 180 seconds. Cookies use HttpOnly and SameSite Strict, with Secure disabled for local HTTP. State assumes one server process.

Only synthetic data is supported. Raw records stay in ignored `runs/`; model observations may contain synthetic values. Published logs redact outputs and constrain recorded action metadata. DOM evidence excludes attributes, tokens, and unknown text. Static purpose descriptions are explicitly distinguished from model reasoning.

These measures are specific to the demo. Production use would require approved data boundaries, upstream minimization, retention controls, and broader redaction testing. Financial writes are unsupported, and the review acknowledgement is not banking authorization.

# Cuts

Desktop adapters, cross-tenant infrastructure, general escalation, production authentication, financial writes, and a capability catalog are outside this implementation. Replay has no model fallback. Goal handling, compilation, and business-outcome recognition remain specific to savings-balance retrieval.

Testing covers the implemented workflow and selected failure conditions, not exhaustive production behavior. Unexpected dialogs, permission changes, and session changes lack dedicated semantic classifiers. Future work would prioritize artifact approval and compatibility checks, richer outcome classification, and additional adapters. Model reasoning is not persisted; published action-purpose descriptions are static. The prototype prioritizes an inspectable discovery-to-replay workflow with explicit failure handling.