"""Pages and master pages: multi-page documents for decks, carousels, booklets and forms.

A document starts as one canvas. The first ``page add`` turns it into a page list: every page has
its own layers (and the state that refers to them: timeline, symbols, comps, artboards …), while
the canvas size, fonts, swatches, styles, palettes, brushes, guides and variables are shared.
Master pages hold layers drawn underneath every page that uses them.

Only one page is *active* at a time and its content lives in the ordinary top-level state, so every
operation edits the active page unchanged. Inactive pages keep their content in their record.
``page select`` (or a ``page`` field on any operation) switches pages. Renders and exports read a
page through ``page_project``, which draws the master's layers first and fills the built-in
variables ``${page}``, ``${pages}`` and ``${page_name}``.
"""

from copy import copy, deepcopy
import hashlib
import json
import re

from .errors import VixlError, require
from .model import uid

TYPES = ("page", "master")
# State that belongs to one page because it holds or refers to that page's layers.
SCOPED = ("layers", "active_layer", "selection", "timeline", "blanks", "layout", "comps", "symbols", "artboards",
          "roles", "containers", "animation")
PAGE_FIELDS = {"id", "name", "notes", "master", "background", "variables", "hidden", "transition", "content"}
MASTER_FIELDS = {"background", "content"}
TRANSITIONS = ("none", "fade", "push", "wipe", "cover", "split", "zoom")
BUILTINS = ("page", "pages", "page_name")
MAX_PAGES = 500
MASTER_PREFIX = "master:"


def has_pages(state):
    return bool(state.get("pages"))


def empty_content():
    return {"layers": [], "active_layer": None, "selection": None}


def take_content(state):
    """Remove and return the active page's scoped state."""
    content = {key: state.pop(key) for key in SCOPED if key in state}
    state.update(empty_content())
    return content


def put_content(state, content):
    for key in SCOPED:
        state.pop(key, None)
    state.update(empty_content())
    state.update(deepcopy(content))


def _slug(value, field="name"):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][\w-]{0,79}", value),
            f"{field} must be 1–80 letters, numbers, underscores or hyphens", field=field)
    return value


def find_page(state, ref, field="page"):
    """The page record for a name, an id or a 1-based number."""
    pages = state.get("pages") or []
    require(pages, "This document has no pages yet; create one with page add", field=field)
    if isinstance(ref, int) and not isinstance(ref, bool):
        require(1 <= ref <= len(pages), f"Page number must be 1–{len(pages)}", field=field)
        return pages[ref - 1]
    for page in pages:
        if ref in (page["id"], page["name"]):
            return page
    if isinstance(ref, str) and ref.isdigit():
        return find_page(state, int(ref), field)
    names = [page["name"] for page in pages]
    raise VixlError("page_not_found", f"Page {ref!r} does not exist. Pages: {', '.join(names[:40])}", field=field,
                    available=names[:100])


def active_page(state):
    ref = state.get("page")
    if not ref or ref.startswith(MASTER_PREFIX):
        return None
    return next((page for page in state.get("pages", []) if page["id"] == ref), None)


def page_number(state, page):
    return state["pages"].index(page) + 1


def set_builtins(state):
    """Keep ``${page}``, ``${pages}`` and ``${page_name}`` defined for the active page."""
    if not has_pages(state):
        return
    page = active_page(state)
    variables = state.setdefault("variables", {})
    if page is None:
        variables.update(page=0, pages=len(state["pages"]), page_name="")
    else:
        variables.update(page=page_number(state, page), pages=len(state["pages"]), page_name=page["name"])


def _store_active(state):
    """Put the active page's (or master's) content back into its record."""
    ref = state.get("page")
    if not ref:
        return
    content = take_content(state)
    if ref.startswith(MASTER_PREFIX):
        state["masters"][ref[len(MASTER_PREFIX):]]["content"] = content
    else:
        page = next(page for page in state["pages"] if page["id"] == ref)
        page["content"] = content
    state["page"] = None


def select(state, page=None, master=None):
    """Make a page (or a master) the active, editable content."""
    if master is not None:
        require(master in state.get("masters", {}), f"Unknown master {master!r}; masters: "
                f"{', '.join(state.get('masters', {})) or 'none'}", field="master")
        target_ref = MASTER_PREFIX + master
    else:
        target_ref = find_page(state, page)["id"]
    if state.get("page") == target_ref:
        return
    _store_active(state)
    if master is not None:
        content = state["masters"][master].pop("content")
    else:
        record = find_page(state, target_ref)
        content = record.pop("content")
    put_content(state, content)
    state["page"] = target_ref
    set_builtins(state)


def ensure_pages(state, first_name="page-1"):
    """Turn a single-canvas document into a one-page document (its content becomes page 1)."""
    if has_pages(state):
        return
    page = {"id": uid("pg"), "name": first_name}
    state["pages"] = [page]
    state["page"] = page["id"]
    set_builtins(state)


def _insert_index(state, op):
    pages = state["pages"]
    if "index" in op:
        index = op["index"]
        require(isinstance(index, int) and 1 <= index <= len(pages) + 1, f"index must be 1–{len(pages) + 1}", field="index")
        return index - 1
    if "after" in op:
        return pages.index(find_page(state, op["after"], "after")) + 1
    if "before" in op:
        return pages.index(find_page(state, op["before"], "before"))
    active = active_page(state)
    return pages.index(active) + 1 if active else len(pages)


def _page_settings(state, page, op):
    from .design import resolve_color
    from .render import color

    if "notes" in op:
        require(isinstance(op["notes"], str) and len(op["notes"]) <= 50000, "notes must be text up to 50000 characters",
                field="notes")
        if op["notes"]:
            page["notes"] = op["notes"]
        else:
            page.pop("notes", None)
    if "master" in op:
        if op["master"] in (None, "none", ""):
            page["master"] = None
        else:
            require(op["master"] in state.get("masters", {}), f"Unknown master {op['master']!r}", field="master")
            page["master"] = op["master"]
    if "background" in op:
        if op["background"] in (None, ""):
            page.pop("background", None)
        else:
            color(resolve_color(op["background"], state))
            page["background"] = op["background"]
    if "variables" in op:
        variables = op["variables"]
        require(isinstance(variables, dict) and len(variables) <= 256 and all(
            isinstance(k, str) and re.fullmatch(r"[\w-]+", k) and k not in BUILTINS and isinstance(v, (str, int, float, bool))
            for k, v in variables.items()), "variables maps names to scalar values (page, pages and page_name are built in)",
            field="variables")
        page["variables"] = deepcopy(variables)
    if "hidden" in op:
        require(isinstance(op["hidden"], bool), "hidden must be true or false", field="hidden")
        if op["hidden"]:
            page["hidden"] = True
        else:
            page.pop("hidden", None)
    if "transition" in op:
        require(op["transition"] in TRANSITIONS, f"transition must be one of {', '.join(TRANSITIONS)}", field="transition")
        if op["transition"] == "none":
            page.pop("transition", None)
        else:
            page["transition"] = op["transition"]


def _fresh_ids(content):
    """Give copied content new layer IDs, rewriting every reference to them."""
    mapping = {layer["id"]: uid("lyr") for layer in content.get("layers", [])}
    if not mapping:
        return content
    text = json.dumps(content)
    for old, new in mapping.items():
        text = text.replace(old, new)
    return json.loads(text)


def execute(project, op):
    state = project.state
    action = op.get("action")
    if op["type"] == "master":
        masters = state.setdefault("masters", {})
        if action == "add":
            name = _slug(op["name"])
            require(name not in masters, f"Master {name!r} already exists", field="name")
            ensure_pages(state)
            content = empty_content()
            if op.get("from"):
                source = find_page(state, op["from"], "from")
                if state.get("page") == source["id"]:
                    content = {key: deepcopy(state[key]) for key in SCOPED if key in state}
                else:
                    content = deepcopy(source["content"])
                content = _fresh_ids(content)
            masters[name] = {"content": content}
            if op.get("background"):
                from .design import resolve_color
                from .render import color

                color(resolve_color(op["background"], state))
                masters[name]["background"] = op["background"]
            if op.get("select", True):
                select(state, master=name)
        elif action == "select":
            select(state, master=op["name"])
        elif action == "remove":
            name = op["name"]
            require(name in masters, f"Unknown master {name!r}", field="name")
            if state.get("page") == MASTER_PREFIX + name:
                select(state, page=1)
            del masters[name]
            for page in state["pages"]:
                if page.get("master") == name:
                    page["master"] = None
        else:  # set
            name = op["name"]
            require(name in masters, f"Unknown master {name!r}", field="name")
            if "background" in op:
                from .design import resolve_color
                from .render import color

                color(resolve_color(op["background"], state))
                masters[name]["background"] = op["background"]
            if op.get("rename"):
                new = _slug(op["rename"], "rename")
                require(new not in masters, f"Master {new!r} already exists", field="rename")
                masters[new] = masters.pop(name)
                if state.get("page") == MASTER_PREFIX + name:
                    state["page"] = MASTER_PREFIX + new
                for page in state["pages"]:
                    if page.get("master") == name:
                        page["master"] = new
        if not masters:
            state.pop("masters", None)
        set_builtins(state)
        return
    if action == "add":
        ensure_pages(state, op.get("first", "page-1"))
        only = state["pages"][0]
        if (len(state["pages"]) == 1 and not op.get("duplicate") and not set(only) - {"id", "name", "content"}
                and only["name"] == op.get("first", "page-1") and not page_content(project, only).get("layers")):
            # A blank document's untouched starting page becomes the first page added.
            name = _slug(op.get("name") or only["name"])
            only["name"] = name
            if "master" not in op and "default" in state.get("masters", {}):
                only["master"] = "default"
            _page_settings(state, only, op)
            if op.get("select", True):
                select(state, page=only["id"])
            set_builtins(state)
            return
        name = _slug(op.get("name") or _next_name(state))
        require(all(page["name"] != name for page in state["pages"]), f"Page {name!r} already exists", field="name")
        require(len(state["pages"]) < MAX_PAGES, f"A document holds at most {MAX_PAGES} pages", "resource_limit")
        index = _insert_index(state, op)
        page = {"id": uid("pg"), "name": name, "content": empty_content()}
        if "master" not in op and "default" in state.get("masters", {}):
            page["master"] = "default"
        if op.get("duplicate"):
            source = find_page(state, op["duplicate"], "duplicate")
            if state.get("page") == source["id"]:
                content = {key: deepcopy(state[key]) for key in SCOPED if key in state}
            else:
                content = deepcopy(source["content"])
            page["content"] = _fresh_ids(content)
            for key in ("notes", "master", "background", "variables", "transition"):
                if key in source:
                    page[key] = deepcopy(source[key])
        _page_settings(state, page, op)
        state["pages"].insert(index, page)
        if op.get("select", True):
            select(state, page=page["id"])
        set_builtins(state)
        return
    if action == "select":
        select(state, page=op["page"])
        return
    require(has_pages(state), "This document has no pages yet; create one with page add", field="action")
    page = find_page(state, op.get("page") or (active_page(state) or {}).get("id") or 1)
    if action == "remove":
        require(len(state["pages"]) > 1, "A document keeps at least one page", field="page")
        index = state["pages"].index(page)
        if state.get("page") == page["id"]:
            neighbour = state["pages"][index + 1] if index + 1 < len(state["pages"]) else state["pages"][index - 1]
            select(state, page=neighbour["id"])
        state["pages"].remove(page)
    elif action == "move":
        state["pages"].remove(page)
        index = _insert_index(state, op) if any(k in op for k in ("index", "after", "before")) else len(state["pages"])
        state["pages"].insert(min(index, len(state["pages"])), page)
    else:  # set
        if op.get("rename"):
            new = _slug(op["rename"], "rename")
            require(all(other["name"] != new for other in state["pages"] if other is not page), f"Page {new!r} already exists",
                    field="rename")
            page["name"] = new
        _page_settings(state, page, op)
    set_builtins(state)


def _next_name(state):
    taken = {page["name"] for page in state.get("pages", [])}
    index = len(taken) + 1
    while f"page-{index}" in taken:
        index += 1
    return f"page-{index}"


def schemas(add):
    from .schema import S, B

    ref = {"type": ["string", "integer"]}
    add("page", {"action": {"enum": ["add", "select", "remove", "move", "set"]}, "page": ref, "name": S, "rename": S,
                 "after": ref, "before": ref, "index": {"type": "integer", "minimum": 1}, "duplicate": ref, "first": S,
                 "master": {"type": ["string", "null"]}, "notes": S, "background": {"type": ["string", "null"]},
                 "variables": {"type": "object"}, "hidden": B, "select": B, "transition": {"enum": list(TRANSITIONS)}},
        ["action"])
    add("master", {"action": {"enum": ["add", "select", "remove", "set"]}, "name": S, "from": ref, "background": S,
                   "rename": S, "select": B}, ["action", "name"])


def compile_command(cmd, args):
    """``vixl page add|select|remove|move|set …`` and ``vixl master add|select|remove|set …``."""
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    p = Parser(prog=f"vixl {cmd}")
    if cmd == "master":
        p.add_argument("action", choices=["add", "select", "remove", "set"])
        p.add_argument("name")
        p.add_argument("--from", dest="from_", metavar="PAGE", help="Start the master from a copy of this page")
        p.add_argument("--background")
        p.add_argument("--rename")
        p.add_argument("--no-select", dest="select", action="store_false", default=None)
        data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
        if "from_" in data:
            data["from"] = data.pop("from_")
        return {"type": "master", **data}
    p.add_argument("action", choices=["add", "select", "remove", "move", "set"])
    p.add_argument("page", nargs="?", help="Page name or number (add: the new page's name)")
    for key in ("after", "before", "duplicate", "master", "notes", "background", "rename", "first"):
        p.add_argument("--" + key)
    p.add_argument("--index", type=int)
    p.add_argument("--transition", choices=list(TRANSITIONS))
    p.add_argument("--variables", type=json.loads, help="JSON object of page variables")
    p.add_argument("--hidden", action="store_true", default=None)
    p.add_argument("--shown", dest="hidden", action="store_false")
    p.add_argument("--no-select", dest="select", action="store_false", default=None)
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if data["action"] == "add" and "page" in data:
        data["name"] = data.pop("page")
    for key in ("page", "after", "before", "duplicate"):
        if isinstance(data.get(key), str) and data[key].isdigit():
            data[key] = int(data[key])
    if "notes" in data:
        data["notes"] = data["notes"].replace("\\n", "\n")
    return {"type": "page", **data}


# ---------------------------------------------------------------------------------------------
# Views


def page_content(project, page):
    """The scoped content of a page record (the live state for the active page)."""
    state = project.state
    if state.get("page") == page["id"]:
        return {key: state[key] for key in SCOPED if key in state}
    return page["content"]


def master_content(project, name):
    state = project.state
    if state.get("page") == MASTER_PREFIX + name:
        return {key: state[key] for key in SCOPED if key in state}
    return state["masters"][name]["content"]


def page_project(project, page=None):
    """A render-only copy showing one page: its master's layers underneath its own, its
    background, and its variables (with ``page``, ``pages`` and ``page_name`` filled in)."""
    state = project.state
    if not has_pages(state):
        require(page in (None, 1, "1"), "This document has no pages", field="page")
        return project
    record = find_page(state, page) if page is not None else (active_page(state) or state["pages"][0])
    view = copy(project)
    view._document = getattr(project, "_document", None) or project
    view.state = {key: deepcopy(value) for key, value in state.items() if key not in SCOPED and key != "pages"}
    view.state["pages"] = state["pages"]  # shared read-only; numbering and counts read it
    content = deepcopy(page_content(project, record))
    layers = content.get("layers", [])
    background = record.get("background")
    master = record.get("master")
    if master and master in state.get("masters", {}):
        master_layers = deepcopy(master_content(project, master).get("layers", []))
        names = {layer["name"] for layer in layers}
        for layer in master_layers:
            if layer["name"] in names:
                layer["name"] = f"{MASTER_PREFIX}{master}/{layer['name']}"
        layers = master_layers + layers
        background = background or state["masters"][master].get("background")
    view.state.update(empty_content())
    view.state.update(content)
    view.state["layers"] = layers
    view.state["page"] = record["id"]
    if background:
        view.state["canvas"] = {**view.state["canvas"], "background": background}
    variables = view.state.setdefault("variables", {})
    variables.update(record.get("variables", {}))
    variables.update(page=page_number(state, record), pages=len(state["pages"]), page_name=record["name"])
    from .render import LayerCache

    view._cache = project._cache if isinstance(project._cache, LayerCache) else LayerCache()
    return view


def parse_pages(value):
    """``"1-3,5,intro"`` (or a list) → page references: numbers, ranges and names."""
    if value is None or isinstance(value, list):
        return value
    refs = []
    for part in str(value).split(","):
        part = part.strip()
        if re.fullmatch(r"\d+-\d+", part):
            first, last = map(int, part.split("-"))
            require(1 <= first <= last <= MAX_PAGES, f"Invalid page range {part!r}", field="pages")
            refs += list(range(first, last + 1))
        elif part.isdigit():
            refs.append(int(part))
        elif part:
            refs.append(part)
    require(refs, "pages lists page numbers, ranges (2-4) or names", field="pages")
    return refs


def page_list(project, include_hidden=True):
    """Page records in order (``hidden`` pages skipped unless asked for)."""
    pages = project.state.get("pages") or []
    return [page for page in pages if include_hidden or not page.get("hidden")]


def summary(project):
    """Pages and masters without their content, for inspection."""
    state = project.state
    if not has_pages(state):
        return None
    pages = []
    for number, page in enumerate(state["pages"], 1):
        content = page_content(project, page)
        texts = [layer.get("text", "") for layer in content.get("layers", []) if layer["type"] == "text"]
        pages.append({
            "number": number, "id": page["id"], "name": page["name"], "layers": len(content.get("layers", [])),
            **{key: page[key] for key in ("master", "background", "hidden", "transition") if page.get(key)},
            **({"notes": page["notes"][:200]} if page.get("notes") else {}),
            "words": sum(len(text.split()) for text in texts),
            "active": state.get("page") == page["id"],
        })
    masters = {name: {"layers": len(master_content(project, name).get("layers", [])),
                      "active": state.get("page") == MASTER_PREFIX + name}
               for name in state.get("masters", {})}
    return {"pages": pages, "masters": masters, "active": state.get("page")}


# ---------------------------------------------------------------------------------------------
# Validation


def validate_pages(project, state):
    """Validate the page list, masters and every inactive page's content as a document state."""
    from .validation import check_state

    pages = state.get("pages")
    if pages is None:
        require("masters" not in state and not state.get("page"), "Masters and page selection need pages", "invalid_project")
        return
    require(isinstance(pages, list) and 1 <= len(pages) <= MAX_PAGES, "Invalid page list", "invalid_project")
    ids, names = set(), set()
    active = state.get("page")
    holders = 0
    masters = state.get("masters", {})
    require(isinstance(masters, dict) and len(masters) <= 64, "Invalid masters", "invalid_project")
    for page in pages:
        require(isinstance(page, dict) and not set(page) - PAGE_FIELDS and isinstance(page.get("id"), str),
                "Invalid page record", "invalid_project")
        _slug(page.get("name"))
        require(page["id"] not in ids and page["name"] not in names, "Duplicate page", "invalid_project")
        ids.add(page["id"])
        names.add(page["name"])
        if page["id"] == active:
            require("content" not in page, "The active page keeps its content in the document", "invalid_project")
        else:
            require(isinstance(page.get("content"), dict), "Inactive pages need content", "invalid_project")
            holders += 1
        require(page.get("master") is None or page["master"] in masters, "Page uses a missing master", "invalid_project")
        require(page.get("transition", "fade") in TRANSITIONS, "Invalid transition", "invalid_project")
        require(isinstance(page.get("notes", ""), str) and len(page.get("notes", "")) <= 50000, "Invalid notes", "invalid_project")
        require(isinstance(page.get("variables", {}), dict), "Invalid page variables", "invalid_project")
    for name, master in masters.items():
        _slug(name)
        require(isinstance(master, dict) and not set(master) - MASTER_FIELDS, "Invalid master", "invalid_project")
        require((active == MASTER_PREFIX + name) != ("content" in master), "Invalid master content", "invalid_project")
    require(active in ids or (isinstance(active, str) and active.startswith(MASTER_PREFIX)
                              and active[len(MASTER_PREFIX):] in masters), "Invalid active page", "invalid_project")
    # Inactive content is validated as a document state of its own (cached by content hash).
    seen = getattr(project, "_valid_pages", None)
    if seen is None:
        seen = project._valid_pages = set()
    layer_ids = {layer["id"] for layer in state["layers"]}
    contents = [page["content"] for page in pages if "content" in page]
    contents += [master["content"] for master in masters.values() if "content" in master]
    for content in contents:
        require(isinstance(content, dict) and not set(content) - set(SCOPED), "Invalid page content", "invalid_project")
        ids_here = {layer["id"] for layer in content.get("layers", [])}
        require(not (ids_here & layer_ids), "Layer IDs must be unique across pages", "invalid_project")
        layer_ids |= ids_here
        key = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
        if key in seen:
            continue
        view = {k: v for k, v in state.items() if k not in SCOPED and k not in ("pages", "masters", "page")}
        view.update(empty_content())
        view.update(content)
        check_state(project, view)
        seen.add(key)
