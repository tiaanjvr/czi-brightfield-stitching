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
        def paddingGeom = padding.getROI().getGeometry()
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
