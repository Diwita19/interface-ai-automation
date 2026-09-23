import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page


# Only these exact static UI labels can appear as text in evidence.
# Do not add member values, balances, credentials, or arbitrary page text.
SAFE_UI_TEXT = [
    "Demo Credit Union",
    "Member search",
    "Search results",
    "Member details",
    "Savings account",
    "Member not found",
    "Invalid member ID",
    "Manual review required",
    "Review rejected",
    "Accounts",
    "Member ID",
    "Name",
    "Action",
    "Account type",
    "Available balance",
    "Currency",
    "Search",
    "Open member",
    "View savings",
    "Open savings",
    "Back to search",
    "Back to member",
    "I have reviewed this request",
    "Confirm review",
]


SANITIZED_DOM_SCRIPT = """
(body, safeLabels) => {
    const safeText = new Set(safeLabels);

    const safeTags = new Set([
        "body", "main", "section", "article", "header", "footer",
        "nav", "div", "span", "p", "hr", "br",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "thead", "tbody", "tfoot", "tr", "th", "td",
        "form", "label", "input", "button", "a",
        "select", "option", "textarea", "ul", "ol", "li"
    ]);

    const labelContainers = new Set([
        "h1", "h2", "h3", "h4", "h5", "h6",
        "label", "button", "a", "th"
    ]);

    const skippedTags = new Set([
        "script", "style", "template", "noscript",
        "iframe", "object", "embed", "svg", "canvas"
    ]);

    const safeInputTypes = new Set([
        "text", "password", "hidden", "checkbox", "radio",
        "submit", "button", "email", "number", "search"
    ]);

    const maxNodes = 1500;
    const maxDepth = 24;

    let visited = 0;
    let truncated = false;

    function visit(node, depth) {
        if (visited >= maxNodes || depth > maxDepth) {
            truncated = true;
            return null;
        }

        visited += 1;

        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent.replace(/\\s+/g, " ").trim();

            if (!text) return null;

            const parentTag = node.parentElement?.localName;
            const permitted = (
                labelContainers.has(parentTag)
                && safeText.has(text)
            );

            return {
                node: "text",
                text: permitted ? text : "[REDACTED]"
            };
        }

        if (node.nodeType !== Node.ELEMENT_NODE) {
            return null;
        }

        const tag = node.localName;

        if (skippedTags.has(tag)) {
            return {node: "omitted_element"};
        }

        const result = {
            node: "element",
            tag: safeTags.has(tag) ? tag : "other",
            children: []
        };

        if (tag === "input") {
            const inputType = node.type;

            result.input_type = safeInputTypes.has(inputType)
                ? inputType
                : "other";

            // Never read or serialize the input's value.
        }

        // No attributes, URLs, IDs, styles, or event handlers are copied.
        for (const child of node.childNodes) {
            if (visited >= maxNodes) {
                truncated = true;
                break;
            }

            const sanitized = visit(child, depth + 1);

            if (sanitized !== null) {
                result.children.push(sanitized);
            }
        }

        return result;
    }

    const tree = visit(body, 0);

    return {
        tree: tree,
        truncated: truncated,
        visited_nodes: visited
    };
}
"""


def capture_failure_evidence(
    *,
    page: Page | None,
    directory: Path,
) -> dict[str, str]:
    """Save a sanitized DOM tree without replacing the original failure."""

    if page is None:
        return {
            "status": "unavailable",
            "reason": "page_not_created",
        }

    try:
        if page.is_closed():
            return {
                "status": "unavailable",
                "reason": "page_closed",
            }

        # Sanitize in the browser before returning data to Python.
        snapshot = page.locator("body").evaluate(
            SANITIZED_DOM_SCRIPT,
            SAFE_UI_TEXT,
            timeout=2000,
        )

        document = {
            "evidence_version": 1,
            "kind": "sanitized_dom",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "redaction_policy": "demo_static_labels_only_v1",
            "scope": "main_document_body",
            "snapshot": snapshot,
        }

        serialized = json.dumps(
            document,
            indent=2,
            ensure_ascii=False,
        )

        if len(serialized.encode("utf-8")) > 1_000_000:
            return {
                "status": "unavailable",
                "reason": "snapshot_size_limit",
            }

        directory.mkdir(parents=True, exist_ok=True)
        filename = f"failure-dom-{uuid4().hex}.json"
        path = directory / filename

        with path.open("x", encoding="utf-8") as evidence_file:
            evidence_file.write(serialized)
            evidence_file.write("\n")

        return {
            "status": "saved",
            "kind": "sanitized_dom",
            "file": filename,
        }

    except Exception:
        # Never fall back to saving raw HTML or raw exception text.
        return {
            "status": "unavailable",
            "reason": "snapshot_capture_failed",
        }