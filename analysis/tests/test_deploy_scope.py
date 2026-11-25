"""deploy/deploy-scope.sh decides whether a push to main needs the Kiasha/Iran VPS deploy (Global/docs/research/CI-only => no)."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "deploy-scope.sh"


def classify(tmp_path, files):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, env=env, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    (tmp_path / "seed.txt").write_text("x")
    git("add", "-A"); git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("y")
    git("add", "-A"); git("commit", "-qm", "change")
    out = subprocess.run(["bash", str(SCRIPT), "push", git("rev-parse", "HEAD"), base], cwd=tmp_path, env=env, capture_output=True, text=True).stdout
    return out.splitlines()[0]


@pytest.mark.parametrize("files", [
    [".github/workflows/biap-nov19-returns.yml", ".github/workflows/paper-portfolio-diagnostics.yml"],
    [".github/workflows/biap-global-xyz.yml"], [".github/workflows/research-foo.yml"],
    ["research/outputs/x.csv", "research/paper_portfolio_diagnostics.py"], ["analysis/global_markets/risk_agent.py"], ["docs/a.md"],
])
def test_research_global_docs_never_deploy(tmp_path, files):
    assert classify(tmp_path, files) == "deploy=false"


@pytest.mark.parametrize("files", [
    ["analysis/api_server.py"], [".github/workflows/some-other.yml"], ["backend/x.js"],
    ["research/x.csv", "analysis/benchmark_refresh.py"],           # one deploy-relevant file in the mix is enough
])
def test_backend_changes_still_deploy(tmp_path, files):
    assert classify(tmp_path, files) == "deploy=true"
