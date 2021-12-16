import json
from os import listdir
from chaos.checks.result import Result
from os.path import isdir, isfile, join
from chaos.faults.all import FAULTS
from chaos.faults.types import FaultType
import jinja2
import re

INDEX = """
<html>
<header>
    <style>
        img {
            width: 800px;
            height: auto;
        }
    </style>
</header>
<body>

<h1>Chaos tests</h1>
<h2>{{ overall_status }}</h2>

<table>
    <tr>
        <th>Status</th>
        <th>Run</th>
        <th>Experiment</th>
        <th>Max unavailability (us)</th>
    </tr>
{% for experiment in failed %}
    <tr>
        <td>{{ experiment.status }}</td>
        <td><a href="#{{ experiment.run }}">{{ experiment.run }}</a></td>
        <td>{{ experiment.name }}</td>
        {% if experiment.max_unavailability_us %}
        {% if max_unavailable_experiment %}
        {% if experiment.run == max_unavailable_experiment.run %}
        <td><a href="#{{ experiment.run }}">{{ experiment.max_unavailability_us }}</a></td>
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% endif %}
    </tr>
{% endfor %}
{% for experiment in unknown %}
    <tr>
        <td>{{ experiment.status }}</td>
        <td><a href="#{{ experiment.run }}">{{ experiment.run }}</a></td>
        <td>{{ experiment.name }}</td>
        {% if experiment.max_unavailability_us %}
        {% if max_unavailable_experiment %}
        {% if experiment.run == max_unavailable_experiment.run %}
        <td><a href="#{{ experiment.run }}">{{ experiment.max_unavailability_us }}</a></td>
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% endif %}
    </tr>
{% endfor %}
{% for experiment in passed %}
    <tr>
        <td>{{ experiment.status }}</td>
        <td><a href="#{{ experiment.run }}">{{ experiment.run }}</a></td>
        <td>{{ experiment.name }}</td>
        {% if experiment.max_unavailability_us %}
        {% if max_unavailable_experiment %}
        {% if experiment.run == max_unavailable_experiment.run %}
        <td><a href="#{{ experiment.run }}">{{ experiment.max_unavailability_us }}</a></td>
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% else %}
        <td>{{ experiment.max_unavailability_us }}</td>
        {% endif %}
        {% endif %}
    </tr>
{% endfor %}
</table>



{% for workload in workloads %}
    <h2>{{ workload.name }}</h2>
    {% for experiment in workload.experiments %}
    <h3><a id="{{ experiment.run }}"></a> {{ experiment.fault }} ({{ experiment.run }}) </h3>
    <table>
        <tr>
            <th>workload</th>
            <td>{{ workload.name }}</td>
        </tr>
        {% if experiment.checks %}
        <tr>
            <th>Checks</th>
        </tr>
        {% for check in experiment.checks %}
        <tr>
            <td>{{ check.name }}</td>
            <td>{{ check.status }}</td>
        <tr>
        {% endfor %}
        {% endif %}
        {% if experiment.max_unavailability_us %}
        <tr>
            <th>max unavailability (us)</th>
            <td>{{ experiment.max_unavailability_us }}</td>
        </tr>
        {% endif %}
        {% if experiment.throughput %}
        <tr>
            <td></td>
            <th>avg ops/s</th>
            <th>max ops/s</th>
        </tr>
        <tr>
            <th>throughput</th>
            <td>{{ experiment.throughput.avg }}</td>
            <td>{{ experiment.throughput.max }}</td>
        </tr>
        {% endif %}
        {% if experiment.latencies %}
        <tr>
            <th>Latency (us)</th>
        </tr>
        <tr>
            <th>metric</th>
            <th>p99</th>
            <th>min</th>
            <th>max</th>
        </tr>
        {% for latency in experiment.latencies %}
        <tr>
            <td>{{ latency.name }}</td>
            <td>{{ latency.p99 }}</td>
            <td>{{ latency.min }}</td>
            <td>{{ latency.max }}</td>
        </tr>
        {% endfor %}
        {% endif %}
    </table>
    {% for image in experiment.images %}{% if image.is_overview %}<img src={{ image.path }} />{% endif %}{% endfor %}
    {% endfor %}
{% endfor %}

</body>
</html>
"""

class Experiment:
    def __init__(self):
        self.name = None
        self.run = None
        self.status = None
        self.workload = None
        self.fault = None
        self.throughput = None
        self.max_unavailability_us = None
        self.latencies = []
        self.images = []
        self.checks = []

class Workload:
    def __init__(self, name):
        self.name = name
        self.experiments = []

class Image:
    def __init__(self):
        self.path = None
        self.is_overview = False

class Latency:
    def __init__(self):
        self.min = None
        self.max = None
        self.p99 = None
        self.title = None

class Throughput:
    def __init__(self):
        self.max = None
        self.avg = None

class Check:
    def __init__(self):
        self.name = None
        self.status = None

def build(path):
    result = None
    with open(join(path, "all.json"), "r") as result_file:
        result = json.load(result_file)
    
    overall_status = result["result"]
    failed = []
    unknown = []
    passed = []
    workloads = dict()
    max_unavailable_experiment = None
    for name in result["test_runs"].keys():
        experiments = []
        for run in result["test_runs"][name].keys():
            experiment = Experiment()
            experiment.name = name
            experiment.run = run
            experiment.status = result["test_runs"][name][run]

            info = None
            with open(join(path, run, "info.json"), "r") as info_file:
                info = json.load(info_file)
                experiment.workload = info["workload"]["name"]
                experiment.fault = info["fault"]
                if experiment.fault != None:
                    if isinstance(experiment.fault, str):
                        experiment.fault = {
                            "name": experiment.fault
                        }
                    experiment.fault = experiment.fault["name"]
                else:
                    experiment.fault = "baseline"
                for node in info["workload"]["nodes"]:
                    node_dir = join(path, run, node)
                    for img in listdir(node_dir):
                        if not isfile(join(node_dir, img)):
                            continue
                        if img.endswith(".png"):
                            image = Image()
                            image.path = join(run, node, img)
                            if img == "overview.png":
                                image.is_overview = True
                            experiment.images.append(image)
                should_progress_check = False
                if "checks" in info["workload"]:
                    for check in info["workload"]["checks"]:
                        check_info = Check()
                        check_info.name = check["name"]
                        check_info.status = Result.UNKNOWN
                        if "result" in check:
                            check_info.status = check["result"]
                        experiment.checks.append(check_info)
                    for check in info["checks"]:
                        if check["name"] == "progress_during_fault":
                            should_progress_check = True
                        check_info = Check()
                        check_info.name = check["name"]
                        check_info.status = Result.UNKNOWN
                        if "result" in check:
                            check_info.status = check["result"]
                        experiment.checks.append(check_info)
                    if experiment.fault == "baseline":
                        should_progress_check = True
                    elif experiment.fault in FAULTS:
                        if FAULTS[experiment.fault](None).fault_type == FaultType.ONEOFF:
                            should_progress_check = True
                if experiment.workload in ["reads-writes / java", "tx-money / java", "tx-single-reads-writes / java", "tx-streaming / java"]:
                    if len(info["workload"]["nodes"]) != 1:
                        raise Exception("only one node workloads are supported")
                    for check in info["workload"]["checks"]:
                        if check["name"] == "stat":
                            if info["workload"]["nodes"][0] in check:
                                stat = check[info["workload"]["nodes"][0]]
                                if "latency_us" in stat:
                                    for latency_name in stat["latency_us"].keys():
                                        latency = Latency()
                                        latency.name = latency_name
                                        latency.min = stat["latency_us"][latency_name]["min"]
                                        latency.max = stat["latency_us"][latency_name]["max"]
                                        latency.p99 = stat["latency_us"][latency_name]["p99"]
                                        experiment.latencies.append(latency)
                                if "throughput" in stat:
                                    experiment.throughput = Throughput()
                                    experiment.throughput.avg = stat["throughput"]["avg/s"]
                                    experiment.throughput.max = stat["throughput"]["max/s"]
                                if "max_unavailability_us" in stat:
                                    experiment.max_unavailability_us = stat["max_unavailability_us"]
                elif experiment.workload == "list-offsets / java":
                    if len(info["workload"]["nodes"]) != 1:
                        raise Exception("only one node workloads are supported")
                    for check in info["workload"]["checks"]:
                        if check["name"] == "stat":
                            if info["workload"]["nodes"][0] in check:
                                stat = check[info["workload"]["nodes"][0]]
                                if "latency_us" in stat:
                                    latency = Latency()
                                    latency.name = "send latency"
                                    latency.min = stat["latency_us"]["min"]
                                    latency.max = stat["latency_us"]["max"]
                                    latency.p99 = stat["latency_us"]["p99"]
                                    experiment.latencies.append(latency)
                                if "throughput" in stat:
                                    experiment.throughput = Throughput()
                                    experiment.throughput.avg = stat["throughput"]["avg/s"]
                                    experiment.throughput.max = stat["throughput"]["max/s"]
                                if "max_unavailability_us" in stat:
                                    experiment.max_unavailability_us = stat["max_unavailability_us"]
                else:
                    raise Exception(f"unsupported workload: {experiment.workload}")
                if should_progress_check and experiment.max_unavailability_us != None:
                    if max_unavailable_experiment == None:
                        max_unavailable_experiment = experiment
                    if max_unavailable_experiment.max_unavailability_us < experiment.max_unavailability_us:
                        max_unavailable_experiment = experiment
            if experiment.workload not in workloads:
                workloads[experiment.workload] = Workload(experiment.workload)
            workloads[experiment.workload].experiments.append(experiment)
            experiments.append(experiment)
        for experiment in experiments:
            if experiment.status == Result.PASSED:
                passed.append(experiment)
            elif experiment.status == Result.UNKNOWN:
                unknown.append(experiment)
            elif experiment.status == Result.FAILED:
                failed.append(experiment)
            else:
                raise Exception(f"Unknown status: {experiment.status}")

    with open(join(path, "index.html"), "w") as index_file:
            index_file.write(jinja2.Template(INDEX).render(
                overall_status = overall_status,
                failed=failed,
                unknown=unknown,
                passed=passed,
                max_unavailable_experiment = max_unavailable_experiment,
                workloads=list(workloads.values())))

build("results")