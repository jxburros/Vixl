## Summary

<!-- What changes and why, in a few sentences. -->

## Core or plugin?

<!-- Required for a new feature (CLAUDE.md, docs/reference/plugins.md "Is a new feature a plugin?"). Say which way it went and why, or write "not a new feature". -->

## Checklist for a user-visible change

- [ ] Code plus a regression test that fails without it
- [ ] Docs (`docs/`, and `skills/vixl/SKILL.md` and `skills/vixl/references/` when behaviour, fields or defaults change)
- [ ] `docs/use-cases.md` row added or moved (measured figures: `docs/project/use-case-evidence.md`)
- [ ] `CHANGELOG.md` entry in the top section
- [ ] Goldens regenerated and reviewed, if rendering changed (`VIXL_UPDATE_GOLDEN=1 pytest tests/visual`)
- [ ] Version bumps kept in sync, if this is a release change (see docs/reference/releases.md)

## Size

<!-- About 800 changed lines is the review budget, excluding goldens, CHANGELOG.md and generated tables. If this is larger, say why it cannot be split. Mechanical moves belong in their own pull request. -->

## Commit messages

- [ ] No model signatures or authorship trailers (`Co-Authored-By:`, `Claude-Session:`) in commits or this description. `scripts/hooks/commit-msg` strips them from commits.
