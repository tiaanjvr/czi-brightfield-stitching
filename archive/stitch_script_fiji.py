import os
import glob
import subprocess
import time
from aicspylibczi import CziFile  # NEW: We use Python to intelligently parse the metadata

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/path/to/czi_files/"
OUTPUT_BASE_FOLDER = "/path/to/stitched_output/"

# Update this line to your exact Fiji executable path
FIJI_EXECUTABLE = "/path/to/Fiji.app/ImageJ-linux64" 
# =============================================================================

def fiji_batch_stitch():
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

    print("--- HYBRID BATCH STITCHING STARTED ---")
    print(f"Found {total_files} files to process.\n")

    overall_start_time = time.time()
    success_count = 0
    fail_count = 0

    for idx, czi_path in enumerate(czi_files, 1):
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        out_tiff_path = os.path.join(OUTPUT_BASE_FOLDER, f"{base_name}.tiff")
        macro_path = os.path.join(OUTPUT_BASE_FOLDER, f"stitch_{base_name}.ijm")
        
        print(f"[{idx}/{total_files}] Processing: {filename}")
        file_start_time = time.time()
        
        if os.path.exists(out_tiff_path):
            print(f"  -> Skipping: Output already exists.")
            success_count += 1
            continue

        try:
            # --- 1. PYTHON METADATA PARSING ---
            czi = CziFile(czi_path)
            if 'M' not in czi.dims:
                print("  -> Skipping: Not a mosaic (Single Image).")
                continue
                
            dimensions = czi.get_dims_shape()[0]
            tile_count = dimensions['M'][1]
            
            # Dynamically generate "series_1 series_2 ... series_25"
            # This explicitly blocks Fiji from loading the 50% and 25% ghost pyramids
            series_flags = " ".join([f"series_{i}" for i in range(1, tile_count + 1)])
            
            # --- 2. THE STABLE MACRO ---
            # Removed 'compute_overlap' -> Forces perfect Zeiss stage alignment (no jagged edges)
            # Kept 'Linear Blending' -> Erases dark grid lines seamlessly
            macro_code = f"""
            run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by image metadata] browse=[{czi_path}] multi_series_file=[{czi_path}] {series_flags} fusion_method=[Linear Blending] computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
            saveAs("Tiff", "{out_tiff_path}");
            run("Close All");
            run("Quit");
            """
            
            with open(macro_path, "w") as f:
                f.write(macro_code)
                
            cmd = [FIJI_EXECUTABLE, "--headless", "--mem=10G", "-macro", macro_path]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if os.path.exists(out_tiff_path):
                elapsed = time.time() - file_start_time
                print(f"  -> Success in {elapsed:.1f}s: Saved {base_name}.tiff (Stitched {tile_count} tiles)")
                success_count += 1
            else:
                error_log_path = os.path.join(OUTPUT_BASE_FOLDER, f"ERROR_LOG_{base_name}.txt")
                with open(error_log_path, "w") as err_file:
                    err_file.write(result.stdout if result.stdout else "No output from Fiji.")
                print(f"  -> ERROR: Fiji finished, but output was not created. Log saved.")
                fail_count += 1
                
        except subprocess.CalledProcessError as e:
            error_log_path = os.path.join(OUTPUT_BASE_FOLDER, f"CRASH_LOG_{base_name}.txt")
            with open(error_log_path, "w") as err_file:
                err_file.write(e.stdout if e.stdout else str(e))
            print(f"  -> FATAL ERROR: Fiji crashed. Log saved.")
            fail_count += 1
            
        except Exception as e:
            print(f"  -> UNEXPECTED ERROR on {filename}: {e}")
            fail_count += 1
            
        finally:
            if os.path.exists(macro_path):
                os.remove(macro_path)
                
    total_time = (time.time() - overall_start_time) / 60
    print("\n--- BATCH STITCHING COMPLETE ---")
    print(f"Total time taken: {total_time:.2f} minutes")
    print(f"Successfully stitched: {success_count}/{total_files}")

if __name__ == "__main__":
    fiji_batch_stitch()