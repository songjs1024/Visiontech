# VSTARS Ignore
import math
import copy
import numpy as np

from .gmatrix import GMatrix

class GTransformationMatrix:
    def __init__(self):
        self.data = [[0]]
        self.data = [[0 for y in range(4)] for x in range(4)]

    def rotationMatrix(self):
        R = [[0]]
        R = [[0 for y in range(3)] for x in range(3)]

        for i in range(0, 3):
            for j in range(0, 3):
                R[i][j] = self.data[i][j]

        s = 1.0 / self.scale()

        Normalized = np.dot(R, s)

        return Normalized

    def fromGMatrix(self, src: GMatrix):
        if src.cols != 4:
            raise Exception("GMatrix must be 4x4")
        if src.rows != 4:
            raise Exception("GMatrix must be 4x4")

        self.data = copy.deepcopy(src.data)

        R = self.rotationMatrix()

        Rt = np.transpose(R)
        shouldBeIdentity = np.dot(Rt, R)
        ident = np.identity(3, float)
        norm = np.linalg.norm(ident - shouldBeIdentity)

        if norm > 1e-6:
            raise Exception("Not a valid transformation matrix")

    def scale(self):
        R = self.data

        s1 = math.sqrt(R[0][0] * R[0][0] + R[1][0] * R[1][0] + R[2][0] * R[2][0])
        # s2 = math.sqrt(R[0][1] * R[0][1] + R[1][1] * R[1][1] + R[2][1] * R[2][1])
        # s3 = math.sqrt(R[0][2] * R[0][2] + R[1][2] * R[1][2] + R[2][2] * R[2][2])
        return s1

    def shift(self):
        x = self.data[0][3]
        y = self.data[1][3]
        z = self.data[2][3]
        return x, y, z

    # Calculates rotation matrix to euler angles
    # The result is the same as MATLAB except the order
    # of the euler angles ( x and z are swapped ).
    def rotationMatrixToEulerAngles(self):

        R = self.rotationMatrix()
        sy = math.sqrt(R[0][0] * R[0][0] + R[1][0] * R[1][0])

        singular = sy < 1e-6

        if not singular:
            x = math.atan2(R[2][1], R[2][2])
            y = math.atan2(-R[2][0], sy)
            z = math.atan2(R[1][0], R[0][0])
        else:
            x = math.atan2(-R[1][2], R[1][1])
            y = math.atan2(-R[2][0], sy)
            z = 0

        return x, y, z