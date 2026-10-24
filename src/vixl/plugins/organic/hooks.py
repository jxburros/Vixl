"""Registry hooks for organic shapes."""


def normalize(kind, op, note):
    if kind == "organic":
        from ...normalize import illustration_alias

        return illustration_alias(op, note)
    return op
