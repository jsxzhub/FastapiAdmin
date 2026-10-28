"""SQL 控制台服务测试：DSN 构造、只读/确认写前置校验、密码加密、出参不含密码。"""

import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.engine import make_url

from app.config.db_url import build_redis_url
from app.core.exceptions import CustomException
from app.modules.ops.dbconsole import service as service_module
from app.modules.ops.dbconsole.schema import DbConnectionCreateSchema, DbConnectionUpdateSchema
from app.modules.ops.dbconsole.service import DbConsoleService, build_url
from app.utils.crypto_util import CryptoUtil


def test_build_url_escapes_password_and_database() -> None:
    url = build_url("mysql", "db.internal", 3306, "user", "p@ss/w:ord!", "app db")
    assert url.startswith("mysql+aiomysql://user:")
    assert "p%40ss" in url and "w%3Aord%21" in url
    parsed = make_url(url)
    assert parsed.password == "p@ss/w:ord!"
    assert parsed.username == "user"
    assert parsed.database == "app db"
    assert build_url("postgres", "pg", 5432, "u", "p", None) == "postgresql+asyncpg://u:p@pg:5432"


def test_redis_url_escapes_special_chars() -> None:
    url = build_redis_url(username="", password="p@ss!中文", host="redis", port=6379, db=1)
    assert "%40" in url and "%21" in url
    assert "p@ss!" not in url


def test_build_url_rejects_unsupported_type() -> None:
    with pytest.raises(CustomException):
        build_url("sqlite", "x", 0, "u", "p", None)


class _FakeCrud:
    def __init__(self, row: SimpleNamespace | None = None) -> None:
        self.row = row
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.deleted: list[int] = []

    async def get_or_404(self, id: int, msg: str) -> SimpleNamespace:
        if self.row is None:
            raise CustomException(msg=msg)
        return self.row

    async def get(self, **kwargs: Any) -> SimpleNamespace | None:
        return None

    async def get_list(self) -> list[SimpleNamespace]:
        return [self.row] if self.row else []

    async def create(self, data: dict[str, Any]) -> SimpleNamespace:
        self.created.append(data)
        return SimpleNamespace(id=1, status=0, **data)

    async def update(self, id: int, data: dict[str, Any]) -> SimpleNamespace:
        self.updated.append(data)
        return SimpleNamespace(id=id, status=0, **{**data, "password": data.get("password", "")})

    async def delete(self, ids: list[int]) -> None:
        self.deleted.extend(ids)


def _service_with(crud: _FakeCrud) -> DbConsoleService:
    service = DbConsoleService.__new__(DbConsoleService)
    setattr(service, "auth", None)
    setattr(service, "db", None)
    setattr(service, "_crud", lambda: crud)
    return service


def _row(**overrides: Any) -> SimpleNamespace:
    data: dict[str, Any] = {
        "id": 1,
        "name": "prod",
        "db_type": "mysql",
        "host": "db.internal",
        "port": 3306,
        "username": "u",
        "password": CryptoUtil.encrypt("secret"),
        "database": "app",
        "status": 0,
        "description": "",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_service_has_no_local_sqlite_support() -> None:
    """仅外部 mysql/postgres：服务里不应出现 sqlite 驱动映射。"""
    source = inspect.getsource(service_module)
    assert "sqlite" not in source.lower()


async def test_create_encrypts_password() -> None:
    crud = _FakeCrud()
    service = _service_with(crud)
    data = DbConnectionCreateSchema(name="prod", db_type="mysql", host="h", port=3306, username="u", password="secret")
    out = await service.create(data)
    assert crud.created and crud.created[0]["password"] != "secret"
    assert CryptoUtil.decrypt(crud.created[0]["password"]) == "secret"
    assert not hasattr(out, "password") or "password" not in out.model_dump()


async def test_update_without_password_keeps_original() -> None:
    crud = _FakeCrud(row=_row())
    service = _service_with(crud)
    data = DbConnectionUpdateSchema(name="prod", db_type="mysql", host="h", port=3306, username="u")
    await service.update(1, data)
    assert "password" not in crud.updated[0], "未传密码时不应写入 password 字段"


async def test_run_query_requires_confirmation_for_writes() -> None:
    service = _service_with(_FakeCrud(row=_row()))
    with pytest.raises(CustomException, match="写操作需要先确认"):
        await service.run_query(1, "update sys_user set name = 'x'", confirmed=False)


async def test_run_query_rejects_multi_statement_write() -> None:
    service = _service_with(_FakeCrud(row=_row()))
    with pytest.raises(CustomException, match="一次只能执行一条语句"):
        await service.run_query(1, "delete from t; drop table t", confirmed=True)


async def test_run_query_rejects_unsafe_readonly_before_connecting() -> None:
    service = _service_with(_FakeCrud(row=_row()))
    with pytest.raises(CustomException):
        await service.run_query(1, "select 1; drop table t", confirmed=False)


async def test_run_query_rejects_disabled_connection() -> None:
    service = _service_with(_FakeCrud(row=_row(status=1)))
    with pytest.raises(CustomException, match="已停用"):
        await service.run_query(1, "select 1")
