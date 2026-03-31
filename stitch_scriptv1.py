import os
import glob
from datetime import datetime
from pylibczi import CziFile
import tifffile

# =============================================================================
# 1. GLOBAL VARIABLES
# =============================================================================
# Use raw strings (r"") for Windows file paths to avoid escape character errors
INPUT_FOLDER = r"C:\Path\To\Your\Raw_CZI_Files"
OUTPUT_BASE_FOLDER = r"C:\Path\To\Your\Stitched_Output"

# For standard 2D brightfield/histology, we pull the first channel and focal plane.
# If your images have multiple fluorescent channels, you can adjust this.
CHANNEL_TO_STITCH = 0 
Z_PLANE_TO_STITCH = 0
# =============================================================================

def process_microscopy_files():
    # 2. Create the dynamically named output folder
    timestamp = datetime.now().strftime("%d%b%Y_at_%Hh%Mm%Ss")
    output_folder_name = f"tiff_output_{timestamp}"
    output_dir = os.path.join(OUTPUT_BASE_FOLDER, output_folder_name)
    
    # Create the folder (exist_ok prevents crashes if it already exists)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}\n")

    # 3. Take all CZI files in the input folder
    search_pattern = os.path.join(INPUT_FOLDER, "*.czi")
    czi_files = glob.glob(search_pattern)
    
    if not czi_files:
        print(f"No .czi files found in {INPUT_FOLDER}")
        return

    print(f"Found {len(czi_files)} files. Starting batch processing...\n")

    # 4. Perform the steps on each file
    for czi_path in czi_files:
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        
        # Keep the original filename, change extension to .tiff
        out_tiff_path = os.path.join(output_dir, f"{base_name}.tiff")
        
        print(f"Processing: {filename}...")
        
        try:
            # Open the CZI file
            czi = CziFile(czi_path)
            
            # Read the mosaic metadata and automatically stitch the tiles 
            # into a single 2D image matrix based on the X/Y stage coordinates.
            mosaic_array = czi.read_mosaic(C=CHANNEL_TO_STITCH, Z=Z_PLANE_TO_STITCH)
            
            # Save the stitched array as a TIFF
            # bigtiff=True is used safely in case your 5x5 grids exceed 4GB in memory
            # imagej=True writes metadata so Fiji can still easily read the final file
            tifffile.imwrite(out_tiff_path, mosaic_array, bigtiff=True, imagej=True)
            
            print(f"  -> Success: Saved to {out_tiff_path}")
            
        except Exception as e:
            print(f"  -> Error processing {filename}: {e}")

if __name__ == "__main__":
    process_microscopy_files()