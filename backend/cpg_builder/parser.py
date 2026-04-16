from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParseResult:
    tree: Any
    changed_ranges: list[dict[str, Any]]


class TreeSitterRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def parser_for_language(self, language: str) -> Any | None:
        if language in self._cache:
            return self._cache[language]

        try:
            from tree_sitter import Language, Parser
        except ImportError:
            self._cache[language] = None
            return None

        parser = None
        try:
            if language == "typescript":
                import tree_sitter_typescript as tsts  # type: ignore

                parser = Parser(Language(tsts.language_typescript()))
            elif language == "tsx":
                import tree_sitter_typescript as tsts  # type: ignore

                parser = Parser(Language(tsts.language_tsx()))
            elif language == "javascript":
                import tree_sitter_javascript as tsjs  # type: ignore

                parser = Parser(Language(tsjs.language()))
            elif language == "python":
                import tree_sitter_python as tspy  # type: ignore

                parser = Parser(Language(tspy.language()))
            elif language == "java":
                import tree_sitter_java as tsjava  # type: ignore

                parser = Parser(Language(tsjava.language()))
        except Exception:
            parser = None

        self._cache[language] = parser
        return parser

    def parser_for_file(self, path: Path, language: str) -> Any | None:
        if language == "typescript" and path.suffix == ".tsx":
            return self.parser_for_language("tsx")
        return self.parser_for_language(language)


def parse_source(
    parser: Any,
    source_bytes: bytes,
    previous_tree: Any | None = None,
) -> ParseResult:
    if parser is None:
        raise ValueError("Parser is required")

    tree = None
    if previous_tree is not None:
        try:
            tree = parser.parse(source_bytes, previous_tree)
        except TypeError:
            try:
                tree = parser.parse(source_bytes, old_tree=previous_tree)
            except TypeError:
                tree = parser.parse(source_bytes)
    else:
        tree = parser.parse(source_bytes)

    changed_ranges: list[dict[str, Any]] = []
    if previous_tree is not None:
        try:
            for change in previous_tree.changed_ranges(tree):
                changed_ranges.append(
                    {
                        "start_byte": int(change.start_byte),
                        "end_byte": int(change.end_byte),
                        "start_point": {
                            "row": int(change.start_point[0]),
                            "column": int(change.start_point[1]),
                        },
                        "end_point": {
                            "row": int(change.end_point[0]),
                            "column": int(change.end_point[1]),
                        },
                    },
                )
        except Exception:
            changed_ranges = []

    return ParseResult(tree=tree, changed_ranges=changed_ranges)
