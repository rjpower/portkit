#!/usr/bin/env python3

import tempfile
from pathlib import Path

import pytest

from portkit.config import ProjectConfig
from portkit.sourcemap import SourceMap


@pytest.fixture
def temp_project():
    """Create a temporary project structure for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)

        # Create C source structure
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True)

        # Create Rust structure
        rust_src_dir = project_root / "rust" / "src"
        rust_fuzz_dir = project_root / "rust" / "fuzz" / "fuzz_targets"
        rust_src_dir.mkdir(parents=True)
        rust_fuzz_dir.mkdir(parents=True)

        yield project_root


class TestStructExtraction:
    """Test struct extraction patterns."""

    def test_regular_struct_extraction(self, temp_project):
        """Test extracting regular struct definitions."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
struct ZopfliLZ77Store {
    unsigned short* litlens;
    unsigned short* dists;
    size_t size;
};
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        struct_symbols = [
            s for s in symbols if s.name == "ZopfliLZ77Store" and s.kind == "struct"
        ]
        assert len(struct_symbols) == 1

        symbol = struct_symbols[0]
        assert symbol.language == "c"
        # Structs in header files have declaration_file set, not definition_file
        assert symbol.declaration_file.name == "test.h"
        assert "ZopfliLZ77Store" in symbol.signature


    def test_struct_with_dependencies(self, temp_project):
        """Test struct with type dependencies."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
typedef struct Node Node;

struct Tree {
    Node* root;
    size_t count;
};
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        tree_symbols = [s for s in symbols if s.name == "Tree" and s.kind == "struct"]
        assert len(tree_symbols) == 1

        symbol = tree_symbols[0]
        assert "Node" in symbol.type_dependencies


class TestFunctionExtraction:
    """Test function extraction patterns."""

    def test_function_definition(self, temp_project):
        """Test extracting function definitions."""
        c_file = temp_project / "src" / "test.c"
        c_file.write_text(
            """
int ZopfliVerifyLenDist(const unsigned char* data, size_t datasize,
                        size_t pos, unsigned dist, unsigned length) {
    if (pos + length > datasize) {
        return 0;
    }
    
    // Add more lines to exceed the 10-line threshold
    int check = 1;
    for (size_t i = 0; i < length; i++) {
        if (data[pos + i] != data[pos + i - dist]) {
            check = 0;
            break;
        }
    }
    
    return check;
}
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        func_symbols = [
            s
            for s in symbols
            if s.name == "ZopfliVerifyLenDist" and s.kind == "function"
        ]
        assert len(func_symbols) == 1

        symbol = func_symbols[0]
        assert symbol.language == "c"
        assert symbol.definition_file.name == "test.c"
        assert not symbol.is_static

    def test_function_declaration(self, temp_project):
        """Test extracting function declarations."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
int ZopfliVerifyLenDist(const unsigned char* data, size_t datasize,
                        size_t pos, unsigned dist, unsigned length);

void ZopfliInitCache(ZopfliLongestMatchCache* lmc);
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        func_symbols = [
            s for s in symbols if s.kind == "function" and s.language == "c"
        ]
        func_names = {s.name for s in func_symbols}

        assert "ZopfliVerifyLenDist" in func_names
        assert "ZopfliInitCache" in func_names

    def test_static_function(self, temp_project):
        """Test extracting static functions."""
        c_file = temp_project / "src" / "test.c"
        c_file.write_text(
            """
static int helper_function(int x) {
    return x * 2;
}

int public_function(int x) {
    return helper_function(x);
}
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        source_map.parse_project()

        # Static functions should be parsed but excluded from topological order
        all_func_symbols = []
        for (_name, lang), symbol in source_map.symbols.items():
            if symbol.kind == "function" and lang == "c":
                all_func_symbols.append(symbol)

        static_funcs = [s for s in all_func_symbols if s.is_static]
        public_funcs = [s for s in all_func_symbols if not s.is_static]

        assert len(static_funcs) == 1
        assert static_funcs[0].name == "helper_function"

        assert len(public_funcs) == 1
        assert public_funcs[0].name == "public_function"


class TestEnumExtraction:
    """Test enum extraction patterns."""

    def test_regular_enum(self, temp_project):
        """Test extracting regular enum definitions."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
enum ZopfliFormat {
    ZOPFLI_FORMAT_GZIP,
    ZOPFLI_FORMAT_ZLIB,
    ZOPFLI_FORMAT_DEFLATE
};
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        enum_symbols = [
            s for s in symbols if s.name == "ZopfliFormat" and s.kind == "enum"
        ]
        assert len(enum_symbols) == 1

        symbol = enum_symbols[0]
        assert symbol.language == "c"
        assert "ZopfliFormat" in symbol.signature


class TestTypedefExtraction:
    """Test typedef extraction patterns."""

    def test_simple_typedef(self, temp_project):
        """Test extracting simple typedef declarations."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
typedef unsigned char ZopfliBlockType;
typedef int (*CompareFunc)(const void* a, const void* b);
typedef struct _Point {
    int x;
    int y;
} Point;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()
        symbol_names = {s.name for s in symbols}

        assert "CompareFunc" not in symbol_names
        assert "ZopfliBlockType" not in symbol_names
        assert "_Point" in symbol_names

    def test_typedef_with_dependencies(self, temp_project):
        """Test typedef with type dependencies."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
struct Node;
typedef struct Node* NodePtr;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        typedef_symbols = [s for s in symbols if s.name == "NodePtr"]
        if typedef_symbols:
            symbol = typedef_symbols[0]
            assert "Node" in symbol.type_dependencies


class TestDependencyOrdering:
    """Test dependency ordering functionality."""

    def test_basic_dependency_order(self, temp_project):
        """Test that dependencies appear before dependent symbols."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
typedef struct Node {
    int value;
} Node;

typedef struct Tree {
    Node* root;
} Tree;

void process_tree(Tree* tree);
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        # Get the order of symbols
        symbol_names = [s.name for s in symbols]

        # Node should appear before Tree
        if "Node" in symbol_names and "Tree" in symbol_names:
            node_pos = symbol_names.index("Node")
            tree_pos = symbol_names.index("Tree")
            assert node_pos < tree_pos

        # Tree should appear before process_tree
        if "Tree" in symbol_names and "process_tree" in symbol_names:
            tree_pos = symbol_names.index("Tree")
            func_pos = symbol_names.index("process_tree")
            assert tree_pos < func_pos

    def test_function_dependency_order(self, temp_project):
        """Test function call dependencies."""
        c_file = temp_project / "src" / "test.c"
        c_file.write_text(
            """
int helper(int x) {
    return x * 2;
}

int main_func(int x) {
    return helper(x) + 1;
}
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        # Check call dependencies are detected
        main_func_symbols = [s for s in symbols if s.name == "main_func"]
        if main_func_symbols:
            # Should detect call to helper function
            assert "helper" in source_map.call_graph.get("main_func", set())


class TestZopfliSpecificIssues:
    """Test specific issues mentioned in the requirements."""

    def test_zopfli_has_builtin_clz_filtered(self, temp_project):
        """Test that ZOPFLI_HAS_BUILTIN_CLZ is filtered out."""
        h_file = temp_project / "src" / "zopfli.h"
        h_file.write_text(
            """
#define ZOPFLI_HAS_BUILTIN_CLZ
#define ZOPFLI_VERSION "1.0.0"
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}
        assert "ZOPFLI_HAS_BUILTIN_CLZ" not in symbol_names
        assert "ZOPFLI_VERSION" in symbol_names

    def test_zopfli_lz77_store_found(self, temp_project):
        """Test that ZopfliLZ77Store shows up as a symbol."""
        h_file = temp_project / "src" / "zopfli.h"
        h_file.write_text(
            """
typedef struct ZopfliLZ77Store {
    unsigned short* litlens;
    unsigned short* dists;
    size_t size;
} ZopfliLZ77Store;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}
        assert "ZopfliLZ77Store" in symbol_names

        # Verify it's parsed as a struct
        store_symbols = [s for s in symbols if s.name == "ZopfliLZ77Store"]
        assert len(store_symbols) == 1
        assert store_symbols[0].kind == "struct"


class TestTypedefUnification:
    """Test typedef unification and filtering patterns."""

    def test_simple_typedef_filtering(self, temp_project):
        """Test filtering of simple pointer typedefs."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
typedef xmlXIncludeDoc *xmlXIncludeDocPtr;  // Should be filtered
typedef xmlChar *xmlCharPtr;                // Should be filtered  
typedef int MyInt;                          // Should be filtered
typedef struct MyStruct MyStruct;           // Forward decl - should be filtered
typedef struct {
    int x;
    int y;
} Point;                                    // Should be kept - has body
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}

        # Simple typedefs should be filtered out
        assert "xmlXIncludeDocPtr" not in symbol_names
        assert "xmlCharPtr" not in symbol_names
        assert "MyInt" not in symbol_names
        assert "MyStruct" not in symbol_names

        # Typedef with body should be kept
        assert "Point" in symbol_names

    def test_struct_typedef_unification(self, temp_project):
        """Test unification of struct definitions with their typedefs."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
struct _xmlXIncludeRef {
    xmlChar *URI;
    xmlChar *fragment; 
    xmlChar *base;
    xmlNodePtr elem;
    xmlNodePtr inc;
    int xml;
    int fallback;
    int expanding;
    int replace;
};

typedef struct _xmlXIncludeRef xmlXIncludeDoc;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}

        # Should result in single symbol named "xmlXIncludeDoc" (typedef name preferred)
        assert "xmlXIncludeDoc" in symbol_names
        assert (
            "_xmlXIncludeRef" not in symbol_names
        )  # Internal struct name should be unified away

        # Verify the unified symbol has struct body info
        unified_symbols = [s for s in symbols if s.name == "xmlXIncludeDoc"]
        assert len(unified_symbols) == 1
        assert unified_symbols[0].kind == "struct"
        assert (
            "xmlChar" in unified_symbols[0].signature
            or "URI" in unified_symbols[0].signature
        )

    def test_typedef_struct_same_name(self, temp_project):
        """Test typedef struct with same name as struct."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
typedef struct xmlXIncludeRef {
    xmlChar *URI;
    xmlChar *fragment;
} xmlXIncludeRef;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}

        # Should result in single symbol named "xmlXIncludeRef"
        assert "xmlXIncludeRef" in symbol_names
        ref_symbols = [s for s in symbols if s.name == "xmlXIncludeRef"]
        assert len(ref_symbols) == 1
        assert ref_symbols[0].kind == "struct"

    def test_mixed_struct_typedef_patterns(self, temp_project):
        """Test complex mix of struct and typedef patterns."""
        h_file = temp_project / "src" / "test.h"
        h_file.write_text(
            """
// Forward declaration - should be filtered
typedef struct _Node Node;

// Struct definition  
struct _Node {
    int value;
    Node *next;  // Uses typedef
};

// Simple pointer typedef (should be filtered)
typedef Node *NodePtr;

// Struct with same name as typedef
typedef struct Tree {
    Node *root;
} Tree;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}

        # Forward declaration should be filtered
        forward_decl_count = len([s for s in symbols if s.name == "Node"])
        # Should have unified struct _Node with typedef Node
        assert "Node" in symbol_names
        assert forward_decl_count <= 1  # Should be unified, not duplicated

        # Simple pointer typedef should be filtered
        assert "NodePtr" not in symbol_names

        # Typedef struct with body should be kept
        assert "Tree" in symbol_names

    def test_xmlinclude_real_patterns(self, temp_project):
        """Test with actual xmlInclude-style patterns from the requirements."""
        h_file = temp_project / "src" / "xinclude.h"
        h_file.write_text(
            """
struct _xmlXIncludeRef {
    xmlChar              *URI; /* the fully resolved resource URL */
    xmlChar         *fragment; /* the fragment in the URI */
    xmlChar             *base; /* base URI of xi:include element */
    xmlNodePtr           elem; /* the xi:include element */
    xmlNodePtr            inc; /* the included copy */
    int                   xml; /* xml or txt */
    int                 fallback; /* fallback was loaded */
    int            expanding; /* flag to detect inclusion loops */
    int              replace; /* should the node be replaced? */
};

typedef struct _xmlXIncludeDoc xmlXIncludeDoc;
typedef xmlXIncludeDoc *xmlXIncludeDocPtr;
"""
        )

        config = ProjectConfig(
            project_name="test", library_name="test", project_root=temp_project
        )
        source_map = SourceMap(temp_project, config)
        symbols = source_map.parse_project()

        symbol_names = {s.name for s in symbols}

        # The struct definition should be kept (no typedef to unify with)
        assert "_xmlXIncludeRef" in symbol_names

        # Forward declaration should be filtered (no struct body)
        assert "xmlXIncludeDoc" not in symbol_names

        # Simple pointer typedef should be filtered
        assert "xmlXIncludeDocPtr" not in symbol_names


class TestRealZopfliProject:
    """Test with the real zopfli-port project to validate dependency ordering."""

    def test_zopfli_dependency_ordering(self):
        """Test dependency ordering with the real zopfli-port project."""
        # Use the actual zopfli-port project
        zopfli_path = Path("/Users/power/code/portkit/zopfli-port")
        if not zopfli_path.exists():
            pytest.skip("zopfli-port project not available")

        config = ProjectConfig(
            project_name="zopfli", library_name="zopfli", project_root=zopfli_path
        )
        source_map = SourceMap(zopfli_path, config)
        symbols = source_map.parse_project()

        print(f"\nFound {len(symbols)} symbols in zopfli-port")

        # Test 1: ZOPFLI_HAS_BUILTIN_CLZ should be filtered out (empty define)
        symbol_names = {s.name for s in symbols}
        assert (
            "ZOPFLI_HAS_BUILTIN_CLZ" not in symbol_names
        ), "ZOPFLI_HAS_BUILTIN_CLZ should be filtered out as empty define"

        # Test 2: ZopfliLZ77Store should show up as a symbol
        assert (
            "ZopfliLZ77Store" in symbol_names
        ), "ZopfliLZ77Store should be extracted as a struct symbol"
        store_symbols = [s for s in symbols if s.name == "ZopfliLZ77Store"]
        assert len(store_symbols) == 1
        assert store_symbols[0].kind == "struct"

        # Test 3: Check that CalculateBlockSymbolSizeSmall appears in symbol list
        assert (
            "CalculateBlockSymbolSizeSmall" in symbol_names
        ), "CalculateBlockSymbolSizeSmall should be extracted"

        # Test 4: Validate dependency ordering - symbols should appear before their dependents
        symbol_order = [s.name for s in symbols]
        print(f"\nSymbol order (first 20): {symbol_order[:20]}")

        # Find dependencies of CalculateBlockSymbolSizeSmall
        calc_symbols = [s for s in symbols if s.name == "CalculateBlockSymbolSizeSmall"]
        if calc_symbols:
            calc_symbol = calc_symbols[0]
            print(
                f"\nCalculateBlockSymbolSizeSmall dependencies: {calc_symbol.all_dependencies}"
            )

            # Check that each dependency appears before CalculateBlockSymbolSizeSmall in the order
            calc_position = symbol_order.index("CalculateBlockSymbolSizeSmall")

            for dep_name in calc_symbol.all_dependencies:
                if (
                    dep_name in symbol_names
                ):  # Only check deps that are actually symbols
                    dep_position = symbol_order.index(dep_name)
                    assert (
                        dep_position < calc_position
                    ), f"Dependency '{dep_name}' (pos {dep_position}) should appear before 'CalculateBlockSymbolSizeSmall' (pos {calc_position})"

        # Test 5: Check specific expected dependencies are in the symbol list
        expected_deps = {
            "ZopfliLZ77Store",  # struct used as parameter
            "ZopfliGetLengthSymbol",  # function called
            "ZopfliGetDistSymbol",  # function called
            "ZopfliGetLengthSymbolExtraBits",  # function called
            "ZopfliGetDistSymbolExtraBits",  # function called
        }

        missing_deps = expected_deps - symbol_names
        print(f"\nExpected dependencies: {expected_deps}")
        print(f"Missing dependencies: {missing_deps}")
        print(
            f"Available symbols containing 'Zopfli': {sorted([s for s in symbol_names if 'Zopfli' in s])}"
        )

        # Test 6: Check if static inline functions are parsed but excluded from topological sort
        print("\nChecking internal symbol storage for static functions:")
        for (name, lang), symbol in source_map.symbols.items():
            if "GetLengthSymbol" in name or "GetDistSymbol" in name:
                print(f"  {name} ({symbol.kind}, {lang}, static={symbol.is_static})")

        # Count static vs non-static symbols
        static_symbols = [
            (name, symbol)
            for (name, lang), symbol in source_map.symbols.items()
            if lang == "c" and symbol.is_static
        ]
        non_static_symbols = [
            (name, symbol)
            for (name, lang), symbol in source_map.symbols.items()
            if lang == "c" and not symbol.is_static
        ]

        print(
            f"\nSymbol counts: {len(static_symbols)} static, {len(non_static_symbols)} non-static"
        )
        print(f"Static symbol examples: {[name for name, _ in static_symbols[:10]]}")

        # The core issue: static inline functions are dependencies but excluded from ordering
        assert (
            len(static_symbols) > 0
        ), "Should find some static symbols in internal storage"
