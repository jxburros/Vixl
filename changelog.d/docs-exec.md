### Changed defaults

- **Python `Project.save(path)` refuses to replace another existing `.vixl`** with `output_exists`, like `vixl new`, `vixl save` and every export. Saving to the document's own file (or the one it was loaded from) is unchanged. Pass `overwrite=True` for the old result (#313).

### Added

- **Executable documentation**: `tests/test_docs_executable.py` (`pytest -m docs`, part of the normal run) runs the `vixl …` commands of every shell block in `docs/` and `skills/` in a temporary workspace and validates, then applies, every JSON operation block. New blocks are picked up automatically; `<!-- docs-test: continue | save FILE | skip REASON -->` steers walkthroughs (see `docs/documentation-maintenance.md`).

### Fixes

- **`vixl guide NAME x|y POSITION`** and `vixl guide NAME --kind …` add a guide again; since the craft guide took the `guide` command they returned "No kind of work matches" (docs/guides.md, docs/design-tools.md).
- **`vixl capabilities pen`** lists `pen`, then shape and path operations, instead of leading with `oil-paint`: matches rank by the word that matched. The `pen --nodes` help and schema say that `in`/`out` handles are positions in the anchors' coordinates, not offsets (#324).
- Documentation examples run top to bottom: the presenter export examples write different files, the `tear` examples remove a mask before switching to a clip, and the CLI reference creates a guide before constraining to it.
