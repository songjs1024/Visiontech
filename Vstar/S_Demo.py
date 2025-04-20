import os
from datetime import datetime
from configparser import ConfigParser

from vstars import VSTARS


def main():
    vs = VSTARS()
    vs.init()

    template_name = "Demo Project"

    # Get date and time for project name.
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H-%M-%S")

    job_number, operator_initials = vs.Prompt2(title="Enter job number and your initials", label1="Job Number", label2="Initials")

    project_name = f"On {current_date} at {current_time} Job {job_number} by {operator_initials}"

    vs.FileOpenTemplateProject(template=template_name, save=project_name)

    vs.PicturesSetImagePath(path=R"D:\image_path")

    vs.ProjectImportImages(below=True)

    #  Scan and process the pictures.
    vs.ProjectAutomeasure(begin=True, close=True, findNewPoints=True, attendedMode=False)

    # Rename the file bundle
    vs.Rename3D(newName="Final Results")

    # prepare the header
    project_path = vs.ProjectPath()

    # configure the report header via the report.ini file
    reportIniParser = ConfigParser()
    reportIniParser.read(os.path.join(project_path, "report.ini"))

    if not reportIniParser.has_section("header1"):
        reportIniParser.add_section("header1")
    reportIniParser.set("header1", "title", "Operator")
    reportIniParser.set("header1", "data", operator_initials)
    reportIniParser.set("header1", "active", "True")

    if not reportIniParser.has_section("header2"):
        reportIniParser.add_section("header2")
    reportIniParser.set("header2", "title", "Job Number")
    reportIniParser.set("header2", "data", f"{job_number}")
    reportIniParser.set("header2", "active", "True")

    if not reportIniParser.has_section("header3"):
        reportIniParser.add_section("header3")
    reportIniParser.set("header3", "active", "False")

    if not reportIniParser.has_section("header4"):
        reportIniParser.add_section("header4")
    reportIniParser.set("header4", "active", "False")

    if not reportIniParser.has_section("datetime"):
        reportIniParser.add_section("datetime")
    reportIniParser.set("datetime", "active", "True")

    if not reportIniParser.has_section("filename"):
        reportIniParser.add_section("filename")
    reportIniParser.set("filename", "active", "True")

    with open(os.path.join(project_path, "report.ini"), "w") as reportFile:
        reportIniParser.write(reportFile)

    vs.XYZExportReport(filename="Final Results", saveAs="Final Results.txt", measuredData=True, save=True, ok=True)


    vs.Pause("Project Complete.  Results are in file: Final Results.txt")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unknown Scripting Error: {e}")
