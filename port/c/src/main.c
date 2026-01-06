#define _CRT_SECURE_NO_WARNINGS
#include "khmer_segmenter.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// Platform-specific includes
#ifdef _WIN32
    #include <windows.h>
    #include <psapi.h>
#else
    #include <pthread.h>
    #include <sys/time.h>
    #include <sys/resource.h>
    #include <unistd.h>
    #ifdef __APPLE__
        #include <mach/mach.h>
    #endif
#endif

// Cross-platform strdup compatibility
#if defined(_WIN32)
    #define STRDUP _strdup
#else
    #define STRDUP strdup
#endif

// --- Helpers ---

double get_time_sec() {
#ifdef _WIN32
    LARGE_INTEGER frequency, start;
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&start);
    return (double)start.QuadPart / frequency.QuadPart;
#else
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (double)tv.tv_sec + (double)tv.tv_usec / 1000000.0;
#endif
}

double get_memory_mb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS pmc;
    if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
        return (double)pmc.WorkingSetSize / (1024.0 * 1024.0);
    }
    return 0.0;
#elif defined(__APPLE__)
    struct mach_task_basic_info info;
    mach_msg_type_number_t size = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &size) == KERN_SUCCESS) {
        return (double)info.resident_size / (1024.0 * 1024.0);
    }
    return 0.0;
#else
    // Linux: read from /proc/self/status
    FILE* f = fopen("/proc/self/status", "r");
    if (!f) return 0.0;
    
    char line[256];
    double mem_mb = 0.0;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "VmRSS:", 6) == 0) {
            long mem_kb;
            if (sscanf(line + 6, "%ld", &mem_kb) == 1) {
                mem_mb = (double)mem_kb / 1024.0;
            }
            break;
        }
    }
    fclose(f);
    return mem_mb;
#endif
}

// --- Batch Processing ---

// --- Batch Processing (Multi-threaded) ---

#define BATCH_CHUNK_SIZE 2000

typedef struct {
    KhmerSegmenter* seg;
    char** lines;
    char** results;
    int count;
    int thread_id;
    int total_threads;
} BatchWorkerArgs;

#ifdef _WIN32
DWORD WINAPI batch_worker(LPVOID lpParam) {
#else
void* batch_worker(void* lpParam) {
#endif
    BatchWorkerArgs* args = (BatchWorkerArgs*)lpParam;
    for (int i = args->thread_id; i < args->count; i += args->total_threads) {
        // Initialize result to NULL first
        args->results[i] = NULL;
        if (args->lines[i]) {
            args->results[i] = khmer_segmenter_segment(args->seg, args->lines[i], " | ");
        }
    }
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

static char* read_line(FILE* f) {
    size_t cap = 4096;
    size_t len = 0;
    char* data = (char*)malloc(cap);
    if (!data) return NULL;

    while (fgets(data + len, (int)(cap - len), f)) {
        size_t read_len = strlen(data + len);
        len += read_len;
        if (data[len - 1] == '\n') break;
        if (len + 1 >= cap) {
            cap *= 2;
            char* next_data = (char*)realloc(data, cap);
            if (!next_data) {
                free(data);
                return NULL;
            }
            data = next_data;
        }
    }

    if (len == 0) {
        free(data);
        return NULL;
    }

    // Strip trailing newline/cr
    while (len > 0 && (data[len - 1] == '\r' || data[len - 1] == '\n')) {
        data[--len] = '\0';
    }

    // Shrink buffer to fit actual content to save memory
    // (Otherwise we waste ~4KB per line)
    char* shrunk = (char*)realloc(data, len + 1);
    if (shrunk) data = shrunk;

    return data;
}

void batch_process_file(KhmerSegmenter* seg, const char* filepath, FILE* out, int threads_count, int* limit) {
    if (!filepath || (*limit == 0)) return;
    FILE* f = fopen(filepath, "r");
    if (!f) {
        fprintf(stderr, "Error: Could not open file %s\n", filepath);
        return;
    }

    fprintf(stderr, "Processing %s (Limit: %d)...\n", filepath, *limit);

    char** lines = (char**)malloc(BATCH_CHUNK_SIZE * sizeof(char*));
    char** results = (char**)calloc(BATCH_CHUNK_SIZE, sizeof(char*));
    
    int chunk_idx = 0;
    int first_line = 1;

    char* line;
    while ((*limit != 0) && (line = read_line(f))) {
        char* line_start = line;
        if (*limit > 0) (*limit)--;
        // Strip BOM if first line
        if (first_line) {
            unsigned char* ub = (unsigned char*)line;
            if (ub[0] == 0xEF && ub[1] == 0xBB && ub[2] == 0xBF) {
                line_start = STRDUP(line + 3);
                free(line);
            } else {
                line_start = line;
            }
            first_line = 0;
        }

        lines[chunk_idx++] = line_start;

        if (chunk_idx >= BATCH_CHUNK_SIZE) {
            // Process Chunk
            if (threads_count <= 1) {
                for(int i=0; i<chunk_idx; i++) {
                    results[i] = khmer_segmenter_segment(seg, lines[i], " | ");
                }
            } else {
#ifdef _WIN32
                HANDLE* handles = (HANDLE*)malloc(threads_count * sizeof(HANDLE));
                BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads_count * sizeof(BatchWorkerArgs));
                
                for(int t=0; t<threads_count; t++) {
                    args[t].seg = seg;
                    args[t].lines = lines;
                    args[t].results = results;
                    args[t].count = chunk_idx;
                    args[t].thread_id = t;
                    args[t].total_threads = threads_count;
                    handles[t] = CreateThread(NULL, 0, batch_worker, &args[t], 0, NULL);
                }
                WaitForMultipleObjects(threads_count, handles, TRUE, INFINITE);
                for(int t=0; t<threads_count; t++) CloseHandle(handles[t]);
                free(handles);
                free(args);
#else
                pthread_t* threads = (pthread_t*)malloc(threads_count * sizeof(pthread_t));
                BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads_count * sizeof(BatchWorkerArgs));
                
                for(int t=0; t<threads_count; t++) {
                    args[t].seg = seg;
                    args[t].lines = lines;
                    args[t].results = results;
                    args[t].count = chunk_idx;
                    args[t].thread_id = t;
                    args[t].total_threads = threads_count;
                    pthread_create(&threads[t], NULL, batch_worker, &args[t]);
                }
                for(int t=0; t<threads_count; t++) {
                    pthread_join(threads[t], NULL);
                }
                free(threads);
                free(args);
#endif
            }

            // Print & Free
            for(int i=0; i<chunk_idx; i++) {
                fprintf(out, "Original:  %s\n", lines[i]);
                fprintf(out, "Segmented: %s\n", results[i] ? results[i] : "");
                fprintf(out, "----------------------------------------\n");
                
                free(lines[i]);
                if (results[i]) free(results[i]);
                results[i] = NULL;
            }
            chunk_idx = 0;
        }
    }
    
    // Process remaining
    if (chunk_idx > 0) {
        if (threads_count <= 1) {
            for(int i=0; i<chunk_idx; i++) {
                results[i] = khmer_segmenter_segment(seg, lines[i], " | ");
            }
        } else {
#ifdef _WIN32
             HANDLE* handles = (HANDLE*)malloc(threads_count * sizeof(HANDLE));
             BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads_count * sizeof(BatchWorkerArgs));
             
             for(int t=0; t<threads_count; t++) {
                 args[t].seg = seg;
                 args[t].lines = lines;
                 args[t].results = results;
                 args[t].count = chunk_idx;
                 args[t].thread_id = t;
                 args[t].total_threads = threads_count;
                 handles[t] = CreateThread(NULL, 0, batch_worker, &args[t], 0, NULL);
             }
             WaitForMultipleObjects(threads_count, handles, TRUE, INFINITE);
             for(int t=0; t<threads_count; t++) CloseHandle(handles[t]);
             free(handles);
             free(args);
#else
             pthread_t* threads = (pthread_t*)malloc(threads_count * sizeof(pthread_t));
             BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads_count * sizeof(BatchWorkerArgs));
             
             for(int t=0; t<threads_count; t++) {
                 args[t].seg = seg;
                 args[t].lines = lines;
                 args[t].results = results;
                 args[t].count = chunk_idx;
                 args[t].thread_id = t;
                 args[t].total_threads = threads_count;
                 pthread_create(&threads[t], NULL, batch_worker, &args[t]);
             }
             for(int t=0; t<threads_count; t++) {
                 pthread_join(threads[t], NULL);
             }
             free(threads);
             free(args);
#endif
        }

        for(int i=0; i<chunk_idx; i++) {
            fprintf(out, "Original:  %s\n", lines[i]);
            fprintf(out, "Segmented: %s\n", results[i] ? results[i] : "");
            fprintf(out, "----------------------------------------\n");
            free(lines[i]);
            if (results[i]) free(results[i]);
        }
    }

    free(lines);
    free(results);
    fclose(f);
}

// --- Benchmark ---

void run_input_benchmark(KhmerSegmenter* seg, char** lines, int count, int threads, FILE* out) {
    if (count <= 0) return;
    
    char** results = (char**)calloc(count, sizeof(char*));
    
    // Calculate total size for throughput
    size_t total_bytes = 0;
    for(int i=0; i<count; i++) {
        if (lines[i]) total_bytes += strlen(lines[i]);
    }
    double total_mb = (double)total_bytes / (1024.0 * 1024.0);

    fprintf(stderr, "\n--- Input Benchmark (%d lines, %.2f MB) ---\n", count, total_mb);
    fprintf(stderr, "Initial Memory: %.2f MB\n", get_memory_mb());
    
    // 1. Sequential (1 Thread)
    fprintf(stderr, "[1 Thread] Processing...");
    double start_time = get_time_sec();
    double start_mem = get_memory_mb();
    
    for (int i=0; i<count; i++) {
        results[i] = khmer_segmenter_segment(seg, lines[i], " | ");
    }
    
    double end_time = get_time_sec();
    double end_mem = get_memory_mb();
    double dur_seq = end_time - start_time;
    if (dur_seq < 0.001) dur_seq = 0.001; 
    
    fprintf(stderr, " Done in %.3fs\n", dur_seq);
    fprintf(stderr, "Throughput: %.2f lines/sec (%.2f MB/s)\n", (double)count / dur_seq, total_mb / dur_seq);
    fprintf(stderr, "Mem Delta: %.2f MB\n", end_mem - start_mem);
    
    // Save results to file if output is open
    if (out) {
        fprintf(stderr, "Saving results to output file...\n");
        for (int i=0; i<count; i++) {
            fprintf(out, "Original:  %s\n", lines[i]);
            fprintf(out, "Segmented: %s\n", results[i] ? results[i] : "");
            fprintf(out, "----------------------------------------\n");
        }
    }
    
    // Free results to reuse array for multi-threaded run
    for(int i=0; i<count; i++) { if(results[i]) free(results[i]); results[i] = NULL; }
    
    // 2. Multi-threaded run
    if (threads > 1) {
        fprintf(stderr, "\n[%d Threads] Processing...", threads);
        start_time = get_time_sec();
        start_mem = get_memory_mb();
        
#ifdef _WIN32
        HANDLE* handles = (HANDLE*)malloc(threads * sizeof(HANDLE));
        BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads * sizeof(BatchWorkerArgs));
        
        for(int t=0; t<threads; t++) {
            args[t].seg = seg;
            args[t].lines = lines;
            args[t].results = results;
            args[t].count = count;
            args[t].thread_id = t;
            args[t].total_threads = threads;
            handles[t] = CreateThread(NULL, 0, batch_worker, &args[t], 0, NULL);
        }
        WaitForMultipleObjects(threads, handles, TRUE, INFINITE);
        for(int t=0; t<threads; t++) CloseHandle(handles[t]);
        free(handles);
        free(args);
#else
        pthread_t* thread_handles = (pthread_t*)malloc(threads * sizeof(pthread_t));
        BatchWorkerArgs* args = (BatchWorkerArgs*)malloc(threads * sizeof(BatchWorkerArgs));
        
        for(int t=0; t<threads; t++) {
            args[t].seg = seg;
            args[t].lines = lines;
            args[t].results = results;
            args[t].count = count;
            args[t].thread_id = t;
            args[t].total_threads = threads;
            pthread_create(&thread_handles[t], NULL, batch_worker, &args[t]);
        }
        for(int t=0; t<threads; t++) {
            pthread_join(thread_handles[t], NULL);
        }
        free(thread_handles);
        free(args);
#endif
        
        end_time = get_time_sec();
        end_mem = get_memory_mb();
        double dur_conc = end_time - start_time;
        if (dur_conc < 0.001) dur_conc = 0.001;
        
        fprintf(stderr, " Done in %.3fs\n", dur_conc);
        fprintf(stderr, "Throughput: %.2f lines/sec (%.2f MB/s)\n", (double)count / dur_conc, total_mb / dur_conc);
        fprintf(stderr, "Mem Delta: %.2f MB\n", end_mem - start_mem);
        fprintf(stderr, "Speedup: %.2fx\n", dur_seq / dur_conc);
    }
    
    for(int i=0; i<count; i++) { if(results[i]) free(results[i]); }
    free(results);
}

typedef struct {
    KhmerSegmenter* seg;
    const char* text;
    int iterations;
} ThreadData;

#ifdef _WIN32
DWORD WINAPI benchmark_worker(LPVOID lpParam) {
#else
void* benchmark_worker(void* lpParam) {
#endif
    ThreadData* data = (ThreadData*)lpParam;
    for (int i = 0; i < data->iterations; i++) {
        char* res = khmer_segmenter_segment(data->seg, data->text, NULL);
        free(res);
    }
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

void run_benchmark(KhmerSegmenter* seg, int threads_count, const char* custom_text, FILE* out) {
    const char* text = custom_text;
    if (!text) {
        text = "ក្រុមហ៊ុនទទួលបានប្រាក់ចំណូល ១ ០០០ ០០០ ដុល្លារក្នុងឆ្នាំនេះ ខណៈដែលតម្លៃភាគហ៊ុនកើនឡើង ៥% ស្មើនឹង 50.00$។"
               "លោក ទេព សុវិចិត្រ នាយកប្រតិបត្តិដែលបញ្ចប់ការសិក្សាពីសាកលវិទ្យាល័យភូមិន្ទភ្នំពេញ (ស.ភ.ភ.ព.) "
               "បានថ្លែងថា ភាពជោគជ័យផ្នែកហិរញ្ញវត្ថុនាឆ្នាំនេះ គឺជាសក្ខីភាពនៃកិច្ចខិតខំប្រឹងប្រែងរបស់ក្រុមការងារទាំងមូល "
               "និងការជឿទុកចិត្តពីសំណាក់វិនិយោគិន។";
    }
    int iterations_seq = 1000;
    int iterations_conc = 5000;
    
    printf("\n--- Benchmark Suite ---\n");
    printf("Text Length: %zu chars\n", strlen(text));
    printf("Initial Memory: %.2f MB\n", get_memory_mb());

    // 1. Warmup / Output Check
    char* check = khmer_segmenter_segment(seg, text, " | ");
    if (strlen(text) < 1000) {
        printf("\n[Output Check]\n%s\n", check);
    }
    
    // Save benchmark text and result to file
    if (out) {
        fprintf(out, "Original:  %s\n", text);
        fprintf(out, "Segmented: %s\n", check);
        fprintf(out, "----------------------------------------\n");
    }
    
    free(check);

    // 2. Sequential
    printf("\n[Sequential] Running %d iterations...\n", iterations_seq);
    double start = get_time_sec();
    double start_mem = get_memory_mb();
    
    for (int i=0; i<iterations_seq; i++) {
        char* res = khmer_segmenter_segment(seg, text, NULL);
        free(res);
    }
    
    double end = get_time_sec();
    double end_mem = get_memory_mb();
    double dur = end - start;
    printf("Time: %.3fs\n", dur);
    printf("Avg: %.3f ms/call\n", (dur / iterations_seq) * 1000.0);
    printf("Mem Delta: %.2f MB\n", end_mem - start_mem);

    // 3. Concurrent
    if (threads_count < 1) threads_count = 1;
    printf("\n[Concurrent] Running %d iterations with %d threads...\n", iterations_conc, threads_count);
    
    start = get_time_sec();
    start_mem = get_memory_mb();
    
#ifdef _WIN32
    HANDLE* handles = (HANDLE*)malloc(sizeof(HANDLE) * threads_count);
    ThreadData* tdata = (ThreadData*)malloc(sizeof(ThreadData) * threads_count);
    
    int per_thread = iterations_conc / threads_count;
    
    for (int i=0; i<threads_count; i++) {
        tdata[i].seg = seg;
        tdata[i].text = text;
        tdata[i].iterations = per_thread;
        handles[i] = CreateThread(NULL, 0, benchmark_worker, &tdata[i], 0, NULL);
    }
    
    WaitForMultipleObjects(threads_count, handles, TRUE, INFINITE);
    
    for(int i=0; i<threads_count; i++) CloseHandle(handles[i]);
    free(handles);
    free(tdata);
#else
    pthread_t* handles = (pthread_t*)malloc(sizeof(pthread_t) * threads_count);
    ThreadData* tdata = (ThreadData*)malloc(sizeof(ThreadData) * threads_count);
    
    int per_thread = iterations_conc / threads_count;
    
    for (int i=0; i<threads_count; i++) {
        tdata[i].seg = seg;
        tdata[i].text = text;
        tdata[i].iterations = per_thread;
        pthread_create(&handles[i], NULL, benchmark_worker, &tdata[i]);
    }
    
    for(int i=0; i<threads_count; i++) {
        pthread_join(handles[i], NULL);
    }
    free(handles);
    free(tdata);
#endif
    
    end = get_time_sec();
    end_mem = get_memory_mb();
    dur = end - start;
    
    printf("Time: %.3fs\n", dur);
    printf("Throughput: %.2f calls/sec\n", (double)iterations_conc / dur);
    printf("Mem Delta: %.2f MB\n", end_mem - start_mem);
}

// --- Main ---

int main(int argc, char** argv) {
#ifdef _WIN32
    // Set console to UTF-8 mode for proper Khmer text display
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
    
    // On Windows, convert command line from UTF-16 to UTF-8
    LPWSTR* argvw = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argvw) return 1;

    // Parse Args
    argv = (char**)malloc(argc * sizeof(char*));
    for (int i = 0; i < argc; i++) {
        int len = WideCharToMultiByte(CP_UTF8, 0, argvw[i], -1, NULL, 0, NULL, NULL);
        argv[i] = (char*)malloc(len);
        WideCharToMultiByte(CP_UTF8, 0, argvw[i], -1, argv[i], len, NULL, NULL);
    }
#endif
    
    setbuf(stdout, NULL);
    
    // Config
    int mode_benchmark = 0;
    char** input_files = NULL;
    int input_files_count = 0;
    char* output_file = NULL;
    char* input_text = NULL;
    int threads = 4;
    int limit = -1;
    
    SegmenterConfig config = segmenter_config_default();
    
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--benchmark") == 0) {
            mode_benchmark = 1;
        } else if (strcmp(argv[i], "--input") == 0 || strcmp(argv[i], "--file") == 0) {
            while (i + 1 < argc && argv[i+1][0] != '-') {
                input_files = (char**)realloc(input_files, sizeof(char*) * (input_files_count + 1));
                input_files[input_files_count++] = argv[++i];
            }
        } else if (strcmp(argv[i], "--output") == 0 && i+1 < argc) {
            output_file = argv[++i];
        } else if (strcmp(argv[i], "--threads") == 0 && i+1 < argc) {
            threads = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--limit") == 0 && i+1 < argc) {
            limit = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--no-norm") == 0) {
            config.enable_normalization = 0;
        } else if (strcmp(argv[i], "--no-repair") == 0) {
            config.enable_repair_mode = 0;
        } else if (strcmp(argv[i], "--no-acronym") == 0) {
            config.enable_acronym_detection = 0;
        } else if (strcmp(argv[i], "--no-merging") == 0) {
            config.enable_unknown_merging = 0;
        } else if (strcmp(argv[i], "--no-freq") == 0) {
            config.enable_frequency_costs = 0;
        } else if (argv[i][0] != '-') {
            // Treat positional as text (concatenate multiple args)
            if (input_text == NULL) {
                input_text = STRDUP(argv[i]);
            } else {
                // Append space + arg
                size_t input_len = strlen(input_text);
                size_t arg_len = strlen(argv[i]);
                char* new_text = (char*)malloc(input_len + 1 + arg_len + 1);
                strcpy(new_text, input_text);
                strcat(new_text, " ");
                strcat(new_text, argv[i]);
                free(input_text);
                input_text = new_text;
            }
        }
    }

    if (input_files_count > 0 && !output_file) {
        output_file = "segmentation_results.txt";
    }
    
    // Check for dictionary in probable locations
    const char* dict_path = "khmer_dictionary.kdict";
    const char* freq_path = "";
    
    // 1. CWD .kdict
    FILE* check = fopen(dict_path, "rb");
    
    // 2. port/common/ .kdict
    if (!check) {
        dict_path = "port/common/khmer_dictionary.kdict";
        check = fopen(dict_path, "rb");
    }
    
    // 3. ../common/ .kdict
    if (!check) {
        dict_path = "../common/khmer_dictionary.kdict";
        check = fopen(dict_path, "rb");
    }
    
    // 4. Fallback to txt/bin (Legacy)
    if (!check) {
         dict_path = "port/common/khmer_dictionary_words.txt";
         check = fopen(dict_path, "r");
         if (check) freq_path = "port/common/khmer_frequencies.bin";
    }
    if (!check) {
        dict_path = "../common/khmer_dictionary_words.txt";
        check = fopen(dict_path, "r");
        if (check) freq_path = "../common/khmer_frequencies.bin";
    }
    if (!check) {
        dict_path = "data/khmer_dictionary_words.txt";
        check = fopen(dict_path, "r");
        if (check) freq_path = "data/khmer_frequencies.bin";
    }
    
    if (check) fclose(check);

    if (mode_benchmark || input_files_count > 0) {
        fprintf(stderr, "Initializing segmenter (Dict: %s, Freq: %s)...\n", dict_path, freq_path);
    }

    KhmerSegmenter* seg = khmer_segmenter_init_ex(dict_path, freq_path, &config);
    if (!seg) {
        fprintf(stderr, "Failed to init segmenter.\n");
        return 1;
    }
    
    if (mode_benchmark || input_files_count > 0) {
       fprintf(stderr, "Initialization complete.\n");
    }

    if (mode_benchmark) {
        if (input_files_count > 0) {
            char** lines = NULL;
            int count = 0;
            int temp_limit = limit;
            for (int i = 0; i < input_files_count && (limit == -1 || temp_limit > 0); i++) {
                FILE* f = fopen(input_files[i], "r");
                if (f) {
                    char* line;
                    while ((temp_limit != 0) && (line = read_line(f))) {
                        lines = (char**)realloc(lines, sizeof(char*) * (count + 1));
                        lines[count++] = line;
                        if (temp_limit > 0) temp_limit--;
                    }
                    fclose(f);
                }
            }
            
            FILE* out = NULL;
            if (output_file) {
                out = fopen(output_file, "w");
            }
            
            run_input_benchmark(seg, lines, count, threads, out);
            
            if (out) fclose(out);
            for(int i=0; i<count; i++) free(lines[i]);
            free(lines);
        } else {
            FILE* out = NULL;
            if (output_file) {
                out = fopen(output_file, "w");
                if (!out) {
                    fprintf(stderr, "Warning: Could not open output file %s for benchmark results\n", output_file);
                }
            } else {
                // Default output file for internal benchmark
                out = fopen("benchmark_results.txt", "w");
                if (!out) {
                    fprintf(stderr, "Warning: Could not create benchmark_results.txt\n");
                }
            }
            
            run_benchmark(seg, threads, NULL, out);
            
            if (out) fclose(out);
        }
    } else if (input_files_count > 0) {
        FILE* out = stdout;
        if (output_file) {
            out = fopen(output_file, "w");
            if (!out) {
                fprintf(stderr, "Error: Could not open output file %s\n", output_file);
                out = stdout;
            }
        }
        
        int current_limit = limit;
        for (int i = 0; i < input_files_count; i++) {
            batch_process_file(seg, input_files[i], out, threads, &current_limit);
            if (current_limit == 0) break;
        }
        
        if (output_file && out != stdout) fclose(out);
    } else if (input_text) {
        char* res = khmer_segmenter_segment(seg, input_text, " | ");
        printf("Input: %s\n", input_text);
        printf("Output: %s\n", res);
        
        // Save to file
        FILE* out = NULL;
        if (output_file) {
            out = fopen(output_file, "w");
        } else {
            out = fopen("segmentation_results.txt", "w");
        }
        
        if (out) {
            fprintf(out, "Original:  %s\n", input_text);
            fprintf(out, "Segmented: %s\n", res);
            fprintf(out, "----------------------------------------\n");
            fclose(out);
            fprintf(stderr, "Results saved to %s\n", output_file ? output_file : "segmentation_results.txt");
        } else {
            fprintf(stderr, "Warning: Could not save results to file\n");
        }
        
        free(res);
    } else {
        printf("Usage: khmer_segmenter.exe [flags] [text]\n");
        printf("  --input <path...> Multiple input files\n");
        printf("  --output <path>   Output file path\n");
        printf("  --limit <N>       Limit total lines processed\n");
        printf("  --threads <N>     Number of threads (default: 4)\n");
        printf("  --benchmark       Run benchmark (uses --input if provided)\n");
        printf("  <text>            Process raw text\n");
    }

    khmer_segmenter_free(seg);
    
#ifdef _WIN32
    LocalFree(argvw); 
    for(int i=0; i<argc; i++) free(argv[i]);
    free(argv);
#endif
    
    if (input_files) free(input_files);
    
    return 0;
}
