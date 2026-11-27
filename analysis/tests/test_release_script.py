"""The owner-run release script must run the tests as the invoking user (not root) with a raised open-files limit."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "restart-global-prod.sh"


def test_script_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_tests_run_as_sudo_user_with_higher_limit_and_throwaway_data_dir():
    text = SCRIPT.read_text()
    assert 'runuser -u "$runas"' in text and "SUDO_USER" in text
    assert "ulimit -n 65536" in text
    assert "PYTHONDONTWRITEBYTECODE=1" in text and "-p no:cacheprovider" in text
    assert 'BIAP_GLOBAL_DATA_DIR="$testdata"' in text and "mktemp -d" in text
    # the restart still happens only after the tests, and the quiet-window/rollback lines are unchanged
    assert text.index("pytest") < text.index("systemctl restart biap-global.service")
    assert "rollback: git checkout $prev" in text
