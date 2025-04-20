# VSTARS Ignore
from .vreturn_value_manager import VReturnValueManager

class AlignmentStats:
    def __init__(self):
        self.PrimaryPointCount = -1
        self.SecondaryPointCount = -1
        self.CommonPointCount = -1
        self.AcceptedPointCount = -1
        self.RejectedPointCount = -1
        self.IterationCount = -1
        self.RejectionLimit = -1
        self.RMSX = -1
        self.RMSY = -1
        self.RMSZ = -1
        self.RMSTotal = -1

    def update(self, rvManager : VReturnValueManager):
        self.PrimaryPointCount = rvManager.getValue("v.alignmentPrimaryPointCount")
        self.SecondaryPointCount = rvManager.getValue("v.alignmentSecondaryPointCount")
        self.CommonPointCount = rvManager.getValue("v.alignmentCommonPointCount")
        self.AcceptedPointCount = rvManager.getValue("v.alignmentAcceptedPointCount")
        self.RejectedPointCount = rvManager.getValue("v.alignmentRejectedPointCount")
        self.IterationCount = rvManager.getValue("v.alignmentIterationCount")
        self.RejectionLimit = rvManager.getValue("v.alignmentRejectionLimit")
        self.RMSX = rvManager.getValue("v.alignmentRMSX")
        self.RMSY = rvManager.getValue("v.alignmentRMSY")
        self.RMSZ = rvManager.getValue("v.alignmentRMSZ")
        self.RMSTotal = rvManager.getValue("v.alignmentRMSTotal")