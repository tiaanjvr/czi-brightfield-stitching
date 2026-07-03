import qupath.lib.roi.GeometryTools
import qupath.lib.objects.PathObjects

clearAnnotations()

// 1. Detect the Black Padding (Values < 10)
createAnnotationsFromPixelClassifier("Black_Padding", 0.0, 0.0)
def paddingObjects = getAnnotationObjects().findAll()

// 2. Detect the Tissue (Values < 1700)
// (This initially includes the black padding, because 0 is less than 1700)
createAnnotationsFromPixelClassifier("Brightfield_Mask", 100000.0, 0.0)
def tissueObjects = getAnnotationObjects().findAll { it.getPathClass() == getPathClass("Tissue") }

if (tissueObjects.isEmpty()) {
    print "No tissue found!"
    return
}

// 3. Mathematically Subtract Padding from Tissue
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

// 4. Clean up the board and add only the final, trimmed tissue mask
clearAnnotations()
addObjects(newTissues)

// Lock the annotation so it isn't accidentally moved
getAnnotationObjects().each { it.setLocked(true) }
fireHierarchyUpdate()

print "Phase 2: Dual-Threshold Kidney Masking Complete!"
