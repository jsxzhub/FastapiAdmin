"""应用入口测试 —— 健康检查接口返回码与响应体校验。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _probe_env(env_name: str) -> str:
    """在干净子进程中执行 main.run(env=...)，返回最终生效的运行环境。"""
    code = f"""
import os
os.environ.pop("ENVIRONMENT", None)
import uvicorn

captured = {{}}
uvicorn.run = lambda **kwargs: captured.update(kwargs)

import main
main.run(env={env_name!r})

from app.config.setting import settings
print(f"PROBE_RESULT={{settings.ENVIRONMENT.value}}|{{captured.get('host')}}")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={key: value for key, value in os.environ.items() if key != "ENVIRONMENT"},
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("PROBE_RESULT=")]
    assert lines, result.stdout
    return lines[-1].split("=", 1)[1]


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_run_env_is_applied_before_settings_load(env_name: str) -> None:
    """--env 必须在导入 app/settings 之前生效，否则 reload 父子进程配置不一致。"""
    assert _probe_env(env_name).split("|")[0] == env_name


def test_default_environment_is_prod() -> None:
    """不显式指定 ENVIRONMENT 时，gunicorn 等入口默认加载 prod。"""
    result = subprocess.run(
        [sys.executable, "-c", "from app.config.setting import settings; print(f'PROBE_RESULT={settings.ENVIRONMENT.value}')"],
        cwd=BACKEND_DIR,
        env={key: value for key, value in os.environ.items() if key != "ENVIRONMENT"},
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert "PROBE_RESULT=prod" in result.stdout


def test_check_health(test_client: TestClient) -> None:
    response = test_client.get("/monitor/health/check/")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["code"] == 0
