"""One creation path for new documents: CLI ``vixl new``, Python ``Project()``/``Project.sized()``/``Project.new()``,
MCP ``vixl_document_create``, compose and the REST session all come here.

A new document gets, in this order:
1. its size: the given width/height or named size, else the purpose's size (the house-style profile's ``size``),
   else the general profile's 1080×1080;
2. the workspace default fonts (``brand.json``), when ``workspace_fonts``;
3. reproducible ``design_defaults`` rolled from ``seed``/``variety`` (and ``purpose``);
4. a canvas background: the given one, else transparent for marks (logos, icons, favicons), else the rolled
   palette's background role;
5. the rolled font pairing, from the font cache first and then the network, when ``workspace_fonts`` and no
   brand fonts apply. Without either, the document keeps the proofing fallback and the report says why.

Everything is folded into the document's first revision, so the first edit stays the first undoable step.
``VIXL_AUTO_FONTS`` set to ``cache`` never downloads during creation, and ``off`` skips step 5.
"""

import os
import random

from .errors import VixlError, require

# After one failed automatic download, later creations in this process use the cache only, so an
# offline machine pays the network timeout at most once.
_offline = False
CONNECT_TIMEOUT = 3


def resolve_size(width=None, height=None, size=None, purpose=None):
    """``(width, height, size, source)``: exactly one of width/height or size, with ``source`` one of
    ``argument``, ``purpose`` or ``default``."""
    from .sizes import default_size, purpose_size

    require((width is None) == (height is None), "Give width and height together, or a named size", field="width")
    require(size is None or width is None, "Give width and height, or a named size, not both", field="size")
    if size is not None or width is not None:
        return width, height, size, "argument"
    size = purpose_size(purpose)
    if size is not None:
        return None, None, size, "purpose"
    return *default_size(), None, "default"


def create(width=None, height=None, background=None, *, size=None, purpose=None, dpi=None, orientation=None,
           bleed=False, seed=None, variety=None, workspace=None, remember=True, workspace_fonts=True, limits=None,
           report=None):
    """A new unsaved document with design defaults (see the module docstring). ``remember`` records an
    unseeded roll in the workspace history (``.vixl/rolls.json``) so the next roll differs; ``report``
    receives what creation chose."""
    from .project import Project

    width, height, size, source = resolve_size(width, height, size, purpose)
    if size is not None:
        project = Project.sized(size, "transparent", limits=limits, dpi=dpi, orientation=orientation, bleed=bleed,
                                workspace=workspace, design=False)
    else:
        require(not (orientation or bleed), "orientation and bleed need a named size", field="size")
        project = Project(width, height, "transparent", limits=limits, workspace=workspace)
        if dpi is not None:
            require(isinstance(dpi, (int, float)) and 36 <= dpi <= 2400, "dpi must be 36–2400", field="dpi")
            project.state["canvas"]["dpi"] = dpi
    design(project, size=size, size_from=source, purpose=purpose, background=background, seed=seed, variety=variety,
           workspace=workspace, remember=remember, workspace_fonts=workspace_fonts, report=report)
    return project


def design(project, *, size=None, size_from="argument", purpose=None, background=None, seed=None, variety=None,
           workspace=None, remember=True, workspace_fonts=True, report=None):
    """Give a freshly constructed document its design defaults, background and fonts in its first revision."""
    from .sizes import is_mark, purpose_name
    from .variety import document_defaults, seed_for

    purpose = purpose_name(purpose)
    report = {} if report is None else report
    label = project.nodes[project.head].get("label", "Create document") if project.head in project.nodes else "Create document"
    if background is not None:
        from .render import color

        color(background)
    if workspace_fonts:
        from .brand import apply_workspace_fonts

        fonts = apply_workspace_fonts(project, workspace)
        if fonts:
            report["workspace_fonts"] = fonts
    if not remember:
        # A pre-resolved seed keeps an unseeded roll out of the workspace history (and reads none).
        seed, variety = seed_for(project, seed, variety, workspace)
    defaults = document_defaults(project, seed=seed, variety=variety, workspace=workspace, purpose=purpose)
    canvas = project.state["canvas"]
    if background is not None:
        canvas["background"], background_from = background, "argument"
    elif is_mark(purpose, canvas.get("size")):
        canvas["background"], background_from = "transparent", "mark"
    else:
        canvas["background"], background_from = palette_background(project, defaults), "palette"
    from .layouts import assign_roles, ROLES

    direction = defaults.get("direction", {})
    if direction.get("palette"):
        settings = {"palette": direction["palette"], "mode": direction.get("mode", "light"),
                    "_house_style_version": defaults.get("house_style_version", 2)}
        if canvas["background"] != "transparent":
            settings["colors"] = {"background": canvas["background"]}
        roles = assign_roles(settings, random.Random(defaults["seed"]))
        swatches = project.state.setdefault("swatches", {})
        for role in ROLES:
            swatches.setdefault(role, roles[role])
    created = {"size": canvas.get("size") or f"{canvas['width']}x{canvas['height']}", "size_from": size_from,
               **({"purpose": purpose} if purpose else {}), "background": canvas["background"],
               "background_from": background_from}
    if workspace_fonts:
        created["fonts"] = install_rolled_pairing(project, defaults)
    report["creation"] = created
    _fold(project, label)
    return report


def palette_background(project, defaults):
    """The background role of the rolled palette in the rolled mode (a brand palette's own background wins)."""
    from .brand import for_project
    from .layouts import assign_roles

    kit = for_project(project).get("palette") or {}
    if kit.get("background"):
        return kit["background"]
    direction = defaults.get("direction", {})
    palette = direction.get("palette")
    if palette is None:
        return "transparent"
    roles = assign_roles({"palette": palette, "mode": direction.get("mode", "light"),
                          "_house_style_version": defaults.get("house_style_version", 2)}, random.Random(defaults["seed"]))
    return roles["background"]


def install_rolled_pairing(project, defaults):
    """Embed the rolled pairing as the document typography: from the font cache, else (once per process)
    from the network. Returns what happened; creation never fails for want of fonts."""
    global _offline
    import httpx

    from .typefaces import pair_fonts

    pairing = defaults.get("direction", {}).get("pairing")
    typography = project.state.get("typography") or {}
    if not pairing or pairing == "workspace-brand" or (typography.get("heading") and typography.get("body")):
        return {"installed": False, "reason": "the workspace fonts apply"} if typography else {"installed": False}
    mode = os.environ.get("VIXL_AUTO_FONTS", "on").strip().lower()
    hint = (f"Install them with vixl_font_pair(pairing='{pairing}') or vixl font pair {pairing}; until then text uses "
            "the proofing fallback.")
    if mode == "off":
        return {"pairing": pairing, "installed": False, "reason": "VIXL_AUTO_FONTS=off", "next_step": hint}

    def refuse(request):
        raise httpx.ConnectError("offline", request=request)

    attempts = [lambda: httpx.Client(transport=httpx.MockTransport(refuse))]
    if mode != "cache" and not _offline:
        attempts.append(network_client)
    error = None
    for connect in attempts:
        client = connect()
        candidate = project.clone()
        try:
            with client:
                installed = pair_fonts(candidate, pairing, client=client)
        except VixlError as exc:
            error = exc
            continue
        project.__dict__.update(candidate.__dict__)
        return {"pairing": pairing, "installed": True, "origin": installed["origin"],
                "heading": installed["heading"]["name"], "body": installed["body"]["name"]}
    if len(attempts) > 1 and error.code == "font_download_failed":
        _offline = True
        return {"pairing": pairing, "installed": False, "reason": "not in the font cache and the download failed",
                "warning": f"Fonts were not installed: {error}. Later documents in this session will not retry "
                           "the network.", "next_step": hint}
    reason = "not in the font cache" + ("" if mode == "cache" or _offline else f" ({error})")
    return {"pairing": pairing, "installed": False, "reason": reason, "next_step": hint}


def network_client():
    """The client for automatic downloads: a short connect timeout keeps an offline creation fast."""
    import httpx

    return httpx.Client(timeout=httpx.Timeout(20, connect=CONNECT_TIMEOUT), follow_redirects=False,
                        headers={"User-Agent": "vixl"})


def _fold(project, label):
    """Make everything done since construction part of the first revision."""
    project.nodes, project.head, project._head_state, project.branches = {}, None, None, {}
    project._verified = set()
    project._record([], label)
