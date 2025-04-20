# VSTARS Ignore
import json

from .gobject_point import GObjectPoint

class GCloud:
    def __init__(self):
        self.points = list()

    def fromJSON(self, jsonStr):
        data = json.loads(jsonStr)

        top = data["GCloud"]

        pointsList = list(top["points"])

        for i in range(len(pointsList)):
            Dict = pointsList[i]
            point = GObjectPoint()
            point.fromDict(Dict)
            self.points.append(point)