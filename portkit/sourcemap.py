#!/usr/bin/env python3

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter_c as tsc
import tree_sitter_rust as tsrust
from pydantic import BaseModel
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from portkit.config import ProjectConfig


class SymbolInfo(BaseModel):
    """Information about all locations where a symbol exists."""
    ffi_path: str | None = None
    rust_src_path: str | None = None
    rust_fuzz_path: str | None = None
    c_header_path: str | None = None
    c_source_path: str | None = None


@dataclass
class Symbol:
    """Unified symbol representation for C and Rust."""

    name: str
    kind: str  # 'function', 'struct', 'enum', 'typedef', 'const', 'static', 'impl'
    language: str  # 'c' | 'rust'
    signature: str

    # Location tracking
    declaration_file: Path | None = None
    declaration_line: int | None = None
    definition_file: Path | None = None
    definition_line: int | None = None

    # Dependencies (computed lazily)
    type_dependencies: set[str] = field(default_factory=set)
    call_dependencies: set[str] = field(default_factory=set)
    transitive_dependencies: set[str] = field(default_factory=set)

    # Analysis metadata
    is_cycle: bool = False
    is_static: bool = False
    line_count: int = 0
    reference_count: int = 0

    # Raw AST nodes for further analysis
    _declaration_node: Any = None
    _definition_node: Any = None

    def __hash__(self):
        return hash((self.name, self.kind, self.language))

    def __eq__(self, other):
        return (
            isinstance(other, Symbol)
            and self.name == other.name
            and self.kind == other.kind
            and self.language == other.language
        )

    @property
    def header_path(self) -> Path | None:
        """Get header file path if declaration is in header."""
        if not self.declaration_file:
            return None
        if str(self.declaration_file).endswith(".h"):
            return self.declaration_file
        return None

    @property
    def source_path(self) -> Path | None:
        """Get source file path if definition exists."""
        return self.definition_file

    @property
    def all_dependencies(self) -> set[str]:
        """Get all dependencies (type + call + transitive)."""
        return (
            self.type_dependencies
            | self.call_dependencies
            | self.transitive_dependencies
        )

    @property
    def dependencies(self) -> set[str]:
        """Backwards compatibility alias for all_dependencies."""
        return self.all_dependencies

    @property
    def file_path(self) -> Path | None:
        """Backwards compatibility alias for source file path."""
        return self.definition_file or self.declaration_file

    @property
    def line_number(self) -> int | None:
        """Backwards compatibility alias for line number."""
        return self.definition_line or self.declaration_line

    def merge_with(self, other: "Symbol") -> None:
        """Merge another symbol's information into this one."""
        if self.name != other.name or self.language != other.language:
            return

        # Allow merging function and ffi_function
        if not (self.kind == other.kind or 
                (self.kind == "function" and other.kind == "ffi_function") or
                (self.kind == "ffi_function" and other.kind == "function")):
            return

        if self is other:
            return

        # Prefer "function" over "ffi_function" when merging
        if self.kind == "ffi_function" and other.kind == "function":
            self.kind = "function"

        # Merge locations
        if other.declaration_file and not self.declaration_file:
            self.declaration_file = other.declaration_file
            self.declaration_line = other.declaration_line
            self._declaration_node = other._declaration_node
        if other.definition_file and not self.definition_file:
            self.definition_file = other.definition_file
            self.definition_line = other.definition_line
            self._definition_node = other._definition_node

        # Merge dependencies
        self.type_dependencies.update(other.type_dependencies)
        self.call_dependencies.update(other.call_dependencies)
        self.transitive_dependencies.update(other.transitive_dependencies)

        # Merge metadata
        self.is_static = self.is_static or other.is_static
        self.line_count = max(self.line_count, other.line_count)
        self.reference_count += other.reference_count


class SourceMap:
    """Unified source map for C and Rust symbols with dependency analysis."""

    def __init__(self, project_root: Path, config: "ProjectConfig"):
        assert project_root.exists(), f"Project root {project_root} does not exist"
        assert (
            project_root.is_absolute()
        ), f"Project root {project_root} is not absolute"
        self.project_root = project_root
        self.config = config
        self.c_language = Language(tsc.language())
        self.rust_language = Language(tsrust.language())
        self.c_parser = Parser(self.c_language)
        self.rust_parser = Parser(self.rust_language)

        # Core symbol storage (using composite key to allow same name in different languages)
        self.symbols: dict[tuple[str, str], Symbol] = {}  # (name, language) -> Symbol
        self.symbols_by_name: dict[str, list[Symbol]] = {}  # name -> list of symbols
        self.call_graph: dict[str, set[str]] = {}

        # Built-in types to ignore
        self.built_in_types = {
            "assert",
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
            "u8",
            "u16",
            "u32",
            "u64",
            "usize",
            "i8",
            "i16",
            "i32",
            "i64",
            "isize",
            "f32",
            "f64",
            "String",
            "str",
            "Vec",
            "Option",
            "Result",
        }

        # Parse all files immediately at initialization
        self._parse_all_files()
        self._resolve_transitive_dependencies()

    def parse_project(self) -> list[Symbol]:
        """Return topologically ordered symbols (parsing is done at init)."""
        return self._topological_sort()

    def _parse_all_files(self):
        """Find and parse all relevant source files."""
        for file_path in self.project_root.rglob("*"):
            if file_path.is_file():
                if file_path.suffix in [".c", ".h"]:
                    if "png" not in str(file_path):
                        self._parse_c_file(file_path)
                elif file_path.suffix == ".rs":
                    self._parse_rust_file(file_path)

    def _parse_c_file(self, file_path: Path):
        """Parse a C file and extract symbols."""
        try:
            code = file_path.read_bytes()
            tree = self.c_parser.parse(code)

            self._traverse_c_node(tree.root_node, file_path, code)

        except Exception as e:
            print(f"Warning: Failed to parse C file {file_path}: {e}")

    def _parse_rust_file(self, file_path: Path):
        """Parse a Rust file and extract symbols."""
        try:
            code = file_path.read_bytes()
            tree = self.rust_parser.parse(code)

            self._traverse_rust_node(tree.root_node, file_path, code)

        except Exception as e:
            print(f"Warning: Failed to parse Rust file {file_path}: {e}")

    def _traverse_c_node(self, node: Node, file_path: Path, code: bytes):
        """Traverse C AST and extract symbols."""
        if node.type == "function_definition":
            symbol = self._extract_c_function(node, file_path, code, is_definition=True)
            if symbol:
                self._add_or_merge_symbol(symbol)
                # Extract call dependencies for function bodies
                calls = self._find_c_function_calls(node, code)
                self.call_graph[symbol.name] = calls

        elif node.type == "declaration":
            # Check if it's a function declaration
            for child in node.children:
                if child.type == "function_declarator":
                    symbol = self._extract_c_function(node, file_path, code, is_definition=False)
                    if symbol:
                        self._add_or_merge_symbol(symbol)
                    break

        elif node.type == "struct_specifier":
            symbol = self._extract_c_struct(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "enum_specifier":
            symbol = self._extract_c_enum(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "type_definition":
            symbol = self._extract_c_typedef(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        # Recurse to children
        for child in node.children:
            self._traverse_c_node(child, file_path, code)

    def _traverse_rust_node(self, node: Node, file_path: Path, code: bytes):
        """Traverse Rust AST and extract symbols."""
        if node.type == "function_item":
            symbol = self._extract_rust_function(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)
                # Extract call dependencies
                calls = self._find_rust_function_calls(node, code)
                self.call_graph[symbol.name] = calls

        elif node.type == "struct_item":
            symbol = self._extract_rust_struct(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "enum_item":
            symbol = self._extract_rust_enum(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        # elif node.type == "const_item":
        #     symbol = self._extract_rust_const(node, file_path, code)
        #     if symbol:
        #         self._add_or_merge_symbol(symbol)

        elif node.type == "static_item":
            symbol = self._extract_rust_static(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "type_item":
            symbol = self._extract_rust_type_alias(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "impl_item":
            symbol = self._extract_rust_impl(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "function_signature_item":
            symbol = self._extract_rust_ffi_function(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        # Recurse to children
        for child in node.children:
            self._traverse_rust_node(child, file_path, code)

    def _extract_c_function(self, node: Node, file_path: Path, code: bytes, is_definition: bool) -> Symbol | None:
        """Extract C function symbol."""
        name_node = self._find_function_name_node(node)
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from parameters and return type
        type_deps = self._extract_c_function_type_dependencies(node, code)

        # Calculate line count for definitions
        line_count = 0
        if is_definition:
            line_count = node.end_point[0] - node.start_point[0] + 1

        # Check if static
        is_static = self._is_c_function_static(node, code)

        return self._create_symbol(
            name=name,
            kind="function",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=is_definition,
            type_deps=type_deps,
            line_count=line_count,
            is_static=is_static,
            ast_node=node,
        )

    def _extract_c_struct(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C struct symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from struct fields
        type_deps = self._extract_c_struct_type_dependencies(node, code)

        is_definition = file_path.suffix != ".h"
        return self._create_symbol(
            name=name,
            kind="struct",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=is_definition,
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_c_enum(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C enum symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        is_definition = file_path.suffix != ".h"
        return self._create_symbol(
            name=name,
            kind="enum",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=is_definition,
            ast_node=node,
        )

    def _extract_c_typedef(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C typedef symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from the typedef
        type_deps = self._extract_c_typedef_type_dependencies(node, code)

        return self._create_symbol(
            name=name,
            kind="typedef",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=False,
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_rust_function(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust function symbol."""
        name_node = self._find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1
        line_count = node.end_point[0] - node.start_point[0] + 1

        # Extract type dependencies
        type_deps = self._extract_rust_function_type_dependencies(node, code)

        return self._create_symbol(
            name=name,
            kind="function",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            type_deps=type_deps,
            line_count=line_count,
            ast_node=node,
        )

    def _extract_rust_struct(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust struct symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from struct fields
        type_deps = self._extract_rust_struct_type_dependencies(node, code)

        return self._create_symbol(
            name=name,
            kind="struct",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_rust_enum(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust enum symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from enum variants
        type_deps = self._extract_rust_enum_type_dependencies(node, code)

        return self._create_symbol(
            name=name,
            kind="enum",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_rust_const(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust const symbol."""
        name_node = self._find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="const",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_rust_static(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust static symbol."""
        name_node = self._find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="static",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_rust_type_alias(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust type alias symbol."""
        name_node = self._find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="type",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_rust_impl(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust impl block symbol."""
        type_node = self._find_node_by_type(node, "type_identifier")
        if not type_node:
            return None

        type_name = type_node.text.decode()
        name = f"impl_{type_name}"
        signature = self._extract_signature(code, node)
        line_num = type_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="impl",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_rust_ffi_function(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust FFI function symbol."""
        name_node = self._find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = name_node.text.decode()
        signature = self._extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="ffi_function",
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=False,
            ast_node=node,
        )

    def _create_symbol(
        self,
        name: str,
        kind: str,
        language: str,
        signature: str,
        file_path: Path,
        line_num: int,
        is_definition: bool = True,
        type_deps: set[str] = None,
        line_count: int = 0,
        is_static: bool = False,
        ast_node: Node = None,
    ) -> Symbol:
        """Helper method to create symbols with relative paths."""
        relative_path = file_path.relative_to(self.project_root)

        symbol = Symbol(
            name=name,
            kind=kind,
            language=language,
            signature=signature,
            type_dependencies=type_deps or set(),
            line_count=line_count,
            is_static=is_static,
        )

        if is_definition:
            symbol.definition_file = relative_path
            symbol.definition_line = line_num
            symbol._definition_node = ast_node
        else:
            symbol.declaration_file = relative_path
            symbol.declaration_line = line_num
            symbol._declaration_node = ast_node

        return symbol

    def _add_or_merge_symbol(self, symbol: Symbol):
        """Add symbol or merge with existing one."""
        key = (symbol.name, symbol.language)
        existing = self.symbols.get(key)
        if existing is None:
            self.symbols[key] = symbol
            # Also add to by-name index
            if symbol.name not in self.symbols_by_name:
                self.symbols_by_name[symbol.name] = []
            self.symbols_by_name[symbol.name].append(symbol)
        else:
            existing.merge_with(symbol)

    def _find_function_name_node(self, node: Node) -> Node | None:
        """Find the function name identifier node."""
        def find_identifier(n: Node) -> Node | None:
            if n.type == "identifier":
                return n
            for child in n.children:
                result = find_identifier(child)
                if result:
                    return result
            return None

        # Look for function_declarator first
        for child in node.children:
            if child.type == "function_declarator":
                return find_identifier(child)

        return find_identifier(node)

    def _find_node_by_type(self, node: Node, node_type: str) -> Node | None:
        """Find first child node of given type."""
        if node.type == node_type:
            return node
        for child in node.children:
            result = self._find_node_by_type(child, node_type)
            if result:
                return result
        return None

    def _extract_signature(self, code: bytes, node: Node) -> str:
        """Extract a clean signature from a node."""
        node_text = node.text.decode()

        # Remove comments
        node_text = re.sub(r"/\*.*?\*/", "", node_text, flags=re.DOTALL)
        node_text = re.sub(r"//.*$", "", node_text, flags=re.MULTILINE)

        # Clean up whitespace
        lines = [line.strip() for line in node_text.split("\n") if line.strip()]

        # For functions, extract just the declaration part
        if node.type in ["function_definition", "declaration", "function_item", "function_signature_item"]:
            signature_lines = []
            for line in lines:
                signature_lines.append(line)
                if "{" in line:
                    line = line[:line.index("{")].strip()
                    if line:
                        signature_lines[-1] = line
                    break
            return " ".join(signature_lines)

        # For other types, limit to reasonable size
        if len(lines) > 4:
            return "\n".join(lines[:3] + ["..."])
        else:
            return "\n".join(lines)

    def _extract_c_function_type_dependencies(
        self, node: Node, _code: bytes
    ) -> set[str]:
        """Extract type dependencies from C function parameters and return type."""
        deps = set()

        def extract_type_names(n: Node):
            if n.type == "type_identifier":
                type_name = n.text.decode()
                if type_name not in self.built_in_types:
                    deps.add(type_name)
            for child in n.children:
                extract_type_names(child)

        extract_type_names(node)
        return deps

    def _extract_c_struct_type_dependencies(self, node: Node, code: bytes) -> set[str]:
        """Extract type dependencies from C struct fields."""
        deps = set()

        def extract_field_types(n: Node):
            if n.type == "field_declaration":
                for child in n.children:
                    if child.type == "type_identifier":
                        type_name = child.text.decode()
                        if type_name not in self.built_in_types:
                            deps.add(type_name)
            for child in n.children:
                extract_field_types(child)

        extract_field_types(node)
        return deps

    def _extract_c_typedef_type_dependencies(self, node: Node, code: bytes) -> set[str]:
        """Extract type dependencies from C typedef."""
        deps = set()

        def extract_typedef_types(n: Node):
            if n.type == "type_identifier" and n != node.children[-1]:  # Don't include the typedef name itself
                type_name = n.text.decode()
                if type_name not in self.built_in_types:
                    deps.add(type_name)
            for child in n.children:
                extract_typedef_types(child)

        extract_typedef_types(node)
        return deps

    def _extract_rust_function_type_dependencies(self, node: Node, code: bytes) -> set[str]:
        """Extract type dependencies from Rust function."""
        deps = set()

        def extract_type_names(n: Node):
            if n.type == "type_identifier":
                type_name = n.text.decode()
                if type_name not in self.built_in_types:
                    deps.add(type_name)
            for child in n.children:
                extract_type_names(child)

        extract_type_names(node)
        return deps

    def _extract_rust_struct_type_dependencies(self, node: Node, code: bytes) -> set[str]:
        """Extract type dependencies from Rust struct fields."""
        deps = set()

        def extract_field_types(n: Node):
            if n.type == "field_declaration":
                for child in n.children:
                    if child.type == "type_identifier":
                        type_name = child.text.decode()
                        if type_name not in self.built_in_types:
                            deps.add(type_name)
            for child in n.children:
                extract_field_types(child)

        extract_field_types(node)
        return deps

    def _extract_rust_enum_type_dependencies(self, node: Node, code: bytes) -> set[str]:
        """Extract type dependencies from Rust enum variants."""
        deps = set()

        def extract_variant_types(n: Node):
            if n.type == "enum_variant":
                for child in n.children:
                    if child.type == "type_identifier":
                        type_name = child.text.decode()
                        if type_name not in self.built_in_types:
                            deps.add(type_name)
            for child in n.children:
                extract_variant_types(child)

        extract_variant_types(node)
        return deps

    def _is_c_function_static(self, node: Node, code: bytes) -> bool:
        """Check if C function is static."""
        node_text = node.text.decode()
        return "static" in node_text.split()[0:3]  # Check first few tokens

    def _find_c_function_calls(self, node: Node, code: bytes) -> set[str]:
        """Find all function calls within a C function."""
        calls = set()

        def find_calls(n: Node):
            if n.type == "call_expression":
                # Get the function name from the call
                for child in n.children:
                    if child.type == "identifier":
                        calls.add(child.text.decode())
                        break
            for child in n.children:
                find_calls(child)

        find_calls(node)
        return calls

    def _find_rust_function_calls(self, node: Node, code: bytes) -> set[str]:
        """Find all function calls within a Rust function."""
        calls = set()

        def find_calls(n: Node):
            if n.type == "call_expression":
                # Get the function name from the call
                for child in n.children:
                    if child.type == "identifier":
                        calls.add(child.text.decode())
                        break
                    elif child.type == "field_expression":
                        # Handle method calls
                        for grandchild in child.children:
                            if grandchild.type == "field_identifier":
                                calls.add(grandchild.text.decode())
                                break
            for child in n.children:
                find_calls(child)

        find_calls(node)
        return calls

    def _resolve_transitive_dependencies(self):
        """Resolve transitive dependencies by combining type deps and call graph."""
        for (symbol_name, _), symbol in self.symbols.items():
            all_deps = set(symbol.type_dependencies)

            # Add function call dependencies if this is a function
            if symbol.kind == "function" and symbol_name in self.call_graph:
                all_deps.update(self.call_graph[symbol_name])

            # Compute transitive closure
            visited = set()
            to_visit = list(all_deps)

            while to_visit:
                dep = to_visit.pop()
                if dep in visited:
                    continue
                visited.add(dep)
                all_deps.add(dep)

                # Add dependencies of this dependency
                if dep in self.symbols_by_name:
                    for dep_symbol in self.symbols_by_name[dep]:
                        for sub_dep in dep_symbol.type_dependencies:
                            if sub_dep not in visited:
                                to_visit.append(sub_dep)

                # Add function calls of this dependency
                if dep in self.call_graph:
                    for sub_dep in self.call_graph[dep]:
                        if sub_dep not in visited:
                            to_visit.append(sub_dep)

            # Update transitive dependencies
            symbol.transitive_dependencies = all_deps - symbol.type_dependencies - symbol.call_dependencies

    def _detect_strongly_connected_components(self) -> list[set[str]]:
        """Use Tarjan's algorithm to find strongly connected components."""
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
            # Get node symbol (try rust first, then c)
            node_symbol = None
            for (name, language), s in self.symbols.items():
                if name == node:
                    if node_symbol is None or language == "rust":
                        node_symbol = s

            for dep in node_symbol.all_dependencies if node_symbol else []:
                if dep in self.symbols_by_name:
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

        for node in self.symbols_by_name:
            if node not in index:
                strongconnect(node)

        return result

    def _detect_strongly_connected_components_for_c_symbols(
        self, c_symbols: dict, c_symbols_by_name: dict
    ) -> list[set[str]]:
        """Use Tarjan's algorithm to find strongly connected components for C symbols only."""
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

            # Get successors (dependencies) - only for C symbols
            node_symbol = None
            for (name, _), s in c_symbols.items():
                if name == node:
                    node_symbol = s
                    break

            for dep in node_symbol.all_dependencies if node_symbol else []:
                if dep in c_symbols_by_name:
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

        for node in c_symbols_by_name:
            if node not in index:
                strongconnect(node)

        return result

    def _topological_sort(self) -> list[Symbol]:
        """Perform topological sort with cycle handling, focusing only on C symbols."""
        # Filter to only include C symbols (functions, structs, enums)
        c_symbols = {}
        c_symbols_by_name = {}

        for (symbol_name, language), symbol in self.symbols.items():
            if (
                language == "c"
                and symbol.kind in ["function", "struct", "enum"]
                and not symbol.is_static
            ):
                c_symbols[(symbol_name, language)] = symbol
                if symbol_name not in c_symbols_by_name:
                    c_symbols_by_name[symbol_name] = []
                c_symbols_by_name[symbol_name].append(symbol)

        # Detect strongly connected components (cycles) - only for C symbols
        sccs = self._detect_strongly_connected_components_for_c_symbols(
            c_symbols, c_symbols_by_name
        )

        # Mark symbols in cycles
        for scc in sccs:
            if len(scc) > 1:
                for symbol_name in scc:
                    if symbol_name in c_symbols_by_name:
                        for s in c_symbols_by_name[symbol_name]:
                            s.is_cycle = True

        # Build adjacency list and in-degree count - only for C symbols
        adj_list = defaultdict(list)
        in_degree = defaultdict(int)

        # Initialize all C symbols with in-degree 0
        for symbol_name in c_symbols_by_name:
            in_degree[symbol_name] = 0

        # Build graph - only consider dependencies between C symbols
        for (symbol_name, _), symbol in c_symbols.items():
            for dep in symbol.all_dependencies:
                if dep in c_symbols_by_name and dep != symbol_name:
                    adj_list[dep].append(symbol_name)
                    in_degree[symbol_name] += 1

        # Kahn's algorithm with cycle-aware processing
        queue: deque[str] = deque()
        result: list[Symbol] = []

        # Start with nodes that have no dependencies
        for symbol_name, degree in in_degree.items():
            if degree == 0:
                queue.append(symbol_name)

        while queue:
            current = queue.popleft()
            # Get the C symbol
            current_symbol = None
            for (name, _), s in c_symbols.items():
                if name == current:
                    current_symbol = s
                    break
            if current_symbol:
                result.append(current_symbol)

            # Remove edges from current node
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Handle remaining nodes (those in cycles)
        remaining = set(key[0] for key in c_symbols.keys()) - {s.name for s in result}
        if remaining:
            # Add remaining symbols sorted by name
            for symbol_name in sorted(remaining):
                # Get the first symbol with this name
                for (name, _), symbol in c_symbols.items():
                    if name == symbol_name:
                        result.append(symbol)
                        break

        return result

    def get_symbol_source_code(self, symbol_name: str) -> str:
        """Get the source code for a symbol."""
        # Get the first symbol with this name (prefer rust over c)
        symbol = None
        for (name, language), s in self.symbols.items():
            if name == symbol_name:
                if symbol is None or language == "rust":
                    symbol = s
        if not symbol:
            return ""

        # Use definition file if available, otherwise declaration file
        rel_file_path = symbol.definition_file or symbol.declaration_file
        if not rel_file_path:
            return ""

        # Convert relative path to absolute path
        file_path = self.project_root / rel_file_path
        if not file_path.exists():
            return ""

        if symbol.language == "c":
            return self._get_c_symbol_source_code(symbol, file_path)
        else:
            return self._get_rust_symbol_source_code(symbol, file_path)

    def _get_c_symbol_source_code(self, symbol: Symbol, file_path: Path) -> str:
        """Get C symbol source code using tree-sitter."""
        node = symbol._definition_node or symbol._declaration_node
        if not node:
            return ""

        try:
            code = file_path.read_bytes()
            return self._get_node_context(code, node)
        except Exception:
            return ""

    def _get_rust_symbol_source_code(self, symbol: Symbol, file_path: Path) -> str:
        """Get Rust symbol source code using tree-sitter."""
        node = symbol._definition_node or symbol._declaration_node
        if not node:
            return ""

        try:
            code = file_path.read_bytes()
            return self._get_node_context(code, node)
        except Exception:
            return ""

    def _get_node_context(self, code: bytes, node: Node) -> str:
        """Extract context around a tree-sitter node."""
        lines = code.decode().split("\n")
        start_line = node.start_point[0]
        end_line = node.end_point[0]

        # Add some context lines around the definition
        context_start = max(0, start_line - 2)
        context_end = min(len(lines), end_line + 3)

        return "\n".join(lines[context_start:context_end])

    def lookup_symbol(self, symbol_name: str) -> SymbolInfo:
        """Find all locations of a symbol and return SymbolInfo with all paths."""
        # Look for all symbols with this name (may have multiple with different languages)
        matching_symbols = self.symbols_by_name.get(symbol_name, [])

        info = SymbolInfo()

        if matching_symbols:
            # Process all matching symbols
            for symbol in matching_symbols:
                # Check for FFI binding (if this is the declaration in ffi.rs)
                if symbol.declaration_file and str(symbol.declaration_file).endswith('ffi.rs'):
                    info.ffi_path = str(symbol.declaration_file)

                # Check for Rust implementation
                if symbol.definition_file and str(symbol.definition_file).endswith('.rs') and 'ffi.rs' not in str(symbol.definition_file):
                    info.rust_src_path = str(symbol.definition_file)
                elif symbol.declaration_file and str(symbol.declaration_file).endswith('.rs') and 'ffi.rs' not in str(symbol.declaration_file):
                    info.rust_src_path = str(symbol.declaration_file)

                # Check for C header (could be declaration or definition in .h file)
                if symbol.declaration_file and str(symbol.declaration_file).endswith('.h'):
                    info.c_header_path = str(symbol.declaration_file)
                elif symbol.definition_file and str(symbol.definition_file).endswith('.h'):
                    info.c_header_path = str(symbol.definition_file)

                # Check for C source
                if symbol.definition_file and str(symbol.definition_file).endswith('.c'):
                    info.c_source_path = str(symbol.definition_file)

        # Check for FFI binding manually if not found in symbols
        if not info.ffi_path:
            ffi_path = self.config.rust_ffi_path()
            if ffi_path.exists() and self.find_ffi_binding_definition(
                ffi_path, symbol_name
            ):
                info.ffi_path = str(ffi_path.relative_to(self.project_root))

        # Check for fuzz test
        fuzz_path = self.config.rust_fuzz_path_for_symbol(symbol_name)
        if fuzz_path.exists():
            info.rust_fuzz_path = str(fuzz_path.relative_to(self.project_root))

        return info

    def get_topo_ordered_dependencies(self, symbol_name: str) -> list[str]:
        """Get topologically ordered dependencies for a symbol."""
        if symbol_name not in self.symbols_by_name:
            return []

        symbol = None
        for s in self.symbols_by_name[symbol_name]:
            if symbol is None or s.language == "c":
                symbol = s
        deps = symbol.all_dependencies

        # Filter to only include dependencies that exist in our symbol map
        valid_deps = {dep for dep in deps if dep in self.symbols_by_name}

        # Create subgraph for dependencies
        subgraph_symbols = {}
        for name in valid_deps:
            # Get the first symbol with this name
            for s in self.symbols_by_name[name]:
                subgraph_symbols[name] = s
                break

        # Perform topological sort on subgraph
        if not subgraph_symbols:
            return []

        # Build adjacency list for dependencies only
        adj_list = defaultdict(list)
        in_degree = defaultdict(int)

        for dep_name in valid_deps:
            in_degree[dep_name] = 0

        for dep_name in valid_deps:
            dep_symbol = subgraph_symbols[dep_name]
            for sub_dep in dep_symbol.all_dependencies:
                if sub_dep in valid_deps and sub_dep != dep_name:
                    adj_list[sub_dep].append(dep_name)
                    in_degree[dep_name] += 1

        # Kahn's algorithm
        queue: deque[str] = deque()
        result: list[str] = []

        for dep_name, degree in in_degree.items():
            if degree == 0:
                queue.append(dep_name)

        while queue:
            current = queue.popleft()
            result.append(current)

            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Handle any remaining (cyclic dependencies)
        remaining = valid_deps - set(result)
        result.extend(sorted(remaining))

        return result

    def generate_repomap(self) -> str:
        """Generate Aider-style repository map summary."""
        lines = []
        lines.append("# Repository Map")
        lines.append("")

        # Group symbols by file
        files_map = defaultdict(list)
        for symbol in [s for symbols_list in self.symbols_by_name.values() for s in symbols_list]:
            file_path = symbol.definition_file or symbol.declaration_file
            if file_path:
                # file_path is already relative to project_root
                files_map[file_path].append(symbol)

        # Sort files by path
        for file_path in sorted(files_map.keys()):
            symbols = files_map[file_path]
            lines.append(f"## {file_path}")
            lines.append("")

            # Group by symbol type
            by_kind = defaultdict(list)
            for symbol in symbols:
                by_kind[symbol.kind].append(symbol)

            # Show each kind
            for kind in sorted(by_kind.keys()):
                kind_symbols = sorted(by_kind[kind], key=lambda s: s.name)
                lines.append(f"### {kind.title()}s")

                for symbol in kind_symbols:
                    line_info = ""
                    if symbol.definition_line:
                        line_info = f":{symbol.definition_line}"
                    elif symbol.declaration_line:
                        line_info = f":{symbol.declaration_line}"

                    deps_info = ""
                    if symbol.all_dependencies:
                        dep_count = len(symbol.all_dependencies)
                        deps_info = f" ({dep_count} deps)"

                    cycle_info = " [CYCLE]" if symbol.is_cycle else ""
                    static_info = " [STATIC]" if symbol.is_static else ""

                    lines.append(f"- **{symbol.name}**{line_info}{deps_info}{cycle_info}{static_info}")

                    # Show signature for smaller items
                    if len(symbol.signature) < 100:
                        lines.append(f"  ```{symbol.language}")
                        lines.append(f"  {symbol.signature}")
                        lines.append("  ```")

                lines.append("")

        return "\n".join(lines)

    def get_topological_order(self) -> list[Symbol]:
        return self.parse_project()

    def generate_repo_map(self) -> str:
        return self.generate_repomap()

    def get_symbol(self, symbol_name: str) -> Symbol:
        """Get a symbol by name.

        Args:
            symbol_name: The name of the symbol to retrieve

        Returns:
            Symbol: The symbol object

        Raises:
            ValueError: If the symbol is not found
        """
        if symbol_name not in self.symbols_by_name:
            # Try to parse the project if we haven't already
            if not self.symbols:
                self.parse_project()

            # Check again after parsing
            if symbol_name not in self.symbols_by_name:
                raise ValueError(f"Symbol '{symbol_name}' not found in project")

        # Return the first symbol with this name (could be C or Rust)
        # In most cases there will only be one, but if there are multiple
        # (e.g., C and Rust versions), prefer the C version for compatibility
        symbols = self.symbols_by_name[symbol_name]
        c_symbols = [s for s in symbols if s.language == "c"]
        if c_symbols:
            return c_symbols[0]
        return symbols[0]

    def find_c_symbol_definition(self, file_path: Path, symbol_name: str) -> str:
        """Find C symbol definition using parsed symbol data."""
        try:
            symbol = self.get_symbol(symbol_name)

            # Check if this symbol has a definition or declaration in the specified file
            target_node = None
            if (
                symbol.definition_file
                and symbol.definition_file.name == file_path.name
                and symbol.language == "c"
                and symbol._definition_node
            ):
                target_node = symbol._definition_node
            elif (
                symbol.declaration_file
                and symbol.declaration_file.name == file_path.name
                and symbol.language == "c"
                and symbol._declaration_node
            ):
                target_node = symbol._declaration_node

            if target_node:
                # Extract the full source code from the AST node
                try:
                    code = file_path.read_bytes()
                    return self._extract_signature(code, target_node)
                except Exception:
                    # Fall back to signature if we can't extract from file
                    return symbol.signature

        except ValueError:
            # Symbol not found in parsed data
            pass

        return ""

    def find_ffi_binding_definition(self, file_path: Path, symbol_name: str) -> str:
        """Find FFI binding definition using parsed symbol data."""
        # Look for a Rust symbol with ffi_function kind or declared in ffi.rs
        if symbol_name in self.symbols_by_name:
            for symbol in self.symbols_by_name[symbol_name]:
                if (
                    symbol.language == "rust"
                    and (
                        symbol.kind == "ffi_function"
                        or (
                            symbol.declaration_file
                            and "ffi.rs" in str(symbol.declaration_file)
                        )
                    )
                    and symbol.declaration_file
                    and symbol.declaration_file.name == file_path.name
                ):
                    # Try to extract full source from AST node
                    if symbol._declaration_node:
                        try:
                            code = file_path.read_bytes()
                            return self._extract_signature(code, symbol._declaration_node)
                        except Exception:
                            pass

                    return symbol.signature

        return ""

    def find_rust_symbol_definition(self, file_path: Path, symbol_name: str) -> str:
        """Find Rust symbol definition using parsed symbol data."""
        if symbol_name in self.symbols_by_name:
            for symbol in self.symbols_by_name[symbol_name]:
                if (
                    symbol.language == "rust"
                    and symbol.definition_file
                    and symbol.definition_file.name == file_path.name
                    and symbol._definition_node
                ):
                    # Try to extract full source from AST node
                    try:
                        code = file_path.read_bytes()
                        return self._extract_signature(code, symbol._definition_node)
                    except Exception:
                        pass

                    return symbol.signature

        return ""

    def is_symbol_defined(self, file_path: Path, symbol_name: str) -> bool:
        """Check if a symbol is defined (not just a stub) in a Rust file."""
        if symbol_name in self.symbols_by_name:
            for symbol in self.symbols_by_name[symbol_name]:
                if (
                    symbol.language == "rust"
                    and symbol.definition_file
                    and symbol.definition_file.name == file_path.name
                    and symbol._definition_node
                ):
                    # Check if it's just an unimplemented stub
                    return "unimplemented!()" not in symbol.signature

        return False

    def is_fuzz_test_defined(self, file_path: Path, symbol_name: str) -> bool:
        """Check if a fuzz test is defined for a symbol."""
        if not file_path.exists():
            return False

        content = file_path.read_text()

        # Look for the symbol name in the fuzz test
        return symbol_name in content and "fuzz_target!" in content


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python sourcemap.py <src_directory>")
        sys.exit(1)

    src_dir = Path(sys.argv[1])
    if not src_dir.exists():
        print(f"Error: Directory {src_dir} does not exist")
        sys.exit(1)

    # Find project root (parent of src directory)
    project_root = src_dir

    print(f"Analyzing C project at: {project_root}")
    print(f"Source directory: {src_dir}")
    print()

    # Create source map and parse project
    # For CLI usage, create a minimal config
    from portkit.config import ProjectConfig
    config = ProjectConfig(project_name="temp", library_name="temp")
    source_map = SourceMap(project_root, config)
    symbols = source_map.parse_project()

    print(f"Found {len(symbols)} C symbols (functions, structs, enums):")
    print()

    # Display symbols in topological order
    for i, symbol in enumerate(symbols, 1):
        cycle_marker = " [CYCLE]" if symbol.is_cycle else ""
        deps_info = (
            f" ({len(symbol.all_dependencies)} deps)" if symbol.all_dependencies else ""
        )
        line_info = f":{symbol.line_number}" if symbol.line_number else ""

        print(
            f"{i:3d}. {symbol.kind:<8} {symbol.name:<30}{line_info:<8}{deps_info}{cycle_marker}"
        )

        # Show file location
        if symbol.definition_file:
            print(f"     Definition: {symbol.definition_file}")
        elif symbol.declaration_file:
            print(f"     Declaration: {symbol.declaration_file}")

        # Show dependencies if any
        if symbol.all_dependencies:
            deps = sorted(symbol.all_dependencies)
            if len(deps) <= 5:
                print(f"     Dependencies: {', '.join(deps)}")
            else:
                print(
                    f"     Dependencies: {', '.join(deps[:5])}, ... ({len(deps)} total)"
                )

        print()
