# drawio-compose

`drawio-compose` builds one editable draw.io diagram from independently editable draw.io modules. It is designed for large architecture diagrams that need normal draw.io output without forcing an AI agent, reviewer, or automation job to load one monolithic XML file.

The CLI is deterministic and agent-independent. The bundled Agent Skill teaches compatible coding agents to read only the manifest, compact symbols, and modules involved in a change.

## Status

This repository is a public v0.1 alpha. The format and commands may change before a stable release.

## Requirements

- Python 3.11 or newer
- `lxml` 5.2 or newer
- draw.io Desktop only when using `render`

## Install the CLI and skill

The Agent Skill delegates XML mechanics to the Python CLI, so both pieces are required.

### Use in this repository

```bash
python -m venv .venv
.venv/Scripts/pip install -e .       # Windows
# .venv/bin/pip install -e .         # macOS/Linux
drawio-compose --version
```

Launch Codex from this repository after installing the CLI. Codex discovers the checked-in skill at `.agents/skills/drawio-compose` automatically.

### Use in another repository

Install the CLI from GitHub:

```bash
python -m pip install "git+https://github.com/kaise1/drawio-compose.git"
drawio-compose --version
```

Then ask Codex to install the skill from `https://github.com/kaise1/drawio-compose/tree/main/.agents/skills/drawio-compose` with `$skill-installer`. For a manual repository-scoped installation, copy or symlink that directory to `$REPO_ROOT/.agents/skills/drawio-compose`. User-wide skills belong under `$HOME/.agents/skills`.

See OpenAI's [Build skills documentation](https://learn.chatgpt.com/docs/build-skills) for current discovery and installation locations.

The skill checks the CLI before touching composition sources. It may use `python -m drawio_compose` when the console entry point is not on `PATH`, but it will not install the package without user approval.

## Quick start

Build the included hybrid AWS/on-premises example:

```bash
drawio-compose validate examples/hybrid-enterprise/hybrid-enterprise.compose.xml
drawio-compose symbols examples/hybrid-enterprise/hybrid-enterprise.compose.xml \
  -o examples/hybrid-enterprise/build/symbols.json
drawio-compose build examples/hybrid-enterprise/hybrid-enterprise.compose.xml \
  -o examples/hybrid-enterprise/build/hybrid-enterprise.drawio
drawio-compose render examples/hybrid-enterprise/build/hybrid-enterprise.drawio \
  -o examples/hybrid-enterprise/build/hybrid-enterprise.png
```

Search the pinned official draw.io shape catalog without loading its 10,000+ entries into an agent context:

```bash
drawio-compose shape-search "aws transit gateway" --limit 5 --json
```

For comparable AWS matches, current AWS4 service icons rank ahead of AWS3, AWS3d, and legacy AWS webicons.

## Source model

```text
architecture.compose.xml
├── modules/on-premises.drawio
├── modules/connectivity.drawio
├── modules/aws-network.drawio
└── modules/aws-application.drawio
             │
             ├── drawio-compose build   ──► build/architecture.drawio
             └── drawio-compose symbols ──► build/symbols.json
```

Each module is a normal one-page `.drawio` file. External connections use stable public keys stored as draw.io metadata:

```xml
<object id="local-cell-id" label="Private Endpoint"
        composeKey="private-endpoint" composeExport="1">
  <mxCell style="rounded=1;" vertex="1" parent="1">
    <mxGeometry x="40" y="40" width="140" height="60" as="geometry"/>
  </mxCell>
</object>
```

The composition references `module-id.compose-key`, never a generated global cell ID. See [the format specification](docs/FORMAT.md).

The CLI refuses to write `build` or `symbols` output over the composition manifest or any referenced module.

## Commands

| Command | Purpose |
| --- | --- |
| `validate` | Validate the manifest, every module, public endpoints, final graph, and official mxfile XSD |
| `build` | Compose an uncompressed, canonical, single-page `.drawio` |
| `symbols` | Write a compact JSON index of modules and exported keys |
| `normalize` | Convert a compressed or bare module into canonical one-page XML |
| `shape-search` | Search the pinned official shape index and return only matching styles |
| `render` | Export PNG, SVG, or PDF with draw.io Desktop |

## Proof-of-concept results

- Five independently editable modules and four cross-module connections
- Byte-identical output from repeated builds
- Incremental working set for the AWS application edit: 28.21% of the generated full XML
- Structural, reference, XSD, path-safety, compression, and shape-search tests

## Scope of v0.1

Version 1 supports a flat composition, one default layer per module, nested groups, fixed module grid placement, and automatic connector routing. Recursive compositions, automatic splitting of existing diagrams, reverse synchronization from generated output, multiple layers, and style compression are intentionally deferred.

## Upstream data

The pinned draw.io shape index and `mxfile.xsd` come from [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp) under Apache-2.0. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
