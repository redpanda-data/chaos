from chaos.checks.result import Result

class RedpandaProcessLivenessCheck:
    def __init__(self):
        pass
    
    def check(self, scenario):
        result = {
            "result": Result.PASSED,
            "details": {}
        }
        for node in scenario.redpanda_cluster.nodes:
            result["details"][node.ip] = scenario.redpanda_cluster.is_alive(node)
            if not result["details"][node.ip]:
                result["result"] = Result.CRUSHED
        return result