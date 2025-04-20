# VSTARS Ignore
import json
from enum import Enum
from pathlib import Path
import pkg_resources
import platform
import re
import shutil
import socket
import sys
import threading
from threading import Event
import time

from .alignment_stats import AlignmentStats
from .autorelabel_results import AutoRelabelResults
from .bundle_stats import BundleStats
from .gcloud import GCloud
from .gpicture import GPicture
from .gmatrix import GMatrix
from .gphotogrammetry_project_compare_stats import GPhotogrammetryProjectCompareStats
from .gtransformation_matrix import GTransformationMatrix
from .scalebar import ScaleBars
from .singleton import Singleton
from .vreturn_value_manager import VReturnValueManager
from .utilities import *


class VError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class MTorresCommunication(Enum):
    USB9481 = 1
    USB6525 = 2

class VSocketHandler:
    """
    Handles the connection to V-STARS
    """

    def __init__(self, address, port):
        self.address = address
        self.port = port
        self.port2 = port + 1

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.socket.connect((self.address, self.port))
        self.socket2.connect((self.address, self.port2))

    def parseCommandName(self, commandString: str):
        name = ""
        index = commandString.find("(")
        if index > 0:
            name = commandString[0:index]

        return name

    def sendCommand(self, commandString):

        V = VSTARS()
        commandNameSent = self.parseCommandName(commandString)
        byteString = commandString.encode("utf-8")

        try:
            self.socket.send(byteString)
            self.socket.send(b"\0")
        except Exception:
            V.init(V.address, V.port)
            self.socket.send(byteString)
            self.socket.send(b"\0")

        data = b''

        while(True):
            part = self.socket.recv(2048)
            data += part

            if (len(part) < 2048 or part.endswith(b'\0')):
                break

        V.returnValueManager.parse(data)
        vstarsError = V.getValue("v.execution_status") == -2

        if V.CheckVstarsVersion(40090040000000):
            commandNameReceived = V.getValue("v.command")
            if commandNameReceived is not None:
                if commandNameReceived != commandNameSent:
                    print("**** response conflict. Sent {} Received {}".format(commandNameSent, commandNameReceived))

        V._VSTARS__setLastCommandError(vstarsError)

        if vstarsError is True:
            self.handleError()

    def handleError(self):
        """
        Handles a command error sent back by V-STARS
        """
        V = VSTARS()
        # errorLevel = V.getValue("v.errorLevel")
        # lastCommand = V.getValue("v.lastCommand")
        V.errorString = V.getValue("v.errorString")
        # busy = V.getValue("v.busyProcessing")

        if V.CheckVstarsVersion(40090040000000):
            V.AddErrorToScriptDoc(V.errorString)

        raise Exception(V.errorString)

        # stuff below here is not reached because of the raise above
        # is that correct?

        # if (busy is None):
        #     busy = False

        # if (busy):
        #     print(V.errorString)
        #     return

        # if (errorLevel == V.returnValueManager.VSTARS_ERROR_LEVEL_END):
        #     message = "Script error executing <{}>: {}".format(
        #         lastCommand, V.errorString)
        #     #print (message)
        #     V.Pause(message)
        #     sys.exit(0)
        # elif (errorLevel == V.returnValueManager.VSTARS_ERROR_LEVEL_CONTINUE):
        #     return
        # elif (errorLevel == V.returnValueManager.VSTARS_ERROR_LEVEL_PAUSE):
        #     message = "Script error executing <{}>: {}".format(
        #         lastCommand, V.errorString)
        #     message = message + "\n press OK to continue"
        #     V.Pause(message)
        #     #print (message)
        #     #input("press Enter to continue")

        # elif (errorLevel == V.returnValueManager.VSTARS_ERROR_LEVEL_WARN):
        #     message = "Script error executing <{}>: {}".format(
        #         lastCommand, V.errorString)
        #     #print (message)
        #     message = message + "\n Continue the script? Yes/No"
        #     V.Warn(message)
        #     #response = input("Continue the script? Yes/No ")
        #     if (V.responseNo()):
        #         sys.exit()


# Thread used to connect to Vstars
class VConnectionTimer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        V = VSTARS()
        self.commandHandler = V
        self.socketHandler = V.socketHandler
        self.connected = False

    def run(self):
        """
        Thread to handle tcp/ip connection to V-STARS
        """
        while not self.connected:
            try:
                if not self.connected:
                    self.socketHandler.connect()
                    self.connected = True

            except Exception:
                # Sleep for a 1/4 second and try again
                time.sleep(0.25)

class VDataSocketTimer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        V = VSTARS()
        self.commandHandler = V
        self.socketHandler = V.socketHandler

    def run(self):
        """
        Thread that automatically gets called to handle input data from V-STARS
        """

        data = ""

        count = 1
        while True:
            # self.socketHandler.socket2.settimeout(.1)
            try:
                tmp = self.socketHandler.socket2.recv(4096)

                data = data + tmp.decode("utf-8")

                # Old style data came in with <data> <\data>
                # just dump it because we don;t handle it in Python
                if data.find("<\\data>") >= 0:
                    data = ""
                    print(str(count))
                    count = count + 1
                elif data.find("<\\json>") >= 0:
                    jsonStrings = []
                    data = self.parseIntoJsonStrings(jsonStrings, data)

                    for jsonStr in jsonStrings:
                        # print(jsonStr)
                        if self.isJson("GCloud", jsonStr):
                            self.commandHandler.cloud = GCloud()
                            self.commandHandler.cloud.fromJSON(jsonStr)
                            if self.commandHandler.cloudEvent is not None:
                                self.commandHandler.cloudEvent.set()

                        elif self.isJson("GPicture", jsonStr):
                            self.commandHandler.picture = GPicture()
                            self.commandHandler.picture.fromJSON(jsonStr)
                            if self.commandHandler.pictureEvent is not None:
                                self.commandHandler.pictureEvent.set()

                        elif self.isJson("GPhotogrammetryProjectCompareStats", jsonStr):
                            self.commandHandler.photogrammetryProjectCompareStats = GPhotogrammetryProjectCompareStats()

                            try:
                                self.commandHandler.photogrammetryProjectCompareStats.fromJSON(jsonStr)
                            except Exception:
                                pass

                            if self.commandHandler.photogrammetryProjectCompareStatsEvent is not None:
                                self.commandHandler.photogrammetryProjectCompareStatsEvent.set()

                        elif self.isJson("GMatrix", jsonStr):
                            self.commandHandler.matrix = GMatrix()
                            self.commandHandler.matrix.fromJSON(jsonStr)
                            if self.commandHandler.matrixEvent is not None:
                                self.commandHandler.matrixEvent.set()

                        elif self.isJson("scalebars", jsonStr):
                            self.commandHandler.scaleBars = ScaleBars()
                            self.commandHandler.scaleBars.fromJSON(json.loads(jsonStr))
                            if self.commandHandler.scaleBarsEvent is not None:
                                self.commandHandler.scaleBarsEvent.set()

                        else:
                            print(jsonStr)

                    # data = data.replace("<json>", "")
                    # jsonStr = data.replace("<\\json>", "")
                    # self.commandHandler.jsonStr = jsonStr
                    # jsonStr = ''
                    # data = ''
            except Exception as e:
                print(str(e))

    def parseIntoJsonStrings(self, jsonStrings: list, data: str):
        header = "<json>"
        footer = "<\\json>"

        while data.find("<\\json>") >= 0:

            firstB = data.find(header)
            firstE = data.find(footer)

            subLen = firstE - firstB - len(footer) + 1
            start = firstB + len(header)

            subString = ""

            try:
                subString = data[start : start + subLen]
                jsonStrings.append(subString)

                start = firstE + len(footer)
                data = data[start:]

            except Exception:
                #  Let it fail
                subString = ""
                data = ""

        return data

    def isJson(self, objectName="", json=""):
        index1 = json.find("{")
        index2 = json.find("{", index1 + 1)

        index3 = json.find(objectName)
        if index3 > index1 and index3 < index2:
            return True

        return False


# This is the main class


class VSTARS(metaclass=Singleton):
    """
    The main interface class to control V-STARS From Python

    .. code:: python

        from vstars import VSTARS

        def main():
            # These 2 lines are essential for all VSTARS / Python scripts
            V = VSTARS()
            V.init()

            V.Pause("Hello World")

        if __name__ == "__main__":
            main()

    """

    # Deprecated
    def lastCommandError(self):
        return self._lastCommandError

    # Private function
    def __setLastCommandError(self, b):
        self._lastCommandError = b

    # The all doing command that will send via tcpip the ascii VSTARS command
    # Private function
    def __vexec(self, command):
        self.jsonStr = ""

        try:
            self.initCalled
        except Exception:
            self.init()

        #    print("Cannot call V-STARS commands before V.init() is called")
        #    exit(0)

        if self.verbose:
            print(time.strftime("%Y-%m-%dT%H:%M:%S: ", time.localtime()), command)

        self.socketHandler.sendCommand(command)

    # Private Function
    def __connect(self, address, port):
        self.socketHandler = VSocketHandler(address, port)
        self.connectionTimer = VConnectionTimer()
        self.connectionTimer.start()
        self.dataTimer = VDataSocketTimer()

    def init(self, address="localhost", port=1210):
        """
        :requires: *V-STARS 4.9.4.0 or greater*

        Initializes the Python-VSTARS link via TCP/IP

        :param address: the ip address of V-STARS
        :param port: the port on which V-STARS is listening.
        """

        self.verbose = False
        self.returnValueManager = VReturnValueManager()
        self.address = address
        self.port = port
        self.jsonStr = ""

        if not hasattr(self, 'connectionTimer'):
            self.__connect(address, port)
        
        self.initCalled = True
        self.errorString = ""
        self._lastCommandError = False
        self._vstarsVersion = 0

        try:
            vstarsPyVersion = pkg_resources.get_distribution("vstars").version
            print("V-STARS Python SDK Version " + vstarsPyVersion)
        except Exception as ex:
            print(str(ex))

        while not self.connectionTimer.connected:
            time.sleep(1)
            if not self.connectionTimer.connected:
                print("Waiting to connect...")

        if not self.dataTimer.is_alive():
            self.dataTimer.start()

        dottedVersion = self.GetVstarsVersion(numeric=False)

        print("Connected to V-STARS Version " + dottedVersion)
        self._vstarsVersion = self.__parseVstarsVersion(dottedVersion)        

        self.cloud = None
        self.cloudEvent = None

        self.picture = None
        self.pictureEvent = None

        self.matrix = None
        self.matrixEvent = None

        self.scaleBars = None
        self.scaleBarsEvent = None

        self.photogrammetryProjectCompareStats = None
        self.photogrammetryProjectCompareEvent = None
        
    def __parseVstarsVersion(self, dottedVersion):
        """
        Convert the dotted version to a single number
        """
        parts = dottedVersion.split(".")

        if len(parts) != 3:
            return 0

        major = int(parts[0])
        minor = int(parts[1])
        rev = 0
        hotfix = 0
        dev = 0

        # local dev builds are always zero
        if "-local_dev" in parts[2]:
            temp = parts[2].split("-local_dev")
            rev = int(temp[0])
            dev = 0
        elif "-dev" in parts[2]:
            if "san" in parts[2]:
                temp = parts[2].split("-dev-san")
            else:
                temp = parts[2].split("-dev")
            rev = int(temp[0])
            if " " in temp[1]:
                dev = int(temp[1][: temp[1].find(" ")])
            else:
                dev = int(temp[1])
        else:
            if minor > 8:
                temp = parts[2].split("-")
            else:
                temp = parts[2].split(" ")

            is_release = False

            if len(temp) <= 2:
                if minor > 8:
                    if " " in temp[-1]:
                        temp2 = temp[-1][: temp[-1].find(" ")]
                        is_release = temp2.isnumeric()
                    else:
                        is_release = temp[-1].isnumeric()
                else:
                    is_release = True

            if is_release:
                rev = int(temp[0])

                if minor > 8:
                    if " " in temp[1]:
                        hotfix = int(temp[1][: temp[1].find(" ")])
                    else:
                        hotfix = int(temp[1])
            else:
                rev = int(temp[0])
                if " " in temp[-1]:
                    temp2 = temp[-1][: temp[-1].find(" ")]
                    dev = int(re.findall("\\d+", temp2)[-1])
                else:
                    dev = int(re.findall("\\d+", temp[-1])[-1])

        # The version number will be of the form: MMMmmmrrrhhhdddd
        # v4.9.3-11     -> 40090030110000
        # v4.9.4-453dev -> 40090040000453
        vstarsVersion = dev
        vstarsVersion += hotfix * 10000
        vstarsVersion += rev * 10000000
        vstarsVersion += minor * 10000000000
        vstarsVersion += major * 10000000000000
        return vstarsVersion

    def setVerbose(self, b):
        """
        :requires: *V-STARS 4.9.4.0 or greater*

        :param b: Set to True to echo data sent back from V-STARS

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.verbose = b

    def RandomizeObjectCoordinates(self, filename="", sigma=0.0001):
        """
        Randomizes point coordinates for debugging and testing

        :requires: *V-STARS 4.9.5.0 or greater*

        :param filename: 3D file to randomize

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "RandomizeObjectCoordinates(filename={}, sigma={})".format(filename, sigma)
        self.__vexec(commandsStr)

    def GetVstarsVersion(self, numeric=False):
        """
        Gets the V-STARS version currently running

        :requires: *V-STARS 4.9.4.0 or greater*

        :param numeric:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "GetVstarsVersion(numeric={})".format(numeric)
        self.__vexec(commandsStr)
        rv = self.getValue("v.vstarsVersion")
        return rv

    def AddPoint(self, filename="", label="point", x=0, y=0, z=0):
        """
        Adds a point to the named cloud

        :requires: *V-STARS 4.9.6.0 or greater*

        :param filename: The cloud name to add the point to 
        :param label: The point label
        :param x: x of point (in mm)
        :param y: y of point (in mm)
        :param z: z of point (in mm)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "AddPoint(filename={}, label={}, x={}, y={}, z={})".format(filename, label, x, y, z)
        self.__vexec(commandsStr)
        rv = self.getValue("v.vstarsVersion")
        return rv

    def AddBox(self, filename="", min_x=0., max_x = 0., min_y=0., max_y = 0.,min_z=0., max_z = 0.):
        """
        Adds a box to the named cloud

        :requires: *V-STARS 4.9.6.0 or greater*

        :param filename: The cloud name to add the box to 
        :param label: The point label
        :param min_x: min_x of box (in mm)
        :param max_x: max x of box (in mm)
        :param min_y: min_y of box (in mm)
        :param max_y: max y of box (in mm)
        :param min_z: min_z of box (in mm)
        :param max_z: max z of box (in mm)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "AddBox(filename={}, min_x={}, max_x={}, min_y={}, max_y={}, min_z={}, max_z={})".format(filename, min_x, max_x, min_y, max_y, min_z, max_z)
        self.__vexec(commandsStr)
        rv = self.getValue("v.vstarsVersion")
        return rv

    def CheckVstarsVersion(self, version):
        """
        Checks the version number against the currently connected Vstars version.

        :param version: The version number to check

        The version number is of the form form MMMmmmrrrhhhdddd, where MMM is
        the major version, mmm is the minor version, rrr is the revision,
        hhh is the hotfix version and dddd is the dev version.

        :returns: True if the currently connected Vstars version is greater than or equal to version.
        """
        try:
            self.initCalled
        except Exception:
            self.init()
        return self._vstarsVersion >= version

    def GetVstarsVersionNumeric(self):
        """
        Gets the V-STARS version currently running as a single integer

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        return self._vstarsVersion

    def getValue(self, key):
        """
        Function to get various **v.xxx** return values from V-STARS' commands

        :requires: *V-STARS 4.9.4.0 or greater*

        :param key:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        return self.returnValueManager.getValue(key)

    def scriptContinueData(self):
        """
        Returns the value of 'v.scriptContinueData' Used in conjunction with a USB6525

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        test = self.returnValueManager.getValue("v.scriptContinueData")
        if test is None:
            return -9999
        return test

    def toolName(self):
        test = self.returnValueManager.getValue("v.toolName")
        if test is None:
            return ""
        return test

    def partCount(self):
        test = self.returnValueManager.getValue("v.partCount")
        if test is None:
            return ""
        return test

    def ProjectBundleSetup(self, BundleConvergenceLimit=None, TotalErrorPropagation=None, MinimumRays=None, VOD=None):
        """
        Set various bundle settings.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param BundleConvergenceLimit: Value to indicate when the bundle has converged.
        :param TotalErrorPropagation: If True the total error propagation will be performed when the bundle converges.
        :param MinimumRays: sets the minimum rays required for a point in the bundle.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.Bundle.Setup("

        if BundleConvergenceLimit is not None:
            commandString += "Bundle Convergence Limit={},".format(BundleConvergenceLimit)
        if TotalErrorPropagation is not None:
            commandString += "Total Error Propagation={}, ".format(TotalErrorPropagation)
        if MinimumRays is not None:
            commandString += "Minimum Rays={}, ".format(MinimumRays)
        if VOD is not None:
            commandString += "VOD={},".format(VOD)
        commandString += ")"
        self.__vexec(commandString)

    # Start defining VSTARS commands
    def ProjectBundleRun(self, start=True, accept=True, initialBundle=False):
        """
        Runs a bundle for the currently loaded project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param start: When True the bundle will start automatically.
        :param initialBundle: When this parameter is set to true, V-STARS will run an initial bundle.
        :param accept: When True, V-STARS will automatically accept the bundle and the next script command will run.

        Return Values:

        **BundleStats**
        Return an object to the bundle stats

        **NOTE:** If the bundle has been scaled using code-scale, bundle_results.bundleTotalScalebarCount will be reported as a negative number. Eg. if 5 coded targets where used as scale bundle_results.bundleTotalScalebarCount will be set to -5.
        These are RMS accuracies estimates in object space that the script can use after the bundle has run:
        bundle_results.bundleTotalRMSX bundle_results.bundleTotalRMSY bundle_results.bundleTotalRMSZ bundle_results.bundleLimitingRMSX bundle_results.bundleLimitingRMSY bundle_results.bundleLimitingRdMSZ
        These are image space residuals that the script can use after the bundle has run:
        bundle_results.bundleResidualRMSx bundle_results.bundleResidualRMSy bundle_results.bundleResidualRMSxy
        These are other Bundle variables that the script can use after the bundle has run:
        bundle_results.bundlePlanQualityFactor

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("Project.Bundle.Run(Start={}, Accept={}, Initial Bundle={})").format(
            start, accept, initialBundle
        )
        self.__vexec(commandString)
        results = BundleStats()
        results.update(self.returnValueManager)
        return results

    def ProjectBundleSummary(self, filename=None):
        """
        Get bundle statistic.

        :requires: *V-STARS 4.9.6.0 or greater*

        :param filename: The bundle name (required if not overwriting bundle folder, except if there is only one bundle).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.Bundle.Summary("

        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += ")"
        self.__vexec(commandString)
        stats = BundleStats()
        stats.update(self.returnValueManager)
        return stats

    def ShowPythonConsole(self, show=True):
        """
        Command to show or hide Python Console When scripts are run

        :requires: *V-STARS 4.9.4.0 or greater*

        :param show:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "ShowPythonConsole(show={})".format(show)
        self.__vexec(commandStr)

    def ProSpotInit(self, timeout_sec = 90):

        try:
            self.ProSpotFocus(init=True)
        except:
            return False

        tick = 0
        moving = True
        focusInitialized = False
        while (moving or not focusInitialized ):
            try:
                self.ProSpotStatus()
                moving = self.returnValueManager.getValue("v.proSpotFocusing")
                focus = self.returnValueManager.getValue("v.proSpotFocus")
                if (focus > -9000 and focus < 9000):
                    focusInitialized = True

                if (moving or not focusInitialized):
                    time.sleep(1)
                    #print ("moving {} focus {} ".format(moving, focus))
                    tick = tick + 1

                if (tick > timeout_sec):
                    return False
            except:
                return False

        print ("inited in {}  secs".format(tick))
        return True

    def ProspotComboModeOn(self):
        """
        Puts prospot into Combo Shot Mode

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "ProspotComboModeOn()"
        self.__vexec(commandStr)

    def SetCodeAlias(self, codes=None, postfix=None, scalebar=False):
        """
        Set up a code or codes to take on an alias

        :requires: *V-STARS 4.9.4.0 or greater*

        :param codes: a string containing the names of codes to alias as in codes="1 2 5 8"
        :param postfix: a string to be appended onto the normal code name eg. CODE1 become CODE1_A
        :param scalebar:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SetCodeAlias("

        if codes is not None:
            commandString += f"codes={codes},"

        if postfix is not None:
            commandString += f"postfix={postfix},"

        commandString += f"scalebar={scalebar})"

        self.__vexec(commandString)

    def AliasCodesInPictures(self, codes=None, pictures=None, postfix=None):
        """
        Rename codes in pictures with a prefix

        :requires: *V-STARS 4.9.7.0 or greater*

        :param codes: a string containing the names of codes to alias as in codes="1 2 5 8"
        :param pictures: a string containing the numbers of pictures to relabel
        :param postfix: a string to be appended onto the normal code name eg. CODE1 become CODE1_A

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """

        commandString = "AliasCodesInPictures("

        if codes is not None:
            commandString += f"codes={codes},"

        if pictures is not None:
            commandString += f"pictures={pictures},"

        if postfix is not None:
            commandString += f"postfix={postfix},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def AddMovableCodes(self, codes=None):
        """
        Set up a code or codes to take on an alias

        :requires: *V-STARS 4.9.4.2 or greater*

        :param codes: a string containing the names of codes to set as movable as in codes="1 2 5 8"

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "AddMoveableCodes("

        if codes is not None:
            commandString += f"codes={codes}"

        commandString += ")"
        self.__vexec(commandString)

    def RelabelPicturePoint(self, picture=-1, old_label="", new_label=""):
        
        commandString = f"RelabelPicturePoint(picture={picture}, old_label={old_label}, new_label={new_label})"
        
        self.__vexec(commandString)
        
        return self.returnValueManager.getValue("v.PointRelabeled")

    def FFTFind(
        self,
        filename: str = None,
        project: bool = None,
        deletePlanes: bool = None,
        doSpecialTest: bool = None):
        """
        Searches a 3D file for Flange Feature Targets (FFTs).

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The filename to search
        :param project: If True, the FFT points are projected to a best-fit plane formed from the FFT points. These projected points are labeled _PFX where X is the FFT code number. These best-fit plane will be labeled _FX to matched their corresponding
        :param deletePlane: Delete the FFT planes

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "FFTFind("
        
        if filename is not None:
            commandString += f"filename={filename},"

        if project is not None:
            commandString += f"project={project},"

        if deletePlanes is not None:
            commandString += f"delete planes={deletePlanes},"

        if doSpecialTest is not None:
            commandString += f"doSpecialTest={doSpecialTest},"

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def FFTRelabel(
        self,
        filename: str = None,
        relabel: bool = None,
        tolerance: float = None):
        """
        Relabel Flange Feature Targets (FFTs) based on a relabel file.

        :requires: *V-STARS 4.9.8.20 or greater*

        :param filename: The filename to search
        :param relabel: The filename containing the relabel points
        :param tolerance: The search tolerance in units of filename

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "FFTRelabel("
        
        if filename is not None:
            commandString += f"filename={filename},"

        if relabel is not None:
            commandString += f"relabel={relabel},"

        if tolerance is not None:
            commandString += f"tolerance={tolerance},"

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def Find4PointBCDs(
        self,
        filename: str = None,
        prefix: str = None,
        minDiameter: float = None,
        maxDiameter: float = None,
        useSelection: bool = None
    ):
        """
        Find the four point BCDs

        :requires: *V-STARS 4.9.6.0 or greater*

        :param filename:
        :param prefix:
        :param minDiameter:
        :param maxDiameter:
        :param useSelection:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Find4PointBCDs("

        if filename is not None:
            commandString += f"filename={filename},"
        if prefix is not None:
            commandString += f"prefix={prefix},"
        if minDiameter is not None:
            commandString += f"min diameter={minDiameter},"
        if maxDiameter is not None:
            commandString += f"max diameter={maxDiameter},"
        if useSelection is not None:
            commandString += f"use selection={useSelection},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        
        self.__vexec(commandString)

    def ProjectAutomeasure(
        self,
        begin=None,
        cont=None,
        close=None,
        findNewPoints=None,
        solvePictureStations=None,
        showPictures=None,
        attendedMode=None,
        intermediateBundlesInitial=None,
        finalBundleInitial=None,
        hideBundleWarnings=None,
        hideDialogs=None,
        testing=None,
    ):
        """
        Starts the AutoMeasure dialog. Note regarding default values: The default condition of many of these parameters is set by how the user last used the dialog. It is best to be explicit when using these parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param cont: If True, Starts the process as if the continue button had been pressed.
        :param begin: If True, the automeasure dialog will show and begin automatically (as if the Begin button were pressed)
        :param close: If True, closes the both the final bundle dialog and the Automeasure dialog when done.
        :param findNewPoints: If True, causes the automeasure to find new points.
        :param solvePictureStations: If False, causes the solve picture stations step to be skipped. Normally this will default to True.
        :param showPictures: If False, causes the pictures to be scanned using multiple threads.
        :param attendedMode: If True, the automeasure process will proceed in attended mode.
        :param intermediateBundlesInitial: If True, Intermediate bundles will be run as initial bundles
        :param finalBundleInitial: If True, Final bundle will be run as initial bundle
        :param hideBundleWarnings: If True, Hide bundle warning messages
        :param hideDialogs: If True, Hide the automeasure and bundle dialogs
        :param testing:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.Automeasure("

        if begin is not None:
            commandString += f"begin={begin},"

        if cont is not None:
            commandString += f"continue={cont},"

        if close is not None:
            commandString += f"close={close},"

        if findNewPoints is not None:
            commandString += f"find new points={findNewPoints},"

        if solvePictureStations is not None:
            commandString += f"solve picture stations={solvePictureStations},"

        if showPictures is not None:
            commandString += f"show pictures={showPictures}"

        if attendedMode is not None:
            commandString += f"attended mode={attendedMode},"

        if intermediateBundlesInitial is not None:
            commandString += f"intermediate bundles initial={intermediateBundlesInitial},"

        if finalBundleInitial is not None:
            commandString += f"final bundle initial={finalBundleInitial},"

        if hideBundleWarnings is not None:
            commandString += f"hide bundle warnings={hideBundleWarnings},"

        if hideDialogs is not None:
            commandString += f"hide dialogs={hideDialogs},"

        if testing is not None:
            commandString += f"testing={testing},"

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)
        results = BundleStats()
        results.update(self.returnValueManager)
        return results
        # Hide bundle warnings
        # When present, warnings about running an initial bundle during the final bundle sequence will be hidden
        # from the user.

    def ReverseAllTemplates(self, reverseX=False, reverseY=False, reverseZ=False):
        """
        Special function to reverse the sign of the given X, Y or Z coordinates of all 3D templates.
        Useful for converting to eg. Left hand side of a symmetric object

        :requires: *V-STARS 4.9.4.0 or greater*

        :param reverseX:
        :param reverseY:
        :param reverseZ:

        :return: The reverse count

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ReverseAllTemplates("
        commandString += ("reverseX={}, reverseY={}, reverseZ={})").format(reverseX, reverseY, reverseZ)

        self.__vexec(commandString)
        return self.getValue("v.reverseCount")

    def PatternRelabel(
        self,
        filename=None,
        pattern=None,
        relabelCloseness=-1.0,
        distanceMatch=-1.0,
        transformRejectionFactor=4.44,
        onlyAutomatched=True,
        minPatternDistance=1,
        ransac=False,
    ):
        """
        Relabels points in a 3D file with labels from another 3D file. Unlike 3D.AutoRelabel(), this command does not require any common labels between the two files. Using a two-phase approach, 1st a pattern match is performed to identify common points based on common distances. Then 2nd a temporary alignment is performed using these common points, which allows the remaining points to be relabeled based on their closeness.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to relabel. It must exist in the current project. If no filename is specified, the driver file is used.
        :param pattern: The name of the 3D file that defines the pattern. It must exist in the current project.
        :param distanceMatch: The pattern search identifies common points using a distance match. The distance match parameter is the tolerance (in project units) for determining if a pair of points in the 3D file specified by filename matches a pair of points in the pattern 3D file.
        :param transformRejectionFactor: After a sufficient number of points (3 or more) are pattern matched using the distance match parameter, a coordinate transformation is done. Points above this transform rejection criterion are not used in the transformation calculation.
        :param relabelCloseness: After the pattern match phase, points in filename 3D file are aligned to the pattern 3D file's coordinate system. Points in filename are relabeled if they are less than relabel closeness from a corresponding point in pattern.
        :param onlyAutomatched: If present, only points that were automatched will be relabeled.
        :param minPatternDistance:
        :param ransac:

        **NOTE:** This command was previously called "3D.Match" and "3D.Pattern Relabel". Any uses of these command names will be forwarded to PatternRelabel.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "PatternRelabel("

        if filename is not None:
            commandString += ("filename={},").format(filename)

        if pattern is not None:
            commandString += ("pattern={},").format(pattern)

        commandString += ("relabel closeness={}, distance match={}, transform rejection={},").format(
            relabelCloseness, distanceMatch, transformRejectionFactor
        )

        commandString += ("only automatched={}, minPatternDistance={}, ransac={})").format(
            onlyAutomatched, minPatternDistance, ransac
        )

        self.__vexec(commandString)

    def EnableNuggets(self, codes=""):
        """
        Enables a coded target's or range of coded targets' nuggets.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param codes: A string of code space separated numbers whose nuggets will get enabled

        :examples:

        .. code:: python

            V.EnableNuggets(codes="1 4 6 8")
            # will enable nuggets for CODE1, CODE4, CODE6 & CODE8.

            V.EnableNuggets(codes="7-11")
            # will enable pictures CODE7, CODE8, CODE9, CODE10 & CODE11.

            V.EnableNuggets(codes="all")
            # will enable all codes.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "EnableNuggets(codes={})".format(codes)

        self.__vexec(commandString)

    def DisableNuggets(self, codes=""):
        """
        Disables a coded target's or range of coded targets' nuggets.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param codes: A string of space separated code numbers whose nuggets will get disabled

        :examples:

        .. code:: python

            V.DisableNuggets(codes = "1 4 6 8")
            # will disable nuggets for CODE1, CODE4, CODE6 & CODE8.

            V.DisableNuggets(codes = "7-11")
            # will disable nuggets for CODE7, CODE8, CODE9, CODE10 & CODE11.

            V.DisableNuggets(codes = "all")
            # will disable all code nuggets.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "DisableNuggets(codes={})".format(codes)
        self.__vexec(commandString)

    def ProjectGlobalPointEdit(self, newLabel=None, oldLabel=None, enable="", disable="", delete=""):
        """
        Used to enable, disable or delete points from all pictures in the currently opened project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param enable: A list of labels (separated by a blank space) of points to be enabled in all pictures.
        :param disable: A list of labels (separated by a blank space) of points to be disabled in all pictures.
        :param delete: A list of labels (separated by a blank space) of points to be deleted in all pictures.
        :param oldLabel: The old label
        :param newLabel: Use these two parameters together to globally re-label the point "old label" to "new label". Re-labels the point in all pictures and the Driver file.

        **NOTE:** Labels may include wild-cards. For example enable=SCALE* will enable all points that begin with the label SCALE (case does not matter). Also, just using the asterisk character (*) will enable or disable or delete all the points.

        **WARNING!** Only one of the above parameters should be used in the parameter list or unpredictable results can occur.

        :example:

        .. code:: python

            ProjectGlobalPointEdit(disable = "*")
            ProjectGlobalPointEdit(enable = "line1 line2 plane*")
            #Disables all points, then enables points 'line1', 'line2' and all points that start with 'plane'

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.Global Point Edit("
        if len(enable) > 0:
            commandString += (", enable={}").format(enable)
        if len(disable) > 0:
            commandString += (", disable={}").format(disable)
        if len(delete) > 0:
            commandString += (", delete={}").format(delete)
        if newLabel is not None:
            commandString += ", new label={}".format(newLabel)
        if oldLabel is not None:
            commandString += ", old label={}".format(oldLabel)
        commandString += ")"
        self.__vexec(commandString)

    def ProjectImportImages(self, above=False, below=False):
        """
        Imports images to the project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param above: Optional When true the images will be stored in the folder above the project folder.
        :param below: Optional When true the images will be stored in the folder below the project folder.

        **NOTE**: When neither of the above parameters are specified, the images are stored in the project folder.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("Project.Import.Images(Above={}, Below={})").format(above, below)
        self.__vexec(commandString)

    def PicturesSetImagePath(self, path: str = None):
        """
        Set the image path for the current project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param path: The new full image path.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Pictures.Set Image Path("
        if path is not None:
            commandString += "path={}".format(path)
        commandString += ")"
        self.__vexec(commandString)

    def PicturesInformation(self, index: int = None, picture: int = None, radians: bool = None):
        """
        Command to return information about the specified picture.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param index: The picture number whose information will be returned.
        :param radians: If true, the angles will be expressed in radians, otherwise they will be specified in degrees.

        The return vales can be accessed by using the V.getValue() function for example:

        .. code:: python

            V.PicturesInformation(picture=14)
            Y = V.getValue("v.pictureY")

        **Return Values:**

        **v.pictureX**
        The X location of the picture.

        **v.pictureY**
        The Y location of the picture.

        **v.pictureZ**
        The Z location of the picture.

        **v.pictureAzimuth**
        The azimuth angle.

        **v.pictureElevation**
        The elevation angle.

        **v.pictureRoll**
        The roll angle.

        **v.pictureTotalResidualRMS**
        The RMS of the resection residuals.  -1.0 indicates that the picture is not resected.

        **v.pictureNumberOfPoints**
        The number of points, including scan points, in the picture.

        **v.pictureNumberOfNonScanPoints**
        The number of identified points in the picture.

        **v.pictureNumberOfCodes**
        The number of coded targets identified in the picture.

        **v.pictureNumberOfResectionPoints**
        The number of points identified in the picture that are also found in the current driver file.

        **v.pictureNumberOfResectionCodes**
        The number of coded targets identified in the picture that are also found in the current driver file.

        **v.day v.month v.year**
        The date the image was captured. The day and month will be numeric and the year will be represented as a four-digit value.

        **v.hour v.minute v.second**
        The time of day the image was captured in 24 hour format.

        **v.xres v.yres**
        The X and Y resolution of the image.

        **v.shutterUS**
        The shutter value used to capture the image in microseconds.

        **v.strobe**
        The strobe value used to capture the image. Inca and DynaMo cameras will use the standard GSI 1-32 value. DSLR cameras will use a percentage of total power.

        **v.compression**
        The standard GSI compression value.

        **v.compressionQuality**
        The JPEG quality.

        **v.compressionString**
        The compression value represented as a character string if the image was captured with a DSLR.

        **v.serialNumber**
        The serial number of the camera.

        **v.firmware1 v.firmware2 v.firmware3 v.firmware4**
        The four numeric firmware version numbers. The Inca camera firmware version is comprised of four parts.

        **v.timeStamp**
        The 64-bit image time stamp. Used to keep track of image sequences in high speed applications.

        **v.cameraName**
        The name of the camera.

        **v.imageName**
        The name of the image file.

        **v.iso**
        The ISO value. (DSLR only)

        **v.fnumber**
        The f-number. (DSLR only)

        **v.whiteBalance**
        The white balance value represented as a character string. (DSLR only)

        **v.shutterCount**
        The number of shutter releases at the time of image capture. (DSLR only)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Pictures.Information("

        # one or the other
        if index is not None:
            commandString += "index={},".format(index)
        elif picture is not None:
            commandString += "picture={},".format(picture)

        if radians is not None:
            commandString += "radians={},".format(radians)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def PictureIsResected(self, index: int = None, picture: int = None):
        """
        Command to determine if a picture is resected or not.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param picture: The picture number to test.

        Return values:

        **v.pictureIsResected**
        True if the picture is resected, False if not

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "PictureIsResected("

        # one or the other
        if index is not None:
            commandString += "index={}".format(index)
        elif picture is not None:
            commandString += "picture={}".format(picture)

        commandString += ")"
        self.__vexec(commandString)
        rv = self.getValue("v.pictureIsResected")
        return rv

    def GetDrivebackMedianPixelOfROI(self, image: int, filename = "", output_csv_file = "", roi_width: int = None, roi_height: int = None):
        """
        Command to get the median of the pixel ROI for a back projected 3d point.

        :requires: *V-STARS 4.9.7.0 or greater*

        :param image: The picture index.
        :param filename: The cloud filename to use, uses the driver file if empty.
        :param output_csv_file: The filename of the output csv file. If empty the value of "PictureIndex - filename - roi_width x roi_height.csv" is used.
        :param roi_width: The roi width to use. If both roi width and height are not provided, the zoom window ROI is used.
        :param roi_height: The roi height to use. If both roi width and height are not provided, the zoom window ROI is used.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetDrivebackMedianPixelOfROI("
        commandString += "image={},".format(image)
        commandString += "filename={},".format(filename)
        commandString += "output={}".format(output_csv_file)

        if roi_width is not None:
            commandString += ",roi_width={}".format(roi_width)
        if roi_height is not None:
            commandString += ",roi_height={}".format(roi_height)

        commandString += ")"
        self.__vexec(commandString)

    def CreateMedianImage(self):
        """
        Special test function for creating median images

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CreateMedianImage()"
        self.__vexec(commandString)

    def PictureFromDisk(self, index: int = None, picture: int = None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Picture.From Disk("

        # one or the other
        if index is not None:
            commandString += "index={}".format(index)
        elif picture is not None:
            commandString += "picture={}".format(picture)

        commandString += ")"
        self.__vexec(commandString)

    def PictureFromCamera(self, index: int = None, name: str = None, next: bool = None):
        """
        Takes a picture from a camera. The camera must be connected and online.  You can specify the camera by its name or by its index

        :requires: *V-STARS 4.9.4.0 or greater*

        :param name: The name of the camera to take the picture from. It must be in the opened project.
        :param index: The index (1 to n) of the camera to take the picture from. For example, if there are 4 cameras in the project, the index values would be 1,2,3,4.  The camera indexes are determined by the order they are listed in the project (first in list = 1).
        :param next: If true the command will save and close the current picture before taking the next.

        **NOTE**: Do not specify by name and index in the same command or an error will occur.

        :examples:

        .. code:: python

            PictureFromCamera()
            #Without the name parameter, this command takes a picture from the active camera.

        .. code:: python

            PictureFromCamera(name=INCA3 sn0077 21mm 2005-10-20)
            PictureFromCamera(index=1)
            #Takes a picture from the named/first listed camera.

        **NOTE**: To close and therefore save the picture to disk, call the CloseAllPictures() command afterward. In addition, call wait(1000) to allow enough time for the image to be transmitted from the camera to V-STARS before calling CloseAllPictures()

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Picture.From Camera("
        if index is not None:
            commandString += "index={},".format(index)
        if name is not None:
            commandString += "name={},".format(name)
        if next is not None:
            commandString += "next={},".format(next)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def PicturesDisable(self, pictures: str = None):
        """
        Disables a picture or range of pictures.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param pictures: a string of code numbers who's pictures will get disabled

        :examples:

        .. code:: python

            PicturesDisable(pictures = "1 4 6 8")
            # will disable pictures 1, 4, 6 & 8.

            PicturesDisable(pictures = "7-14")
            # will disable pictures 7, 8, 9, 10, 11, 12, 13 & 14.

            PicturesDisable(pictures = "ALL")
            # will disable all pictures.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Pictures.Disable("
        if pictures is not None:
            commandString += f'pictures="{pictures}"'
        #commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)


    def PicturesEnable(self, pictures: str = None):
        """
        Enables a picture or range of pictures.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param pictures: a string of code numbers whose pictures will get enabled

        :examples:

        .. code:: python

            # will enable pictures 1, 4, 6 & 8.
            V.PicturesEnable(pictures ="1 4 6 8")

            # will enable pictures 7, 8, 9, 10, 11, 12, 13 & 14.
            V.PicturesEnable(pictures ="7-14")

            # will enable all pictures.
            V.PicturesEnable(pictures ="ALL")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Pictures.Enable("
        if pictures is not None:
            commandString += f'pictures="{pictures}"'
        #commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def PictureClose(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Picture.Close()"
        self.__vexec(commandString)

    def PictureSuperStart(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Picture.SuperStart()"
        self.__vexec(commandString)
        pointCount = self.getValue("v.pointCount")
        ellipseCount = self.getValue("v.ellipseCount")
        return pointCount, ellipseCount

    def FileOpenTemplateProject(self,
        template: str = None,
        save: str = None,
        savePrepend: bool = None,
        saveAppend: bool = None,
        prependDateTime: bool = None,
        subdir: str = None,
        ignorePrefix: str = None,
        copyScriptToProject: bool = True
        ):
        """
        Opens a V-STARS template project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param template: The name of the template project, usually in the 'C://Gsi//System//templates//projects' directory. Only the file name must be specified.
        :param save: The destination project name. Only the file name must be specified. A folder with the given name will be created in the default V-STARS project directory (usually "C:/Vstars/Projects"). If the folder already exists in the default project directory, an "_1" or "_2" etc. is appended until an unique name is made as to not overwrite an existing project.
        :param savePrepend: If true the value of save is prepended to the template name.
        :param saveAppend: If true the value of save is appended to the template name.
        :param subdir:

        :examples:

        .. code:: python

            V.FileOpenTemplateProject(template="Wing", save="Wing Meas1")
            # Will use the template project "Wing" to automatically create a project folder "Wing Meas1" in the default VSTARS project directory.

            V.FileOpenTemplateProject(template="Wing")
            # Will use the template project 'Wing' but will open a dialog so the user can select the name of the template project.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "File.Open Template Project("
        
        if template is not None:
            commandString += f'template="{template}",'
        if save is not None:
            commandString += f'save="{save}",'
        if saveAppend is not None:
            commandString += f'save append={saveAppend},'
        if savePrepend is not None:
            commandString += f'save prepend={savePrepend},'
        if prependDateTime is not None:
            commandString += f'prepend date and time={prependDateTime},'
        if subdir is not None:
            commandString += f'subdir="{subdir}",'
        if ignorePrefix is not None:
            commandString += f'ignore prefix="{ignorePrefix}",'

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        if copyScriptToProject:
            self.CopyScriptToProject()

    def FileOpen(self, filename: str = None, copyScriptToProject: bool = True):
        """
        Opens a V-STARS project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the V-STARS project to open. The file's entire path name must be given.

        :example:

        .. code:: python

            FileOpen(filename="c:/Vstars/Projects/Antenna_1")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "File.Open("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

        if copyScriptToProject:
            self.CopyScriptToProject()

    def FileClose(self):
        """
        Closes the currently open project. This function takes no parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "File.Close()"
        self.__vexec(commandString)

    def FileSaveImageAs(self, filename=None, index=-1):
        """
        Saves the currently open image or opens the image specified by index and saves

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("File.Save Image As(filename={}, index={})").format(filename, index)
        self.__vexec(commandString)

    def CopyScriptToProject(self):
        """
        Copies the current script to the project directory
        """

        try:
            projPath = self.ProjectPath()
            shutil.copy(sys.argv[0], projPath)
        except Exception as ex:
            print(str(ex))

    def GetNumberOfCameras(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "GetNumberOfCameras()"
        self.__vexec(commandsStr)
        rv = self.getValue("v.numberOfCameras")
        if rv is None:
            rv = -1
        return rv

    def MakeFakeBoardProject(self, mpictures: str = None):
        """
        Creates a fakeboard project
        Currently just for M-Projects
        Project must have an MPictures folder with pictures
        Requires a project close and re-open to take effect

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MakeFakeBoardProject("
        if mpictures is not None:
            commandString += "mpictures={},".format(mpictures)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SetFakeBoardStart(self, start=1):
        """
        Changes the starting image for a fakeboard project
        Currently just for M-Projects
        Project must be already set up as a fakeboard project
        Requires a project close and re-open to take effect

        :requires: *V-STARS 4.9.4.0 or greater*

        :param start: The number of the image Epoch to begin with

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "SetFakeBoardStart(start={})".format(start)
        self.__vexec(commandsStr)
    
    def SetFakeBoardNextEpoch(self, epoch=1):
        """
        Changes the next Epoch for a fakeboard project
        Currently just for M-Projects
        Project must be already set up as a fakeboard project

        :requires: *V-STARS 4.9.6.0 or greater*

        :param epoch: The number of the next image Epoch

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "SetFakeBoardNextEpoch(epoch={})".format(epoch)
        self.__vexec(commandsStr)

    def SetFakeBoardEpochIncrement(self, increment=1):
        """
        Changes the Epoch Increment Count for a fakeboard project
        Currently just for M-Projects
        Project must be already set up as a fakeboard project

        :requires: *V-STARS 4.9.6.0 or greater*

        :param epoch: The number of the next image Epoch

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "SetFakeBoardEpochIncrement(increment={})".format(increment)
        self.__vexec(commandsStr)

    def FreeAllCameraIOParameters(self, index=None):
        """
        Frees all camera IO parameters for a specific camera
        If index is not specified all camera parameters are freed

        :requires: *V-STARS 4.9.6.0 or greater*

        :param index: The index of the camera or None for all

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "FreeAllCameraIOParameters(index={})".format(index)
        self.__vexec(commandsStr)

    def FixCameraIOParameter(self, parameter, index=None):
        """
        Fix an IO parameter for a specific camera
        If index is not specified all cameras are affected

        :requires: *V-STARS 4.9.6.0 or greater*

        :param parameter: The index of the camera parameter to fix
        :param index: The index of the camera or None for all

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "FixCameraIOParameter(index={}, parameter={})".format(index, parameter)
        self.__vexec(commandsStr)


    def GetCameraParameters(self, on=True):
        self.__vexec("GetCameraParameters()")
        nCameras = self.returnValueManager.getValue("v.numCameras")
        params = self.returnValueManager.getValue("v.Parameters")

        return int(nCameras), params.split()

    def GetNumberOfPictures(self):
        """
        Returns a variable v.pictureCount that has the number of pictures in the project. This can be tested to see if the
        desired number of pictures were taken as shown in the example below. This command takes no parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        .. code:: python

            if( V.GetNumberOfPictures() < 12 ):
                # Do something

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetNumberOfPictures()"
        self.__vexec(commandString)
        rv = self.getValue("v.pictureCount")
        return rv

    def StopLookingForPictures(self):
        """
        Stops looking for wireless pictures. This is useful for making sure no other unintentional wireless pictures are used in the project as shown in the example below. This command takes no parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        .. code:: python

            V.StopLookingForPictures()

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "StopLookingForPictures()"
        self.__vexec(commandString)

    def UnSelectPointsAll(self):
        """
        Unselects all points in the selection buffer. This function takes no parameters. It clears the selection buffer. This is usually done before selecting points to make sure all previous unwanted selections are removed.

        :requires: *V-STARS 4.9.4.0 or greater*

        **NOTE**: Use this command to remove points from the selection buffer. Use 'DeleteSelection()' to delete points from the 3D file.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer is set to 0 by this command.

        **v.selectionNumberFound**
        The number of points unselected by the command.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "UnselectPointsAll()"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectPointsGreaterThan(
        self, filename=None, x=None, y=None, z=None, theta=None, radius=None, measured=True, design=False
    ):
        """
        Select a group of points that satisfy the value parameter.
        See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to True to select the measured points in the 3D file. If no selection type is specified as True, the measured points are used.
        :param design: Set to True to rename the design points in the 3D file.
        :param X: Of the X, Y, Z, radius parameters
        :param Y: Of the X, Y, Z, radius parameters
        :param Z: Of the X, Y, Z, radius parameters
        :param radius: Of the X, Y, Z, radius parameters
        :param theta:

        Set to a floating point value to have points greater than this value
        selected. The radius parameter is a special case that selects points
        that have (X2 + Y2) 1/2 greater than the radius value.

        **WARNING!** - Only set one of measured or design=True or
        unpredictable results can occur.

        Return Values:

        **v.selectionTotalNumberSelected**  The number of points in the
        selection buffer after the command is executed. It is set to 0
        by an UnselectPointsAll command, and when any Selection Points
        Command references a new 3D file.

        **v.selectionNumberFound**  The number of points selected by the command.

        :examples:

        .. code:: python

            # Selects all design points in the 3D file 'part1' with an X coordinate greater than 1055.5.
            V.SelectPointsGreaterThan(filename="part1", design=True, X=1055.5)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPointsGreaterThan("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        if theta is not None:
            commandString += "theta={},".format(theta)
        if radius is not None:
            commandString += "radius={},".format(radius)
        if design:
            commandString += "design=true,"
        else:
            commandString += "measured=true,"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectPointsLessThan(
        self, filename=None, x=None, y=None, z=None, theta=None, radius=None, measured=True, design=False
    ):
        """
        Select a group of points that satisfy the value parameter.
        See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to True to select the measured points in the 3D file. If no selection type is specified as True, the measured points are used.
        :param design: Set to True to rename the design points in the 3D file.
        :param X: Of the X, Y, Z, radius parameters
        :param Y: Of the X, Y, Z, radius parameters
        :param Z: Of the X, Y, Z, radius parameters
        :param radius: Of the X, Y, Z, radius parameters
        :param theta:

        Set to a floating point value to have points less than this value
        selected. The radius parameter is a special case that selects points
        that have (X2 + Y2) 1/2 greater than the radius value.

        **WARNING!** - Only set one of measured or design=True or
        unpredictable results can occur.

        Return Values:

        **v.selectionTotalNumberSelected**  The number of points in the
        selection buffer after the command is executed. It is set to 0
        by an UnselectPointsAll command, and when any Selection Points
        Command references a new 3D file.

        **v.selectionNumberFound**  The number of points selected by the command.

        :example:

        .. code:: python

            SelectPointsLessThan(filename=part1, X=1055.5)
            #Selects all measured points in the 3D file 'part1' with an X coordinate less than 1055.5.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPointsLessThan("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        if theta is not None:
            commandString += "theta={},".format(theta)
        if radius is not None:
            commandString += "radius={},".format(radius)
        if design:
            commandString += "design=true,"
        else:
            commandString += "measured=true,"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectPointsSigmaGreaterThan(
        self, filename=None, sx=None, sy=None, sz=None, total=None, measured=True, design=False
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to True to select the measured points in the 3D file. If no selection type is specified as true, the measured points are used.
        :param design: Set to true to select the design points in the 3D file.
        :param sx:
        :param sy:
        :param sz:
        :param total:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPointsSigmaGreaterThan("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if sx is not None:
            commandString += "SX={},".format(sx)
        if sy is not None:
            commandString += "SY={},".format(sx)
        if sz is not None:
            commandString += "SZ={},".format(sx)
        if total is not None:
            commandString += "total={},".format(total)
        if design:
            commandString += "design=true,"
        else:
            commandString += "measured=true,"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectPointsByLabel(
        self,
        filename: str = None,
        labels: str = None,
        measured: bool = True,
        design: bool = False,
        construction: bool = None,
        rejected: bool = None,
        accepted: bool = None,
    ):
        """
        Select a group of point for a later operation. See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param labels: A list of labels (separated by a blank space) to be selected. Labels may include wild-cards. For example labels=SCALE* will select all points that begin with the label SCALE (case does not matter). A range of points can also be specified by separating them with the ">" symbol (i.e. "TARGET1>TARGET20" would include all points with labels from TARGET1 to TARGET20 inclusive); spaces are not allowed between the > symbol and the two labels. The comparison is case insensitive.
        :param measured: Select from measured data (default)
        :param design: Select from design data
        :param construction: Only select points that were created by construction
        :param rejected: Only select points that were flagged as rejected (bundle, resection, etc.)
        :param accepted: Only select points that were NOT flagged as rejected (bundle, resection, etc.)

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer after the command is executed. It is set to 0 by an UnselectPointsAll command, and when any Selection Points Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        :example:

        .. code:: python

            SelectPointsByLabel(labels=Scale* Code*)
            #Selects all the measured points whose labels begin with 'Scale' or 'Code' from the current driver file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPointsByLabel("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if labels is not None:
            commandString += "labels={},".format(labels)
        if construction is not None:
            commandString += "construction={},".format(construction)
        if rejected is not None:
            commandString += "rejected={},".format(rejected)
        if accepted is not None:
            commandString += "accepted={},".format(accepted)

        if design:
            commandString += "design=True,"
        else:
            commandString += "measured=True,"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def Prompt(self, label, title: str = None):
        """
        Shows a dialog with a message, and an edit box for the user to enter a value.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param label:
        :param title:

        :return: The entered value

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Prompt(label={},".format(label)

        if title is not None:
            commandString += "title={},".format(title)

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        return self.getPrompt1()

    def Selection(self, title: str = None, items: str = None):
        """
        Shows a selection dialog with a list of items to select.
        The items should be a single string delimited by a semi-colon

        :requires: *V-STARS 4.9.5.0 or greater*

        :param title:
        :param items:

        :return: The selected item

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Selection("

        if title is not None:
            commandString += "title={},".format(title)
        if items is not None:
            commandString += "items={},".format(items)

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        return self.getValue("v.selection")

    def Message(self, message: str = None, title: str = None, yesno: bool = None, modeless: bool = None):
        """
        Show a message dialog in V-STARS

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message: Message to display
        :param title: Title to display in dialog box
        :param yesno: Set True to display **Yes** & **No** Button instead of the default **Ok** **Cancel** buttons
        :param modeless: Set True to make a modeless dialog

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """

        commandString = "Message("

        if message is not None:
            commandString += "message={},".format(message)
        if title is not None:
            commandString += "title={},".format(title)
        if yesno is not None:
            commandString += "yesno={},".format(yesno)
        if modeless is not None:
            commandString += "modeless={},".format(modeless)

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def Prompt2(self, label1, label2, title: str = None):
        """
        Same as prompt but with two messages to enter two values.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param label1:
        :param label2:

        If you press the Cancel button, the entered values are undefined.

        :returns: value1 and value2

        :example:

        .. code:: python

            t1, t2 = V.Prompt2("Thing 1", "Thing 2")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Prompt2(label1={}, label2={},".format(label1, label2)

        if title is not None:
            commandString += "title={},".format(title)

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        rv1 = self.getPrompt1()
        rv2 = self.getPrompt2()

        return rv1, rv2

    def getPrompt1(self):
        rv = self.getValue("v.prompt1")
        return rv

    def getPrompt2(self):
        rv = self.getValue("v.prompt2")
        return rv

    def responceNo(self):
        return self.getValue("v.no")

    def responceYes(self):
        return self.getValue("v.yes")

    def responceOk(self):
        return self.getValue("v.ok")

    def responceCancel(self):
        return self.getValue("v.cancel")

    def responseNo(self):
        return self.getValue("v.no")

    def responseYes(self):
        return self.getValue("v.yes")

    def responseOk(self):
        return self.getValue("v.ok")

    def responseCancel(self):
        return self.getValue("v.cancel")

    def Pause(self, text, yesno=False, modeless=False):
        """
        Pauses the script by showing a dialog box with a message and an 'OK ' button.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param text: The message to display
        :param yesno: Set True to show Yes No buttons instead of Ok Cancel buttons
        :param modeless: set True to create a modeless dialog

        .. code:: python

            V.Pause("press OK to continue")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ('Message(message="{}", modeless={}, title="V-Stars", yesno={})').format(text, modeless, yesno)
        self.__vexec(commandString)
        return self.responseYes()

    def Warn(self, text, yesno=True, modeless=False):
        """
        Pauses the script by showing a Warning dialog

        :requires: *V-STARS 4.9.4.0 or greater*

        :param text: The message to display
        :param yesno: Set True to show Yes No buttons instead of Ok Cancel buttons
        :param modeless: set True to create a modeless dialog

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ('Message(message="{}", modeless={}, title="V-Stars", yesno={})').format(text, modeless, yesno)
        self.__vexec(commandString)

    def XYZUpdateFeatureTargets(self, filename=""):
        """
        Updates a 3D file's feature targets.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Update.Feature Targets("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += ")"
        self.__vexec(commandString)

    def XYZDesignDelete(self, filename=""):
        """
        Deletes design data from name 3D file

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: 3D file to delete design from

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Design.Delete("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += ")"
        self.__vexec(commandString)

    def XYZUpdateFeatureTargetsSpecial(self, filename=""):
        """
        Updates a 3D file's feature targets. (A special version to support a boeing project)

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.UpdateFeatureTargetsSpecial("
        if filename is not None:
            commandString += "filename={}, ".format(filename)
        commandString += ")"
        self.__vexec(commandString)

    def XYZCopyMissingFeatureTargets(self, filename=""):
        """
        Copies into a 3D file's all feature targets. (special version to support a boeing project)

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.CopyMissingFeatureTargets("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += ")"
        self.__vexec(commandString)

    def XYZNewDataFile(self, filename=""):
        """
        Creates a new 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name for the new 3D file. If the 3D file already exists, an error message will be displayed and the script will be stopped.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.New.Data File("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += ")"
        self.__vexec(commandString)

    def XYZNewPoint(self, filename: str = None, label: str = None, x: float = None, y: float = None, z: float = None):
        """
        Creates a new point in the specified file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file in which to create a new point.  If omitted, the current driver is used.
        :param label: Point label of the new point.  If omitted, "NewPoint" is used.
        :param x: The value of the X coordinate, zero if omitted.
        :param y: The value of the Y coordinate, zero if omitted.
        :param z: The value of the Z coordinate, zero if omitted.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.New.Point("
    
        if filename is not None:
            commandString += f"filename={filename},"

        if label is not None:
            commandString += f"label={label},"

        if x is not None:
            commandString += f"x={x},"
        if y is not None:
            commandString += f"y={y},"
        if z is not None:
            commandString += f"z={z},"
    
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def Modeless(self, text, yesno=True):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param text:
        :param yesno:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """

        commandString = ('Message(message="{}", modeless=true, title="warn", yesno={})').format(text, yesno)
        self.__vexec(commandString)

    def UnSelectPointsByLabel(self, labels=""):
        """
        This command is useful for removing unwanted points from the selection buffer before pasting or deleting. For example you might have selected all 'Code' points using a wildcard. Then you can use this command to remove specific unwanted codes from the selection buffer before pasting or deleting.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param labels: A list of point labels (separated by a blank space) to be unselected. Labels may include wild-cards. For example, 'labels=SCALE*' will unselect all points that begin with the label SCALE.

        :example:

        .. code:: python

            SelectPointsByLabel(labels=Scale* Code*)
            UnSelectPointsByLabel(labels=Scale12 code101 code 201)
            PasteSelection(filename=F3, overwrite=true)
            #This will remove points 'Scale12', 'Code101', and 'Code201' from the selection buffer before they are pasted into the measured points of file F3.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer after the command is executed. It is set to 0 by an UnselectPointsAll command, and when any Selection Points Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points unselected by the command.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("UnSelectPointsByLabel(labels={})").format(labels)
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def XYZShiftTo(
        self,
        coordinate_system_name="",
        filename="",
        point="",
        line="",
        plane="",
        sphere="",
        cylinder="",
        circle="",
        picture="",
    ):
        """
        Performs a XYZ shift to the specified geometry setting the specified axis
        Only one of point, line, plane, sphere, cylinder, circle, picture can be specified


        :param coordinate_system_name: The name to give the coordinate system.

        :requires: *V-STARS 4.9.5.1 or greater*

        """
        commandString = (
            "XYZShiftTo(coordinate_system_name={},filename={}, point={}, line={}, plane={}, sphere={}, cylinder={}, circle={}, picture={})"
        ).format(coordinate_system_name, filename, point, line, plane, sphere, cylinder, circle, picture)
        self.__vexec(commandString)

    def XYZAlignTo(
        self,
        coordinate_system_name="",
        filename="",
        point="",
        line="",
        plane="",
        sphere="",
        cylinder="",
        circle="",
        picture="",
        pointing_axis="X",
    ):
        """
        Performs an Alignment to the specified geometry setting the specified axis
        Only one of point, line, plane, sphere, Cylinder, circle, picture can be specified
        the pointing_axis parameter only applies to geometry with a normal vector eg. a plane, line, cylinder, circle

        :param coordinate_system_name: The name to give the coordinate system.

        :requires: *V-STARS 4.9.5.1 or greater*

        """
        commandString = (
            "XYZAlignTo(coordinate_system_name={},filename={}, point={}, line={}, plane={}, sphere={}, cylinder={}, circle={}, picture={}, pointing_axis={})"
        ).format(coordinate_system_name, filename, point, line, plane, sphere, cylinder, circle, picture, pointing_axis)
        self.__vexec(commandString)

    def XYZClockTo(
        self,
        coordinate_system_name="",
        filename="",
        point="",
        line="",
        plane="",
        sphere="",
        cylinder="",
        circle="",
        picture="",
        toward="Y",
        about="X",
    ):
        """
        Clocks "about" an axis "toward" the specified geometry

        :param coordinate_system_name: The name to give the coordinate system.

        :requires: *V-STARS 4.9.5.1 or greater*

        """
        commandString = (
            "XYZClockTo(coordinate_system_name={},filename={}, point={}, line={}, plane={}, sphere={}, cylinder={}, circle={}, picture={}, toward={}, about={})"
        ).format(coordinate_system_name, filename, point, line, plane, sphere, cylinder, circle, picture, toward, about)
        self.__vexec(commandString)

    def XYZRotateTo(
        self,
        coordinate_system_name="",
        filename="",
        point="",
        line="",
        plane="",
        sphere="",
        cylinder="",
        circle="",
        picture="",
        toward="Y",
    ):
        """
        Rotates "toward" the specified geometry

        :param coordinate_system_name: The name to give the coordinate system.

        :requires: *V-STARS 4.9.5.1 or greater*

        """
        commandString = (
            "XYZRotateTo(coordinate_system_name={},filename={}, point={}, line={}, plane={}, sphere={}, cylinder={}, circle={}, picture={}, toward={})"
        ).format(coordinate_system_name, filename, point, line, plane, sphere, cylinder, circle, picture, toward)
        self.__vexec(commandString)

    def XYZAlignmentManual(
        self,
        filename: str = None,
        begin: bool = None,
        close: bool = None,
        shiftX: float = None,
        shiftY: float = None,
        shiftZ: float = None,
        rotationX: float = None,
        rotationY: float = None,
        rotationZ: float = None,
        scale: float = None,
        newCoordinateSystem: str = None,
        degrees: bool = True
    ):
        """
        Performs a manual alignment using the parameters
        
        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. Must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param begin: When in the parameter list, the alignment will begin automatically as if the user pressed the Begin button.
        :param close: When in the parameter list, the alignment dialog will be closed when finished as if the user pressed the Close button.
        :param shiftX:
        :param shiftY:
        :param shiftZ:
        :param rotationX:
        :param rotationY:
        :param rotationZ:
        :param scale:
        :param newCoordinateSystem:
        :param degrees: if True the rotation angles are in degrees, else they are in radians

        """
        commandString = "3D.Alignment.Manual("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if begin is not None:
            commandString += "begin={},".format(begin)
        if close is not None:
            commandString += "close={},".format(close)
        if shiftX is not None:
            commandString += "Shift X={},".format(shiftX)
        if shiftY is not None:
            commandString += "Shift Y={},".format(shiftY)
        if shiftZ is not None:
            commandString += "Shift Z={},".format(shiftZ)
        if rotationX is not None:
            commandString += "Rotation X={},".format(rotationX)
        if rotationY is not None:
            commandString += "Rotation Y={},".format(rotationY)
        if rotationZ is not None:
            commandString += "Rotation Z={},".format(rotationZ)
        if scale is not None:
            commandString += "Scale={},".format(scale)
        if newCoordinateSystem is not None:
            commandString += "new={},".format(newCoordinateSystem)

        if degrees:
            commandString += "Rotation=Degrees)"
        else:
            commandString += "Rotation=Radians)"

        self.__vexec(commandString)

    def XYZAlignmentAxis(
        self,
        filename: str = None,
        begin: bool = None,
        close: bool = None,
        anchor: str = None,
        axis: str = None,
        plane: str = None,
        newCoordinateSystem: str = None,
        timeout=None,
    ):
        """
        Performs a Axis Alignment using the parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. Must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param begin: When in the parameter list, the alignment will begin automatically as if the user pressed the Begin button.
        :param close: When in the parameter list, the alignment dialog will be closed when finished as if the user pressed the Close button.
        :param anchor: The Anchor point label and its coordinates. If no coordinate is specified, the default is 0 0 0.
        :param axis: The Axis point label and the axis the point goes thru. Axis must be one of the following: +X +Y +Z -X -Y -Z. If no Axis direction is given, the default is +X.
        :param plane: The Plane point label and the axis the plane goes thru. Axis must be one of the following: +X +Y +Z -X -Y -Z.  If no Axis direction is given the default is +Y.
        :param newCoordinateSystem:

        :examples:

        .. code:: python

            XYZAlignmentAxis(  )
            #Opens the dialog but does nothing. The user will make the settings and run the alignment

            XYZAlignmentAxis( Begin,  Anchor = CODE25 0 0 0, Axis= Code28 +X, Plane=Code30 +Y )
            #Sets CODE25 as the anchor point and sets its coordinates to be the origin (at 0,0,0); the +X axis goes thru CODE28, and the plane goes thru CODE30 in the +Y direction (as shown in the dialog above). When done, the dialog is left open so the operator can interact with the dialog, if desired

            XYZAlignmentAxis( Begin,  Close, Anchor = CODE25 0 0 0, Axis= Code28 +X, Plane=Code30 +Y )
            #Identical to the second example, except it automatically closes the dialog after the alignment so the script will proceed to the next command

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        # the matrix is only returned on 4.9.6-dev249 or greater
        if self.CheckVstarsVersion(40090060000249):
            self.matrixEvent = Event()

        commandString = "3D.Alignment.Axis("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if begin is not None:
            commandString += "begin={},".format(begin)
        if close is not None:
            commandString += "close={},".format(close)
        if anchor is not None:
            commandString += "anchor={},".format(anchor)
        if axis is not None:
            commandString += "axis={},".format(axis)
        if plane is not None:
            commandString += "plane={},".format(plane)
        if newCoordinateSystem is not None:
            commandString += "new={},".format(newCoordinateSystem)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        # the matrix is only returned on 4.9.6-dev249 or greater
        if self.CheckVstarsVersion(40090060000249):
            self.matrixEvent.wait(timeout=timeout)

            matrix = self.matrix
            self.matrixEvent = None

            if matrix is None:
                raise Exception("A timeout occurred waiting for the Alignment")
            return matrix

    def XYZAlignmentQuick(
        self,
        filename: str = None,
        begin: bool = None,
        close: bool = None,
        holdScale: bool = None,
        automaticRejection: bool = None,
        rejection: float = None,
        newCoordinateSystem: str = None,
        moreResidualsSave: str = None,
        moreTransformationSaveInfo: str = None,
        timeout=None,
        stats=None,
        hideDialog=None,
        altTrans=None
    ):
        """
        Performs a Quick Alignment using the parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. It must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param begin: When in the parameter list, the alignment will begin automatically as if the user pressed the Begin button.
        :param close: When in the parameter list, the alignment dialog will be closed when finished as if the user pressed the Close button.
        :param holdScale: When set to true, the scale of the measured values is not changed. If set to false, the scale of the measured values is allowed to change.
        :param automaticRejection: When true the rejection level is set automatically depending on the quality of the alignment.
        :param rejection: A floating point value for the rejection limit. Same as typing a value into the Rejection Edit box of the dialog.
        :param newCoordinateSystem: The name of the new coordinate system.
        :param moreResidualsSave: A filename to save point-to-point transformation residual information. Same as pressing the More button, then the Residuals tab and then the Save button. If no filename is specified, a default file name derived from the input file name will be used.
        :param moreTransformationSaveInfo: A filename to save transformation information (rotation angles and rotation matrices). Same as pressing the More button, then the Transformation tab and then the Save Info. button.
        :param altTrans: Use an alternate transformation algorithm

        :example:

        .. code:: python

            3D.Alignment.Quick(Hold Scale=true, Rejection=.01, Begin, More Residuals Save=Final results.txt )
            #Sets the Hold Scale checkbox,(the other check boxes are unknown/don't care since they are not specified), sets the Rejection limit to .01, Begins the alignment and when done saves the results in the file 'Final results.txt'.

        **Return Values:**

        **v.alignmentPrimaryPointCount**
        The number of design points in the 3D file.

        **v.alignmentSecondaryPointCount**
        The number of measured points in the 3D file.

        **v.alignmentCommonPointCount**
        The number of measured and design points with matching labels.

        **v.alignmentAcceptedPointCount**
        The number of points with residuals below the rejection limit.

        **v.alignmentRejectedPointCount**
        The number of points with residuals above the rejection limit.

        **v.alignmentIterationCount**
        The number of iterations the least squares alignment took to solve.

        **v.alignmentRejectionLimit**
        The rejection limit for the alignment.

        **v.alignmentRMSX**
        The residual X RMS after the alignment.

        **v.alignmentRMSY**
        The residual Y RMS after the alignment.

        **v.alignmentRMSZ**
        The residual Z RMS after the alignment.

        **v.alignmentRMSTotal**
        The residual XYZ total vector difference after the alignment.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        # the matrix is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.matrixEvent = Event()

        commandString = "3D.Alignment.Quick("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if begin is not None:
            commandString += "begin={},".format(begin)
        if close is not None:
            commandString += "close={},".format(close)
        if holdScale is not None:
            commandString += "hold scale={},".format(holdScale)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if newCoordinateSystem is not None:
            commandString += "new={},".format(newCoordinateSystem)
        if moreResidualsSave is not None:
            commandString += "more residuals save={},".format(moreResidualsSave)
        if moreTransformationSaveInfo is not None:
            commandString += "more transformation save info={},".format(moreTransformationSaveInfo)
        if automaticRejection is not None:
            commandString += "automatic rejection={},".format(automaticRejection)
        if hideDialog is not None:
            commandString += "hide dialog={},".format(hideDialog)
        if altTrans is not None:
            commandString += "altTrans={},".format(altTrans)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        if (stats is not None):
            stats.update(self.returnValueManager)

        # the matrix is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.matrixEvent.wait(timeout=timeout)

            matrix = self.matrix
            self.matrixEvent = None

            if matrix is None:
                raise Exception("A timeout occurred waiting for the Alignment")

            H = GTransformationMatrix()
            H.fromGMatrix(matrix)
            return H

    def XYZAlignmentSurface(
        self,
        filename: str = None,
        label: str = None,
        surfaceTolerance: float = None,
        holdScale: bool = None,
        rejection: float = None,
    ):
        """
        Performs a Surface Alignment using the parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. It must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param label: Point labels to fit
        :param surfaceTolerance: Only use a surface if it is within the tolerance
        :param holdScale: When set to true, the scale of the measured values is not changed. If set to false, the scale of the measured values is allowed to change.
        :param rejection: A floating point value for the rejection limit. Same as typing a value into the Rejection Edit box of the dialog.

        **Return Values:**

        **v.alignmentRMSTotal**
        The residual XYZ total vector difference after the alignment.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        # the matrix is only returned on 4.9.4-1 or greater
        # if self.CheckVstarsVersion(40090040010000):
        #     self.matrixEvent = Event()

        commandString = "3D.Alignment.Surface("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if label is not None:
            commandString += "label={},".format(label)
        if surfaceTolerance is not None:
            commandString += "surfaceTolerance={},".format(surfaceTolerance)
        if holdScale is not None:
            commandString += "holdScale={},".format(holdScale)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        rms = self.getValue("v.alignmentRMSTotal")
        return rms

        # the matrix is only returned on 4.9.4-1 or greater
        # if self.CheckVstarsVersion(40090040010000):
        #     self.matrixEvent.wait(timeout=timeout)

        #     matrix = self.matrix
        #     self.matrixEvent = None

        #     if matrix is None:
        #         raise Exception("A timeout occurred waiting for the Alignment")

        #     H = GTransformationMatrix()
        #     H.fromGMatrix(matrix)
        #     return H

    def XYZAlignmentStandard(
        self,
        filename: str = None,
        begin: bool = None,
        close: bool = None,
        holdScale: bool = None,
        automaticRejection: bool = None,
        rejection: float = None,
        newCoordinateSystem: str = None,
        moreResidualsSave: str = None,
        moreTransformationSaveInfo: str = None,
        timeout=None,
        stats=None,
        hideDialog=None,
        altTrans=None
    ):
        """
        Performs a Standard Alignment using the parameters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. It must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param begin: When in the parameter list, the alignment will begin automatically as if the user pressed the Begin button.
        :param close: When in the parameter list, the alignment dialog will be closed when finished as if the user pressed the Close button.
        :param holdScale: When set to true, the scale of the measured values is not changed. If set to false, the scale of the measured values is allowed to change.
        :param automaticRejection: When true the rejection level is set automatically depending on the quality of the alignment.
        :param rejection: A floating point value for the rejection limit. Same as typing a value into the Rejection Edit box of the dialog.
        :param newCoordinateSystem: The name of the new coordinate system.
        :param moreResidualsSave: A filename to save point-to-point transformation residual information. Same as pressing the More button, then the Residuals tab and then the Save button. If no filename is specified, a default file name derived from the input file name will be used.
        :param moreTransformationSaveInfo: A filename to save transformation information (rotation angles and rotation matrices). Same as pressing the More button, then the Transformation tab and then the Save Info. button.
        :param altTrans: Use an alternate transformation algorithm

        :example:

        .. code:: python

            3D.Alignment.Standard(Hold Scale=true, Rejection=.01, Begin, More Residuals Save=Final results.txt )
            #Sets the Hold Scale checkbox,(the other check boxes are unknown/don't care since they are not specified), sets the Rejection limit to .01, Begins the alignment and when done saves the results in the file 'Final results.txt'.

        **Return Values:**

        **v.alignmentPrimaryPointCount**
        The number of design points in the 3D file.

        **v.alignmentSecondaryPointCount**
        The number of measured points in the 3D file.

        **v.alignmentCommonPointCount**
        The number of measured and design points with matching labels.

        **v.alignmentAcceptedPointCount**
        The number of points with residuals below the rejection limit.

        **v.alignmentRejectedPointCount**
        The number of points with residuals above the rejection limit.

        **v.alignmentIterationCount**
        The number of iterations the least squares alignment took to solve.

        **v.alignmentRejectionLimit**
        The rejection limit for the alignment.

        **v.alignmentRMSX**
        The residual X RMS after the alignment.

        **v.alignmentRMSY**
        The residual Y RMS after the alignment.

        **v.alignmentRMSZ**
        The residual Z RMS after the alignment.

        **v.alignmentRMSTotal**
        The residual XYZ total vector difference after the alignment.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        # the matrix is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.matrixEvent = Event()

        commandString = "3D.Alignment.Standard("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if begin is not None:
            commandString += "begin={},".format(begin)
        if close is not None:
            commandString += "close={},".format(close)
        if holdScale is not None:
            commandString += "hold scale={},".format(holdScale)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if newCoordinateSystem is not None:
            commandString += "new={},".format(newCoordinateSystem)
        if moreResidualsSave is not None:
            commandString += "more residuals save={},".format(moreResidualsSave)
        if moreTransformationSaveInfo is not None:
            commandString += "more transformation save info={},".format(moreTransformationSaveInfo)
        if automaticRejection is not None:
            commandString += "automatic rejection={},".format(automaticRejection)
        if hideDialog is not None:
            commandString += "hide dialog={},".format(hideDialog)
        if altTrans is not None:
            commandString += "altTrans={},".format(altTrans)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        if (stats is not None):
            stats.update(self.returnValueManager)

        # the matrix is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.matrixEvent.wait(timeout=timeout)

            matrix = self.matrix
            self.matrixEvent = None

            if matrix is None:
                raise Exception("A timeout occurred waiting for the Alignment")

            H = GTransformationMatrix()
            H.fromGMatrix(matrix)
            return H

    def XYZAlignmentResidualsQuick(self, filename=None, save=None, rejection=-1, ok=False, newFilename=None, hideDialog=None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        Shows a list of measured to design residuals. The 'Quick' means that all design points are included in the RMS calculation.

        :param filename: The 3D file whose residuals to design values are to be shown. If this parameter is not in the parameter list, the driver file is used.
        :param save: If true, a Save Filename Dialog appears so that the user can select a filename for saving the residual information. If a filename is given, the residuals are written to this file.

        **WARNING!**  The file will be overwritten if it exists; no warning message is given.

        :param rejection: When a point's residual (X, Y or Z) is above this value it is not included as part of the RMS calculation.
        :param ok: When present, the dialog will close automatically. This is useful for making scripts that run without requiring any user interaction.
        :param newFilename:

        :example:

        .. code:: python

            XYZAlignmentResidualsQuick(save = Quick results, rejection = .01)
            #The driver file is used; a rejection limit of .01 is used, the results are saved in the current project in a file named 'Quick results.3D' and the dialog is not closed when done (so the results can be reviewed).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Alignment.Residuals - Quick(rejection={}, ok={}, ".format(rejection, ok)
        if filename is not None:
            commandString += "filename={},".format(filename)
        if save is not None:
            commandString += "save={},".format(save)
        if newFilename is not None:
            commandString += "new filename={},".format(newFilename)
        if hideDialog is not None:
            commandString += "hide dialog={},".format(hideDialog)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        
        stats = AlignmentStats()
        stats.update(self.returnValueManager)
        return stats

    def XYZAlignmentResidualsStandard(self, filename=None, save=None, rejection=-1, ok=False, newFilename=None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        Identical to XYZAlignmentResidualsQuick above but only design coordinates that are 'FIXED' are included in the RMS calculation. Coordinates which are not included in the RMS calculation are surrounded by brackets '[ ]'.

        :param filename: The 3D file whose residuals to design values are to be shown. If this parameter is not in the parameter list, the driver file is used.
        :param save: If true, a Save Filename Dialog appears so that the user can select a filename for saving the residual information. If a filename is given, the residuals are written to this file.

        **WARNING!**  The file will be overwritten if it exists; no warning message is given.

        :param rejection: When a point's residual (X, Y or Z) is above this value it is not included as part of the RMS calculation.
        :param ok: When present, the dialog will close automatically. This is useful for making scripts that run without requiring any user interaction.
        :param newFilename:

        :example:

        .. code:: python

            XYZAlignmentResidualsStandard(filename = Part1, save = true, OK)
            #The 3D file 'Part1' is used; the latest rejection limit is used, a dialog will appear so the operator can save the results in a file of his choosing (with a default filename presented that is derived from the input filename). Since OK is specified the dialog will be automatically closed when done and the next script command will be run.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Alignment.Residuals - Standard(rejection={}, ok={}".format(rejection, ok)
        if filename is not None:
            commandString += "filename={},".format(filename)
        if save is not None:
            commandString += "save={},".format(save)
        if newFilename is not None:
            commandString += "new filename={},".format(newFilename)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        stats = AlignmentStats()
        stats.update(self.returnValueManager)
        return stats

    def XYZFindCommonPointsAndRelabel(self, filename: str = None):
        """
        Find corresponding points between measured and design and label measured points accordingly. 
        A 1-1 relationship is required between the points that is every measured points should match to design.
        There is not requirement for design to have a corresponding measured point.

        :requires: *V-STARS 4.9.5.0 or greater*

        :param filename: The 3D file where the filtering is going to be applied. If this parameter is not in the parameter list, the driver file is used..

        :example:

        .. code:: python

            3D.FindCommonPointsAndRelabel(filename=Part1)

        **Return Values:**

        **v.NumberOfRelabeledPoints**
        Number of relabeled points.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.FindCommonPointsAndRelabel("
        if filename is not None:
            commandString += "filename={}".format(filename)
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.NumberOfRelabeledPoints")

    def XYZFilterMeasuredPointsUsingSurface(self, labels_wildcard: str = None, filename: str = None,  alignToSurface=False, multiplier=None, add=None):
        """
        Filter Measured points by their distance to a design surface. Median distance of all required points is initially calculated and then the filter distance is set to multiplier * median.

        :requires: *V-STARS 4.9.5.0 or greater*

        :param filename: The 3D file where the filtering is going to be applied. If this parameter is not in the parameter list, the driver file is used.
        :param labels_wildcard: Space delimited string that includes that labels that will be filtered.
        :param multiplier: The multiplier that will be used to multiply the median by to calculate the distance filter value, by default it is 3.

        :example:

        .. code:: python

            3D.FilterMeasuredPointsUsingSurface(labels: _S* TAR*, filename=Part1, multiplier=3)

        **Return Values:**

        **v.NumberOfDeletedPoints**
        Number of Deleted points.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.FilterMeasuredPointsUsingSurface(alignToSurface={},".format(alignToSurface)
        if labels_wildcard is not None:
            commandString += "labels={},".format(labels_wildcard)
        if filename is not None:
            commandString += "filename={},".format(filename)
        if multiplier is not None:
            commandString += "multiplier={},".format(multiplier)
        if (add is not None):
            commandString += "add={},".format(add)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.NumberOfDeletedPoints")

    def XYZInterpolate(
        self,
        fileName=None,
        gridFile=None,
        interpolatedPoints=None,
        scaleFactor=3.0,
        labeledEpochs=True,
        epochAgreement=None,
        insufficientDataPoints=False,
        questionableDataPoints=False,
        offsetPoints=False,
        questionableOffsetPoints=False,
        proximity=None,
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fileName:
        :param gridFile:
        :param interpolatedPoints:
        :param scaleFactor:
        :param labeledEpochs:
        :param epochAgreement:
        :param insufficientDataPoints:
        :param questionableDataPoints:
        :param offsetPoints:
        :param questionableOffsetPoints:
        :param proximity:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        if fileName is None:
            raise VError("fileName not specified in XYZInterpolate")
        if gridFile is None:
            raise VError("gridFile not specified in XYZInterpolate")

        commandString = ("3D.Interpolate(filename={}, grid file={}, scale factor={}, labeled epochs={}").format(
            fileName, gridFile, scaleFactor, labeledEpochs
        )

        if interpolatedPoints is not None:
            commandString += (", interpolated points={}").format(interpolatedPoints)
        if epochAgreement is not None:
            commandString += (", epoch agreement={}").format(epochAgreement)
        if proximity is not None:
            commandString += (", proximity={}").format(proximity)
        if insufficientDataPoints is True:
            commandString += ", insufficient data points"
        if questionableDataPoints is True:
            commandString += ", questionable data points"
        if offsetPoints is True:
            commandString += ", offset points"
        if questionableOffsetPoints is True:
            commandString += ", questionable offset points"

        commandString += ")"
        self.__vexec(commandString)

    def DeleteSelection(self, Global=False):
        """
        Deletes any points from the 3D file that were previously selected via one of the 'SelectPoints' commands (see above). This function has no parameters.
        **NOTE:**  Use this command to delete points from the 3D file. Use 'UnselectAllPoints()' to remove points from the selection buffer.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param Global:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "DeleteSelection(global={})".format(Global)
        self.__vexec(commandString)

    def ExportSelectionToExcelWriter(
        self, ipaddress=None, port=None, workbook="workbook", sheet="sheet", xyz=None, row=0, column=0
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param ipaddress:
        :param port:
        :param workbook:
        :param sheet:
        :param xyz:
        :param row:
        :param column:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ExportSelectionToExcelWriter("

        if ipaddress is not None:
            commandString += "ipaddress={}, ".format(ipaddress)

        if port is not None:
            commandString += "port={}, ".format(port)

        if xyz is not None:
            commandString += "xyz={}, ".format(xyz)

        commandString += "workbook={}, sheet={}, row={}, column={})".format(workbook, sheet, row, column)
        self.__vexec(commandString)

    def WriteStringToExcelWriter(
        self, ipaddress=None, port=None, workbook="workbook", sheet="sheet", row=0, column=0, string="string"
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param ipaddress:
        :param port:
        :param workbook:
        :param sheet:
        :param row:
        :param column:
        :param string:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "WriteStringToExcelWriter("
        if ipaddress is not None:
            commandString += "ipaddress={}, ".format(ipaddress)

        if port is not None:
            commandString += "port={}, ".format(port)

        commandString += "workbook={}, sheet={}, row={}, column={}, string={})".format(
            workbook, sheet, row, column, string
        )
        self.__vexec(commandString)

    def SystemPath(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SystemPath()"
        self.__vexec(commandString)
        path = str(self.getValue("v.systemPath"))
        path += "\\"
        return path

    def ProjectPath(self):
        """
        Returns the current project path.

        :requires: *V-STARS 4.9.4.0 or greater*

        :returns: The path of the current project.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProjectPath()"
        self.__vexec(commandString)
        path = self.getValue("v.projectPath")
        path += "\\"
        return path

    def ProjectName(self):
        """
        Gets the name of the project

        :requires: *V-STARS 4.9.4.0 or greater*

        :returns: The name of the current project.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProjectPath()"
        self.__vexec(commandString)
        path = self.getValue("v.projectPath")
        name = Path(path).stem
        return name

    def GetProjectCloudNames(self):
        """
        Gets the 3d cloud names of the project

        :requires: *V-STARS 4.9.7.1 or greater*

        :returns: The cloud names in current project.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetProjectCloudNames()"
        self.__vexec(commandString)
        clouds = self.getValue("v.projectCloudNames")

        if clouds is not None:
            cloud_names = clouds.split("|")
        else:
            cloud_names = []

        return cloud_names

    def UnSelectCirclesByLabel(self, labels=""):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param labels:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "UnSelectCirclesByLabel(labels={})".format(labels)
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def UnSelectPlanesByLabel(self, labels=""):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param labels:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "UnSelectPlanesByLabel(labels={})".format(labels)
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def UnSelectPointsGreaterThan(self, x=None, y=None, z=None, radius=None):
        """
        This command is useful for removing unwanted points from the
        selection buffer based on a coordinate value. For example, you
        might want to remove all points above or below a certain Z value.
        You can use this command to remove points from the selection
        buffer before pasting or deleting.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param x: Of the X, Y, Z, radius parameters.
        :param y: Of the X, Y, Z, radius parameters.
        :param z: Of the X, Y, Z, radius parameters.
        :param radius: Of the X, Y, Z, radius parameters.

        Set to a floating point value to have points greater than this value
        unselected. The radius parameter is a special case that selects points
        that have (X2 + Y2) 1/2 greater than the radius value.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer after the command is
        executed. It is set to 0 by an UnselectPointsAll command, and when
        any Selection Points Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        :example:

        .. code:: python

            UnSelectPointsGreaterThan(Z=100)
            #Unselects all measured points in the selection buffer with a Z coordinate greater than 100.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "UnSelectPointsGreaterThan("
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        if radius is not None:
            commandString += "radius={}".format(radius)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def UnSelectPointsLessThan(self, x=None, y=None, z=None, radius=None):
        """
        This command is useful for removing unwanted points from the
        selection buffer based on a coordinate value. For example, you
        might want to remove all points above or below a certain Z value.
        You can use this command to remove points from the selection
        buffer before pasting or deleting.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param x: Of the X, Y, Z, radius parameters.
        :param y: Of the X, Y, Z, radius parameters.
        :param z: Of the X, Y, Z, radius parameters.
        :param radius: Of the X, Y, Z, radius parameters.

        Set to a floating point value to have points less than this value
        unselected. The radius parameter is a special case that selects points
        that have (X2 + Y2) 1/2 greater than the radius value.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer after the command is
        executed. It is set to 0 by an UnselectPointsAll command, and when
        any Selection Points Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        :example:

        .. code:: python

            UnSelectPointsLessThan(z=100)
            #Unselects all measured points in the selection buffer with a Z coordinate less than 100.


        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "UnselectPointsLessThan("
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        if radius is not None:
            commandString += "radius={},".format(radius)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def GetClosestPoint(self, fromPoint: str = None):
        """
        Using the current set of selected points, this command returns a variable with the label for the point that is closest to the specified point.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fromPoint: The label of the point to use.

        :return: A string containing the label of the closest point to the "from" point.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetClosestPoint("
        
        if fromPoint is not None:
            commandString += f"from={fromPoint}"

        #commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        closestPoint = self.getValue("v.closestPoint")

        return closestPoint

    def GetFurthestPoint(self, fromPoint: str = None):
        """
        Using the current set of selected points, this command returns a variable with the label for the point that is furthest from the specified point.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fromPoint: The label of the point to use.

        :return: A string containing the label of the furthest point to the "from" point.

        :example:

        .. code:: python

            V = VSTARS()
            V.GetFurthestPoint(from = "Code193")
            if (V.getValue("v.furthestPoint") == "ZRO_1" ):

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetFurthestPoint("
        
        if fromPoint is not None:
            commandString += f"from={fromPoint}"

        #commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        return self.getValue("v.furthestPoint")

    def RelabelAutomatch(self, prefix, filename: str = None):
        """

        Relabels automatched points

        :requires: *V-STARS 4.9.4.0 or greater*

        :param prefix: The prefix for the relabelled points. Case insensitive but the points will be labeled in uppercase.
        :param filename: The 3D File to relabel

        :examples:

        .. code:: python

            RelabelAutomatch(filename="Driver", prefix="_S")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "RelabelAutomatch(prefix={}".format(prefix)

        if filename is not None:
            commandString += ",filename={}".format(filename)
        
        # commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def RelabelPoint(self, oldLabel: str, newLabel: str, filename: str = None):
        """
        Relabels the named point. The new label should not already exists in the 3D file.
        If filename is omitted, the driver and the pictures are relabeled

        :requires: *V-STARS 4.9.5.0 or greater*

        :param old_label: The point's old label
        :param new_label: The point's new label
        :param filename: The 3D File to relabel

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = f"RelabelPoint(old_label={oldLabel}, new_label={newLabel}"

        if filename is not None:
            commandString += f",filename={filename}"
        
        commandString += ")"

        self.__vexec(commandString)

    def RelabelSelectedPoints(self, prefix: str = None):
        """

        Relabels the points that have been selected using the specified prefix.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param prefix: The prefix for the relabelled points. Case insensitive but the points will be labeled in uppercase.

        Return Values:

        **v.RelabelPoints**
        The number of points that were relabelled.

        :examples:

        .. code:: python

            SelectPointsLessThan(z=1.)
            RelabelSelectedPoints( prefix="Floor_")
            SelectPointsGreaterThan(z=100.)
            RelabelSelectedPoints( prefix="Ceiling_")
            #Points on the floor will be labeled FLOOR_1,2,3, etc. while points on the ceiling will be labeled CEILING_1,2,3, etc.


        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "RelabelSelectedPoints("
        
        if prefix is not None:
            commandString += "prefix={}".format(prefix)

        #commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def AddToSelectedPoints(self, x: float = None, y: float = None, z: float = None):
        """
        :requires: *V-STARS 4.9.6.0 or greater*

        Adds to the selected points by the value specified.

        :param x: the value of x
        :param y: the value of y
        :param z: the value of z

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "AddToSelectedPoints("
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def MultiplySelectedPointsBy(self, x: float = None, y: float = None, z: float = None):
        """
        :requires: *V-STARS 4.9.6.0 or greater*

        Multiplies the selected points by the value specified.

        :param x: the value of x
        :param y: the value of y
        :param z: the value of z

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "MultiplySelectedPointsBy("
        if x is not None:
            commandString += "X={},".format(x)
        if y is not None:
            commandString += "Y={},".format(y)
        if z is not None:
            commandString += "Z={},".format(z)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def GetPointVector(self, label: str = None):
        """
        :requires: *V-STARS 4.9.4.0 or greater*

        Gets a point's approximate normal vector based on the cameras that view it. The point must exist in the current driver file.

        :param label: The label of the point to use.

        Return Values:

        **v.pointi**

        **v.pointj**

        **v.pointk**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetPointVector("
        
        if label is not None:
            commandString += "label={}".format(label)

        # commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        return self.getValue("v.pointi"), self.getValue("v.pointj"), self.getValue("v.pointk")

    def RelabelByAngle(
        self,
        prefix: str = None,
        angleTolerance: float = None,
        expectedCount: int = None,
        relabelCodes: bool = None,
        numberingNominalDegrees: bool = None,
        numberingSequential0: bool = None,
        numberingSequential1: bool = None,
        numberingActualDegrees: bool = None,
    ):
        """
        Sorts the currently selected points by angle (as defined by a cylindrical coordinate system) and relabels these points
        in ascending order as controlled by the parameters.
        The points are expected to be laid out with a common angle spacing within the supplied tolerance. The nominal
        spacing is determined by the median angle separation (if an even number of points) or by the average of the middle
        3 points of the sorted angles if an odd number of points.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param prefix: The label prefix for the sorted points as in **H_**. The default for this parameter is **A_**
        :param angleTolerance: The angle tolerance in degrees. To be accepted for relabeling, a point must be the "common angle spacing" +/- this tolerance from at least one adjacent neighbor.
        :param relabelCodes: If True, codes and their nuggets (if selected) are relabeled. The default is False.

        **NOTE:** Only one of the following parameters can be present. If none of these is present, the default is numberingNominalDegrees

        :param numberingSequential0: points will be labeled starting form 0, for example H_0, H_1 etc.
        :param numberingSequential1: points will be labeled starting form 1, for example H_1, H_2 etc.
        :param numberingActualDegrees: points will be labeled based on their actual degree (rounded to nearest integer), for example H_2, H_44, H_91
        :param numberingNominalDegrees: points will be labeled based on their nominal degree in increments of the common angle spacing (rounded to nearest integer), for example H_0, H_45, H_90 etc.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "RelabelByAngle("

        if prefix is not None:
            commandString += "prefix={},".format(prefix)

        if angleTolerance is not None:
            commandString += "angle tolerance={},".format(angleTolerance)

        if relabelCodes is not None:
            commandString += "relabelCodes={},".format(relabelCodes)

        if expectedCount is not None:
            commandString += "expectedCount={},".format(expectedCount)

        if numberingNominalDegrees is not None:
            commandString += "numbering nominal degrees={},".format(numberingNominalDegrees)

        if numberingSequential0 is not None:
            commandString += "numbering sequential0={},".format(numberingSequential0)

        if numberingSequential1 is not None:
            commandString += "numbering sequential1={},".format(numberingSequential1)

        if numberingActualDegrees is not None:
            commandString += "numbering actual degrees={},".format(numberingActualDegrees)

        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

        return self.getValue("v.relabelCount")

    def RelabelPairsByAngle(
        self,
        expectedPairs: int = None,
        innerPrefix: str = None,
        outerPrefix: str = None,
        angleTolerance: float = None,
        radiusDifference: float = None,
        radiusTolerance: float = None,
        warningTolerance: float = None,
        middlePrefix: str = None,
        middleTolerance: float = None,
    ):
        """
        Relabels Inner and Outer flange point pairs in order of their angle angle (as defined by a cylindrical coordinate system) and relabels these points in ascending order as controlled by the parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param innerPrefix: The label prefix for the Inner flange points.
        :param outerPrefix: The label prefix for Outer flange points.
        :param radiusDifference: The radius difference of the Outer and Inner flange points.
        :param radiusTolerance: The target pair must be separated by the radius difference above, within this tolerance.
        :param angleTolerance: The point pairs are targeted on the flange at the same angle spacing within this tolerance.
        :param expectedPairs: This is an optional parameter that specifies the expected number of pairs. The angle spacing between pairs is determined from this. If this parameter is not given, the angle spacing is automatically determined.
        :param warningTolerance: Similar to radius tolerance, however points above this tolerance (but below the radius tolerance) are counted as being marginal. This may be an indication that more care should be taken when targeting. The labels of these marginal points are returned in the parameter v.matchingPairsOutOfTolerance.
        :param middlePrefix: The label prefix for Middle flange points. The default value is **M_**.
        :param middleTolerance: When present, middle points are also identified. The middle point is expected halfway between the inner and outer points. Only a point within this tolerance is considered.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        :return matchingPairsCount, matchingPairsOrphanCount, matchingPairsOutOfTolerance: as a triplet of return values

        """
        commandString = "RelabelPairsByAngle("

        if expectedPairs is not None:
            commandString += "expected pairs={},".format(expectedPairs)

        if innerPrefix is not None:
            commandString += "inner prefix={},".format(innerPrefix)

        if outerPrefix is not None:
            commandString += "outer prefix={},".format(outerPrefix)

        if angleTolerance is not None:
            commandString += "angle tolerance={},".format(angleTolerance)

        if radiusDifference is not None:
            commandString += "radius difference={},".format(radiusDifference)

        if radiusTolerance is not None:
            commandString += "radius tolerance={},".format(radiusTolerance)

        if warningTolerance is not None:
            commandString += "warning tolerance={},".format(warningTolerance)

        if middlePrefix is not None:
            commandString += "middle prefix={},".format(middlePrefix)

        if middleTolerance is not None:
            commandString += "middle tolerance={},".format(middleTolerance)

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        r1 = self.getValue("v.matchingPairsCount")
        r2 = self.getValue("v.matchingPairsOrphanCount")
        r3 = self.getValue("v.matchingPairsOutOfTolerance")

        return r1, r2, r3


    def GraphicalViewSetup(
        self,
        colors: str = None,
        tolerances: str = None,
        filename: str = None,
        labelScale: float = None,
        highlight: bool = None,
        highlightStr: str = None,
        hideObjects: bool = None,
        hideObjectsStr: str = None,
        viewPoints: bool = None,
        viewPlanes: bool = None,
        viewLines: bool = None,
        viewCircles: bool = None,
        viewSpheres: bool = None,
        viewCylinders: bool = None,
        viewCurves: bool = None,
        viewSurface: bool = None,
        viewDesignPoints: bool = None,
        viewDesignPlanes: bool = None,
        viewDesignLines: bool = None,
        viewDesignCircles: bool = None,
        viewDesignSpheres: bool = None,
        viewDesignCylinders: bool = None,
        viewDesignCurves: bool = None,
        viewDesignSurface: bool = None,
        viewProbePoints: bool = None,
        viewResiduals: bool = None,
        viewResidualLabels: int = None,
        viewMeasurements: bool = None,
        viewDesignResiduals: bool = None,
        viewDx: bool = None,
        viewDy: bool = None,
        viewDz: bool = None,
        ViewDTotal: bool = None,
        viewLabels: bool = None,
    ):
        """
        Sets values for the 3D graphical view.

        :requires: *V-STARS 4.9.6.0 or greater*

        :param colors: Nine hexadecimal space separated RGB color values.
        :param tolerances: Nine space separated tolerance values.
        :param filename:
        :param labelScale:
        :param highlight:
        :param highlightStr:
        :param hideObjects:
        :param hideObjectsStr:
        :param viewPoints:
        :param viewPlanes:
        :param viewLines:
        :param viewCircles:
        :param viewSpheres:
        :param viewCylinders:
        :param viewCurves:
        :param viewSurface:
        :param viewDesignPoints:
        :param viewDesignPlanes:
        :param viewDesignLines:
        :param viewDesignCircles:
        :param viewDesignSpheres:
        :param viewDesignCylinders:
        :param viewDesignCurves:
        :param viewDesignSurface:
        :param viewProbePoints:
        :param viewResiduals: View the point to object residuals.
        :param viewResidualLabels: 0 => No labels, 1 => Label, 2 => Value, 3 => Both
        :param viewMeasurements: View the point to object measurements.
        :param viewDesignResiduals: View the point to design point differences.
        :param viewDx: View the difference in X.
        :param viewDy: View the difference in Y.
        :param viewDz: View the difference in Z.
        :param ViewDTotal: View the total difference.
        :param viewLabels: View the point labels.

        :examples:

        .. code:: python

            # set the view tolerances and colors (red red red green green green blue blue blue)
            V.GraphicalViewSetup(tolerances="-0.028 -0.021 -0.014 -0.007 0.000 0.007 0.014 0.021 0.028")
            V.GraphicalViewSetup(colors=ff0000 ff0000 ff0000 00ff00 00ff00 00ff00 0000ff 0000ff 0000ff)

            # display the point labels, hide the total vectors and display the delta x values
            V.GraphicalViewSetup(viewLabels = True, viewDTotal=False, viewDx= True)

            # Hide the point labels and display the total vectors
            V.GraphicalViewSetup(viewLabels=False, viewDTotal=True)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GraphicalViewSetup("
        if colors is not None:
            commandString += "colors={},".format(colors)
        if tolerances is not None:
            commandString += "tolerances={},".format(tolerances)
        if filename is not None:
            commandString += "filename={},".format(filename)
        if labelScale is not None:
            commandString += "label scale={},".format(labelScale)
        if highlight is not None:
            commandString += "view highlight points={},".format(highlight)
        if highlightStr is not None:
            commandString += "highlight points={},".format(highlightStr)
        if hideObjects is not None:
            commandString += "hide objects={},".format(hideObjects)
        if hideObjectsStr is not None:
            commandString += "hide objects string={},".format(hideObjectsStr)
        if viewPoints is not None:
            commandString += "view points={},".format(viewPoints)
        if viewPlanes is not None:
            commandString += "view planes={},".format(viewPlanes)
        if viewLines is not None:
            commandString += "view lines={},".format(viewLines)
        if viewCircles is not None:
            commandString += "view circles={},".format(viewCircles)
        if viewSpheres is not None:
            commandString += "view spheres={},".format(viewSpheres)
        if viewCylinders is not None:
            commandString += "view cylinders={},".format(viewCylinders)
        if viewCurves is not None:
            commandString += "view curves={},".format(viewCurves)
        if viewSurface is not None:
            commandString += "view surfaces={},".format(viewSurface)
        if viewDesignPoints is not None:
            commandString += "view design points={},".format(viewDesignPoints)
        if viewDesignPlanes is not None:
            commandString += "view design planes={},".format(viewDesignPlanes)
        if viewDesignLines is not None:
            commandString += "view design lines={},".format(viewDesignLines)
        if viewDesignCircles is not None:
            commandString += "view design circles={},".format(viewDesignCircles)
        if viewDesignSpheres is not None:
            commandString += "view design spheres={},".format(viewDesignSpheres)
        if viewDesignCylinders is not None:
            commandString += "view design cylinders={},".format(viewDesignCylinders)
        if viewDesignCurves is not None:
            commandString += "view design curves={},".format(viewDesignCurves)
        if viewDesignSurface is not None:
            commandString += "view design surfaces={},".format(viewDesignSurface)
        if viewProbePoints is not None:
            commandString += "view probe points={},".format(viewProbePoints)
        if viewResiduals is not None:
            commandString += "view residuals={},".format(viewResiduals)
        if viewResidualLabels is not None:
            commandString += "view residual labels={},".format(viewResidualLabels)
        if viewMeasurements is not None:
            commandString += "view measurements={},".format(viewMeasurements)
        if viewDesignResiduals is not None:
            commandString += "view design residuals={},".format(viewDesignResiduals)
        if viewDx is not None:
            commandString += "view dx={},".format(viewDx)
        if viewDy is not None:
            commandString += "view dy={},".format(viewDy)
        if viewDz is not None:
            commandString += "view dz={},".format(viewDz)
        if ViewDTotal is not None:
            commandString += "view dtotal={},".format(ViewDTotal)
        if viewLabels is not None:
            commandString += "view labels={},".format(viewLabels)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SetSelectedPointsSigma(self, all=None, x=None, y=None, z=None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param all:
        :param x:
        :param y:
        :param z:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "SetSelectedPointsSigma("
        if all is not None:
            commandStr += "all={},".format(all)
        if x is not None:
            commandStr += "X={},".format(x)
        if y is not None:
            commandStr += "Y={},".format(y)
        if z is not None:
            commandStr += "Z={},".format(z)
        commandStr = commandStr.rstrip(",")
        commandStr += ")"
        self.__vexec(commandStr)

    def SetSelectedPointsDescription(self, description):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param all:
        :param x:
        :param y:
        :param z:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "SetSelectedPointsDescription(description={})".format(description)
        self.__vexec(commandStr)

    def CodedTargetSetup(self,
        codes: str = None,
        enable: bool = None,
        disable: bool = None,
        targetNuggets: bool = None
     ):
        """
        Configures the coded targets for the current project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param codes: If "ALL" then this command will apply to all codes otherwise specific codes must be specified and space separated.  A dash can be used to indicate a range of codes (ex., "45-67 34-45 21 22").
        :param enable: If False, enables all specified codes.  Cannot be used with disabled.
        :param disable: If True, disables all specified codes.  Cannot be used with enabled.
        :param targetNuggets: If True, sets the Target Nuggets flag which will cause the software to triangulate the code nugget points.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CodedTargetSetup("
        if codes is not None:
            # sanitize with codes string by replacing commas with spaces
            codes = codes.replace(",", " ")
            commandString += f"codes={codes},"

        if enable is not None:
            commandString += f"enable={enable},"

        if disable is not None:
            commandString += f"disable={disable},"

        if targetNuggets is not None:
            commandString += f"target nuggets={targetNuggets},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SetCodeType(
        self,
        codes: str,
        codeType: int
    ):
        """
        Set the type for a coded target's or range of coded targets' nuggets.

        :requires: *V-STARS 4.9.6.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        :param codes: A space separated string of code numbers whose nuggets will get enabled.
        :param type: Enum setting for the code type.
        
        V.SetCodeType(codes: "1 4 6 8", type: "back to back") 
        // will set nuggets for CODE1, CODE4, CODE6 & CODE8 to back to back.
        
        V.SetCodeType(codes: "7-11", type: "spinner") 
        // will set CODE7, CODE8, CODE9, CODE10 & CODE11 nuggets to spinner.
        
        V.SetCodeType(codes: "all", type: "normal") 
        // will set all codes to normal.
        """
        typeStr = "normal"

        # sanitize with codes string by replacing commas with spaces
        codes = codes.replace(",", " ")

        if codeType == 1:
            typeStr = "back to back"
        elif codeType == 2:
            typeStr = "spinner"

        self.__vexec(f"SetCodeType(codes={codes}, type={typeStr})")


    def SelectCirclesAll(self, filename=None, measured=True, design=False):
        """
        Select a group of circle for a later operation. See DeleteSelection or PasteSelection.

        :requires: V-STARS 4.9.4.0 or greater
        :param filename: The 3D file from which the circles are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to True to select the measured circles in the 3D file. If no selection type is specified as true, the measured circles are used.
        :param design: Set to True to select the design circles in the 3D file.

        **WARNING!** - Only set one of measured or design=true or unpredictable results can occur.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of circles in the selection buffer after the command is executed. It is set to 0 by an UnselectCirclesAll command, and when any Selection Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        :example:

        .. code:: python

            V.SelectCirclesAll(filename=bundle, design=true)
            #This will select all the design circles from the 3D file named bundle.

        :raises: Exception see Error Handling for details

        """
        commandString = "SelectCirclesAll("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += "measured={}, design={})".format(measured, design)
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectPlanesAll(self, filename=None, measured=True, design=False):
        """

        Select a group of planes for a later operation. See 'DeleteSelection' or 'PasteSelection'.

        :requires: V-STARS 4.9.4.0 or greater

        :param filename: The 3D file from which the planes are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to true to select the measured planes in the 3D file. If no selection type is specified as true, the measured planes are used.
        :param design: Set the true to select the design planes in the 3D file.

        **WARNING!** - Only set one of measured or design=true or unpredictable results can occur.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of planes in the selection buffer after the command is executed. It is set to 0 by an UnselectPlanesAll command, and when any Selection Command references a new 3D file.

        **v.selectionNumberFound**
        The number of planes selected by the command.

        :example:

        .. code:: python

            SelectCirclesAll(filename=bundle, design=true)
            #This will select all the design planes from the 3D file named 'bundle'.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPlanesAll("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += "measured={}, design={})".format(measured, design)
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SortSelectedPoints(self, theta=False):
        """

        :requires: V-STARS 4.9.4.0 or greater

        :param theta:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("SortSelectedPoints(theta={})").format(theta)
        self.__vexec(commandString)

    def MModeTrigger(self):
        """
        Fires an M-Mode trigger just the same as pressing the 'T' button in V-STARS. You must be in M-Mode for this to work. This command has no parameters

        :requires: V-STARS 4.9.4.0 or greater

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.Trigger()"
        self.__vexec(commandString)

    def MModeTriggerEx(self, projectorMarker=False, projectorMarkerAutoExposure=False):
        """
        Fires an M-Mode trigger just the same as pressing the 'T' button in V-STARS. You must be in M-Mode for this to work.

        :requires: V-STARS 4.9.4.0 or greater

        :param projectorMarker: Takes and scans the picture, looking for specific projector marker targets
        :param projectorMarkerAutoExposure: Adjusts the camera exposure based on the scanned targets

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.Trigger(projector marker={}, projector marker exposure={})".format(
            projectorMarker, projectorMarkerAutoExposure
        )
        self.__vexec(commandString)

    def ExportScanSettings(self):
        """

        :requires: V-STARS 4.9.4.0 or greater

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ExportScanSettings()"
        self.__vexec(commandString)

    def MModeBeginSendingData(
        self, driver=False, probe=False, triangulation=False, camera=False, station=False, dream=False
    ):
        """

        :requires: V-STARS 4.9.4.0 or greater

        :param driver:
        :param probe:
        :param triangulation:
        :param camera:
        :param station:
        :param dream:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = (
            "MModeBeginSendingData(driver={}, probe={}, triangulation={}, camera={}, station={}, dream={})"
        ).format(driver, probe, triangulation, camera, station, dream)
        self.__vexec(commandString)

    def MModeEndSendingData(self):
        """

        :requires: V-STARS 4.9.4.0 or greater

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MModeEndSendingData()"
        self.__vexec(commandString)

    def MModeSetContinuousTriggerMode(self, state=True):
        """
        Toggles MMode continuous trigger mode on / off

        :requires: V-STARS 4.9.4.0 or greater

        :param state: Sets the state of continuous trigger mode, True for on and False for off

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        self.__vexec("MModeSetContinuousTriggerMode(state={})".format(state))

    def MModeGetContinuousTriggerMode(self):
        """
        Returns the current state of the MMode continuous trigger

        :requires: V-STARS 4.9.4.0 or greater

        Return values:

        **v.ContinuousTriggerMode**
        The state of the m mode continuous trigger

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        self.__vexec("MModeGetContinuousTriggerMode()")
        return self.getValue("v.ContinuousTriggerMode")

    def MModeOn(
        self,
        on: bool = None,
        testing: bool = None
    ):
        """

        Toggles MMode on / off just like the menu command.

        :requires: V-STARS 4.9.4.0 or greater

        :param on: Set on = true to turn MMode on, on = false to turn MMode off.
        :param testing: Set testing mode on or off

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.On("
        if on is not None:
            commandString += f"on={on},"
        if testing  is not None:
            commandString += f"testing={testing},"
        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def MModeQuickCameraOrientation(self, begin=True, cont=False, quickFourStation=True, useCurrentDriver=True, saveImages=True, accept=False,  showWarnings = False):
        """

        :requires: V-STARS 4.9.4.0 or greater

        :param begin:
        :param cont:
        :param quickFourStation:
        :param useCurrentDriver:
        :param saveImages:
        :param accept:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = (
            "MMode.Quick Camera Orientation(Begin={}, Continue={}, Quick Four Station={}, Use Current Driver={}, Save Images={}, Accept={}, showWarnings={})"
        ).format(begin, cont, quickFourStation, useCurrentDriver, saveImages, accept, showWarnings)
        self.__vexec(commandString)

    def MModeProbeDuplicatePointCheck(self, enable=True, threshold=None):
        """
        Enables MMode Duplicate Probe Point check

        :requires: V-STARS 4.9.7.22 or greater

        :param enable: Boolean value that enables or Disables the check
        :param threshold: The threshold closeness value for a point to be considered duplicate in project units

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MModeProbeDuplicatePointCheck("
        if enable is not None:
            commandString += "enable={},".format(enable)
        if threshold is not None:
            commandString += "threshold={},".format(threshold)

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def MModeOnlineConstructionSuperSampling(self, enable=True, required_num_samples=None, max_num_samples=None, rms_threshold=None):
        """
        Enables MMode Online Geometry - Super sampling

        :requires: V-STARS 4.9.7.22 or greater

        :param enable: Boolean value that enables or Disables the check
        :param required_num_samples: The required number of samples required to be collected
        :param max_num_samples: The max number of samples to be collected before considering the measurement a failure
        :param rms_threshold: The rms threshold value for a measurement to be accepted

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MModeOnlineConstructionSuperSampling("
        if enable is not None:
            commandString += "enable={},".format(enable)
        if required_num_samples is not None:
            commandString += "required samples={},".format(required_num_samples)
        if max_num_samples is not None:
            commandString += "max samples={},".format(max_num_samples)
        if rms_threshold is not None:
            commandString += "rms threshold={},".format(rms_threshold)
        
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def ExportSelection(self, filename=None, type="csv", save=True):
        """
        Exports the selected points to a file of the specified type. Points selected by one of the 'SelectPoints' commands (see
        above) are exported to the named file.

        :requires: V-STARS 4.9.4.0 or greater

        :param filename: The name of the exported file. If not present, the filename of the 3D file used for the current selection(s) is used.
        :param type: The type of file to export. The filename will be given this three-letter extension (csv = comma separated variable file, tab = tabbed file, txt = ASCII text file).
        :param save: If not True, a Save File dialog is displayed with the specified export file name. The operator can then change the name or location if desired. If present, the file is automatically saved and no dialog box is displayed.

        :examples:

        .. code:: python

            V.UnselectPointsAll()

            V.SelectPointsByLabel(filename="Bundle3", labels="I* CODE*")

            V.ExportSelection(type="csv")
            # The exported file is a .csv file and it gets the same file name as the current
            # driver and is saved in the current project. The Save As dialog will be displayed so the operator can change the file name or location if desired

            V.ExportSelection(filename="Bundle3", type="txt", save=True)
            # Exports the Bundle3.3D file's points as a .txt file called "Final Results.txt".
            # It is saved automatically (no dialog appears)

        :raises: Exception see Error Handling for details

        """
        commandString = "ExportSelection("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += "type={}, save={})".format(type, save)
        self.__vexec(commandString)

    def XYZExport3D(self, filename=None, saveAs=None, overwrite=True):
        """
        Function to export an existing 3D file, to 3D file format on disk.

        :requires: V-STARS 4.9.4.0 or greater

        :param filename: The name of the source file.
        :param saveAs: The name of the destination file.
        :param overwrite: True will overwrite the destination file if it already exists.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Export.3D("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if saveAs is not None:
            commandString += "save as={},".format(saveAs)
        if overwrite is not None:
            commandString += "overwrite={},".format(overwrite)
        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def XYZExportReport(self,
        filename: str = None, ok: bool = None, save: bool = None, saveAs: str = None, units: str = None,
        measuredData: bool = None, designData: bool = None, measurements: bool = None, pointsLayout: bool = None,
        points: bool = None, planes: bool = None, lines: bool = None, circles: bool = None, spheres: bool = None, cylinders: bool = None, curves: bool = None, surfaces: bool = None,
        designPoints: bool = None, designPlanes: bool = None, designLines: bool = None, designCircles: bool = None, designSpheres: bool = None, designCylinders: bool = None, designCurves: bool = None, designSurfaces: bool = None,
        columnHeadings: bool = None, label: bool = None, xyz: bool = None, sigma: bool = None, offset: bool = None, description: bool = None,
        tab: bool = None, space: bool = None,
        designResiduals: bool = None,
        pointPoint: bool = None, pointPlane: bool = None, pointLine: bool = None, pointCircle: bool = None, pointSphere: bool = None, pointCylinder: bool = None, pointCurve: bool = None, pointSurface: bool = None,
        planePlane: bool = None, planeLine: bool = None, lineLine: bool = None,
        probePoints: bool = None,
        compactFormat: bool = None,
        headerDefault: bool = None, headerNone: bool = None, headerCompact: bool = None, headerCustom: str = None, headerLine1: str = None, headerLine2: str = None,
        default: bool = None, none: bool = None, compact: bool = None, custom: str = None, line1: str = None, line2: str = None
    ):
        """
        Export a 3D file to a report text file.

        :requires: V-STARS 4.9.8.0 or greater

        :param filename: (str, optional): The data file to export, driver file if. Defaults to None.
        :param ok: (bool, optional): Close the report setup dialog automatically. Defaults to None.
        :param save: (bool, optional): Close the file save dialog automatically. Defaults to None.
        :param saveAs: (str, optional): The name of the report file. Use the data file name with a txt extension if omitted. Defaults to None.
        :param units: (str, optional): Export file units. Project units if None. Defaults to None.
        :param measuredData: (bool, optional): Export all measured data. Defaults to None.
        :param designData: (bool, optional): Export all design data. Defaults to None.
        :param measurements: (bool, optional): Export all point to object measurements. Defaults to None.
        :param pointsLayout: (bool, optional): Export all point details. Defaults to None.
        :param points: (bool, optional): Export points. Defaults to None.
        :param planes: (bool, optional): Export planes. Defaults to None.
        :param lines: (bool, optional): Export lines. Defaults to None.
        :param circles: (bool, optional): Export circles. Defaults to None.
        :param spheres: (bool, optional): Export spheres. Defaults to None.
        :param cylinders: (bool, optional): Export cylinders. Defaults to None.
        :param curves: (bool, optional): Export curves. Defaults to None.
        :param surfaces: (bool, optional): Export surfaces. Defaults to None.
        :param designPoints: (bool, optional): Export design points. Defaults to None.
        :param designPlanes: (bool, optional): Export design planes. Defaults to None.
        :param designLines: (bool, optional): Export design lines. Defaults to None.
        :param designCircles: (bool, optional): Export design circles. Defaults to None.
        :param designSpheres: (bool, optional): Export design spheres. Defaults to None.
        :param designCylinders: (bool, optional): Export design cylinders. Defaults to None.
        :param designCurves: (bool, optional): Export design curves. Defaults to None.
        :param designSurfaces: (bool, optional): Export design surfaces. Defaults to None.
        :param columnHeadings: (bool, optional): Point column headings. Defaults to None.
        :param label: (bool, optional): Point labels. Defaults to None.
        :param xyz: (bool, optional): Point XYZ. Defaults to None.
        :param sigma: (bool, optional): Point sigmas. Defaults to None.
        :param offset: (bool, optional): Point offset. Defaults to None.
        :param description: (bool, optional): Point description. Defaults to None.
        :param tab: (bool, optional): Tab delimited. Defaults to None.
        :param space: (bool, optional): Space delimited. Space wins if both tab and space are set. Defaults to None.
        :param designResiduals: (bool, optional): Export measured to design point residuals. Defaults to None.
        :param pointPoint: (bool, optional): Export point to point measurements. Defaults to None.
        :param pointPlane: (bool, optional): Export point to plane measurements. Defaults to None.
        :param pointLine: (bool, optional): Export point to line measurements. Defaults to None.
        :param pointCircle: (bool, optional): Export point to circle measurements. Defaults to None.
        :param pointSphere: (bool, optional): Export point to sphere measurements. Defaults to None.
        :param pointCylinder: (bool, optional): Export point to cylinder measurements. Defaults to None.
        :param pointCurve: (bool, optional): Export point to curve measurements. Defaults to None.
        :param pointSurface: (bool, optional): Export point to surface measurements. Defaults to None.
        :param planePlane: (bool, optional): Export plane to plane measurements. Defaults to None.
        :param planeLine: (bool, optional): Export plane to line measurements. Defaults to None.
        :param lineLine: (bool, optional): Export line to line measurements. Defaults to None.
        :param probePoints: (bool, optional): Export probe points. Defaults to None.
        :param compactFormat: (bool, optional): Export using a more compact file format. Defaults to None.
        :param headerDefault: (bool, optional): Use the default report header. Defaults to None.
        :param headerNone: (bool, optional): Use no report header. Defaults to None.
        :param headerCompact: (bool, optional): Use a compact report header. Defaults to None.
        :param headerCustom: (str, optional): Custom report header name. Defaults to None.
        :param headerLine1: (str, optional): Report header line 1 text. Defaults to None.
        :param headerLine2: (str, optional): Report header line 2 text. Defaults to None.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        cmd = "3D.Export.Report("

        if measuredData is not None:
            cmd += f"Measured Data={measuredData},"
        if designData is not None:
            cmd += f"Design Data={designData},"
        if measurements is not None:
            cmd += f"Measurements={measurements},"
        if pointsLayout is not None:
            cmd += f"Points Layout={pointsLayout},"
        
        if filename is not None:
            cmd += f"filename={filename},"
        if ok is not None:
            cmd += f"Ok={ok},"
        if units is not None:
            cmd += f"units={units},"
        if save is not None:
            cmd += f"Save={save},"
        if saveAs is not None:
            cmd += f"Save As={saveAs},"

        if points is not None:
            cmd += f"points={points},"
        if planes is not None:
            cmd += f"planes={planes},"
        if lines is not None:
            cmd += f"lines={lines},"
        if circles is not None:
            cmd += f"circles={circles},"
        if spheres is not None:
            cmd += f"spheres={spheres},"
        if cylinders is not None:
            cmd += f"cylinders={cylinders},"
        if curves is not None:
            cmd += f"curves={curves},"
        if surfaces is not None:
            cmd += f"surfaces={surfaces},"

        if designPoints is not None:
            cmd += f"design points={designPoints},"
        if designPlanes is not None:
            cmd += f"design planes={designPlanes},"
        if designLines is not None:
            cmd += f"design lines={designLines},"
        if designCircles is not None:
            cmd += f"design circles={designCircles},"
        if designSpheres is not None:
            cmd += f"design spheres={designSpheres},"
        if designCylinders is not None:
            cmd += f"design cylinders={designCylinders},"
        if designCurves is not None:
            cmd += f"design curves={designCurves},"
        if designSurfaces is not None:
            cmd += f"design surfaces={designSurfaces},"

        if columnHeadings is not None:
            cmd += f"column headings={columnHeadings},"
        if label is not None:
            cmd += f"label={label},"
        if xyz is not None:
            cmd += f"XYZ={xyz},"
        if sigma is not None:
            cmd += f"Sigma={sigma},"
        if offset is not None:
            cmd += f"Offset={offset},"
        if description is not None:
            cmd += f"Description={description},"

        if tab is not None:
            cmd += f"Tab={tab},"
        if space is not None:
            cmd += f"Space={space},"

        if designResiduals is not None:
            cmd += f"Design Residuals={designResiduals},"
        
        if pointPoint is not None:
            cmd += f"Point Point={pointPoint},"
        if pointPlane is not None:
            cmd += f"Point Plane={pointPlane},"
        if pointLine is not None:
            cmd += f"Point Line={pointLine},"
        if pointCircle is not None:
            cmd += f"Point Circle={pointCircle},"
        if pointSphere is not None:
            cmd += f"Point Sphere={pointSphere},"
        if pointCylinder is not None:
            cmd += f"Point Cylinder={pointCylinder},"
        if pointCurve is not None:
            cmd += f"Point Curve={pointCurve},"
        if pointSurface is not None:
            cmd += f"Point Surface={pointSurface},"
        
        if planePlane is not None:
            cmd += f"Plane Plane={planePlane},"
        if planeLine is not None:
            cmd += f"Plane Line={planeLine},"
        if lineLine is not None:
            cmd += f"Line Line={lineLine},"

        if probePoints is not None:
            cmd += f"Probe Points={probePoints},"
    
        if compactFormat is not None:
            cmd += f"Compact Format={compactFormat},"

        if headerDefault is not None:
            cmd += f"Default={headerDefault},"
        elif default is not None:
            cmd += f"Default={default},"

        if headerNone is not None:
            cmd += f"None={headerNone},"
        elif none is not None:
            cmd += f"None={none},"

        if headerCompact is not None:
            cmd += f"Compact={headerCompact},"
        elif compact is not None:
            cmd += f"Compact={compact},"

        if headerCustom is not None:
            cmd += f"Custom={headerCustom},"
        elif custom is not None:
            cmd += f"Custom={custom},"

        if headerLine1 is not None:
            cmd += f"Line1={headerLine1},"
        elif line1 is not None:
            cmd += f"Line1={line1},"

        if headerLine2 is not None:
            cmd += f"Line2={headerLine2},"
        elif line2 is not None:
            cmd += f"Line2={line2},"

        cmd = cmd.rstrip(",")
        cmd += ")"

        self.__vexec(cmd)

    def Copy3D(self, filename=None, newName="", copyBundleStatisticsFolder=False):
        """
        Copies the entire contents of a 3D data file to another 3D file in the currently opened project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to copy. When this parameter is omitted, the current driver is copied.
        :param newName: The new name for the 3D file.
        :param copyBundleStatisticsFolder:

        :example:

        .. code:: python

            # This will copy the current driver file to 'final3D'
            V.Copy3D(newName="final3D")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Copy3D("
        if filename is not None:
            commandString += "filename={},".format(filename)
        commandString += "new name={}, copy bundle statistics folder={})".format(newName, copyBundleStatisticsFolder)
        self.__vexec(commandString)

    def Rename3D(self, filename=None, oldName=None, newName="NewName"):
        """
        Function to rename a 3D data file within the currently opened project.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to rename. When this parameter is omitted, the current driver is renamed.
        :param oldname:
        :param newName: The new name for the 3D file.

        :example:

        .. code:: python

            Rename3D(new name=final3D)
            #This will rename the current driver file to 'final3D.3D'.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Rename3D("
        if filename is not None:
            commandString += "filename={},".format(filename)
        elif oldName is not None:
            filename = oldName
            commandString += "filename={},".format(filename)

        commandString += "new name={})".format(newName)
        self.__vexec(commandString)

    def XYZImportDataFile(self, filename: str, units: str = None):
        """
        Imports a data file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to import.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.Data File("
        commandString += f'filename="{filename}",'
        if units is not None:
            commandString += f"units={units},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZImportViewSettings(self, filename: str = None, source: str = None):
        """

        Function to import graphical view settings.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The filename to apply the imported view settings to. If this parameter is missing, the driver file is used.
        :param source: The 3D file from which to import the graphical view settings.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.View Settings("
        if filename is not None:
            commandString += f"filename={filename},"
        if source is not None:
            commandString += f"source={source},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZImportCoordinateSystems(self, filename: str = None, source: str = None):
        """
        Imports coordinate systems into a specified 3D file.  You need to make sure the destination 3D file is currently in the same coordinate system as the active coordinate system in the source file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to import coordinate systems into. If omitted, coordinate systems are imported into the current driver.
        :param source: The name of the 3D file of coordinate systems.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.Coordinate Systems("
        if filename is not None:
            commandString += f"filename={filename},"
        if source is not None:
            commandString += f"source={source},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZUpdateConstructionObjects(self, filename: str = None):
        """
        Update a 3D file's construction objects.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Update.Construction Objects("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZUpdateProximityPointLabelers(self, filename: str = None):
        """
        Update a 3D file's proximity labelers.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Update.Proximity Point Labelers("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZDelete(self, filename: str, ignoreMissing=True):
        """
        Deletes one or more 3D files.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: 3D file name to delete. Case does not matter. Filename can contain wildcards but only one filename entry is allowed.
        :param ignoreMissing:

        :examples:

        .. code:: python

            V.XYZDelete(filename = "Bundle3" )

            V.XYZDelete(filename = "Bundle*")

            V.XYZDelete(filename = "AutoMatch*" )

            V.XYZDelete(filename = "RO*")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

         """
        commandString = f"3D.Delete(filename={filename}, ignore missing={ignoreMissing})"
        self.__vexec(commandString)

    def DeleteALL3D(self, exceptFilenames: str = None):
        """
        Deletes all 3D files from the opened project, except for those specified by the exceptFilenames parameter

        :requires: *V-STARS 4.9.4.0 or greater*

        :param exceptFilenames: names separated by spaces of all the 3D files **NOT** to delete

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "DeleteALL3D("
        
        if exceptFilenames is not None:
            commandString += f"except filenames={exceptFilenames}"

        #commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def Select3D(self, filename: str = None):
        """
        Select a 3D file (show the graphical view).

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: 3D file name to display. If no filename is specified, the Driver file is selected.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Select3D("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZConstructionDelete(self, filename: str = None):
        """

        Deletes all construction data from the specified 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: 3D file name who's construction data will be deleted.  If omitted, the driver file will be selected.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Construction.Delete("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZImportConstructionData(self, filename=None, construction=None):
        """
        Imports construction data into a specified 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to import construction data into. If omitted, construction data are imported into the current driver.
        :param construction: The name of the 3D file of construction data.

        :examples:

        .. code:: python

            # import the construction data in the 3D file 'Build data' into the current driver file.
            V.XYZImportConstructionData(construction = "Build data")

            # import the construction data in the 3D file 'Build data' into the 3D file 'New Data'.
            V.XYZImportConstructionData(filename = "New Data", construction = "Build data")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.Construction Data("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if construction is not None:
            commandString += "construction={},".format(construction)
        commandString += ")"
        self.__vexec(commandString)

    def SelectPointsAll(self, filename=None, measured=True, design=False, construction=False):
        """
        Select a group of point for a later operation. See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to true to select the measured points in the 3D file. If no selection type is specified as true, the measured points are used.
        :param design: Set the true to select the design points in the 3D file.
        :param construction: Set to true to select only points construction points.

        **WARNING!** - Only set one of measured, design or construction=true or unpredictable results can occur.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPointsAll("
        if filename is not None:
            commandString += f"filename={filename},"
        if design:
            measured = False
        commandString += f"measured={measured}, design={design}, construction={construction})"
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def PasteSelection(self, filename=None, measured=None, design=None, overwrite=None, append=None):
        """
        Paste selected points in the specified 3D file. Points selected by one of the 'SelectPoints' commands (see above) are pasted into the named 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file to paste into. Must be in the project. If this parameter is omitted, then the driver file is used.
        :param measured: Set to true to paste into the measured points in the 3D file. If no selection type is specified as true, the points will be pasted into the measured points.
        :param design: Set to true to paste into the design points in the 3D file.
        :param overwrite: Set to true to overwrite existing points with the same label. The default is false.
        :param append:

        **WARNING!** - Do not set measured=true and design=true or unpredictable results can occur.

        :examples:

        .. code:: python

            #  paste all the current selections into the measured area of the current driver file.
            #  Any points with labels that are the same as already existing labels will have their labels appended.
            V.PasteSelection()

            # paste all the current selections into the design area of the 3D file 'F3'.
            # Any existing points with labels that are the same as the labels of any pasted point will be overwritten.
            V.PasteSelection(filename="F3", design=True, overwrite=True)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "PasteSelection("
        if filename is not None:
            commandString += f"filename={filename},"
        if measured is not None:
            commandString += f"measured={measured},"
        if design is not None:
            commandString += f"design={design},"
        if overwrite is not None:
            commandString += f"overwrite={overwrite},"
        if append is not None:
            commandString += f"append={append},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZAlignFile(self, filename=None, off=False):
        """
        Function to set the current alignment file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to set as the alignment file. The 3D file must exist in the current project.
        :param off: Set this parameter to true to turn the current alignment file off.

        :example:

        .. code:: python

            XYZAlignFile(filename="TestFile")
            # This will set the 3D file named 'TestFile' as the alignment file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Alignment File("
        if filename is not None:
            commandString += f"filename={filename},"
        commandString += f"off={off})"
        self.__vexec(commandString)

    def XYZDriverFile(self, filename=None, off=False):
        """
        Function to set the current driver file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to set as the driver file. The 3D file must exist in the current project.
        :param off: Set this parameter to true to turn the current driver file off.

        :example:

        .. code:: python

            XYZDriverFile(filename="DriverPoints")
            #This will set the 3D file named 'DriverPoints' as the Driver file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Driver File("
        if filename is not None:
            commandString += f"filename={filename},"
        commandString += f"off={off})"
        self.__vexec(commandString)

    def XYZSourceFile(self, filename=None, off=False):
        """
        Function to set the current source file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to set as the source file. The 3D file must exist in the current project.
        :param off: Set this parameter to true to turn the current source file off.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Source File("
        if filename is not None:
            commandString += f"filename={filename},"
        commandString += f"off={off})"
        self.__vexec(commandString)

    def ProjectFileNames(self):
        """
        Returns the names of the current driver file and current triangulation file.

        :requires: *V-STARS 4.9.4.0 or greater*

        Return values:

        **v.projectDriver**
        The name of the current driver file.

        **v.projectTriangulation**
        The name of the current triangulation file (MMode).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetProjectFileNames()"
        self.__vexec(commandString)
        return self.getValue("v.projectDriver"), self.getValue("v.projectTriangulation")

    def XYZDetailFile(self, filename=None):
        """
        Select the detail file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: 3D file name to mark as a detail file.

        :example:

        .. code:: python

            XYZDetailFile(filename="Wing Details")
            #This will set the 3D file named 'Wing Details' as the Detail file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Detail File("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZProbeFile(self, filename=None):
        """
        Function to set the current probe file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to set as the probe file. The 3D file must exist in the current project.

        :example:

        .. code:: python

            XYZProbeFile(filename="AftEnd")
            #This will set the 3D file named 'AftEnd' as the Probe file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Probe File("
        if filename is not None:
            commandString += f"filename={filename}"
        commandString += ")"
        self.__vexec(commandString)

    def XYZCoordinateSystems(
        self, filename=None, name=None, design=False, delete=False, ignoreMissing=False, rename=None
    ):
        """
        Edit a coordinate system in a 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to use. It must exist in the current project. If no filename is specified, the driver file is used.
        :param name: The name of the coordinate system to modify. This coordinate system must exist in the chosen 3D file.
        :param design: Set to true to have the design data within the 3D file also change coordinate systems when changing the active system. The default value is false.
        :param delete: Deletes a coordinate system in a 3D file.
        :param ignoreMissing: If True and the named coordinate system is missing when delete is True an error will not be generated.
        :param rename: The new name of the coordinate system. If set, the named coordinate system will be renamed.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Coordinate Systems("

        if filename is not None:
            commandString += f"filename={filename},"

        if name is not None:
            commandString += f"name={name},"

        if design is not None:
            commandString += f"design={design},"

        if delete is not None:
            commandString += f"delete={delete},"

        if ignoreMissing is not None:
            commandString += f"ignore missing={ignoreMissing},"

        if rename is not None:
            commandString += f"rename={rename},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZCoordinateSystemsActive(self, filename=None, name=None, design=False):
        """
        Makes a coordinate system in a 3D file active so that all points and objects are displayed in that coordinate system.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to use. It must exist in the current project. If no filename is specified, the driver file is used.
        :param name: The name of the coordinate system to make active. This coordinate system must exist in the chosen 3D file.
        :param design: Set to true to have the design data within the 3D file also change coordinate systems. The default value is false.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Coordinate Systems.Active("

        if filename is not None:
            commandString += f"filename={filename},"

        if name is not None:
            commandString += f"name={name},"

        if design is not None:
            commandString += f"design={design},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZCoordinateSystemsDelete(self, filename=None, name=None, ignoreMissing=False):
        """
        Deletes a coordinate system in a 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to use. It must exist in the current project. If no filename is specified, the driver file is used.
        :param name: The coordinate system to delete. The active coordinate system cannot be deleted unless it is the only coordinate system in the file. Wildcards can be used. If a wildcard is used, the active coordinate system can be deleted if it is the only coordinate system in the file.
        :param ignoreMissing: If True and the named coordinate system is missing an error will not be generated.

        **NOTE:** The active coordinate system cannot be deleted unless it is the only coordinate system in the file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Coordinate Systems.Delete("
        if filename is not None:
            commandString += f"filename={filename},"
        if name is not None:
            commandString += f"name={name},"
        if ignoreMissing is not None:
            commandString += f"ignore missing={ignoreMissing},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def XYZAutoRelabel(
        self, filename=None, desiredLabels=None, nearnessThreshold=None, doAlignment=None, onlyAutoMatched=None
    ):
        """
        Relabels points in a 3D file with labels from another 3D file. At least three labels between the two files must already match (at least four is recommended). Using these three (or more) points a temporary alignment is performed and the remaining points are relabeled based on their closeness.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file whose points are being relabeled. This 3D file must exist in the current project. If no filename is specified, the Driver file is used.
        :param desiredLabels: The name of the 3D file whose points have the desired labels. This 3D file must also exist in the current project.
        :param nearnessThreshold: Designates how close points must be (after the temporary alignment) to be relabeled. If this value is less than 0, it is used as a multiplier to determine a threshold based on the RMS of the transformation. eg. Threshold = multiplier*RMS.
        :param doAlignment: Align the filename data and desired labels data before matching the points for relabel. This requires that you have at least four points in common that are already labeled correctly. These four points are typically coded targets.
        :param onlyAutoMatched: If set to only automatched, then only auto matched (TARGET) points are relabeled. Set to all points to relabel points of any label. (only automatched is the default behavior)

        Return Values:

        **AutoRelabelResults**
        The class holding all relevant info

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.AutoRelabel("
        if filename is not None:
            commandString += f"filename={filename},"
        if desiredLabels is not None:
            commandString += f"desired Labels={desiredLabels},"
        if nearnessThreshold is not None:
            commandString += f"nearness Threshold={nearnessThreshold},"
        if doAlignment is not None:
            commandString += f"do Alignment={doAlignment},"
        if onlyAutoMatched is not None:
            commandString += f"only AutoMatched={onlyAutoMatched},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        
        results = AutoRelabelResults()
        results.update(self.returnValueManager)
        return results

    def XYZPointsMoveToDesign(self, filename=None, overwrite=False):
        """
        Moves measured points from the given 3D file to design

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param overwrite: If True, points of the same name will be over-written, otherwise same named points are ignored

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Points.Move to Design("

        if filename is not None:
            commandString += f"filename={filename},"

        commandString += f"overwrite={overwrite})"

        self.__vexec(commandString)

    # Beginning of New Functions-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def HideVStars(self):
        """
        Hides the V-STARS program

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "HideVStars()"
        self.__vexec(commandString)

    def FFTDeletePlanes(self, filename=""):
        """
        Deletes FFT planes made by the FFTFind() command. Useful for cleaning up a 3D file of unwanted FFT planes.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: Name of the 3D file to delete FFT plane form.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "FFTDeletePlanes(filename={})".format(filename)
        self.__vexec(commandString)

    def WaitForCameraTrigger(self):
        """
        Puts the cameras into message only mode. When they detect a trigger (fire button or external trigger), they will not take a picture but will notify V-STARS of the trigger. The command will not return
        a success message until the cameras have triggered and sent a message to V-STARS. This allows a script that waits for an external event to happen before proceeding on. This command takes no parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "WaitForCameraTrigger()"
        self.__vexec(commandString)

    def TriangulatePoints(self, labels="", filename="", rejection=0):
        """
        Command to triangulate points that are not already present in the driver file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param labels: The labels of the points to be triangulated. Multiple labels are separated by a space and may contain wild cards: labels=CODE* P1 P2.
        :param filename: The file name for the newly created 3D file. All points (and other geometry) already in the driver file will be copied into this new file with the newly triangulated points added._This new file becomes the new driver file. If filename already exists the name is incremented, until a unique name is found, as in: triangulation3.
        :param rejection: The image coordinate rejection limit expressed in um.

        Return values:

        **v.triangulateTotalCount**
        The number of points attempted to_triangulate.

        **v.triangulateSuccessCount**
        The number of points successfully triangulated.

        **v.triangulateRMS**
        The overall RMS al all image residuals for all points successfully triangulated.

        **v.triangulateFailCount**
        The number of points that failed to_triangulate.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "TriangulatePoints(labels={}, filename={}, rejection={})".format(labels, filename, rejection)
        self.__vexec(commandString)

    def GetCameraName(self, index=0):
        """
        Get the camera name by index, where index is the number of the camera as listed in the project starting at 1.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param index: The index of the camera.

        Return values:

        The name of the camera.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "GetCameraName(index={})".format(index)
        self.__vexec(commandString)
        rv = self.getValue("v.cameraName")
        return rv

    def ClosePicture(self, camera="", index=0):
        """
        Closes a picture window. You can specify the camera by its name or by its index

        :requires: *V-STARS 4.9.4.0 or greater*

        **NOTE**:  Do not specify by name and index in the same command or an error will occur.

        :param camera: The name of the camera whose picture will be closed. It must be in the opened project.
        :param index: The index (1 to n) of the camera whose picture will be closed.  For example, if there are 4 cameras in the project, the index values would be 1,2,3,4.  The camera indexes are determined by the order they are listed in the project (first in list = 1).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "ClosePicture(camera={}, index={})".format(camera, index)
        self.__vexec(commandString)

    def CameraAutoExposure(
        self, camera=None, index=0, autoShutter=False, autoStrobe=False, shutterAdjust=0, strobeAdjust=0, minimize=False
    ):
        """
        Perform the auto exposure command on the specified camera. Reference the camera by either name (camera) or by index. When referencing by index the first camera will be index=1.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param camera:
        :param index:
        :param autoShutter:
        :param autoStrobe:
        :param shutterAdjust:
        :param strobeAdjust:
        :param minimize:

        **v.autoExposureShutter**
        The calculated shutter value.

        **v.autoExposureStrobe**
        The calculated strobe value.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "CameraAutoExposure("
        if camera is not None:
            commandString += "camera={}, ".format(camera)
        else:
            commandString += "index={}, ".format(index)
        commandString += "auto shutter={}, auto strobe={}, shutter adjust={}, strobe adjust={}, minimize={})".format(
            autoShutter, autoStrobe, shutterAdjust, strobeAdjust, minimize
        )
        self.__vexec(commandString)

    def GetCameraTemperature(self, index: int = None, camera: str = None):
        """
        Gets the current camera temperature in C

        :requires: *V-STARS 4.9.8 or greater*

        :param index: the 1 based camera index (Do not use this and camera)
        :param camera: The name of the camera (Do not use this and index)

        :return temperature

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetCameraTemperature("
        if index is not None:
            commandString += f"index={index},"
        if camera is not None:
            commandString += f"camera={camera},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        temp = self.getValue("v.cameraTemperature")
        return temp

    def GetCameraFileName(self, index=0):
        """
        :requires: *V-STARS 4.9.4.0 or greater*

        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "GetCameraFileName(index={})".format(index)
        self.__vexec(commandString)
        return self.getValue("v.cameraFileName")

    def Beep(self, success=False, failure=False, sound=""):
        """
        Plays a V-STARS sound. As of V-STARS 4.9 these sounds are specified in the sounds.ini file located the the GSI system folder.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param success: Plays the V-STARS Probe Success sound.
        :param failure: Plays the V-STARS Probe Failure sound.
        :param sound: Plays another sound registered using the string specified. As of V-STARS 4.9 this is the full path to a wav file to be played.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Beep(success={}, failure={}, sound={})".format(success, failure, sound)
        self.__vexec(commandString)

    def ProSpotStatus(self):
        """
        Returns the current status of a connected ProSpot/A. This function takes no parameters.

        :requires: *V-STARS 4.9.5.0 or greater*

        Return values:

        **v.proSpotFocusing**
        A Boolean value indicating if a ProSpot/A is currently focusing.

        **v.proSpotFocus**
        The current focus value in object distance.  Feet for imperial units and meters for metric.
        If == -9999.0 the focus needs to be initialized

        **v.proSpotPower**
        The current power setting in percent of full power.

        **v.proSpotEnabled**
        A Boolean value indicating if a ProSpot/A is currently Enabled and ready.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "ProSpotStatus()"
        self.__vexec(commandString)
        self.proSpotFocusing = self.getValue("v.proSpotFocusing")
        self.proSpotFocus = self.getValue("v.proSpotFocus")
        self.proSpotPower = self.getValue("v.proSpotPower")
        self.proSpotEnabled = self.getValue("v.proSpotEnabled")

    def ProSpotCell(self, on=False):
        """
        Sets the photocell for the Prospot/A projector on or off.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param on: Turn the photocell on (true) or off (false).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "ProSpotCell(on={})".format(on)
        self.__vexec(commandString)

    def ProSpotPower(self, power=0):
        """
        Sets the strobe power for the Prospot/A projector.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param power: A decimal percentage from 0 to 100. e.g. power=50 will set the Prospot to its 50% power level.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "ProSpotPower(power={})".format(power)
        self.__vexec(commandString)

    def ProSpotFocus(self, focus=0, init=False):
        """
        Set the focus distance for ProSpot/A projector.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param focus: The object distance in decimal feet or meters (in feet if the project is in inches, feet or yards, otherwise in meters).
        :param init: If true initialize the focus. An initialization should be done before any focus value is set.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProSpotFocus(focus={}, init={})".format(focus, init)
        self.__vexec(commandString)

    def ProSpotConnect(self):
        """
        Connect / reconnects USB Prospot control

        :requires: *V-STARS 4.9.6.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProSpotConnect()"
        self.__vexec(commandString)

    def ProSpotConnected(self, refresh=False):
        """
        Queries to see if a ProSpot/A is connected.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param refresh: If true, no value is returned. Instead the connected cameras are queried to see if a ProSpot/A is connected.

        Return values:

        **v.proSpotConnected**
        A Boolean value indicating if a ProSpot/A is connected.  Only returned if refresh is not specified or set to false.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProSpotConnected(refresh={})".format(refresh)
        self.__vexec(commandString)

    def MModePointLabel(self, label="", wait=False):
        """
        Sets the M Mode point label.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param label: Set the next probe label (must be a legal V-STARS point label, returns error if not).
        :param wait: If true V-STARS will not return a success until a probe point is collected

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MModePointLabel(label={}, wait={})".format(label, wait)
        self.__vexec(commandString)

    def MModeMeasurementType(self, measurementType: str = None, showWarnings: bool = None, toggle: bool = None):
        """
        Sets the M Mode measurement type.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param measurementType: M-Mode measurement type **_ _ _'probe'** - Probe mode **_ _ _'prospot'** - Single shot prospot mode **_ _ _'comboshot'** - Combo shot prospot mode **_ _ _'automatch'** - Automatch mode
        :param showWarnings: If true will show the V-STARS warning dialogs (defaults to false).

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MModeMeasurementType("
        if measurementType is not None:
            commandString += "type={},".format(measurementType)
        if showWarnings is not None:
            commandString += "show warnings={},".format(showWarnings)
        if toggle is not None:
            commandString += "toggle={},".format(toggle)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def DisableBundledPictures(self, bad=False, weak=False):
        """
        Disable the pictures from the last bundle that meet the specified criteria. After being disabled the bundle will need to be run again so those pictures are not included in the output.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param bad: If true, pictures categorized as bad will be disabled.
        :param weak: If true, pictures categorized as weak will be disabled.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "DisableBundlesPictures(bad={}, weak={})".format(bad, weak)
        self.__vexec(commandString)

    def SelectPlanesByLabel(self, filename="", measured=False, design=False, labels=""):
        """
        Select a group of planes for a later operation. See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the planes are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set the true to select the measured planes in the 3D file. If no selection type is specified as true, the measured planes are used.
        :param design: Set the true to select the design planes in the 3D file.

        **WARNING!** - Only set one of measured or design=true or unpredictable results can occur.

        :param labels: A list of labels (separated by a blank space) to be selected. Labels may include wild-cards. For example labels=PLATE* will select all planes that begin with the label PLATE (case does not matter).

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of planes in the selection buffer after the command is executed. It is set to 0 by an UnselectPlanesAll command, and when any Selection Command references a new 3D file.

        **v.selectionNumberFound**
        The number of planes selected by the command.

        Example:

        .. code:: python

            SelectPlanesByLabel(labels=PLATE* TOP*)
            #Selects all the measured circles whose labels begin with 'PLATE' or 'TOP' from the current driver file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectPlanesByLabel(filename={}, measured={}, design={}, labels={})".format(
            filename, measured, design, labels
        )
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectCirclesByLabel(self, filename="", measured=False, design=False, labels=""):
        """
        Select a group of circles for a later operation. See 'DeleteSelection' or 'PasteSelection'.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the circles are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param measured: Set the true to select the measured circles in the 3D file. If no selection type is specified as true, the measured circles are used.
        :param design: Set the true to select the design circles in the 3D file.

        **WARNING!** - Only set one of measured or design=true or unpredictable results can occur.

        :param labels: A list of labels (separated by a blank space) to be selected. Labels may include wild-cards. For example labels=HULL* will select all circles that begin with the label HULL (case does not matter).

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of circles in the selection buffer after the command is executed. It is set to 0 by an UnselectCirclesAll command, and when any Selection Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        Example:

        .. code:: python

            SelectCirclesByLabel(labels=HULL* FLANGE*)
            #Selects all the measured circles whose labels begin with 'HULL' or 'FLANGE' from the current driver file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectCirclesByLabel(filename={}, measured={}, design={}, labels={})".format(
            filename, measured, design, labels
        )
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def SelectClosePoints(self, filename="", distance=0, onlyAutomatched=False):
        """
        Select a group of points that are within a tolerance of each other for a later operation.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file from which the points are selected. Must be part of the opened project. If this parameter is omitted, then the driver file is used.
        :param distance: Set to true to select the measured points in the 3D file. If no selection type is specified as true, the measured points are used.
        :param onlyAutomatched: Set the true to select from only automatched points in the 3D file.

        Return Values:

        **v.selectionTotalNumberSelected**
        The number of points in the selection buffer after the command is executed. It is set to 0 by an UnselectPointsAll command, and when any Selection Points Command references a new 3D file.

        **v.selectionNumberFound**
        The number of points selected by the command.

        Example:

        .. code:: python

            SelectClosePoints(filename=bundle,distance=1.5, only automatched)
            #This will select all the automatched points that are within 1.5 units of each other in the 3D file called 'bundle'.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SelectClosePoints(filename={}, distance={}, only Automatched={})".format(
            filename, distance, onlyAutomatched
        )
        self.__vexec(commandString)
        return self.getValue("v.selectionTotalNumberSelected"), self.getValue("v.selectionNumberFound")

    def PicturesResect(self, pictures="", rejection=0, automaticRejection=False):
        """
        Command to resect a picture or group of pictures using the current driver file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param pictures: The picture number and/or range of pictures to resect as in: pictures=1 9 10-13. May also be pictures=all to resect all pictures
        :param rejection: The image coordinate rejection limit expressed in um.
        :param automaticRejection: If set to True, the image coordinate rejection limit is automatically calculated.

        Return values:

        **v.resectRMS**
        The overall RMS of all image residuals for all pictures successfully resect by this command.

        **v.resectTotalCount**
        The total number of pictures attempted to resect.

        **v.resectSuccessCount**
        The number of successfully resected pictures.

        **v.resectFailCount**
        The number of un-successfully resected pictures.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Pictures.Resect(pictures={}, rejection={}, automatic Rejection={})".format(
            pictures, rejection, automaticRejection
        )
        self.__vexec(commandString)

    def MModeUnStableCameraOrientation(self,
        bOK: bool = None,
        bundleMethod: bool = None,
        useDriverSigmas: bool = None
    ):
        """
        Executes the stable Camera Orientation just like the menu command.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param bOK: Closes the dialog when done.
        :param bundleMethod: Uses the old bundle unstable method
        :param useDriverSigmas: Uses the sigmas that are set in the driver file

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.UnStable Camera Orientation("

        if bOK is not None:
            commandString += f"OK={bOK},"
        if bundleMethod is not None:
            commandString += f"bundleMethod={bundleMethod},"
        if useDriverSigmas is not None:
            commandString += f"useDriverSigmas={useDriverSigmas},"
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def MModeStableCameraOrientation(self, hideWarnings = False):
        """
        Executes the Stable Camera Orientation just like the menu command.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param OK: Closes the dialog when done.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.Stable Camera Orientation(hide warnings={})".format(hideWarnings)
        self.__vexec(commandString)

    def MModeStableCameraCalibrationAndOrientation(self, hideWarnings = False):
        """
        Executes the Stable Camera Calibration & Orientation just like the menu command.

        :requires: *V-STARS 4.9.6.0 or greater*

        :param OK: Closes the dialog when done.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.Stable Camera Calibration & Orientation(hide warnings={})".format(hideWarnings)
        self.__vexec(commandString)

    def MModeStableMode(self, on=True):
        """
        Executes the MModeStableMode.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param OK: Closes the dialog when done.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("MMode.Stable Mode(on={})").format(on)
        self.__vexec(commandString)

    def MModeStableCameraOrientationBundle(self, accept=False):
        """
        Executes the stable Camera Orientation Bundle.

        :param accept: When True, V-STARS will automatically accept the bundle and the next script command will run.

        :requires: *V-STARS 4.9.6.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("MMode.Stable Camera Orientation Bundle(Accept={})").format(accept)
        self.__vexec(commandString)
        results = BundleStats()
        results.update(self.returnValueManager)
        return results

    def MModeSetup(
        self,
        lineMatching: bool = None,
        helperPoints: bool = None,
        helperPointsFeatureTargets: bool = None,
        mergePreviousTriangulation: bool = None,
        deletePreviousTriangulation: bool = None,
        triangulate: bool = None,
        saveImages: bool = None,
        saveEpochs: bool = None,
        softwareTrigger: bool = None,
    ):
        """
        Sets various MMode parameters that control how MMode operates. Currently a sub-set of those available on the MMode Setup Dialog.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param lineMatching: ?
        :param helperPoints: ?
        :param helperPointsFeatureTargets: ?
        :param mergePreviousTriangulation: ?
        :param deletePreviousTriangulation: If set to true, the previous triangulation 3D file will be removed from the V-STARS project tree after each trigger.
        :param triangulate: If true turns on MMode triangulation mode. This will cause V-STARS to triangulate codes and other targets that are not in the current driver file.
        :param saveImages: Save images in m mode
        :param saveEpochs: Save m pictures in m mode
        :param softwareTrigger: Set either software or hardware trigger

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MMode.Setup("

        if lineMatching is not None:
            commandString += "line Matching={},".format(lineMatching)
        if helperPoints is not None:
            commandString += "helper Points={},".format(helperPoints)
        if helperPointsFeatureTargets is not None:
            commandString += "helper points feature targets={},".format(helperPointsFeatureTargets)
        if mergePreviousTriangulation is not None:
            commandString += "merge previous triangulation={},".format(mergePreviousTriangulation)
        if deletePreviousTriangulation is not None:
            commandString += "delete previous triangulation={},".format(deletePreviousTriangulation)
        if triangulate is not None:
            commandString += "triangulate={},".format(triangulate)
        if saveImages is not None:
            commandString += "save images={},".format(saveImages)
        if saveEpochs is not None:
            commandString += "save epochs={},".format(saveEpochs)
        if softwareTrigger is not None:
            commandString += "software trigger={},".format(softwareTrigger)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def FileExit(self):
        """

        Exits the V-STARS application. This function takes no parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "File.Exit()"
        self.__vexec(commandString)

    def XYZScale(self, filename="", apply=False, saveLog=False):
        """
        Scale the specified 3D file using the project scale bars. If the driver file is scaled then the pictures (or M pictures if in M Mode) will also be scaled.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file in which to scale.  If omitted, the current driver is used.
        :param apply: Apply the calculated scale values. If not specified the scale values are only calculated and returned.
        :param saveLog: Save the scale values to a log file. Apply must also be set to true.

        Return Values:

        **v.scaleFactor**
        The calculated scale factor.

        **v.scaleRMS**
        The RMS of the scale distance differences.

        **v.scaleMin**
        The minimum of the absolute values of the scale differences.

        **v.scaleMax**
        The maximum of the absolute values of the scale differences.

        :example:

        .. code:: python

            XYZScale(filename=Bundle2,apply,save log)
            #This will calculate scale factor for the 3D file named 'Bundle2', apply that scale factor and save the results to the Scale Log.txt file in the project.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Scale(filename={}, apply={}, save Log={})".format(filename, apply, saveLog)
        self.__vexec(commandString)

    def XYZDistance(
        self,
        filename: str = None,
        point1: str = None,
        point2: str = None
    ):
        """
        Construct a point to point distance using the specified points in the cloud specified by filename.
        If filename is not specified the current driver will be used. If point1 or point2 is not specified
        a point or points will be selected from the current selection buffer.

        :requires: *V-STARS 4.9.6.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        :param filename: 3D file to select points from.
        :param point1: First point.
        :param point2: Second point.
        """
        commandString = "3D.Distance("

        if filename is not None:
            commandString += f"filename={filename},"
        if point1 is not None:
            commandString += f"point1={point1},"
        if point2 is not None:
            commandString += f"point2={point2},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        
        self.__vexec(commandString)

    def XYZAverage(
        self,
        name: str = None
    ):
        """
        Constructs an average point using the current selection buffer.

        :requires: *V-STARS 4.9.6.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        :param name: Name of the new point
        """
        commandString = "3D.Average("

        if name is not None:
            commandString += f"name={name}"

        # commandString = commandString.rstrip(",")
        commandString += ")"
        
        self.__vexec(commandString)

    def XYZMerge(
        self,
        filenames="",
        output="",
        simpleMerge=True,
        averagePointsWithSameLabel=False,
        add=False,
        noNameCheck=False,
        deleteDupes=False,
    ):
        """

        Creates a new 3D file of merged points from two or more 3D files.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filenames: The names of the 3D files to merge. These file names may contain wildcards.
        :param output: The name for the new 3D file. If the 3D file already exists, the new name will be appended by a number (1, 2, 3etc.) until a unique name is found.
        :param simpleMerge: This is the default merge type. Points are copied from all specified 3D files and merged into the output file.
        :param averagePointsWithSameLabel: If set true, points of the same label are averaged in the output 3D file.
        :param add: If set true, the XYZ's of points with the same label are added and the result put in the output 3D file.
        :param noNameCheck: Only relevant for Simple Merge. If set to true points with duplicate labels are added to the output 3D file. If set to false (the default) points with duplicate labels have their labels incremented to form a unique label then added to the output 3D file.
        :param deleteDupes: Only relevant for Simple Merge.  If set to true AND the No Name Check was also true, only one point of a specific label will be merged into the output file, with no preference form which source file it came from.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Merge(filenames={}, output={}, simple Merge={}, average Points With Same Label={}, add={}, no Name Check={}, delete Dupes={})".format(
            filenames, output, simpleMerge, averagePointsWithSameLabel, add, noNameCheck, deleteDupes
        )
        self.__vexec(commandString)

    def XYZPatternRelabel(
        self,
        filename=None,
        pattern=None,
        relabelCloseness=None,
        distanceMatch=None,
        transformRejection=None,
        onlyAutomatched=None,
        logFile=None,
        ransac=None,
        minPatternDistance=None,
    ):
        """
        Does 3D point label matching using two 3D files

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to match. Driver if not specified
        :param pattern: The name of the 3D file that contains the points to match and relabel.
        :param relabelCloseness: Tolerance used for point relabeling
        :param distanceMatch: Tolerance used to matched the pattern
        :param transformRejection: Transformation rejection factor for final transformation check
        :param onlyAutomatched: Only consider automatched points
        :param logFile: Save results to a log file
        :param ransac: Use RanSac algorithm (deprecated, use PatternRelabelRansac instead)
        :param minPatternDistance: Distance tolerance for RanSac algorithm

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Pattern Relabel("

        if filename is not None:
            commandString += "filename={},".format(filename)
        if pattern is not None:
            commandString += "pattern={},".format(pattern)
        if relabelCloseness is not None:
            commandString += "relabel closeness={},".format(relabelCloseness)
        if distanceMatch is not None:
            commandString += "distance match={},".format(distanceMatch)
        if transformRejection is not None:
            commandString += "transform rejection={},".format(transformRejection)
        if onlyAutomatched is not None:
            commandString += "only automatched={},".format(onlyAutomatched)
        if logFile is not None:
            commandString += "log file={},".format(logFile)
        if minPatternDistance is not None:
            commandString += "minPatternDistance={},".format(minPatternDistance)
        if ransac is not None:
            commandString += "ransac={},".format(ransac)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def PatternRelabelRansac(
        self,
        filename=None,
        pattern=None,
        relabelCloseness=None,
        distanceMatch=None,
        minPatternDistance=None,
        minPercent=None,
        numTrials=None,
        minx=None,
        maxx=None,
        miny=None,
        maxy=None,
        minz=None,
        maxz=None,
    ):
        """
        Does 3D point label matching using the RanSac algorithm using two 3D files

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to match. Driver if not specified.
        :param pattern: The name of the 3D file that contains the points to match and relabel.
        :param relabelCloseness: in project units, how close a point needs to be, to be considered an inlier (default disabled)
        :param distanceMatch: The algorithm first guesses candidate matching points by comparing point to point distances, distances below this threshold will be considered a candidate (default disabled)
        :param minPatternDistance: Percent of the size of the pattern extents to use for initial distance match (default = .1)
        :param minPercent: The minimum percent (expressed as 0 to 1.0) of pattern point relabeled to be considered a successful match (default 0.5 or 50%)
        :param numTrials: Number of RANSAC attempts to try (default 100)
        :param minx: ROI minimum x
        :param maxx: ROI maximum x
        :param miny: ROI minimum y
        :param maxy: ROI maximum y
        :param minz: ROI minimum z
        :param maxz: ROI maximum z

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "PatternRelabelRansac("

        if filename is not None:
            commandString += "filename={},".format(filename)
        if pattern is not None:
            commandString += "pattern={},".format(pattern)
        if relabelCloseness is not None:
            commandString += "relabelCloseness={},".format(relabelCloseness)
        if distanceMatch is not None:
            commandString += "distanceMatch={},".format(distanceMatch)
        if minPatternDistance is not None:
            commandString += "minPatternDistance={},".format(minPatternDistance)
        if minPercent is not None:
            commandString += "minPercent={},".format(minPercent)
        if numTrials is not None:
            commandString += "numTrials={},".format(numTrials)
        if minx is not None:
            commandString += "minx={},".format(minx)
        if maxx is not None:
            commandString += "maxx={},".format(maxx)
        if miny is not None:
            commandString += "miny={},".format(miny)
        if maxy is not None:
            commandString += "maxy={},".format(maxy)
        if minz is not None:
            commandString += "minz={},".format(minz)
        if maxz is not None:
            commandString += "maxz={},".format(maxz)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

        matchSuccessCount = self.getValue("v.matchSuccessCount")
        matchPatternCount = self.getValue("v.matchPatternCount")

        return matchSuccessCount, matchPatternCount

    def XYZExportVSURF(
        self,
        filename="",
        save_as="",
        save=False,
        overwrite=False,
        include_header=False,
        xyz_fields="",
        separator="",
        sort_by="",
        sort_by_direction="",
    ):
        """

        Function to export an existing 3D file point to surface measurements to a text file using the VSURF format.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the source file. If omitted, the driver file will be used.
        :param save_as: The name of the output file.
        :param save: If true then the File Save dialog is not shown and the value in the Save As parameter is used.  If the Save As parameter is omitted then an error will be returned.
        :param overwrite: True will overwrite the output file if it already exists.
        :param include_header: If true then the column headings will be included in the output file.
        :param xyz_fields: Specifies which type of value will appear in the XYZ columns. If omitted, the current value in the gsi32.ini file will be used. This parameter will also update the gsi32.ini file.
        :param separator: Specifies the field delimiter. This parameter will also update the gsi32.ini file.
        :param sort_by: Specifies the field by which to sort. This parameter will also update the gsi32.ini file.
        :param sort_by_direction: Specifies the sort direction. This parameter will also update the gsi32.ini file.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Export.VSURF(filename={}, save as={}, save={}, overwrite={}, include header={}, xyz fields={}, separator={}, sort by={}, sort by direction={})".format(
            filename, save_as, save, overwrite, include_header, xyz_fields, separator, sort_by, sort_by_direction
        )
        self.__vexec(commandString)

    # End of New Functions-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def XYZImportToDesign(self, filename=None, design=None, delete_existing=True, description=None):
        """
        Function to import design data into a specified 3D file. All the values (not just points) in the measured area of the Design file are imported into the design area of the specified 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to import design values into. If omitted, values are imported into the current driver. Any existing design data will be deleted.
        :param design: The name of the 3D file of design values.
        :param delete_existing: Set True to erase any existing design data
        :param description: Set the description for the measured points

        :examples:

        .. code:: python

            # This example will import the design data in the 3D file **'Plane design'** into the current driver file.
            V.XYZImportToDesign(design = "Plane design")

            # This example will import the design data in the 3D file **'Plane Design'** into the 3D file **'Plane Measure'**.
            V.XYZImportToDesign(filename = "Plane Measure", design = "Plane design")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.To Design("
        commandString += "delete existing={},".format(delete_existing)
        if filename is not None:
            commandString += "filename={},".format(filename)
        if design is not None:
            commandString += "design={},".format(design)
        if description is not None:
            commandString += "description={},".format(description)
        commandString += ")"
        self.__vexec(commandString)

    def XYZImportProximityPointLabelers(self, proximity=None, filename=None):
        """
        Update a 3D file's proximity labelers.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param proximity: The filename with the proximity point labelers
        :param filename:  The name of the 3D file to update. If omitted, the current driver is updated.

        :examples:

        .. code:: python

            V.XYZImportProximityPointLabelers(filename="dft-tetra-30-with-codes")

            V.XYZImportProximityPointLabelers(filename="dft-tetra-60-with-codes")

            V.XYZImportProximityPointLabelers(filename="dft-tetra-60")

            V.XYZImportProximityPointLabelers(filename="dft-tetra-30")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Import.Proximity Point Labelers("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if proximity is not None:
            commandString += "proximity={},".format(proximity)
        commandString += ")"
        self.__vexec(commandString)

    def WindowTile(self):
        """
        Tiles the windows. This command takes no parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Window.Tile()"
        self.__vexec(commandString)

    def ExportProject(self, filename=None, inJSON=True):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ExportProject("
        if filename is not None:
            commandString += "filename={},".format(filename)

        commandString += "inJSON={},".format(inJSON)
        commandString += ")"
        self.__vexec(commandString)

    def setScanningBlackTargets(self, value=True):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param value:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("Project.Scanning.setBlackTargets(value={})").format(value)
        self.__vexec(commandString)

    def setHoleMeasurement(self, value=True):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param value:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("Project.setHoleMeasurement(value={})").format(value)
        self.__vexec(commandString)

    def isHoleMeasurement(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.isHoleMeasurement()"
        self.__vexec(commandString)
        return self.getValue("v.isHoleMeasurement")

    def setHoleProcAlreadyRun(self, value=True):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param value:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("Project.setHoleProcAlreadyRun(value={})").format(value)
        self.__vexec(commandString)

    def isHoleProcAlreadyRun(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.isHoleProcAlreadyRun()"
        self.__vexec(commandString)
        return self.getValue("v.isHoleProcAlreadyRun")

    def AddErrorToInfoDoc(self, message=""):
        """
        Prints the error message to the info window and to the vstars log file

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddErrorToInfoDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def AddWarningToInfoDoc(self, message=""):
        """
        Prints the warning message to the info window and to the vstars log file

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddWarningToInfoDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def AddMessageToInfoDoc(self, message=""):
        """
        Prints the message to the info window and to the vstars log file

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddMessageToInfoDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def AddErrorToScriptDoc(self, message=""):
        """
        Prints the error message to the script window

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddErrorToScriptDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def AddWarningToScriptDoc(self, message=""):
        """
        Prints the warning message to the script window

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddWarningToScriptDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def AddMessageToScriptDoc(self, message=""):
        """
        Prints the message to the script window

        :requires: *V-STARS 4.9.4.0 or greater*

        :param message:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = 'AddMessageToScriptDoc(message="{}")'.format(message)
        self.__vexec(commandString)

    def CreateHoleMeasurementTemplateFiles(self, filename="", side=""):
        """
        Special one off function to support black hole measurements

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param side:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("CreateHoleMeasurementTemplateFiles(filename={}, side={})").format(filename, side)
        self.__vexec(commandString)
        return self.getValue("v.holeMeasurementFeatureCount")

    def ShowHoleMeasurementInitDlg(self, selectSide=True):
        """
        Special one off function to support black hole measurements

        :requires: *V-STARS 4.9.4.0 or greater*

        :param selectSide:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = ("ShowHoleMeasurementInitDlg(selectSide={})").format(selectSide)
        self.__vexec(commandString)
        return self.getValue("v.AirplaneHoleSide")

    def LoadHoleMeasurementAirplaneSide(self):
        """
        Special one off function to support black hole measurements

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Project.LoadHoleMeasurementSide()"
        self.__vexec(commandString)
        return self.getValue("v.AirplaneHoleSide")

    def ShowHoleMeasurementModelessDlg(self):
        """
        Special one off function to support black hole measurements

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ShowHoleMeasurementModelessDlg()"
        self.__vexec(commandString)

    def ComparePhotogrammetryProjects(self, filename1="", filename2="", doTrans=False, timeout=None):
        """
        Special test function to compare the state of 2 projects. This is used for internal GSI testing

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename1:
        :param filename2:
        :param timeout:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.jsonStr = ""
        commandString = f"CompareCPP(filename1={filename1}, filename2={filename2}, doTRans={doTrans})"

        self.photogrammetryProjectCompareStatsEvent = Event()

        self.__vexec(commandString)

        self.photogrammetryProjectCompareStatsEvent.wait(timeout=timeout)
        self.photogrammetryProjectCompareStatsEvent = None

        stats = self.photogrammetryProjectCompareStats

        if stats is None:
            raise Exception("A timeout occurred waiting for ComparePhotogrammetryProjects")

        return stats

    def RemoveAllScanPoints(self):
        """
        Removes all scan points form all pictures

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "RemoveAllScanPoints()"
        self.__vexec(commandStr)

    def RemoveDriveThroughPoints(
        self, geometryType="line", geometryName="centerline", design=True, excludeLabels="", testAngleDegrees=90
    ):
        """
        Remove un-seeable image points testing each 3D driver points from each camera pos against the geometry specified

        :requires: *V-STARS 4.9.4.0 or greater*

        :param geometryType:
        :param geometryName:
        :param design:
        :param excludeLabels:
        :param testAngleDegrees:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "RemoveDriveThroughPoints(geometryType={}, geometryName={}, design={}, excludeLabels={}, testAngleDegrees={})".format(
            geometryType, geometryName, design, excludeLabels, testAngleDegrees
        )
        self.__vexec(commandStr)

    def OutputXYZSpecial(
        self,
        outputFilename="bundleResults.csv",
        weakRayMin=8,
        badRayMin=5,
        weakSigmaMin=0.01,
        badSigmaMin=0.02,
        weakRayPercent=0.75,
        badRayPercent=0.5,
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param outputFilename:
        :param weakRayMin:
        :param badRayMin:
        :param weakSigmaMin:
        :weakRayPercent:
        :param badRayPercent:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "OutputXYZSpecial(outputFilename={}, weakRayMin = {}, badRayMin = {}, weakSigmaMin = {}, badSigmaMin = {}, weakRayPercent={}, badRayPercent ={})".format(
            outputFilename, weakRayMin, badRayMin, weakSigmaMin, badSigmaMin, weakRayPercent, badRayPercent
        )
        self.__vexec(commandStr)

    def Get3D(self, filename="", timeout=None) -> GCloud:
        """
        Gets a 3D cloud from V-STARS

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file
        :param timeout:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.cloud = None
        commandString = ("Get3D(filename={})").format(filename)

        self.cloudEvent = Event()

        self.__vexec(commandString)

        self.cloudEvent.wait(timeout=timeout)
        self.cloudEvent = None

        cloud = self.cloud

        if cloud is None:
            raise Exception("A timeout occurred waiting for Get3D")
        return cloud

    def GetPicture(self, index: int, timeout=None) -> GPicture:
        """
        Gets a picture from V-STARS

        :requires: *V-STARS 4.9.9.0 or greater*

        :param index: The picture index
        :param timeout:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.picture = None
        commandString = f"GetPicture(index={index})"

        self.pictureEvent = Event()

        self.__vexec(commandString)

        self.pictureEvent.wait(timeout=timeout)
        self.pictureEvent = None

        picture = self.picture

        if picture is None:
            raise Exception("A timeout occurred waiting for GetPicture")
        return picture

    def GetSelection(self, timeout=None) -> GCloud:
        """
        Gets the current selection as a 3D cloud from V-STARS

        :requires: *V-STARS 4.9.6.0 or greater*

        :param timeout:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.cloud = None
        commandString = "GetSelection()"

        self.cloudEvent = Event()

        self.__vexec(commandString)

        self.cloudEvent.wait(timeout=timeout)
        self.cloudEvent = None

        cloud = self.cloud

        if cloud is None:
            raise Exception("A timeout occurred waiting for Get3D")
        return cloud

    def TransformCurves(self, fillCloudName="", curveDriver="", step=1.0, design=True):
        """
        After cures have been scanned, this function will triangulation new control
        points for the curve. The curves have to exist in the current driver file for
        this function to work because the knots of the curves are copied from the driver
        step is in Millimeters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fillCloudName:
        :param curveDriver:
        :param step:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "TransformCurves(fillCloudName={}, curveDriver={}, step={}, design={})".format(
            fillCloudName, curveDriver, step, design
        )

        self.__vexec(commandString)

    def AddCurveGroup(self, design=False, curves=""):
        """
        Creates a curve *group*. Useful for curve scanning as groups of curve operate as a single entity

        :requires: *V-STARS 4.9.4.0 or greater*

        :param design: Set to True to specify design curves
        :param curves: Names of curves to group separated by spaces

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "AddCurveGroup(design={}, curves={})".format(design, curves)
        self.__vexec(commandString)

    def GroupContinuousCurves(self, design, tolerance):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param design:
        :param tolerance:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GroupContinuousCurves(design={}, tolerance={})".format(design, tolerance)
        self.__vexec(commandString)

    def ClearCurveGroups(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ClearCurveGroups()"

        self.__vexec(commandString)

    def TriangulateCurveEdges(
        self, fillCloudName="", curveDriver="", step=1.0, rejection=0.001, min_rays=5, design=True
    ):
        """
        After cures have been scanned, this function will triangulation edge points on
        a curve. The curves have to exist in the current driver file for
        this function to work because point labels for the edge points follow a
        pattern and the function must know the curves by name
        step is in Millimeters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fillCloudName:
        :param curveDriver:
        :param step:
        :param rejection:
        :param min_rays:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "TriangulateCurveEdges(fillCloudName={}, curveDriver={}, step={}, rejection={}, min_rays={}, design={})".format(
            fillCloudName, curveDriver, step, rejection, min_rays, design
        )

        self.__vexec(commandString)

    def ClearAllCurveScans(self):
        """
        Clears all pictures of curve scan point *(Assume label starts with "~")*

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ClearAllCurveScans()"

        self.__vexec(commandString)

    def ScanCurves(
        self, picture=-1, curveDriver="", step=1.0, nPixels=10, useDifferentialsForEdges=True, smoothing=0, design=True
    ):
        """

        scans the named picture for curves that appear in the driver file
        step is in Millimeters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param picture: The 1-based picture index
        :param curveDriver: 3D file containing curves to scan
        :param step:
        :param nPixels:
        :param useDifferentialsForEdges:
        :param smoothing:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ScanCurves(picture={}, curveDriver={}, step={}, nPixels={}, use_differentials_for_edges={}, smoothing={}, design={})".format(
            picture, curveDriver, step, nPixels, useDifferentialsForEdges, smoothing, design
        )

        self.__vexec(commandString)

    def RemoveCurveEdges(self, picture=-1):
        """
        Removes all "~" labeled points

        :requires: *V-STARS 4.9.4.0 or greater*

        :param picture:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "RemoveCurveEdges(picture={})".format(picture)

        self.__vexec(commandString)
        
    def CreateFeatureAidedSmartScale(self, filename = ""):
        """
        Create an FT4 scale.

        :requires: *V-STARS 4.9.5.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CreateFeatureAidedSmartScale(filename={})".format(filename)
        self.__vexec(commandString)

    def ProjectCurves(self, picture=-1, curveDriver="", step=1.0, design=True):
        """
        A debug function to project curves to images
        step is in Millimeters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param picture:
        :param curveDriver:
        :param step:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ProjectCurves(picture={}, curveDriver={}, step={}, design={})".format(
            picture, curveDriver, step, design
        )

        self.__vexec(commandString)

    def ShiftCurve(self, filename="", curveName="", direction="X", distance=0, design=True):
        """
        A function to shift a curve an amount along 1 of the axes

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param curveName:
        :param direction:
        :param distance:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ShiftCurve(filename={}, curveName={}, direction={}, distance={}, design={})".format(
            filename, curveName, direction, distance, design
        )

        self.__vexec(commandString)

    def ScanAndProcessCurves(
        self,
        fillCloud="",
        step=1.0,
        min_rays=5,
        rej_factor=3,
        rej_add=0.01,
        maxIters=5,
        nPixels=20,
        design=True,
        useDifferentialsForEdges=True,
        smoothing=0,
    ):
        """
        scans all pictures and triangulates curves and edges
        curves must exist in driver
        step is in Millimeters

        :requires: *V-STARS 4.9.4.0 or greater*

        :param fillCloud:
        :param step:
        :param min_rays:
        :param rej_factor:
        :param rej_add:
        :param maxIters:
        :param nPixels:
        :param design:
        :param useDifferentialsForEdges:
        :param smoothing:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.CurvesSucceeded = 0
        self.CurvesFailed = 0
        commandString = "ScanAndProcessCurves(fillCloud={}, step={}, min_rays={}, rej_factor={}, rej_add={}, maxIters={}, nPixels={}, design={}, use_differentials_for_edges={}, smoothing={})".format(
            fillCloud,
            step,
            min_rays,
            rej_factor,
            rej_add,
            maxIters,
            nPixels,
            design,
            useDifferentialsForEdges,
            smoothing,
        )

        self.__vexec(commandString)
        self.CurvesSucceeded = self.getValue("v.CurvesSucceeded")
        self.CurvesFailed = self.getValue("v.CurvesFailed")
        return self.CurvesSucceeded, self.CurvesFailed

    def ExportScannedCurvePoints(self, Cloud=""):
        """
        Exports all scanned curve points

        :requires: *V-STARS 4.9.4.0 or greater*

        :param Cloud:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ExportScannedCurvePoints(Cloud={})".format(Cloud)
        self.__vexec(commandString)
        return self.getValue("v.Success")

    def CreateBarrelAxis3DLine(self):
        """
        Creates a best fit line from all codes or alternatively all the curves' control points.
        This is used to create an approximate centerline to form a viewing vector for drive back

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CreateBarrelAxis3DLine()"
        self.__vexec(commandString)

    def GetCameraPosition(self, index: int = None, camera: str = None):
        """
        Gets the current Pan Tilt Roll positions

        :requires: *V-STARS 4.9.4.0 or greater*

        :param index: the 1 based camera index (Do not use this and camera)
        :param camera: The name of the camera (Do not use this and index)

        :return pan, tilt, roll: as a triplet of return values

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetCameraPosition("
        if index is not None:
            commandString += "index={},".format(index)
        if camera is not None:
            commandString += "camera={},".format(camera)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        pan = self.getValue("v.panPosition")
        tilt = self.getValue("v.tiltPosition")
        roll = self.getValue("v.rollPosition")
        return pan, tilt, roll

    def MoveCamera(
        self,
        pan: float = None,
        tilt: float = None,
        roll: float = None,
        camera: str = None,
        index: int = None,
        wait: bool = True,
        reset: bool = None,
        zero: bool = None,
    ):
        """
        Command to activate pan / tilt / roll motors

        :requires: *V-STARS 4.9.4.0 or greater*

        :param pan: Absolute pan location in degrees
        :param tilt: Absolute tilt location in degrees
        :param roll: Absolute roll location in degrees
        :param camera: Name of camera
        :param index: 1 based index of camera
        :param wait: if false command operated asynchronously
        :param reset:
        :param zero:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "MoveCamera("

        if pan is not None:
            commandString += "pan={},".format(pan)
        if tilt is not None:
            commandString += "tilt={},".format(tilt)
        if roll is not None:
            commandString += "roll={},".format(roll)
        if camera is not None:
            commandString += "camera={},".format(camera)
        if index is not None:
            commandString += "index={},".format(index)
        if reset is not None:
            commandString += "reset={},".format(reset)
        if zero is not None:
            commandString += "zero={},".format(zero)
        commandString += "wait={})".format(wait)
        self.__vexec(commandString)

    def PanTiltMoving(self):
        """
        Tests if any of the pan tilt roll are in motion

        :requires: *V-STARS 4.9.4.0 or greater*

        :return: True if any pan tilt rolls are in motion

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetPanTiltStatus()"
        self.__vexec(commandString)
        moving = self.getValue("v.panTiltMoving")
        return moving

    def PanTiltStatus(self):
        """
        Tests if any of the pan tilt roll are in motion or timed out

        :requires: *V-STARS 4.9.5.0 or greater*

        :return moving, timeout: as a pair of return values

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetPanTiltStatus()"
        self.__vexec(commandString)
        moving = self.getValue("v.panTiltMoving")
        timedOut = self.getValue("v.panTiltTimedOut")
        return moving, timedOut

    def PanTiltCommand(self, camera=None, index=None, command=None):
        """
        Sends a raw command to the specified camera PTR unit

        :requires: *V-STARS 4.9.4.0 or greater*

        :param camera: Name of camera
        :param index: 1 based index of camera
        :param command: raw command string

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "PanTiltCommand("

        if camera is not None:
            commandString += "camera={},".format(camera)
        if index is not None:
            commandString += "index={},".format(index)
        if command is not None:
            commandString += 'command="{} ",'.format(command)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)
        result = self.getValue("v.panTiltCommandResult")
        return result

    def DisableBundledPoints(self, bad=False, weak=False):
        """
        Disable the points from the last bundle that meet the specified criteria. After being disabled the bundle will need to be run again so those points are not included in the output.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param bad: If true, points categorized as bad will be disabled.
        :param weak: If true, points categorized as weak will be disabled.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "DisableBundledPoints(Bad={}, Weak={})".format(bad, weak)
        self.__vexec(commandString)

    def SaveProject(self):
        """
        Saves the current project to disk

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SaveProject()"
        self.__vexec(commandString)

    def WriteIniFileEntry(self, filename="", section="", entry="", value=""):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param section:
        :param entry:
        :param value:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "WriteIniFileEntry(filename={}, section={}, entry={}, value={})".format(
            filename, section, entry, value
        )
        self.__vexec(commandString)

    def WriteMTorresOVRFile(self, filename="", point1="", point2="", point3=""):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param point1:
        :param point2:
        :param point3:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "WriteMTorresOVRFile(filename={}, point1={}, point2={}, point3={})".format(
            filename, point1, point2, point3
        )
        self.__vexec(commandString)

    def ParseMTorresToolIniFile(self, filename="", tool=-1):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param tool:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ParseMTorresToolIniFile(filename={}, tool={})".format(filename, tool)
        self.__vexec(commandString)

    def SetSourceFile(self, filename: str = None, clear: bool = None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param clear:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SetSourceFile("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if clear is not None:
            commandString += "clear={},".format(clear)
        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def XYZTemplateFile(self, filename=None, on=None, off=None, active=None, deactivateAll=None):
        """
        Turns a 3D file either on or off as a template file. Template files are used in conjunction with the 3D.Update Feature Targets() command.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to update. If omitted, the current driver is updated
        :param on: When True the file is tagged as a template file.
        :param off: When True the file untagged as a template file.
        :param active: When True the template will be marked as active.
        :param deactivateAll:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "3D.Template File("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if on is not None:
            commandString += "on={},".format(on)
        if off is not None:
            commandString += "off={},".format(off)
        if active is not None:
            commandString += "active={},".format(active)
        if deactivateAll is not None:
            commandString += "deactivate all={},".format(deactivateAll)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def CopyDesignPointsToMeasured(self, filename="", destination="", increment=False):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param destination:
        :param increment:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CopyDesignPointsToMeasured(filename={}, destination={}, increment={})".format(
            filename, destination, increment
        )
        self.__vexec(commandString)

    def SetMTorresValues(
        self,
        unit=None,
        referenceFile=None,
        index=None,
        trimOffset=None,
        trimPrefix=None,
        mcd=None,
        mcdRequireNBlock=None,
        mcdname=None,
        flipDrillDwell=None,
    ):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param unit:
        :param referenceFile:
        :param index:
        :param trimOffset:
        :param trimPrefix:
        :param mcd:
        :param mcdRequireNBlock:
        :param mcdname:
        :param flipDrillDwell:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SetMTorresValues("
        if unit is not None:
            commandString += "unit={},".format(unit)
        if referenceFile is not None:
            commandString += "reference file={},".format(referenceFile)
        if index is not None:
            commandString += "index={},".format(index)
        if trimOffset is not None:
            commandString += "trim offset={},".format(trimOffset)
        if trimPrefix is not None:
            commandString += "trim prefix={},".format(trimPrefix)
        if mcd is not None:
            commandString += "mcd={},".format(mcd)
        if mcdRequireNBlock is not None:
            commandString += "mcdRequireNBlock={},".format(mcdRequireNBlock)
        if mcdname is not None:
            commandString += "mcdname={},".format(mcdname)
        if flipDrillDwell is not None:
            commandString += "flip drill dwell={},".format(flipDrillDwell)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def ImportMCDFile(
        self,
        filename: str = None,
        unit: int = None,
        flipDrillDwell: bool = None,
        mcdRequireNBlock: bool = None,
        mcdName: str = None,
    ):
        """

        :requires: *V-STARS 4.9.5.0 or greater*

        :param fileName:
        :param unit:
        :param flipDrillDwell:
        :param mcdRequireNBlock:
        :param mcdName:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ImportMCDFile("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if unit is not None:
            commandString += "unit={},".format(unit)
        if flipDrillDwell is not None:
            commandString += "flipDrillDwell={},".format(flipDrillDwell)
        if mcdRequireNBlock is not None:
            commandString += "mcdRequireNBlock={},".format(mcdRequireNBlock)
        if mcdName is not None:
            commandString += "mcdName={},".format(mcdName)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def CameraPairSettings(self, pair=-1):
        commandsStr = "CameraPairSettings(pair={})".format(pair)
        self.__vexec(commandsStr)


    def CameraSettings(
        self,
        camera: str = None,
        index: int = None,
        strobe: float = None,
        strobepw: int = None,
        shutter: int = None,
        gain: int = None,
        laser: bool = None,
        disableShutterCheck: bool = None,
        extSync: bool = None,
    ):
        """
        Sets the camera shutter speed, strobe power and gain.

        :requires: *V-STARS 4.9.4.0 or greater*

        **NOTE:** Do not specify by name and index in the same command or an error will occur.

        :param camera: The name of the camera to set. Must be part of the opened project. If no camera parameter is specified, all cameras in the project are set to the specified settings.
        :param index: The index (1 to n) of the camera to set. For example, if there are 4 cameras in the project, the index values would be 1,2,3,4. The camera indexes are determined by the order they are listed in the project (first in list = 1).
        :param strobe: The camera strobe power. Valid values are decimal numbers from 0 (lowest power) to 21 (highest power). Each increase of 1 in the strobe value increases strobe power by about 26%. An increase in the strobe value of 3 increases the strobe power by a factor of 2. **NOTE:** Some strobes will not fire at power levels of 0 or 1.
        :param strobepw: The time in us of the signal sent from the DynaMo camera to the strobe hardware
        :param shutter: The camera shutter speed in milliseconds. Valid values are integers greater than 3. However, a shutter speed of at least 8 milliseconds is recommended in single-camera applications and at least 12 milliseconds is recommended for multiple-camera applications to ensure strobe synchronization.
        :param gain: The camera gain. Valid values are (0,1,2,3,4). 0 is the lowest gain and is the standard value. Each higher number increases the gain by a factor of 2. Gain settings of 3 and 4 are not recommended..
        :param laser: True turns the lasers on, False turns the laser off.
        :param disableShutterCheck:
        :param extSync: Enable the S mode external sync

        :examples:

        .. code:: python

            # Sets the gain to 2 (4x as bright as standard)
            # and the shutter speed to 10 milliseconds for all cameras in the project.
            V.CameraSettings( gain = 2, shutter = 10 )

            #Sets the strobe power for the named camera to 9
            V.CameraSettings(camera=INCA3 sn0077 21mm 2005-10-20, strobe=9)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CameraSettings("
        if camera is not None:
            commandString += "camera={},".format(camera)
        if index is not None:
            commandString += "index={},".format(index)
        if strobe is not None:
            commandString += "strobe={},".format(strobe)
        if strobepw is not None:
            commandString += "strobepw={},".format(strobepw)
        if disableShutterCheck is not None:
            commandString += "disable shutter check={},".format(disableShutterCheck)
        if shutter is not None:
            commandString += "shutter={},".format(shutter)
        if gain is not None:
            commandString += "gain={},".format(gain)
        if laser is not None:
            commandString += "laser={},".format(laser)
        if extSync is not None:
            commandString += "ext sync={},".format(extSync)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def CloseAllPictures(self):
        """
        Closes all currently displayed pictures

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CloseAllPictures()"
        self.__vexec(commandString)

    def ScriptWait(self, line=None, data=None):
        """
        Pauses the script until a **ScriptContinue** command is sent

        :requires: *V-STARS 4.9.4.0 or greater*

        :param line:
        :parma data:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ScriptWait("
        if line is not None:
            commandString += "line={},".format(line)
        if data is not None:
            commandString += "data={},".format(data)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def ScriptContinue(self, line=None, data=None):
        """
        Continues a script after a call to **ScriptWait**

        :requires: *V-STARS 4.9.4.0 or greater*

        :param line:
        :param data:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "ScriptContinue("
        if line is not None:
            commandString += "line={},".format(line)
        if data is not None:
            commandString += "data={},".format(data)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SignalUSB9481(self, line: int):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param line:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SignalUSB9481(line={})".format(line)
        self.__vexec(commandString)

    def SignalUSB6525(self, data: int):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param data:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SignalUSB6525(data={})".format(data)
        self.__vexec(commandString)

    def GetCameraStatus(self, index: int = None, camera: str = None):
        """
        Tests the picture status.

        :requires: *V-STARS 4.9.4.0 or greater*

        :returns: takingPicture, connected, temperature (C)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetCameraStatus("
        if index is not None:
            commandString += "index={},".format(index)
        if camera is not None:
            commandString += "camera={},".format(camera)
        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)
        takingPictures = self.getValue("v.cameraTakingPicture")
        connected = self.getValue("v.cameraConnected")
        temperature = self.getValue("v.cameraTemperature")
        return takingPictures, connected, temperature

    def CamerasTakingPictures(self):
        """
        Tests the picture taking state

        :requires: *V-STARS 4.9.4.0 or greater*

        :returns: True if cameras are currently taking pictures

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetCameraStatus()"
        self.__vexec(commandString)
        takingPictures = self.getValue("v.cameraTakingPicture")
        return takingPictures

    def CheckPictureInformation(
        self,
        iso: str = None,
        strobe: str = None,
        fnumber: str = None,
        exposure: str = None,
        exposureUS: str = None,
        whiteBalance: str = None,
    ):
        """
        Command to verify settings in the image header.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param iso:
        :param strobe:
        :param fnumber:
        :param exposure: Exposure in milliseconds
        :param exposureUS: Exposure in microseconds
        :param white balance:

        Exposure and exposureUS can not both be set. An error will be returned.

        A value or range that is acceptable.
        iso = "200"
        iso = "400-800"
        strobe = 3-9"
        fnumber = "5.6"
        exposure = "20-50"
        whiteBalance = "AUTO"

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CheckPictureInformation("
        if iso is not None:
            commandString += "iso={},".format(iso)
        if strobe is not None:
            commandString += "strobe={},".format(strobe)
        if fnumber is not None:
            commandString += "fnumber={},".format(fnumber)
        if exposure is not None:
            commandString += "exposure={},".format(exposure)
        if exposureUS is not None:
            commandString += "exposureUS={},".format(exposureUS)
        if whiteBalance is not None:
            commandString += "white balance={},".format(whiteBalance)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def CameraBackup(self, camera=None, index=None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param camera:
        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CameraBackup("
        if camera is not None:
            commandString += "camera={},".format(camera)
        if index is not None:
            commandString += "index={},".format(index)
        commandString = commandString.rstrip(',')
        commandString += ")"

        self.__vexec(commandString)

    def CameraRestoreBackup(self, camera=None, index=None):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param camera:
        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CameraRestoreBackup("
        if camera is not None:
            commandString += "camera={},".format(camera)
        if index is not None:
            commandString += "index={},".format(index)
        commandString = commandString.rstrip(",")
        commandString += ")"

        self.__vexec(commandString)

    def CopyCameraParameters(self, cameraPath=None):
        """
        Copy the calibration parameters from a set of cameras to the current projects cameras.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param cameraPath: The path to the source cameras.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CopyCameraParameters("

        if cameraPath is not None:
            commandString += 'camera path="{}"'.format(cameraPath)

        commandString += ")"

        self.__vexec(commandString)

    def AutomaticCameraImport(self, enable=None):
        """
        Enable the automatic importing of DynaMo camera files when opening a project. This setting is not save across sessions.

        :requires *V-STARS 4.9.4.0 or greater*

        :param enable: A required parameter. True to enable automatic importing, False to disable.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "AutomaticCameraImport("

        if enable is not None:
            commandString += 'enable="{}"'.format(enable)

        commandString += ")"

        self.__vexec(commandString)

    def CheckImagePixel(self,
        pictureIndex: str = None,
        cameraIndex: str = None,
        row: int = None,
        column: int = None
    ):
        """

        :requires: *V-STARS 4.9.6.0 or greater*

        :param pictureIndex: Index of the S picture
        :param cameraIndex: Index of the M camera, error if not in m mode
        :param row:
        :param column:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "CheckImagePixel("
        if pictureIndex is not None:
            commandString += "picture index={},".format(pictureIndex)
        if cameraIndex is not None:
            commandString += "camera index={},".format(cameraIndex)
        if row is not None:
            commandString += "row={},".format(row)
        if column is not None:
            commandString += "column={},".format(column)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SaveJpegFile(self, filename=None, index=-1):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:
        :param index:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SaveJpegFile("

        if filename is not None:
            commandString += "filename={},".format(filename)

        commandString += "index={})".format(index)

        self.__vexec(commandString)

    def CurvesToEdges(self, step=1.0, design=False):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param step:
        :param design:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "CurvesToEdges(step={}, design={})".format(step, design)
        self.__vexec(commandString)

    def XYZAlignmentPlaneLinePoint(
        self,
        filename="",
        plane="",
        line="",
        point="",
        lineOrientation="",
        planeOrientation="",
        planeValue=0,
        lineValue=0,
        pointValue=0,
        new="",
    ):
        """

        Performs an alignment using a specified plane, line and point.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The 3D file on which the alignment is performed. Must be part of the opened project. If no filename parameter is present or the filename parameter has no value, the current Driver file is used.
        :param plane: The name fo the plane.
        :param line: The name of the line.
        :param point: The name of the point.
        :param lineOrientation: The axis the line will represent. Must be one of the following: "X", "Y" or "Z".
        :param planeOrientation: The plane the axis defined by Line orientation will lie in. Must be one of the following: "XY", "XZ" or "YZ". If "X" is chosen for the Line orientation then Plane orientation must be "XY" or "XZ". If "Y" is chosen for the Line orientation then the Plane orientation must be "XY" or "YZ". If "Z" is chosen for the Line orientation then the Plane orientation must be "XZ" or "YZ".
        :param planeValue: The plane offset from the new origin.
        :param lineValue: The line offset from the new origin in the plane.
        :param pointValue: The point offset from the new origin along the axis.
        :param new: The name of the new coordinate system.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "3D.Alignment.Plane Line Point(filename={}, plane={}, line={}, point={}, line orientation={}, plane orientation={}, plane value={}, line value={}, point value={}, new={})".format(
            filename, plane, line, point, lineOrientation, planeOrientation, planeValue, lineValue, pointValue, new
        )
        self.__vexec(commandString)

    def ExportPointDirection(self, filename=""):
        """
        A function to export approximate point ijk

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "GetDriverPointingVectors(filename={})".format(filename)
        self.__vexec(commandString)

    def SaveProbeLogFile(self, filename=""):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "SaveProbeLogFile(filename={})".format(filename)
        self.__vexec(commandsStr)

    def SetDreamMode(self, on=True):
        """
        Function to turn on and off Dream Mode

        :requires: *V-STARS 4.9.4.0 or greater*

        :param on: True for on False for off

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "SetDreamMode(on={})".format(on)
        self.__vexec(commandStr)

    def SModeDream(self, dream="", pictures="", rejection=2, allow_single=False):
        """

        For tracking an object using DREAM algorithm in S Mode

        :requires: *V-STARS 4.9.7.27 or greater*

        :param dream: The name of the object 
        :param pictures: A list of picture indexes to perform calculation
        :param rejection: The rejection limit in microns

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandsStr = "SModeDream(dream={}, pictures={}, rejection={}, allow_single={})".format(dream, pictures, rejection, allow_single)
        self.__vexec(commandsStr)

    def SetDreamValues(self, probeOffset=None, probePrefix=None):
        """

        :requires: *V-STARS 4.9.5.0 or greater*

        :param probeOffset:
        :param probePrefix:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SetDreamValues("
        if probeOffset is not None:
            commandString += "probe offset={},".format(probeOffset)
        if probePrefix is not None:
            commandString += "probe prefix={},".format(probePrefix)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SelectFolder(self):
        """

        :requires: *V-STARS 4.9.4.0 or greater*

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandStr = "SelectFolder()"
        self.__vexec(commandStr)
        rv = self.getValue("v.selectedPath")
        return rv

    def SaveAsTemplateProject(self, name=""):
        """
        Saves the current project as a template project

        :requires: *V-STARS 4.9.4.0 or greater*

        :param name: The name for the template project (Should not already exist)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """

        commandStr = "SaveAsTemplateProject(name={})".format(name)
        self.__vexec(commandStr)

    def autoMatchNoBackToBack(self):
        """
        Experimental function

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        self.PicturesEnable(pictures="all")
        self.XYZDelete(filename="part1")
        self.XYZDelete(filename="part2")
        self.EnableNuggets("all")

        for i in range(0, 2):
            self.XYZDriverFile(off=True)
            self.ProjectAutomeasure(begin=True, close=True)
            # self.FFTFind()
            self.SelectPointsByLabel(labels="CODE*")
            self.UnSelectPlanesByLabel(labels="CODE209 CODE210 CODE211 CODE212 CODE213 CODE214 CODE215 CODE216")
            self.SolidsPlane(name="CodePlane")

            selectionNumberFound = 0
            self.UnSelectPointsAll()
            for code in range(1, 199):
                codeStr = "CODE{}".format(code)
                self.SelectPointsByLabel(labels=codeStr)
                selectionNumberFound = self.getValue("v.selectionNumberFound")
                if selectionNumberFound > 0:
                    break

            nuggetB = "NUGGET{}_B".format(code)
            nuggetC = "NUGGET{}_C".format(code)

            self.UnSelectPointsAll()
            self.SelectPointsByLabel(labels="{} {} {}".format(codeStr, nuggetB, nuggetC))

            self.SolidsProject(plane="CodePlane")

            anchorPt = "PROJ_CODE{}".format(code)
            axisPt = "PROJ_{}".format(nuggetC)
            planePt = "PROJ_{}".format(nuggetB)

            self.XYZAlignmentAxis(anchor=anchorPt, axis=axisPt, plane=planePt)

            if i == 0:
                self.SelectPointsAll()
                self.UnSelectPointsLessThan(z=-1000)
                self.RelabelSelectedPoints(prefix="NOT_TIE")

            if i == 1:
                self.SelectPointsByLabel(labels="TARGET*")
                self.UnSelectPointsGreaterThan(z=-1000)
                self.RelabelSelectedPoints(prefix="TIE")

            pictureCount = self.GetNumberOfPictures()

            if i == 0:
                for j in range(0, pictureCount):
                    index = j + 1
                    if self.PictureIsResected(picture=index):
                        self.PicturesDisable(index)

            nameStr = "part{}".format(i + 1)
            self.Rename3D(newName=nameStr)

        self.PatternRelabel(
            filename="part1", pattern="part2", distanceMatch=3, relabelCloseness=3, onlyAutomatched=True
        )

        self.XYZImportToDesign(design="part1")

        self.XYZAlignmentQuick(automaticRejection=True, holdScale=False, begin=True, close=True)

        self.PicturesEnable(pictures="all")
        self.ProjectAutomeasure(begin=True, close=True)

        self.UnSelectPointsAll()
        self.SelectPointsAll(design=True)
        self.SelectPlanesAll(design=True)
        self.DeleteSelection()
        self.SelectPointsByLabel(labels="NOT*")
        self.RelabelSelectedPoints(prefix="TARGET")

    def SolidsLine(self, name="", rejection=None, createTemplate=None):
        """
        Does a best-fit line on the currently selected points using the parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param name: The name given to the best-fit line. If no name is specified, a default name will be assigned (typically NewLine1,2,3, etc.)
        :param rejection: The rejection limit for the Best-fit line. If Rejection is not specified, no rejection limit is used.
        :param createTemplate: If present causes a construction template to be made for the line.

        Example:

        .. code:: python

            SelectPointsByLabel(labels = TOP*)
            SolidsLine(rejection=.01, Name="TOP")

        Return Values:

        :requires: *V-STARS 4.9.5-1 or greater*

        **v.lineX**
        **v.lineY**
        **v.lineZ**
        **v.lineI**
        **v.lineJ**
        **v.lineK**
        **v.lineX1**
        **v.lineY1**
        **v.lineZ1**
        **v.lineX2**
        **v.lineY2**
        **v.lineZ2**
        **v.lineLength**
        **v.lineRMS**
        **v.lineAccepted**
        **v.lineRejected**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Solids.Line("
        if len(name) > 0:
            commandString += "name={},".format(name)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if createTemplate is not None:
            commandString += "create template={},".format(createTemplate)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsPlane(self, name="", rejection=None, createTemplate=None):
        """
        Does a best-fit plane on the currently selected points using the parameters.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param name: The name given to the best-fit plane. If no name is specified, a default name will be assigned (typically NewPlane1,2,3, etc.)
        :param rejection: The rejection limit for the Best-fit plane. If Rejection is not specified, no rejection limit is used.
        :param createTemplate: If present causes a construction template to be made for the plane.

        :example:

        .. code:: python

            SelectPointsByLabel(labels = TOP*)
            Solids.Plane(rejection=.01, Name="TOP")

        Return Values:

        :requires: *V-STARS 4.9.5-1 or greater*

        **v.planeA**
        **v.planeB**
        **v.planeC**
        **v.planeD**
        **v.planeRMS**
        **v.planeAccepted**
        **v.planeRejected**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Solids.Plane("
        if len(name) > 0:
            commandString += "name={},".format(name)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if createTemplate is not None:
            commandString += "create template={}".format(createTemplate)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsCircle(self, name="", rejection=None, createTemplate=None, center=""):
        """

        Does a best-fit circle on the currently selected points using the parameters.

        :requires: *V-STARS 4.9.4.1 or greater*

        :param name: The name given to the best-fit circle. If no name is specified, a default name will be assigned (typically NewCircle1,2,3, etc.)
        :param rejection: The rejection limit for the Best-fit circle. If Rejection is not specified, no rejection limit is used.
        :param createTemplate: If present causes a construction template to be made for the circle.
        :param center:  The name given to the center point of the circle. The center point is added to the currently selected 3D file. If no name is specified, the center point is not created.

        :examples:

        .. code:: python

            SelectPointsByLabel(labels = IN*)
            SolidsCircle(rejection=.01, Name="INNER", Center="C-INNER")
            #Uses all points starting with IN and calls it 'INNER" and adds a center point called 'C-INNER'

            UnSelectPointsAll()
            SelectPointsByLabel(labels = Out*)
            SolidsCircle(rejection=.01, Name="OUTER", Center="C-Outer")
            #Uses all points starting with OUT (notice case does not matter - all point labels are always all uppercase) and calls it 'OUTER" and adds a center point called 'C-OUTER' (the case will be converted to uppercase)

            UnSelectPointsAll()
            SelectPointsByLabel(labels = In* Out*)
            SolidsCircle(rejection=.1, Name="BOTH")
            #Uses both the 'Inner' and 'Outer' points, has a higher rejection limit, and calls the resulting circle 'BOTH'. No center point is made.

        Return Values:

        :requires: *V-STARS 4.9.5-1 or greater*

        **v.circleA**
        **v.circleB**
        **v.circleC**
        **v.circleD**
        **v.circleX**
        **v.circleY**
        **v.circleZ**
        **v.circleRadius**
        **v.circleRMS**
        **v.circleInPlaneRMS**
        **v.circleOutPlaneRMS**
        **v.circleAccepted**
        **v.circleRejected**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Solids.Circle("
        if len(name) > 0:
            commandString += "name={},".format(name)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if createTemplate is not None:
            commandString += "create template={}".format(createTemplate)
        if len(center) > 0:
            commandString += "center={},".format(center)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsSphere(self, name="", rejection=None, createTemplate=None, center=""):
        """

        Does a best-fit sphere on the currently selected points using the parameters.

        :requires: *V-STARS 4.9.4.1 or greater*

        :param rejection: The rejection limit for the Best-fit circle. If Rejection is not specified, no rejection limit is used.
        :param name: The name given to the best-fit circle. If no name is specified, a default name will be assigned (typically NewCircle1,2,3, etc.)
        :param createTemplate: If present causes a construction template to be made for the sphere.
        :param center:  The name given to the center point of the sphere. The center point is added to the currently selected 3D file. If no name is specified, the center point is not created.

        :examples:

        .. code:: python

            SelectPointsByLabel(labels = IN*)
            SolidsSphere(rejection=.01, Name="INNER", Center="C-INNER")
            #Uses all points starting with IN and calls it 'INNER" and adds a center point called 'C-INNER'

            UnSelectPointsAll()
            SelectPointsByLabel(labels = Out*)
            SolidsSphere(rejection=.01, Name="OUTER", Center="C-Outer")
            #Uses all points starting with OUT (notice case does not matter - all point labels are always all uppercase) and calls it 'OUTER" and adds a center point called 'C-OUTER' (the case will be converted to uppercase)

            UnSelectPointsAll()
            SelectPointsByLabel(labels = In* Out*)
            SolidsSphere(rejection=.1, Name="BOTH")
            #Uses both the 'Inner' and 'Outer' points, has a higher rejection limit, and calls the resulting sphere 'BOTH'. No center point is made.

        Return Values:

        :requires: *V-STARS 4.9.5-1 or greater*

        **v.SphereX**
        **v.SphereY**
        **v.SphereZ**
        **v.SphereRadius**
        **v.SphereRMS**
        **v.SphereAccepted**
        **v.SphereRejected**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Solids.Sphere("
        if len(name) > 0:
            commandString += "name={},".format(name)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if createTemplate is not None:
            commandString += "create template={}".format(createTemplate)
        if len(center) > 0:
            commandString += "center={},".format(center)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsCylinder(self, name="", rejection=None, createTemplate=None, center=""):
        """

        Does a best-fit circle on the currently selected points using the parameters.

        :requires: *V-STARS 4.9.4.1 or greater*

        :param rejection: The rejection limit for the Best-fit circle. If Rejection is not specified, no rejection limit is used.
        :param name: The name given to the best-fit circle. If no name is specified, a default name will be assigned (typically NewCircle1,2,3, etc.)
        :param createTemplate: If present causes a construction template to be made for the cylinder.
        :param center: The name given to the center line of the cylinder. The center line is added to the currently selected 3D file. If no name is specified, the center line is not created.

        :examples:

        .. code:: python

            SelectPointsByLabel(labels = IN*)
            SolidsCircle(rejection=.01, Name="INNER", Center="C-INNER")
            #Uses all points starting with IN and calls it 'INNER" and adds a center point called 'C-INNER'

            UnSelectPointsAll()
            SelectPointsByLabel(labels = Out*)
            SolidsCircle(rejection=.01, Name="OUTER", Center="C-Outer")
            #Uses all points starting with OUT (notice case does not matter - all point labels are always all uppercase) and calls it 'OUTER" and adds a center point called 'C-OUTER' (the case will be converted to uppercase)

            UnSelectPointsAll()
            SelectPointsByLabel(labels = In* Out*)
            SolidsCircle(rejection=.1, Name="BOTH")
            #Uses both the 'Inner' and 'Outer' points, has a higher rejection limit, and calls the resulting circle 'BOTH'. No center point is made.

        Return Values:

        :requires: *V-STARS 4.9.5-1 or greater*

        **v.cylinderX**
        **v.cylinderY**
        **v.cylinderZ**
        **v.cylinderI**
        **v.cylinderJ**
        **v.cylinderK**
        **v.cylinderX1**
        **v.cylinderY1**
        **v.cylinderZ1**
        **v.cylinderX2**
        **v.cylinderY2**
        **v.cylinderZ2**
        **v.cylinderRadius**
        **v.cylinderLength**
        **v.cylinderRMS**
        **v.cylinderAccepted**
        **v.cylinderRejected**

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "Solids.Cylinder("
        if len(name) > 0:
            commandString += "name={},".format(name)
        if rejection is not None:
            commandString += "rejection={},".format(rejection)
        if createTemplate is not None:
            commandString += "create template={}".format(createTemplate)
        if len(center) > 0:
            commandString += "center={},".format(center)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsOffset(
        self,
        filename: str = None,
        name: str = None,
        design: bool = None,
        objectType: str = None,
        compensationPoint: str = None,
        offsetValue: float = None,
        deleteComponents: bool = None,
        deleteMeasurements: bool = None,
        prefix: str = None,
        postfix: str = None,
    ):
        """
        Shifts an object in 3D by a given offset. (Currently only supports planes)

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file in which to create a new point.  If omitted, the current driver is used.
        :param name: The name of the object to offset
        :param objectType: The type of object being offset. eg. object=plane
        :param design: If present, the object being offset is from design data.
        :param compensationPoint: The name of a 3D point that defines the direction for the offset to occur.  If omitted, the offset is in the direction of the positive normal of the object.
        :parma offsetValue: The amount to offset the object expressed in the units of the project.
        :param deleteComponents: If present the original object is removed from the 3D file.
        :param prefix: The label prefix to give the offset object.
        :param postfix: The label suffix to give the offset object.

        **WARNING!**: Only specify one of the above 2 parameters, or the result will be unpredictable.

        Example:

        .. code:: python

            SolidsOffset(name="BF_PLANE", object=plane, offset value=120, compensation point=CODE1, postfix="_OFFSET")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "Solids.Offset("
        if filename is not None:
            commandString += "filename={},".format(filename)
        if name is not None:
            commandString += "name={},".format(name)
        if design is not None:
            commandString += "design={},".format(design)
        if objectType is not None:
            commandString += "object={},".format(objectType)
        if compensationPoint is not None:
            commandString += "compensation point={},".format(compensationPoint)
        if offsetValue is not None:
            commandString += "offset value={},".format(offsetValue)
        if deleteComponents is not None:
            commandString += "delete components={},".format(deleteComponents)
        if deleteMeasurements is not None:
            commandString += "delete measurements={},".format(deleteMeasurements)
        if prefix is not None:
            commandString += "prefix={},".format(prefix)
        if postfix is not None:
            commandString += "postfix={},".format(postfix)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsDelete(
        self,
        filename: str = None,
        all: bool = True,
        planes: bool = False,
        lines: bool = False,
        circles: bool = False,
        spheres: bool = False,
        cylinders: bool = False,
        name: str = None,
        design: bool = False,
    ):
        """
        Deletes all solids objects from the specified 3D file.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param filename: The name of the 3D file to use. It must exist in the current project. If no filename is specified, the driver file is used.
        :param all: If True all solids objects will be deleted. Default True.
        :param planes: If True all planes will be deleted. Default False, if True all will be set False.
        :param lines: If True all lines will be deleted. Default False, if True all will be set False.
        :param circles: If True all circles will be deleted. Default False, if True all will be set False.
        :param spheres: If True all spheres will be deleted. Default False, if True all will be set False.
        :param cylinders: If True all cylinders will be deleted. Default False, if True all will be set False.
        :param name: If set all objects matching the name (wildcard) will be deleted
        :param design: If true, design solids objects will be deleted.

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        commandString = "SolidsDelete("
        if filename is not None:
            commandString += "filename={},".format(filename)

        if name is not None:
            commandString += "name={},".format(name)

        if planes or lines or circles or spheres or cylinders:
            all = False

        commandString += "all={}, planes={}, lines={}, circles={}, spheres={}, cylinders={}, design={})".format(
            all, planes, lines, circles, spheres, cylinders, design
        )

        self.__vexec(commandString)

    def SolidsProject(
        self,
        plane: str = None,
        line: str = None,
        circle: str = None,
        sphere: str = None,
        cylinder: str = None,
        curve: str = None,
        surface: str = None,
        design: bool = False,
        prefix: str = None,
        postfix: str = None,
        inPlane: bool = False,
    ):
        """
        Function to project the currently selected point(s) to the specified plane or circle, as passed in as a parameter to this command. The plane or circle must exist in the 3D file within which the select point(s) also exist.

        :requires: *V-STARS 4.9.4.0 or greater*

        :param plane: The name of the plane to consider for the point(s) projection.
        :param line: The name of the line to consider for the point(s) projection.
        :param circle: The name of the circle to consider for the point(s) projection.
        :param sphere: The name of the circle to consider for the point(s) projection.
        :param cylinder: The name of the circle to consider for the point(s) projection.
        :param curve: The name of the circle to consider for the point(s) projection.
        :param surface: The name of the circle to consider for the point(s) projection.

        **WARNING!:** Only specify one of the above parameters, or the result will be unpredictable.

        :param design: If True will look for the design object specified

        :param prefix: The label prefix to give the projected point(s).
        :param postfix: The label suffix to give the projected point(s).

        **WARNING!:** Only specify one of the above 2 parameters, or the result will be unpredictable.

        :param inPlane: In the case of a circle projection, the projection direction will be parallel to the plane of the circle, and hence fall on a cylinder that passes through the circle. The default is False.

        :example:

        .. code:: python

            SelectPointsByLabel(labels = POINT*)
            Solids.Project(circle="CIRCLE1", prefix="C_", in plane=true)

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        designStr = ""
        if design:
            designStr = "design "

        commandString = "Solids.Project("
        if plane is not None:
            commandString += "{}plane={},".format(designStr, plane)
        if line is not None:
            commandString += "{}line={},".format(designStr, line)
        if circle is not None:
            commandString += "{}circle={},".format(designStr, circle)
        if sphere is not None:
            commandString += "{}sphere={},".format(designStr, sphere)
        if curve is not None:
            commandString += "{}curve={},".format(designStr, curve)
        if surface is not None:
            commandString += "{}surface={},".format(designStr, surface)
        if prefix is not None:
            commandString += "prefix={},".format(prefix)
        if postfix is not None:
            commandString += "postfix={},".format(postfix)
        commandString += "in plane={})".format(inPlane)
        self.__vexec(commandString)

    def SolidsMeasure(
        self,
        plane: str = None,
        line: str = None,
        circle: str = None,
        sphere: str = None,
        cylinder: str = None,
        curve: str = None,
        surface: str = None,
        design: bool = False,
    ):
        """
        :requires: *V-STARS 4.9.4.0 or greater*

        Function to measure the currently selected point(s) to the specified plane or circle or cylinder, as passed in as a parameter to this command. The plane, circle or cylinder must exist in the 3D file within which the select point(s) also exist.

        :param plane: The name of the plane to consider for the point(s) measurement.
        :param line: The name of the line to consider for the point(s) measurement.
        :param circle: The name of the circle to consider for the point(s) measurement.
        :param sphere: The name of the sphere to consider for the point(s) measurement.
        :param cylinder: The name of the cylinder to consider for the point(s) measurement.
        :param curve: The name of the curve to consider for the point(s) measurement.
        :param surface: The name of the surface to consider for the point(s) measurement.

        **WARNING!:** Only specify one of the above parameters, or the result will be unpredictable.

        :param design: If True will look for the design object specified

        :example:

        .. code:: python

            SelectPointsByLabel(labels = POINT*)
            Solids.Measure(circle="CIRCLE1")

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        designStr = ""
        if design:
            designStr = "design "

        commandString = "Solids.Measure("
        if plane is not None:
            commandString += "{}plane={},".format(designStr, plane)
        if line is not None:
            commandString += "{}line={},".format(designStr, line)
        if circle is not None:
            commandString += "{}circle={},".format(designStr, circle)
        if sphere is not None:
            commandString += "{}sphere={},".format(designStr, sphere)
        if curve is not None:
            commandString += "{}curve={},".format(designStr, curve)
        if surface is not None:
            commandString += "{}surface={},".format(designStr, surface)
        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsPlanePositiveDirection(
        self,
        filename: str = None,
        plane: str = None,
        point: str = None,
        pointi: float = None,
        pointj: float = None,
        pointk: float = None,
        negativeDirection: bool = None
    ):
        """
        :requires: *V-STARS 4.9.6.0 or greater*

        Ensure the planes positive direction is towards to point specified.

        :param filename:
        :param plane:
        :param point:
        :param pointi:
        :param pointj:
        :param pointk:
        :param negativeDirection:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "PlanePositiveDirection("

        if filename is not None:
            commandString += f"filename={filename},"
        if plane is not None:
            commandString += f"plane={plane},"
        if point is not None:
            commandString += f"point={point},"
        if pointi is not None:
            commandString += f"pointi={pointi},"
        if pointj is not None:
            commandString += f"pointj={pointj},"
        if pointk is not None:
            commandString += f"pointk={pointk},"
        if negativeDirection is not None:
            commandString += f"negative={negativeDirection},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def SolidsLinePositiveDirection(
        self,
        filename: str = None,
        line: str = None,
        point1: str = None,
        point2: str = None
    ):
        """
        :requires: *V-STARS 4.9.6.0 or greater*

        Ensure the lines positive direction follows the vector of the two points specified.

        :param filename:
        :param line:
        :param point1:
        :param point2:

        :raises: Exception see `Error Handling <error_handling.html>`_ for details
        """
        commandString = "SolidsLinePositiveDirection("

        if filename is not None:
            commandString += f"filename={filename},"
        if line is not None:
            commandString += f"line={line},"
        if point1 is not None:
            commandString += f"point1={point1},"
        if point2 is not None:
            commandString += f"point2={point2},"

        commandString = commandString.rstrip(",")
        commandString += ")"
        self.__vexec(commandString)

    def GetScaleBars(
            self,
            timeout=None,
        ):
        """
        Gets the scalebars from the project

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """
        # the scaleInfo is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.scaleBarsEvent = Event()

        self.__vexec("GetScaleBars()")

        # the scaleInfo is only returned on 4.9.4-1 or greater
        if self.CheckVstarsVersion(40090040010000):
            self.scaleBarsEvent.wait(timeout=timeout)

            scaleBars = self.scaleBars
            self.scaleBarsEvent = None

            if scaleBars is None:
                raise Exception("A timeout occurred waiting for the ScaleBars")

            return scaleBars

    def initMTorres(self, mtorres_communication):
        """
        Initializes MTorres in Vstars

        :raises: Exception see `Error Handling <error_handling.html>`_ for details

        """

        if mtorres_communication == MTorresCommunication.USB9481:
            self.__vexec("initMTorres(type=usb9481)")
        elif mtorres_communication == MTorresCommunication.USB6525:
            self.__vexec("initMTorres(type=usb6525)")

class VSTARSTester:
    def __init__(self, templateName, address="localhost", port=1210):
        self.V = VSTARS()
        self.V.init(address, port)
        self.templateName = templateName
        self.resultStr = ""
        self.resultStr2 = ""

    def compareArchives(self, archiveName="", config="release", sourcePath=""):
        """
        Does a byte by byte comparison of 2 files
        This is used for internal testing

        archiveName the name of a files to compare. Both files must have the same name

        One file exists in the \\standards folder under the current project folder
        The other file exists in the "\\sourcePath" folder under the current project folder

        The sourcePath can be left blank in which case the second file is assumed to be in the project folder

        """
        # tmp = platform.processor()
        # tmp2 = tmp.replace(' ', '')
        # processor = tmp2.replace(',', '')

        proj_path = Path(self.V.ProjectPath())
        standard_file = proj_path / "standard" / config / archiveName

        if len(sourcePath) > 0:
            proj_path = proj_path / sourcePath

        cur_results = proj_path / archiveName

        try:
            f1 = open(standard_file, "rb")
            f2 = open(cur_results, "rb")
        except IOError:
            return False

        bytes1 = f1.read()
        bytes2 = f2.read()

        l1 = len(bytes1)
        l2 = len(bytes2)

        if l1 != l2:
            return False

        for i in range(0, l1):
            if bytes1[i] != bytes2[i]:
                return False

        return True

    def compareOldPictureFormat(self, archiveName="", config="release", sourcePath=""):
        """
        Compare 2 x Pictures that are stored in a specific text format
        This is used for internal testing

        archiveName the name of a files to compare. Both files must have the same name

        One file exists in the \\standards folder under the current project folder
        The other file exists in the "\\sourcePath" folder under the current project folder

        The sourcePath can be left blank in which case the second file is assumed to be in the project folder

        """
        # tmp = platform.processor()
        # tmp2 = tmp.replace(' ', '')
        # processor = tmp2.replace(',', '')

        proj_path = Path(self.V.ProjectPath())
        standard_file = proj_path / "standard" / config / archiveName

        if len(sourcePath) > 0:
            proj_path = proj_path / sourcePath

        cur_results = proj_path / archiveName

        try:
            with open(standard_file) as f:
                standard_lines = [line.rstrip() for line in f]

            with open(cur_results) as f:
                test_lines = [line.rstrip() for line in f]
        except IOError:
            return False

        if len(standard_lines) != len(test_lines):
            print("Different line count")
            return False

        for index, (line1, line2) in enumerate(zip(standard_lines, test_lines)):

            if line1 == line2:
                continue
        
            if (line1[0] == '*'): # comment section, format is "key=val"
                s1 = line1.split('=')
                s2 = line2.split('=')

                for el_index, (el1, el2) in enumerate(zip(s1, s2)):
                    if el1 == el2:
                        continue
                
                    if el_index == 0: # key
                            print("Different key")
                            return False
                    else: # value
                        try:
                            val1 = float(el1)
                            val2 = float(el2)
                        except:
                            print("Different value")
                            return False

                        diff = val1 - val2;
                        
                        if abs(diff) > 1e-12:
                            print('Difference for Key {} over limit > 1e-12 ({})'.format(s1[0], diff))
                            return False

            else: # points section, format is "Label X Y"
                s1 = line1.split()
                s2 = line2.split()

                for el_index, (el1, el2) in enumerate(zip(s1, s2)):
                    if el1 == el2:
                        continue
                    
                    if el_index == 0: # XY label
                        print("Different point label")
                        return False
                    else: # X, Y coordinates
                        val1 = float(el1)
                        val2 = float(el2)
                        diff = val1 - val2

                        if abs(diff) > 1e-12:
                            print('XY point {} over limit > 1e-12 + ({})'.format(s1[0], diff))
                            return False

        return True

    def compareProjects(self, archiveName="", config="release", sourcePath="", doTrans=False):

        print("* checking {0} *".format(archiveName))

        tmp = platform.processor()
        tmp2 = tmp.replace(" ", "")
        processor = tmp2.replace(",", "")

        self.resultStr2 = processor

        proj_path = Path(self.V.ProjectPath())
        standards_file = proj_path / "standard" / config / archiveName

        if len(sourcePath) > 0:
            proj_path = proj_path / sourcePath

        cur_results = proj_path / archiveName

        V = VSTARS()
        stats = GPhotogrammetryProjectCompareStats()

        if not standards_file.is_file():
            print("cannot read {}".format(standards_file))
            return stats

        if not cur_results.is_file():
            print("cannot read {}".format(cur_results))
            return stats

        stats = V.ComparePhotogrammetryProjects(standards_file, cur_results, doTrans, timeout=60)

        return stats

    def checkResultsEdges(self, stats: GPhotogrammetryProjectCompareStats):
        success_array = []

        if stats.differentCameraCount:
            success_array.append(False)
            print("Different camera count")
        # if (stats.differentImagePointCount):
        #     success_array.append(False)
        #     print ("Different image point count")
        if stats.differentPointCloudCount:
            success_array.append(False)
            print("Different point cloud count")
        if stats.differentPointCount:
            success_array.append(False)
            print("Different point count")
        if stats.mismatchLabel:
            success_array.append(False)
            print("3D mismatched label")
        if stats.differentStationCount:
            success_array.append(False)
            print("Different station count")

        # Check camera sensor
        sensorLimit = 0
        success_array.append(cmpValues(stats.maxImageWidth, sensorLimit, "Image Width over limit"))
        success_array.append(cmpValues(stats.maxImageHeight, sensorLimit, "Image Height over limit"))
        success_array.append(cmpValues(stats.maxPixelSize, sensorLimit, "Pixel size over limit"))

        # Check Image Observations
        # imageLimit = 1e-14
        # success_array.append(cmpValues(stats.maxImageX, imageLimit, "Image X over limit >{}".format(imageLimit)))
        # success_array.append(cmpValues(stats.maxImageY, imageLimit, "Image Y over limit >{}".format(imageLimit)))

        # Check Camera Parameters
        bundleLimit = 1e-12
        success_array.append(cmpValues(stats.maxC, bundleLimit, "Focal Length over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxXP, bundleLimit, "Xp over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxYP, bundleLimit, "Yp over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK1, bundleLimit, "K1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK2, bundleLimit, "K2 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK3, bundleLimit, "K3 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxP1, bundleLimit, "P1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxP2, bundleLimit, "P2 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxB1, bundleLimit, "B1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxB2, bundleLimit, "B2 over limit >{}".format(bundleLimit)))

        # Check image observations bundle vXY
        # success_array.append(cmpValues(stats.maxImageVX, bundleLimit, "vX over limit >{}".format(bundleLimit)))
        # success_array.append(cmpValues(stats.maxImageVY, bundleLimit, "vY over limit >{}".format(bundleLimit)))

        # Check Objects Points
        edgeLimit = 1e-5
        success_array.append(cmpValues(stats.maxObjectX, edgeLimit, "X over limit >{}".format(edgeLimit)))
        success_array.append(cmpValues(stats.maxObjectY, edgeLimit, "Y over limit >{}".format(edgeLimit)))
        success_array.append(cmpValues(stats.maxObjectZ, edgeLimit, "Z over limit >{}".format(edgeLimit)))

        sigmaLimit = 1e-7
        for r in range(0, 3):
            for c in range(r, 3):
                success_array.append(cmpValues(stats.maxObjectCovariance[r][c], sigmaLimit, "XYZ Sigma({},{}) over limit >{}".format(r,c,sigmaLimit)))

        # Check image EO Rotation
        for r in range(0, 3):
            for c in range(0, 3):
                success_array.append(cmpValues(stats.maxStationH[r][c], bundleLimit, "Image EO Rotation({},{}) over limit >{}".format(r,c,bundleLimit)))

        # Check image EO XYZ
        for r in range(0, 3):
            success_array.append(cmpValues(stats.maxStationH[r][3], bundleLimit, "Image EO XYZ({}) over limit >{}".format(r,bundleLimit)))

        # EO Sanity Check
        for c in range(0, 4):
            success_array.append(cmpValues(stats.maxStationH[3][c], bundleLimit, "Image EO H(3,{}) Sanity fail >{}".format(c,bundleLimit)))

        if not all(success_array):
            return False

        print("Test successful")
        return True

    def checkResults(self, stats: GPhotogrammetryProjectCompareStats, sensorLimit = 0, bundleLimit = 1e-11):
        success_array = []

        if stats.differentCameraCount:
            success_array.append(False)
            print("Different camera count")
        if stats.differentImagePointCount:
            success_array.append(False)
            print("Different image point count")
        if stats.differentPointCloudCount:
            success_array.append(False)
            print("Different point cloud count")
        if stats.differentPointCount:
            success_array.append(False)
            print("Different point count")
        if stats.differentDreamMatrixCount:
            success_array.append(False)
            print("Different dream matrix count")
        if stats.mismatchLabel:
            success_array.append(False)
            print("3D mismatched label")
        if stats.differentStationCount:
            success_array.append(False)
            print("Different station count")

        # Check camera sensor
        success_array.append(cmpValues(stats.maxImageWidth, sensorLimit, "Image Width over limit >{}".format(sensorLimit)))
        success_array.append(cmpValues(stats.maxImageHeight, sensorLimit, "Image Width over limit >{}".format(sensorLimit)))
        success_array.append(cmpValues(stats.maxPixelSize, sensorLimit, "Image Width over limit >{}".format(sensorLimit)))

        # Check Image Observations
        success_array.append(cmpValues(stats.maxImageX, sensorLimit, "Image X over limit >{}".format(sensorLimit)))
        success_array.append(cmpValues(stats.maxImageY, sensorLimit, "Image Y over limit >{}".format(sensorLimit)))

        # Check Camera Parameters
        success_array.append(cmpValues(stats.maxC, bundleLimit, "Focal Length over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxXP, bundleLimit, "Xp over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxYP, bundleLimit, "Yp over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK1, bundleLimit, "K1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK2, bundleLimit, "K2 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxK3, bundleLimit, "K3 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxP1, bundleLimit, "P1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxP2, bundleLimit, "P2 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxB1, bundleLimit, "B1 over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxB2, bundleLimit, "B2 over limit >{}".format(bundleLimit)))

        # Check image observations bundle vXY
        success_array.append(cmpValues(stats.maxImageVX, bundleLimit, "vX over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxImageVY, bundleLimit, "vY over limit >{}".format(bundleLimit)))

        # Check Objects Points
        success_array.append(cmpValues(stats.maxObjectX, bundleLimit, "X over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxObjectY, bundleLimit, "Y over limit >{}".format(bundleLimit)))
        success_array.append(cmpValues(stats.maxObjectZ, bundleLimit, "Z over limit >{}".format(bundleLimit)))

        for r in range(0, 3):
            for c in range(r, 3):
                success_array.append(cmpValues(stats.maxObjectCovariance[r][c], bundleLimit, "XYZ Sigmas({},{}) over limit >{}".format(r,c,bundleLimit)))

        # Check image EO Rotation
        for r in range(0, 3):
            for c in range(0, 3):
                success_array.append(cmpValues(stats.maxStationH[r][c], bundleLimit, "Image EO Rotation({},{}) over limit >{}".format(r,c,bundleLimit)))

        # Check image EO XYZ
        for r in range(0, 3):
            success_array.append(cmpValues(stats.maxStationH[r][3], bundleLimit, "Image EO XYZ({}) over limit >{}".format(r,bundleLimit)))

        # EO Sanity Check
        for c in range(0, 4):
            success_array.append(cmpValues(stats.maxStationH[3][c], bundleLimit, "Image EO H(3, {}) Sanity fail >{}".format(c,bundleLimit)))

        # DREAM matrix check
        for r in range(0, 4):
            for c in range(0, 4):
                success_array.append(cmpValues(stats.maxDreamDiff[r][c], bundleLimit, "Dream 4x4 R{}{} over limit >{}".format(r,c,bundleLimit)))

        if not all(success_array):
            return False

        print("Test successful")
        return True

    def beginTest(
        self,
        configuration="release",
        usingDriver=False,
        findNewPoints=True,
        justCont=False,
        autoRelabel: str = None
    ):

        tmp = platform.processor()
        tmp2 = tmp.replace(" ", "")
        processor = tmp2.replace(",", "")

        self.resultStr = processor
        self.resultStr += "\n"

        V = self.V

        print("running tests on {}".format(processor))

        V.FileOpenTemplateProject(template=self.templateName, save=self.templateName)
        V.ProjectAutomeasure(
            cont=justCont, begin=True, close=True, findNewPoints=findNewPoints, attendedMode=False, testing=True, hideDialogs=True
        )

        if autoRelabel is not None:
            V.XYZAutoRelabel(desiredLabels=autoRelabel, onlyAutoMatched=True)
            V.ProjectBundleRun(start=True, accept=True)

        tripletsSuccess = True

        # If we are not finding new points this test is not run
        if findNewPoints:
            tripletsSuccess = self.compareArchives(archiveName="triplets.txt", config=configuration)

        print("triplets success = {0}".format(tripletsSuccess))

        # If using a driver don;t do this test
        scanSuccess = True

        #if not usingDriver:
        scanStats = GPhotogrammetryProjectCompareStats()
        scanStats = self.compareProjects(archiveName="scan.json", config=configuration)
        scanSuccess = self.checkResults(scanStats)

        roSuccess = True

        # If using a driver don;t do this test
        if not usingDriver:
            roStats = GPhotogrammetryProjectCompareStats()
            roStats = self.compareProjects(archiveName="ro.json", config=configuration)
            roSuccess = self.checkResults(roStats)

        # If we are using a driver this test is not run
        resectBundleSuccess = True
        #if not usingDriver:
        resectBundleStats = GPhotogrammetryProjectCompareStats()
        resectBundleStats = self.compareProjects(archiveName="resectBundle.json", config=configuration, doTrans=True)
        resectBundleSuccess = self.checkResults(resectBundleStats)

        # If we are not finding new points this test is not run
        automatchSuccess = True
        if findNewPoints:
            automatchStats = GPhotogrammetryProjectCompareStats()
            automatchStats = self.compareProjects(archiveName="automatch.json", config=configuration, doTrans=True)
            automatchSuccess = self.checkResults(automatchStats)

        bundleStats = GPhotogrammetryProjectCompareStats()
        bundleStats = self.compareProjects(archiveName="finalBundle.json", config=configuration, doTrans=True)
        bundleSuccess = self.checkResults(bundleStats)

        success = (
            tripletsSuccess and bundleSuccess and resectBundleSuccess and scanSuccess and roSuccess and automatchSuccess
        )

        return success
