import os
import glob
import subprocess
import time

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/home/tiaan/Downloads/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/home/tiaan/Downloads/2026 rats/stitched_output/fiji_batch/"

# Update this line to your exact Fiji executable path
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
# =============================================================================

def fiji_batch_stitch():
    # --- 1. PRE-FLIGHT CHECKS ---
    if not os.path.exists(FIJI_EXECUTABLE):
        print(f"CRITICAL ERROR: Fiji executable not found at {FIJI_EXECUTABLE}")
        return

    if not os.path.exists(INPUT_FOLDER):
        print(f"CRITICAL ERROR: Input folder not found at {INPUT_FOLDER}")
        return

    os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)
    czi_files = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.czi")))
    total_files = len(czi_files)
    
    if total_files == 0:
        print(f"No CZI files found in {INPUT_FOLDER}")
        return

    print("--- BATCH STITCHING STARTED ---")
    print(f"Found {total_files} files to process.\n")

    overall_start_time = time.time()
    success_count = 0
    fail_count = 0

    # --- 2. THE MAIN LOOP ---
    for idx, czi_path in enumerate(czi_files, 1):
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        
        # We are using standard .tiff here to bypass the Bio-Formats crash
        out_tiff_path = os.path.join(OUTPUT_BASE_FOLDER, f"{base_name}.tiff")
        macro_path = os.path.join(OUTPUT_BASE_FOLDER, f"stitch_{base_name}.ijm")
        
        print(f"[{idx}/{total_files}] Processing: {filename}")
        file_start_time = time.time()
        
        # Resume capability: Skip if already stitched
        if os.path.exists(out_tiff_path):
            print(f"  -> Skipping: Output already exists.")
            success_count += 1
            continue

        # --- THE STABLE MACRO ---
        # 1. 'series_1' ignores the ghosts.
        # 2. 'compute_overlap subpixel_accuracy' calculates the exact seams.
        # 3. 'saveAs' safely writes the fused canvas to disk.
        macro_code = f"""
        run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by image metadata] browse=[{czi_path}] multi_series_file=[{czi_path}] series_1 fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
        saveAs("Tiff", "{out_tiff_path}");
        run("Close All");
        run("Quit");
        """
        
        with open(macro_path, "w") as f:
            f.write(macro_code)
            
        # --mem=10G limits Java RAM usage so Fedora doesn't crash
        cmd = [FIJI_EXECUTABLE, "--headless", "--mem=10G", "-macro", macro_path]
        
        try:
            # capture_output records the console logs to catch headless Java errors
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # --- 3. SILENT FAILURE DETECTION ---
            if os.path.exists(out_tiff_path):
                elapsed = time.time() - file_start_time
                print(f"  -> Success in {elapsed:.1f}s: Saved {base_name}.tiff")
                success_count += 1
            else:
                # If Fiji finished but no file appeared, save the exact log
                error_log_path = os.path.join(OUTPUT_BASE_FOLDER, f"ERROR_LOG_{base_name}.txt")
                with open(error_log_path, "w") as err_file:
                    err_file.write(result.stdout if result.stdout else "No output from Fiji.")
                
                print(f"  -> ERROR: Fiji finished, but output was not created.")
                print(f"  -> FULL ERROR LOG SAVED TO: {error_log_path}")
                fail_count += 1
                
        except subprocess.CalledProcessError as e:
            # Handles actual crashes (e.g., Out of Memory, severe Java exceptions)
            error_log_path = os.path.join(OUTPUT_BASE_FOLDER, f"CRASH_LOG_{base_name}.txt")
            with open(error_log_path, "w") as err_file:
                err_file.write(e.stdout if e.stdout else str(e))
                
            print(f"  -> FATAL ERROR: Fiji crashed while processing {filename}")
            print(f"  -> FULL CRASH LOG SAVED TO: {error_log_path}")
            fail_count += 1
            
        except Exception as e:
            print(f"  -> UNEXPECTED ERROR on {filename}: {e}")
            fail_count += 1
            
        finally:
            # --- 4. GUARANTEED CLEANUP ---
            if os.path.exists(macro_path):
                os.remove(macro_path)
                
    # --- 5. FINAL SUMMARY ---
    total_time = (time.time() - overall_start_time) / 60
    print("\n--- BATCH STITCHING COMPLETE ---")
    print(f"Total time taken: {total_time:.2f} minutes")
    print(f"Successfully stitched: {success_count}/{total_files}")
    if fail_count > 0:
        print(f"Failed to stitch: {fail_count}/{total_files} (Check logs in output folder)")

if __name__ == "__main__":
    fiji_batch_stitch()