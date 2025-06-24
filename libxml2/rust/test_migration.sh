#!/bin/bash
set -e

echo "Testing libxml2 chimera build configurations..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run test with error handling
run_test() {
    local test_name="$1"
    local command="$2"
    
    echo -e "${YELLOW}Testing $test_name...${NC}"
    if eval "$command"; then
        echo -e "${GREEN}✓ $test_name passed${NC}"
    else
        echo -e "${RED}✗ $test_name failed${NC}"
        exit 1
    fi
    echo
}

# Test pure C build
run_test "pure C build" "cargo clean && cargo build"

# Test individual Rust modules
MODULES=(
    "xmlstring" "chvalid" "dict" "hash" "list" "buf" "xmlmemory" "error" 
    "threads" "encoding" "xmlio" "uri" "entities" "tree" "xmlsave"
    "parser-internals" "parser" "sax2" "xpath" "pattern" "xpointer" 
    "valid" "xmlregexp" "xmlschemas" "relaxng" "schematron" 
    "htmlparser" "htmltree" "xmlreader" "xmlwriter" "c14n"
)

for module in "${MODULES[@]}"; do
    run_test "rust-$module feature" "cargo clean && cargo build --features rust-$module"
done

# Test environment variable approach
for module in xmlstring dict chvalid; do
    run_test "RUST_MODULES=$module" "cargo clean && RUST_MODULES=$module cargo build"
done

# Test multiple modules via environment
run_test "RUST_MODULES=xmlstring,dict,chvalid" "cargo clean && RUST_MODULES=xmlstring,dict,chvalid cargo build"

# Test all Rust
run_test "all Rust modules" "cargo clean && cargo build --all-features"

# Test basic functionality
run_test "unit tests (pure C)" "cargo clean && cargo test"
run_test "unit tests (with rust-xmlstring)" "cargo clean && cargo test --features rust-xmlstring"
run_test "unit tests (all Rust)" "cargo clean && cargo test --all-features"

# Test that fuzz targets compile (but don't run them)
echo -e "${YELLOW}Testing fuzz target compilation...${NC}"
if command -v cargo-fuzz >/dev/null 2>&1; then
    run_test "fuzz target compilation" "cargo fuzz build fuzz_xmlstring"
else
    echo -e "${YELLOW}cargo-fuzz not available, skipping fuzz compilation test${NC}"
fi

# Verify critical invariants
echo -e "${YELLOW}Verifying build artifacts...${NC}"

# Check that wrapper.h is generated
run_test "wrapper.h generation" "cargo clean && cargo build && test -f wrapper.h"

# Check that bindings are generated  
run_test "bindings generation" "cargo clean && cargo build && test -f target/debug/build/*/out/bindings.rs"

# Test symbol visibility with different configurations
if command -v nm >/dev/null 2>&1; then
    echo -e "${YELLOW}Checking symbol visibility...${NC}"
    
    # Build pure C version
    cargo clean && cargo build
    if [ -f target/debug/liblibxml2.a ]; then
        echo "Pure C build symbols sample:"
        nm target/debug/liblibxml2.a | grep -E "(xmlStr|xmlDict)" | head -5 || true
    fi
    
    # Build with rust-dict
    cargo clean && cargo build --features rust-dict
    if [ -f target/debug/liblibxml2.a ]; then
        echo "With rust-dict symbols sample:"
        nm target/debug/liblibxml2.a | grep -E "(xmlStr|xmlDict)" | head -5 || true
    fi
else
    echo -e "${YELLOW}nm not available, skipping symbol visibility test${NC}"
fi

echo -e "${GREEN}All chimera build configurations tested successfully!${NC}"
echo
echo "Summary:"
echo "- Pure C build: ✓"
echo "- Individual Rust modules: ✓ (${#MODULES[@]} modules)"
echo "- Environment variable control: ✓"
echo "- All Rust build: ✓" 
echo "- Unit tests: ✓"
echo "- Build artifacts: ✓"
echo
echo "The chimera build system is ready for incremental C-to-Rust migration!"