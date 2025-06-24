#!/usr/bin/env python3

# type: ignore[missing-attribute]

import csv
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter_c as tsc
import tree_sitter_rust as tsrust
from pydantic import BaseModel
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from portkit.config import ProjectConfig


# Helper to avoid type-checking warnings.
def _node_text(node: Node) -> str:
    assert node.text is not None
    return node.text.decode().strip()


def detect_strongly_connected_components(
    symbols_by_name: dict, get_dependencies_fn
) -> list[set[str]]:
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

        for dep in get_dependencies_fn(node):
            if dep in symbols_by_name:
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

    for node in symbols_by_name:
        if node not in index:
            strongconnect(node)

    return result


# Constants for header guard detection
COMMON_IGNORE_PATTERNS = {
    # Version checks
    "_MSC_VER",
    "_WIN32",
    "_WIN64",
    "__GNUC__",
    "__clang__",
    # Feature test macros
    "_GNU_SOURCE",
    "_POSIX_C_SOURCE",
    "_XOPEN_SOURCE",
    # Compiler attributes
    "__STDC__",
    "__STDC_VERSION__",
    "__cplusplus",
    # Library-specific version macros (common pattern)
    "LIBXML_VERSION",
    "LIBXML_DOTTED_VERSION",
    "LIBXML_VERSION_STRING",
}

IGNORE_SUFFIXES = (
    "_H",
    "_H_",
    "_H__",
    "_HPP",
    "_HPP_",
    "_HPP__",  # Header guards
    "_ENABLED",
    "_INCLUDED",
    "_DEFINED",
    "_AVAILABLE",  # Feature flags
    "_VERSION",
    "_MAJOR",
    "_MINOR",
    "_PATCH",
    "_BUILD",  # Version info
)

# Built-in types to ignore during dependency extraction
BUILT_IN_C_TYPES = {
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
}

BUILT_IN_RUST_TYPES = {
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

C_KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "int",
    "long",
    "register",
    "return",
    "va_list",
    "va_start",
    "va_end",
    "sizeof",
    "short",
    "signed",
    "static",
    "struct",
    "switch",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
    "inline",
    "restrict",
}

ALL_BUILT_IN_TYPES = BUILT_IN_C_TYPES | BUILT_IN_RUST_TYPES


def should_skip(name: str, built_in_types: set[str]) -> bool:
    """Check if a symbol name is meaningless or should be filtered out.
    
    Combines logic for filtering built-in types, keywords, and other invalid symbols.
    """
    # Filter out built-in types
    if name in built_in_types:
        return True

    # Filter out built-in C types specifically
    if name in BUILT_IN_C_TYPES:
        return True

    # Filter out C keywords
    if name in C_KEYWORDS:
        return True

    # Filter out very short names (likely noise)
    if len(name) <= 1:
        return True

    # Filter out common macro patterns
    if name.startswith("__") and name.endswith("__"):
        return True

    return False


def is_empty_define(node: Node) -> bool:
    """Check if this #define has no value (empty/flag define) using tree-sitter."""
    # For a preproc_def node, check the children
    # Structure: #define IDENTIFIER [optional_value]

    children = node.children
    if len(children) < 2:
        return True  # Malformed define

    # First child should be "#define", second should be identifier
    # If there's no third child, it's an empty define
    if len(children) == 2:
        return True

    # If there's a third child, check if it's whitespace or comment only
    if len(children) >= 3:
        value_node = children[2]
        value_text = _node_text(value_node).strip()
        # Check if it's empty, whitespace, or starts with comment
        if not value_text or value_text.startswith("/*") or value_text.startswith("//"):
            return True

    return False


def get_c_symbol_source_code(symbol, file_path: Path) -> str:
    """Get C symbol source code using tree-sitter."""
    node = symbol._definition_node or symbol._declaration_node
    if not node:
        return ""

    try:
        code = file_path.read_bytes()
        return get_node_context(code, node)
    except Exception:
        return ""


def get_node_context(code: bytes, node: Node) -> str:
    """Extract context around a tree-sitter node."""
    lines = code.decode().split("\n")
    start_line = node.start_point[0]
    end_line = node.end_point[0]

    # Add some context lines around the definition
    context_start = max(0, start_line - 2)
    context_end = min(len(lines), end_line + 3)

    return "\n".join(lines[context_start:context_end])


def create_simple_symbol(
    name: str,
    kind: str,
    language: str,
    signature: str,
    file_path: Path,
    line_num: int,
    project_root: Path,
    is_definition: bool = True,
    type_deps: set[str] = None,
    ast_node=None,
) -> "Symbol":
    """Helper to create simple symbols with relative paths."""
    relative_path = file_path.relative_to(project_root)

    symbol = Symbol(
        name=name,
        kind=kind,
        language=language,
        signature=signature,
        type_dependencies=type_deps or set(),
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


def extract_simple_c_symbol_info(
    node: Node,
    code: bytes,
    kind: str,
    file_path: Path,
    project_root: Path,
    built_in_types: set[str],
) -> tuple[str, str, int, bool, set[str]] | None:
    """Extract common info for simple C symbols (struct, enum)."""
    name_node = find_node_by_type(node, "type_identifier")
    if not name_node:
        return None

    name = _node_text(name_node)
    signature = extract_signature(code, node)
    line_num = name_node.start_point[0] + 1
    is_definition = file_path.suffix != ".h"

    # Extract type dependencies if needed
    type_deps = set()
    if kind == "struct":
        type_deps = extract_field_type_dependencies(node, built_in_types, "field_declaration")

    return name, signature, line_num, is_definition, type_deps


def extract_signature(code: bytes, node: Node) -> str:
    """Extract a clean signature from a node."""
    node_text = _node_text(node)

    # Remove comments
    node_text = re.sub(r"/\*.*?\*/", "", node_text, flags=re.DOTALL)
    node_text = re.sub(r"//.*$", "", node_text, flags=re.MULTILINE)

    # Clean up whitespace
    lines = [line.strip() for line in node_text.split("\n") if line.strip()]

    # For functions, extract just the declaration part
    if node.type in [
        "function_definition",
        "declaration",
        "function_item",
        "function_signature_item",
    ]:
        signature_lines = []
        for line in lines:
            signature_lines.append(line)
            if "{" in line:
                line = line[: line.index("{")].strip()
                if line:
                    signature_lines[-1] = line
                break
        return " ".join(signature_lines)

    # For other types, limit to reasonable size
    if len(lines) > 4:
        return "\n".join(lines[:3] + ["..."])
    else:
        return "\n".join(lines)


def find_node_by_type(node: Node, node_type: str) -> Node | None:
    """Find first child node of given type."""
    if node.type == node_type:
        return node
    for child in node.children:
        result = find_node_by_type(child, node_type)
        if result:
            return result
    return None


def find_function_name_node(node: Node) -> Node | None:
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


def extract_generic_type_dependencies(node: Node, built_in_types: set[str]) -> set[str]:
    """Extract type dependencies for functions (C and Rust)."""
    deps = set()

    def extract_type_names(n: Node):
        if n.type == "type_identifier":
            type_name = _node_text(n)
            if not should_skip(type_name, built_in_types):
                deps.add(type_name)
        for child in n.children:
            extract_type_names(child)

    extract_type_names(node)
    return deps


def extract_field_type_dependencies(
    node: Node, built_in_types: set[str], field_node_type: str
) -> set[str]:
    """Extract type dependencies from struct/enum fields."""
    deps = set()

    def extract_field_types(n: Node):
        if n.type == field_node_type:
            for child in n.children:
                if child.type == "type_identifier":
                    type_name = _node_text(child)
                    if not should_skip(type_name, built_in_types):
                        deps.add(type_name)
        for child in n.children:
            extract_field_types(child)

    extract_field_types(node)
    return deps


def is_c_function_static(node: Node) -> bool:
    """Check if C function is static by looking for storage_class_specifier in AST."""

    def find_static(n: Node) -> bool:
        if n.type == "storage_class_specifier" and _node_text(n) == "static":
            return True
        # Only check direct children to avoid finding static in nested scopes
        for child in n.children:
            if (
                child.type == "storage_class_specifier"
                and _node_text(child) == "static"
            ):
                return True
        return False

    return find_static(node)


def extract_typedef_type_dependencies(node: Node, built_in_types: set[str]) -> set[str]:
    """Extract type dependencies from C typedef, excluding the typedef name itself."""
    deps = set()

    def extract_types(n: Node):
        if n.type == "type_identifier" and n != node.children[-1]:
            type_name = _node_text(n)
            if not should_skip(type_name, built_in_types):
                deps.add(type_name)
        for child in n.children:
            extract_types(child)

    extract_types(node)
    return deps


def is_simple_typedef(node: Node) -> bool:
    """Check if this is a simple typedef that should be filtered out.

    Filters:
    - typedef Type *TypePtr  (simple pointer typedef)
    - typedef Type TypeAlias (simple type alias)
    - typedef struct _Name Name (forward declaration without body)
    """
    try:
        node_text = _node_text(node).strip()

        # Skip if this typedef has a struct/enum body (indicated by braces)
        if "{" in node_text and "}" in node_text:
            return False

        # Simple pointer typedef: typedef SomeType *SomeTypePtr
        if "*" in node_text:
            return True

        # Pattern: typedef struct _Name Name (forward declaration)
        if "struct" in node_text and "{" not in node_text:
            return True

        # Find all type identifiers and primitive types
        all_types = []

        def find_types(n: Node):
            if n.type == "type_identifier":
                all_types.append(_node_text(n))
            elif n.type == "primitive_type":
                all_types.append(_node_text(n))
            for child in n.children:
                find_types(child)

        find_types(node)

        # Simple type alias: typedef PrimitiveType TypeAlias or typedef Type Type
        if len(all_types) == 2:
            source_type, target_type = all_types[0], all_types[1]

            # typedef int MyInt - filter out
            if source_type in {"int", "char", "float", "double", "void", "long", "short"}:
                return True

            # typedef SomeType SameType - filter out if essentially the same
            if source_type.lower().replace("_", "") == target_type.lower().replace("_", ""):
                return True

        # typedef Type (single type, malformed) - filter out
        if len(all_types) <= 1:
            return True

    except Exception as e:
        print(f"Error in is_simple_typedef: {e}, node_text: {node_text}")

    return False


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
    _depth: int = 0  # Depth in dependency graph

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
        return self.type_dependencies | self.call_dependencies | self.transitive_dependencies

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
        if not (
            self.kind == other.kind
            or (self.kind == "function" and other.kind == "ffi_function")
            or (self.kind == "ffi_function" and other.kind == "function")
        ):
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


def find_unification_candidate(typedef_symbol: Symbol, symbols_by_name: dict) -> Symbol | None:
    """Find struct that should be unified with this typedef.

    Looks for patterns like:
    - struct _Name {...} + typedef struct _Name Name
    - struct Name {...} + typedef struct Name Name
    """
    if typedef_symbol.kind != "struct" and typedef_symbol.kind != "typedef":
        return None

    typedef_name = typedef_symbol.name

    # Look for matching struct definitions
    # Pattern 1: typedef Name matches struct _Name
    underscore_name = f"_{typedef_name}"
    if underscore_name in symbols_by_name:
        for candidate in symbols_by_name[underscore_name]:
            if (
                candidate.language == "c"
                and candidate.kind == "struct"
                and candidate != typedef_symbol
                and has_struct_body(candidate)
            ):  # Has actual struct body
                return candidate

    # Pattern 2: typedef _Name matches struct _Name (same name)
    if typedef_name in symbols_by_name:
        for candidate in symbols_by_name[typedef_name]:
            if (
                candidate.language == "c"
                and candidate.kind == "struct"
                and candidate != typedef_symbol
                and has_struct_body(candidate)
            ):  # Has actual struct body
                return candidate

    # Pattern 3: Look through ALL struct symbols to find typedef references in their AST
    # This handles cases like: struct _xmlXIncludeRef + typedef struct _xmlXIncludeRef xmlXIncludeDoc
    typedef_node = typedef_symbol._definition_node or typedef_symbol._declaration_node
    if typedef_node and "struct" in _node_text(typedef_node):
        # Extract the struct name from the typedef (the name after 'struct')
        import re

        typedef_text = _node_text(typedef_node)
        match = re.search(r"struct\s+(\w+)", typedef_text)
        if match:
            struct_name = match.group(1)
            if struct_name in symbols_by_name:
                for candidate in symbols_by_name[struct_name]:
                    if (
                        candidate.language == "c"
                        and candidate.kind == "struct"
                        and candidate != typedef_symbol
                        and has_struct_body(candidate)
                    ):
                        return candidate

    return None


def has_struct_body(symbol: Symbol) -> bool:
    """Check if a struct symbol has an actual body (field declarations)."""
    node = symbol._definition_node or symbol._declaration_node
    if not node:
        return False

    # Check for field_declaration_list recursively in case it's nested
    def find_field_list(n):
        if n.type == "field_declaration_list":
            return True
        for child in n.children:
            if find_field_list(child):
                return True
        return False

    return find_field_list(node)


def unify_struct_typedef(struct_symbol: Symbol, typedef_symbol: Symbol) -> Symbol:
    """Unify struct definition with typedef, preferring typedef name."""
    # Create new unified symbol with typedef name but struct body information
    unified = Symbol(
        name=typedef_symbol.name,  # Use typedef name
        kind="struct",  # Always struct kind
        language="c",
        signature=struct_symbol.signature,  # Use struct body signature
        type_dependencies=struct_symbol.type_dependencies.copy(),
        call_dependencies=struct_symbol.call_dependencies.copy(),
        transitive_dependencies=struct_symbol.transitive_dependencies.copy(),
        is_cycle=struct_symbol.is_cycle or typedef_symbol.is_cycle,
        is_static=struct_symbol.is_static or typedef_symbol.is_static,
        line_count=max(struct_symbol.line_count, typedef_symbol.line_count),
        reference_count=struct_symbol.reference_count + typedef_symbol.reference_count,
    )

    # Prefer struct definition info for location (has the actual body)
    if struct_symbol.definition_file:
        unified.definition_file = struct_symbol.definition_file
        unified.definition_line = struct_symbol.definition_line
        unified._definition_node = struct_symbol._definition_node
    elif struct_symbol.declaration_file:
        unified.declaration_file = struct_symbol.declaration_file
        unified.declaration_line = struct_symbol.declaration_line
        unified._declaration_node = struct_symbol._declaration_node

    # Use typedef for declaration info if available
    if typedef_symbol.declaration_file and not unified.declaration_file:
        unified.declaration_file = typedef_symbol.declaration_file
        unified.declaration_line = typedef_symbol.declaration_line
        unified._declaration_node = typedef_symbol._declaration_node

    return unified


class SourceMap:
    """Unified source map for C and Rust symbols with dependency analysis."""

    def __init__(self, project_root: Path, config: "ProjectConfig"):
        assert project_root.exists(), f"Project root {project_root} does not exist"
        assert project_root.is_absolute(), f"Project root {project_root} is not absolute"
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
        self.built_in_types = ALL_BUILT_IN_TYPES

        # Parse all files immediately at initialization
        self._parse_all_files()
        self._unify_struct_typedefs()
        # Skip transitive dependency resolution since we only output direct dependencies

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
        name = _node_text(node)
        if should_skip(name, self.built_in_types):
            return

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

        # Handle typedef struct patterns
        elif node.type == "declaration" and self._is_typedef_struct(node):
            symbol = self._extract_c_typedef_struct(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "preproc_def" and file_path.suffix == ".h":
            symbol = self._extract_c_define(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "preproc_function_def" and file_path.suffix == ".h":
            symbol = self._extract_c_function_like_macro(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)
                # Extract call dependencies for function-like macros
                calls = self._find_c_function_calls(node, code)
                self.call_graph[symbol.name] = calls

        elif node.type == "init_declarator" and self._is_top_level_constant(node):
            symbol = self._extract_c_constant(node, file_path, code)
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "declaration" and self._is_constant_declaration(node):
            symbol = self._extract_c_constant_declaration(node, file_path, code)
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

        elif node.type == "const_item":
            symbol = self._extract_simple_rust_symbol(node, file_path, code, "const")
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "static_item":
            symbol = self._extract_simple_rust_symbol(node, file_path, code, "static")
            if symbol:
                self._add_or_merge_symbol(symbol)

        elif node.type == "type_item":
            symbol = self._extract_simple_rust_symbol(
                node, file_path, code, "type", "type_identifier"
            )
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

    def _extract_c_function(
        self, node: Node, file_path: Path, code: bytes, is_definition: bool
    ) -> Symbol | None:
        """Extract C function symbol."""
        name_node = find_function_name_node(node)
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from parameters and return type
        type_deps = extract_generic_type_dependencies(node, self.built_in_types)

        # Calculate line count for definitions
        line_count = 0
        if is_definition:
            line_count = node.end_point[0] - node.start_point[0] + 1

        # Check if static
        is_static = is_c_function_static(node)

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
        # Skip forward declarations (structs without field_declaration_list)
        has_body = any(child.type == "field_declaration_list" for child in node.children)
        if not has_body:
            return None

        info = extract_simple_c_symbol_info(
            node, code, "struct", file_path, self.project_root, self.built_in_types
        )
        if not info:
            return None

        name, signature, line_num, is_definition, type_deps = info
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
        info = extract_simple_c_symbol_info(
            node, code, "enum", file_path, self.project_root, self.built_in_types
        )
        if not info:
            return None

        name, signature, line_num, is_definition, type_deps = info
        return self._create_symbol(
            name=name,
            kind="enum",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=is_definition,
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_c_typedef(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C typedef symbol."""
        # Only filter non-struct simple typedefs - let struct forward declarations through for unification
        node_text = _node_text(node)
        if (
            "*" in node_text  # pointer typedefs
            or (
                "struct" not in node_text
                and "enum" not in node_text
                and any(prim in node_text for prim in ["int", "char", "float", "double", "void"])
            )
        ):  # primitive aliases
            return None

        # For typedef struct patterns, find all type_identifiers and take the last one
        type_identifiers = []

        def find_type_identifiers(n: Node):
            if n.type == "type_identifier":
                type_identifiers.append(n)
            for child in n.children:
                find_type_identifiers(child)

        find_type_identifiers(node)

        if not type_identifiers:
            return None

        # The typedef name is usually the last type_identifier
        name_node = type_identifiers[-1]
        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from the typedef, excluding the typedef name itself
        type_deps = extract_typedef_type_dependencies(node, self.built_in_types)
        type_deps.discard(name)  # Don't depend on yourself

        # Determine the kind based on the typedef content
        node_text = _node_text(node)
        if "struct" in node_text:
            kind = "struct"
        elif "enum" in node_text:
            kind = "enum"
        else:
            kind = "typedef"

        return self._create_symbol(
            name=name,
            kind=kind,
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,  # typedef struct definitions are definitions
            type_deps=type_deps,
            ast_node=node,
        )

    def _extract_rust_function(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust function symbol."""
        name_node = find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1
        line_count = node.end_point[0] - node.start_point[0] + 1

        # Extract type dependencies
        type_deps = extract_generic_type_dependencies(node, self.built_in_types)

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
        name_node = find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from struct fields
        type_deps = extract_field_type_dependencies(node, self.built_in_types, "field_declaration")

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
        name_node = find_node_by_type(node, "type_identifier")
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Extract type dependencies from enum variants
        type_deps = extract_field_type_dependencies(node, self.built_in_types, "enum_variant")

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

    def _extract_simple_rust_symbol(
        self,
        node: Node,
        file_path: Path,
        code: bytes,
        kind: str,
        name_node_type: str = "identifier",
    ) -> Symbol | None:
        """Extract simple Rust symbol (const, static, type alias)."""
        name_node = find_node_by_type(node, name_node_type)
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return create_simple_symbol(
            name=name,
            kind=kind,
            language="rust",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            project_root=self.project_root,
            is_definition=True,
            ast_node=node,
        )

    def _extract_rust_impl(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract Rust impl block symbol."""
        type_node = find_node_by_type(node, "type_identifier")
        if not type_node:
            return None

        type_name = _node_text(type_node)
        name = f"impl_{type_name}"
        signature = extract_signature(code, node)
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
        name_node = find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
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

    def _extract_c_define(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C #define symbol."""
        # For #define, the name is typically the second child (after "define")
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break

        if not name_node:
            return None

        name = _node_text(name_node)

        # Skip header guards and other common preprocessor patterns
        if self._is_header_guard_or_common_define(name, file_path, node):
            return None

        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        # Check if this is a function-like macro (has parameters)
        # Look for parameter list after the macro name
        is_function_like = self._is_function_like_macro(node, name_node)

        # Treat function-like macros as functions for dependency purposes
        kind = "function" if is_function_like else "define"

        return self._create_symbol(
            name=name,
            kind=kind,
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_c_function_like_macro(
        self, node: Node, file_path: Path, code: bytes
    ) -> Symbol | None:
        """Extract C function-like macro symbol."""
        # For preproc_function_def, the name is the second child (after "#define")
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break

        if not name_node:
            return None

        name = _node_text(name_node)

        # Skip header guards and other common preprocessor patterns
        if self._is_header_guard_or_common_define(name, file_path, node):
            return None

        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="function",  # Function-like macros are treated as functions
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_c_constant(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C constant from init_declarator."""
        # Find the identifier in the init_declarator
        name_node = find_node_by_type(node, "identifier")
        if not name_node:
            return None

        name = _node_text(name_node)
        signature = extract_signature(code, node)
        line_num = name_node.start_point[0] + 1

        return self._create_symbol(
            name=name,
            kind="const",
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            ast_node=node,
        )

    def _extract_c_constant_declaration(
        self, node: Node, file_path: Path, code: bytes
    ) -> Symbol | None:
        """Extract C constant from a const declaration."""
        # Find all init_declarators in this declaration
        symbols = []
        for child in node.children:
            if child.type == "init_declarator":
                symbol = self._extract_c_constant(child, file_path, code)
                if symbol:
                    symbols.append(symbol)

        # Return the first symbol found, or None if none
        return symbols[0] if symbols else None

    def _is_top_level_constant(self, node: Node) -> bool:
        """Check if this init_declarator is a top-level constant."""
        # Walk up the AST to check if this is at file scope and has const qualifier
        parent = node.parent
        while parent and parent.type != "translation_unit":
            if parent.type == "function_definition" or parent.type == "compound_statement":
                return False  # Inside a function
            parent = parent.parent

        # Check if the declaration has const qualifier
        if parent and parent.type == "translation_unit":
            # Look for const in the parent declaration
            decl_parent = node.parent
            if decl_parent and decl_parent.type == "declaration":
                decl_text = _node_text(decl_parent)
                return "const" in decl_text or "static const" in decl_text

        return False

    def _is_constant_declaration(self, node: Node) -> bool:
        """Check if this declaration is a constant declaration."""
        # Check if the declaration contains const qualifier
        node_text = _node_text(node)
        return (
            "const" in node_text
            and "=" in node_text
            and not any(child.type == "function_declarator" for child in node.children)
        )

    def _is_header_guard_or_common_define(self, name: str, file_path: Path, node: Node) -> bool:
        """Check if this #define is a header guard or other common pattern to ignore."""
        # Header guard patterns
        if name.startswith("__") and name.endswith("__"):
            return True

        # Common pattern: file-based header guards
        if name.endswith(("_H", "_H_", "_H__", "_HPP", "_HPP_", "_HPP__")):
            return True

        # Check if this is an empty define (flag macro)
        if is_empty_define(node):
            return True

        # For non-empty defines, only filter common ignore patterns (not version/feature flags)
        if name in COMMON_IGNORE_PATTERNS:
            return True

        # Only filter feature flag patterns if they are empty defines
        # (This logic is already handled above by is_empty_define check)

        # Pattern: single letter or very short defines (often used for feature flags)
        if len(name) <= 2:
            return True

        return False

    def _is_function_like_macro(self, node: Node, name_node: Node) -> bool:
        """Check if this #define is a function-like macro (has parameters)."""
        # Check the next character after the name
        # If it's '(' without whitespace, it's a function-like macro
        try:
            # Get the full text of the preproc_def node
            node_text = _node_text(node)
            name_text = _node_text(name_node)

            # Find the name in the node text
            name_start = node_text.find(name_text)
            if name_start >= 0:
                name_end = name_start + len(name_text)
                # Check if the character immediately after the name is '('
                if name_end < len(node_text) and node_text[name_end] == "(":
                    return True
        except Exception:
            pass

        return False

    def _is_typedef_struct(self, node: Node) -> bool:
        """Check if this declaration is a typedef struct."""
        node_text = _node_text(node)
        return (
            "typedef" in node_text
            and ("struct" in node_text or "enum" in node_text)
            and node_text.strip().endswith(";")
        )

    def _extract_c_typedef_struct(self, node: Node, file_path: Path, code: bytes) -> Symbol | None:
        """Extract C typedef struct/enum symbol."""
        # Filter out simple typedefs
        if is_simple_typedef(node):
            return None

        # Look for the typedef name (usually the last identifier before semicolon)
        identifiers = []

        def find_identifiers(n: Node):
            if n.type == "type_identifier":
                identifiers.append(_node_text(n))
            for child in n.children:
                find_identifiers(child)

        find_identifiers(node)

        if not identifiers:
            return None

        # The typedef name is usually the last identifier
        name = identifiers[-1]
        signature = extract_signature(code, node)
        line_num = node.start_point[0] + 1

        # Extract type dependencies from the struct/enum body
        type_deps = extract_generic_type_dependencies(node, self.built_in_types)

        return self._create_symbol(
            name=name,
            kind="struct",  # Could be enum too, but struct is more general
            language="c",
            signature=signature,
            file_path=file_path,
            line_num=line_num,
            is_definition=True,
            type_deps=type_deps,
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
        type_deps: set[str] | None = None,
        line_count: int = 0,
        is_static: bool = False,
        ast_node: Node | None = None,
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

    def _unify_struct_typedefs(self):
        """Unify struct definitions with their typedef counterparts."""
        symbols_to_remove = []
        unified_symbols = []
        processed_pairs = set()

        # Find typedef symbols that could be unified with structs
        for (_, language), symbol in self.symbols.items():
            if language == "c" and symbol.kind in ["struct", "typedef"]:
                unification_candidate = find_unification_candidate(symbol, self.symbols_by_name)

                if unification_candidate:
                    # Avoid processing the same pair twice
                    pair_key = tuple(sorted([symbol.name, unification_candidate.name]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)

                    # Create unified symbol - prefer typedef name
                    # Determine which one is the typedef and which is the struct with body
                    if has_struct_body(symbol):
                        struct_symbol = symbol
                        typedef_symbol = unification_candidate
                    else:
                        struct_symbol = unification_candidate
                        typedef_symbol = symbol

                    unified = unify_struct_typedef(struct_symbol, typedef_symbol)

                    unified_symbols.append(unified)

                    # Mark originals for removal
                    symbols_to_remove.append((symbol.name, language))
                    symbols_to_remove.append((unification_candidate.name, language))

        # Also remove any remaining forward declarations that didn't get unified
        for (symbol_name, language), symbol in list(self.symbols.items()):
            if (
                language == "c"
                and symbol.kind in ["struct", "typedef"]
                and (symbol_name, language) not in symbols_to_remove
            ):
                # Check if this is a forward declaration or simple typedef
                node = symbol._definition_node or symbol._declaration_node
                if node and is_simple_typedef(node):
                    symbols_to_remove.append((symbol_name, language))
                # Also remove struct symbols that don't have bodies
                elif symbol.kind == "struct" and not has_struct_body(symbol):
                    symbols_to_remove.append((symbol_name, language))

        # Remove original symbols
        for key in symbols_to_remove:
            if key in self.symbols:
                old_symbol = self.symbols[key]
                del self.symbols[key]

                # Remove from by-name index
                if old_symbol.name in self.symbols_by_name:
                    self.symbols_by_name[old_symbol.name] = [
                        s for s in self.symbols_by_name[old_symbol.name] if s != old_symbol
                    ]
                    if not self.symbols_by_name[old_symbol.name]:
                        del self.symbols_by_name[old_symbol.name]

        # Add unified symbols
        for unified in unified_symbols:
            self._add_or_merge_symbol(unified)

    def _find_c_function_calls(self, node: Node, code: bytes) -> set[str]:
        """Find all function calls within a C function."""
        del code  # Unused parameter
        calls = set()

        def find_calls(n: Node):
            if should_skip(_node_text(n), self.built_in_types):
                return

            if n.type == "call_expression":
                # Get the function name from the call
                for child in n.children:
                    if child.type == "identifier":
                        calls.add(_node_text(child))
                        break
            for child in n.children:
                find_calls(child)

        find_calls(node)
        return calls

    def _find_rust_function_calls(self, node: Node, code: bytes) -> set[str]:
        """Find all function calls within a Rust function."""
        del code  # Unused parameter
        calls = set()

        def find_calls(n: Node):
            if n.type == "call_expression":
                # Get the function name from the call
                for child in n.children:
                    if child.type == "identifier":
                        calls.add(_node_text(child))
                        break
                    elif child.type == "field_expression":
                        # Handle method calls
                        for grandchild in child.children:
                            if grandchild.type == "field_identifier":
                                calls.add(_node_text(grandchild))
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
            symbol.transitive_dependencies = (
                all_deps - symbol.type_dependencies - symbol.call_dependencies
            )

    def _get_symbol_dependencies(self, node_name: str) -> set[str]:
        """Get dependencies for a node (try rust first then c)."""
        node_symbol = None
        for (name, language), s in self.symbols.items():
            if name == node_name:
                if node_symbol is None or language == "rust":
                    node_symbol = s

        if not node_symbol:
            return set()

        # Filter dependencies to only include symbols that should be kept
        filtered_deps = set()
        for dep in node_symbol.all_dependencies:
            if dep in self.symbols_by_name:
                for dep_symbol in self.symbols_by_name[dep]:
                    if dep_symbol.language == "c" and self._should_keep_symbol(
                        dep_symbol
                    ):
                        filtered_deps.add(dep)
                        break

        return filtered_deps

    def _detect_strongly_connected_components(self) -> list[set[str]]:
        """Use Tarjan's algorithm to find strongly connected components."""
        return detect_strongly_connected_components(
            self.symbols_by_name, self._get_symbol_dependencies
        )

    def _get_c_symbol_dependencies(self, node_name: str, c_symbols: dict) -> set[str]:
        """Get dependencies for a C symbol."""
        if should_skip(node_name, self.built_in_types):
            return set()

        if node_name not in c_symbols:
            return set()

        return c_symbols[node_name].all_dependencies

    def _detect_strongly_connected_components_for_c_symbols(
        self, c_symbols: dict, c_symbols_by_name: dict
    ) -> list[set[str]]:
        """Use Tarjan's algorithm to find strongly connected components for C symbols only."""
        return detect_strongly_connected_components(
            c_symbols_by_name, lambda name: self._get_c_symbol_dependencies(name, c_symbols)
        )

    def _should_keep_symbol(self, symbol: Symbol) -> bool:
        """Determine if symbol should be kept in the graph.

        Keep symbol if:
        - It's defined in a header file, OR
        - It's non-static AND implementation size > 10 lines
        """
        if should_skip(symbol.name, self.built_in_types):
            return False

        # Always keep symbols defined in header files
        if symbol.header_path:
            return True

        # For non-header symbols, keep if non-static and implementation size > 10 lines
        if not symbol.is_static and symbol.line_count > 10:
            return True

        return False

    def _topological_sort(self) -> list[Symbol]:
        """Perform topological sort with cycle handling and depth tracking, focusing only on C symbols."""
        # Filter to only include C symbols that pass the keep heuristic
        c_symbols = {}
        c_symbols_by_name = {}

        for (symbol_name, language), symbol in self.symbols.items():
            if (
                language == "c"
                and symbol.kind
                in ["function", "struct", "enum", "const", "define", "typedef"]
                and self._should_keep_symbol(symbol)
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

        # Kahn's algorithm with depth tracking
        queue: deque[tuple[str, int]] = deque()  # (symbol_name, depth)
        result: list[tuple[Symbol, int]] = []  # (symbol, depth)
        symbol_depths: dict[str, int] = {}

        # Start with nodes that have no dependencies at depth 0
        for symbol_name, degree in in_degree.items():
            if degree == 0:
                queue.append((symbol_name, 0))
                symbol_depths[symbol_name] = 0

        while queue:
            current, depth = queue.popleft()
            # Get the C symbol
            current_symbol = None
            for (name, _), s in c_symbols.items():
                if name == current:
                    current_symbol = s
                    break
            if current_symbol:
                result.append((current_symbol, depth))

            # Remove edges from current node and update depths
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                # Update neighbor's depth to be at least current depth + 1
                neighbor_depth = max(symbol_depths.get(neighbor, 0), depth + 1)
                symbol_depths[neighbor] = neighbor_depth

                if in_degree[neighbor] == 0:
                    queue.append((neighbor, neighbor_depth))

        # Handle remaining nodes (those in cycles) - assign them max depth + 1
        remaining = set(key[0] for key in c_symbols.keys()) - {s.name for s, _ in result}
        if remaining:
            max_depth = max((depth for _, depth in result), default=0)
            cycle_depth = max_depth + 1
            # Add remaining symbols sorted by name
            for symbol_name in sorted(remaining):
                # Get the first symbol with this name
                for (name, _), symbol in c_symbols.items():
                    if name == symbol_name:
                        result.append((symbol, cycle_depth))
                        symbol_depths[symbol_name] = cycle_depth
                        break

        # Store depths in symbols for later use
        for symbol, depth in result:
            symbol._depth = depth

        # Return just the symbols (depths are stored in the symbols themselves)
        return [symbol for symbol, _ in result]

    def get_symbol_source_code(self, symbol_name: str) -> str:
        """Get the source code for a symbol."""
        # Get the first symbol with this name (prefer rust over c)
        symbol: Symbol | None = None
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
        return get_c_symbol_source_code(symbol, file_path)

    def _get_rust_symbol_source_code(self, symbol: Symbol, file_path: Path) -> str:
        """Get Rust symbol source code using tree-sitter."""
        return get_c_symbol_source_code(symbol, file_path)  # Same implementation works for both

    def lookup_symbol(self, symbol_name: str) -> SymbolInfo:
        """Find all locations of a symbol and return SymbolInfo with all paths."""
        # Look for all symbols with this name (may have multiple with different languages)
        matching_symbols = self.symbols_by_name.get(symbol_name, [])

        info = SymbolInfo()

        if matching_symbols:
            # Process all matching symbols
            for symbol in matching_symbols:
                # Check for FFI binding (if this is the declaration in ffi.rs)
                if symbol.declaration_file and str(symbol.declaration_file).endswith("ffi.rs"):
                    info.ffi_path = str(symbol.declaration_file)

                # Check for Rust implementation
                if (
                    symbol.definition_file
                    and str(symbol.definition_file).endswith(".rs")
                    and "ffi.rs" not in str(symbol.definition_file)
                ):
                    info.rust_src_path = str(symbol.definition_file)
                elif (
                    symbol.declaration_file
                    and str(symbol.declaration_file).endswith(".rs")
                    and "ffi.rs" not in str(symbol.declaration_file)
                ):
                    info.rust_src_path = str(symbol.declaration_file)

                # Check for C header (could be declaration or definition in .h file)
                if symbol.declaration_file and str(symbol.declaration_file).endswith(".h"):
                    info.c_header_path = str(symbol.declaration_file)
                elif symbol.definition_file and str(symbol.definition_file).endswith(".h"):
                    info.c_header_path = str(symbol.definition_file)

                # Check for C source
                if symbol.definition_file and str(symbol.definition_file).endswith(".c"):
                    info.c_source_path = str(symbol.definition_file)

        # Check for FFI binding manually if not found in symbols
        if not info.ffi_path:
            ffi_path = self.config.rust_ffi_path()
            if ffi_path.exists() and self.find_ffi_binding_definition(ffi_path, symbol_name):
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

        symbol: Symbol | None = None
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

                    lines.append(
                        f"- **{symbol.name}**{line_info}{deps_info}{cycle_info}{static_info}"
                    )

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
                    return extract_signature(code, target_node)
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
                        or (symbol.declaration_file and "ffi.rs" in str(symbol.declaration_file))
                    )
                    and symbol.declaration_file
                    and symbol.declaration_file.name == file_path.name
                ):
                    # Try to extract full source from AST node
                    if symbol._declaration_node:
                        try:
                            code = file_path.read_bytes()
                            return extract_signature(code, symbol._declaration_node)
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
                        return extract_signature(code, symbol._definition_node)
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
    if len(sys.argv) != 2:
        print("Usage: python sourcemap.py <src_directory>")
        sys.exit(1)

    src_dir = Path(sys.argv[1]).resolve()
    if not src_dir.exists():
        print(f"Error: Directory {src_dir} does not exist")
        sys.exit(1)

    # Find project root (parent of src directory)
    project_root = src_dir

    # Create source map and parse project
    # For CLI usage, create a minimal config
    from portkit.config import ProjectConfig

    config = ProjectConfig(
        project_name="temp", library_name="temp", project_root=project_root
    )
    source_map = SourceMap(project_root, config)
    symbols = source_map.parse_project()

    # Sort symbols by depth first, then by file stem within each depth
    sorted_symbols = sorted(symbols, key=lambda s: (
        getattr(s, '_depth', 0),  # Primary sort: depth
        (Path(str(s.definition_file or s.declaration_file or "")).stem if s.definition_file or s.declaration_file else "")  # Secondary sort: file stem
    ))

    # Output CSV format
    output = StringIO()
    csv_writer = csv.writer(output)

    # Write header
    csv_writer.writerow(
        [
            "name",
            "kind",
            "location",
            "is_cycle",
            "is_static",
            "dependencies",
        ]
    )

    # Write symbol data
    for symbol in sorted_symbols:
        # Determine file path and line number
        if symbol.definition_file:
            file_path = str(symbol.definition_file)
            line_number = symbol.definition_line or ""
            is_definition = True
        elif symbol.declaration_file:
            file_path = str(symbol.declaration_file)
            line_number = symbol.declaration_line or ""
            is_definition = False
        else:
            file_path = ""
            line_number = ""
            is_definition = False

        dependencies = []
        # Only include direct dependencies, not transitive ones
        for dep in symbol.type_dependencies | symbol.call_dependencies:
            try:
                dependencies.append(dep)
            except Exception:
                pass
                # dependencies.append(dep)

        dependencies = set(dependencies)

        csv_writer.writerow(
            [
                symbol.name,
                symbol.kind,
                f"{file_path}:{line_number}",
                "cycle" if symbol.is_cycle else "",
                "static" if symbol.is_static else "",
                ";".join(set(dependencies)),
            ]
        )

    # Collect file statistics
    file_stats = {}
    for symbol in sorted_symbols:
        file_path = ""
        if symbol.definition_file:
            file_path = str(symbol.definition_file)
        elif symbol.declaration_file:
            file_path = str(symbol.declaration_file)
        
        if file_path:
            if file_path not in file_stats:
                # Get actual file line count
                try:
                    full_path = source_map.project_root / file_path
                    if full_path.exists():
                        with open(full_path, encoding='utf-8', errors='ignore') as f:
                            line_count = sum(1 for _ in f)
                    else:
                        line_count = 0
                except Exception:
                    line_count = 0
                    
                file_stats[file_path] = {'lines': line_count, 'functions': 0}
            
            # Count functions
            if symbol.kind == 'function':
                file_stats[file_path]['functions'] += 1

    # Output symbol table
    print("## Symbol Dependencies")
    print(output.getvalue(), end="")
    
    # Output file statistics table
    print("\n## File Statistics")
    file_output = StringIO()
    file_csv_writer = csv.writer(file_output)
    file_csv_writer.writerow(["file", "lines", "functions"])
    
    for file_path in sorted(file_stats.keys()):
        stats = file_stats[file_path]
        file_csv_writer.writerow([file_path, stats['lines'], stats['functions']])
    
    print(file_output.getvalue(), end="")
