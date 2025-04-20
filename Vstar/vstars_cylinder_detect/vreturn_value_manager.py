# VSTARS Ignore

class VReturnValue:
    """
    A simple return value sent back from V-STARS.
    """
    def __init__(self):
        self.key = ""
        self.value = 0


class VReturnValueManager:
    """
    class to parse the string archive retruned from V-STARS and stores the various "v." values
    """

    def __init__(self):
        self.list = []
        self.VSTARS_ERROR_LEVEL_END = 4
        self.VSTARS_ERROR_LEVEL_CONTINUE = 1
        self.VSTARS_ERROR_LEVEL_WARN = 3
        self.VSTARS_ERROR_LEVEL_PAUSE = 2

    def parse(self, data):
        dataStr = data.decode("utf-8")

        # Special case of error
        if dataStr.startswith("vstarsError"):
            rv = VReturnValue()
            rv.key = "v.execution_status"
            rv.value = -2
            self.storeReturnValue(rv)
        else:
            rv = VReturnValue()
            rv.key = "v.execution_status"
            rv.value = 0
            self.storeReturnValue(rv)

        start = dataStr.find("{") + 1
        end = dataStr.rfind("}")

        if (start == -1) or (end == -1):
            return

        dataStr = dataStr[start:end]
        strings = dataStr.split(";")

        for string in strings:
            token = string.split("=")
            if len(token) == 2:
                key = token[0]
                value = token[1]

                if (
                    (key.find("null") == 0)
                    or (key.find("this") == 0)
                    or (key.find("parent") == 0)
                    or (key.find("objectName") == 0)
                ):
                    continue

                rv = VReturnValue()
                rv.key = key

                if rv.key.find("v.") != 0:
                    #print("Note to GSI: {} is missing the v.".format(key))
                    rv.key = "v.{}".format(key)

                if value == "false":
                    rv.value = False
                elif value == "true":
                    rv.value = True
                else:
                    try:
                        rv.value = int(value)
                    except Exception:
                        try:
                            rv.value = float(value)
                        except Exception:
                            rv.value = value

                self.storeReturnValue(rv)

    def storeReturnValue(self, returnValue):
        """
        Internal function to store a return key/value or replaces the value if the key is already there
        """
        test = self.getValue(returnValue.key)
        if test is None:
            self.list.append(returnValue)
        else:
            self.replaceValue(returnValue)

    def replaceValue(self, returnValue):
        for item in self.list:
            if (item.key.find(returnValue.key) == 0) and (len(item.key) == len(returnValue.key)):
                item.value = returnValue.value
                return

    # gets the value named by key
    def getValue(self, key):
        for item in self.list:
            if (item.key.find(key) == 0) and (len(item.key) == len(key)):
                return item.value

        return None
    
