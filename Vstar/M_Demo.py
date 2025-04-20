import time
from datetime import datetime

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

    vs.MModeSetup(saveEpochs=True, saveImages=True)

    vs.MModeUnStableCameraOrientation(bOk=False)

    for i in range(1, 12):
        time.sleep(2)
        vs.MModeTrigger()

    # Get the project file names
    driver, triangulation = vs.ProjectFileNames()

    vs.XYZExportReport(filename=triangulation, saveAs=f"{triangulation}.txt", measuredData=True, save=True, ok=True)

    vs.Pause(f"Project Complete.  Results are in file: {triangulation}.txt")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unknown Scripting Error: {e}")
