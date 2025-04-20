# VSTARS Ignore
import json

from .utilities import *

class GPhotogrammetryProjectCompareStats:
    def __init__(self):
        self.differentPointCount = True
        self.differentPointCloudCount = True
        self.differentCameraCount = True
        self.differentStationCount = True
        self.differentImagePointCount = True
        self.differentDreamMatrixCount = True
        self.mismatchLabel = True

        self.maxObjectX = 9999
        self.maxObjectY = 9999
        self.maxObjectZ = 9999
        self.aveObjectX = 9999
        self.aveObjectY = 9999
        self.aveObjectZ = 9999
        self.maxObjectCovariance = np.full(shape=(3, 3), fill_value=9999.0)
        self.maxDreamDiff = np.full(shape=(4, 4), fill_value=9999.0)
        self.maxImageX = 9999
        self.maxImageY = 9999
        self.aveImageX = 9999
        self.aveImageY = 9999
        self.maxImageVX = 9999
        self.maxImageVY = 9999

        self.maxC = 9999
        self.maxXP = 9999
        self.maxYP = 9999
        self.maxK1 = 9999
        self.maxK2 = 9999
        self.maxK3 = 9999
        self.maxP1 = 9999
        self.maxP2 = 9999
        self.maxB1 = 9999
        self.maxB2 = 9999

        self.maxImageWidth = 9999
        self.maxImageHeight = 9999
        self.maxPixelSize = 9999

        self.maxStationH = np.full(shape=(4, 4), fill_value=9999.0)

    def fromJSON(self, jsonStr):

        data = json.loads(jsonStr)

        top = data["GPhotogrammetryProjectCompareStats"]

        self.maxObjectCovariance = matrixFromDict(top["maxObjectCovariance"])
        self.maxDreamDiff = matrixFromDict(top["maxDreamDiff"])
        self.differentPointCount = top["differentPointCount"]
        self.differentPointCloudCount = top["differentPointCloudCount"]
        self.differentCameraCount = top["differentCameraCount"]
        self.differentStationCount = top["differentStationCount"]
        self.differentImagePointCount = top["differentImagePointCount"]
        self.differentDreamMatrixCount = top["differentDreamMatrixCount"]
        self.mismatchLabel = top["mismatchLabel"]
        self.maxObjectX = top["maxObjectX"]
        self.maxObjectY = top["maxObjectY"]
        self.maxObjectZ = top["maxObjectZ"]
        self.aveObjectX = top["aveObjectX"]
        self.aveObjectY = top["aveObjectY"]
        self.aveObjectZ = top["aveObjectZ"]

        self.maxImageX = top["maxImageX"]
        self.maxImageY = top["maxImageY"]
        self.aveImageX = top["aveImageX"]
        self.aveImageY = top["aveImageY"]
        self.maxImageVX = top["maxImageVX"]
        self.maxImageVY = top["maxImageVY"]

        self.maxC = top["maxC"]
        self.maxXP = top["maxxp"]
        self.maxYP = top["maxyp"]
        self.maxK1 = top["maxK1"]
        self.maxK2 = top["maxK2"]
        self.maxK3 = top["maxK3"]
        self.maxP1 = top["maxP1"]
        self.maxP2 = top["maxP2"]
        self.maxB1 = top["maxB1"]
        self.maxB2 = top["maxB2"]

        self.maxImageWidth = top["maximageWidth"]
        self.maxImageHeight = top["maximageHeight"]
        self.maxPixelSize = top["maxpixelSize"]

        self.maxStationH = matrixFromDict(top["maxStationH"])