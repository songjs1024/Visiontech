# VSTARS Ignore
import json
import numpy as np

class GMatrix:
    def __init__(self):
        self.rows = 0
        self.cols = 0
        self.data = np.ndarray((0, 0))

    def fromJSON(self, jsonStr):
        json_data = json.loads(jsonStr)
        top = json_data["GMatrix"]
        self.fromDict(top)

    def fromDict(self, dict):
        self.cols = dict["cols"]
        self.rows = dict["rows"]
        temp1D = np.array(dict["data"])
        self.data = temp1D.reshape(self.rows, self.cols)
