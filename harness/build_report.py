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
        .fault_group {
            line-height: 1.7em;
        }
        .fault_group a {
            padding-right: 1em;
        }
        .overview th, .overview td {
            padding-right: 1em;
        }
        .summary {
            float: left;
            padding-right: 1em;
        }
        .summary table {
            margin-bottom: 1em;
        }
        table.throughput {
            border-collapse: collapse;
        }
        .throughput th, .throughput td {
            border: 1px solid black;
            padding: 3px;
        }
        table.latency {
            border-collapse: collapse;
        }
        .latency th, .latency td {
            border: 1px solid black;
            padding: 3px;
        }
        table.checks {
            border-collapse: collapse;
        }
        .checks th, .checks td {
            border: 1px solid black;
            padding: 3px;
        }
        .borderless {
            border: 0px !important;
        }
    </style>
</header>
<body>

<h1>Chaos tests</h1>
<h2>{{ overall_status }}</h2>

<table class="overview">
    <tr>
        <th>Status</th>
        <th>Run</th>
        <th>Experiment</th>
        <th>Max unavailability (us)</th>
    </tr>
{% for group in experiment_groups %}
{% for experiment in group %}
    <tr>
        <td>{{ experiment.status }}</td>
        <td><a href="#{{ experiment.run }}">{{ experiment.run }}</a></td>
        <td>{{ experiment.name }}</td>
        {% if experiment.max_unavailability_us %}
        {% if max_unavailable_experiment %}
        {% if experiment.run == max_unavailable_experiment.run %}
        <td><a href="#{{ experiment.run }}">{{ '{0:,}'.format(experiment.max_unavailability_us) }}</a></td>
        {% else %}
        <td>{{ '{0:,}'.format(experiment.max_unavailability_us) }}</td>
        {% endif %}
        {% else %}
        <td>{{ '{0:,}'.format(experiment.max_unavailability_us) }}</td>
        {% endif %}
        {% endif %}
    </tr>
{% endfor %}
{% endfor %}
</table>

<h2>Grouped by fault injection</h2>
<div class="fault_group">
    {% for group in fault_groups %}
    <a href="{{ group.id }}.html">{{ group.name }}</a>
    {% endfor %}
</div>

<h2>Experiments</h2>
{% for workload in workloads %}
    {% for experiment in workload.experiments %}
    <h3><a id="{{ experiment.run }}"></a> {{ experiment.name }} ({{ experiment.run }}) </h3>
    <div>
    <div class="summary">
    {% if experiment.checks %}
    <table class="checks">
        <tr>
            <th colspan="2" class="borderless">Checks</th>
        </tr>
        {% for check in experiment.checks %}
        <tr>
            <td>{{ check.name }}</td>
            <td class="{{ check.status }}">{{ check.status }}</td>
        <tr>
        {% endfor %}
    </table>
    {% endif %}
    {% if experiment.max_unavailability_us %}
    <table class="unavailability">
        <tr>
            <th>max unavailability (us)</th>
            <td>{{ '{0:,}'.format(experiment.max_unavailability_us) }}</td>
        </tr>
    </table>
    {% endif %}
    {% if experiment.throughput %}
    <table class="throughput">
        <tr>
            <td class="borderless"></td>
            <th>avg ops/s</th>
            <th>max ops/s</th>
        </tr>
        <tr>
            <th>throughput</th>
            <td>{{ experiment.throughput.avg }}</td>
            <td>{{ experiment.throughput.max }}</td>
        </tr>
    </table>
    {% endif %}
    {% if experiment.latencies %}
    <table class="latency">
        <tr>
            <th colspan="4" class="borderless">Latency (us)</th>
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
    </table>
    {% endif %}
    </div>
    {% for image in experiment.images %}{% if image.is_overview %}<a href="{{ image.path }}"><img src={{ image.path }} /></a>{% endif %}{% endfor %}
    <div style="clear: both;"></div>
    </div>
    {% endfor %}
{% endfor %}

</body>
</html>
"""

FAULT = """
<html>
<header>
    <style>
        img {
            width: 800px;
            height: auto;
        }
        .summary {
            float: left;
            padding-right: 1em;
        }
        .summary table {
            margin-bottom: 1em;
        }
        table.throughput {
            border-collapse: collapse;
        }
        .throughput th, .throughput td {
            border: 1px solid black;
            padding: 3px;
        }
        table.latency {
            border-collapse: collapse;
        }
        .latency th, .latency td {
            border: 1px solid black;
            padding: 3px;
        }
        table.checks {
            border-collapse: collapse;
        }
        .checks th, .checks td {
            border: 1px solid black;
            padding: 3px;
        }
        .borderless {
            border: 0px !important;
        }
    </style>
</header>
<body>

<h1>{{ fault }}</h1>
{% for workload in workloads %}
    {% for experiment in workload.experiments %}
    <h3>{{ experiment.name }} ({{ experiment.run }}) </h3>
    <div>
    <div class="summary">
    {% if experiment.checks %}
    <table class="checks">
        <tr>
            <th colspan="2">Checks</th>
        </tr>
        {% for check in experiment.checks %}
        <tr>
            <td>{{ check.name }}</td>
            <td class="{{ check.status }}">{{ check.status }}</td>
        <tr>
        {% endfor %}
    </table>
    {% endif %}
    {% if experiment.max_unavailability_us %}
    <table class="unavailability">
        <tr>
            <th>max unavailability (us)</th>
            <td>{{ '{0:,}'.format(experiment.max_unavailability_us) }}</td>
        </tr>
    </table>
    {% endif %}
    {% if experiment.throughput %}
    <table class="throughput">
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
    </table>
    {% endif %}
    {% if experiment.latencies %}
    <table class="latency">
        <tr>
            <th colspan="4">Latency (us)</th>
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
    </table>
    {% endif %}
    </div>
    {% for image in experiment.images %}{% if image.is_overview %}<a href="{{ image.path }}"><img src={{ image.path }} /></a>{% endif %}{% endfor %}
    <div style="clear: both;"></div>
    </div>
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

class Fault:
    def __init__(self):
        self.name = None
        self.alias = None

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

class FaultGroup:
    def __init__(self):
        self.name = None
        self.id = None
        self.experiments = []

def build(path):
    result = None
    with open(join(path, "all.json"), "r") as result_file:
        result = json.load(result_file)
    
    overall_status = result["result"]
    
    failed = []
    unknown = []
    crushed = []
    hang = []
    passed = []

    workloads = dict()
    fault_groups = dict()
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
                fault_config = info["fault"]
                if fault_config != None:
                    if isinstance(fault_config, str):
                        fault_config = {
                            "name": fault_config
                        }
                    if "alias" not in fault_config:
                        fault_config["alias"] = fault_config["name"]
                    
                    experiment.fault = Fault()
                    experiment.fault.name = fault_config["name"]
                    experiment.fault.alias = fault_config["alias"]
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
                    if experiment.fault == None:
                        should_progress_check = True
                    elif experiment.fault.name in FAULTS:
                        if FAULTS[experiment.fault.name](None).fault_type == FaultType.ONEOFF:
                            should_progress_check = True
                if experiment.workload in ["reads-writes / java", "tx-money / java", "tx-single-reads-writes / java", "tx-streaming / java", "list-offsets / java"]:
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
                if experiment.workload in ["reads-writes / java", "tx-money / java", "tx-single-reads-writes / java", "tx-streaming / java"]:
                    if len(info["workload"]["nodes"]) != 1:
                        raise Exception(f"only one node workloads are supported: {run}")
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
                elif experiment.workload == "tx-subscribe / java":
                    for check in info["workload"]["checks"]:
                        if check["name"] == "stat":
                            if "total" in check:
                                stat = check["total"]
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
                    node_dir = join(path, run)
                    for img in listdir(node_dir):
                        if not isfile(join(node_dir, img)):
                            continue
                        if img.endswith(".png"):
                            image = Image()
                            image.path = join(run, img)
                            if img == "overview.png":
                                image.is_overview = True
                            experiment.images.append(image)
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
            if experiment.fault == None:
                experiment.fault = Fault()
                experiment.fault.name = "baseline"
                experiment.fault.alias = "baseline"
            if experiment.fault.alias not in fault_groups:
                group = FaultGroup()
                group.name = experiment.fault.alias
                group.id = f"fault{len(fault_groups)}"
                fault_groups[group.name] = group
            fault_groups[experiment.fault.alias].experiments.append(experiment)
            experiments.append(experiment)
        for experiment in experiments:
            if experiment.status == Result.PASSED:
                passed.append(experiment)
            elif experiment.status == Result.UNKNOWN:
                unknown.append(experiment)
            elif experiment.status == Result.FAILED:
                failed.append(experiment)
            elif experiment.status == Result.CRUSHED:
                crushed.append(experiment)
            elif experiment.status == Result.HANG:
                hang.append(experiment)
            else:
                raise Exception(f"Unknown status: {experiment.status}")

    for key in fault_groups.keys():
        group = fault_groups[key]
        group_workloads = dict()
        for experiment in group.experiments:
            if experiment.workload not in group_workloads:
                group_workloads[experiment.workload] = Workload(experiment.workload)
            group_workloads[experiment.workload].experiments.append(experiment)
        with open(join(path, f"{group.id}.html"), "w") as group_file:
            group_file.write(jinja2.Template(FAULT).render(
                fault = group.name,
                workloads=list(group_workloads.values())))

    with open(join(path, "index.html"), "w") as index_file:
            index_file.write(jinja2.Template(INDEX).render(
                fault_groups = fault_groups.values(),
                overall_status = overall_status,
                experiment_groups=[failed, unknown, hang, crushed, passed],
                max_unavailable_experiment = max_unavailable_experiment,
                workloads=list(workloads.values())))

build("results")