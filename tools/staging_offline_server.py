#!/usr/bin/env python3
"""Staging-only: run the Global API on 127.0.0.1 with outbound network blocked (reads the stored data copy only).

    cd <checkout>/analysis && BIAP_GLOBAL_DATA_DIR=<staging data copy> RISK_AGENT_ENABLED=1 PYTHONPATH=$PWD \
        python ../tools/staging_offline_server.py --port 8197

The guard is loaded by file path so it also works on older checkouts. Refuses any host except loopback. Not used by production.
"""
import argparse
import importlib.util
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8197)
a = ap.parse_args()
guard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis", "global_markets", "offline_guard.py")
spec = importlib.util.spec_from_file_location("offline_guard_staging", guard_path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
guard.install()
sys.path.insert(0, os.getcwd())
import uvicorn  # noqa: E402

uvicorn.run("global_api_server:app", host="127.0.0.1", port=a.port, workers=1, log_level="warning")
