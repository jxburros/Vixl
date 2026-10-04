"""Opt-in trusted Python extension entry points. Never load code from a .vixl archive."""

from importlib.metadata import entry_points
from .errors import VixlError

_ENABLED = False


def enable_plugins():
    global _ENABLED
    _ENABLED = True


def load(group, name):
    if not _ENABLED:
        raise VixlError("plugins_disabled", "Third-party plugins require --plugins or enable_plugins()")
    found = entry_points(group=f"vixl.{group}", name=name)
    if not found:
        raise VixlError("plugin_not_found", f"No {group} plugin named {name}")
    found = list(found)
    if len(found) != 1:
        raise VixlError("plugin_collision", f"Multiple {group} plugins named {name}")
    try:
        return found[0].load()
    except Exception as exc:
        raise VixlError("plugin_failed", f"Cannot load {group} plugin {name}: {exc}") from exc


def filter_plugin(name):
    return load("filters", name)


def discover():
    """List installed Python extensions without importing or executing them."""
    return {
        "enabled": _ENABLED,
        "api_version": 1,
        "extensions": [
            {"group": group, "name": ep.name, "entry_point": ep.value}
            for group in ("filters", "providers", "operations")
            for ep in entry_points(group=f"vixl.{group}")
        ],
    }


def run(project, name, options=None, *, dry_run=False):
    """Trusted Python operation plugins return ordinary operations; mutations remain atomic."""
    from .interfaces import service_check
    from .errors import require
    from copy import deepcopy

    handler = load("operations", name)
    require(getattr(handler, "api_version", None) == 1, "Plugin must declare api_version = 1")
    try:
        operations = handler(deepcopy(project.inspect()), deepcopy(options or {}))
    except Exception as exc:
        raise VixlError("plugin_failed", f"Plugin {name} failed: {exc}") from exc
    return project.apply(operations, check=service_check, detail="compact", dry_run=dry_run)


def package(session, action, request):
    """Versioned declarative plugin packs. No downloaded code or document code is executed."""
    import json
    import re
    from copy import deepcopy
    from .resources import resource_path, validate, BUILTINS
    from .assets import read_bounded
    from .production import write_json
    from .fileio import file_lock
    from .design import named
    from .errors import require

    path = resource_path(session.workspace)
    with file_lock(str(path)):
        data = json.loads(read_bounded(path, 1024 * 1024)) if path.exists() else {}
        require(isinstance(data, dict), "Invalid resource library")
        packages = data.setdefault("_plugins", {})
        require(isinstance(packages, dict) and len(packages) <= 100, "Invalid plugin registry")
        if action == "plugin-list":
            return {"packages": deepcopy(packages), "python": discover()}
        if action == "plugin-remove":
            name = named(request["name"])
            require(name in packages, "Plugin pack is not installed")
            require(
                not any(name in p.get("dependencies", {}) for key, p in packages.items() if key != name),
                "Other plugin packs depend on this pack",
            )
            old = packages.pop(name)
            for kind, names in old["resources"].items():
                for key in names:
                    data.get(kind, {}).pop(key, None)
            write_json(path, data)
            return {"removed": name}
        manifest = deepcopy(request["manifest"])
        require(
            isinstance(manifest, dict)
            and set(manifest)
            <= {"api_version", "name", "version", "description", "dependencies", "resources"},
            "Invalid plugin manifest",
        )
        require(manifest.get("api_version") == 1, "Plugin API version must be 1")
        name = named(manifest.get("name"))
        require(
            isinstance(manifest.get("version"), str) and re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]),
            "Plugin version must be major.minor.patch",
        )
        require(
            name not in packages or request.get("replace", False), "Plugin exists; set replace to upgrade"
        )
        dependencies = manifest.get("dependencies", {})
        require(isinstance(dependencies, dict) and name not in dependencies, "Invalid plugin dependencies")
        for dependency, version in dependencies.items():
            require(
                dependency in packages and packages[dependency]["version"] == version,
                "Missing exact plugin dependency",
                dependency=dependency,
                version=version,
            )
        for other, installed in packages.items():
            if other != name and name in installed.get("dependencies", {}):
                require(
                    installed["dependencies"][name] == manifest["version"],
                    "Upgrade would break a dependent plugin",
                )
        resources = manifest.get("resources")
        require(
            isinstance(resources, dict) and resources and set(resources) <= set(BUILTINS),
            "Invalid plugin resources",
        )
        prior = packages.get(name, {}).get("resources", {})
        owned = {}
        for kind, entries in resources.items():
            require(isinstance(entries, dict) and len(entries) <= 100, "Invalid plugin resource collection")
            owned[kind] = []
            for key, value in entries.items():
                named(key)
                require(key.startswith(name + "-"), "Plugin resource names must start with plugin-name-")
                require(
                    key not in BUILTINS[kind]
                    and (key not in data.get(kind, {}) or key in prior.get(kind, [])),
                    "Plugin resource collision",
                )
                validate(kind, value)
                owned[kind].append(key)
        for kind, keys in prior.items():
            for key in keys:
                data.get(kind, {}).pop(key, None)
        for kind, entries in resources.items():
            data.setdefault(kind, {}).update(entries)
        packages[name] = {
            k: manifest[k] for k in ("version", "api_version", "description", "dependencies") if k in manifest
        }
        packages[name]["resources"] = owned
        require(len(packages) <= 100, "Plugin registry supports up to 100 packs", "resource_limit")
        visited = set()

        def visit(current, chain):
            require(current not in chain, "Plugin dependency cycle")
            if current in visited:
                return
            for dependency in packages[current].get("dependencies", {}):
                visit(dependency, chain | {current})
            visited.add(current)

        visit(name, set())
        require(
            len(json.dumps(data).encode()) <= 1024 * 1024, "Plugin library exceeds 1 MiB", "resource_limit"
        )
        write_json(path, data)
        return {"installed": name, **packages[name]}
