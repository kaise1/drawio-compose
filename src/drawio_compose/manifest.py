from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

from .errors import DrawioComposeError, ValidationError
from .models import CompositionSpec, ConnectionSpec, ModuleSpec
from .resources import COMPOSITION_XSD
from .xmlio import parse_xml_file


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    try:
        return etree.XMLSchema(etree.parse(str(COMPOSITION_XSD)))
    except (OSError, etree.XMLSchemaParseError, etree.XMLSyntaxError) as exc:
        raise DrawioComposeError(f"cannot load composition schema: {exc}") from exc


def _schema_errors(document: etree._Element) -> list[str]:
    schema = _schema()
    if schema.validate(document):
        return []
    return [f"composition XML: {error.message}" for error in schema.error_log]


def parse_composition(path: str | Path) -> CompositionSpec:
    manifest_path = Path(path).resolve()
    document = parse_xml_file(manifest_path)
    errors = _schema_errors(document)
    if document.xpath("//comment()"):
        errors.append("composition XML: XML comments are not allowed")
    if errors:
        raise ValidationError(errors)

    base = manifest_path.parent.resolve()
    modules: list[ModuleSpec] = []
    module_ids: set[str] = set()
    slots: set[tuple[int, int]] = set()
    for node in document.find("modules").findall("module"):
        module_id = node.get("id") or ""
        src_text = node.get("src") or ""
        relative = Path(src_text)
        if relative.is_absolute():
            errors.append(f"module {module_id}: src must be relative")
            continue
        resolved = (base / relative).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            errors.append(f"module {module_id}: src escapes the composition directory")
            continue
        row = int(node.get("row") or 0)
        column = int(node.get("column") or 0)
        if module_id in module_ids:
            errors.append(f"duplicate module id: {module_id}")
        if (row, column) in slots:
            errors.append(f"duplicate module grid slot: row={row}, column={column}")
        module_ids.add(module_id)
        slots.add((row, column))
        modules.append(
            ModuleSpec(
                id=module_id,
                src=resolved,
                src_text=relative.as_posix(),
                label=node.get("label") or module_id,
                row=row,
                column=column,
            )
        )

    connections: list[ConnectionSpec] = []
    connection_ids: set[str] = set()
    container = document.find("connections")
    if container is not None:
        for node in container.findall("connect"):
            connection_id = node.get("id") or ""
            if connection_id in connection_ids:
                errors.append(f"duplicate connection id: {connection_id}")
            connection_ids.add(connection_id)
            connections.append(
                ConnectionSpec(
                    id=connection_id,
                    source=node.get("from") or "",
                    target=node.get("to") or "",
                    label=node.get("label") or "",
                    style=node.get("style"),
                )
            )

    if errors:
        raise ValidationError(errors)
    return CompositionSpec(
        path=manifest_path,
        id=document.get("id") or "composition",
        page_name=document.get("pageName") or document.get("id") or "Architecture",
        column_gap=float(document.get("columnGap") or 80),
        row_gap=float(document.get("rowGap") or 80),
        padding=float(document.get("padding") or 30),
        modules=tuple(modules),
        connections=tuple(connections),
    )
