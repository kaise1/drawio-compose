from __future__ import annotations

import base64
import contextlib
import io
import tempfile
import unittest
import urllib.parse
import zlib
from pathlib import Path

from lxml import etree

from drawio_compose.composer import build_composition
from drawio_compose.cli import main as cli_main
from drawio_compose.errors import DrawioComposeError, ValidationError
from drawio_compose.manifest import parse_composition
from drawio_compose.models import ModuleSpec
from drawio_compose.shapes import search_shapes
from drawio_compose.validation import validate_module
from drawio_compose.xmlio import canonical_xml_bytes, load_graph_model, make_uncompressed_mxfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT_ROOT / "examples" / "hybrid-enterprise" / "hybrid-enterprise.compose.xml"


def module_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<mxfile compressed="false"><diagram id="p" name="Module">'
        '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        f"{body}</root></mxGraphModel></diagram></mxfile>"
    )


def vertex(identifier: str, *, exported: str | None = None) -> str:
    cell = (
        '<mxCell style="rounded=1;" vertex="1" parent="1">'
        '<mxGeometry x="0" y="0" width="100" height="60" as="geometry"/>'
        '</mxCell>'
    )
    if exported is not None:
        return (
            f'<object id="{identifier}" label="Export" composeKey="{exported}" '
            f'composeExport="1">{cell}</object>'
        )
    return cell.replace('<mxCell ', f'<mxCell id="{identifier}" ')


class DrawioComposeTests(unittest.TestCase):
    def test_hybrid_example_is_deterministic_and_context_efficient(self) -> None:
        composition = parse_composition(EXAMPLE)
        first = build_composition(composition)
        second = build_composition(composition)
        self.assertEqual(first.xml, second.xml)
        manifest_size = EXAMPLE.stat().st_size
        module_size = next(
            spec.src.stat().st_size for spec in composition.modules if spec.id == "aws-application"
        )
        working_set = manifest_size + module_size + len(first.symbols)
        self.assertLessEqual(working_set / len(first.xml), 0.35)

    def test_shape_search_returns_official_transit_gateway_style(self) -> None:
        results = search_shapes("aws transit gateway", 5)
        self.assertTrue(results)
        self.assertTrue(
            any("transit_gateway" in str(item["style"]) for item in results),
            results,
        )

    def test_shape_search_prefers_current_aws4_icons(self) -> None:
        for query, expected in (
            ("aws application load balancer", "mxgraph.aws4.application_load_balancer"),
            ("aws rds", "resIcon=mxgraph.aws4.rds"),
            ("aws s3", "resIcon=mxgraph.aws4.s3"),
        ):
            with self.subTest(query=query):
                results = search_shapes(query, 5)
                self.assertTrue(results)
                self.assertIn(expected, str(results[0]["style"]))

    def test_hybrid_example_has_no_legacy_aws_icons(self) -> None:
        module_dir = EXAMPLE.parent / "modules"
        legacy_markers = ("mxgraph.aws3.", "mxgraph.aws3d.", "mxgraph.webicons.aws")
        for module in module_dir.glob("*.drawio"):
            with self.subTest(module=module.name):
                xml = module.read_text(encoding="utf-8")
                self.assertFalse(any(marker in xml for marker in legacy_markers))

    def test_duplicate_cell_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.drawio"
            path.write_text(module_xml(vertex("node") + vertex("node")), encoding="utf-8")
            spec = ModuleSpec("duplicate", path, "duplicate.drawio", "Duplicate", 0, 0)
            with self.assertRaisesRegex(ValidationError, "duplicate cell id"):
                validate_module(spec)

    def test_duplicate_export_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "exports.drawio"
            path.write_text(
                module_xml(vertex("first", exported="api") + vertex("second", exported="api")),
                encoding="utf-8",
            )
            spec = ModuleSpec("exports", path, "exports.drawio", "Exports", 0, 0)
            with self.assertRaisesRegex(ValidationError, "duplicate exported composeKey"):
                validate_module(spec)

    def test_broken_internal_edge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "edge.drawio"
            edge = (
                '<mxCell id="edge" edge="1" parent="1" source="node" target="missing">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>'
            )
            path.write_text(module_xml(vertex("node") + edge), encoding="utf-8")
            spec = ModuleSpec("edge", path, "edge.drawio", "Edge", 0, 0)
            with self.assertRaisesRegex(ValidationError, "invalid target"):
                validate_module(spec)

    def test_duplicate_grid_slot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "duplicate.compose.xml"
            manifest.write_text(
                '<composition version="1" id="duplicate"><modules>'
                '<module id="first" src="first.drawio" row="0" column="0"/>'
                '<module id="second" src="second.drawio" row="0" column="0"/>'
                '</modules></composition>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "duplicate module grid slot"):
                parse_composition(manifest)

    def test_manifest_cannot_escape_its_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "escape.compose.xml"
            manifest.write_text(
                '<composition version="1" id="escape"><modules>'
                '<module id="outside" src="../outside.drawio" row="0" column="0"/>'
                '</modules></composition>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "escapes the composition directory"):
                parse_composition(manifest)

    def test_non_exported_connection_endpoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source.drawio").write_text(module_xml(vertex("internal")), encoding="utf-8")
            (root / "target.drawio").write_text(
                module_xml(vertex("target", exported="api")), encoding="utf-8"
            )
            manifest = root / "invalid.compose.xml"
            manifest.write_text(
                '<composition version="1" id="invalid"><modules>'
                '<module id="source" src="source.drawio" row="0" column="0"/>'
                '<module id="target" src="target.drawio" row="0" column="1"/>'
                '</modules><connections>'
                '<connect id="invalid-edge" from="source.internal" to="target.api"/>'
                '</connections></composition>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "non-exported node"):
                build_composition(parse_composition(manifest))

    def test_missing_module_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "missing.compose.xml"
            manifest.write_text(
                '<composition version="1" id="missing"><modules>'
                '<module id="missing-module" src="missing.drawio" row="0" column="0"/>'
                '</modules></composition>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DrawioComposeError, "cannot read"):
                build_composition(parse_composition(manifest))

    def test_failed_cli_build_does_not_overwrite_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "missing.compose.xml"
            output = root / "architecture.drawio"
            output.write_bytes(b"preserve-me")
            manifest.write_text(
                '<composition version="1" id="missing"><modules>'
                '<module id="missing-module" src="missing.drawio" row="0" column="0"/>'
                '</modules></composition>',
                encoding="utf-8",
            )
            with contextlib.redirect_stderr(io.StringIO()):
                exit_code = cli_main(["build", str(manifest), "-o", str(output)])
            self.assertEqual(exit_code, 2)
            self.assertEqual(output.read_bytes(), b"preserve-me")

    def test_generated_outputs_cannot_overwrite_composition_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = root / "module.drawio"
            module.write_text(module_xml(vertex("api", exported="api")), encoding="utf-8")
            manifest = root / "architecture.compose.xml"
            manifest.write_text(
                '<composition version="1" id="architecture"><modules>'
                '<module id="module" src="module.drawio" row="0" column="0"/>'
                "</modules></composition>",
                encoding="utf-8",
            )
            manifest_before = manifest.read_bytes()
            module_before = module.read_bytes()

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                build_exit = cli_main(["build", str(manifest), "-o", str(manifest)])
            self.assertEqual(build_exit, 2)
            self.assertIn("refusing to overwrite composition manifest", stderr.getvalue())
            self.assertEqual(manifest.read_bytes(), manifest_before)

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                symbols_exit = cli_main(["symbols", str(manifest), "-o", str(module)])
            self.assertEqual(symbols_exit, 2)
            self.assertIn("refusing to overwrite module module", stderr.getvalue())
            self.assertEqual(module.read_bytes(), module_before)

    def test_top_level_edge_points_are_shifted_and_included_in_bounds(self) -> None:
        first = (
            '<mxCell id="first" value="First" vertex="1" parent="1">'
            '<mxGeometry x="100" y="200" width="100" height="60" as="geometry"/>'
            "</mxCell>"
        )
        second = (
            '<mxCell id="second" value="Second" vertex="1" parent="1">'
            '<mxGeometry x="300" y="200" width="100" height="60" as="geometry"/>'
            "</mxCell>"
        )
        edge = (
            '<mxCell id="edge" edge="1" parent="1" source="first" target="second">'
            '<mxGeometry relative="1" as="geometry">'
            '<mxPoint x="100" y="230" as="sourcePoint"/>'
            '<mxPoint x="400" y="230" as="targetPoint"/>'
            '<Array as="points"><mxPoint x="250" y="150"/></Array>'
            '<mxPoint x="5" y="10" as="offset"/>'
            "</mxGeometry></mxCell>"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "module.drawio").write_text(
                module_xml(first + second + edge), encoding="utf-8"
            )
            manifest = root / "architecture.compose.xml"
            manifest.write_text(
                '<composition version="1" id="architecture"><modules>'
                '<module id="module" src="module.drawio" row="0" column="0"/>'
                "</modules></composition>",
                encoding="utf-8",
            )

            result = build_composition(parse_composition(manifest))
            document = etree.fromstring(result.xml)
            container = document.xpath('//mxCell[@id="module__module"]/mxGeometry')[0]
            self.assertEqual(container.get("width"), "360")
            self.assertEqual(container.get("height"), "200")

            first_geometry = document.xpath('//mxCell[@id="m_module__first"]/mxGeometry')[0]
            self.assertEqual((first_geometry.get("x"), first_geometry.get("y")), ("30", "110"))

            edge_geometry = document.xpath('//mxCell[@id="m_module__edge"]/mxGeometry')[0]
            source_point = edge_geometry.xpath('./mxPoint[@as="sourcePoint"]')[0]
            target_point = edge_geometry.xpath('./mxPoint[@as="targetPoint"]')[0]
            waypoint = edge_geometry.xpath('./Array[@as="points"]/mxPoint')[0]
            offset = edge_geometry.xpath('./mxPoint[@as="offset"]')[0]
            self.assertEqual((source_point.get("x"), source_point.get("y")), ("30", "140"))
            self.assertEqual((target_point.get("x"), target_point.get("y")), ("330", "140"))
            self.assertEqual((waypoint.get("x"), waypoint.get("y")), ("180", "60"))
            self.assertEqual((offset.get("x"), offset.get("y")), ("5", "10"))

    def test_nested_group_references_are_prefixed(self) -> None:
        group = (
            '<mxCell id="group" style="group;" vertex="1" parent="1">'
            '<mxGeometry x="20" y="20" width="240" height="140" as="geometry"/>'
            '</mxCell>'
        )
        child = (
            '<mxCell id="child" value="Child" style="rounded=1;" vertex="1" parent="group">'
            '<mxGeometry x="20" y="40" width="100" height="60" as="geometry"/>'
            '</mxCell>'
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested.drawio").write_text(module_xml(group + child), encoding="utf-8")
            manifest = root / "nested.compose.xml"
            manifest.write_text(
                '<composition version="1" id="nested"><modules>'
                '<module id="nested-module" src="nested.drawio" row="0" column="0"/>'
                '</modules></composition>',
                encoding="utf-8",
            )
            result = build_composition(parse_composition(manifest))
            document = etree.fromstring(result.xml)
            nested_child = document.xpath('//mxCell[@id="m_nested-module__child"]')[0]
            self.assertEqual(nested_child.get("parent"), "m_nested-module__group")

    def test_compressed_module_loads_with_warning_and_normalizes(self) -> None:
        graph = (
            '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f'{vertex("api", exported="api")}</root></mxGraphModel>'
        )
        encoded = urllib.parse.quote(graph, safe="~()*!.'-_")
        compressor = zlib.compressobj(wbits=-15)
        payload = base64.b64encode(compressor.compress(encoded.encode()) + compressor.flush()).decode()
        compressed = f'<mxfile compressed="true"><diagram id="p" name="Compressed">{payload}</diagram></mxfile>'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "compressed.drawio"
            path.write_text(compressed, encoding="utf-8")
            spec = ModuleSpec("compressed", path, "compressed.drawio", "Compressed", 0, 0)
            document = validate_module(spec)
            self.assertTrue(document.compressed)
            self.assertTrue(document.warnings)
            model, was_compressed, page_name = load_graph_model(path)
            self.assertTrue(was_compressed)
            normalized = canonical_xml_bytes(make_uncompressed_mxfile(model, page_name))
            self.assertIn(b'compressed="false"', normalized)
            self.assertIn(b"mxGraphModel", normalized)


if __name__ == "__main__":
    unittest.main()
