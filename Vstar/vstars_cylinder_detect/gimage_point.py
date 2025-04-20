# VSTARS Ignore
import math
import json

from .gmatrix import GMatrix

class GImagePoint:
    def __init__(self):

        self.label = ""
        self.x = 0
        self.y = 0
        self.vx = 0
        self.vy = 0

    def fromDict(self, Dict):
        self.label = Dict["label"]
        self.x = Dict["x"]
        self.y = Dict["y"]
        self.vx = Dict["vx"]
        self.vy = Dict["vy"]

    def fromJSON(self, jsonStr):
        data = json.loads(jsonStr)
        Dict = dict(data)
        self.fromDict(Dict)

    def distanceSquaredTo(self, other):
        return (self.x - other.x) * (self.x - other.x) + (self.y - other.y) * (self.y - other.y)

    def distanceTo(self, other):
        return math.sqrt(self.distanceSquaredTo(other))