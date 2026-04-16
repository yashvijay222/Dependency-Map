from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class NodeCategory(StrEnum):
    META = "meta"
    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    FLOW = "flow"


class EdgeCategory(StrEnum):
    CONTAINMENT = "containment"
    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    FLOW = "flow"


class NodeLabel(StrEnum):
    REPO = "REPO"
    DIRECTORY = "DIRECTORY"
    FILE = "FILE"
    MODULE = "MODULE"
    PACKAGE = "PACKAGE"
    AST_ROOT = "AST_ROOT"
    AST_NODE = "AST_NODE"
    SYMBOL = "SYMBOL"
    SCOPE = "SCOPE"
    TYPE = "TYPE"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    CLASS = "CLASS"
    MODULE_SYMBOL = "MODULE_SYMBOL"
    PARAMETER = "PARAMETER"
    VARIABLE = "VARIABLE"
    IMPORT = "IMPORT"
    LITERAL = "LITERAL"
    CALLSITE = "CALLSITE"


class EdgeLabel(StrEnum):
    REPO_CONTAINS_DIR = "REPO_CONTAINS_DIR"
    DIR_CONTAINS_FILE = "DIR_CONTAINS_FILE"
    FILE_CONTAINS_AST_ROOT = "FILE_CONTAINS_AST_ROOT"
    AST_CHILD = "AST_CHILD"
    AST_PARENT = "AST_PARENT"
    AST_NEXT_SIBLING = "AST_NEXT_SIBLING"
    DECLARES = "DECLARES"
    REFERENCES = "REFERENCES"
    HAS_TYPE = "HAS_TYPE"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    OVERRIDES = "OVERRIDES"
    DEFINES = "DEFINES"
    USES = "USES"
    DEF_USE = "DEF_USE"
    RETURNS = "RETURNS"
    CAPTURES = "CAPTURES"
    BELONGS_TO_SCOPE = "BELONGS_TO_SCOPE"
    RESOLVES_TO = "RESOLVES_TO"
    ALIASES = "ALIASES"
    CFG_NEXT = "CFG_NEXT"
    CDG_DEPENDS_ON = "CDG_DEPENDS_ON"
    DDG_REACHES = "DDG_REACHES"


SUPPORTED_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
}


@dataclass(slots=True)
class NodeRecord:
    id: str
    label: str
    category: str
    language: str
    file_path: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Node id is required")
        if not self.label:
            raise ValueError(f"Node {self.id} is missing label")
        if self.label not in NodeLabel._value2member_map_:
            raise ValueError(f"Node {self.id} has unsupported label {self.label}")
        if not self.category:
            raise ValueError(f"Node {self.id} is missing category")
        if self.category not in NodeCategory._value2member_map_:
            raise ValueError(f"Node {self.id} has unsupported category {self.category}")
        if self.language is None:
            raise ValueError(f"Node {self.id} is missing language")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "language": self.language,
            "file_path": self.file_path,
            **self.properties,
        }


@dataclass(slots=True)
class EdgeRecord:
    id: str
    label: str
    src: str
    dst: str
    category: str
    properties: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Edge id is required")
        if not self.label:
            raise ValueError(f"Edge {self.id} is missing label")
        if self.label not in EdgeLabel._value2member_map_:
            raise ValueError(f"Edge {self.id} has unsupported label {self.label}")
        if not self.src or not self.dst:
            raise ValueError(f"Edge {self.id} must have src and dst")
        if not self.category:
            raise ValueError(f"Edge {self.id} is missing category")
        if self.category not in EdgeCategory._value2member_map_:
            raise ValueError(f"Edge {self.id} has unsupported category {self.category}")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "label": self.label,
            "src": self.src,
            "dst": self.dst,
            "category": self.category,
            **self.properties,
        }


@dataclass(slots=True)
class FileRecord:
    path: Path
    repo_root: Path
    language: str
    sha256: str
    size: int
    last_modified: float
    git_ref: str | None = None

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(self.repo_root).as_posix()


@dataclass(slots=True)
class RepoIndex:
    repo_root: Path
    repo_id: str
    files: list[FileRecord]
    directories: list[str]
    packages: list[str]
    git_ref: str | None = None


@dataclass(slots=True)
class ParsedFile:
    file: FileRecord
    source_bytes: bytes
    tree: Any
    root_id: str
    ast_nodes: list[NodeRecord]
    ast_edges: list[EdgeRecord]
    ast_index: dict[str, dict[str, Any]]
    changed_ranges: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class BuildArtifacts:
    repo_index: RepoIndex
    parsed_files: list[ParsedFile]
    nodes: list[NodeRecord]
    edges: list[EdgeRecord]
    summaries: dict[str, Any]


@dataclass(slots=True)
class GraphDiff:
    added_nodes: list[dict[str, Any]]
    removed_nodes: list[dict[str, Any]]
    changed_nodes: list[dict[str, Any]]
    added_edges: list[dict[str, Any]]
    removed_edges: list[dict[str, Any]]
    changed_edges: list[dict[str, Any]]
