---
name: drawio-compose
description: Compose and incrementally edit large, single-page draw.io architecture diagrams from independently editable .drawio modules. Use when Codex needs to create, build, validate, normalize, render, or modify a modular draw.io composition; preserve module boundaries and public connection contracts; search official draw.io shapes without loading the full shape catalog; or avoid loading a large generated XML file during a targeted diagram edit.
---

# Drawio Compose

Use the `drawio-compose` CLI as the deterministic build layer. Keep diagram reasoning in the agent and XML mechanics in the CLI.

## Check the prerequisite

Before reading or changing composition sources, run `drawio-compose --version`.

- If the executable is unavailable, try `python -m drawio_compose --version` and use `python -m drawio_compose` as the command prefix when it succeeds.
- If neither command succeeds, report that the drawio-compose CLI must be installed. Do not install it without user approval.

## Context discipline

- Read the composition manifest, a freshly generated compact symbol index, and only the modules required for the current change.
- Do not read `search-index.json`; run `drawio-compose shape-search` and use only the returned candidates.
- Do not read the generated full `.drawio` unless a failure cannot be isolated to the manifest or a module.
- Treat module files and the composition manifest as source. Treat the combined `.drawio`, symbol index, and previews as generated output.

## Create a composition

1. Divide the requested architecture into independently understandable modules, normally 6-30 nodes each.
2. Create one uncompressed, single-page `.drawio` file per module.
3. Give every externally connectable `object` or `UserObject` a stable `composeKey` and `composeExport="1"`.
4. Create a version 1 compose XML with module paths, fixed grid positions, and connections in `module-id.compose-key` form.
5. Search extended or vendor shapes with:

   `drawio-compose shape-search "aws transit gateway" --limit 5 --json`

6. Prefer the newest official vendor generation when equivalent shapes exist unless the user requires a legacy generation; use AWS4 instead of AWS3, AWS3d, or legacy AWS webicons by default.
7. Generate the symbol index before later incremental work:

   `drawio-compose symbols architecture.compose.xml -o build/symbols.json`

## Edit incrementally

1. Read `architecture.compose.xml`.
2. Regenerate `build/symbols.json` before reading it so a missing or stale generated index cannot guide the edit:

   `drawio-compose symbols architecture.compose.xml -o build/symbols.json`

3. Read the regenerated symbol index and identify the smallest set of affected modules.
4. Read and edit only those module files; update manifest connections only when the public contract changes.
5. Keep internal cell IDs local. Never pre-prefix them with a module ID; the CLI adds global prefixes during composition.
6. Normalize a module explicitly after a GUI save if validation reports compression:

   `drawio-compose normalize modules/example.drawio --in-place`

## Validate and build

Run these commands in order:

1. `drawio-compose validate architecture.compose.xml`
2. `drawio-compose build architecture.compose.xml -o build/architecture.drawio`
3. `drawio-compose symbols architecture.compose.xml -o build/symbols.json`
4. `drawio-compose render build/architecture.drawio -o build/architecture.png`

If draw.io Desktop is unavailable, deliver the validated `.drawio` and clearly report that visual verification was skipped. When rendering succeeds, inspect the image for overlaps, clipped labels, excessive crossings, and inconsistent spacing. Make focused corrections until the requested result is visually sound or a concrete layout limitation remains to report.

## Contract rules

- Use only the default layer in version 1 modules; nested groups are supported.
- Connect modules only through exported keys. Do not expose internal nodes merely to bypass validation.
- Keep module paths relative to and within the composition directory.
- Keep module, connection, and public keys lowercase kebab-case.
- Do not add XML comments or compressed output.
- Write build and symbol outputs to a generated-output directory, never to the manifest or a module path.
- Preserve fixed module grid placement; allow draw.io connectors to route between published endpoints.
