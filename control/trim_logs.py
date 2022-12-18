import sys
from os import listdir, remove, rename
from os.path import isfile, join

for log_name in listdir(sys.argv[1]):
    log_name = join(sys.argv[1], log_name)
    if not isfile(log_name):
        continue
    tmp_file = join(sys.argv[1], "tmp")

    keep = True

    with open(log_name, "r") as log_in:
        with open(tmp_file, "w") as log_out:
            for line in log_in:
                if any(map(lambda x: line.startswith(x), ["TRACE", "DEBUG"])):
                    keep = False
                if any(map(lambda x: line.startswith(x), ["INFO", "WARN", "ERROR"])):
                    keep = True
                if keep:
                    log_out.write(line)

    remove(log_name)
    rename(tmp_file, log_name)