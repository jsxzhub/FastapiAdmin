"""SQL 控制台数据契约。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DbConnectionBaseSchema(BaseModel):
    """连接配置公共字段（不含密码）"""

    name: str = Field(..., min_length=1, max_length=64, description="连接名称（唯一）")
    db_type: Literal["mysql", "postgres"] = Field(..., description="数据库类型（仅外部连接：mysql/postgres）")
    host: str = Field(..., min_length=1, max_length=255, description="主机地址")
    port: int = Field(..., ge=1, le=65535, description="端口")
    username: str = Field(..., min_length=1, max_length=128, description="用户名")
    database: str | None = Field(None, max_length=128, description="默认库名（可空）")
    description: str | None = Field(None, max_length=500, description="备注")


class DbConnectionCreateSchema(DbConnectionBaseSchema):
    """新建连接"""

    password: str = Field(..., min_length=1, max_length=500, description="密码（加密存储）")


class DbConnectionUpdateSchema(DbConnectionBaseSchema):
    """修改连接（不传密码表示不修改）"""

    password: str | None = Field(None, max_length=500, description="密码；不传表示不修改")


class DbConnectionTestSchema(BaseModel):
    """按填写中的凭据测试连接（不落库）"""

    db_type: Literal["mysql", "postgres"] = Field(..., description="数据库类型")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=500)
    database: str | None = Field(None, max_length=128)


class DbConnectionOutSchema(DbConnectionBaseSchema):
    """连接出参（不含密码）"""

    id: int = Field(..., description="连接ID")
    status: int = Field(..., description="状态(0:启用 1:停用)")
    has_password: bool = Field(False, description="是否已设置密码")

    model_config = ConfigDict(from_attributes=True)


class DbQuerySchema(BaseModel):
    """执行 SQL"""

    sql: str = Field(..., min_length=1, max_length=20000, description="SQL 语句")
    confirmed: bool = Field(False, description="写操作必须显式确认（true）")


class DbQueryResultSchema(BaseModel):
    """SQL 执行结果"""

    sql: str = Field(..., description="实际执行的 SQL")
    read_only: bool = Field(..., description="是否为只读语句")
    columns: list[str] = Field(default_factory=list, description="列名")
    rows: list[list[Any]] = Field(default_factory=list, description="行（最多 200 行）")
    rowcount: int = Field(0, description="影响行数/返回行数")
    masked_columns: list[str] = Field(default_factory=list, description="已脱敏的敏感列")
    truncated: bool = Field(False, description="是否因行数上限被截断")
    elapsed_ms: int = Field(0, description="耗时（毫秒）")


class DbObjectSchema(BaseModel):
    """库/表名"""

    name: str = Field(..., description="名称")
