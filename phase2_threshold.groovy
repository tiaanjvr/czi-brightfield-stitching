import qupath.lib.roi.GeometryTools
import qupath.lib.objects.PathObjects

// 1. Clear old annotations safely (Updated for QuPath 0.4+)
removeObjects(getAnnotationObjects(), false)

// 2. Detect the Black Padding (Ensure Thresholder assigns to "Artifact")
createAnnotationsFromPixelClassifier("Black_Padding", 0.0, 0.0)
def paddingObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Artifact" }

// 3. Detect the Tissue (Ensure Thresholder assigns to "Tissue")
createAnnotationsFromPixelClassifier("Brightfield_Mask", 10000.0, 0.0)
def tissueObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Tissue" }

if (tissueObjects.isEmpty()) {
    print "No tissue found! Please check that your 'Brightfield_Mask' thresholder assigns the class 'Tissue'."
    return
}

// 4. Mathematically Subtract Padding from Tissue
def newTissues = []
def plane = tissueObjects[0].getROI().getImagePlane()

for (tissue in tissueObjects) {
    def tissueGeom = tissue.getROI().getGeometry()
    
    // Subtract every piece of black padding from the tissue geometry
    for (padding in paddingObjects) {
        // FIX: Add a 5-pixel expansion (buffer) to the padding geometry.
        // This ensures it swallows any blurry anti-aliased pixels on the border!
        def paddingGeom = padding.getROI().getGeometry().buffer(2.0)
        tissueGeom = tissueGeom.difference(paddingGeom)
    }
    
    // If tissue remains after subtraction, save the perfectly trimmed outline
    if (!tissueGeom.isEmpty()) {
        def newRoi = GeometryTools.geometryToROI(tissueGeom, plane)
        newTissues << PathObjects.createAnnotationObject(newRoi, getPathClass("Tissue"))
    }
}

// 5. Clean up the board and add only the final, trimmed tissue mask
removeObjects(getAnnotationObjects(), false)
addObjects(newTissues)

// Lock the annotation so it isn't accidentally moved
getAnnotationObjects().each { it.setLocked(true) }
fireHierarchyUpdate()

print "Phase 2: Dual-Threshold Kidney Masking Complete!"



// Step 1: Save the Black Padding Thresholder
// Open your image. Go to Classify → Pixel classification → Create thresholder.
// Set Resolution to Full 1.10 µm/px 
// Channel to Average Channels.
// Smoothing to 0
// Set the Threshold to 10.
// Set Below threshold to Artifact (Leave "Above threshold" blank).
// Region to everywhere
// Name it Black_Padding and click Save.

// Step 2: Save the Tissue Thresholder
// Stay in the Thresholder menu.
// Set Resolution to Very High 2.19 µm/px 
// Channel to Average Channels.
// Smoothing to 0.5
// Change the Threshold to 1700.
// Set Below threshold to Tissue (Leave "Above threshold" blank).
// In the Create Objects menu, set Min object size to 10000 and Min hole size to 0 (for the Swiss cheese effect).
// Name it Brightfield_Mask and click Save.

