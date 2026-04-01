import os
import glob
import subprocess
import time
import shutil
import numpy as np
import tifffile
from aicspylibczi import CziFile

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
INPUT_FOLDER = "/home/tiaan/Downloads/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/home/tiaan/Downloads/2026 rats/stitched_output/perfect_pipelineP4/"
# =============================================================================
# Conclusion: Colours correct! Files compressed (sample file 423MB), timing added, saving successfully.

# (microscopy_env) tiaan@fedora:/mnt/data/dev/personal/stitch_script$ python p4test.py 
# --- PERFECT EXTRACTION & STITCHING PIPELINE ---

# [1/49] Processing: R26_PRFG2-0017.czi
#   -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#      (Completed in 3.5s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 62.2s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#      (Completed in 14.8s)
#   -> SUCCESS: Stitched and saved R26_PRFG2-0017.ome.tif (Total file time: 80.4s)

# [2/49] Processing: R30_HE-0002.czi
#   -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#      (Completed in 1.9s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 41.7s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#      (Completed in 10.1s)
#   -> SUCCESS: Stitched and saved R30_HE-0002.ome.tif (Total file time: 53.7s)

# [3/49] Processing: R30_PRFG-0003.czi
#   -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#      (Completed in 3.6s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 70.7s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#      (Completed in 17.5s)
#   -> SUCCESS: Stitched and saved R30_PRFG-0003.ome.tif (Total file time: 91.8s)

# [4/49] Processing: R30_PRFG-0004.czi
#   -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#      (Completed in 4.1s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 72.1s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#      (Completed in 23.4s)
#   -> SUCCESS: Stitched and saved R30_PRFG-0004.ome.tif (Total file time: 99.6s)

# [5/49] Processing: R30_PRFG-0005.czi
#   -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#      (Completed in 3.8s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 74.6s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#      (Completed in 15.1s)
#   -> SUCCESS: Stitched and saved R30_PRFG-0005.ome.tif (Total file time: 93.5s)

#  Ignore rhis prompt: ok cool, here is some output:
# (microscopy_env) tiaan@fedora:/mnt/data/dev/personal/stitch_script$ python stitch_script_extract_fiji.py 
# --- PERFECT EXTRACTION & STITCHING PIPELINE ---
# [1/49] Processing: R26_PRFG2-0017.czi
#  -> Stage 1: Extracting tiles and reading metadata using multiple threads...
#     (Completed in 4.1s)
#  -> Stage 2: Fiji mathematical blending...
#     (Completed in 67.0s)
#  -> Stage 3: Zlib compression and OME metadata wrapping...
#     (Completed in 18.7s)
#  -> SUCCESS: Stitched and saved R26_PRFG2-0017.ome.tif (Total file time: 89.8s)
# It still uses 200-400MB and saves as ".ome.tif", is that fine?
# Also give me a readme for the repo with 1. Evolution and tools used to develop this 2. 
# Libraries+versions used to run this script 3. Details of the microscopy_env. 
# Rememer to use extra quotation marks (```` some text ````) to not escape the output text box
    

def perfect_pipeline_stitch():
    if not os.path.exists(FIJI_EXECUTABLE):
        print(f"CRITICAL ERROR: Fiji not found at {FIJI_EXECUTABLE}")
        return

    os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)
    czi_files = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.czi")))
    total_files = len(czi_files)
    
    if total_files == 0:
        print("No CZI files found.")
        return

    print("--- PERFECT EXTRACTION & STITCHING PIPELINE ---")
    overall_start_time = time.time()
    
    for idx, czi_path in enumerate(czi_files, 1):
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        final_ome_tiff_path = os.path.join(OUTPUT_BASE_FOLDER, f"{base_name}.ome.tif")
        
        print(f"\n[{idx}/{total_files}] Processing: {filename}")
        file_start_time = time.time()
        
        if os.path.exists(final_ome_tiff_path):
            print("  -> Skipping: Output already exists.")
            continue

        temp_dir = os.path.join(OUTPUT_BASE_FOLDER, f"temp_{base_name}")
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_fiji_out = os.path.join(temp_dir, "fiji_stitched.tiff")
        
        try:
            # --- STAGE 1: MULTITHREADED PYTHON EXTRACTION ---
            stage1_start = time.time()
            print("  -> Stage 1: Extracting tiles and reading metadata using multiple threads...")
            czi = CziFile(czi_path)
            
            if 'M' not in czi.dims:
                print("  -> Skipping: Not a mosaic.")
                shutil.rmtree(temp_dir)
                continue
                
            tile_count = czi.get_dims_shape()[0]['M'][1]
            
            # Extract Metadata
            pixel_size_x, pixel_size_y = 1.0, 1.0
            try:
                x_node = czi.meta.find('.//Distance[@Id="X"]/Value')
                y_node = czi.meta.find('.//Distance[@Id="Y"]/Value')
                if x_node is not None: pixel_size_x = float(x_node.text) * 1e6
                if y_node is not None: pixel_size_y = float(y_node.text) * 1e6
            except Exception as e:
                print(f"     (Warning: Could not read physical pixel size. {e})")
            
            # --- THE MULTITHREADING FUNCTION ---
            def process_single_tile(m):
                # 1. Read the tile
                tile_data, _ = czi.read_image(M=m)
                tile_data = np.squeeze(tile_data) 
                
                # 2. Fix the color
                if len(tile_data.shape) == 3:
                    if tile_data.shape[0] == 3:      
                        tile_data = np.moveaxis(tile_data, 0, -1)
                        tile_data = tile_data[..., ::-1] 
                    elif tile_data.shape[-1] == 3:   
                        tile_data = tile_data[..., ::-1] 
                        
                # 3. Save to disk
                tile_name = f"tile_{m:02d}.tiff"
                tifffile.imwrite(os.path.join(temp_dir, tile_name), tile_data, photometric='rgb')
                
                # 4. Grab coordinates
                bbox = czi.get_mosaic_tile_bounding_box(M=m)
                return m, tile_name, bbox.x, bbox.y

            import concurrent.futures
            
            # Execute the tile processing across all available CPU cores
            extracted_data = {}
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(process_single_tile, m) for m in range(tile_count)]
                for future in concurrent.futures.as_completed(futures):
                    m, t_name, x, y = future.result()
                    extracted_data[m] = (t_name, x, y)
                    
            # Write the Fiji coordinate map in the correct sequential order
            tile_conf_path = os.path.join(temp_dir, "TileConfiguration.txt")
            with open(tile_conf_path, "w") as f:
                f.write("dim = 2\n\n")
                for m in range(tile_count):
                    t_name, x, y = extracted_data[m]
                    f.write(f"{t_name}; ; ({x}, {y})\n")
                    
            print(f"     (Completed in {time.time() - stage1_start:.1f}s)")
            
            # --- STAGE 2: FIJI PHASE CORRELATION STITCHING ---
            stage2_start = time.time()
            print("  -> Stage 2: Fiji mathematical blending...")
            macro_path = os.path.join(temp_dir, "stitch.ijm")
            
            macro_code = f"""
            run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by TileConfiguration] directory=[{temp_dir}] layout_file=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
            saveAs("Tiff", "{temp_fiji_out}");
            run("Close All");
            run("Quit");
            """
            with open(macro_path, "w") as f:
                f.write(macro_code)
                
            cmd = [FIJI_EXECUTABLE, "--headless", "--mem=10G", "-macro", macro_path]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if not os.path.exists(temp_fiji_out):
                print("  -> Error: Fiji failed to output the stitched TIFF.")
                continue
            print(f"     (Completed in {time.time() - stage2_start:.1f}s)")
            
            # --- STAGE 3: COMPRESSION & METADATA INJECTION ---
            stage3_start = time.time()
            print("  -> Stage 3: Zlib compression and OME metadata wrapping...")
            
            # Read Fiji's uncompressed output
            stitched_img = tifffile.imread(temp_fiji_out)
            
            # 1. Strip out any fake Z or T dimensions Fiji added (e.g., turns 1x3xYxX into 3xYxX)
            stitched_img = np.squeeze(stitched_img)
            
            # 2. If Fiji put the 3 Colors at the front (CYX), move them to the back (YXC)
            if len(stitched_img.shape) == 3 and stitched_img.shape[0] == 3:
                stitched_img = np.moveaxis(stitched_img, 0, -1)
            
            # Save it as a highly compressed, tiled, metadata-rich OME-TIFF
            tifffile.imwrite(
                final_ome_tiff_path,
                stitched_img,
                photometric='rgb',
                tile=(512, 512),
                compression='zlib',
                ome=True,
                metadata={
                    'axes': 'YXC',
                    'PhysicalSizeX': pixel_size_x,
                    'PhysicalSizeXUnit': 'µm',
                    'PhysicalSizeY': pixel_size_y,
                    'PhysicalSizeYUnit': 'µm',
                }
            )
            print(f"     (Completed in {time.time() - stage3_start:.1f}s)")
            print(f"  -> SUCCESS: Stitched and saved {base_name}.ome.tif (Total file time: {time.time() - file_start_time:.1f}s)")
                
        except Exception as e:
            print(f"  -> ERROR on {filename}: {e}")
            
        finally:
            # --- STAGE 4: CLEANUP ---
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    print("\n--- BATCH STITCHING COMPLETE ---")
    print(f"Grand Total Processing Time: {(time.time() - overall_start_time) / 60:.2f} minutes")

if __name__ == "__main__":
    perfect_pipeline_stitch()