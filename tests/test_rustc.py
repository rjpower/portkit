#!/usr/bin/env python3

import tempfile
from pathlib import Path

import pytest
import tree_sitter_c as tsc
from tree_sitter import Language, Parser

from portkit.config import ProjectConfig
from portkit.rustc import (
    RustTranscribeError,
    can_transpile_directly,
    extract_const_declaration,
    extract_define_value_and_type,
    map_c_type_to_rust,
    transpile,
    transpile_const,
    transpile_enum,
)
from portkit.sourcemap import SourceMap, Symbol


def create_symbol_from_c_code(c_code: str, symbol_name: str) -> Symbol:
    """Create a symbol with AST node by parsing C code."""
    # Create a temporary project structure
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        src_dir = project_root / "src"
        src_dir.mkdir()
        
        # Write C code to a temporary file  
        c_file = src_dir / "test.h"  # Use .h extension to ensure defines are parsed
        c_file.write_text(c_code)
        
        # Create a minimal config
        config = ProjectConfig(project_name="test", library_name="test", project_root=project_root)
        
        # Parse the file to create symbols
        source_map = SourceMap(project_root, config)
        
        # Find the symbol we're looking for
        if symbol_name in source_map.symbols_by_name:
            return source_map.symbols_by_name[symbol_name][0]
        
        # If not found, create manually with tree-sitter parsing
        c_language = Language(tsc.language())
        parser = Parser(c_language)
        tree = parser.parse(c_code.encode())
        
        # Find the relevant node by type
        def find_node_by_type(node, node_type):
            if node.type == node_type:
                return node
            for child in node.children:
                result = find_node_by_type(child, node_type)
                if result:
                    return result
            return None
        
        # Determine symbol kind and find appropriate AST node
        if "#define" in c_code:
            kind = "define" 
            ast_node = find_node_by_type(tree.root_node, "preproc_def")
        elif "const" in c_code:
            kind = "const"
            ast_node = find_node_by_type(tree.root_node, "declaration")
        elif "enum" in c_code:
            kind = "enum"
            ast_node = find_node_by_type(tree.root_node, "enum_specifier")
        else:
            kind = "unknown"
            ast_node = tree.root_node
        
        # Create symbol with AST node
        symbol = Symbol(
            name=symbol_name,
            kind=kind,
            language="c",
            signature=c_code.strip()
        )
        symbol._definition_node = ast_node
        
        return symbol


def test_map_c_type_to_rust():
    """Test C to Rust type mapping."""
    assert map_c_type_to_rust("int") == "i32"
    assert map_c_type_to_rust("unsigned int") == "u32"
    assert map_c_type_to_rust("const unsigned int") == "u32"
    assert map_c_type_to_rust("size_t") == "usize"
    assert map_c_type_to_rust("char") == "i8"
    assert map_c_type_to_rust("unsigned char") == "u8"
    assert map_c_type_to_rust("float") == "f32"
    assert map_c_type_to_rust("double") == "f64"


def test_extract_define_value_and_type():
    """Test extraction of #define values and type inference."""
    # Integer values
    value, rust_type = extract_define_value_and_type("#define MAX_SIZE 1024")
    assert value == "1024"
    assert rust_type == "u32"  # Updated from u16 to u32 (AST-based inference)
    
    # Boolean values
    value, rust_type = extract_define_value_and_type("#define ENABLED true")
    assert value == "true"
    assert rust_type == "bool"
    
    # Float values
    value, rust_type = extract_define_value_and_type("#define PI 3.14159")
    assert value == "3.14159"
    assert rust_type == "f64"
    
    # String values
    value, rust_type = extract_define_value_and_type('#define VERSION "1.0"')
    assert value == '"1.0"'
    assert rust_type == "&str"


def test_extract_const_declaration():
    """Test extraction of const declarations."""
    name, rust_type, value = extract_const_declaration("const int MAX_SIZE = 1024;")
    assert name == "MAX_SIZE"
    assert rust_type == "i32"
    assert value == "1024"
    
    name, rust_type, value = extract_const_declaration("static const size_t BUFFER_SIZE = 4096;")
    assert name == "BUFFER_SIZE"
    assert rust_type == "usize"
    assert value == "4096"


def test_can_transpile_directly():
    """Test which symbols can be directly transpiled."""
    const_symbol = Symbol(name="MAX_SIZE", kind="const", language="c", signature="const int MAX_SIZE = 1024;")
    define_symbol = Symbol(name="BUFFER_SIZE", kind="define", language="c", signature="#define BUFFER_SIZE 4096")
    enum_symbol = Symbol(name="Status", kind="enum", language="c", signature="enum Status { OK, ERROR };")
    function_symbol = Symbol(name="foo", kind="function", language="c", signature="int foo(void);")
    
    assert can_transpile_directly(const_symbol)
    assert can_transpile_directly(define_symbol)
    assert can_transpile_directly(enum_symbol)
    assert not can_transpile_directly(function_symbol)


def test_transpile_const():
    """Test transpilation of const symbols."""
    # Test #define
    define_symbol = create_symbol_from_c_code("#define MAX_SIZE 1024", "MAX_SIZE")
    result = transpile_const(define_symbol)
    assert result == "pub const MAX_SIZE: u32 = 1024;"
    
    # Test const declaration
    const_symbol = create_symbol_from_c_code("const int BUFFER_SIZE = 4096;", "BUFFER_SIZE")
    result = transpile_const(const_symbol)
    assert result == "pub const BUFFER_SIZE: i32 = 4096;"


def test_transpile_enum():
    """Test transpilation of enum symbols."""
    # Simple enum with variants
    enum_symbol = create_symbol_from_c_code("enum Status { OK, ERROR, PENDING };", "Status")
    result = transpile_enum(enum_symbol)
    expected = """#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    OK,
    ERROR,
    PENDING,
}"""
    assert result == expected

    # Enum with explicit values
    enum_symbol = create_symbol_from_c_code("enum ErrorCode { SUCCESS = 0, FAILURE = 1, TIMEOUT = 2 };", "ErrorCode")
    result = transpile_enum(enum_symbol)
    expected = """#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCode {
    SUCCESS = 0,
    FAILURE = 1,
    TIMEOUT = 2,
}"""
    assert result == expected


def test_transpile():
    """Test the main transpile function."""
    project_root = Path("/tmp/test_project")
    
    # Test const symbol
    const_symbol = create_symbol_from_c_code("const int MAX_SIZE = 1024;", "MAX_SIZE")
    result = transpile(const_symbol, project_root)
    assert result == "pub const MAX_SIZE: i32 = 1024;"
    
    # Test define symbol
    define_symbol = create_symbol_from_c_code("#define BUFFER_SIZE 4096", "BUFFER_SIZE")
    result = transpile(define_symbol, project_root)
    assert result == "pub const BUFFER_SIZE: u32 = 4096;"
    
    # Test enum symbol
    enum_symbol = create_symbol_from_c_code("enum Status { OK, ERROR };", "Status")
    result = transpile(enum_symbol, project_root)
    assert result is not None
    assert "pub enum Status" in result
    assert "#[repr(C)]" in result
    
    # Test non-transpilable symbol
    function_symbol = Symbol(
        name="foo",
        kind="function",
        language="c",
        signature="int foo(void);"
    )
    with pytest.raises(RustTranscribeError):
        transpile(function_symbol, project_root)


def test_real_world_examples():
    """Test with real-world examples from zopfli-port."""
    # Test zopfli constants
    define_symbol = create_symbol_from_c_code("#define ZOPFLI_MAX_MATCH 258", "ZOPFLI_MAX_MATCH")
    result = transpile_const(define_symbol)
    assert result == "pub const ZOPFLI_MAX_MATCH: u32 = 258;"
    
    # Test boolean define
    bool_symbol = create_symbol_from_c_code("#define ZOPFLI_HASH_SAME 1", "ZOPFLI_HASH_SAME")
    result = transpile_const(bool_symbol)
    assert result == "pub const ZOPFLI_HASH_SAME: u32 = 1;"
    
    # Test float define
    float_symbol = create_symbol_from_c_code("#define ZOPFLI_LARGE_FLOAT 1e30", "ZOPFLI_LARGE_FLOAT")
    result = transpile_const(float_symbol)
    assert result == "pub const ZOPFLI_LARGE_FLOAT: f64 = 1e30;"


if __name__ == "__main__":
    pytest.main([__file__])
