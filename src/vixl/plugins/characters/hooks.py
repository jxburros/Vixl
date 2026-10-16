"""Registry hooks for characters."""


def check(checks, candidate, resolved, issue, **context):
    if "character" in checks:
        from .characters import findings

        for finding in findings(candidate):
            target = resolved.get(finding.get("layer"))
            issue("character", finding["severity"], finding["message"], [target] if target else [],
                  **{k: v for k, v in finding.items() if k not in ("check", "severity", "message", "layer")})
