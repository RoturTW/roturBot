# sandbox_worker.py

import sys
import json
import time
import resource

# ---------------- limits ----------------

CPU_TIME = 2            # seconds
MEMORY = 128 * 1024 * 1024  # 128MB

resource.setrlimit(resource.RLIMIT_CPU, (CPU_TIME, CPU_TIME))
resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))

# no file spam
resource.setrlimit(resource.RLIMIT_FSIZE, (1 * 1024 * 1024, 1 * 1024 * 1024))

# ---------------- safe builtins ----------------

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}

# ---------------- read code ----------------

code = sys.stdin.read()

globals_dict = {
    "__builtins__": SAFE_BUILTINS
}

start = time.time()

try:
    exec(code, globals_dict, None)
    result = globals_dict.get("_")
    ok = True
    err = None
except Exception as e:
    ok = False
    result = None
    err = f"{type(e).__name__}: {e}"

out = {
    "success": ok,
    "result": repr(result),
    "time": round(time.time() - start, 4),
    "error": err
}

print(json.dumps(out))