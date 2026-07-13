# drawio-compose format version 1

## Composition document

A composition is a local XML file with one `composition` root. Module paths are resolved relative to this file and must remain inside its directory.

```xml
<composition version="1" id="hybrid-enterprise"
             pageName="Hybrid Architecture"
             columnGap="80" rowGap="80" padding="30">
  <modules>
    <module id="on-premises" src="modules/on-premises.drawio"
            label="On-Premises" row="0" column="0"/>
    <module id="aws-platform" src="modules/aws-platform.drawio"
            label="AWS Platform" row="0" column="1"/>
  </modules>
  <connections>
    <connect id="private-link"
             from="on-premises.private-endpoint"
             to="aws-platform.ingress" label="Private routing"/>
  </connections>
</composition>
```

Module, connection, and public-key identifiers must match `[a-z][a-z0-9-]*`. Module grid slots and IDs must be unique. `columnGap`, `rowGap`, and `padding` are non-negative pixel values with defaults of 80, 80, and 30.

Connections require stable IDs and `module-id.public-key` endpoints. The optional `style` attribute replaces the default orthogonal draw.io edge style.

## Module document

A canonical module is an uncompressed `.drawio` file containing exactly one page and one default layer:

```xml
<mxfile compressed="false">
  <diagram id="module" name="Module">
    <mxGraphModel>
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Every visible element must have a unique local ID, one geometry, and exactly one of `vertex="1"` or `edge="1"`. Edges require valid local `source` and `target` IDs and `<mxGeometry relative="1" as="geometry"/>`.

Expose a node by wrapping its visual cell in `object` or `UserObject` and setting `composeKey` plus `composeExport="1"`. Public keys must be unique inside the module. Nested groups are supported; additional layers are not supported in version 1.

Compressed modules can be read and validated, but should be converted with `drawio-compose normalize MODULE --in-place` before agent editing.

## Build behavior

The assembler:

1. Validates the composition and every module.
2. Computes each module's local bounding box.
3. Creates a titled draw.io container for each fixed grid slot.
4. Prefixes local IDs and rewrites `parent`, `source`, and `target` references.
5. Generates cross-module edges only between exported nodes.
6. Validates the final document with the official mxfile XSD and semantic reference checks.
7. Writes uncompressed canonical XML without timestamps or XML comments.

The combined `.drawio` is generated output. Changes made directly to it are not synchronized back to module sources.
