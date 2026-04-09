import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fusionframe import App
from fusionframe.testing import TestClient


app = App()


@app.get("/ping")
async def ping(request):
    return {"ok": True}


def run(iterations=2000):
    client = TestClient(app)
    started = time.perf_counter()
    for _ in range(iterations):
        response = client.get("/ping")
        if response.status_code != 200:
            raise RuntimeError("benchmark request failed")
    elapsed = time.perf_counter() - started
    return {
        "iterations": iterations,
        "elapsed_seconds": round(elapsed, 6),
        "requests_per_second": round(iterations / elapsed, 2),
    }


if __name__ == "__main__":
    iterations = int(os.getenv("FUSIONFRAME_BENCH_ITERATIONS", "2000"))
    print(json.dumps(run(iterations=iterations), indent=2))
