from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .composer import build_composition, load_modules, symbols_document
from .errors import DrawioComposeError
from .manifest import parse_composition
from .render import render_diagram
from .shapes import search_shapes
from .xmlio import atomic_write, canonical_xml_bytes, load_graph_model, make_uncompressed_mxfile


def _emit_warnings(warnings: list[str] | tuple[str, ...]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _command_validate(args: argparse.Namespace) -> None:
    composition = parse_composition(args.composition)
    result = build_composition(composition)
    _emit_warnings(result.warnings)
    print(f"OK: {composition.path}")


def _command_build(args: argparse.Namespace) -> None:
    composition = parse_composition(args.composition)
    result = build_composition(composition)
    output = Path(args.output)
    atomic_write(output, result.xml)
    _emit_warnings(result.warnings)
    print(output.resolve())


def _command_symbols(args: argparse.Namespace) -> None:
    composition = parse_composition(args.composition)
    modules = load_modules(composition)
    output = Path(args.output)
    atomic_write(output, symbols_document(composition, modules))
    _emit_warnings([warning for module in modules.values() for warning in module.warnings])
    print(output.resolve())


def _command_normalize(args: argparse.Namespace) -> None:
    source = Path(args.module).resolve()
    model, _compressed, page_name = load_graph_model(source)
    if args.in_place:
        output = source
    elif args.output:
        output = Path(args.output).resolve()
    else:
        raise DrawioComposeError("normalize requires --in-place or --output")
    mxfile = make_uncompressed_mxfile(model, page_name)
    atomic_write(output, canonical_xml_bytes(mxfile))
    print(output)


def _command_shape_search(args: argparse.Namespace) -> None:
    results = search_shapes(args.query, args.limit)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for item in results:
        print(f"{item['title']} ({item['w']}x{item['h']})")
        print(f"  {item['style']}")


def _command_render(args: argparse.Namespace) -> None:
    source = Path(args.diagram)
    output = Path(args.output)
    render_diagram(source, output)
    print(output.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drawio-compose")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a composition and all modules")
    validate.add_argument("composition")
    validate.set_defaults(handler=_command_validate)

    build = commands.add_parser("build", help="build a deterministic .drawio file")
    build.add_argument("composition")
    build.add_argument("-o", "--output", required=True)
    build.set_defaults(handler=_command_build)

    symbols = commands.add_parser("symbols", help="write the compact public symbol index")
    symbols.add_argument("composition")
    symbols.add_argument("-o", "--output", required=True)
    symbols.set_defaults(handler=_command_symbols)

    normalize = commands.add_parser("normalize", help="convert a module to canonical XML")
    normalize.add_argument("module")
    destination = normalize.add_mutually_exclusive_group()
    destination.add_argument("--in-place", action="store_true")
    destination.add_argument("-o", "--output")
    normalize.set_defaults(handler=_command_normalize)

    shape_search = commands.add_parser("shape-search", help="search the pinned draw.io shape index")
    shape_search.add_argument("query")
    shape_search.add_argument("--limit", type=int, default=5)
    shape_search.add_argument("--json", action="store_true")
    shape_search.set_defaults(handler=_command_shape_search)

    render = commands.add_parser("render", help="render with draw.io Desktop CLI")
    render.add_argument("diagram")
    render.add_argument("-o", "--output", required=True)
    render.set_defaults(handler=_command_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except DrawioComposeError as exc:
        for line in str(exc).splitlines():
            print(f"error: {line}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
