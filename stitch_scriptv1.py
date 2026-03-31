import os
import glob
from datetime import datetime
import numpy as np
from aicspylibczi import CziFile
import tifffile
import concurrent.futures

# =============================================================================
# 1. GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/run/media/tiaan/Windows-SSD/czi/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/run/media/tiaan/Windows-SSD/czi/2026 rats/stitched_output/"

CHANNEL_TO_STITCH = 0 
Z_PLANE_TO_STITCH = 0

# How many files to process at the exact same time. 
# WARNING: Each file might use 1-2GB of RAM during stitching. 
# If you have 16GB of RAM, keep this at 4 or 6. If you have 32GB+, you can increase it.
MAX_WORKERS = 4 
# =============================================================================

def process_single_file(czi_path, output_dir):
    """Worker function to process a single file. Isolated for multithreading."""
    filename = os.path.basename(czi_path)
    base_name = os.path.splitext(filename)[0]
    out_tiff_path = os.path.join(output_dir, f"{base_name}.tiff")
    
    try:
        czi = CziFile(czi_path)
        
        # 1. Dimension and Tile Check
        if 'M' not in czi.dims:
            return f"Skipped {filename}: Not a mosaic (single image)."
        
        dimensions = czi.get_dims_shape()[0]
        tile_count = dimensions['M'][1] 
        if tile_count != 25:
            return f"Skipped {filename}: Found {tile_count} tiles instead of 25."
            
        # 2. Build arguments dynamically
        kwargs = {'scale_factor': 1.0}
        if 'C' in czi.dims: kwargs['C'] = CHANNEL_TO_STITCH
        if 'Z' in czi.dims: kwargs['Z'] = Z_PLANE_TO_STITCH
            
        # 3. Read and Squeeze
        mosaic_data = czi.read_mosaic(**kwargs)
        mosaic_array = np.squeeze(mosaic_data)
        
        # 4. Save with zlib compression to reduce file size significantly
        tifffile.imwrite(
            out_tiff_path, 
            mosaic_array, 
            bigtiff=True, 
            imagej=True, 
            compression='zlib'
        )
        
        return f"Success: {filename} -> Saved (Stitched {tile_count} tiles)"
        
    except Exception as e:
        return f"Error: {filename} -> {e}"

def process_microscopy_files():
    timestamp = datetime.now().strftime("%d%b%Y_at_%Hh%Mm%Ss")
    output_folder_name = f"tiff_output_{timestamp}"
    output_dir = os.path.join(OUTPUT_BASE_FOLDER, output_folder_name)
    
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}\n")

    search_pattern = os.path.join(INPUT_FOLDER, "*.czi")
    czi_files = glob.glob(search_pattern)
    
    if not czi_files:
        print(f"No .czi files found in {INPUT_FOLDER}")
        return

    print(f"Found {len(czi_files)} files. Starting multithreaded processing with {MAX_WORKERS} workers...\n")

    # Use ProcessPoolExecutor to bypass Python's Global Interpreter Lock (GIL) and max out CPU cores
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks to the executor
        futures = {executor.submit(process_single_file, path, output_dir): path for path in czi_files}
        
        # As each file finishes processing, print its result
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(result)

    print("\nBatch processing complete!")

if __name__ == "__main__":
    process_microscopy_files()