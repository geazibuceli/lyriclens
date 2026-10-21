import json
import shutil
import subprocess
from pathlib import Path
import sys
import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows installer')
def test_check_only_reports_missing_installation_without_creating_environment(tmp_path):
    script = Path(__file__).resolve().parents[3]/'setup.ps1'
    shutil.copyfile(script, tmp_path/'setup.ps1')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                             str(tmp_path/'setup.ps1'), '-CheckOnly'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    assert result.stdout.strip(), result.stderr
    status = json.loads(result.stdout)
    assert status['ready'] is False and status['python'] is None
    assert not status['backend_dependencies'] and not status['model_prepared']
    assert list(tmp_path.iterdir()) == [tmp_path/'setup.ps1']
