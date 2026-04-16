# Code Property Graph Architecture

## Purpose

The CPG pipeline in `backend/cpg_builder/` builds a heterogeneous multigraph that merges:

- repository structure
- syntax trees
- semantic symbol and scope relations
- lightweight program-analysis links where heuristics are reliable

The result is a single graph representation that keeps syntax and semantics connected through stable IDs and AST anchors, which makes it suitable for graph learning and explainable visualization.

## Layers

### Repository layer

`repo_index.py` walks a repository, prefers `git ls-files -co --exclude-standard` when the repo is git-backed, and falls back to recursive walking otherwise. It emits file records with:

- relative path
- inferred language
- SHA-256 content hash
- size
- last-modified time
- optional git ref

It also records directory and package nodes so the graph retains repository topology.

### AST layer

`ast_builder.py` uses Tree-sitter parsers from `parser.py` and creates:

- one `AST_ROOT` per file
- `AST_NODE` nodes for named syntax nodes by default
- `AST_CHILD`, `AST_PARENT`, and `AST_NEXT_SIBLING` edges with child ordering preserved

Each syntax node stores byte offsets, point ranges, the field name when available, and a small text snippet.

Tree-sitter previous trees can be supplied for changed files, allowing incremental reparsing and changed-range reporting.

### Semantic layer

`semantic_builder.py` traverses parsed ASTs and builds a first-pass semantic graph with:

- module symbols and module scopes
- classes
- functions and methods
- variables
- imports
- callsites
- unresolved placeholder symbols when name resolution fails

Semantic nodes that originate from syntax keep `anchor_ast_id` so downstream consumers can jump back to the AST.

Resolution strategy is intentionally conservative:

1. Resolve inside the current scope.
2. Fall back to enclosing scopes.
3. Fall back to module-level imported names and exported symbols.
4. If unresolved, create a stable placeholder symbol with `unresolved=true`.

This keeps links partial but trustworthy.

### Fusion layer

`fusion.py` builds a `networkx.MultiDiGraph` with four high-level categories:

- `meta`
- `syntax`
- `semantic`
- `flow`

Node labels currently include:

- `REPO`
- `DIRECTORY`
- `FILE`
- `MODULE`
- `PACKAGE`
- `AST_ROOT`
- `AST_NODE`
- `SYMBOL`
- `SCOPE`
- `TYPE`
- `FUNCTION`
- `METHOD`
- `CLASS`
- `MODULE_SYMBOL`
- `PARAMETER`
- `VARIABLE`
- `IMPORT`
- `LITERAL`
- `CALLSITE`

Edge labels currently include:

- containment: `REPO_CONTAINS_DIR`, `DIR_CONTAINS_FILE`, `FILE_CONTAINS_AST_ROOT`
- syntax: `AST_CHILD`, `AST_PARENT`, `AST_NEXT_SIBLING`
- semantic: `DECLARES`, `REFERENCES`, `HAS_TYPE`, `CALLS`, `IMPORTS`, `INHERITS`, `OVERRIDES`, `DEFINES`, `USES`, `DEF_USE`, `RETURNS`, `CAPTURES`, `BELONGS_TO_SCOPE`, `RESOLVES_TO`, `ALIASES`
- optional flow placeholders: `CFG_NEXT`, `CDG_DEPENDS_ON`, `DDG_REACHES`

The current implementation focuses on repository structure, AST preservation, symbol tables, callsites, imports, and def-use links. The schema already reserves flow edges for later extension.

## Stable IDs

IDs are generated from deterministic hashes over:

- repository path for the repo node
- relative path plus byte spans for AST nodes
- semantic label, scope, name, and AST anchor for semantic nodes
- edge label and endpoint IDs for edges

That keeps unchanged files stable across repeated builds and supports diffing between revisions.

## Diff model

`git_diff.py` computes changed files with `git diff --name-only` and materializes both refs into temp directories. The head build can reuse the base parsed trees for unchanged paths, then `diff_artifacts(...)` compares nodes and edges by stable ID plus attribute fingerprints.

The emitted diff contains:

- `added_nodes`
- `removed_nodes`
- `changed_nodes`
- `added_edges`
- `removed_edges`
- `changed_edges`

## Current semantic approximations

The first implementation intentionally uses conservative heuristics:

- local lexical scoping for declarations and references
- module-level import linking where target modules can be identified
- unresolved placeholders instead of guessed symbols
- def-use links tied to name matches inside visible scope
- call graph edges created when a callsite target resolves in known scope

These heuristics are partial but predictable, which is usually better than emitting broad, low-confidence edges for training data.

## Next extensions

- better import binding resolution for named imports and re-exports
- type inference and `HAS_TYPE` edges for annotations and literals
- explicit parameter and return modeling across all supported languages
- CFG, CDG, and DDG construction per language
- dependency-driven impacted-file recomputation beyond direct file changes
- optional persistence of intermediate AST and symbol tables for faster repeated analysis
