import os
import glob
from datetime import datetime
import numpy as np
from aicspylibczi import CziFile
import tifffile

# =============================================================================
# 1. GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/run/media/tiaan/Windows-SSD/czi/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/run/media/tiaan/Windows-SSD/czi/2026 rats/stitched_output/"

CHANNEL_TO_STITCH = 0 
Z_PLANE_TO_STITCH = 0
# =============================================================================

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

    print(f"Found {len(czi_files)} files. Starting batch processing...\n")

    for czi_path in czi_files:
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        out_tiff_path = os.path.join(output_dir, f"{base_name}.tiff")
        
        print(f"Processing: {filename}...")
        
        try:
            czi = CziFile(czi_path)
            
            # --- NEW ERROR HANDLING / SKIP LOGIC ---
            
            # 1. Check if the file is actually a mosaic (does it have an 'M' dimension?)
            if 'M' not in czi.dims:
                print(f"  -> Skipping {filename}: Not a mosaic (single image).")
                continue # Skips to the next file
            
            # 2. (Optional) Check if it has exactly 25 tiles (5x5)
            # czi.get_dims_shape() returns a list of dicts. We extract the size of 'M'.
            dimensions = czi.get_dims_shape()[0]
            tile_count = dimensions['M'][1] 
            
            if tile_count != 25:
                print(f"  -> Skipping {filename}: Found {tile_count} tiles instead of 25.")
                continue # Skips to the next file
                
            # ---------------------------------------

            # Dynamically build the arguments
            kwargs = {'scale_factor': 1.0}
            if 'C' in czi.dims: kwargs['C'] = CHANNEL_TO_STITCH
            if 'Z' in czi.dims: kwargs['Z'] = Z_PLANE_TO_STITCH
                
            # Read, squeeze, and save
            mosaic_data = czi.read_mosaic(**kwargs)
            mosaic_array = np.squeeze(mosaic_data)
            tifffile.imwrite(out_tiff_path, mosaic_array, bigtiff=True, imagej=True)
            
            print(f"  -> Success: Saved to {out_tiff_path} (Stitched {tile_count} tiles)")
            
        except Exception as e:
            print(f"  -> Error processing {filename}: {e}")

if __name__ == "__main__":
    process_microscopy_files()