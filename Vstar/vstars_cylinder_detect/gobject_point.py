# VSTARS Ignore
import math
import json

from .gmatrix import GMatrix

class GObjectPoint:
    def __init__(self):

        self.label = ""
        self.X = 0
        self.Y = 0
        self.Z = 0
        self.i = 0
        self.j = 0
        self.k = 0
        self.nRays = 0
        self.nTotalRays = 0

        self.offset = 0
        self.covariance = GMatrix()

    def fromDict(self, Dict):
        self.label = Dict["label"]
        self.X = Dict["X"]
        self.Y = Dict["Y"]
        self.Z = Dict["Z"]
        self.i = Dict["i"]
        self.j = Dict["j"]
        self.k = Dict["k"]
        self.nRays = Dict["nRays"]
        self.nTotalRays = Dict.get("nTotalRays", -1)

        self.offset = Dict["offset"]

        self.covariance.fromDict(Dict["covariance"])

    def fromJSON(self, jsonStr):
        data = json.loads(jsonStr)
        Dict = dict(data)
        self.fromDict(Dict)

    def distanceSquaredTo(self, other):
        return (self.X - other.X) * (self.X - other.X) + (self.Y - other.Y) * (self.Y - other.Y) + (self.Z - other.Z) * (self.Z - other.Z)

    def distanceTo(self, other):
        return math.sqrt(self.distanceSquaredTo(other))