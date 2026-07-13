from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree

from .errors import DrawioComposeError, ValidationError
from .models import Bounds, CompositionSpec, ModuleDocument, ModuleSpec
from .resources import MXFILE_XSD
from .xmlio import load_graph_model


ID_PATTERN = r"^[a-z][a-z0-9-]*$"


@dataclass(frozen=True)
class CellEntry:
    element: etree._Element
    cell: etree._Element
    id: str


def _entries(model: etree._Element) -> tuple[etree._Element, list[CellEntry], list[str]]:
    errors: list[str] = []
    roots = model.findall("root")
    if len(roots) != 1:
        raise ValidationError("mxGraphModel must contain exactly one root element")
    graph_root = roots[0]
    entries: list[CellEntry] = []
    for element in graph_root:
        if element.tag == "mxCell":
            identifier = element.get("id")
            if identifier is None:
                errors.append("plain mxCell is missing id")
                continue
            entries.append(CellEntry(element, element, identifier))
        elif element.tag in {"object", "UserObject"}:
            identifier = element.get("id")
            cells = element.findall("mxCell")
            if not identifier:
                errors.append(f"{element.tag} is missing id")
                continue
            if len(cells) != 1:
                errors.append(f"{element.tag} {identifier} must contain exactly one mxCell")
                continue
            if cells[0].get("id") is not None:
                errors.append(f"{element.tag} {identifier}: nested mxCell must not have its own id")
            entries.append(CellEntry(element, cells[0], identifier))
        else:
            errors.append(f"unsupported element under graph root: {element.tag}")
    return graph_root, entries, errors


def _number(value: str | None, field: str, identifier: str, errors: list[str]) -> float:
    if value is None:
        errors.append(f"cell {identifier}: geometry is missing {field}")
        return 0.0
    try:
        return float(value)
    except ValueError:
        errors.append(f"cell {identifier}: geometry {field} must be numeric")
        return 0.0


def validate_module(spec: ModuleSpec) -> ModuleDocument:
    model, compressed, _page_name = load_graph_model(spec.src)
    errors: list[str] = []
    if model.tag != "mxGraphModel":
        errors.append(f"{spec.src}: expected mxGraphModel")
    if model.xpath("//comment()"):
        errors.append(f"{spec.src}: XML comments are not allowed")

    try:
        graph_root, entries, structural_errors = _entries(model)
        errors.extend(f"{spec.src}: {message}" for message in structural_errors)
    except ValidationError as exc:
        raise ValidationError([f"{spec.src}: {message}" for message in exc.messages]) from exc

    by_id: dict[str, CellEntry] = {}
    for entry in entries:
        if entry.id in by_id:
            errors.append(f"{spec.src}: duplicate cell id: {entry.id}")
        by_id[entry.id] = entry

    if "0" not in by_id or by_id["0"].cell.get("parent") is not None:
        errors.append(f"{spec.src}: root cell id=0 is missing or has a parent")
    if "1" not in by_id or by_id["1"].cell.get("parent") != "0":
        errors.append(f"{spec.src}: default layer id=1 parent=0 is missing")

    exports: dict[str, str] = {}
    top_level_bounds: list[tuple[float, float, float, float]] = []
    for entry in entries:
        cell = entry.cell
        if entry.id in {"0", "1"}:
            continue
        parent = cell.get("parent")
        if parent == "0":
            errors.append(f"{spec.src}: additional layers are not supported in v0.1 ({entry.id})")
        elif not parent:
            errors.append(f"{spec.src}: cell {entry.id} is missing parent")
        elif parent not in by_id:
            errors.append(f"{spec.src}: cell {entry.id} references missing parent {parent}")

        is_vertex = cell.get("vertex") == "1"
        is_edge = cell.get("edge") == "1"
        if is_vertex == is_edge:
            errors.append(f"{spec.src}: cell {entry.id} must be exactly one of vertex or edge")

        geometries = cell.findall("mxGeometry")
        if len(geometries) != 1:
            errors.append(f"{spec.src}: cell {entry.id} must contain exactly one mxGeometry")
            continue
        geometry = geometries[0]
        if is_vertex:
            x = _number(geometry.get("x", "0"), "x", entry.id, errors)
            y = _number(geometry.get("y", "0"), "y", entry.id, errors)
            width = _number(geometry.get("width"), "width", entry.id, errors)
            height = _number(geometry.get("height"), "height", entry.id, errors)
            if width <= 0 or height <= 0:
                errors.append(f"{spec.src}: cell {entry.id} width and height must be positive")
            if parent == "1":
                top_level_bounds.append((x, y, x + width, y + height))
        if is_edge:
            source = cell.get("source")
            target = cell.get("target")
            if not source or source not in by_id:
                errors.append(f"{spec.src}: edge {entry.id} has missing or invalid source")
            if not target or target not in by_id:
                errors.append(f"{spec.src}: edge {entry.id} has missing or invalid target")
            if geometry.get("relative") != "1":
                errors.append(f"{spec.src}: edge {entry.id} geometry must have relative=1")

        if entry.element.tag in {"object", "UserObject"} and entry.element.get("composeExport") == "1":
            key = entry.element.get("composeKey") or ""
            if not key:
                errors.append(f"{spec.src}: exported cell {entry.id} is missing composeKey")
            elif key in exports:
                errors.append(f"{spec.src}: duplicate exported composeKey: {key}")
            elif not __import__("re").fullmatch(r"[a-z][a-z0-9-]*", key):
                errors.append(f"{spec.src}: invalid composeKey: {key}")
            else:
                exports[key] = entry.id

    if not top_level_bounds:
        errors.append(f"{spec.src}: module has no top-level vertices")
        bounds = Bounds(0, 0, 0, 0)
    else:
        bounds = Bounds(
            min(item[0] for item in top_level_bounds),
            min(item[1] for item in top_level_bounds),
            max(item[2] for item in top_level_bounds),
            max(item[3] for item in top_level_bounds),
        )
    if errors:
        raise ValidationError(errors)
    warnings = [f"{spec.src}: compressed module should be normalized"] if compressed else []
    return ModuleDocument(spec, model, graph_root, exports, bounds, compressed, warnings)


def validate_connection_endpoints(
    composition: CompositionSpec,
    modules: dict[str, ModuleDocument],
) -> None:
    errors: list[str] = []
    for connection in composition.connections:
        for role, endpoint in (("from", connection.source), ("to", connection.target)):
            module_id, key = endpoint.split(".", 1)
            module = modules.get(module_id)
            if module is None:
                errors.append(f"connection {connection.id}: {role} references unknown module {module_id}")
            elif key not in module.exports:
                errors.append(
                    f"connection {connection.id}: {role} references non-exported node {endpoint}"
                )
    if errors:
        raise ValidationError(errors)


@lru_cache(maxsize=1)
def _mxfile_schema() -> etree.XMLSchema:
    try:
        return etree.XMLSchema(etree.parse(str(MXFILE_XSD)))
    except (OSError, etree.XMLSchemaParseError, etree.XMLSyntaxError) as exc:
        raise DrawioComposeError(f"cannot load mxfile schema: {exc}") from exc


def validate_final_document(mxfile: etree._Element) -> None:
    errors: list[str] = []
    schema = _mxfile_schema()
    if not schema.validate(mxfile):
        errors.extend(f"mxfile XSD: {error.message}" for error in schema.error_log)

    model = mxfile.find("./diagram/mxGraphModel")
    if model is None:
        errors.append("final document is missing mxGraphModel")
    else:
        try:
            _root, entries, entry_errors = _entries(model)
            errors.extend(entry_errors)
            by_id = {entry.id: entry for entry in entries}
            if len(by_id) != len(entries):
                errors.append("final document contains duplicate cell IDs")
            for entry in entries:
                if entry.id in {"0", "1"}:
                    continue
                for attribute in ("parent", "source", "target"):
                    reference = entry.cell.get(attribute)
                    if reference and reference not in by_id:
                        errors.append(
                            f"final cell {entry.id} references missing {attribute} {reference}"
                        )
                if entry.cell.get("edge") == "1":
                    geometry = entry.cell.find("mxGeometry")
                    if geometry is None or geometry.get("relative") != "1":
                        errors.append(f"final edge {entry.id} must have relative geometry")
        except ValidationError as exc:
            errors.extend(exc.messages)
    if errors:
        raise ValidationError(errors)
