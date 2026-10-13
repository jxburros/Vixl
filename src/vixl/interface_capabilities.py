"""Interface policy shared by REST enforcement and the generated capability matrix."""

from .studio import REST_ACTIONS as STUDIO_REST_ACTIONS

REST_WORKFLOWS = frozenset({
    "check", "act", "plan", "film-plan", "lyric-video-plan", "organic-catalog", "form-fill",
    "drawing-report", "links", "repair-layout", "protected-edit",
} | STUDIO_REST_ACTIONS)


def markdown_table():
    from .workflows import ACTIONS

    rest = ", ".join(f"`{name}`" for name in sorted(REST_WORKFLOWS))
    all_actions = f"All {len(ACTIONS)} registered actions"
    rows = [
        ("Documents per session", "One fixed document", "Multiple, inside the workspace", "One active document; workspace workflows", "Multiple Project instances; Session for workflows"),
        ("Workflows", rest, all_actions, all_actions, all_actions + " via workflows.dispatch(Session, ...)"),
        ("AI tools", "Configured local providers via /ai", "Configured local providers; a second server, vixl mcp --tools ai", "Configured local providers", "Configured local providers"),
        ("Linked files outside workspace", "Forbidden", "Forbidden", "Explicit --allow-linked", "Explicit allow_linked=True"),
        ("Screen capture", "Unavailable", "Disabled by default; --allow-screen-capture or VIXL_ALLOW_SCREEN_CAPTURE=1", "Explicit screen-capture workflow", "Explicit screen-capture workflow"),
        ("Jobs", "Detached timed-out calls via /jobs; no durable workflow queue", "Durable workflow queue and detached calls", "Durable workflow queue", "Durable queue via Session/workflows"),
        ("Authentication", "Optional bearer token; required beyond loopback", "stdio: OS process access; HTTP: bearer token required beyond loopback", "OS process access", "Caller controls access"),
        ("Per-call limits", "Configurable timeout, megapixels, pages, concurrency", "Configurable timeout, megapixels, pages, concurrency", "Resource Limits; service flags for serve/view/mcp", "Resource Limits; CallLimits for service builders"),
    ]
    return "\n".join(["| Capability | REST | MCP | CLI | Python |", "| --- | --- | --- | --- | --- |",
                      *("| " + " | ".join(row) + " |" for row in rows)])
