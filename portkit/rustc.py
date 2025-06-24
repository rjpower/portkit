#!/usr/bin/env python3

"""Routines to map trivial C symbols: enums, constants, and #defines to Rust."""

import re
from pathlib import Path

import tree_sitter_c as tsc
from tree_sitter import Language, Node, Parser

from portkit.sourcemap import Symbol


class RustTranscribeError(Exception):
    """Raised when rustc cannot handle a symbol and should fall back to agent."""
    pass


# helper to avoid type-checking warnings
def _node_text(node: Node) -> str:
    return node.text.decode().strip()


def map_c_type_to_rust(c_type: str) -> str:
    """Map C types to appropriate Rust types."""
    # Remove qualifiers and normalize whitespace
    c_type = re.sub(r'\b(const|static|extern|volatile)\b', '', c_type).strip()
    c_type = re.sub(r'\s+', ' ', c_type).strip()
    
    # Common type mappings
    type_map = {
        'int': 'i32',
        'unsigned int': 'u32',
        'unsigned': 'u32',
        'char': 'i8',
        'unsigned char': 'u8',
        'short': 'i16',
        'unsigned short': 'u16',
        'long': 'i64',
        'unsigned long': 'u64',
        'long long': 'i64',
        'unsigned long long': 'u64',
        'size_t': 'usize',
        'ptrdiff_t': 'isize',
        'float': 'f32',
        'double': 'f64',
        'bool': 'bool',
        '_Bool': 'bool',
    }
    
    return type_map.get(c_type, c_type)


def extract_define_value_and_type_from_ast(node: Node) -> tuple[str, str]:
    """Extract value and infer type from a #define AST node."""
    if node.type != "preproc_def":
        raise RustTranscribeError("Expected preproc_def node")
    
    # Find the macro value (everything after the name)
    children = list(node.children)
    if len(children) < 3:  # #define NAME VALUE
        raise RustTranscribeError("Empty #define (no value)")
    
    # Skip the #define keyword and macro name
    value_nodes = children[2:]  # Everything after the name
    
    if not value_nodes:
        raise RustTranscribeError("Empty #define (no value)")
    
    # Simple case: single literal value
    if len(value_nodes) == 1:
        value_node = value_nodes[0]
        # Handle preproc_arg nodes which contain the actual value
        if value_node.type == "preproc_arg":
            return _extract_preproc_arg_value_and_type(value_node)
        else:
            return _extract_literal_value_and_type(value_node)
    
    # Multiple nodes could be a complex expression
    raise RustTranscribeError("Complex #define expression with multiple nodes")


def _extract_preproc_arg_value_and_type(preproc_arg_node: Node) -> tuple[str, str]:
    """Extract value and type from a preproc_arg node."""
    # preproc_arg contains the raw text of the macro value
    value_text = _node_text(preproc_arg_node)

    # Check string literals first (before checking for dots)
    if value_text.startswith('"') and value_text.endswith('"'):
        # String literal
        return value_text, "&str"
    elif value_text.startswith("'") and value_text.endswith("'"):
        # Char literal
        return value_text, "u8"
    elif value_text.lower() in ('true', 'false'):
        return value_text.lower(), "bool"
    elif value_text.isdigit():
        # Simple integer
        val = int(value_text)
        if 0 <= val <= 4294967295:
            return value_text, "u32"
        else:
            return value_text, "i32"
    elif value_text.startswith('0x') or value_text.startswith('0X'):
        # Hex literal
        try:
            val = int(value_text, 16)
            if 0 <= val <= 4294967295:
                return value_text, "u32"
            else:
                return value_text, "u64"
        except ValueError as e:
            raise RustTranscribeError(f"Invalid hex literal in preproc_arg: {value_text}") from e
    elif '.' in value_text or 'e' in value_text.lower():
        # Float literal (check after string literals)
        if value_text.endswith(('f', 'F')):
            return value_text.rstrip('fF'), "f32"
        else:
            return value_text, "f64"
    else:
        # Could be a complex expression or identifier
        raise RustTranscribeError(f"Complex or unsupported preproc_arg value: {value_text}")


def _extract_literal_value_and_type(node: Node) -> tuple[str, str]:
    """Extract value and type from a single literal node."""
    node_text = _node_text(node)

    if node.type == "number_literal":
        # Integer literal
        if node_text.endswith(('u', 'U')):
            return node_text.rstrip('uU'), "u32"
        elif node_text.endswith(('ul', 'UL', 'uL', 'Ul')):
            return node_text.rstrip('ulUL'), "usize"
        elif node_text.endswith(('l', 'L')):
            return node_text.rstrip('lL'), "isize"
        elif node_text.startswith('0x') or node_text.startswith('0X'):
            # Hex literal
            try:
                val = int(node_text, 16)
                if 0 <= val <= 4294967295:
                    return node_text, "u32"
                else:
                    return node_text, "u64"
            except ValueError as e:
                raise RustTranscribeError(f"Invalid hex literal: {node_text}") from e
        elif '.' in node_text or 'e' in node_text.lower():
            # Float literal
            if node_text.endswith(('f', 'F')):
                return node_text.rstrip('fF'), "f32"
            else:
                return node_text, "f64"
        else:
            # Plain integer
            try:
                val = int(node_text)
                if 0 <= val <= 4294967295:
                    return node_text, "u32"
                else:
                    return node_text, "i32"
            except ValueError as e:
                raise RustTranscribeError(f"Invalid number literal: {node_text}") from e

    elif node.type == "string_literal":
        return node_text, "&str"

    elif node.type == "char_literal":
        return node_text, "u8"

    elif node.type == "identifier":
        # Could be true/false or other constants
        if node_text.lower() in ('true', 'false'):
            return node_text.lower(), "bool"
        else:
            raise RustTranscribeError(f"Identifier in #define: {node_text}")

    else:
        raise RustTranscribeError(f"Unsupported #define value type: {node.type}")


def extract_const_declaration_from_ast(node: Node) -> tuple[str, str, str]:
    """Extract name, type, and value from a const declaration AST node."""
    if node.type not in ("declaration", "init_declarator"):
        raise RustTranscribeError(f"Expected declaration node, got {node.type}")

    # Find the declarator and initializer
    name = None
    value_node = None
    type_info = None

    def find_declarator_info(n: Node):
        nonlocal name, value_node, type_info

        if n.type == "init_declarator":
            # Get the name from array_declarator or identifier
            for child in n.children:
                if child.type == "array_declarator":
                    # Array declaration: type name[size] = {...}
                    return _extract_array_declaration(child, n)
                elif child.type == "identifier":
                    name = _node_text(child)
                elif child.type == "=":
                    continue  # Skip assignment operator
                elif child.type in ("number_literal", "string_literal", "initializer_list"):
                    value_node = child

        elif n.type == "identifier":
            name = _node_text(n)

        elif n.type in ("number_literal", "string_literal", "initializer_list"):
            value_node = n

        # Recursively search children
        for child in n.children:
            find_declarator_info(child)

    find_declarator_info(node)

    if not name:
        raise RustTranscribeError("Cannot find variable name in declaration")

    if not value_node:
        raise RustTranscribeError(f"Cannot find initializer for {name}")

    # Extract type from the declaration context
    rust_type = _infer_type_from_declaration_and_value(node, value_node)
    value_str = _extract_value_from_node(value_node)

    return name, rust_type, value_str


def _extract_array_declaration(array_declarator: Node, init_declarator: Node) -> tuple[str, str, str]:
    """Extract array declaration information."""
    # Get array name and size
    name = None
    size = None

    for child in array_declarator.children:
        if child.type == "identifier":
            name = _node_text(child)
        elif child.type == "number_literal":
            size = _node_text(child)

    if not name or not size:
        raise RustTranscribeError("Cannot parse array declarator")

    # Find the initializer list
    initializer = None
    for child in init_declarator.children:
        if child.type == "initializer_list":
            initializer = child
            break

    if not initializer:
        raise RustTranscribeError(f"Cannot find array initializer for {name}")

    # Count elements and check complexity
    elements = []
    for child in initializer.children:
        if child.type == "number_literal":
            elements.append(_node_text(child))
        elif child.type != ",":  # Skip commas
            # Complex element (expression, etc.)
            raise RustTranscribeError(f"Complex array element in {name}: {child.type}")

    if len(elements) > 20:
        raise RustTranscribeError(f"Array {name} has {len(elements)} elements, too complex for direct transpilation")

    # Infer element type from first element
    if elements:
        first_elem = elements[0]
        if first_elem.endswith('u'):
            rust_element_type = "u32"
        else:
            rust_element_type = "u32"  # Default
    else:
        rust_element_type = "u32"

    rust_type = f"[{rust_element_type}; {size}]"
    value_str = f"[{', '.join(elements)}]"

    return name, rust_type, value_str


def _infer_type_from_declaration_and_value(decl_node: Node, value_node: Node) -> str:
    """Infer Rust type from C declaration context and value."""
    # Look for type information in the declaration node and its parent
    node_text = _node_text(decl_node)

    # If we're in an init_declarator, check the parent declaration for type info
    if decl_node.type == "init_declarator" and decl_node.parent:
        parent_text = _node_text(decl_node.parent)
        node_text = parent_text

    # Look for C type keywords
    if "size_t" in node_text:
        return "usize"
    elif "ptrdiff_t" in node_text:
        return "isize"
    elif "unsigned long" in node_text:
        return "u64"
    elif "unsigned" in node_text and "int" in node_text:
        return "u32"
    elif "unsigned" in node_text:
        return "u32"
    elif "long" in node_text:
        return "i64"
    elif "int" in node_text:
        return "i32"
    elif "float" in node_text:
        return "f32"
    elif "double" in node_text:
        return "f64"

    # Fall back to inferring from value
    if value_node.type == "number_literal":
        value_text = value_node.text.decode()
        if value_text.endswith('u'):
            return "u32"
        elif '.' in value_text:
            return "f64"
        else:
            return "i32"
    elif value_node.type == "string_literal":
        return "&str"

    # Default fallback
    return "i32"


def _extract_value_from_node(value_node: Node) -> str:
    """Extract the value string from an AST node."""
    if value_node.type == "initializer_list":
        # Array initializer
        elements = []
        for child in value_node.children:
            if child.type == "number_literal":
                elements.append(_node_text(child))
        return f"[{', '.join(elements)}]"
    else:
        # Simple value
        return _node_text(value_node)


def _transpile_enum_from_ast(enum_node: Node, enum_name: str) -> str:
    """Transpile a C enum to Rust using AST analysis."""
    if enum_node.type != "enum_specifier":
        raise RustTranscribeError(f"Expected enum_specifier node, got {enum_node.type}")
    
    # Find the enumerator list
    enumerator_list = None
    for child in enum_node.children:
        if child.type == "enumerator_list":
            enumerator_list = child
            break
    
    if not enumerator_list:
        raise RustTranscribeError(f"Enum {enum_name} has no enumerator list")
    
    # Parse enum variants from AST
    variants = []
    for child in enumerator_list.children:
        if child.type == "enumerator":
            variant_info = _parse_enum_variant_from_ast(child)
            if variant_info:
                variants.append(variant_info)
    
    if not variants:
        raise RustTranscribeError(f"Enum {enum_name} has no valid variants")
    
    variants_str = ',\n'.join(variants)
    if variants_str:
        variants_str += ','
    
    return f"""#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum {enum_name} {{
{variants_str}
}}"""


def _parse_enum_variant_from_ast(enumerator_node: Node) -> str | None:
    """Parse a single enum variant from an enumerator AST node."""
    name = None
    value = None

    for child in enumerator_node.children:
        if child.type == "identifier":
            name = _node_text(child)
        elif child.type == "number_literal":
            value = _node_text(child)
        elif child.type in ("unary_expression", "binary_expression"):
            # Complex expression - bail out
            raise RustTranscribeError(f"Complex enum value expression: {child.type}")

    if not name:
        return None

    if value:
        # Validate the value is simple
        if not (value.isdigit() or value.startswith('0x') or value.startswith('-')):
            raise RustTranscribeError(f"Complex enum value: {value}")
        return f"    {name} = {value}"
    else:
        return f"    {name}"


def transpile_const(symbol: Symbol) -> str:
    """Transpile a C constant to Rust using AST analysis."""
    # Get the AST node from the symbol
    ast_node = symbol._definition_node or symbol._declaration_node
    if not ast_node:
        raise RustTranscribeError(f"No AST node available for symbol {symbol.name}")
    
    if symbol.kind == "define":
        # Handle #define using AST
        value, rust_type = extract_define_value_and_type_from_ast(ast_node)
        return f"pub const {symbol.name}: {rust_type} = {value};"
    elif symbol.kind == "const":
        # Handle const declaration using AST
        name, rust_type, value = extract_const_declaration_from_ast(ast_node)
        return f"pub const {name}: {rust_type} = {value};"
    else:
        raise RustTranscribeError(f"Cannot transpile symbol of kind: {symbol.kind}")


def transpile_enum(symbol: Symbol) -> str:
    """Transpile a C enum to Rust using AST analysis."""
    # Get the AST node from the symbol
    ast_node = symbol._definition_node or symbol._declaration_node
    if not ast_node:
        raise RustTranscribeError(f"No AST node available for enum {symbol.name}")
    
    return _transpile_enum_from_ast(ast_node, symbol.name)


def can_transpile_directly(symbol: Symbol) -> bool:
    """Check if a symbol can be directly transpiled without LLM."""
    return symbol.kind in ("const", "define", "enum")


def transpile(symbol: Symbol, project_root: Path) -> str:  # noqa: ARG001
    """
    Transpile a symbol directly to Rust code.
    
    Args:
        symbol: The symbol to transpile
        project_root: Project root path (for potential future use)
    
    Returns:
        Rust code string if transpilation is successful.
        
    Raises:
        RustTranscribeError: If the symbol cannot be transpiled directly.
    """
    if not can_transpile_directly(symbol):
        raise RustTranscribeError(f"Symbol kind '{symbol.kind}' cannot be transpiled directly")
    
    if symbol.kind in ("const", "define"):
        return transpile_const(symbol)
    elif symbol.kind == "enum":
        return transpile_enum(symbol)
    
    raise RustTranscribeError(f"No transpilation handler for symbol kind: {symbol.kind}")


def extract_define_value_and_type(define_text: str) -> tuple[str, str]:
    """Legacy compatibility function for tests that use regex parsing."""
    # Parse the C code to get AST for compatibility
    language_c = Language(tsc.language())
    parser = Parser(language_c)
    
    tree = parser.parse(define_text.encode())
    root = tree.root_node
    
    # Find the preproc_def node
    for child in root.children:
        if child.type == "preproc_def":
            return extract_define_value_and_type_from_ast(child)
    
    raise RustTranscribeError(f"Could not parse #define: {define_text}")


def extract_const_declaration(decl_text: str) -> tuple[str, str, str]:
    """Legacy compatibility function for tests that use regex parsing."""
    # Parse the C code to get AST for compatibility
    language_c = Language(tsc.language())
    parser = Parser(language_c)
    
    tree = parser.parse(decl_text.encode())
    root = tree.root_node
    
    # Find the declaration node
    for child in root.children:
        if child.type == "declaration":
            for declarator in child.children:
                if declarator.type == "init_declarator":
                    return extract_const_declaration_from_ast(declarator)
    
    raise RustTranscribeError(f"Could not parse const declaration: {decl_text}")


def write_transpiled_symbol(symbol: Symbol, rust_code: str, target_file: Path) -> None:
    """Write transpiled Rust code to the target file."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content if file exists
    existing_content = ""
    if target_file.exists():
        existing_content = target_file.read_text()
    
    # Check if symbol already exists in file
    if f"pub const {symbol.name}" in existing_content or f"pub enum {symbol.name}" in existing_content:
        # Symbol already exists, don't duplicate
        return
    
    # Append the new symbol
    if existing_content and not existing_content.endswith('\n'):
        existing_content += '\n'
    
    new_content = existing_content + rust_code + '\n\n'
    target_file.write_text(new_content)
