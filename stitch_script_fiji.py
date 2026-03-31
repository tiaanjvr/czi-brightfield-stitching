import os
import glob
import subprocess

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
INPUT_FOLDER = "/home/tiaan/Downloads/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/home/tiaan/Downloads/2026 rats/stitched_output/fiji_batch/"

# You MUST update this path to point exactly to your extracted Fiji executable
# Example: "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64"
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
# =============================================================================

def fiji_batch_stitch():
    os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)
    czi_files = glob.glob(os.path.join(INPUT_FOLDER, "*.czi"))
    
    if not czi_files:
        print(f"No CZI files found in {INPUT_FOLDER}")
        return

    print(f"Found {len(czi_files)} files. Handing them over to headless Fiji...\n")

    for czi_path in czi_files:
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        
        print(f"Stitching {filename}...")
        
        # Fiji's plugin saves outputs as 'img_t1_z1_c1...' so we need a dedicated subfolder for each slide
        out_dir = os.path.join(OUTPUT_BASE_FOLDER, base_name)
        os.makedirs(out_dir, exist_ok=True)
        
        # The ImageJ Macro code
        # 'fusion_method=[Linear Blending]' is what erases the dark seams perfectly
        # 'compute_overlap' forces the phase correlation alignment
        macro_code = f"""
        run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by image metadata] browse=[{czi_path}] multi_series_file=[{czi_path}] fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Write to disk] output_directory=[{out_dir}]");
        run("Quit");
        """
        
        macro_path = os.path.join(out_dir, "stitch.ijm")
        with open(macro_path, "w") as f:
            f.write(macro_code)
            
        # Command to run Fiji completely invisibly via the terminal
        cmd = [FIJI_EXECUTABLE, "--headless", "-macro", macro_path]
        
        try:
            # We hide the massive amount of Fiji console text by sending it to DEVNULL
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            print(f"  -> Success: Saved to {out_dir}")
        except Exception as e:
            print(f"  -> Error on {filename}: {e}")

if __name__ == "__main__":
    fiji_batch_stitch()