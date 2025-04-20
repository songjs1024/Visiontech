# VSTARS Ignore
from .vreturn_value_manager import VReturnValueManager

class BundleStats:
    def __init__(self):
            self.bundleBadPictureCount = 0
            self.bundleTotalPictureCount = 0
            self.bundleTotalScalebarCount = 0
            self.bundleBadPointCount = 0
            self.bundleBadScalebarCount = 0
            self.bundleWeakPictureCount = 0
            self.bundleWeakPointCount = 0
            self.bundleWeakScalebarCount = 0
            self.bundleTotalPointCount = 0
            self.bundleTwoRayPointCount = 0
            self.bundleTotalInternalTriangulationRMS = 0
            self.bundleTotalRMSX = 0
            self.bundleTotalRMSY = 0
            self.bundleTotalRMSZ = 0
            self.bundleLimitingRMSX = 0
            self.bundleLimitingRMSY = 0
            self.bundleLimitingRMSZ = 0
            self.bundleResidualRMSx = 0
            self.bundleResidualRMSy = 0
            self.bundleResidualRMSxy = 0
            self.bundleAcceptedScaleBarCount = 0
            self.bundleRejectedImagePointCount = 0
            self.bundlePlanQualityFactor = 0
            self.bundleScaleBarRMS = 0

    def update(self, rvManager : VReturnValueManager):
            self.bundleBadPictureCount = rvManager.getValue("v.bundleBadPictureCount")
            self.bundleTotalPictureCount = rvManager.getValue("v.bundleTotalPictureCount")
            self.bundleTotalScalebarCount = rvManager.getValue("v.bundleTotalScalebarCount")
            self.bundleBadPointCount = rvManager.getValue("v.bundleBadPointCount")
            self.bundleBadScalebarCount = rvManager.getValue("v.bundleBadScalebarCount")
            self.bundleWeakPictureCount = rvManager.getValue("v.bundleWeakPictureCount")
            self.bundleWeakPointCount = rvManager.getValue("v.bundleWeakPointCount")
            self.bundleWeakScalebarCount = rvManager.getValue("v.bundleWeakScalebarCount")
            self.bundleTotalPointCount = rvManager.getValue("v.bundleTotalPointCount")
            self.bundleTwoRayPointCount = rvManager.getValue("v.bundleTwoRayPointCount")
            self.bundleTotalInternalTriangulationRMS = rvManager.getValue("v.bundleTotalInternalTriangulationRMS")
            self.bundleTotalRMSX = rvManager.getValue("v.bundleTotalRMSX")
            self.bundleTotalRMSY = rvManager.getValue("v.bundleTotalRMSY")
            self.bundleTotalRMSZ = rvManager.getValue("v.bundleTotalRMSZ")
            self.bundleLimitingRMSX = rvManager.getValue("v.bundleLimitingRMSX")
            self.bundleLimitingRMSY = rvManager.getValue("v.bundleLimitingRMSY")
            self.bundleLimitingRMSZ = rvManager.getValue("v.bundleLimitingRMSZ")
            self.bundleResidualRMSx = rvManager.getValue("v.bundleResidualRMSx")
            self.bundleResidualRMSy = rvManager.getValue("v.bundleResidualRMSy")
            self.bundleResidualRMSxy = rvManager.getValue("v.bundleResidualRMSxy")
            self.bundleAcceptedScaleBarCount = rvManager.getValue("v.bundleAcceptedScaleBarCount")
            self.bundleRejectedImagePointCount = rvManager.getValue("v.bundleRejectedImagePointCount")
            self.bundlePlanQualityFactor = rvManager.getValue("v.bundlePlanQualityFactor")
            self.bundleScaleBarRMS = rvManager.getValue("v.bundleScaleBarRMS")