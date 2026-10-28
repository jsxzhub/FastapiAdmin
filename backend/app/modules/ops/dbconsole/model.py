"""SQL 控制台：**外部**数据库连接（仅 mysql / postgres）。

按需求**不包含**本地/内置数据库（例如 FastHub 的 `data/fasthub.db` 这类本机 SQLite 浏览）。
密码用 Fernet 加密存储（CryptoUtil），出参永不返回密码，只回 `has_password`。
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class DbConnectionModel(ModelMixin, UserMixin):
    """外部数据库连接配置"""

    __tablename__: str = "dbconsole_connection"
    __table_args__: dict[str, str] = {"comment": "SQL控制台外部数据库连接表"}

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="连接名称")
    db_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="数据库类型(mysql/postgres)")
    host: Mapped[str] = mapped_column(String(255), nullable=False, comment="主机地址")
    port: Mapped[int] = mapped_column(Integer, nullable=False, comment="端口")
    username: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户名")
    password: Mapped[str] = mapped_column(Text, nullable=False, comment="密码(Fernet加密)")
    database: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True, comment="默认库名")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="状态(0:启用 1:停用)")
    description: Mapped[str | None] = mapped_column(Text, default=None, nullable=True, comment="备注")
