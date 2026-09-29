/*
 * Tissue masking and collagen quantification for Picrosirius Red / Fast Green
 * (PRFG) stained slides (QuPath 0.4+).
 *
 * 1. Creates the trimmed "Tissue" annotation (same method as tissue_mask.groovy).
 * 2. Measures the Sirius Red area inside the tissue with the "PR_Red_Mask"
 *    pixel classifier, without creating detection objects.
 * 3. Adds Sirius Red and Fast Green percentages to the tissue annotation's
 *    measurements. Fast Green is the tissue area that is not Sirius Red.
 *
 * WARNING: all existing annotations on the image are deleted.
 *
 * Requires the pixel classifiers Black_Padding and Brightfield_Mask (see
 * tissue_mask.groovy) and PR_Red_Mask saved in the project.
 */
import qupath.lib.roi.GeometryTools
import qupath.lib.objects.PathObjects

// =============================================================================
// STAGE 1: DUAL-THRESHOLD TISSUE MASKING
// =============================================================================
removeObjects(getAnnotationObjects(), false)

createAnnotationsFromPixelClassifier("Black_Padding", 0.0, 0.0)
def paddingObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Artifact" }

createAnnotationsFromPixelClassifier("Brightfield_Mask", 10000.0, 0.0)
def tissueObjects = getAnnotationObjects().findAll { it.getPathClass()?.getName() == "Tissue" }

if (tissueObjects.isEmpty()) {
    print "ERROR: No tissue found! Please check that 'Brightfield_Mask' assigns the class 'Tissue'."
    return
}

def newTissues = []
def plane = tissueObjects[0].getROI().getImagePlane()

for (tissue in tissueObjects) {
    def tissueGeom = tissue.getROI().getGeometry()
    for (padding in paddingObjects) {
        def paddingGeom = padding.getROI().getGeometry().buffer(2.0)
        tissueGeom = tissueGeom.difference(paddingGeom)
    }
    if (!tissueGeom.isEmpty()) {
        def newRoi = GeometryTools.geometryToROI(tissueGeom, plane)
        newTissues << PathObjects.createAnnotationObject(newRoi, getPathClass("Tissue"))
    }
}

removeObjects(getAnnotationObjects(), false)
addObjects(newTissues)
selectObjects(newTissues)

// =============================================================================
// STAGE 2: SIRIUS RED MEASUREMENT
// =============================================================================
print "Measuring Sirius Red area..."

// Adds per-class area measurements to the selected annotations
addPixelClassifierMeasurements("PR_Red_Mask", "Red_Signal")

getAnnotationObjects().each { it.setLocked(true) }
fireHierarchyUpdate()

// =============================================================================
// STAGE 3: AREA STATISTICS
// =============================================================================
def tissueObj = newTissues[0]
def measurements = tissueObj.getMeasurementList()

def server = getCurrentServer()
def pixelWidth = server.getPixelCalibration().getPixelWidthMicrons()
def pixelHeight = server.getPixelCalibration().getPixelHeightMicrons()
def pixelAreaMicrons = pixelWidth * pixelHeight

// Total tissue area
def totalPixelsRaw = tissueObj.getROI().getArea()
def totalArea = totalPixelsRaw * pixelAreaMicrons

// Sirius Red area from the pixel classifier measurements
def redArea = 0.0
measurements.getNames().each { name ->
    if (name.startsWith("Red_Signal:") && name.endsWith("area µm^2")) {
        redArea = measurements.get(name)
    }
}

// Fast Green area: remaining tissue
def greenAreaClean = totalArea - redArea

long totalPixels = Math.round(totalPixelsRaw)
long redPixels = Math.round(redArea / pixelAreaMicrons)
long greenPixels = Math.round(greenAreaClean / pixelAreaMicrons)

def redPct = (redArea / totalArea) * 100.0
def greenPct = 100.0 - redPct

measurements.put("Area: Green Tissue (µm^2)", greenAreaClean)
measurements.put("Percent: Sirius Red (%)", redPct)
measurements.put("Percent: Fast Green (%)", greenPct)

print "\n========================================================"
print "                 QUANTIFICATION RESULTS                 "
print "========================================================"
print String.format("Total Tissue Area:   %,.2f µm²  (~%,d pixels)", totalArea, totalPixels)
print String.format("Sirius Red Area:     %,.2f µm²  (~%,d pixels) | %.2f%%", redArea, redPixels, redPct)
print String.format("Calculated Green:    %,.2f µm²  (~%,d pixels) | %.2f%%", greenAreaClean, greenPixels, greenPct)
print "========================================================\n"
print "PRFG quantification complete."
