# VSTARS Ignore
import numpy as np

def cmpValues(val, epsilon, msg):
    if abs(val) > epsilon:
        print("{} ({})".format(msg, abs(val)))
        return False

    return True

def matrixFromDict(matrixDict: dict) -> np.ndarray:

    # count of the rows and cols
    rows = 0
    while "value{}".format(rows) in matrixDict.keys():
        rows = rows + 1

    # count up the columns in the first row (matrix is square)
    firstRow = matrixDict["value0"]

    cols = 0
    while "value{}".format(cols) in firstRow.keys():
        cols = cols + 1

    # Creates a rows x cols matrix init'd to zero
    # Matrix = [[0 for y in range(cols)] for x in range(rows)]

    mt = np.zeros(shape=(cols, rows))

    try:
        for r in range(0, rows):
            rowValues = matrixDict["value{}".format(r)]
            for c in range(0, cols):
                mt[r][c] = rowValues["value{}".format(c)]
    except Exception as ex:
        print(str(ex))

    return mt
