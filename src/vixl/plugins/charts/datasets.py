"""Shared numeric datasets, derived chart views and merge fields without renderer coupling."""

from copy import copy, deepcopy
import json
import re

from ...errors import require
from . import charts

TYPES = ("dataset",)
MAX_DATASETS = 64
NAME = re.compile(r"[\w-]{1,64}")


def contents(state):
    """The live page plus stored pages and masters; datasets are document-wide."""
    yield state
    for record in [*(state.get("pages") or []), *(state.get("masters") or {}).values()]:
        if isinstance(record, dict) and isinstance(record.get("content"), dict):
            yield record["content"]


def all_layers(state):
    return [layer for content in contents(state) for layer in content.get("layers", [])]


def token(value):
    """Labels become case-preserving merge-field segments; collisions are refused."""
    return re.sub(r"[^\w-]+", "-", value).strip("-") or "value"


def derive_data(categories, series, derive=None):
    if derive is None:
        return deepcopy(categories), deepcopy(series)
    require(isinstance(derive, dict) and set(derive) <= {"kind", "by"}
            and derive.get("kind") in ("sum", "share", "max")
            and derive.get("by", "category") in ("series", "category"),
            "derive needs kind: sum, share or max and by: series or category", field="derive")
    kind = derive["kind"]
    by_series = derive.get("by", "category") == "series"
    names = [s["name"] for s in series] if by_series else categories
    groups = [s["values"] for s in series] if by_series else list(zip(*(s["values"] for s in series)))
    values = []
    for group in groups:
        present = [v for v in group if v is not None]
        values.append(max(present) if kind == "max" and present else None if kind == "max" else sum(present))
    if kind == "share":
        require(all(v >= 0 for group in groups for v in group if v is not None),
                "share derivation needs non-negative values", field="derive")
        total = sum(values)
        values = [v / total if total else 0 for v in values]
    return charts.clean_table(names, [{"name": kind, "values": values}])


def resolve(state, name, trail=(), memo=None, snapshot=False):
    """Follow chart sources and dataset bindings, detecting cycles before any redraw."""
    memo = {} if memo is None else memo
    require(name not in trail, f"Dataset cycle: {' -> '.join((*trail, name))}", "invalid_data", field="data")
    if name in memo:
        return memo[name]
    records = state.get("datasets", {})
    require(isinstance(name, str) and name in records, f"Unknown dataset {name!r}", "not_found", field="data")
    record = records[name]
    source = record.get("source", {})
    if "from" in source:
        group = next((layer for layer in all_layers(state) if layer.get("id") == source["from"]), None)
        if group is None and snapshot:
            # Page/artboard views omit other pages' layers; apply already saved the resolved data.
            result = charts.clean_table(record.get("categories"), record.get("series"))
            memo[name] = result
            return result
        require(group is not None and group["type"] == "group" and "chart" in group,
                f"Dataset {name!r} needs its source chart", "not_found", field="from")
        recipe = group["chart"]
        if "data" in recipe:
            categories, series = resolve(state, recipe["data"], (*trail, name), memo, snapshot)
            result = derive_data(categories, series, recipe.get("derive"))
        else:
            result = charts.clean_table(recipe.get("categories"), recipe.get("series"))
    else:
        result = charts.clean_table(record.get("categories"), record.get("series"))
    memo[name] = result
    return result


def binding(project, op, recipe):
    """Resolve a chart/table's binding; inline replacements detach it explicitly."""
    name = op.get("data", recipe.get("data"))
    require(isinstance(name, str), "data must name a dataset", field="data")
    derive = op.get("derive", recipe.get("derive"))
    categories, series = derive_data(*resolve(project.state, name), derive)
    recipe["data"] = name
    recipe.pop("source", None)
    if derive is None:
        recipe.pop("derive", None)
    else:
        recipe["derive"] = deepcopy(derive)
    return categories, series


def rows(categories, series):
    return [["Category", *(s["name"] for s in series)],
            *[[name, *(s["values"][i] for s in series)] for i, name in enumerate(categories)]]


def detach(recipe):
    recipe.pop("data", None)
    recipe.pop("derive", None)


def validate_state(project, state):
    records = state.get("datasets", {})
    require(isinstance(records, dict) and len(records) <= MAX_DATASETS,
            f"datasets holds at most {MAX_DATASETS} named datasets", "invalid_project")
    for name, record in records.items():
        require(isinstance(name, str) and NAME.fullmatch(name), "Dataset names use 1–64 letters, numbers, _ or -",
                field="name")
        require(isinstance(record, dict) and set(record) <= {"categories", "series", "source"},
                f"Invalid dataset {name!r}", "invalid_project")
        charts.clean_table(record.get("categories"), record.get("series"))
        source = record.get("source", {})
        require(isinstance(source, dict) and (not source or
                (set(source) == {"from"} and isinstance(source["from"], str)) or
                ("csv" in source and set(source) <= {"csv", "category_column", "series_columns"}
                 and isinstance(source["csv"], str)
                 and isinstance(source.get("category_column", ""), str)
                 and isinstance(source.get("series_columns", []), list)
                 and all(isinstance(v, str) for v in source.get("series_columns", [])))),
                f"Invalid dataset source for {name!r}", "invalid_project")
    # Page validation passes its isolated scoped state with the same shared dataset object.
    context = project.state if (state is not project.state and records is project.state.get("datasets")
                                and "pages" not in state and project.state.get("pages")) else state
    memo = {}
    for name in records:
        resolve(context, name, memo=memo)
    for layer in all_layers(state):
        if layer["type"] != "group":
            continue
        for key in ("chart", "table"):
            recipe = layer.get(key, {})
            if "data" in recipe:
                derive_data(*resolve(context, recipe["data"], memo=memo), recipe.get("derive"))
            else:
                require("derive" not in recipe, "derive needs a dataset binding", field="derive")
    _variables(state, memo)


def refresh(project):
    """Recompute dependents inside the apply transaction and preserve generated layer IDs."""
    records = project.state.get("datasets", {})
    if not records:
        # A removed dataset must not silently leave charts drawing their old cached values.
        for layer in all_layers(project.state):
            for key in ("chart", "table") if layer["type"] == "group" else ():
                require("data" not in layer.get(key, {}), "A bound chart or table still needs its dataset",
                        field="name")
        return
    memo = {}
    for name in records:
        resolve(project.state, name, memo=memo)
    for name, (categories, series) in memo.items():
        records[name].update(categories=deepcopy(categories), series=deepcopy(series))
    for content in contents(project.state):
        target = project
        if content is not project.state:
            from ...pages import SCOPED

            target = copy(project)
            target.state = {key: value for key, value in project.state.items() if key not in SCOPED}
            target.state.update(content)
        _refresh_content(target, project.state, memo)


def _refresh_content(project, state, memo):
    active = project.state["active_layer"]
    for layer in list(project.state["layers"]):
        if layer["type"] != "group":
            continue
        for key in ("chart", "table"):
            recipe = layer.get(key, {})
            if "data" not in recipe:
                continue
            categories, series = derive_data(*resolve(state, recipe["data"], memo=memo), recipe.get("derive"))
            data = {"categories": categories, "series": series} if key == "chart" else {"rows": rows(categories, series)}
            if any(recipe.get(k) != v for k, v in data.items()):
                from . import tables

                (charts if key == "chart" else tables).redraw(project, layer, {**deepcopy(recipe), **data})
    project.state["active_layer"] = active


def _variables(state, memo=None):
    result = {}
    for name in state.get("datasets", {}):
        categories, series = resolve(state, name, memo=memo, snapshot=True)
        cells = [(s["name"], c, value) for s in series for c, value in zip(categories, s["values"])]
        values = {"total": sum(value for _, _, value in cells if value is not None)}
        present = [(s, c, value) for s, c, value in cells if value is not None]
        if present:
            largest = max(present, key=lambda cell: cell[2])
            values.update({"max.value": largest[2], "max.label": largest[1], "max.series": largest[0]})
        for s, c, value in cells:
            key = f"{token(s)}.{token(c)}"
            require(key not in values, f"Dataset {name!r} has colliding variable key {key!r}; rename its labels",
                    field="series")
            values[key] = value
        result.update({f"{name}.{key}": value for key, value in values.items() if value is not None})
    return result


def variables(project):
    return _variables(project.state, {})


def execute(project, op):
    name = op["name"]
    require(NAME.fullmatch(name), "Dataset names use 1–64 letters, numbers, _ or -", field="name")
    records = project.state.setdefault("datasets", {})
    action = op.get("action", "set")
    if action == "remove":
        require(set(op) <= {"type", "name", "action"}, "remove takes only a dataset name", field="action")
        require(name in records, f"Unknown dataset {name!r}", "not_found", field="name")
        del records[name]
        if not records:
            project.state.pop("datasets")
        return
    recipe = deepcopy(records.get(name, {}))
    if "from" in op:
        require(not any(key in op for key in (*charts.DATA_KEYS, "set")) and action == "set",
                "from cannot be combined with inline data, CSV, edits or reload", field="from")
        group = project.layer(op["from"])
        require(group["type"] == "group" and "chart" in group, "from must name a chart group", field="from")
        recipe = {"categories": deepcopy(group["chart"]["categories"]),
                  "series": deepcopy(group["chart"]["series"]), "source": {"from": group["id"]}}
    elif action == "reload":
        require(set(op) <= {"type", "name", "action"}, "reload takes only a dataset name", field="action")
        require(recipe.get("source", {}).get("csv"), "Only CSV datasets can reload", field="action")
        recipe["categories"], recipe["series"] = charts.table_from_csv(project, recipe["source"])
    else:
        require(not recipe.get("source", {}).get("from") or any(k in op for k in charts.DATA_KEYS),
                "Edit the source chart, or replace this dataset's table to detach it", field="set")
        require(recipe or any(k in op for k in charts.DATA_KEYS), "A new dataset needs table, csv or from", field="table")
        charts.edit_data(project, op, recipe)
    records[name] = recipe
    require(len(records) <= MAX_DATASETS, f"At most {MAX_DATASETS} datasets", "resource_limit")
    # Resolve now so later operations in the same batch see the new data and cycles fail at this operation.
    resolve(project.state, name)


def binding_schema():
    from ...schema import field

    return {
        "data": field({"type": "string"}, "Named dataset shared with other charts, tables and data.* text fields."),
        "derive": field({"type": ["object", "null"], "properties": {
            "kind": field({"enum": ["sum", "share", "max"]}, "Aggregate sum, fraction of total, or maximum."),
            "by": field({"enum": ["series", "category"]}, "Group by series or category (default category).")},
            "required": ["kind"], "additionalProperties": False},
            "Aggregate a dataset into one series; null clears the derivation."),
    }


def schemas(add):
    from ...schema import field

    variants = {}
    charts.schemas(lambda name, props, **kw: variants.update({name: props}))
    source = variants["chart-data"]
    add("dataset", {
        "name": field({"type": "string", "pattern": r"^[\w-]{1,64}$"}, "Dataset name used by data and data.NAME merge fields."),
        "action": field({"enum": ["set", "reload", "remove"]}, "Set/create or edit (default), reload its CSV, or remove."),
        "from": field({"type": "string"}, "Source chart ID or name; follows its data until replaced by inline data."),
        **{key: deepcopy(source[key]) for key in ("categories", "series", "table", "csv", "category_column", "series_columns", "set")},
    }, required=("name",), description="Set, edit, reload or remove shared data; bound charts, tables and text update atomically.")


def compile_command(cmd, args):
    if cmd != "dataset":
        return None
    from ...commands import Parser

    parser = Parser(prog="vixl dataset", description="Shared datasets; vixl schema dataset lists every field.")
    parser.add_argument("name")
    parser.add_argument("--action", choices=["set", "reload", "remove"])
    parser.add_argument("--table", type=json.loads)
    parser.add_argument("--categories", type=json.loads)
    parser.add_argument("--series", type=json.loads)
    parser.add_argument("--csv")
    parser.add_argument("--category-column")
    parser.add_argument("--series-columns", type=lambda value: value.split(","))
    parser.add_argument("--from", dest="from")
    parser.add_argument("--set", action="append", type=charts.parse_set)
    return {"type": cmd, **{key: value for key, value in vars(parser.parse_args(args)).items() if value is not None}}
