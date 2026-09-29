/*
 * Dual-threshold tissue masking for stitched brightfield slides (QuPath 0.4+).
 *
 * Creates one locked "Tissue" annotation per image, with the black padding
 * left around the edges of the stitched canvas removed.
 *
 * WARNING: all existing annotations on the image are deleted.
 *
 * Requires two pixel thresholders saved in the project
 * (Classify > Pixel classification > Create thresholder):
 *
 *   Black_Padding
 *     Resolution: Full (1.10 µm/px)   Channel: Average channels
 *     Smoothing sigma: 0              Threshold: 10
 *     Below threshold: Artifact       Above threshold: (none)
 *     Region: Everywhere
 *
 *   Brightfield_Mask
 *     Resolution: Very high (2.19 µm/px)   Channel: Average channels
 *     Smoothing sigma: 0.5                 Threshold: 1700
 *     Below threshold: Tissue              Above threshold: (none)
 *     Create objects: minimum object size 10000, minimum hole size 0
 */
import qupath.lib.roi.GeometryTools
import qupath.lib.objects.PathObjects

// 1. Clear existing annotations
removeObjects(getAnnotationObjects(), false)

// 2. Detect the black padding (class "Artifact")
createAnnotationsFromPixelClassifier("Black_Padding", 0.0, 0.0)
def paddingObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Artifact" }

// 3. Detect the tissue (class "Tissue")
createAnnotationsFromPixelClassifier("Brightfield_Mask", 10000.0, 0.0)
def tissueObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Tissue" }

if (tissueObjects.isEmpty()) {
    print "No tissue found! Please check that your 'Brightfield_Mask' thresholder assigns the class 'Tissue'."
    return
}

// 4. Subtract the padding from the tissue
def newTissues = []
def plane = tissueObjects[0].getROI().getImagePlane()

for (tissue in tissueObjects) {
    def tissueGeom = tissue.getROI().getGeometry()

    for (padding in paddingObjects) {
        // A 2-pixel buffer also removes the anti-aliased pixels along the padding border
        def paddingGeom = padding.getROI().getGeometry().buffer(2.0)
        tissueGeom = tissueGeom.difference(paddingGeom)
    }

    if (!tissueGeom.isEmpty()) {
        def newRoi = GeometryTools.geometryToROI(tissueGeom, plane)
        newTissues << PathObjects.createAnnotationObject(newRoi, getPathClass("Tissue"))
    }
}

// 5. Keep only the trimmed tissue annotations
removeObjects(getAnnotationObjects(), false)
addObjects(newTissues)

// Lock the annotations to prevent accidental edits
getAnnotationObjects().each { it.setLocked(true) }
fireHierarchyUpdate()

print "Tissue masking complete."
