"""Registry hooks for charts, tables and key-value lists."""


def normalize(kind, op, note):
    if kind in ("chart", "chart-data"):
        from .charts import normalize as normalize_chart

        return normalize_chart(op, note)
    if kind in ("table", "table-data"):
        from .tables import normalize as normalize_table

        return normalize_table(op, note)
    if kind == "key-value-list":
        from .key_values import normalize as normalize_key_values

        return normalize_key_values(op, note)
    return op


def validate_layer(layer, state, project):
    if "table" in layer and layer["type"] == "group":
        from .tables import validate_table

        validate_table(layer, state)
    if "key_values" in layer:
        from .key_values import validate

        validate(layer, state)
    if "chart" in layer:
        from .charts import validate_chart

        validate_chart(layer, state)
