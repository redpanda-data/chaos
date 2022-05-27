class Result:
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CRUSHED = "CRUSHED"
    HANG = "HANG"
    NODATA = "NODATA"
    @staticmethod
    def more_severe(a, b):
        results = [Result.FAILED, Result.UNKNOWN, Result.PASSED, Result.CRUSHED, Result.HANG, Result.NODATA]
        if a not in results:
            raise Exception(f"unknown result value: a={a}")
        if b not in results:
            raise Exception(f"unknown result value: b={b}")
        if a == Result.FAILED or b == Result.FAILED:
            return Result.FAILED
        if a == Result.UNKNOWN or b == Result.UNKNOWN:
            return Result.UNKNOWN
        if a == Result.HANG or b == Result.HANG:
            return Result.HANG
        if a == Result.NODATA or b == Result.NODATA:
            return Result.NODATA
        if a == Result.CRUSHED or b == Result.CRUSHED:
            return Result.CRUSHED
        return Result.PASSED
    
    @staticmethod
    def least_severe(a, b):
        results = [Result.FAILED, Result.UNKNOWN, Result.PASSED, Result.CRUSHED, Result.HANG, Result.NODATA]
        if a not in results:
            raise Exception(f"unknown result value: a={a}")
        if b not in results:
            raise Exception(f"unknown result value: b={b}")
        if a == Result.PASSED or b == Result.PASSED:
            return Result.PASSED
        if a == Result.CRUSHED or b == Result.CRUSHED:
            return Result.CRUSHED
        if a == Result.NODATA or b == Result.NODATA:
            return Result.NODATA
        if a == Result.HANG or b == Result.HANG:
            return Result.HANG
        if a == Result.UNKNOWN or b == Result.UNKNOWN:
            return Result.UNKNOWN
        return Result.FAILED