use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::Instant;

const INCLUDE_DIRS: &[&str] = &[
    "..",                   // For config.h and libxml.h (first so they're found first)
    "../include",           // Main libxml2 headers
    "../include/libxml",    // Public headers  
];

// Mapping of module names to their C files
const MODULE_FILES: &[(&str, &[&str])] = &[
    ("xmlstring", &["xmlstring.c"]),
    ("chvalid", &["chvalid.c"]),
    ("dict", &["dict.c"]),
    ("hash", &["hash.c"]),
    ("list", &["list.c"]),
    ("buf", &["buf.c"]),
    ("xmlmemory", &["xmlmemory.c"]),
    ("error", &["error.c"]),
    ("threads", &["threads.c"]),
    ("encoding", &["encoding.c"]),
    ("xmlio", &["xmlIO.c"]),
    ("uri", &["uri.c"]),
    ("entities", &["entities.c"]),
    ("tree", &["tree.c", "timsort.h"]),
    ("xmlsave", &["xmlsave.c"]),
    ("parser-internals", &["parserInternals.c"]),
    ("parser", &["parser.c"]),
    ("sax2", &["SAX2.c"]),
    ("xpath", &["xpath.c"]),
    ("pattern", &["pattern.c"]),
    ("xpointer", &["xpointer.c"]),
    ("valid", &["valid.c"]),
    ("xmlregexp", &["xmlregexp.c"]),
    ("xmlschemas", &["xmlschemas.c"]),
    ("relaxng", &["relaxng.c"]),
    ("schematron", &["schematron.c"]),
    ("htmlparser", &["HTMLparser.c"]),
    ("htmltree", &["HTMLtree.c"]),
    ("xmlreader", &["xmlreader.c"]),
    ("xmlwriter", &["xmlwriter.c"]),
    ("c14n", &["c14n.c"]),
];

// Additional C files not covered by the main modules
const ADDITIONAL_C_FILES: &[&str] = &[
    "catalog.c", "debugXML.c", "globals.c", "nanohttp.c", 
    "xinclude.c", "xlink.c", "xmlmodule.c", "xmlschemastypes.c", "xzlib.c"
];

// Test binaries from CMakeLists.txt
const TEST_BINARIES: &[&str] = &[
    "runtest",
    "runxmlconf", 
    "runsuite",
    "testapi",
    "testchar",
    "testdict",
    "testModule",
    "testlimits",
    "testparser",
    "testrecurse",
];

fn main() {
    let build_start = Instant::now();
    println!("cargo:warning=Starting libxml2 build process...");
    
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-env-changed=RUST_MODULES");
    
    // Step 0: Ensure configure has been run and config files exist
    let step_start = Instant::now();
    ensure_configure_generated().expect("Failed to run configure");
    println!("cargo:warning=Configure step completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    // Step 1: Determine which modules are implemented in Rust
    let step_start = Instant::now();
    let rust_modules = get_rust_modules();
    println!("cargo:warning=Module detection completed in {:.2}s - {} Rust modules", 
             step_start.elapsed().as_secs_f64(), rust_modules.len());
    
    // Step 2: Generate wrapper.h with only C module headers
    let step_start = Instant::now();
    generate_wrapper_header(&rust_modules).expect("Failed to generate wrapper.h");
    println!("cargo:warning=Wrapper header generation completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    // Step 3: ALWAYS build pure C library for baseline testing
    let step_start = Instant::now();
    build_pure_c_library().expect("Failed to build C baseline");
    println!("cargo:warning=C baseline library build completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    // Step 4: Build hybrid library if Rust modules selected
    if !rust_modules.is_empty() {
        let step_start = Instant::now();
        build_hybrid_library(&rust_modules).expect("Failed to build hybrid");
        println!("cargo:warning=Hybrid library build completed in {:.2}s", step_start.elapsed().as_secs_f64());
    } else {
        println!("cargo:warning=Skipping hybrid library build (no Rust modules)");
    }
    
    // Step 5: Build test binaries against appropriate libraries
    let step_start = Instant::now();
    build_test_binaries(&rust_modules).expect("Failed to build tests");
    println!("cargo:warning=Test binaries build completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    // Step 6: Generate bindings with dynamic library support
    let step_start = Instant::now();
    generate_bindings_with_dynamic_support().expect("Failed to generate bindings");
    println!("cargo:warning=Bindings generation completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    // Step 7: Configure linking for final library selection
    let step_start = Instant::now();
    setup_conditional_linking(&rust_modules);
    println!("cargo:warning=Linking setup completed in {:.2}s", step_start.elapsed().as_secs_f64());
    
    println!("cargo:warning=Total build time: {:.2}s", build_start.elapsed().as_secs_f64());
}

fn get_rust_modules() -> Vec<String> {
    let mut rust_modules = Vec::new();
    
    // First check environment variable
    if let Ok(modules) = env::var("RUST_MODULES") {
        for module in modules.split(',') {
            let module = module.trim();
            if MODULE_FILES.iter().any(|(name, _)| *name == module) {
                rust_modules.push(module.to_string());
            }
        }
    }
    
    // Also check which features are enabled
    for (module, _) in MODULE_FILES {
        let feature_var = format!("CARGO_FEATURE_RUST_{}", module.to_uppercase().replace('-', "_"));
        if env::var(&feature_var).is_ok() {
            if !rust_modules.contains(&module.to_string()) {
                rust_modules.push(module.to_string());
            }
        }
    }
    
    rust_modules
}

fn ensure_configure_generated() -> Result<(), Box<dyn std::error::Error>> {
    let config_h_path = "../config.h";
    let xmlversion_h_path = "../include/libxml/xmlversion.h";
    let configure_path = "../configure";
    let configure_ac_path = "../configure.ac";

    // Check if both config.h and xmlversion.h exist
    let config_exists = std::path::Path::new(config_h_path).exists();
    let xmlversion_exists = std::path::Path::new(xmlversion_h_path).exists();

    // Check if configure needs to be re-run based on timestamps
    let needs_reconfigure = if config_exists && xmlversion_exists {
        let config_time = std::fs::metadata(config_h_path)?.modified()?;
        let xmlversion_time = std::fs::metadata(xmlversion_h_path)?.modified()?;
        
        // Check if configure.ac is newer than generated files
        if let Ok(configure_ac_meta) = std::fs::metadata(configure_ac_path) {
            let configure_ac_time = configure_ac_meta.modified()?;
            configure_ac_time > config_time || configure_ac_time > xmlversion_time
        } else {
            false
        }
    } else {
        true
    };

    if !config_exists || !xmlversion_exists || needs_reconfigure {
        if needs_reconfigure {
            println!("cargo:warning=Configure files are outdated, regenerating");
        } else {
            println!("cargo:warning=Configure files missing, generating");
        }
        
        println!("cargo:rerun-if-changed={}", configure_path);
        println!("cargo:rerun-if-changed=../configure.ac");
        println!("cargo:rerun-if-changed=../config.h.in");
        println!("cargo:rerun-if-changed=../include/libxml/xmlversion.h.in");

        // Check if configure script exists, if not run autogen.sh
        if !std::path::Path::new(configure_path).exists() {
            println!("cargo:warning=Configure script not found, running autogen.sh");
            let autogen_start = Instant::now();
            let autogen_output = Command::new("./autogen.sh")
                .current_dir("..")
                .output()?;
                
            if !autogen_output.status.success() {
                let stderr = String::from_utf8_lossy(&autogen_output.stderr);
                eprintln!("autogen.sh failed with error: {}", stderr);
                return Err(format!("autogen.sh failed: {}", stderr).into());
            }
            println!("cargo:warning=autogen.sh completed in {:.2}s", autogen_start.elapsed().as_secs_f64());
        }

        println!("cargo:warning=Running configure to generate config files");
        let configure_start = Instant::now();
        
        // Run configure from the parent directory
        let output = Command::new("./configure")
            .current_dir("..")
            .arg("--disable-shared")
            .arg("--enable-static")
            .arg("--disable-dependency-tracking")
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            eprintln!("Configure failed with error: {}", stderr);
            return Err(format!("Configure script failed: {}", stderr).into());
        }

        // Verify the files were created
        if !std::path::Path::new(config_h_path).exists() {
            return Err("config.h was not generated by configure".into());
        }
        if !std::path::Path::new(xmlversion_h_path).exists() {
            return Err("xmlversion.h was not generated by configure".into());
        }

        println!("cargo:warning=Configure completed in {:.2}s", configure_start.elapsed().as_secs_f64());
    } else {
        println!("cargo:warning=Configure files up to date, skipping");
    }

    Ok(())
}

fn generate_wrapper_header(_rust_modules: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let wrapper_path = "wrapper.h";
    
    // Include all public libxml2 headers for complete bindgen coverage
    let public_headers = [
        "libxml/xmlexports.h",
        "libxml/xmlversion.h", 
        "libxml/xmlerror.h",
        "libxml/globals.h",
        "libxml/xmlmemory.h",
        "libxml/xmlstring.h",
        "libxml/dict.h",
        "libxml/hash.h",
        "libxml/list.h",
        "libxml/threads.h",
        "libxml/chvalid.h",
        "libxml/encoding.h",
        "libxml/xmlIO.h",
        "libxml/uri.h",
        "libxml/entities.h",
        "libxml/tree.h",
        "libxml/xmlsave.h",
        "libxml/parserInternals.h", 
        "libxml/parser.h",
        "libxml/SAX.h",
        "libxml/SAX2.h",
        "libxml/xpath.h",
        "libxml/xpathInternals.h",
        "libxml/pattern.h",
        "libxml/xpointer.h",
        "libxml/valid.h",
        "libxml/xmlregexp.h",
        "libxml/xmlschemas.h",
        "libxml/xmlschemastypes.h",
        "libxml/schemasInternals.h",
        "libxml/relaxng.h",
        "libxml/schematron.h",
        "libxml/HTMLparser.h",
        "libxml/HTMLtree.h",
        "libxml/xmlreader.h",
        "libxml/xmlwriter.h",
        "libxml/c14n.h",
        "libxml/catalog.h",
        "libxml/debugXML.h",
        "libxml/xinclude.h",
        "libxml/xlink.h",
        "libxml/xmlmodule.h",
        "libxml/xmlautomata.h",
        "libxml/xmlunicode.h",
        "libxml/nanoftp.h",
        "libxml/nanohttp.h",
    ];
    
    // Check if wrapper needs regeneration
    let needs_regeneration = if std::path::Path::new(wrapper_path).exists() {
        let wrapper_time = std::fs::metadata(wrapper_path)?.modified()?;
        
        // Check if any header file is newer than wrapper.h
        public_headers.iter().any(|header| {
            let header_path = format!("../include/{}", header);
            if let Ok(header_meta) = std::fs::metadata(&header_path) {
                if let Ok(header_time) = header_meta.modified() {
                    header_time > wrapper_time
                } else { true }
            } else { false }
        })
    } else {
        true
    };
    
    if needs_regeneration {
        println!("cargo:warning=Regenerating wrapper.h due to header changes");
        
        let mut wrapper = String::from("#ifndef LIBXML2_WRAPPER_H\n#define LIBXML2_WRAPPER_H\n\n");
        
        for header in &public_headers {
            wrapper.push_str(&format!("#include \"{}\"\n", header));
        }
        
        wrapper.push_str("\n#endif /* LIBXML2_WRAPPER_H */\n");
        
        fs::write(wrapper_path, wrapper)?;
    } else {
        println!("cargo:warning=Wrapper header up to date, skipping");
    }
    
    // Add rerun triggers for all headers
    for header in &public_headers {
        let header_path = format!("../include/{}", header);
        println!("cargo:rerun-if-changed={}", header_path);
    }
    println!("cargo:rerun-if-changed={}", wrapper_path);
    
    Ok(())
}

fn build_pure_c_library() -> Result<(), Box<dyn std::error::Error>> {
    // Build ALL C sources (no exclusions)
    // Output: libxml2_c.a (complete C implementation)
    // Purpose: Baseline for fuzz testing
    let out_dir = env::var("OUT_DIR")?;
    let out_path = PathBuf::from(&out_dir);
    
    // Collect ALL C files to compile
    let mut c_files = Vec::new();
    
    // Add all module files
    for (_, files) in MODULE_FILES {
        for file in *files {
            if file.ends_with(".c") {
                let full_path = format!("../{}", file);
                if std::path::Path::new(&full_path).exists() {
                    println!("cargo:rerun-if-changed={}", full_path);
                    c_files.push(full_path);
                }
            }
        }
    }
    
    // Add additional C files
    for file in ADDITIONAL_C_FILES {
        let full_path = format!("../{}", file);
        if std::path::Path::new(&full_path).exists() {
            println!("cargo:rerun-if-changed={}", full_path);
            c_files.push(full_path);
        }
    }
    
    compile_c_library(&c_files, "libxml2_c")
}

fn build_hybrid_library(rust_modules: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    // Build C sources EXCLUDING Rust-replaced modules
    // Output: libxml2_hybrid.a (C + Rust FFI symbols)
    // Purpose: Integration testing with C test suite
    let out_dir = env::var("OUT_DIR")?;
    let out_path = PathBuf::from(&out_dir);
    
    // Create mapping of C files to modules for exclusion
    let mut excluded_files = std::collections::HashSet::new();
    for module in rust_modules {
        if let Some((_, files)) = MODULE_FILES.iter().find(|(name, _)| *name == module) {
            for file in *files {
                excluded_files.insert(*file);
            }
        }
    }
    
    // Collect C files to compile (excluding Rust modules)
    let mut c_files = Vec::new();
    
    // Add module files that aren't excluded
    for (_, files) in MODULE_FILES {
        for file in *files {
            if !excluded_files.contains(file) && file.ends_with(".c") {
                let full_path = format!("../{}", file);
                if std::path::Path::new(&full_path).exists() {
                    println!("cargo:rerun-if-changed={}", full_path);
                    c_files.push(full_path);
                }
            }
        }
    }
    
    // Add additional C files
    for file in ADDITIONAL_C_FILES {
        let full_path = format!("../{}", file);
        if std::path::Path::new(&full_path).exists() {
            println!("cargo:rerun-if-changed={}", full_path);
            c_files.push(full_path);
        }
    }
    
    compile_c_library(&c_files, "libxml2_hybrid")
}

fn compile_c_library(c_files: &[String], lib_name: &str) -> Result<(), Box<dyn std::error::Error>> {
    let out_dir = env::var("OUT_DIR")?;
    let out_path = PathBuf::from(&out_dir);
    
    println!("cargo:warning=Building {} with {} C files", lib_name, c_files.len());
    
    // Build each C file to object file individually
    let mut object_files = Vec::new();
    let mut compiled_count = 0;
    let mut skipped_count = 0;
    
    for c_file in c_files {
        let obj_name = format!("{}.o", 
            std::path::Path::new(c_file)
                .file_stem()
                .unwrap()
                .to_str()
                .unwrap()
        );
        let obj_path = out_path.join(&obj_name);
        
        // Check if we need to rebuild this object file
        let c_path = std::path::Path::new(c_file);
        let should_rebuild = if obj_path.exists() {
            let c_time = c_path.metadata()?.modified()?;
            let obj_time = obj_path.metadata()?.modified()?;
            c_time > obj_time
        } else {
            true
        };
        
        if should_rebuild {
            let compile_start = Instant::now();
            
            // Compile to object file using direct cc command
            let mut cc_cmd = std::process::Command::new("cc");
            cc_cmd.args(&[
                "-c",
                "-fPIC",  // Position-independent code for dynamic linking
                "-o", obj_path.to_str().unwrap(),
                c_file,
                "-I", "..",
                "-I", "../include", 
                "-I", "../include/libxml",
                "-I", ".",
                "-DHAVE_CONFIG_H",
                "-DLIBXML_STATIC",
                "-D_GNU_SOURCE",
                "-D_DEFAULT_SOURCE",
                "-Wno-unused-function",
                "-Wno-implicit-function-declaration",
                "-Wno-error=implicit-function-declaration",
                "-Wno-format-extra-args",
            ]);
            
            let cc_status = cc_cmd.status()?;
            if !cc_status.success() {
                return Err(format!("Failed to compile {} to object file", c_file).into());
            }
            
            compiled_count += 1;
            println!("cargo:warning=Compiled {} in {:.3}s", 
                     std::path::Path::new(c_file).file_name().unwrap().to_str().unwrap(),
                     compile_start.elapsed().as_secs_f64());
        } else {
            skipped_count += 1;
        }
        
        object_files.push(obj_path);
    }
    
    println!("cargo:warning=Compilation: {} built, {} up-to-date", compiled_count, skipped_count);
    
    // Create static library from object files
    let static_lib_path = out_path.join(&format!("lib{}.a", lib_name));
    
    // Check if static library needs rebuilding
    let should_rebuild_static = if static_lib_path.exists() {
        let static_time = static_lib_path.metadata()?.modified()?;
        object_files.iter().any(|obj_path| {
            if let Ok(obj_meta) = obj_path.metadata() {
                if let Ok(obj_time) = obj_meta.modified() {
                    obj_time > static_time
                } else { true }
            } else { true }
        })
    } else {
        true
    };
    
    if should_rebuild_static {
        let ar_start = Instant::now();
        println!("cargo:warning=Creating static library {}", lib_name);
        
        // Use ar to create the static library
        let mut ar_cmd = std::process::Command::new("ar");
        ar_cmd.arg("rcs").arg(&static_lib_path);
        
        for obj_file in &object_files {
            ar_cmd.arg(obj_file);
        }
        
        let ar_status = ar_cmd.status()?;
        if !ar_status.success() {
            return Err("Failed to create static library with ar".into());
        }
        
        println!("cargo:warning=Static library created in {:.3}s at {}", 
                 ar_start.elapsed().as_secs_f64(), static_lib_path.display());
    } else {
        println!("cargo:warning=Static library {} up to date", lib_name);
    }
    
    // Also create dynamic library for differential testing
    if lib_name == "libxml2_c" {
        let dynamic_lib_path = out_path.join("liblibxml2_c.so");
        
        let should_rebuild_dynamic = if dynamic_lib_path.exists() {
            let dynamic_time = dynamic_lib_path.metadata()?.modified()?;
            let static_time = static_lib_path.metadata()?.modified()?;
            static_time > dynamic_time
        } else {
            true
        };
        
        if should_rebuild_dynamic {
            let gcc_start = Instant::now();
            println!("cargo:warning=Creating dynamic library for differential testing");
            
            let mut gcc_cmd = std::process::Command::new("gcc");
            gcc_cmd.args(&[
                "-shared",
                "-fPIC",
                "-o", dynamic_lib_path.to_str().unwrap(),
                "-Wl,--whole-archive",
                static_lib_path.to_str().unwrap(),
                "-Wl,--no-whole-archive",
                "-lm", "-ldl", "-lpthread"
            ]);
            
            let gcc_status = gcc_cmd.status()?;
            if !gcc_status.success() {
                return Err("Failed to create dynamic library with gcc".into());
            }
            
            println!("cargo:warning=Dynamic library created in {:.3}s at {}", 
                     gcc_start.elapsed().as_secs_f64(), dynamic_lib_path.display());
        } else {
            println!("cargo:warning=Dynamic library up to date");
        }
    }
    
    Ok(())
}

fn configure_build_defines(build: &mut cc::Build) {
    // Basic compilation flags
    build.flag("-Wno-unused-function");
    build.flag("-Wno-implicit-function-declaration");
    build.flag("-Wno-error=implicit-function-declaration");
    build.flag("-Wno-format-extra-args");
    build.flag("-DLIBXML_STATIC");
    
    // Platform-specific base defines
    if cfg!(target_os = "windows") {
        build.define("WIN32", None);
        build.define("_WINDOWS", None);
    } else {
        // Enable config.h which contains all the feature detection
        build.define("HAVE_CONFIG_H", None);
        build.define("_GNU_SOURCE", None);
        build.define("_DEFAULT_SOURCE", None);
    }
    
    // Note: LIBXML_MODULE_EXTENSION is now defined in xmlversion.h, no need to duplicate
}

fn generate_bindings_with_dynamic_support() -> Result<(), Box<dyn std::error::Error>> {
    let out_path = PathBuf::from(env::var("OUT_DIR")?);
    let static_bindings_path = out_path.join("static_bindings.rs");
    let dynamic_bindings_path = out_path.join("dynamic_bindings.rs");
    let wrapper_path = std::path::Path::new("wrapper.h");
    
    // Check if bindings need regeneration based on wrapper.h timestamp
    let needs_regeneration = if static_bindings_path.exists() && dynamic_bindings_path.exists() {
        let wrapper_time = wrapper_path.metadata()?.modified()?;
        let static_time = static_bindings_path.metadata()?.modified()?;
        let dynamic_time = dynamic_bindings_path.metadata()?.modified()?;
        wrapper_time > static_time || wrapper_time > dynamic_time
    } else {
        true
    };
    
    if needs_regeneration {
        println!("cargo:warning=Generating Rust bindings");
        let bindgen_start = Instant::now();
        
        // Static bindings (for hybrid library)
        let static_start = Instant::now();
        let static_bindings = bindgen::Builder::default()
            .header("wrapper.h")
            .parse_callbacks(Box::new(bindgen::CargoCallbacks::default()))
            .clang_arg("-I../include")
            .clang_arg("-I../include/libxml")
            .clang_arg("-I..")
            .clang_arg("-DHAVE_CONFIG_H")
            .clang_arg("-DLIBXML_STATIC")
            .allowlist_type(".*xml.*")
            .allowlist_type(".*HTML.*") 
            .allowlist_type(".*LIBXML_.*")
            .allowlist_function(".*xml.*")
            .allowlist_function(".*HTML.*")
            .allowlist_var(".*xml.*")
            .allowlist_var(".*LIBXML_.*")
            .derive_default(true)
            .derive_debug(true)
            .size_t_is_usize(true)
            .generate()?;
        
        static_bindings.write_to_file(&static_bindings_path)?;
        println!("cargo:warning=Static bindings generated in {:.3}s", static_start.elapsed().as_secs_f64());
        
        // Dynamic bindings (for baseline testing)
        let dynamic_start = Instant::now();
        let dynamic_bindings = bindgen::Builder::default()
            .header("wrapper.h")
            .parse_callbacks(Box::new(bindgen::CargoCallbacks::default()))
            .clang_arg("-I../include")
            .clang_arg("-I../include/libxml")
            .clang_arg("-I..")
            .clang_arg("-DHAVE_CONFIG_H")
            .clang_arg("-DLIBXML_DYNAMIC")  // Different define for dynamic
            .allowlist_type(".*xml.*")
            .allowlist_type(".*HTML.*") 
            .allowlist_type(".*LIBXML_.*")
            .allowlist_function(".*xml.*")
            .allowlist_function(".*HTML.*")
            .allowlist_var(".*xml.*")
            .allowlist_var(".*LIBXML_.*")
            .dynamic_library_name("libxml2_c")
            .derive_default(true)
            .derive_debug(true)
            .size_t_is_usize(true)
            .generate()?;
        
        dynamic_bindings.write_to_file(&dynamic_bindings_path)?;
        println!("cargo:warning=Dynamic bindings generated in {:.3}s", dynamic_start.elapsed().as_secs_f64());
        
        println!("cargo:warning=Bindings generation completed in {:.3}s", bindgen_start.elapsed().as_secs_f64());
    } else {
        println!("cargo:warning=Bindings up to date, skipping generation");
    }
    
    Ok(())
}

fn build_test_binaries(rust_modules: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let out_dir = env::var("OUT_DIR")?;
    let mut built_count = 0;
    let mut skipped_count = 0;
    
    println!("cargo:warning=Building test binaries");
    
    for test_name in TEST_BINARIES {
        let test_c_file = format!("../{}.c", test_name);
        
        // Check if the test C file exists
        if !std::path::Path::new(&test_c_file).exists() {
            println!("cargo:warning=Test file {} not found, skipping", test_c_file);
            continue;
        }
        
        println!("cargo:rerun-if-changed={}", test_c_file);
        
        // ALWAYS build test binaries against pure C library during build script execution
        // This ensures Rust symbols aren't needed at build time, even when Rust modules are enabled
        let binary_name = if rust_modules.is_empty() {
            format!("{}_c", test_name)
        } else {
            // When Rust modules are enabled, still use pure C for build-time tests
            // Runtime differential testing will use the hybrid library via other mechanisms
            format!("{}_buildtime", test_name)
        };
        let binary_path = PathBuf::from(&out_dir).join(&binary_name);
        
        if build_single_test_binary(&test_c_file, &binary_path, test_name, "libxml2_c")? {
            built_count += 1;
        } else {
            skipped_count += 1;
        }
        
        // Set environment variables for test binaries
        if rust_modules.is_empty() {
            // Pure C build - standard naming
            let c_env_var = format!("TEST_{}_C_BINARY", test_name.to_uppercase());
            println!("cargo:rustc-env={}={}", c_env_var, binary_path.display());
        } else {
            // Hybrid build - build-time test uses pure C library
            let buildtime_env_var = format!("TEST_{}_BUILDTIME_BINARY", test_name.to_uppercase());
            println!("cargo:rustc-env={}={}", buildtime_env_var, binary_path.display());
            
            // Also set the C binary env var to point to the same binary for compatibility
            let c_env_var = format!("TEST_{}_C_BINARY", test_name.to_uppercase());
            println!("cargo:rustc-env={}={}", c_env_var, binary_path.display());
        }
    }
    
    println!("cargo:warning=Test binaries: {} built, {} up-to-date", built_count, skipped_count);
    Ok(())
}

fn build_single_test_binary(test_c_file: &str, binary_path: &PathBuf, test_name: &str, lib_name: &str) -> Result<bool, Box<dyn std::error::Error>> {
    let out_dir = env::var("OUT_DIR")?;
    let lib_path = PathBuf::from(&out_dir).join(&format!("lib{}.a", lib_name));
    
    // Check if binary needs rebuilding
    let should_rebuild = if binary_path.exists() {
        let binary_time = binary_path.metadata()?.modified()?;
        let test_time = std::fs::metadata(test_c_file)?.modified()?;
        let lib_time = lib_path.metadata()?.modified()?;
        test_time > binary_time || lib_time > binary_time
    } else {
        true
    };
    
    if should_rebuild {
        let build_start = Instant::now();
        
        // Use cc to compile the test binary, linking against specified library
        let mut cmd = std::process::Command::new("cc");
        cmd.args(&[
            "-o", binary_path.to_str().unwrap(),
            test_c_file,
            "-include", "../libxml.h",  // Force include libxml.h first to get XML_HIDDEN
            "-I", "..",
            "-I", "../include", 
            "-I", "../include/libxml",
            "-I", ".",
            "-DHAVE_CONFIG_H",
            "-DLIBXML_STATIC",
            "-D_GNU_SOURCE",
            "-D_DEFAULT_SOURCE",
            "-Wno-unused-function",
            "-Wno-format-extra-args",
            "-Wno-implicit-function-declaration",
            "-Wno-error=implicit-function-declaration",
            "-Wno-format-extra-args",
        ]);
        
        // Add link arguments including our static library
        let link_args = get_test_link_args(test_name);
        
        // Link against specified library
        cmd.arg("-L").arg(&out_dir);
        cmd.arg(&format!("-l{}", lib_name));
        cmd.args(&link_args);
        
        let status = cmd.status()?;
            
        if !status.success() {
            return Err(format!("Failed to compile test binary: {} with {}", test_name, lib_name).into());
        }
        
        println!("cargo:warning=Built test {} with {} in {:.3}s", 
                 test_name, lib_name, build_start.elapsed().as_secs_f64());
        Ok(true)
    } else {
        Ok(false)
    }
}

fn get_test_link_args(test_name: &str) -> Vec<&str> {
    let mut args = vec![
        "-lm",  // Math library
    ];
    
    // Add platform-specific libraries
    if cfg!(target_os = "linux") {
        args.push("-ldl");
        args.push("-lpthread");
    }
    
    // Special cases for specific tests
    match test_name {
        "runtest" => {
            if cfg!(not(target_os = "windows")) {
                args.push("-pthread");
            }
        },
        _ => {}
    }
    
    args
}

fn setup_conditional_linking(rust_modules: &[String]) {
    let out_dir = env::var("OUT_DIR").unwrap();
    
    // Add search path for our static libraries
    println!("cargo:rustc-link-search=native={}", out_dir);
    
    if rust_modules.is_empty() {
        // Pure C build
        println!("cargo:rustc-link-lib=static=libxml2_c");
        println!("cargo:rustc-env=LIBXML2_VARIANT=c");
    } else {
        // Hybrid build
        println!("cargo:rustc-link-lib=static=libxml2_hybrid");
        println!("cargo:rustc-env=LIBXML2_VARIANT=hybrid");
    }
    
    // Platform-specific system libraries
    if cfg!(target_os = "windows") {
        println!("cargo:rustc-link-lib=ws2_32");
        println!("cargo:rustc-link-lib=bcrypt");
    } else {
        println!("cargo:rustc-link-lib=m");
        if cfg!(target_os = "linux") {
            println!("cargo:rustc-link-lib=dl");
            println!("cargo:rustc-link-lib=pthread");
        }
    }
}