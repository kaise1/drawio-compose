from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    src: Path
    src_text: str
    label: str
    row: int
    column: int


@dataclass(frozen=True)
class ConnectionSpec:
    id: str
    source: str
    target: str
    label: str = ""
    style: str | None = None


@dataclass(frozen=True)
class CompositionSpec:
    path: Path
    id: str
    page_name: str
    column_gap: float
    row_gap: float
    padding: float
    modules: tuple[ModuleSpec, ...]
    connections: tuple[ConnectionSpec, ...]


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


@dataclass
class ModuleDocument:
    spec: ModuleSpec
    model: etree._Element
    graph_root: etree._Element
    exports: dict[str, str]
    bounds: Bounds
    compressed: bool = False
    warnings: list[str] = field(default_factory=list)
