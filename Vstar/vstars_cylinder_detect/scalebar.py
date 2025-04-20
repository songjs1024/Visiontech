# VSTARS Ignore

class ScaleDistance:
    def __init__(self):
        self.from_pt = ""
        self.to_point = ""
        self.is_active = False
        self.is_rejected = False
        self.distance = 0
        self.difference = 0

    def fromJSON(self, json):
        self.from_pt = json["tuple_element0"]
        self.to_point = json["tuple_element1"]
        self.is_active = json["tuple_element2"]
        self.is_rejected = json["tuple_element3"]
        self.distance = json["tuple_element4"]
        self.difference = json["tuple_element5"]

class ScaleBar:
    def __init__(self):
        self.name = ""
        self.is_active = False
        self.units = ""
        self.distances = []

    def fromJSON(self, json):
        self.name = json["tuple_element0"]
        self.is_active = json["tuple_element1"]
        self.units = json["tuple_element2"]
        for scaleDistStr in json["tuple_element3"]:
            scaleDist = ScaleDistance()
            scaleDist.fromJSON(scaleDistStr)
            self.distances.append(scaleDist)

class ScaleBars:
    def __init__(self):
        self.scalebars = []

    def fromJSON(self, json):
        for scaleStr in json["scalebars"]:
            scale = ScaleBar()
            scale.fromJSON(scaleStr)
            self.scalebars.append(scale)