#!/usr/bin/env python3
"""
C source code traversal and topological ordering tool.

Uses clang to parse C source files and produces a topological ordering
of symbols (structs, typedefs, functions) based on their dependencies.
"""

import os
import sys
from collections import defaultdict, deque
from pathlib import Path

import clang.cindex as clang
from pydantic import BaseModel


class Symbol(BaseModel):
    """Represents a C symbol (struct, typedef, function, etc.)"""

    name: str
    kind: str  # 'struct', 'typedef', 'function', 'enum'
    file_path: str
    line_number: int
    dependencies: set[str]  # Names of symbols this depends on
    cycle: bool = False

    def __hash__(self):
        return hash((self.name, self.kind))

    def __eq__(self, other):
        return (
            isinstance(other, Symbol)
            and self.name == other.name
            and self.kind == other.kind
        )


class CTraversal:
    """Analyzes C source code and produces topological ordering of symbols."""

    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.built_in_types = {
            "int",
            "char",
            "float",
            "double",
            "void",
            "short",
            "long",
            "signed",
            "unsigned",
            "unsigned int",
            "unsigned char",
            "unsigned short",
            "unsigned long",
            "unsigned long long",
            "size_t",
            "ptrdiff_t",
            "wchar_t",
            "bool",
            "_Bool",
            "FILE",
        }

    def parse_project(self, source_dir: str) -> list[Symbol]:
        """Parse all C files in a directory and return topologically ordered symbols."""
        # Initialize clang - libclang package handles library path automatically
        index = clang.Index.create()

        # Find all C files
        c_files = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".h") and "lodepng" not in file:
                    c_files.append(os.path.join(root, file))

        # Parse each file
        for file_path in c_files:
            self._parse_file(index, file_path)

        # Return topologically sorted symbols
        return self._topological_sort()

    def _parse_file(self, index: clang.Index, file_path: str):
        """Parse a single C file and extract symbols."""
        try:
            # Parse the translation unit
            tu = index.parse(file_path, args=["-std=c99"])

            # Traverse the AST
            self._traverse_cursor(tu.cursor, file_path)

        except Exception as e:
            print(f"Warning: Failed to parse {file_path}: {e}", file=sys.stderr)

    def _traverse_cursor(self, cursor: clang.Cursor, target_file: str):
        """Recursively traverse AST cursor to find symbols."""
        # Only process nodes from the target file
        if cursor.location.file and cursor.location.file.name != target_file:
            return

        # Extract symbol based on cursor kind
        symbol = None

        if cursor.kind == clang.CursorKind.STRUCT_DECL:  # type: ignore
            symbol = self._extract_struct(cursor, target_file)
        elif cursor.kind == clang.CursorKind.TYPEDEF_DECL:  # type: ignore
            symbol = self._extract_typedef(cursor, target_file)
        elif cursor.kind == clang.CursorKind.FUNCTION_DECL:  # type: ignore
            symbol = self._extract_function(cursor, target_file)
        elif cursor.kind == clang.CursorKind.ENUM_DECL:  # type: ignore
            symbol = self._extract_enum(cursor, target_file)

        if symbol and symbol.name:
            self.symbols[symbol.name] = symbol

        # Recurse into children
        for child in cursor.get_children():
            self._traverse_cursor(child, target_file)

    def _extract_struct(self, cursor: clang.Cursor, file_path: str) -> Symbol | None:
        """Extract struct symbol and its dependencies."""
        if not cursor.spelling:  # Anonymous struct
            return None

        dependencies = set()

        # Analyze struct members
        for child in cursor.get_children():
            if child.kind == clang.CursorKind.FIELD_DECL:  # type: ignore
                type_name = self._get_type_name(child.type)
                if type_name and type_name not in self.built_in_types:
                    dependencies.add(type_name)

        return Symbol(
            name=cursor.spelling,
            kind="struct",
            file_path=file_path,
            line_number=cursor.location.line,
            dependencies=dependencies,
        )

    def _extract_typedef(self, cursor: clang.Cursor, file_path: str) -> Symbol | None:
        """Extract typedef symbol and its dependencies."""
        if not cursor.spelling:
            return None

        dependencies = set()

        # Get the underlying type
        underlying_type = cursor.underlying_typedef_type
        type_name = self._get_type_name(underlying_type)
        if type_name and type_name not in self.built_in_types:
            dependencies.add(type_name)

        return Symbol(
            name=cursor.spelling,
            kind="typedef",
            file_path=file_path,
            line_number=cursor.location.line,
            dependencies=dependencies,
        )

    def _extract_function(self, cursor: clang.Cursor, file_path: str) -> Symbol | None:
        """Extract function symbol and its dependencies."""
        if not cursor.spelling:
            return None

        dependencies = set()

        # Analyze return type
        return_type = cursor.result_type
        type_name = self._get_type_name(return_type)
        if type_name and type_name not in self.built_in_types:
            dependencies.add(type_name)

        # Analyze parameter types
        for child in cursor.get_children():
            if child.kind == clang.CursorKind.PARM_DECL:  # type: ignore
                param_type = child.type
                type_name = self._get_type_name(param_type)
                if type_name and type_name not in self.built_in_types:
                    dependencies.add(type_name)

        return Symbol(
            name=cursor.spelling,
            kind="function",
            file_path=file_path,
            line_number=cursor.location.line,
            dependencies=dependencies,
        )

    def _extract_enum(self, cursor: clang.Cursor, file_path: str) -> Symbol | None:
        """Extract enum symbol."""
        if not cursor.spelling:
            return None

        return Symbol(
            name=cursor.spelling,
            kind="enum",
            file_path=file_path,
            line_number=cursor.location.line,
            dependencies=set(),  # Enums typically don't depend on other types
        )

    def _get_type_name(self, clang_type) -> str | None:
        """Extract the base type name from a clang Type."""
        if not clang_type:
            return None

        # Handle pointer types
        if clang_type.kind == clang.TypeKind.POINTER:  # type: ignore
            return self._get_type_name(clang_type.get_pointee())

        # Handle array types
        if clang_type.kind == clang.TypeKind.CONSTANTARRAY:  # type: ignore
            return self._get_type_name(clang_type.get_array_element_type())

        # Get the type spelling and clean it up
        type_name = clang_type.spelling
        if not type_name:
            return None

        # Remove qualifiers and extract base type
        type_name = (
            type_name.replace("const ", "").replace("struct ", "").replace("enum ", "")
        )
        type_name = type_name.strip("*").strip()

        return type_name if type_name else None

    def _detect_self_cycles(self):
        """Detect and mark self-referential symbols."""
        for symbol_name, symbol in self.symbols.items():
            if symbol_name in symbol.dependencies:
                # Remove self-dependency to avoid trivial cycles
                symbol.dependencies.discard(symbol_name)
                symbol.cycle = True

    def _detect_strongly_connected_components(self) -> list[set[str]]:
        """Use Tarjan's algorithm to find strongly connected components (cycles)."""
        index_counter = [0]
        stack = []
        lowlinks = {}
        index = {}
        on_stack = {}
        result = []

        def strongconnect(node):
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            # Get successors (dependencies)
            for dep in self.symbols[node].dependencies:
                if dep in self.symbols:  # Only consider known symbols
                    if dep not in index:
                        strongconnect(dep)
                        lowlinks[node] = min(lowlinks[node], lowlinks[dep])
                    elif on_stack.get(dep, False):
                        lowlinks[node] = min(lowlinks[node], index[dep])

            # If node is a root node, pop the stack and create an SCC
            if lowlinks[node] == index[node]:
                component = set()
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.add(w)
                    if w == node:
                        break
                result.append(component)

        for node in self.symbols:
            if node not in index:
                strongconnect(node)

        return result

    def _topological_sort(self) -> list[Symbol]:
        """Perform topological sort with improved cycle handling."""
        # First, detect and handle self-cycles
        self._detect_self_cycles()

        # Detect strongly connected components (cycles)
        sccs = self._detect_strongly_connected_components()

        # Mark symbols in cycles (components with more than 1 element)
        for scc in sccs:
            if len(scc) > 1:
                for symbol_name in scc:
                    self.symbols[symbol_name].cycle = True

        # Build adjacency list and in-degree count (excluding self-deps)
        adj_list = defaultdict(list)
        in_degree = defaultdict(int)

        # Initialize all symbols with in-degree 0
        for symbol_name in self.symbols:
            in_degree[symbol_name] = 0

        # Build graph (excluding self-dependencies)
        for symbol_name, symbol in self.symbols.items():
            for dep in symbol.dependencies:
                if dep in self.symbols and dep != symbol_name:
                    adj_list[dep].append(symbol_name)
                    in_degree[symbol_name] += 1

        # Modified Kahn's algorithm with cycle-aware processing
        queue: deque[str] = deque()
        result: list[Symbol] = []

        # Start with nodes that have no dependencies
        for symbol_name, degree in in_degree.items():
            if degree == 0:
                queue.append(symbol_name)

        while queue:
            current = queue.popleft()
            result.append(self.symbols[current])

            # Remove edges from current node
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Handle remaining nodes (those in cycles)
        remaining = set(self.symbols.keys()) - {e.name for e in result}
        if remaining:
            # Sort remaining by SCC size (smaller cycles first) and then by name
            remaining_by_scc = defaultdict(list)
            for scc in sccs:
                if scc & remaining:  # If SCC intersects with remaining
                    for symbol_name in scc & remaining:
                        remaining_by_scc[len(scc)].append(symbol_name)

            # Add remaining symbols, smaller cycles first
            for scc_size in sorted(remaining_by_scc.keys()):
                for symbol_name in sorted(remaining_by_scc[scc_size]):
                    if symbol_name in remaining:  # Check if not already added
                        result.append(self.symbols[symbol_name])
                        remaining.discard(symbol_name)

        return result


def main():
    """Main entry point for command line usage."""
    if len(sys.argv) != 2:
        print("Usage: python c_traversal.py <source_directory>")
        sys.exit(1)

    source_dir = sys.argv[1]
    if not os.path.isdir(source_dir):
        print(f"Error: {source_dir} is not a directory")
        sys.exit(1)

    traversal = CTraversal()
    symbols = traversal.parse_project(source_dir)

    print("Topological ordering of C symbols:")
    print("=" * 50)

    for i, symbol in enumerate(symbols, 1):
        deps_str = (
            ", ".join(sorted(symbol.dependencies)) if symbol.dependencies else "none"
        )
        print(
            f"{'*' if symbol.cycle else ' '} "
            f"{i:3d}. {symbol.kind:<8} {symbol.name:<20} "
            f"({Path(symbol.file_path).name}:{symbol.line_number}) "
            f"deps: {deps_str}"
        )


if __name__ == "__main__":
    main()
