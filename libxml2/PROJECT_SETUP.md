# Chimera Build System - Initial Project Setup

Create the foundational Rust project structure and build system for incremental C-to-Rust migration.

## Overview

The chimera build system allows a C project to be incrementally migrated to Rust by:
1. Building a mixed C/Rust library where modules can be swapped at compile time
2. Using bindgen to generate FFI bindings for the C portions
3. Allowing Rust implementations to override C symbols when enabled
4. Supporting differential testing between C and Rust implementations

The system works by:
- Compiling only the C modules that aren't being replaced by Rust
- Generating bindings only for the active C code
- Using Cargo features to control which Rust modules are compiled
- Using environment variables for runtime module selection

## Goal & Expected Output

You will produce a _stub project_ which contains the basic build setup for a Chimera project.
You will generate _empty_ implementations for each module & test, just sufficient to ensure the project builds.

## Input Project Structure

Project name: libxml2

<file name="sourcemap.txt">

## File Statistics
file,lines,functions
HTMLparser.c,6030,39
HTMLtree.c,1314,18
SAX2.c,2819,34
buf.c,1156,37
c14n.c,2171,4
catalog.c,3634,33
chvalid.c,174,9
debugXML.c,1529,11
dict.c,1026,19
encoding.c,3002,27
entities.c,719,11
error.c,1409,16
example/testWriter.c,1068,4
example/xpath1.c,243,3
fuzz/fuzz.c,603,20
fuzz/testFuzzer.c,324,1
fuzz/xml.c,263,3
globals.c,1130,20
hash.c,1297,23
include/libxml/HTMLparser.h,393,0
include/libxml/chvalid.h,218,0
include/libxml/encoding.h,339,0
include/libxml/entities.h,167,0
include/libxml/parser.h,2114,0
include/libxml/schemasInternals.h,792,0
include/libxml/tree.h,1545,0
include/libxml/uri.h,104,0
include/libxml/valid.h,456,0
include/libxml/xlink.h,197,0
include/libxml/xmlIO.h,392,0
include/libxml/xmlerror.h,1036,0
include/libxml/xpath.h,569,0
include/private/parser.h,158,0
include/private/threads.h,61,0
list.c,710,23
nanohttp.c,305,14
parser.c,13692,105
parserInternals.c,3483,72
pattern.c,2359,15
python/libxml.c,3679,17
python/libxml_wrap.h,317,0
python/types.c,895,34
relaxng.c,10614,25
runtest.c,5457,0
schematron.c,1990,10
shell.c,1590,1
testparser.c,1448,1
threads.c,504,18
timsort.h,603,2
tree.c,8914,107
uri.c,2777,14
valid.c,6559,67
xinclude.c,2190,14
xlink.c,165,4
xmlIO.c,2958,45
xmllint.c,3285,1
xmlmemory.c,516,19
xmlmodule.c,295,4
xmlreader.c,5407,85
xmlregexp.c,6331,25
xmlsave.c,2681,33
xmlschemas.c,28480,34
xmlschemastypes.c,6106,28
xmlstring.c,1137,30
xmlwriter.c,4553,80
xpath.c,12081,145
xpointer.c,666,2
xzlib.c,821,5

</file>
<file name="00001-xmlstring.yaml">
module:
  name: xmlstring
  description: "String manipulation utilities for xmlChar* and UTF-8 handling"
  estimated_loc: 1137
  c_files:
    - xmlstring.c
  header_files:
    - include/libxml/xmlstring.h
  key_functions:
    - xmlStrndup
    - xmlStrdup  
    - xmlStrcmp
    - xmlStrEqual
    - xmlStrlen
    - xmlStrcat
    - xmlUTF8Strlen
    - xmlCheckUTF8
    - xmlGetUTF8Char
    - xmlStrASPrintf
  dependencies: []
  api_overview: |
    Provides fundamental string manipulation utilities specifically designed for libxml2's 
    xmlChar* type and UTF-8 encoding. This is a foundational module with no dependencies 
    on other libxml2 modules. Functions handle string duplication, comparison, concatenation,
    UTF-8 validation and character extraction, and formatted string creation.
    
    Implementation notes:
    - Uses libxml2 memory management (xmlMalloc/xmlFree)
    - All functions operate on xmlChar* (unsigned char*)
    - Includes comprehensive UTF-8 support
    - Can be implemented as pure Rust with UTF-8 string handling
</file>

<file name="00002-chvalid.yaml">
module:
  name: chvalid
  description: "Character validation for Unicode code points using range tables"
  estimated_loc: 174
  c_files:
    - chvalid.c
  header_files:
    - include/libxml/chvalid.h
  key_functions:
    - xmlCharInRange
    - xmlIsBaseChar
    - xmlIsBlank
    - xmlIsChar
    - xmlIsCombining
    - xmlIsDigit
    - xmlIsExtender
    - xmlIsIdeographic
    - xmlIsPubidChar
  dependencies: []
  api_overview: |
    Provides character validation services for Unicode code points using binary search
    over predefined character range tables. The module validates whether characters
    belong to specific Unicode categories needed for XML processing.
    
    Key structures:
    - xmlChRangeGroup: Container for character ranges
    - xmlChSRange: Short ranges (up to 0xFFFF)
    - xmlChLRange: Long ranges (0x10000+)
    
    Implementation notes:
    - Uses binary search for efficient range lookup
    - Supports both short and long Unicode ranges
    - Most functions are deprecated wrappers for *Q variants
    - Range data likely comes from Unicode tables
    - Can be implemented in Rust using Unicode range tables
</file>

<file name="00003-dict.yaml">
module:
  name: dict
  description: "String dictionary/interning service with hash table and memory pools"
  estimated_loc: 1026
  c_files:
    - dict.c
  header_files:
    - include/libxml/dict.h
    - include/private/dict.h
  key_functions:
    - xmlDictCreate
    - xmlDictCreateSub
    - xmlDictFree
    - xmlDictReference
    - xmlDictLookup
    - xmlDictExists
    - xmlDictQLookup
    - xmlDictOwns
    - xmlDictSize
    - xmlDictSetLimit
    - xmlDictGetUsage
    - xmlInitRandom
    - xmlCleanupRandom
    - xmlGlobalRandom
    - xmlRandom
  dependencies:
    - xmlstring
  api_overview: |
    Implements string interning (dictionary) services for libxml2 to optimize memory
    usage and enable fast pointer-based string comparisons. Uses hash tables with
    linked memory pools for string storage and supports hierarchical dictionaries.
    
    Key structures:
    - _xmlDict: Main dictionary with hash table, memory pools, reference counting
    - _xmlDictStrings: Memory pool for string storage
    - xmlHashedString: Hash table entry with string pointer and hash value
    
    Features:
    - Reference counting for shared dictionaries
    - Memory usage limits and tracking
    - Hierarchical dictionaries (sub-dictionaries)
    - QName (qualified name) support
    - Thread-safe PRNG for hash randomization
    
    Implementation notes:
    - Uses custom hash function with randomization
    - Memory pools for contiguous string allocation
    - Can be implemented in Rust using HashMap for interning
    - PRNG functionality can use Rust's rand crate
</file>

<file name="00004-hash.yaml">
module:
  name: hash
  description: "Generic hash table implementation with string keys and void* payloads"
  estimated_loc: 1297
  c_files:
    - hash.c
  header_files:
    - include/libxml/hash.h
  key_functions:
    - xmlHashCreate
    - xmlHashCreateDict
    - xmlHashFree
    - xmlHashAdd3
    - xmlHashUpdateEntry3
    - xmlHashLookup3
    - xmlHashQLookup3
    - xmlHashRemoveEntry3
    - xmlHashScanFull
    - xmlHashCopySafe
    - xmlHashSize
  dependencies:
    - dict
    - xmlstring
  api_overview: |
    Provides a generic hash table implementation using open addressing with Robin Hood
    hashing for collision resolution. Supports up to three string components as
    composite keys and stores arbitrary void* payloads.
    
    Key structures:
    - xmlHashEntry: Hash table entry with hash value, keys, and payload
    - _xmlHashTable: Hash table with storage array, dictionary integration, and metadata
    
    Features:
    - Composite keys (up to 3 string components)
    - QName (qualified name) support
    - Optional dictionary integration for key interning
    - Robin Hood hashing for even distribution
    - Configurable deallocator functions
    - Iterator/scanner support
    - Deep copy functionality
    
    Implementation notes:
    - Uses open addressing with linear probing
    - Power-of-two sizing for efficient modulo operations
    - Random seed for hash function security
    - Can be implemented in Rust using HashMap or custom hash table
    - Dictionary integration allows for memory-efficient key storage
</file>

<file name="00005-list.yaml">
module:
  name: list
  description: "Generic doubly-linked list implementation with custom comparator/deallocator support"
  estimated_loc: 710
  c_files:
    - list.c
  header_files:
    - include/libxml/list.h
  key_functions:
    - xmlListCreate
    - xmlListDelete
    - xmlListSearch
    - xmlListInsert
    - xmlListAppend
    - xmlListRemoveFirst
    - xmlListRemoveAll
    - xmlListClear
    - xmlListEmpty
    - xmlListSize
    - xmlListPushFront
    - xmlListPushBack
    - xmlListWalk
    - xmlListDup
  dependencies: []
  api_overview: |
    Implements a generic doubly-linked list data structure for managing collections
    of arbitrary data pointers. Supports custom data deallocators and comparators
    for flexible data handling.
    
    Key structures:
    - _xmlLink: Individual list node with prev/next pointers and data
    - _xmlList: List container with sentinel node and function pointers
    
    Features:
    - Circular doubly-linked list with sentinel node
    - Custom deallocator function support
    - Custom comparison function for ordering
    - Ordered insertion and appending
    - Search and removal operations
    - Iterator/walker support
    - Shallow duplication
    
    Implementation notes:
    - Uses sentinel node to simplify boundary conditions
    - Function pointers for custom data handling
    - Memory management through libxml2 allocator
    - Can be implemented in Rust using Vec<T> or custom linked list
    - Generic over data type with trait-based comparison/cleanup
</file>

<file name="00006-buf.yaml">
module:
  name: buf
  description: "Dynamic buffer management for strings with modern xmlBuf and legacy xmlBuffer APIs"
  estimated_loc: 1156
  c_files:
    - buf.c
  header_files:
    - include/libxml/tree.h
    - include/private/buf.h
  key_functions:
    - xmlBufCreate
    - xmlBufCreateMem
    - xmlBufFree
    - xmlBufEmpty
    - xmlBufGrow
    - xmlBufAdd
    - xmlBufCat
    - xmlBufContent
    - xmlBufUse
    - xmlBufAvail
    - xmlBufDetach
    - xmlBufferCreate
    - xmlBufferFree
    - xmlBufferAdd
    - xmlBufferCat
  dependencies:
    - xmlstring
  api_overview: |
    Provides dynamic buffer management for string data with both modern (xmlBuf) 
    and legacy (xmlBuffer) APIs. Handles memory allocation, growth, and efficient
    string building operations.
    
    Key structures:
    - _xmlBuf: Modern opaque buffer with 64-bit support and improved memory control
    - _xmlBuffer: Legacy buffer structure for backward compatibility
    
    Features:
    - Dynamic buffer growth with configurable limits
    - Static buffer support (read-only)
    - Memory usage tracking and limits
    - Integration with parser input streams
    - Backward compatibility with xmlBuffer API
    - 64-bit size support in modern API
    
    Implementation notes:
    - Modern xmlBuf API preferred for new code
    - Legacy xmlBuffer maintained for compatibility
    - Memory management through libxml2 allocator
    - Efficient reallocation strategies
    - Can be implemented in Rust using Vec<u8> or String
    - Size limits and error handling important for security
</file>

<file name="00007-xmlmemory.yaml">
module:
  name: xmlmemory
  description: "Memory allocator wrapper with debugging and integrity checking"
  estimated_loc: 516
  c_files:
    - xmlmemory.c
  header_files:
    - include/libxml/xmlmemory.h
    - include/private/memory.h
  key_functions:
    - xmlMemMalloc
    - xmlMemRealloc
    - xmlMemFree
    - xmlMemoryStrdup
    - xmlMemSize
    - xmlMemUsed
    - xmlMemBlocks
    - xmlMemSetup
    - xmlMemGet
    - xmlInitMemoryInternal
    - xmlCleanupMemoryInternal
  dependencies: []
  api_overview: |
    Provides libxml2's internal memory allocator wrapper with debugging capabilities.
    Wraps standard C memory functions (malloc, realloc, free, strdup) with custom
    headers for integrity checking and usage tracking.
    
    Key structures:
    - MEMHDR: Memory block header with magic tag and size for integrity checking
    
    Features:
    - Memory integrity checking with magic numbers
    - Memory usage statistics (total size, block count)
    - Custom allocator override support
    - Thread-safe statistics tracking
    - Zero-fill on free for security
    - Double-free detection
    
    Implementation notes:
    - All allocations include MEMHDR prefix
    - Statistics protected by mutex
    - Can be customized with xmlMemSetup()
    - In Rust: use global allocator or custom allocator trait
    - Debug features can use Rust's debugging allocators
</file>

<file name="00008-error.yaml">
module:
  name: error
  description: "Error reporting and management system with structured error handling"
  estimated_loc: 1409
  c_files:
    - error.c
  header_files:
    - include/libxml/xmlerror.h
    - include/private/error.h
  key_functions:
    - xmlRaiseError
    - xmlFormatError
    - xmlGetLastError
    - xmlResetLastError
    - xmlResetError
    - xmlCopyError
    - xmlSetGenericErrorFunc
    - xmlSetStructuredErrorFunc
    - xmlIsCatastrophicError
    - xmlErrString
  dependencies:
    - xmlmemory
  api_overview: |
    Manages error reporting and handling throughout libxml2. Provides both generic
    (printf-style) and structured error reporting mechanisms with detailed error
    information including context, location, and severity.
    
    Key structures:
    - xmlError: Complete error information with domain, code, message, location
    
    Key enums:
    - xmlErrorLevel: Error severity (NONE, WARNING, ERROR, FATAL)
    - xmlParserErrors: Comprehensive error code enumeration
    
    Features:
    - Thread-local error storage
    - Structured and generic error handlers
    - Error formatting with context information
    - Catastrophic error detection
    - Custom error handler registration
    - Error history and reset capabilities
    
    Implementation notes:
    - Thread-local storage for last error
    - Callback-based error handling
    - Format string security considerations
    - In Rust: use Result<T, Error> types and custom error traits
    - Thread-local storage via thread_local! macro
</file>

<file name="00009-threads.yaml">
module:
  name: threads
  description: "Threading primitives and library initialization/cleanup"
  estimated_loc: 504
  c_files:
    - threads.c
  header_files:
    - include/libxml/threads.h
    - include/private/threads.h
  key_functions:
    - xmlNewMutex
    - xmlFreeMutex
    - xmlMutexLock
    - xmlMutexUnlock
    - xmlNewRMutex
    - xmlFreeRMutex
    - xmlRMutexLock
    - xmlRMutexUnlock
    - xmlLockLibrary
    - xmlUnlockLibrary
    - xmlInitParser
    - xmlCleanupParser
  dependencies:
    - xmlmemory
    - error
  api_overview: |
    Provides threading primitives for libxml2 and manages library-wide initialization
    and cleanup. Essential for thread-safe operation of the library.
    
    Key structures:
    - xmlMutex: Simple non-reentrant mutex wrapper
    - xmlRMutex: Reentrant mutex with lock counting
    
    Features:
    - Simple and reentrant mutex implementations
    - Global library lock for shared resources
    - Thread-safe library initialization (xmlInitParser)
    - Library cleanup (xmlCleanupParser)
    - Platform abstraction (POSIX/Win32)
    - One-time initialization guards
    
    Implementation notes:
    - Wraps platform-specific threading APIs
    - Global library state protection
    - Reentrant mutexes support lock counting
    - xmlInitParser is idempotent and thread-safe
    - In Rust: use std::sync::{Mutex, RwLock}, std::sync::Once for initialization
    - Consider parking_lot for better performance
</file>

<file name="00010-encoding.yaml">
module:
  name: encoding
  description: "Character encoding detection, parsing, and conversion"
  estimated_loc: 3002
  c_files:
    - encoding.c
  header_files:
    - include/libxml/encoding.h
    - include/private/enc.h
  key_functions:
    - xmlDetectCharEncoding
    - xmlParseCharEncoding
    - xmlGetCharEncodingName
    - xmlCreateCharEncodingHandler
    - xmlLookupCharEncodingHandler
    - xmlCharEncNewCustomHandler
    - xmlCharEncInFunc
    - xmlCharEncOutFunc
    - xmlCharEncCloseFunc
    - xmlByteConsumed
  dependencies:
    - xmlstring
    - chvalid
    - xmlmemory
    - error
    - buf
  api_overview: |
    Handles character encoding detection, parsing, and conversion for libxml2.
    Converts between various encodings and libxml2's internal UTF-8 representation.
    Supports built-in encodings and can integrate with iconv/ICU for broader support.
    
    Key structures:
    - xmlCharEncodingHandler: Encoding conversion handler with input/output functions
    
    Key enums:
    - xmlCharEncoding: Known character encodings (UTF-8, UTF-16, ISO-8859-1, etc.)
    - xmlCharEncError: Conversion error codes
    - xmlCharEncFlags: Conversion direction flags (input/output/HTML)
    
    Features:
    - Encoding detection from BOM and content analysis
    - Custom encoding handler registration
    - Built-in encodings (UTF-8, UTF-16, ASCII, ISO-8859-1)
    - External library integration (iconv, ICU)
    - HTML-specific encoding handling
    
    Implementation notes:
    - UTF-8 is internal representation
    - BOM detection for UTF-16/UTF-32
    - Case-insensitive encoding name parsing
    - In Rust: use encoding_rs crate for character encoding
    - UTF-8 validation and conversion can use std library
</file>

<file name="00011-xmlio.yaml">
module:
  name: xmlio
  description: "I/O abstraction layer with buffered input/output and compression support"
  estimated_loc: 2958
  c_files:
    - xmlIO.c
  header_files:
    - include/libxml/xmlIO.h
    - include/private/io.h
  key_functions:
    - xmlAllocParserInputBuffer
    - xmlFreeParserInputBuffer
    - xmlParserInputBufferCreateUrl
    - xmlNewInputBufferMemory
    - xmlAllocOutputBuffer
    - xmlOutputBufferClose
    - xmlOutputBufferCreateFilename
    - xmlOutputBufferCreateFile
    - xmlOutputBufferCreateBuffer
    - xmlEscapeText
    - xmlSerializeText
    - xmlRegisterInputCallbacks
    - xmlRegisterOutputCallbacks
  dependencies:
    - buf
    - encoding
    - xmlstring
    - xmlmemory
    - error
  api_overview: |
    Provides comprehensive I/O abstraction for libxml2, supporting files, memory,
    network, and compressed streams. Handles buffering, encoding conversion,
    and pluggable I/O callbacks for custom data sources.
    
    Key structures:
    - xmlParserInputBuffer: Buffered input with encoding conversion and decompression
    - xmlOutputBuffer: Buffered output with encoding conversion and compression
    - xmlInputCallback/xmlOutputCallback: Custom I/O handler registration
    
    Key enums:
    - xmlParserInputFlags: Input processing flags (compression, static buffers)
    - xmlParserErrors: I/O-specific error codes
    
    Features:
    - File, memory, and network I/O support
    - Gzip and LZMA compression/decompression
    - Character encoding conversion
    - Pluggable I/O callback system
    - URI/URL handling
    - Character escaping utilities
    - Buffered I/O for performance
    
    Implementation notes:
    - Callback-based architecture for extensibility
    - Automatic compression detection
    - Character escaping tables (generated)
    - In Rust: use std::io traits, flate2/xz2 for compression
    - async I/O support possible with tokio
</file>

<file name="00012-uri.yaml">
module:
  name: uri
  description: "URI parsing, manipulation, and normalization according to RFC 3986"
  estimated_loc: 2777
  c_files:
    - uri.c
  header_files:
    - include/libxml/uri.h
  key_functions:
    - xmlCreateURI
    - xmlFreeURI
    - xmlParseURI
    - xmlParseURISafe
    - xmlParseURIReference
    - xmlParseURIRaw
    - xmlSaveUri
    - xmlPrintURI
    - xmlBuildURI
    - xmlBuildURISafe
    - xmlNormalizeURIPath
    - xmlURIEscape
    - xmlURIEscapeStr
    - xmlURIUnescapeString
    - xmlCanonicPath
  dependencies:
    - xmlstring
    - xmlmemory
    - error
  api_overview: |
    Provides comprehensive URI parsing, manipulation, and normalization functionality
    according to RFC 3986. Handles absolute and relative URIs, path normalization,
    percent-encoding/decoding, and URI resolution.
    
    Key structures:
    - xmlURI: Parsed URI with components (scheme, authority, path, query, fragment)
    
    Features:
    - RFC 3986 compliant URI parsing
    - URI component extraction and manipulation
    - Relative URI resolution against base URIs
    - Path normalization (. and .. resolution)
    - Percent-encoding and unescaping
    - URI canonicalization
    - IPv6 address support
    - Error-safe parsing variants
    
    Implementation notes:
    - Comprehensive percent-encoding handling
    - Authority parsing (user, server, port)
    - Path normalization removes redundant segments
    - Handles both hierarchical and opaque URIs
    - In Rust: use url crate for RFC 3986 compliance
    - Consider percent-encoding crate for escaping utilities
</file>

<file name="00013-entities.yaml">
module:
  name: entities
  description: "XML entity management including predefined, general, and parameter entities"
  estimated_loc: 719
  c_files:
    - entities.c
  header_files:
    - include/libxml/entities.h
    - include/private/entities.h
  key_functions:
    - xmlAddEntity
    - xmlGetPredefinedEntity
    - xmlGetDocEntity
    - xmlGetParameterEntity
    - xmlGetDtdEntity
    - xmlFreeEntity
    - xmlNewEntity
    - xmlEncodeEntitiesReentrant
    - xmlFreeEntitiesTable
    - xmlDumpEntityDecl
    - xmlDumpEntitiesTable
  dependencies:
    - hash
    - dict
    - xmlstring
    - xmlmemory
    - error
  api_overview: |
    Manages XML entities including predefined entities (&lt;, &gt;, &amp;, &quot;, &apos;),
    general entities, and parameter entities. Handles both internal and external
    entity declarations and provides entity lookup and text escaping services.
    
    Key structures:
    - xmlEntity: Entity declaration with name, type, content, and external IDs
    
    Key enums:
    - xmlEntityType: Entity classification (internal/external, general/parameter, parsed/unparsed)
    
    Features:
    - Predefined XML entity support
    - General and parameter entity management
    - Internal and external entity declarations
    - Entity lookup in DTD subsets
    - Text encoding with entity substitution
    - Entity table management via hash tables
    - Memory management with dictionary interning
    
    Implementation notes:
    - Uses hash tables for efficient entity lookup
    - Dictionary interning for memory optimization
    - Supports both internal and external DTD subsets
    - Special handling for HTML entity encoding
    - In Rust: use HashMap for entity tables
    - Predefined entities can be constants
</file>

<file name="00014-tree.yaml">
module:
  name: tree
  description: "Core XML tree manipulation and document model implementation"
  estimated_loc: 8914
  c_files:
    - tree.c
    - timsort.h
  header_files:
    - include/libxml/tree.h
    - include/private/tree.h
  key_functions:
    - xmlNewDoc
    - xmlFreeDoc
    - xmlNewNode
    - xmlNewDocNode
    - xmlNewText
    - xmlNewComment
    - xmlNewCDataBlock
    - xmlFreeNode
    - xmlFreeNodeList
    - xmlAddChild
    - xmlAddSibling
    - xmlUnlinkNode
    - xmlReplaceNode
    - xmlCopyNode
    - xmlCopyNodeList
    - xmlNodeGetContent
    - xmlNodeSetContent
    - xmlGetProp
    - xmlSetProp
    - xmlUnsetProp
    - xmlHasProp
    - xmlNewNs
    - xmlSearchNs
    - xmlSearchNsByHref
    - xmlFreeNs
    - xmlReconciliateNs
    - xmlValidateNCName
    - xmlValidateQName
    - xmlValidateName
    - xmlSplitQName2
    - xmlSplitQName3
    - xmlBuildQName
    - xmlDocSetRootElement
    - xmlDocGetRootElement
    - xmlGetLineNo
    - xmlGetNodePath
    - xmlNodeIsText
    - xmlIsBlankNode
    - xmlTextMerge
    - xmlTextConcat
    - xmlSetTreeDoc
    - xmlSetListDoc
    - xmlDOMWrapNewCtxt
    - xmlDOMWrapFreeCtxt
    - xmlDOMWrapRemoveNode
    - xmlDOMWrapReconcileNamespaces
    - xmlDOMWrapCloneNode
    - xmlDOMWrapAdoptNode
  dependencies:
    - xmlstring
    - chvalid
    - dict
    - hash
    - buf
    - xmlmemory
    - error
    - entities
    - uri
  api_overview: |
    Implements the core XML document model with DOM-style tree manipulation.
    Provides the fundamental data structures (xmlDoc, xmlNode, xmlAttr, xmlNs)
    and operations for creating, modifying, and navigating XML documents.
    
    Key structures:
    - xmlDoc: Complete XML document with metadata and root element
    - xmlNode: Generic XML node (element, text, comment, CDATA, etc.)
    - xmlAttr: XML attribute with name, value, and namespace
    - xmlNs: XML namespace declaration
    - xmlDtd: Document Type Definition
    - xmlBuffer: Legacy buffer for string building
    - xmlDOMWrapCtxt: Context for DOM manipulation operations
    
    Key enums:
    - xmlElementType: Node types (element, text, comment, etc.)
    - xmlBufferAllocationScheme: Buffer allocation strategies (deprecated)
    
    Features:
    - Complete DOM tree implementation
    - Namespace handling and reconciliation
    - Attribute management
    - Node manipulation (add, remove, copy, move)
    - QName validation and splitting
    - Content extraction and modification
    - Tree walking and navigation
    - Node serialization
    - Memory management with callbacks
    - DOM wrapper operations for external integration
    
    Implementation notes:
    - Central to all libxml2 operations
    - Reference counted documents
    - Namespace-aware operations
    - Memory callbacks for custom allocation
    - Dict integration for string interning
    - Support for both XML and HTML trees
    - In Rust: define node enums and tree structures
    - Use Rc/RefCell for shared ownership or arena allocation
</file>

<file name="00015-xmlsave.yaml">
module:
  name: xmlsave
  description: "XML/HTML tree serialization with formatting and encoding support"
  estimated_loc: 2681
  c_files:
    - xmlsave.c
  header_files:
    - include/libxml/xmlsave.h
    - include/private/save.h
  key_functions:
    - xmlSaveToBuffer
    - xmlSaveToFd
    - xmlSaveToFilename
    - xmlSaveToIO
    - xmlSaveDoc
    - xmlSaveTree
    - xmlSaveFlush
    - xmlSaveClose
    - xmlSaveFinish
    - xmlSaveSetEscape
    - xmlSaveSetAttrEscape
    - xmlSaveSetIndentString
    - xmlDocDump
    - xmlDocDumpFormatMemory
    - xmlDocDumpMemory
    - xmlDocFormatDump
    - xmlElemDump
    - xmlNodeDump
    - xmlBufNodeDump
    - xmlSaveFile
    - xmlSaveFormatFile
    - xmlSaveFileEnc
    - xmlSaveFormatFileEnc
    - xmlAttrSerializeTxtContent
    - xmlNsListDumpOutput
    - xmlSaveNotationDecl
    - xmlSaveNotationTable
  dependencies:
    - tree
    - buf
    - xmlio
    - encoding
    - xmlstring
    - xmlmemory
    - error
  api_overview: |
    Provides comprehensive XML and HTML document serialization capabilities.
    Converts in-memory document trees to various output formats with encoding,
    formatting, and escaping support.
    
    Key structures:
    - _xmlSaveCtxt: Serialization context with encoding, formatting options, and output buffer
    
    Key enums:
    - XML_SAVE_OPTIONS: Serialization behavior flags (formatting, empty tags, DOCTYPE)
    
    Features:
    - Multiple output targets (file, buffer, FD, custom I/O)
    - Character encoding conversion
    - Pretty-printing with configurable indentation
    - XML, XHTML, and HTML serialization modes
    - Custom character escaping functions
    - Namespace handling and normalization
    - DTD and notation serialization
    - Streaming output support
    - Format preservation options
    
    Implementation notes:
    - Tree traversal for serialization
    - Configurable output formatting
    - Character escaping based on context
    - Namespace reconciliation during output
    - Support for both XML and HTML rules
    - In Rust: use serde or custom serialization traits
    - Consider quick-xml for streaming output
</file>

<file name="00016-parser-internals.yaml">
module:
  name: parser-internals
  description: "Core parser infrastructure including contexts, input management, and error handling"
  estimated_loc: 3483
  c_files:
    - parserInternals.c
  header_files:
    - include/libxml/parserInternals.h
    - include/private/parser.h
  key_functions:
    - xmlCheckVersion
    - xmlInitParserCtxt
    - xmlFreeParserCtxt
    - xmlCtxtSetErrorHandler
    - xmlCtxtGetLastError
    - xmlCtxtResetLastError
    - xmlCtxtGetStatus
    - xmlSwitchEncoding
    - xmlSwitchEncodingName
    - xmlSwitchToEncoding
    - xmlSetDeclaredEncoding
    - xmlGetActualEncoding
    - xmlFreeInputStream
    - xmlNewInputFromFile
    - xmlCtxtNewInputFromUrl
    - xmlCtxtNewInputFromMemory
    - xmlCtxtNewInputFromString
    - xmlCtxtNewInputFromFd
    - xmlCtxtNewInputFromIO
    - xmlParserGrow
    - xmlParserShrink
    - xmlParserCheckEOF
    - xmlNextChar
    - xmlCurrentChar
    - xmlStringCurrentChar
    - xmlCopyChar
    - xmlCopyCharMultiByte
    - xmlDetectEncoding
    - xmlIsLetter
    - xmlSubstituteEntitiesDefault
    - xmlPedanticParserDefault
    - xmlLineNumbersDefault
    - xmlKeepBlanksDefault
  dependencies:
    - tree
    - buf
    - xmlio
    - encoding
    - entities
    - xmlstring
    - chvalid
    - dict
    - xmlmemory
    - error
    - uri
  api_overview: |
    Provides the foundational infrastructure for XML and HTML parsing including
    parser context management, input stream handling, character processing,
    encoding management, and error reporting.
    
    Key structures:
    - xmlParserCtxt: Complete parser state and configuration
    - xmlParserInput: Input stream with position tracking
    - xmlParserInputBuffer: Buffered input with encoding conversion
    
    Key enums:
    - xmlParserErrors: Comprehensive parser error codes
    - xmlParserStatus: Document status flags (well-formed, valid, etc.)
    - xmlCharEncoding: Supported character encodings
    
    Features:
    - Parser context lifecycle management
    - Input stream creation from multiple sources
    - Character encoding detection and conversion
    - Position tracking (line/column numbers)
    - Structured error handling and reporting
    - Buffer management (grow/shrink operations)
    - Character processing utilities
    - Encoding switching during parsing
    - Resource limit enforcement
    
    Implementation notes:
    - Central to all parsing operations
    - Handles streaming input efficiently
    - Position tracking for error reporting
    - Character-by-character processing utilities
    - In Rust: use iterator patterns for character processing
    - Error handling through Result types
    - Stream processing with async support possible
</file>

<file name="00017-parser.yaml">
module:
  name: parser
  description: "Main XML parser implementation with SAX and DOM interfaces"
  estimated_loc: 13692
  c_files:
    - parser.c
  header_files:
    - include/libxml/parser.h
  key_functions:
    - xmlParseDocument
    - xmlParseElement
    - xmlParseContent
    - xmlParseAttribute
    - xmlParseStartTag
    - xmlParseEndTag
    - xmlParseCharData
    - xmlParseComment
    - xmlParsePI
    - xmlParseCDSect
    - xmlParseReference
    - xmlParseEntityRef
    - xmlParsePEReference
    - xmlParseDocTypeDecl
    - xmlParseElementDecl
    - xmlParseAttributeListDecl
    - xmlParseEntityDecl
    - xmlParseNotationDecl
    - xmlParseExternalSubset
    - xmlParseInternalSubset
    - xmlParseXMLDecl
    - xmlParseTextDecl
    - xmlParseVersionInfo
    - xmlParseEncodingDecl
    - xmlParseSDDecl
    - xmlCreatePushParserCtxt
    - xmlCreateIOParserCtxt
    - xmlCreateDocParserCtxt
    - xmlCreateMemoryParserCtxt
    - xmlCreateURLParserCtxt
    - xmlParseChunk
    - xmlStopParser
    - xmlCtxtReset
    - xmlCtxtResetPush
    - xmlCtxtSetOptions
    - xmlCtxtUseOptions
    - xmlCtxtParseDocument
    - xmlSAXParseDoc
    - xmlSAXParseFile
    - xmlSAXParseMemory
    - xmlReadDoc
    - xmlReadFile
    - xmlReadMemory
    - xmlReadFd
    - xmlReadIO
    - xmlCtxtReadDoc
    - xmlCtxtReadFile
    - xmlCtxtReadMemory
    - xmlCtxtReadFd
    - xmlCtxtReadIO
    - xmlParseBalancedChunkMemory
    - xmlParseInNodeContext
    - xmlHasFeature
    - xmlScanName
    - xmlParseName
    - xmlParseNmtoken
    - xmlParseEntityValue
    - xmlParseSystemLiteral
    - xmlParsePubidLiteral
    - xmlParseCharRef
    - xmlStringDecodeEntities
    - xmlStringLenDecodeEntities
  dependencies:
    - parser-internals
    - tree
    - entities
    - xmlio
    - encoding
    - buf
    - xmlstring
    - chvalid
    - dict
    - hash
    - xmlmemory
    - error
    - uri
  api_overview: |
    Implements the complete XML parser with both SAX (event-based) and DOM
    (tree-based) parsing interfaces. Handles all XML constructs including
    elements, attributes, text, comments, processing instructions, CDATA,
    DTD declarations, and entity references.
    
    Key structures:
    - All structures from parser-internals module
    - SAX handler callback structures
    
    Features:
    - Complete XML 1.0 specification compliance
    - Namespace support
    - DTD validation
    - Entity processing (internal/external, general/parameter)
    - Push and pull parsing modes
    - Streaming parser with xmlParseChunk
    - Multiple input sources (file, memory, URL, FD, custom I/O)
    - Incremental parsing support
    - Error recovery mechanisms
    - Configurable parsing options
    - SAX callback interface for event-driven parsing
    - DOM tree building
    - Character reference processing
    - Encoding declaration handling
    - Well-formedness checking
    
    Implementation notes:
    - State machine-based parsing
    - Recursive descent parser for complex constructs
    - Character-by-character processing
    - Lookahead for parsing decisions
    - Comprehensive error reporting with location info
    - Memory-efficient streaming support
    - In Rust: use nom parser combinator or similar
    - Event-driven architecture translates well to iterator patterns
    - State machines map well to Rust enums
</file>

<file name="00018-sax2.yaml">
module:
  name: sax2
  description: "Default SAX2 handler implementation for DOM tree building"
  estimated_loc: 2819
  c_files:
    - SAX2.c
  header_files:
    - include/libxml/SAX2.h
  key_functions:
    - xmlSAX2StartDocument
    - xmlSAX2EndDocument
    - xmlSAX2StartElementNs
    - xmlSAX2EndElementNs
    - xmlSAX2StartElement
    - xmlSAX2EndElement
    - xmlSAX2Characters
    - xmlSAX2IgnorableWhitespace
    - xmlSAX2ProcessingInstruction
    - xmlSAX2Comment
    - xmlSAX2CDataBlock
    - xmlSAX2Reference
    - xmlSAX2ResolveEntity
    - xmlSAX2GetEntity
    - xmlSAX2GetParameterEntity
    - xmlSAX2InternalSubset
    - xmlSAX2ExternalSubset
    - xmlSAX2EntityDecl
    - xmlSAX2AttributeDecl
    - xmlSAX2ElementDecl
    - xmlSAX2NotationDecl
    - xmlSAX2UnparsedEntityDecl
    - xmlSAX2SetDocumentLocator
    - xmlSAX2GetLineNumber
    - xmlSAX2GetColumnNumber
    - xmlSAX2IsStandalone
    - xmlSAX2HasInternalSubset
    - xmlSAX2HasExternalSubset
    - xmlSAXDefaultVersion
    - xmlSAX2InitDefaultSAXHandler
    - xmlSAX2InitHtmlDefaultSAXHandler
    - htmlDefaultSAXHandlerInit
    - xmlDefaultSAXHandlerInit
  dependencies:
    - parser-internals
    - tree
    - entities
    - xmlmemory
    - error
    - uri
    - xmlio
  api_overview: |
    Implements the default SAX2 (Simple API for XML 2) handler that builds
    DOM trees from SAX parsing events. Provides the bridge between the
    low-level parser and high-level tree structures.
    
    Key structures:
    - xmlSAXHandler: Function pointer structure for SAX callbacks
    - Uses xmlParserCtxt, xmlDoc, xmlNode from other modules
    
    Features:
    - Complete SAX2 callback implementation
    - DOM tree construction from SAX events
    - Namespace-aware element processing
    - DTD processing (internal/external subsets)
    - Entity resolution and handling
    - Attribute processing with defaults
    - Character data accumulation
    - Error and warning reporting
    - Document locator support (line/column tracking)
    - Support for both XML and HTML parsing
    - Validation integration
    
    Implementation notes:
    - Default handlers for DOM tree building
    - Namespace reconciliation during parsing
    - Memory management for tree nodes
    - Integration with validation subsystem
    - Parser context state management
    - In Rust: implement trait-based SAX handlers
    - Event-driven architecture maps to iterator patterns
    - DOM building can use builder pattern
</file>

<file name="00019-xpath.yaml">
module:
  name: xpath
  description: "XPath 1.0 implementation for XML document navigation and node selection"
  estimated_loc: 12081
  c_files:
    - xpath.c
  header_files:
    - include/libxml/xpath.h
    - include/libxml/xpathInternals.h
  key_functions:
    - xmlXPathInit
    - xmlInitXPathInternal
    - xmlXPathIsNaN
    - xmlXPathIsInf
    - xmlXPathErrMemory
    - xmlXPathPErrMemory
    - xmlXPathErr
    - xmlXPatherror
    - xmlXPathFreeCompExpr
    - xmlXPathContextSetCache
    - xmlXPathDebugDumpObject
    - xmlXPathDebugDumpCompExpr
    - xmlXPathCompile
    - xmlXPathNewContext
    - xmlXPathEval
    - xmlXPathEvalExpression
    - xmlXPathEvalPredicate
    - xmlXPathCompiledEval
    - xmlXPathNodeSetSort
    - xmlXPathNodeSetCreate
    - xmlXPathNodeSetMerge
    - xmlXPathNodeSetAdd
    - xmlXPathFreeObject
    - xmlXPathNewNodeSet
    - xmlXPathNewValueTree
    - xmlXPathNewString
    - xmlXPathNewFloat
    - xmlXPathNewBoolean
    - xmlXPathStringEvalNumber
    - xmlXPathNextSelf
    - xmlXPathNextChild
    - xmlXPathNextDescendant
    - xmlXPathNextParent
    - xmlXPathNextAncestor
    - xmlXPathNextAttribute
    - xmlXPathNextNamespace
    - xmlXPathNextFollowing
    - xmlXPathNextPreceding
    - xmlXPathLocationSetCreate
    - xmlXPathLocationSetAdd
    - xmlXPathLocationSetMerge
    - xmlXPathLocationSetDel
    - xmlXPathLocationSetRemove
  dependencies:
    - tree
    - xmlmemory
    - error
    - hash
    - parser-internals
    - xmlstring
  api_overview: |
    Implements the XML Path Language (XPath) 1.0 specification for navigating
    and selecting nodes from XML documents. Provides both compiled and
    interpreted expression evaluation with comprehensive axis support.
    
    Key structures:
    - xmlXPathCompExpr: Compiled XPath expression for efficient evaluation
    - xmlXPathStepOp: Individual operation in compiled expression tree
    - xmlXPathContextCache: Object pooling for performance optimization
    - xmlXPathObject: Result object (nodeset, boolean, number, string)
    - xmlNodeSet: Dynamic array of XML nodes
    - xmlLocationSet: XPointer location set support
    
    Key enums:
    - xmlXPathOp: Operation codes for compiled expressions
    - xmlXPathAxisVal: XPath axes (child, parent, ancestor, etc.)
    - xmlXPathTestVal: Node test types (name, type, namespace)
    - xmlXPathTypeVal: XML node types for testing
    
    Features:
    - Complete XPath 1.0 specification support
    - Expression compilation for performance
    - All XPath axes (child, parent, ancestor, descendant, etc.)
    - Node tests (name, type, namespace wildcards)
    - Predicates and filtering
    - Standard XPath function library
    - Custom function and variable registration
    - Object caching for memory efficiency
    - Node set sorting and deduplication
    - Location sets for XPointer support
    - Streaming XPath (when pattern module available)
    - Thread-safe evaluation contexts
    - Comprehensive error reporting
    - Debug dumping capabilities
    
    Implementation notes:
    - Recursive descent parser for XPath syntax
    - Tree-walking evaluator with axis optimization
    - Memory-efficient node set operations
    - Floating-point arithmetic with NaN/Infinity support
    - In Rust: use nom for parsing, enum-based AST
    - Iterator patterns for axis traversal
    - Arena allocation for temporary objects
</file>

<file name="00020-pattern.yaml">
module:
  name: pattern
  description: "XPath pattern compilation and streaming evaluation for efficient node matching"
  estimated_loc: 1438
  c_files:
    - pattern.c
  header_files:
    - include/libxml/pattern.h
  key_functions:
    - xmlPatterncompile
    - xmlFreePattern
    - xmlFreePatternList
    - xmlPatternMatch
    - xmlPatternGetStreamCtxt
    - xmlFreeStreamCtxt
    - xmlStreamPush
    - xmlStreamPushNode
    - xmlStreamPushAttr
    - xmlStreamPop
    - xmlStreamWantsAnyNode
    - xmlPatternFromRoot
    - xmlPatternGetStreamCtxtPtr
    - xmlPatternMaxDepth
    - xmlPatternMinDepth
  dependencies:
    - tree
    - dict
    - xmlmemory
    - error
    - parser-internals
  api_overview: |
    Provides XPath-like pattern compilation and evaluation for both tree-based
    and streaming XML processing. Enables efficient node selection and matching
    with support for XML Schema Identity Constraints.
    
    Key structures:
    - xmlPattern: Compiled XPath pattern for tree/stream matching
    - xmlStreamComp: Pattern compiled for streaming automaton
    - xmlStreamCtxt: Runtime state for streaming pattern evaluation
    - xmlStepOp: Single operation in tree-based pattern
    - xmlStreamStep: Single step in streaming automaton
    
    Key enums:
    - xmlPatOp: Pattern operation types (element, attribute, parent, ancestor)
    
    Features:
    - XPath-like pattern compilation
    - Tree-based pattern matching against existing nodes
    - Streaming pattern evaluation for SAX-like processing
    - Multiple pattern syntaxes (XPath, XML Schema selector/field)
    - Namespace-aware matching
    - Wildcard support (* for any element)
    - Descendant axis support (//)
    - Attribute matching
    - Pattern combination with union (|)
    - Memory-efficient streaming automaton
    - State management for incremental evaluation
    - Integration with XML Schema validation
    - Root and depth constraints
    
    Implementation notes:
    - Finite state automaton for streaming evaluation
    - Optimized pattern compilation with operation fusion
    - Memory pooling through dictionary integration
    - Thread-safe pattern objects (contexts are per-thread)
    - In Rust: state machine with enum-based operations
    - Iterator patterns for streaming evaluation
    - Trait-based pattern matching interface
</file>

<file name="00021-xpointer.yaml">
module:
  name: xpointer
  description: "XML Pointer Language (XPointer) implementation for addressing XML document fragments"
  estimated_loc: 2423
  c_files:
    - xpointer.c
  header_files:
    - include/libxml/xpointer.h
  key_functions:
    - xmlXPtrNewContext
    - xmlXPtrEval
    - xmlXPtrNewLocationSet
    - xmlXPtrFreeLocationSet
    - xmlXPtrLocationSetAdd
    - xmlXPtrLocationSetMerge
    - xmlXPtrLocationSetDel
    - xmlXPtrLocationSetRemove
    - xmlXPtrLocationSetCreate
    - xmlXPtrNewRange
    - xmlXPtrNewRangePoints
    - xmlXPtrNewRangeNodePoint
    - xmlXPtrNewRangePointNode
    - xmlXPtrNewRangeNodes
    - xmlXPtrFreeRange
    - xmlXPtrNewCollapsedRange
    - xmlXPtrRangeToFunction
    - xmlXPtrBuildNodeList
    - xmlXPtrEvalXPtrPart
    - xmlXPtrStringRangeFunction
    - xmlXPtrStartPointFunction
    - xmlXPtrEndPointFunction
    - xmlXPtrHereFunction
    - xmlXPtrOriginFunction
    - xmlXPtrRangeFunction
    - xmlXPtrRangeInsideFunction
    - xmlXPtrRangeToFunction
  dependencies:
    - xpath
    - tree
    - uri
    - parser-internals
    - xmlmemory
    - error
  api_overview: |
    Implements the W3C XML Pointer Language (XPointer) specification for
    addressing and identifying specific parts within XML documents. Extends
    XPath functionality with additional addressing schemes and range support.
    
    Key structures:
    - xmlXPathContext: Extended for XPointer evaluation environment
    - xmlXPathObject: Result objects including location sets and ranges
    - xmlLocationSet: Collection of locations (nodes, points, ranges)
    - xmlXPathRange: Range between two points in document
    - xmlXPathPoint: Position within text or between nodes
    
    XPointer schemes supported:
    - xpointer(): Full XPointer expressions using XPath syntax
    - element(): Child sequence addressing (e.g., element(1/3/2))
    - xmlns(): Namespace prefix registration
    - Bare names: ID-based element selection
    
    Features:
    - Cascaded part evaluation (first successful wins)
    - Range-based selections
    - Point-based addressing
    - Location sets for multiple results
    - Standard XPointer functions (here(), origin(), start-point(), etc.)
    - String range functions
    - ID-based shortcuts
    - Namespace handling
    - Integration with XPath evaluation
    - Error recovery for malformed parts
    
    Implementation notes:
    - Built on top of XPath engine
    - Range operations for text selections
    - Location set management and merging
    - Scheme-specific parsers and evaluators
    - In Rust: enum-based scheme dispatching
    - Range types with proper lifetime management
    - Iterator patterns for location set traversal
</file>

<file name="00022-valid.yaml">
module:
  name: valid
  description: "DTD validation engine with element and attribute declaration processing"
  estimated_loc: 7215
  c_files:
    - valid.c
  header_files:
    - include/libxml/valid.h
  key_functions:
    - xmlNewValidCtxt
    - xmlFreeValidCtxt
    - xmlAddElementDecl
    - xmlAddAttributeDecl
    - xmlFreeEnumeration
    - xmlValidateDocument
    - xmlValidateElement
    - xmlValidateElementDecl
    - xmlValidateAttributeDecl
    - xmlValidateNotationDecl
    - xmlValidateDtd
    - xmlValidateRoot
    - xmlValidateElementContent
    - xmlValidateOneElement
    - xmlValidateOneAttribute
    - xmlValidateAttributeValue
    - xmlValidateNameValue
    - xmlValidateNamesValue
    - xmlValidateNmtokenValue
    - xmlValidateNmtokensValue
    - xmlIsMixedElement
    - xmlGetDtdElementDesc
    - xmlGetDtdAttrDesc
    - xmlGetDtdNotationDesc
    - xmlGetDtdQElementDesc
    - xmlGetDtdQAttrDesc
    - xmlValidatePopElement
    - xmlValidatePushElement
    - xmlValidatePushCData
    - xmlValidBuildContentModel
    - xmlValidateDocumentFinal
    - xmlValidateCheckMixed
    - xmlValidateElementType
  dependencies:
    - tree
    - hash
    - xmlmemory
    - error
    - parser-internals
    - list
    - xmlsave
    - regexp
  api_overview: |
    Implements Document Type Definition (DTD) validation for XML documents.
    Handles element and attribute declarations, content models, and provides
    comprehensive validation against DTD constraints.
    
    Key structures:
    - xmlValidCtxt: Validation context with state tracking
    - xmlElementContent: Tree structure for element content models
    - xmlElement: Element declaration from DTD
    - xmlAttribute: Attribute declaration from DTD  
    - xmlEnumeration: Enumerated attribute values
    - xmlValidState: Content model validation state stack
    
    Key enums:
    - xmlElementContentType: Content model node types (PCDATA, ELEMENT, SEQ, OR)
    - xmlElementContentOccur: Occurrence indicators (once, optional, multiple, plus)
    - xmlElementTypeVal: Element content types (EMPTY, ANY, MIXED, ELEMENT)
    - xmlAttributeType: Attribute data types (CDATA, ID, NMTOKEN, ENUMERATION)
    - xmlAttributeDefault: Default specifications (REQUIRED, IMPLIED, FIXED)
    
    Features:
    - Complete DTD processing and validation
    - Element content model evaluation
    - Attribute validation and type checking
    - ID/IDREF reference validation
    - Mixed content model support
    - Content model regular expression compilation
    - Validation context stack for nested elements
    - Error reporting with location information
    - Incremental validation during parsing
    - Post-parse document validation
    - Notation declaration handling
    - Entity declaration validation
    - Default attribute value application
    
    Implementation notes:
    - State machine for content model validation
    - Regular expression engine for complex models
    - Hash tables for efficient declaration lookup
    - Stack-based validation state tracking
    - In Rust: enum-based content models
    - Regular expression crate integration
    - Visitor pattern for validation traversal
</file>

<file name="00023-xmlregexp.yaml">
module:
  name: xmlregexp
  description: "Regular expression engine for XML content model validation and schema constraints"
  estimated_loc: 8547
  c_files:
    - xmlregexp.c
  header_files:
    - include/libxml/xmlregexp.h
    - include/libxml/xmlautomata.h
  key_functions:
    - xmlRegCompile
    - xmlRegFreeRegexp
    - xmlRegNewExecCtxt
    - xmlRegFreeExecCtxt
    - xmlRegExec
    - xmlRegexpIsDeterminist
    - xmlRegexpCompile
    - xmlRegexpExec
    - xmlRegexpPrint
    - xmlAutomataNew
    - xmlAutomataFree
    - xmlAutomataGetInitState
    - xmlAutomataSetFinalState
    - xmlAutomataNewState
    - xmlAutomataNewTransition
    - xmlAutomataNewEpsilon
    - xmlAutomataNewAtom
    - xmlAutomataNewCounter
    - xmlAutomataNewCountTrans
    - xmlAutomataCompile
    - xmlAutomataGetCounter
    - xmlRegexpTestCompile
  dependencies:
    - xmlmemory
    - error
    - xmlstring
  api_overview: |
    Provides a comprehensive regular expression engine designed specifically
    for XML validation contexts including DTD content models, XML Schema
    patterns, and RELAX-NG expressions.
    
    Key structures:
    - xmlRegParserCtxt: Compilation context with parser state
    - xmlRegexp: Compiled regular expression with finite automaton
    - xmlRegAtom: Atomic expression components (characters, strings, ranges)
    - xmlRegState: Finite automaton states with transitions
    - xmlRegExecCtxt: Execution context for pattern matching
    - xmlAutomata: High-level automaton construction interface
    
    Key enums:
    - xmlRegAtomType: Atom types (char, string, ranges, Unicode categories)
    - xmlRegQuantType: Quantifiers (once, optional, multiple, plus, range)
    - xmlRegStateType: State types (start, final, transition, sink)
    
    Features:
    - Regular expression compilation to finite automata
    - Both NFA and DFA representation support
    - Unicode character class support
    - XML-specific character classes (letters, digits, spaces)
    - Unicode block and category matching
    - Quantifier support (?, *, +, {n,m})
    - Epsilon transitions for complex patterns
    - Backtracking execution for non-deterministic automata
    - Deterministic optimization for performance
    - Compact representation for memory efficiency
    - Token-based and string-based input processing
    - Callback mechanism for custom token handling
    - Counter support for bounded repetition
    - Automaton construction API for programmatic building
    - Pattern debugging and visualization
    
    Implementation notes:
    - Thompson NFA construction algorithm
    - Subset construction for DFA conversion
    - Memory-efficient state representation
    - Optimized transitions for common patterns
    - In Rust: regex crate integration or custom engine
    - State machine with enum-based states
    - Iterator patterns for match processing
</file>

<file name="00024-xmlschemas.yaml">
module:
  name: xmlschemas
  description: "XML Schema (XSD) validation engine with complete W3C XML Schema support"
  estimated_loc: 29084
  c_files:
    - xmlschemas.c
  header_files:
    - include/libxml/xmlschemas.h
    - include/libxml/schemasInternals.h
  key_functions:
    - xmlSchemaNewParserCtxt
    - xmlSchemaParse
    - xmlSchemaFree
    - xmlSchemaNewValidCtxt
    - xmlSchemaValidateDoc
    - xmlSchemaFreeValidCtxt
    - xmlSchemaSetParserErrors
    - xmlSchemaSetValidErrors
    - xmlSchemaNewMemParserCtxt
    - xmlSchemaNewDocParserCtxt
    - xmlSchemaFreeParserCtxt
    - xmlSchemaValidateFile
    - xmlSchemaValidateStream
    - xmlSchemaValidateOneElement
    - xmlSchemaIsValid
    - xmlSchemaSetValidOptions
    - xmlSchemaGetValidErrors
    - xmlSchemaSetParserStructuredErrors
    - xmlSchemaSetValidStructuredErrors
    - xmlSchemaValidCtxtGetOptions
    - xmlSchemaValidCtxtGetParserCtxt
    - xmlSchemaValidateSetFilename
    - xmlSchemaCheckFacet
    - xmlSchemaFreeFacet
    - xmlSchemaNewFacet
  dependencies:
    - tree
    - parser-internals
    - hash
    - uri
    - dict
    - xmlmemory
    - error
    - xmlregexp
    - xmlautomata
    - pattern
    - encoding
    - xmlio
    - xmlreader
    - xmlschemastypes
  api_overview: |
    Implements complete W3C XML Schema Definition (XSD) 1.0 specification
    including schema parsing, compilation, and instance document validation
    with full support for complex types, identity constraints, and imports.
    
    Key structures:
    - xmlSchemaParserCtxt: Schema parsing context with construction state
    - xmlSchemaValidCtxt: Validation context for instance documents
    - xmlSchemaBasicItem: Base type for all schema components
    - xmlSchemaType: Type definitions (simple and complex)
    - xmlSchemaElement: Element declarations
    - xmlSchemaAttribute: Attribute declarations
    - xmlSchemaNodeInfo: Per-element validation state tracking
    - xmlSchemaBucket: Individual schema documents in schema set
    - xmlSchemaConstructionCtxt: Multi-document schema construction
    
    Key enums:
    - xmlSchemaTypeType: Schema component types (element, type, attribute, etc.)
    - xmlSchemaWhitespaceValueType: Whitespace processing rules
    - xmlSchemaBucketType: Schema document relationships (import, include, redefine)
    
    Features:
    - Complete XSD 1.0 specification compliance
    - Schema document parsing and compilation
    - Multi-document schema sets (import, include, redefine)
    - Simple and complex type validation
    - Content model validation with finite automata
    - Identity constraint validation (unique, key, keyref)
    - Facet-based simple type validation
    - Substitution group support
    - Abstract types and elements
    - Nillable elements
    - Default and fixed values
    - Union and list types
    - Wildcard processing (any, anyAttribute)
    - Namespace validation
    - Error collection and reporting
    - Streaming validation support
    - XPath-based identity constraints
    - Schema location hints
    - Type derivation by extension and restriction
    
    Implementation notes:
    - Multi-phase compilation (parsing, construction, compilation)
    - Finite automata for content model validation
    - Hash-based component lookup for performance
    - Memory-efficient schema representation
    - Identity constraint evaluation with XPath
    - In Rust: enum-based schema components
    - Visitor pattern for validation traversal
    - Builder pattern for schema construction
</file>

<file name="00025-relaxng.yaml">
module:
  name: relaxng
  description: "RELAX NG schema validation engine with full compact and XML syntax support"
  estimated_loc: 10403
  c_files:
    - relaxng.c
  header_files:
    - include/libxml/relaxng.h
  key_functions:
    - xmlRelaxNGFree
    - xmlRelaxParserSetFlag
    - xmlRelaxNGNewParserCtxt
    - xmlRelaxNGNewMemParserCtxt
    - xmlRelaxNGNewDocParserCtxt
    - xmlRelaxNGFreeParserCtxt
    - xmlRelaxNGParse
    - xmlRelaxNGNewValidCtxt
    - xmlRelaxNGFreeValidCtxt
    - xmlRelaxNGValidateDoc
    - xmlRelaxNGValidatePushElement
    - xmlRelaxNGValidatePushCData
    - xmlRelaxNGValidatePopElement
    - xmlRelaxNGValidateFullElement
    - xmlRelaxNGSetParserErrors
    - xmlRelaxNGSetValidErrors
    - xmlRelaxNGSetParserStructuredErrors
    - xmlRelaxNGSetValidStructuredErrors
    - xmlRelaxNGGetParserErrors
    - xmlRelaxNGGetValidErrors
    - xmlRelaxNGCleanupTypes
    - xmlRelaxNGInitTypes
    - xmlRelaxNGDump
    - xmlRelaxNGDumpTree
  dependencies:
    - tree
    - parser-internals
    - hash
    - uri
    - xmlmemory
    - error
    - xmlautomata
    - xmlregexp
    - xmlschemastypes
  api_overview: |
    Implements RELAX NG schema validation with support for both XML syntax
    and compact syntax. Provides pattern-based validation with powerful
    content model compilation and efficient validation algorithms.
    
    Key structures:
    - xmlRelaxNG: Compiled RELAX NG schema with grammars and definitions
    - xmlRelaxNGDefine: Individual patterns (element, attribute, choice, etc.)
    - xmlRelaxNGParserCtxt: Schema parsing context with state management
    - xmlRelaxNGValidCtxt: Validation context for instance documents
    - xmlRelaxNGGrammar: Grammar blocks with scoped definitions
    - xmlRelaxNGDocument: External schema document handling
    
    Key enums:
    - xmlRelaxNGCombine: Pattern combination behavior (choice, interleave)
    - xmlRelaxNGType: Pattern types (element, attribute, choice, group, etc.)
    
    Features:
    - Complete RELAX NG specification support
    - Both XML and compact syntax parsing
    - Pattern-based content models
    - Data type validation integration
    - External schema references (externalRef, include)
    - Grammar modularity and scoping
    - Named pattern definitions and references
    - Choice and interleave content models
    - Attribute patterns with data types
    - Text patterns and mixed content
    - Empty and notAllowed patterns
    - Finite automata compilation for performance
    - Streaming validation support
    - Namespace handling
    - Error recovery and detailed reporting
    - Schema debugging and visualization
    - Integration with XML Schema data types
    
    Implementation notes:
    - Multi-pass schema compilation (parse, simplify, compile)
    - Finite automata generation for content models
    - Hash-based definition and reference resolution
    - Memory-efficient pattern representation
    - Backtracking validation with state management
    - In Rust: enum-based pattern types
    - Recursive descent pattern matching
    - Builder pattern for schema construction
</file>

<file name="00026-schematron.yaml">
module:
  name: schematron
  description: "Schematron rule-based validation with XPath assertions and reports"
  estimated_loc: 1664
  c_files:
    - schematron.c
  header_files:
    - include/libxml/schematron.h
  key_functions:
    - xmlSchematronFree
    - xmlSchematronNewParserCtxt
    - xmlSchematronNewMemParserCtxt
    - xmlSchematronNewDocParserCtxt
    - xmlSchematronFreeParserCtxt
    - xmlSchematronParse
    - xmlSchematronNewValidCtxt
    - xmlSchematronFreeValidCtxt
    - xmlSchematronValidateDoc
    - xmlSchematronSetParserErrors
    - xmlSchematronSetValidErrors
    - xmlSchematronSetParserStructuredErrors
    - xmlSchematronSetValidStructuredErrors
    - xmlSchematronGetParserErrors
    - xmlSchematronGetValidErrors
    - xmlSchematronValidCtxtGetOptions
    - xmlSchematronValidCtxtSetOptions
    - xmlSchematronSetValidOptions
    - xmlSchematronValidateStream
    - xmlSchematronValidatePushElement
    - xmlSchematronValidatePopElement
  dependencies:
    - tree
    - parser-internals
    - uri
    - xpath
    - pattern
    - xmlmemory
    - error
  api_overview: |
    Implements ISO Schematron rule-based validation using XPath expressions
    for complex business rule validation beyond structural constraints.
    Provides pattern-based rules with assertions and reports.
    
    Key structures:
    - xmlSchematron: Compiled Schematron schema with patterns and rules
    - xmlSchematronRule: Rule definition with context and tests
    - xmlSchematronTest: Individual assertion or report test
    - xmlSchematronParserCtxt: Schema parsing context
    - xmlSchematronValidCtxt: Validation context for instance documents
    - xmlSchematronPattern: Schema pattern grouping rules
    
    Key enums:
    - xmlSchematronTestType: Test types (assert, report)
    
    Features:
    - Complete ISO Schematron specification support
    - XPath 1.0 expression evaluation for rules
    - Pattern-based rule organization
    - Context-sensitive rule application
    - Assert tests (must be true) and report tests (informational)
    - Let variables for expression reuse
    - Rich error and warning reporting
    - Custom diagnostic messages
    - Namespace support in rules
    - Phase-based validation (if implemented)
    - Abstract patterns and rules
    - Query binding for different XPath engines
    - Integration with XPath pattern matching
    - Streaming validation capabilities
    - SVRL (Schematron Validation Report Language) output
    
    Implementation notes:
    - XPath expression compilation for performance
    - Pattern-based context matching for rule selection
    - Rule evaluation with context node iteration
    - Memory-efficient rule and test representation
    - In Rust: XPath crate integration
    - Rule engine with context-based dispatch
    - Functional programming patterns for rule evaluation
</file>

<file name="00027-htmlparser.yaml">
module:
  name: htmlparser
  description: "HTML5-compliant parser with tokenization and tree construction"
  estimated_loc: 6321
  c_files:
    - HTMLparser.c
  header_files:
    - include/libxml/HTMLparser.h
  key_functions:
    - htmlInitAutoClose
    - htmlTagLookup
    - htmlAutoCloseTag
    - htmlIsAutoClosed
    - htmlIsScriptAttribute
    - htmlParseDocument
    - htmlParseElement
    - htmlParseCharData
    - htmlParseComment
    - htmlParseScript
    - htmlParseStartTag
    - htmlParseEndTag
    - htmlParseEntityRef
    - htmlParseCharRef
    - htmlParseDocTypeDecl
    - htmlCreatePushParserCtxt
    - htmlCreateFileParserCtxt
    - htmlCreateMemoryParserCtxt
    - htmlCtxtReset
    - htmlCtxtSetOptions
    - htmlCtxtUseOptions
    - htmlFreeParserCtxt
    - htmlNewParserCtxt
    - htmlParseChunk
    - htmlStopParser
    - htmlSAXParseDoc
    - htmlSAXParseFile
    - htmlParseDoc
    - htmlParseFile
    - htmlReadDoc
    - htmlReadFile
    - htmlReadMemory
    - htmlReadFd
    - htmlReadIO
    - htmlCtxtReadDoc
    - htmlCtxtReadFile
    - htmlCtxtReadMemory
    - htmlCtxtReadFd
    - htmlCtxtReadIO
    - htmlHandleOmittedElem
  dependencies:
    - tree
    - parser-internals
    - entities
    - encoding
    - xmlio
    - uri
    - xmlmemory
    - error
    - htmltree
  api_overview: |
    Implements HTML5-compliant parsing with robust error recovery and
    tree construction. Handles HTML-specific rules like tag omission,
    auto-closing, and lenient parsing for real-world HTML content.
    
    Key structures:
    - htmlParserCtxt: HTML parsing context with insertion modes
    - htmlElemDesc: HTML element property descriptor
    - htmlParserNodeInfo: Positional information for nodes
    - htmlSAXHandler: HTML-specific SAX event handlers
    
    Key enums:
    - htmlInsertMode: Tree construction insertion contexts
    - Content type flags: Element content models (rawtext, script, rcdata)
    
    Features:
    - HTML5 tokenization algorithm
    - Custom tree construction (non-standard but practical)
    - Automatic tag closing and omission handling
    - Error recovery for malformed HTML
    - Script and style content handling
    - Character and entity reference processing
    - DOCTYPE parsing and validation
    - Push parser for streaming content
    - SAX and DOM parsing interfaces
    - Multiple input sources (file, memory, URL, FD, custom I/O)
    - Configurable parsing options
    - Position tracking for error reporting
    - Integration with HTML tree construction
    - Namespace handling for XHTML
    - Encoding detection and conversion
    - Fragment parsing support
    
    Implementation notes:
    - State machine-based tokenization
    - Stack-based tree construction with insertion modes
    - Lenient parsing with automatic error correction
    - HTML element property tables for behavior lookup
    - In Rust: html5ever crate integration
    - State machine with enum-based insertion modes
    - Builder pattern for HTML tree construction
</file>

<file name="00028-htmltree.yaml">
module:
  name: htmltree
  description: "HTML tree manipulation and serialization with HTML-specific output rules"
  estimated_loc: 1278
  c_files:
    - HTMLtree.c
  header_files:
    - include/libxml/HTMLtree.h
  key_functions:
    - htmlGetMetaEncoding
    - htmlSetMetaEncoding
    - htmlNodeDump
    - htmlNodeDumpFileFormat
    - htmlDocDumpMemoryFormat
    - htmlSaveFileFormat
    - htmlNodeDumpFormatOutput
    - htmlDocContentDumpOutput
    - htmlDocContentDumpFormatOutput
    - htmlNodeDumpOutput
    - htmlAttrDumpOutput
    - htmlNodeListDumpOutput
    - htmlDtdDumpOutput
    - htmlIsBooleanAttr
    - htmlIsScriptAttribute
    - htmlSaveFile
    - htmlSaveFileEnc
    - htmlDocDump
    - htmlDocDumpMemory
    - htmlNewDoc
    - htmlNewDocNoDtd
  dependencies:
    - tree
    - htmlparser
    - xmlsave
    - encoding
    - xmlio
    - buf
    - xmlmemory
    - error
    - uri
  api_overview: |
    Provides HTML-specific tree manipulation and serialization functions
    with proper handling of HTML rules for encoding, attributes, and
    element-specific serialization requirements.
    
    Key structures:
    - htmlMetaEncoding: Meta tag encoding information
    - htmlMetaEncodingOffsets: Byte offsets for encoding strings
    - xmlOutputBuffer: Output buffer with encoding conversion
    
    Features:
    - HTML meta tag encoding inspection and modification
    - HTML-specific serialization rules
    - Boolean attribute handling (e.g., checked, disabled)
    - Script attribute recognition and escaping
    - URI attribute escaping
    - HTML5 void element handling
    - DOCTYPE serialization
    - Multiple output formats (memory, file, buffer)
    - Character encoding conversion during output
    - Proper HTML entity escaping
    - Namespace handling for XHTML
    - Formatting options for readable output
    - Integration with HTML parser element descriptions
    - Support for HTML fragments
    - CDATA section handling in script/style elements
    
    Implementation notes:
    - HTML-specific serialization differs from XML
    - Meta tag encoding detection and manipulation
    - Boolean attributes serialized without values in HTML mode
    - Special handling for script, style, and other raw content elements
    - In Rust: HTML-specific serialization traits
    - Builder pattern for HTML document construction
    - Streaming serialization with proper encoding
</file>

<file name="00029-xmlreader.yaml">
module:
  name: xmlreader
  description: "Streaming pull-parser API for forward-only XML processing with validation support"
  estimated_loc: 5488
  c_files:
    - xmlreader.c
  header_files:
    - include/libxml/xmlreader.h
  key_functions:
    - xmlTextReaderRead
    - xmlTextReaderReadState
    - xmlTextReaderExpand
    - xmlTextReaderNext
    - xmlNewTextReader
    - xmlNewTextReaderFilename
    - xmlNewTextReaderFile
    - xmlFreeTextReader
    - xmlTextReaderNodeType
    - xmlTextReaderName
    - xmlTextReaderLocalName
    - xmlTextReaderNamespaceUri
    - xmlTextReaderPrefix
    - xmlTextReaderValue
    - xmlTextReaderBaseUri
    - xmlTextReaderAttributeCount
    - xmlTextReaderDepth
    - xmlTextReaderHasAttributes
    - xmlTextReaderHasValue
    - xmlTextReaderIsDefault
    - xmlTextReaderIsEmptyElement
    - xmlTextReaderQuoteChar
    - xmlTextReaderXmlLang
    - xmlTextReaderConstName
    - xmlTextReaderConstLocalName
    - xmlTextReaderConstNamespaceUri
    - xmlTextReaderConstPrefix
    - xmlTextReaderConstValue
    - xmlTextReaderGetAttribute
    - xmlTextReaderGetAttributeNo
    - xmlTextReaderGetAttributeNs
    - xmlTextReaderMoveToAttribute
    - xmlTextReaderMoveToAttributeNo
    - xmlTextReaderMoveToAttributeNs
    - xmlTextReaderMoveToFirstAttribute
    - xmlTextReaderMoveToNextAttribute
    - xmlTextReaderMoveToElement
    - xmlTextReaderReadAttributeValue
    - xmlTextReaderSetParserProp
    - xmlTextReaderGetParserProp
    - xmlTextReaderCurrentNode
    - xmlTextReaderCurrentDoc
    - xmlTextReaderRelaxNGValidate
    - xmlTextReaderSchemaValidate
    - xmlTextReaderRelaxNGSetSchema
    - xmlTextReaderSchemaValidateCtxt
    - xmlTextReaderSetSchema
    - xmlTextReaderClose
  dependencies:
    - tree
    - parser-internals
    - xmlmemory
    - error
    - xmlio
    - uri
    - encoding
    - xmlsave
    - relaxng
    - xmlschemas
    - valid
    - xinclude
    - pattern
  api_overview: |
    Provides a streaming, forward-only XML reader API similar to .NET's
    XmlTextReader. Built on top of libxml2's SAX parser with memory-efficient
    processing and integrated validation support.
    
    Key structures:
    - xmlTextReader: Main reader instance with parser state
    - xmlParserCtxt: Underlying parser context
    - xmlNode: Current XML node being processed
    
    Key enums:
    - xmlTextReaderState: Reader position states (element, end, done, error)
    - xmlTextReaderValidate: Validation types (DTD, RelaxNG, XML Schema)
    
    Features:
    - Pull-parser streaming interface
    - Forward-only document traversal
    - Memory-efficient processing (doesn't load entire document)
    - Integrated validation (DTD, RelaxNG, XML Schema)
    - XInclude processing support
    - Node expansion to DOM when needed
    - Attribute navigation and access
    - Namespace-aware processing
    - Custom error handling callbacks
    - Resource loading customization
    - Subtree skipping capabilities
    - Position and depth tracking
    - Document base URI handling
    - Parser property configuration
    - Node recycling for memory efficiency
    - Support for multiple input sources
    - Schema validation integration
    - Pattern-based processing
    
    Implementation notes:
    - Wraps SAX parser for pull-based access
    - On-demand DOM expansion for complex operations
    - Memory recycling for performance
    - State machine for reader position tracking
    - In Rust: Iterator-based streaming with validation
    - Trait-based reader interface
    - Zero-copy string handling where possible
</file>

<file name="00030-xmlwriter.yaml">
module:
  name: xmlwriter
  description: "Streaming XML writer API for programmatic XML document generation"
  estimated_loc: 3816
  c_files:
    - xmlwriter.c
  header_files:
    - include/libxml/xmlwriter.h
  key_functions:
    - xmlNewTextWriter
    - xmlNewTextWriterFilename
    - xmlNewTextWriterDoc
    - xmlFreeTextWriter
    - xmlTextWriterStartDocument
    - xmlTextWriterEndDocument
    - xmlTextWriterStartElement
    - xmlTextWriterEndElement
    - xmlTextWriterWriteAttribute
    - xmlTextWriterWriteString
    - xmlTextWriterSetIndent
    - xmlNewTextWriterMemory
    - xmlNewTextWriterPushParser
    - xmlNewTextWriterTree
    - xmlTextWriterStartElementNS
    - xmlTextWriterEndElement
    - xmlTextWriterStartAttribute
    - xmlTextWriterEndAttribute
    - xmlTextWriterStartAttributeNS
    - xmlTextWriterWriteAttributeNS
    - xmlTextWriterWriteCDATA
    - xmlTextWriterWriteComment
    - xmlTextWriterWriteElement
    - xmlTextWriterWriteElementNS
    - xmlTextWriterWritePI
    - xmlTextWriterWriteRaw
    - xmlTextWriterWriteVFormatString
    - xmlTextWriterWriteFormatString
    - xmlTextWriterWriteFormatAttribute
    - xmlTextWriterWriteFormatAttributeNS
    - xmlTextWriterWriteFormatComment
    - xmlTextWriterWriteFormatElement
    - xmlTextWriterWriteFormatElementNS
    - xmlTextWriterWriteFormatPI
    - xmlTextWriterStartDTD
    - xmlTextWriterEndDTD
    - xmlTextWriterWriteDTD
    - xmlTextWriterStartDTDElement
    - xmlTextWriterEndDTDElement
    - xmlTextWriterWriteDTDElement
    - xmlTextWriterStartDTDAttlist
    - xmlTextWriterEndDTDAttlist
    - xmlTextWriterWriteDTDAttlist
    - xmlTextWriterStartDTDEntity
    - xmlTextWriterEndDTDEntity
    - xmlTextWriterWriteDTDEntity
    - xmlTextWriterWriteDTDExternalEntity
    - xmlTextWriterWriteDTDExternalEntityContents
    - xmlTextWriterWriteDTDInternalEntity
    - xmlTextWriterWriteDTDNotation
    - xmlTextWriterSetIndentString
    - xmlTextWriterFlush
  dependencies:
    - tree
    - parser-internals
    - buf
    - encoding
    - xmlsave
    - xmlmemory
    - error
    - uri
    - sax2
    - htmltree
  api_overview: |
    Provides a streaming API for generating well-formed XML documents
    programmatically. Supports multiple output destinations and formats
    with automatic character escaping and proper XML structure validation.
    
    Key structures:
    - xmlTextWriter: Main writer context with output buffer and state
    - xmlTextWriterStackEntry: Element/construct stack tracking
    - xmlTextWriterNsStackEntry: Namespace declaration stack
    - xmlOutputBuffer: Output destination abstraction
    
    Key enums:
    - xmlTextWriterState: Writer state machine states
    
    Features:
    - Streaming XML document generation
    - Multiple output destinations (file, memory, buffer, DOM tree)
    - Automatic character escaping and encoding
    - Namespace support with prefix management
    - Proper XML well-formedness validation
    - Indentation and formatting options
    - CDATA section writing
    - Comment and processing instruction support
    - DTD generation capabilities
    - Element and attribute stack management
    - Printf-style formatted output functions
    - Self-closing tag optimization
    - Raw content writing for special cases
    - Document tree building while writing
    - Push parser integration
    - Compression support for file output
    - Custom indentation strings
    - Buffer flushing control
    
    Implementation notes:
    - Stack-based element tracking for well-formedness
    - State machine for valid operation sequences
    - Automatic namespace declaration management
    - Character escaping based on context (element, attribute, etc.)
    - In Rust: Builder pattern with type-safe API
    - Streaming writer with proper resource management
    - Event-driven XML generation
</file>

<file name="00031-c14n.yaml">
module:
  name: c14n
  description: "W3C XML Canonicalization (C14N) implementation for cryptographic applications"
  estimated_loc: 1892
  c_files:
    - c14n.c
  header_files:
    - include/libxml/c14n.h
  key_functions:
    - xmlC14NExecute
    - xmlC14NDocSave
    - xmlC14NDocSaveTo
    - xmlC14NDocDumpMemory
    - xmlC14NDocSaveCtxtInit
    - xmlC14NDocSaveFinalize
    - xmlC14NIsVisibleCallback
    - xmlC14NProcessNamespaces
    - xmlC14NAttrsCompare
    - xmlC14NProcessAttrs
    - xmlC14NCheckNamespacesWalker
    - xmlC14NVisibleNsStackFind
    - xmlC14NVisibleNsStackAdd
    - xmlC14NVisibleNsStackShift
    - xmlC14NNodeDataIsVisible
    - xmlC14NProcessNode
    - xmlC14NProcessNodeList
    - xmlC14NNormalizeString
  dependencies:
    - tree
    - parser-internals
    - uri
    - xpath
    - xmlmemory
    - error
    - xmlio
  api_overview: |
    Implements W3C XML Canonicalization (C14N) specifications for creating
    standardized, unambiguous XML representations essential for digital
    signatures and cryptographic hashing.
    
    Key structures:
    - xmlC14NCtx: Canonicalization context with processing state
    - xmlC14NVisibleNsStack: Namespace visibility stack management
    - xmlC14NIsVisibleCallback: Node visibility determination function
    
    Key enums:
    - xmlC14NPosition: Processing position relative to document element
    - xmlC14NNormalizationMode: String normalization rules for different contexts
    - xmlC14NMode: Canonicalization algorithm variants
    
    Features:
    - Canonical XML 1.0 and 1.1 support
    - Exclusive XML Canonicalization 1.0
    - Node-set canonicalization with visibility callbacks
    - Proper namespace inheritance and propagation
    - Attribute ordering and normalization
    - Character data normalization
    - Comment inclusion/exclusion options
    - Processing instruction handling
    - Digital signature compatibility
    - XPath node-set integration
    - Inclusive namespace prefix lists for exclusive C14N
    - Document subset canonicalization
    - Memory and streaming output support
    
    Implementation notes:
    - Recursive tree traversal with namespace stack
    - Attribute sorting for deterministic output
    - Character escaping based on XML context
    - Namespace visibility tracking for inheritance
    - In Rust: deterministic serialization with sorting
    - Cryptographic hash compatibility
    - Standards-compliant byte-for-byte output
</file>

## Module Summaries

Read each of the module summaries in @module_summaries/ to learn about the expected module layout.


## Required Outputs

### 1. Complete Project Structure
```
rust/
├── Cargo.toml              # Main project configuration
├── build.rs                # Build script that orchestrates C/Rust compilation
├── wrapper.h               # Generated by build.rs - includes only active C headers
├── src/
│   ├── lib.rs             # Re-exports bindings and Rust modules
│   └── {module}/          # One directory per module 
│       └── mod.rs
├── fuzz/                  # Differential fuzz tests 
│   └── fuzz_{module}.rs
├── tests/
│   ├── abi_compat.rs      # Verify ABI compatibility 
│   └── {module}_test.rs   # Per-module tests 
├── c_src/                 # Original C source
```

### 2. `Cargo.toml` (Complete File)

```toml
[package]
name = "{project_name}"
version = "0.1.0"
edition = "2021"
authors = ["Your Name <you@example.com>"]
description = "Rust port of {project_name}"

[lib]
name = "{project_name}"
crate-type = ["staticlib", "rlib", "cdylib"]

[features]
default = []

# Expand this section, you'll have a Rust module feature for each module ported.
{for module in modules}
rust-{module} = []
{endfor}

# Convenience features
all-rust = [{comma_separated_rust_features}]

[dependencies]
libc = "0.2"

[build-dependencies]
cc = "1.1"
bindgen = "0.69"
glob = "0.3"

[dev-dependencies]
libfuzzer-sys = "0.4"
criterion = "0.5"

[profile.release]
lto = true

[profile.dev]
debug = true
```

### 3. `build.rs` 

```rust
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const C_SOURCE_DIR: &str = "{c_source_dir}";
const INCLUDE_DIRS: &[&str] = &{include_dirs_array};
const ALL_MODULES: &[&str] = &{modules_array};

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-env-changed=RUST_MODULES");
    
    // Step 1: Determine which modules are implemented in Rust
    let rust_modules = get_rust_modules();
    
    // Step 2: Generate wrapper.h with only C module headers
    generate_wrapper_header(&rust_modules);
    
    // Step 3: Build C library excluding Rust modules
    build_c_library(&rust_modules);
    
    // Step 4: Generate bindings from wrapper.h
    generate_bindings();
    
    // Step 5: Set up linking
    setup_linking();
}

fn get_rust_modules() -> Vec<String> {
    // First check environment variable
    if let Ok(modules) = env::var("RUST_MODULES") {
        modules.split(',')
            .map(|s| s.trim().to_string())
            .filter(|m| ALL_MODULES.contains(&m.as_str()))
            .collect()
    } else {
        // Fall back to checking which features are enabled
        ALL_MODULES.iter()
            .filter(|&&module| {
                env::var(format!("CARGO_FEATURE_RUST_{}", module.to_uppercase()))
                    .is_ok()
            })
            .map(|&s| s.to_string())
            .collect()
    }
}

fn generate_wrapper_header(rust_modules: &[String]) {
    let mut wrapper = String::from("#ifndef {project_name}_H\n#define {project_name}_H\n\n");
    
    // Include headers for modules NOT implemented in Rust
    for module in ALL_MODULES {
        if !rust_modules.contains(&module.to_string()) {
            // This is simplified - in reality you'd map module names to header files
            wrapper.push_str(&format!("#include \"{}.h\"\n", module));
        }
    }
    
    wrapper.push_str("\n#endif /* {project_name}_H */\n");
    fs::write("wrapper.h", wrapper).expect("Failed to write wrapper.h");
    
    println!("cargo:rerun-if-changed=wrapper.h");
}

fn build_c_library(excluded_modules: &[String]) {
    let mut build = cc::Build::new();
    
    // Add all C files except those from excluded modules
    for entry in glob::glob(&format!("{}/*.c", C_SOURCE_DIR)).unwrap() {
        if let Ok(path) = entry {
            let filename = path.file_stem().unwrap().to_str().unwrap();
            
            // Skip if this file belongs to an excluded module
            if !excluded_modules.iter().any(|module| filename.contains(module)) {
                build.file(path);
            }
        }
    }
    
    // Add include directories
    for dir in INCLUDE_DIRS {
        build.include(dir);
    }
    
    // Platform-specific settings
    if cfg!(target_os = "windows") {
        build.define("WIN32", None);
    }
    
    build.compile("{project_name}_c");
}

fn generate_bindings() {
    let bindings = bindgen::Builder::default()
        .header("wrapper.h")
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::default()))
        // Include all type definitions
        .allowlist_type(".*")
        .allowlist_function(".*")
        .allowlist_var(".*")
        // Generate bindings for inline functions
        .generate_inline_functions(true)
        // Derive useful traits
        .derive_default(true)
        .derive_debug(true)
        // Handle common C patterns
        .size_t_is_usize(true)
        .generate()
        .expect("Unable to generate bindings");

    let out_path = PathBuf::from(env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}

fn setup_linking() {
    // Link our compiled C library
    println!("cargo:rustc-link-lib=static={project_name}_c");
    
    // Platform-specific system libraries
    if cfg!(target_os = "windows") {
        println!("cargo:rustc-link-lib=ws2_32");
        println!("cargo:rustc-link-lib=bcrypt");
    } else {
        println!("cargo:rustc-link-lib=m");
        if cfg!(target_os = "linux") {
            println!("cargo:rustc-link-lib=dl");
        }
    }
}
```

### 4. `src/lib.rs` (Complete File)

```rust
//! Chimera build of {project_name} - mixed C/Rust implementation
//! 
//! This library provides a gradual migration path from C to Rust.
//! Modules can be implemented in either C or Rust, controlled by feature flags.

#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(improper_ctypes)]

// Bindgen-generated FFI bindings
pub mod bindings {
    include!(concat!(env!("OUT_DIR"), "/bindings.rs"));
}

// Re-export all bindings by default
// Rust implementations will override these when their features are enabled
pub use bindings::*;

// Conditionally include Rust implementations
{for module in modules}
#[cfg(feature = "rust-{module}")]
pub mod {module};

#[cfg(feature = "rust-{module}")]
pub use {module}::*;
{endfor}

// Initialization function if needed
pub fn init_chimera() {
    // Any global initialization required
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_bindings_available() {
        // Verify bindings were generated successfully
        // This will be expanded by module-specific tests
    }
}
```

#
### 6. `test_migration.sh` (Helper Script)

```bash
#!/bin/bash
set -e

echo "Testing {project_name} chimera build configurations..."

# Test pure C build
echo "Testing pure C build..."
cargo clean
cargo test

# Test individual Rust modules
{for module in modules}
echo "Testing with rust-{module}..."
cargo clean
RUST_MODULES={module} cargo test
{endfor}

# Test all Rust
echo "Testing all Rust modules..."
cargo clean
cargo test --all-features

echo "All configurations tested successfully!"
```

## Invariants That Must Hold

After running this prompt, the following invariants MUST be satisfied:

1. **Build Invariants**:
   - `cargo build` succeeds with no features (pure C build)
   - `cargo build --features rust-{module}` succeeds for each module
   - `cargo build --all-features` succeeds (all Rust build)
   - `RUST_MODULES={module} cargo build` succeeds for each module

2. **Symbol Invariants**:
   - No duplicate symbols when linking
   - Rust functions override C functions when enabled
   - All C functions are available when Rust module is disabled

3. **Bindgen Invariants**:
   - `wrapper.h` only includes headers for non-Rust modules
   - Bindings are generated for all C types and functions
   - No bindgen errors or warnings

4. **Testing Invariants**:
   - `cargo test` passes with any feature combination
   - Fuzz targets compile when their required features are enabled
   - Examples compile and run successfully

5. **File System Invariants**:
   - All directories in the structure exist
   - `c_src` contains or links to original C source
   - No generated files in version control (wrapper.h is regenerated)

6. **Cross-Platform Invariants**:
   - Build succeeds on Linux, macOS, and Windows
   - Correct system libraries are linked per platform
   - No hardcoded paths except those provided in input

## Validation

To verify the setup is correct:

```bash
# Should all succeed
cargo check
cargo check --features rust-dict
cargo check --all-features
RUST_MODULES=dict,list cargo check

# Should generate wrapper.h
cargo clean && cargo build
test -f wrapper.h

# Should show no undefined symbols
nm target/debug/lib{project_name}_chimera.a | grep -E "(dict|list)" | head -20
```

Generate ALL files listed above with the template values filled in based on the input configuration.
