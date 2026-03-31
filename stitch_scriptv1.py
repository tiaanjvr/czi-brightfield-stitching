import os
import glob
from datetime import datetime
import numpy as np
from aicspylibczi import CziFile
import tifffile

# =============================================================================
# 1. GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/path/to/your/Raw_CZI_Files"  # Updated for Linux paths
OUTPUT_BASE_FOLDER = "/path/to/your/Stitched_Output"

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
            # 1. Open with Allen Institute's CZI reader
            czi = CziFile(czi_path)
            
            # 2. Read the mosaic. scale_factor=1.0 keeps it at 100% resolution
            mosaic_data = czi.read_mosaic(C=CHANNEL_TO_STITCH, Z=Z_PLANE_TO_STITCH, scale_factor=1.0)
            
            # 3. aicspylibczi returns a 4D array (T, Z, Y, X). Squeeze removes the empty T and Z.
            mosaic_array = np.squeeze(mosaic_data)
            
            # 4. Save to TIFF
            tifffile.imwrite(out_tiff_path, mosaic_array, bigtiff=True, imagej=True)
            
            print(f"  -> Success: Saved to {out_tiff_path}")
            
        except Exception as e:
            print(f"  -> Error processing {filename}: {e}")

if __name__ == "__main__":
    process_microscopy_files()