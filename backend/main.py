import os
from typing import Annotated, Literal

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from typer.main import Typer

# 注意：禁止在模块顶层导入 app.*。
# 导入 app 包会执行 app/__init__.py 并提前固化 settings，
# 导致 --env 在 settings 加载之后才生效（reload 模式下父子进程配置不一致）。

fastapiadmin_cli: Typer = typer.Typer()
alembic_cfg: Config = Config(file_="alembic.ini")


@fastapiadmin_cli.command(
    name="run",
    help="启动 FastapiAdmin 服务, 运行 python(或uv run) main.py run --env=dev 不加参数默认 dev 环境",
)
def run(
    env: Annotated[Literal["dev", "prod"], typer.Option("--env", help="运行环境 (dev, prod)")] = "dev",
) -> None:
    """按指定环境加载配置并启动 Uvicorn（dev 环境 DEBUG=True 自动开启 reload）。

    参数:
    - env (str): 运行环境（dev/prod），对应 `--env`。

    返回:
    - None
    """
    os.environ["ENVIRONMENT"] = env

    from app.utils.banner import worship
    typer.secho(message=f"{worship()}", fg=typer.colors.GREEN)
    from app.config.setting import settings

    uvicorn.run(
        app="app:create_app",
        factory=True,
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        # 只监听代码目录，避免把 logs/ 纳入热重载监听：
        # 日志文件写在 logs/fastapiadmin.log，而 watchfiles 的 "change detected" 调试日志
        # 又会经 InterceptHandler 写回同一个文件，形成自我激励的死循环
        reload_dirs=["app"] if settings.DEBUG else None,
        workers=settings.WORKERS,
        log_config=None,
        timeout_graceful_shutdown=5,
    )


@fastapiadmin_cli.command(
    name="revision",
    help="生成新的 Alembic 迁移脚本, 运行 python(或uv run) main.py revision --env=dev",
)
def revision(
    env: Annotated[Literal["dev", "prod"], typer.Option("--env", help="运行环境 (dev, prod)")] = "dev",
    message: Annotated[str, typer.Option("--message", "-m", help="迁移说明（进入迁移文件名 slug）")] = "迁移脚本",
) -> None:
    """使用 Alembic 自动生成迁移脚本（autogenerate）。

    参数:
    - env (str): 运行环境（dev/prod），用于加载对应数据库模型元数据。
    - message (str): 迁移说明，写入迁移文件 message 与文件名 slug。

    返回:
    - None
    """
    os.environ["ENVIRONMENT"] = env
    command.revision(config=alembic_cfg, autogenerate=True, message=message)
    typer.echo(message="迁移脚本已生成")


@fastapiadmin_cli.command(
    name="upgrade",
    help="应用最新的 Alembic 迁移, 运行 python(或uv run) main.py upgrade --env=dev",
)
def upgrade(
    env: Annotated[Literal["dev", "prod"], typer.Option("--env", help="运行环境 (dev, prod)")] = "dev",
) -> None:
    """将数据库升级到 Alembic 最新版本（head）。

    参数:
    - env (str): 运行环境（dev/prod）。

    返回:
    - None
    """
    os.environ["ENVIRONMENT"] = env
    command.upgrade(config=alembic_cfg, revision="head")
    typer.echo(message="所有迁移已应用。")


if __name__ == "__main__":
    fastapiadmin_cli()
