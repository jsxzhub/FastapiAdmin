"""SQL 控制台服务：外部数据库连接管理 + 只读/确认写查询。

安全边界：
- 只允许 **mysql / postgres 外部连接**（不提供本地/内置库）；
- 查询分两条路径：只读语句走 ``assert_read_only`` 严格校验且**不提交**（写操作即使绕过校验也会随连接回滚）；
  写语句必须 ``confirmed=true`` 且只允许单条语句；
- 结果最多 200 行，敏感列打码；查询有 30s 超时；
- 密码用 CryptoUtil 加密存储，出参永不含密码。
"""

import asyncio
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config.db_url import build_sqlalchemy_url
from app.core.base_schema import AuthSchema
from app.core.exceptions import CustomException
from app.utils.crypto_util import CryptoUtil

from .crud import DbConnectionCRUD
from .model import DbConnectionModel
from .schema import (
    DbConnectionCreateSchema,
    DbConnectionOutSchema,
    DbConnectionTestSchema,
    DbConnectionUpdateSchema,
    DbObjectSchema,
    DbQueryResultSchema,
)
from .sql_guard import assert_read_only, is_read_only, is_single_statement, mask_rows, to_jsonable

_QUERY_TIMEOUT = 30
_CONNECT_TIMEOUT = 10
_MAX_ROWS = 200
_DRIVERS = {"mysql": "mysql+aiomysql", "postgres": "postgresql+asyncpg"}


def build_url(db_type: str, host: str, port: int, username: str, password: str, database: str | None) -> str:
    """构造 SQLAlchemy 异步 DSN（密码/库名做 URL 转义）。"""
    driver = _DRIVERS.get(db_type)
    if driver is None:
        raise CustomException(msg=f"不支持的数据库类型: {db_type}（仅 mysql/postgres）")
    return build_sqlalchemy_url(
        driver,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )


class DbConsoleService:
    """SQL 控制台服务"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        self.auth = auth
        self.db = db

    def _crud(self) -> DbConnectionCRUD:
        return DbConnectionCRUD(self.auth, self.db)

    # ── 连接管理 ──────────────────────────────────────────────────────

    @staticmethod
    def _to_out(row: DbConnectionModel) -> DbConnectionOutSchema:
        out = DbConnectionOutSchema.model_validate(row)
        out.has_password = bool(row.password)
        return out

    async def get_list(self) -> list[DbConnectionOutSchema]:
        rows = await self._crud().get_list()
        return [self._to_out(row) for row in rows]

    async def detail(self, id: int) -> DbConnectionOutSchema:
        row = await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        return self._to_out(row)

    async def create(self, data: DbConnectionCreateSchema) -> DbConnectionOutSchema:
        if await self._crud().get(name=data.name):
            raise CustomException(msg="创建失败，连接名称已存在")
        payload = data.model_dump()
        payload["password"] = CryptoUtil.encrypt(data.password)
        row = await self._crud().create(data=payload)
        return self._to_out(row)

    async def update(self, id: int, data: DbConnectionUpdateSchema) -> DbConnectionOutSchema:
        await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        exist = await self._crud().get(name=data.name)
        if exist and exist.id != id:
            raise CustomException(msg="更新失败，连接名称已存在")
        payload = data.model_dump(exclude_unset=True)
        if payload.get("password"):
            payload["password"] = CryptoUtil.encrypt(payload["password"])
        else:
            payload.pop("password", None)
        row = await self._crud().update(id=id, data=payload)
        return self._to_out(row)

    async def delete(self, ids: list[int]) -> None:
        await self._crud().delete(ids=ids)

    # ── 探测 ──────────────────────────────────────────────────────────

    async def test_connection(self, data: DbConnectionTestSchema | DbConnectionModel) -> bool:
        """按给定凭据执行 SELECT 1（连接失败抛 CustomException）。"""
        if isinstance(data, DbConnectionModel):
            password = CryptoUtil.decrypt(data.password)
            url = build_url(data.db_type, data.host, data.port, data.username, password, data.database)
        else:
            url = build_url(data.db_type, data.host, data.port, data.username, data.password, data.database)
        await self._probe(url)
        return True

    async def test_by_id(self, id: int) -> bool:
        row = await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        return await self.test_connection(row)

    @staticmethod
    async def _probe(url: str) -> None:
        engine = create_async_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        try:
            async with engine.connect() as conn:
                await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=_CONNECT_TIMEOUT)
        except TimeoutError as exc:
            raise CustomException(msg=f"连接超时（>{_CONNECT_TIMEOUT}s）") from exc
        except CustomException:
            raise
        except Exception as exc:
            reason = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            raise CustomException(msg=f"连接失败: {reason}") from exc
        finally:
            await engine.dispose()

    # ── 库/表浏览 ─────────────────────────────────────────────────────

    async def _fetch(self, row: DbConnectionModel, sql: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        """以连接配置执行一条内部查询（受 _QUERY_TIMEOUT 限制）。"""
        password = CryptoUtil.decrypt(row.password)
        url = build_url(row.db_type, row.host, row.port, row.username, password, row.database)
        engine = create_async_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        try:
            async with engine.connect() as conn:
                result = await asyncio.wait_for(conn.execute(text(sql), params or {}), timeout=_QUERY_TIMEOUT)
                return [[to_jsonable(value) for value in record] for record in result.fetchall()]
        except TimeoutError as exc:
            raise CustomException(msg=f"查询超时（>{_QUERY_TIMEOUT}s）") from exc
        except CustomException:
            raise
        except Exception as exc:
            reason = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            raise CustomException(msg=f"查询失败: {reason}") from exc
        finally:
            await engine.dispose()

    async def list_databases(self, id: int) -> list[DbObjectSchema]:
        row = await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        if row.db_type == "mysql":
            sql = "SHOW DATABASES"
        else:
            sql = "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
        rows = await self._fetch(row, sql)
        return [DbObjectSchema(name=str(item[0])) for item in rows if item and item[0] is not None]

    async def list_tables(self, id: int, database: str | None = None) -> list[DbObjectSchema]:
        row = await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        if row.db_type == "mysql":
            schema = database or row.database
            if not schema:
                raise CustomException(msg="MySQL 需要指定库名（或为该连接设置默认库）")
            rows = await self._fetch(
                row,
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema AND table_type = 'BASE TABLE' ORDER BY table_name",
                {"schema": schema},
            )
        else:
            schema = database or "public"
            rows = await self._fetch(
                row,
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema AND table_type = 'BASE TABLE' ORDER BY table_name",
                {"schema": schema},
            )
        return [DbObjectSchema(name=str(item[0])) for item in rows if item and item[0] is not None]

    # ── 执行 SQL ──────────────────────────────────────────────────────

    async def run_query(self, id: int, sql: str, confirmed: bool = False) -> DbQueryResultSchema:
        row = await self._crud().get_or_404(id=id, msg="数据库连接不存在")
        if row.status != 0:
            raise CustomException(msg="该连接已停用")

        raw_sql = (sql or "").strip()
        if not raw_sql:
            raise CustomException(msg="SQL 不能为空")
        read_only = is_read_only(raw_sql)
        if read_only:
            sql_to_run = assert_read_only(raw_sql)
        else:
            if not confirmed:
                raise CustomException(msg="写操作需要先确认（confirmed=true）")
            if not is_single_statement(raw_sql):
                raise CustomException(msg="一次只能执行一条语句")
            sql_to_run = raw_sql.rstrip(";").strip()

        password = CryptoUtil.decrypt(row.password)
        url = build_url(row.db_type, row.host, row.port, row.username, password, row.database)
        engine = create_async_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        started = time.perf_counter()
        try:
            async with engine.connect() as conn:
                result = await asyncio.wait_for(conn.execute(text(sql_to_run)), timeout=_QUERY_TIMEOUT)
                if result.returns_rows:
                    columns = [str(name) for name in result.keys()]
                    fetched = result.fetchmany(_MAX_ROWS + 1)
                    truncated = len(fetched) > _MAX_ROWS
                    rows = [[to_jsonable(value) for value in record] for record in fetched[:_MAX_ROWS]]
                    rows, masked_columns = mask_rows(columns, rows)
                    return DbQueryResultSchema(
                        sql=sql_to_run,
                        read_only=True,
                        columns=columns,
                        rows=rows,
                        rowcount=len(rows),
                        masked_columns=masked_columns,
                        truncated=truncated,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                    )
                # 写语句：显式提交（只读路径永不提交，理论上写操作在此分支）
                await asyncio.wait_for(conn.commit(), timeout=_CONNECT_TIMEOUT)
                return DbQueryResultSchema(
                    sql=sql_to_run,
                    read_only=False,
                    columns=[],
                    rows=[],
                    rowcount=int(result.rowcount or 0),
                    masked_columns=[],
                    truncated=False,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )
        except TimeoutError as exc:
            raise CustomException(msg=f"执行超时（>{_QUERY_TIMEOUT}s）") from exc
        except CustomException:
            raise
        except Exception as exc:
            reason = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            raise CustomException(msg=f"执行失败: {reason}") from exc
        finally:
            await engine.dispose()
