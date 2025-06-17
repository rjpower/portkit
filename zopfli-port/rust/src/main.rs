use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::process;

use zopfli::ffi::ZopfliOptions;
use zopfli::zopfli::ZopfliFormat;
use zopfli::zopfli_lib::ZopfliCompress;

fn print_usage(program_name: &str) {
    eprintln!("Usage: {} [OPTIONS] [INPUT_FILE] [OUTPUT_FILE]", program_name);
    eprintln!();
    eprintln!("Options:");
    eprintln!("  -f, --format FORMAT    Output format: gzip, zlib, deflate (default: gzip)");
    eprintln!("  -i NUM                 Number of iterations (default: 15)");
    eprintln!("  --i-gzip NUM           Iterations for gzip format");
    eprintln!("  --i-deflate NUM        Iterations for deflate format");
    eprintln!("  --i-zlib NUM           Iterations for zlib format");
    eprintln!("  -h, --help             Show this help message");
    eprintln!();
    eprintln!("If no input file is specified, reads from stdin.");
    eprintln!("If no output file is specified, writes to stdout.");
}

fn parse_format(format_str: &str) -> Result<ZopfliFormat, String> {
    match format_str.to_lowercase().as_str() {
        "gzip" => Ok(ZopfliFormat::ZOPFLI_FORMAT_GZIP),
        "zlib" => Ok(ZopfliFormat::ZOPFLI_FORMAT_ZLIB),
        "deflate" => Ok(ZopfliFormat::ZOPFLI_FORMAT_DEFLATE),
        _ => Err(format!("Unknown format: {}. Use gzip, zlib, or deflate.", format_str)),
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let program_name = &args[0];
    
    let mut format = ZopfliFormat::ZOPFLI_FORMAT_GZIP;
    let mut options = ZopfliOptions {
        verbose: 0,
        verbose_more: 0,
        numiterations: 15,
        blocksplitting: 1,
        blocksplittinglast: 0,
        blocksplittingmax: 15,
    };
    let mut input_file: Option<String> = None;
    let mut output_file: Option<String> = None;
    
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => {
                print_usage(program_name);
                return;
            }
            "-f" | "--format" => {
                if i + 1 >= args.len() {
                    eprintln!("Error: {} requires an argument", args[i]);
                    process::exit(1);
                }
                i += 1;
                match parse_format(&args[i]) {
                    Ok(f) => format = f,
                    Err(e) => {
                        eprintln!("Error: {}", e);
                        process::exit(1);
                    }
                }
            }
            "-i" => {
                if i + 1 >= args.len() {
                    eprintln!("Error: -i requires an argument");
                    process::exit(1);
                }
                i += 1;
                match args[i].parse::<i32>() {
                    Ok(n) if n > 0 => options.numiterations = n,
                    _ => {
                        eprintln!("Error: -i requires a positive integer");
                        process::exit(1);
                    }
                }
            }
            "--i-gzip" => {
                if i + 1 >= args.len() {
                    eprintln!("Error: --i-gzip requires an argument");
                    process::exit(1);
                }
                i += 1;
                match args[i].parse::<i32>() {
                    Ok(n) if n > 0 => {
                        if format == ZopfliFormat::ZOPFLI_FORMAT_GZIP {
                            options.numiterations = n;
                        }
                    }
                    _ => {
                        eprintln!("Error: --i-gzip requires a positive integer");
                        process::exit(1);
                    }
                }
            }
            "--i-deflate" => {
                if i + 1 >= args.len() {
                    eprintln!("Error: --i-deflate requires an argument");
                    process::exit(1);
                }
                i += 1;
                match args[i].parse::<i32>() {
                    Ok(n) if n > 0 => {
                        if format == ZopfliFormat::ZOPFLI_FORMAT_DEFLATE {
                            options.numiterations = n;
                        }
                    }
                    _ => {
                        eprintln!("Error: --i-deflate requires a positive integer");
                        process::exit(1);
                    }
                }
            }
            "--i-zlib" => {
                if i + 1 >= args.len() {
                    eprintln!("Error: --i-zlib requires an argument");
                    process::exit(1);
                }
                i += 1;
                match args[i].parse::<i32>() {
                    Ok(n) if n > 0 => {
                        if format == ZopfliFormat::ZOPFLI_FORMAT_ZLIB {
                            options.numiterations = n;
                        }
                    }
                    _ => {
                        eprintln!("Error: --i-zlib requires a positive integer");
                        process::exit(1);
                    }
                }
            }
            arg if arg.starts_with('-') => {
                eprintln!("Error: Unknown option: {}", arg);
                print_usage(program_name);
                process::exit(1);
            }
            _ => {
                if input_file.is_none() {
                    input_file = Some(args[i].clone());
                } else if output_file.is_none() {
                    output_file = Some(args[i].clone());
                } else {
                    eprintln!("Error: Too many arguments");
                    print_usage(program_name);
                    process::exit(1);
                }
            }
        }
        i += 1;
    }
    
    // Read input data
    let input_data = match input_file {
        Some(filename) => {
            match fs::read(&filename) {
                Ok(data) => data,
                Err(e) => {
                    eprintln!("Error reading file '{}': {}", filename, e);
                    process::exit(1);
                }
            }
        }
        None => {
            let mut buffer = Vec::new();
            match io::stdin().read_to_end(&mut buffer) {
                Ok(_) => buffer,
                Err(e) => {
                    eprintln!("Error reading from stdin: {}", e);
                    process::exit(1);
                }
            }
        }
    };
    
    if input_data.is_empty() {
        eprintln!("Warning: Input is empty");
    }
    
    // Compress the data
    let mut output_data = Vec::new();
    ZopfliCompress(&options, format, &input_data, &mut output_data);
    
    // Write output data
    match output_file {
        Some(filename) => {
            if let Err(e) = fs::write(&filename, &output_data) {
                eprintln!("Error writing file '{}': {}", filename, e);
                process::exit(1);
            }
        }
        None => {
            if let Err(e) = io::stdout().write_all(&output_data) {
                eprintln!("Error writing to stdout: {}", e);
                process::exit(1);
            }
        }
    }
    
    // Print compression statistics to stderr
    let compression_ratio = if input_data.is_empty() {
        0.0
    } else {
        output_data.len() as f64 / input_data.len() as f64
    };
    
    eprintln!("Original size: {} bytes", input_data.len());
    eprintln!("Compressed size: {} bytes", output_data.len());
    eprintln!("Compression ratio: {:.3}", compression_ratio);
    eprintln!("Space savings: {:.1}%", (1.0 - compression_ratio) * 100.0);
}