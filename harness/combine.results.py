from os import listdir
from os.path import isdir, isfile, join
from chaos.checks.result import Result
import re
import json

result_pattern = re.compile("""^\d+\.json$""")

def combine(path):
    if not isdir(path):
        print(f"result dir \"{path}\" isn't found")
        return
    combined = {
        "test_runs": {},
        "result": Result.PASSED
    }
    for f in listdir(path):
        if not isfile(join(path,f)):
            continue
        if not result_pattern.match(f):
            continue
        result = None
        with open(join(path,f), "r") as result_file:
            result = json.load(result_file)
        for test_key in result["test_runs"].keys():
            if test_key not in combined["test_runs"]:
                combined["test_runs"][test_key] = {}
            for test_run_key in result["test_runs"][test_key].keys():
                status = result["test_runs"][test_key][test_run_key]
                combined["test_runs"][test_key][test_run_key] = status
        combined["result"] = Result.more_severe(combined["result"], result["result"])
    with open(join(path,"all.json"), "w") as all_file:
        all_file.write(json.dumps(combined, indent=2))

combine("results")