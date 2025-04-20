# VSTARS Ignore
import json

from .gmatrix import GMatrix
from .gimage_point import GImagePoint

class GPicture:
    def __init__(self):
        self.label = ""
        self.H = GMatrix()
        self.points = list()

    def fromJSON(self, jsonStr):
        data = json.loads(jsonStr)

        top = data["GPicture"]

        self.label = top["label"]
        self.H.fromDict(top["H"])

        pointsList = list(top["points"])

        for i in range(len(pointsList)):
            Dict = pointsList[i]
            point = GImagePoint()
            point.fromDict(Dict)
            self.points.append(point)