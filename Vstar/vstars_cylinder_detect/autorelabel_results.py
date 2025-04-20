# VSTARS Ignore
from .vreturn_value_manager import VReturnValueManager

class AutoRelabelResults:
    """
    AutoRelabel results

    **autoRelabelRelabeledCount**
    The number of points that were relabeled.

    **autoRelabelNotRelabeledCount**
    The number of points that were not relabeled.

    **autoRelabelRMS**
    The RMS of the temporary alignment.

    **autoRelabelAutomatchedOnly**
    The state of the Relabel radio button (true=Only Automatched, false= All Points).

    **autoRelabelThreshold**
    The nearness threshold value used for the AutoRelabel.

    """
    def __init__(self):
        self.autoRelabelRelabeledCount = 0
        self.autoRelabelNotRelabeledCount = 0
        self.autoRelabelRMS = 0
        self.autoRelabelAutomatchedOnly = True
        self.autoRelabelThreshold = 0
        
    def update(self, rvManager: VReturnValueManager):
        self.autoRelabelRelabeledCount = rvManager.getValue("v.autoRelabelRelabeledCount")
        self.autoRelabelNotRelabeledCount = rvManager.getValue("v.autoRelabelNotRelabeledCount")
        self.autoRelabelRMS = rvManager.getValue("v.autoRelabelRMS")
        self.autoRelabelAutomatchedOnly = rvManager.getValue("v.autoRelabelAutomatchedOnly")
        self.autoRelabelThreshold = rvManager.getValue("v.autoRelabelThreshold")