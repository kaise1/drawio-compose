from __future__ import annotations

import base64
import copy
import os
import tempfile
import urllib.parse
import zlib
from pathlib import Path

from lxml import etree

from .errors import DrawioComposeError, ValidationError


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        remove_blank_text=True,
        resolve_entities=False,
        no_network=True,
        recover=False,
        remove_comments=False,
    )


def parse_xml_bytes(data: bytes, source: str) -> etree._Element:
    try:
        return etree.fromstring(data, parser=_parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValidationError(f"{source}: invalid XML: {exc}") from exc


def parse_xml_file(path: Path) -> etree._Element:
    try:
        return parse_xml_bytes(path.read_bytes(), str(path))
    except OSError as exc:
        raise DrawioComposeError(f"cannot read {path}: {exc}") from exc


def _decode_compressed_diagram(payload: str, source: str) -> etree._Element:
    try:
        compressed = base64.b64decode(payload, validate=True)
        encoded = zlib.decompress(compressed, -15).decode("utf-8")
        xml = urllib.parse.unquote(encoded).encode("utf-8")
    except (ValueError, zlib.error, UnicodeDecodeError) as exc:
        raise ValidationError(f"{source}: invalid compressed draw.io page: {exc}") from exc
    model = parse_xml_bytes(xml, source)
    if model.tag != "mxGraphModel":
        raise ValidationError(f"{source}: compressed page does not contain mxGraphModel")
    return model


def load_graph_model(path: Path) -> tuple[etree._Element, bool, str]:
    document = parse_xml_file(path)
    if document.tag == "mxGraphModel":
        return copy.deepcopy(document), False, path.stem
    if document.tag != "mxfile":
        raise ValidationError(f"{path}: expected mxfile or mxGraphModel, got {document.tag}")

    diagrams = document.findall("diagram")
    if len(diagrams) != 1:
        raise ValidationError(f"{path}: module must contain exactly one diagram page")
    diagram = diagrams[0]
    page_name = diagram.get("name") or path.stem
    model = diagram.find("mxGraphModel")
    if model is not None:
        return copy.deepcopy(model), False, page_name

    payload = (diagram.text or "").strip()
    if not payload:
        raise ValidationError(f"{path}: diagram page has no mxGraphModel content")
    return _decode_compressed_diagram(payload, str(path)), True, page_name


def make_uncompressed_mxfile(
    model: etree._Element,
    page_name: str,
    page_id: str = "page-1",
) -> etree._Element:
    mxfile = etree.Element("mxfile", compressed="false")
    diagram = etree.SubElement(mxfile, "diagram", id=page_id, name=page_name)
    diagram.append(copy.deepcopy(model))
    return mxfile


def canonical_xml_bytes(element: etree._Element) -> bytes:
    body = etree.tostring(element, method="c14n2", with_comments=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body + b"\n"


def atomic_write(path: Path, data: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
