class Result:
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CRUSHED = "CRUSHED"
    @staticmethod
    def more_severe(a, b):
        results = [Result.FAILED, Result.UNKNOWN, Result.PASSED, Result.CRUSHED]
        if a not in results:
            raise Exception(f"unknown result value: a={a}")
        if b not in results:
            raise Exception(f"unknown result value: b={b}")
        if a == Result.FAILED or b == Result.FAILED:
            return Result.FAILED
        if a == Result.UNKNOWN or b == Result.UNKNOWN:
            return Result.UNKNOWN
        if a == Result.CRUSHED or b == Result.CRUSHED:
            return Result.CRUSHED
        return Result.PASSED