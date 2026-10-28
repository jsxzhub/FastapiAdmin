"""SQL 控制台只读校验 / 敏感列脱敏 / 值序列化测试。"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import CustomException
from app.modules.ops.dbconsole.sql_guard import (
    assert_read_only,
    is_read_only,
    is_single_statement,
    mask_rows,
    strip_comments,
    to_jsonable,
)


@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT * FROM sys_user LIMIT 10;",
        "show tables",
        "explain select 1",
        "with x as (select 1 as a) select * from x",
        "/* 注释 */ select now()",
        "-- 行注释\nselect 1",
    ],
)
def test_read_only_sql_is_accepted(sql: str) -> None:
    assert is_read_only(sql) is True
    assert assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "update sys_user set name = 'x'",
        "delete from sys_user",
        "drop table sys_user",
        "with x as (select 1) delete from sys_user",
        "select 1 into outfile '/tmp/a'",
        "select 1; drop table sys_user",
        "select sleep(5)",
        "select pg_sleep(5)",
        "   ",
    ],
)
def test_unsafe_sql_is_rejected(sql: str) -> None:
    with pytest.raises(CustomException):
        assert_read_only(sql)


def test_strip_comments_removes_hidden_write() -> None:
    assert "delete" not in strip_comments("select 1 -- delete from t").lower()
    assert "delete" not in strip_comments("select 1 /* delete from t */").lower()


def test_single_statement_detection() -> None:
    assert is_single_statement("select 1") is True
    assert is_single_statement("select 1;") is True
    assert is_single_statement("select 1; select 2") is False


def test_mask_rows_masks_sensitive_columns() -> None:
    columns = ["id", "username", "password", "api_key"]
    rows = [[1, "alice", "hash", "sk-1"], [2, "bob", None, "sk-2"]]
    masked_rows, masked_columns = mask_rows(columns, rows)
    assert masked_columns == ["password", "api_key"]
    assert masked_rows[0][2] == "••••••" and masked_rows[0][3] == "••••••"
    assert masked_rows[1][2] is None, "NULL 不脱敏（保持 NULL 语义）"
    assert masked_rows[0][1] == "alice", "非敏感列不受影响"


def test_mask_rows_noop_without_sensitive_columns() -> None:
    rows = [[1, "alice"]]
    masked_rows, masked_columns = mask_rows(["id", "username"], rows)
    assert masked_columns == []
    assert masked_rows == rows


def test_to_jsonable_converts_db_types() -> None:
    assert to_jsonable(datetime(2026, 1, 2, 3, 4, 5)).startswith("2026-01-02T03:04:05")
    assert to_jsonable(date(2026, 1, 2)) == "2026-01-02"
    assert to_jsonable(Decimal("1.25")) == "1.25"
    assert to_jsonable(b"abc") == "abc"
    assert to_jsonable({"a": 1}) == "{'a': 1}"
    assert len(to_jsonable("x" * 5000)) == 2000
