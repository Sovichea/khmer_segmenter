use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use std::path::Path;
use std::time::Instant;
use rayon::prelude::*;

use khmer_segmenter::khmer_segmenter::{KhmerSegmenter, SegmenterConfig};


fn main() -> io::Result<()> {
    // Config defaults
    let mut config = SegmenterConfig::default();
    let mut input_files = Vec::new();
    let mut output_file: Option<String> = None;
    let mut input_text: Option<String> = None;
    let mut mode_benchmark = false;
    let mut threads = 4;
    let mut limit: i32 = -1;

    let args: Vec<String> = env::args().collect();
    let mut i = 1;
    while i < args.len() {
        let arg = &args[i];
        if arg == "--benchmark" || arg == "--bench" {
            mode_benchmark = true;
            eprintln!("DEBUG: Set benchmark match {}", arg);
        } else if arg == "--input" || arg == "--file" {
            eprintln!("DEBUG: Found input flag at {}", i);
            while i + 1 < args.len() && !args[i+1].starts_with('-') {
                eprintln!("DEBUG: Pushing input file: {}", args[i+1]);
                input_files.push(args[i+1].clone());
                i += 1;
            }
        } else if arg == "--output" {
            if i + 1 < args.len() {
                output_file = Some(args[i+1].clone());
                i += 1;
            }
        } else if arg == "--threads" {
            if i + 1 < args.len() {
                threads = args[i+1].parse().unwrap_or(4);
                i += 1;
            }
        } else if arg == "--limit" {
             if i + 1 < args.len() {
                limit = args[i+1].parse().unwrap_or(-1);
                i += 1;
            }
        } else if arg == "--no-norm" {
            config.enable_normalization = false;
        } else if arg == "--no-repair" {
            config.enable_repair_mode = false;
        } else if arg == "--no-acronym" {
            config.enable_acronym_detection = false;
        } else if arg == "--no-merging" {
            config.enable_unknown_merging = false;
        } else if arg == "--no-freq" {
            config.enable_frequency_costs = false; // Not used in binary dict but kept for compat
        } else if !arg.starts_with('-') {
            if let Some(ref mut text) = input_text {
                text.push(' ');
                text.push_str(arg);
            } else {
                input_text = Some(arg.clone());
            }
        }
        i += 1;
    }

    
    eprintln!("DEBUG: Args: {:?}", args);
    eprintln!("DEBUG: Parsed Input Files: {:?}", input_files);
    eprintln!("DEBUG: Benchmark Mode: {}", mode_benchmark);

    if !input_files.is_empty() && output_file.is_none() {
        output_file = Some("segmentation_results.txt".to_string());
    }

    // Locate Dictionary
    let dict_paths = [
        "khmer_dictionary.kdict",
        "../../port/common/khmer_dictionary.kdict",
        "../common/khmer_dictionary.kdict", // Just in case
        "c:/Users/Sovichea/Documents/git/khmer_segmenter/port/common/khmer_dictionary.kdict", // Absolute fallback
    ];
    
    let mut dict_path: Option<&str> = None;
    for p in &dict_paths {
        if Path::new(p).exists() {
            dict_path = Some(p);
            break;
        }
    }

    if mode_benchmark || !input_files.is_empty() {
        eprintln!("Initializing segmenter (Dict: {:?})...", dict_path);
    }

    let seg = match KhmerSegmenter::new(dict_path, config) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to init segmenter: {}", e);
            return Ok(());
        }
    };
    
    if mode_benchmark || !input_files.is_empty() {
        eprintln!("Initialization complete.");
    }

    // Set thread pool? Rayon auto-configures but we can force it if we want strict control.
    rayon::ThreadPoolBuilder::new().num_threads(threads).build_global().unwrap();

    if mode_benchmark {
        if !input_files.is_empty() {
            let mut lines = Vec::new();
            let mut current_limit = limit;
            
            eprintln!("DEBUG: Input files: {:?}", input_files);
            
            for file in &input_files {
                 eprintln!("DEBUG: Reading file: {}", file);
                 let f = File::open(file)?;
                 let reader = BufReader::new(f);
                 for line in reader.lines() {
                     if limit != -1 && current_limit <= 0 { break; }
                     if let Ok(l) = line {
                         // Remove BOM
                         let clean = if l.starts_with("\u{FEFF}") {
                             l.chars().skip(1).collect()
                         } else {
                             l
                         };
                         lines.push(clean);
                         if limit != -1 { current_limit -= 1; }
                     }
                 }
                 if limit != -1 && current_limit <= 0 { break; }
            }
            
            eprintln!("DEBUG: Read {} lines", lines.len());
            eprintln!("\n--- Input Benchmark ({} lines) ---", lines.len());
            
            // 1. Sequential
            eprint!("[1 Thread] Processing...");
            let start = Instant::now();
            let results_seq: Vec<String> = lines.iter()
                .map(|l| seg.segment(l, Some(" | ")))
                .collect();
            let duration = start.elapsed();
            eprintln!(" Done in {:.3}s ({:.2} lines/sec)", duration.as_secs_f64(), lines.len() as f64 / duration.as_secs_f64());
            
            if let Some(out_path) = &output_file {
                 let mut f = File::create(out_path)?;
                 for (orig, res) in lines.iter().zip(results_seq.iter()) {
                     writeln!(f, "Original:  {}", orig)?;
                     writeln!(f, "Segmented: {}", res)?;
                     writeln!(f, "----------------------------------------")?;
                 }
                 eprintln!("Results saved to {}", out_path);
            }

            // 2. Parallel
            if threads > 1 {
                eprint!("[{} Threads] Processing...", threads);
                let start = Instant::now();
                let _results_par: Vec<String> = lines.par_iter()
                    .map(|l| seg.segment(l, Some(" | ")))
                    .collect();
                let duration_par = start.elapsed();
                eprintln!(" Done in {:.3}s ({:.2} lines/sec)", duration_par.as_secs_f64(), lines.len() as f64 / duration_par.as_secs_f64());
                eprintln!("Speedup: {:.2}x", duration.as_secs_f64() / duration_par.as_secs_f64());
            }

        } else {
             // Standard text benchmark
             let text = "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។";
             let iterations_seq = 1000;
             let iterations_conc = 5000;
             
             println!("\n--- Benchmark Suite ---");
             println!("Text Length: {} chars", text.chars().count()); // C uses strlen (bytes)? Yes.
             
             // Warmup
             let check = seg.segment(text, Some(" | "));
             println!("\n[Output Check]\n{}\n", check);
             
             if let Some(out_path) = output_file {
                 let mut f = File::create(out_path)?;
                 writeln!(f, "Original:  {}", text)?;
                 writeln!(f, "Segmented: {}", check)?;
                 writeln!(f, "----------------------------------------")?;
             } else {
                  let mut f = File::create("benchmark_results.txt")?;
                  writeln!(f, "Original:  {}", text)?;
                  writeln!(f, "Segmented: {}", check)?;
                  writeln!(f, "----------------------------------------")?;
             }
             
             // Sequential
             println!("\n[Sequential] Running {} iterations...", iterations_seq);
             let start = Instant::now();
             for _ in 0..iterations_seq {
                 let _ = seg.segment(text, None); // NULL separator in C means "no separator"? No, C uses default if NULL. BUT benchmark passes NULL?
                 // In C benchmark loop: khmer_segmenter_segment(seg, text, NULL);
                 // In C khmer_segmenter_segment: if (!separator) separator = "\xE2\x80\x8B";
                 // In Rust segment: if separator is None, use ZWS.
             }
             let duration = start.elapsed();
             println!("Time: {:.3}s", duration.as_secs_f64());
             println!("Avg: {:.3} ms/call", (duration.as_secs_f64() * 1000.0) / iterations_seq as f64);
             
             // Concurrent
             println!("\n[Concurrent] Running {} iterations with {} threads...", iterations_conc, threads);
             let start = Instant::now();
             (0..iterations_conc).into_par_iter().for_each(|_| {
                 let _ = seg.segment(text, None);
             });
             let duration = start.elapsed();
             println!("Time: {:.3}s", duration.as_secs_f64());
             println!("Throughput: {:.2} calls/sec", iterations_conc as f64 / duration.as_secs_f64());
        }
    } else if !input_files.is_empty() {
        let mut out: Box<dyn Write> = if let Some(path) = output_file {
            Box::new(File::create(path)?)
        } else {
             Box::new(io::stdout())
        };
        
        let mut lines = Vec::new();
        let mut current_limit = limit;
        for file in &input_files {
             let f = File::open(file)?;
             let reader = BufReader::new(f);
             for line in reader.lines() {
                 if limit != -1 && current_limit <= 0 { break; }
                 if let Ok(l) = line {
                     // Remove BOM
                        let clean = if l.starts_with("\u{FEFF}") {
                             l.chars().skip(1).collect()
                         } else {
                             l
                         };
                     lines.push(clean);
                     if limit != -1 { current_limit -= 1; }
                 }
             }
             if limit != -1 && current_limit <= 0 { break; }
        }
        
        // Use parallel processing if threads > 1
        if threads > 1 {
             let results: Vec<String> = lines.par_iter()
                .map(|l| seg.segment(l, Some(" | ")))
                .collect();
             
             for (orig, res) in lines.iter().zip(results.iter()) {
                 writeln!(out, "Original:  {}", orig)?;
                 writeln!(out, "Segmented: {}", res)?;
                 writeln!(out, "----------------------------------------")?;
             }
        } else {
             for l in lines {
                 let res = seg.segment(&l, Some(" | "));
                 writeln!(out, "Original:  {}", l)?;
                 writeln!(out, "Segmented: {}", res)?;
                 writeln!(out, "----------------------------------------")?;
             }
        }
        
    } else if let Some(text) = input_text {
        let res = seg.segment(&text, Some(" | "));
        println!("Input: {}", text);
        println!("Output: {}", res);
        
        // Save
        let out_path = output_file.unwrap_or("segmentation_results.txt".to_string());
        let mut f = File::create(&out_path)?;
        writeln!(f, "Original:  {}", text)?;
        writeln!(f, "Segmented: {}", res)?;
        writeln!(f, "----------------------------------------")?;
        eprintln!("Results saved to {}", out_path);
    } else {
        println!("Usage: khmer_segmenter.exe [flags] [text]");
        println!("  --input <path...> Multiple input files");
        println!("  --output <path>   Output file path");
        println!("  --limit <N>       Limit total lines processed");
        println!("  --threads <N>     Number of threads (default: 4)");
        println!("  --benchmark       Run benchmark (uses --input if provided)");
        println!("  <text>            Process raw text");
    }

    Ok(())
}
