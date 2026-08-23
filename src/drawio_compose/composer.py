from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from lxml import etree

from .models import CompositionSpec, ModuleDocument
from .validation import validate_connection_endpoints, validate_final_document, validate_module
from .xmlio import canonical_xml_bytes, edge_absolute_points


DEFAULT_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
MODULE_STYLE = (
    "swimlane;startSize=30;horizontal=1;container=1;pointerEvents=0;"
    "collapsible=0;rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;"
    "strokeColor=#666666;fontStyle=1;"
)
HEADER_SIZE = 30.0
OUTER_MARGIN = 40.0


@dataclass(frozen=True)
class BuildResult:
    xml: bytes
    symbols: bytes
    warnings: tuple[str, ...]


def load_modules(composition: CompositionSpec) -> dict[str, ModuleDocument]:
    modules = {spec.id: validate_module(spec) for spec in composition.modules}
    validate_connection_endpoints(composition, modules)
    return modules


def symbols_document(
    composition: CompositionSpec,
    modules: dict[str, ModuleDocument],
) -> bytes:
    payload = {
        "composition": composition.id,
        "modules": [
            {
                "id": spec.id,
                "label": spec.label,
                "src": spec.src_text,
                "row": spec.row,
                "column": spec.column,
                "exports": sorted(modules[spec.id].exports),
            }
            for spec in composition.modules
        ],
        "connections": [
            {
                "id": connection.id,
                "from": connection.source,
                "to": connection.target,
                "label": connection.label,
            }
            for connection in composition.connections
        ],
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fmt(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".6f").rstrip("0").rstrip(".")


def _global_id(module_id: str, local_id: str) -> str:
    return f"m_{module_id}__{local_id}"


def _visual_cell(element: etree._Element) -> etree._Element | None:
    if element.tag == "mxCell":
        return element
    if element.tag in {"object", "UserObject"}:
        return element.find("mxCell")
    return None


def _copy_module_elements(
    module: ModuleDocument,
    module_container_id: str,
    padding: float,
) -> list[etree._Element]:
    copied: list[etree._Element] = []
    shift_x = padding - module.bounds.min_x
    shift_y = HEADER_SIZE + padding - module.bounds.min_y
    for source in module.graph_root:
        if source.tag == "mxCell" and source.get("id") in {"0", "1"}:
            continue
        element = copy.deepcopy(source)
        cell = _visual_cell(element)
        if cell is not None and cell.get("parent") == "1" and cell.get("vertex") == "1":
            geometry = cell.find("mxGeometry")
            if geometry is not None:
                geometry.set("x", _fmt(float(geometry.get("x", "0")) + shift_x))
                geometry.set("y", _fmt(float(geometry.get("y", "0")) + shift_y))
        elif cell is not None and cell.get("parent") == "1" and cell.get("edge") == "1":
            geometry = cell.find("mxGeometry")
            if geometry is not None:
                for point in edge_absolute_points(geometry):
                    for attribute, shift in (("x", shift_x), ("y", shift_y)):
                        value = point.get(attribute)
                        if value is not None:
                            point.set(attribute, _fmt(float(value) + shift))

        for descendant in element.iter():
            identifier = descendant.get("id")
            if identifier and identifier not in {"0", "1"}:
                descendant.set("id", _global_id(module.spec.id, identifier))
            for attribute in ("parent", "source", "target"):
                reference = descendant.get(attribute)
                if reference == "1" and attribute == "parent":
                    descendant.set(attribute, module_container_id)
                elif reference and reference not in {"0", "1"}:
                    descendant.set(attribute, _global_id(module.spec.id, reference))
        copied.append(element)
    return copied


def _grid_positions(
    composition: CompositionSpec,
    modules: dict[str, ModuleDocument],
) -> tuple[dict[int, float], dict[int, float], dict[str, tuple[float, float]]]:
    widths: dict[int, float] = {}
    heights: dict[int, float] = {}
    sizes: dict[str, tuple[float, float]] = {}
    for spec in composition.modules:
        module = modules[spec.id]
        width = module.bounds.width + composition.padding * 2
        height = module.bounds.height + composition.padding * 2 + HEADER_SIZE
        sizes[spec.id] = (width, height)
        widths[spec.column] = max(widths.get(spec.column, 0), width)
        heights[spec.row] = max(heights.get(spec.row, 0), height)

    column_positions: dict[int, float] = {}
    cursor = OUTER_MARGIN
    for column in sorted(widths):
        column_positions[column] = cursor
        cursor += widths[column] + composition.column_gap
    row_positions: dict[int, float] = {}
    cursor = OUTER_MARGIN
    for row in sorted(heights):
        row_positions[row] = cursor
        cursor += heights[row] + composition.row_gap
    return column_positions, row_positions, sizes


def build_composition(composition: CompositionSpec) -> BuildResult:
    modules = load_modules(composition)
    columns, rows, sizes = _grid_positions(composition, modules)

    total_width = max(columns[s.column] + sizes[s.id][0] for s in composition.modules) + OUTER_MARGIN
    total_height = max(rows[s.row] + sizes[s.id][1] for s in composition.modules) + OUTER_MARGIN
    mxfile = etree.Element("mxfile", compressed="false")
    diagram = etree.SubElement(mxfile, "diagram", id=composition.id, name=composition.page_name)
    model = etree.SubElement(
        diagram,
        "mxGraphModel",
        dx="0",
        dy="0",
        grid="1",
        gridSize="10",
        guides="1",
        tooltips="1",
        connect="1",
        arrows="1",
        fold="1",
        page="1",
        pageScale="1",
        pageWidth=_fmt(total_width),
        pageHeight=_fmt(total_height),
        math="0",
        shadow="0",
        adaptiveColors="auto",
    )
    graph_root = etree.SubElement(model, "root")
    etree.SubElement(graph_root, "mxCell", id="0")
    etree.SubElement(graph_root, "mxCell", id="1", parent="0")

    global_exports: dict[str, str] = {}
    for spec in composition.modules:
        module = modules[spec.id]
        container_id = f"module__{spec.id}"
        width, height = sizes[spec.id]
        container = etree.SubElement(
            graph_root,
            "mxCell",
            id=container_id,
            value=spec.label,
            style=MODULE_STYLE,
            vertex="1",
            parent="1",
        )
        etree.SubElement(
            container,
            "mxGeometry",
            x=_fmt(columns[spec.column]),
            y=_fmt(rows[spec.row]),
            width=_fmt(width),
            height=_fmt(height),
            **{"as": "geometry"},
        )
        for element in _copy_module_elements(module, container_id, composition.padding):
            graph_root.append(element)
        for key, local_id in module.exports.items():
            global_exports[f"{spec.id}.{key}"] = _global_id(spec.id, local_id)

    for connection in composition.connections:
        edge = etree.SubElement(
            graph_root,
            "mxCell",
            id=f"connection__{connection.id}",
            value=connection.label,
            style=connection.style or DEFAULT_EDGE_STYLE,
            edge="1",
            parent="1",
            source=global_exports[connection.source],
            target=global_exports[connection.target],
        )
        etree.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})

    validate_final_document(mxfile)
    warnings = tuple(warning for module in modules.values() for warning in module.warnings)
    return BuildResult(
        xml=canonical_xml_bytes(mxfile),
        symbols=symbols_document(composition, modules),
        warnings=warnings,
    )
