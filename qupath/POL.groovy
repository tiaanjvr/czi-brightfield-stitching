/*
 * Export of tissue masks as GeoJSON for the polarised-light (POL) workflow
 * (QuPath 0.4+).
 *
 * Exports all annotations of class "Tissue" on the current image to
 * <project folder>/Exported_Masks/<image name>.geojson, where <image name> is
 * the image name up to the first ".". Images without a "Tissue" annotation
 * are skipped.
 */
import qupath.lib.objects.PathObjects

// Export folder inside the QuPath project. To use another location, replace
// with an absolute path using forward slashes, e.g. new File("C:/data/Exported_Masks")
def exportDir = new File(buildFilePath(PROJECT_BASE_DIR, "Exported_Masks"))
exportDir.mkdirs()

// Image name without extensions
def rawName = getProjectEntry().getImageName()
def coreName = rawName.split("\\.")[0]

def tissueMasks = getAnnotationObjects().findAll {
    it.getPathClass()?.getName() == "Tissue"
}

if (tissueMasks.isEmpty()) {
    print "Skipped ${coreName}: No 'Tissue' mask found."
    return
}

def path = new File(exportDir, coreName + ".geojson").getAbsolutePath()
exportObjectsToGeoJson(tissueMasks, path)

print "Exported: " + coreName + ".geojson to " + exportDir.getAbsolutePath()
