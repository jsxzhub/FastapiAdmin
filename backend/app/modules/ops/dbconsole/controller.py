"""SQL 控制台接口（仅外部数据库连接）。"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Security, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_schema import AuthSchema
from app.core.dependencies import AuthPermission, db_getter
from app.core.router_class import OperationLogRoute

from .schema import (
    DbConnectionCreateSchema,
    DbConnectionOutSchema,
    DbConnectionTestSchema,
    DbConnectionUpdateSchema,
    DbObjectSchema,
    DbQueryResultSchema,
    DbQuerySchema,
)
from .service import DbConsoleService

DbConsoleRouter = APIRouter(route_class=OperationLogRoute, prefix="/dbconsole/connection", tags=["SQL控制台"])


@DbConsoleRouter.get("/list", summary="查询数据库连接列表", response_model=ResponseSchema[list[DbConnectionOutSchema]])
async def list_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).get_list()
    return SuccessResponse(data=result, msg="查询连接列表成功")


@DbConsoleRouter.get("/detail/{id}", summary="查询数据库连接详情", response_model=ResponseSchema[DbConnectionOutSchema])
async def detail_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).detail(id=id)
    return SuccessResponse(data=result, msg="查询连接详情成功")


@DbConsoleRouter.post("/create", status_code=status.HTTP_201_CREATED, summary="新增数据库连接", response_model=ResponseSchema[DbConnectionOutSchema])
async def create_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:create"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[DbConnectionCreateSchema, Body(description="连接配置")],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).create(data=data)
    return SuccessResponse(data=result, msg="新增连接成功")


@DbConsoleRouter.put("/update/{id}", summary="修改数据库连接", response_model=ResponseSchema[DbConnectionOutSchema])
async def update_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
    data: Annotated[DbConnectionUpdateSchema, Body(description="连接配置")],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).update(id=id, data=data)
    return SuccessResponse(data=result, msg="修改连接成功")


@DbConsoleRouter.delete("/delete", summary="删除数据库连接", response_model=ResponseSchema[None])
async def delete_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:delete"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    ids: Annotated[list[int], Body(description="连接ID列表")],
) -> JSONResponse:
    await DbConsoleService(auth, db).delete(ids=ids)
    return SuccessResponse(msg="删除连接成功")


@DbConsoleRouter.post("/test", summary="按填写中的凭据测试连接（不落库）", response_model=ResponseSchema[bool])
async def test_db_connection_config_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:update"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    data: Annotated[DbConnectionTestSchema, Body(description="连接配置")],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).test_connection(data)
    return SuccessResponse(data=result, msg="连接成功")


@DbConsoleRouter.post("/test/{id}", summary="测试已保存的连接", response_model=ResponseSchema[bool])
async def test_db_connection_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:conn:query"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).test_by_id(id=id)
    return SuccessResponse(data=result, msg="连接成功")


@DbConsoleRouter.get("/{id}/databases", summary="查询库/schema 列表", response_model=ResponseSchema[list[DbObjectSchema]])
async def list_db_databases_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:query:execute"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).list_databases(id=id)
    return SuccessResponse(data=result, msg="查询库列表成功")


@DbConsoleRouter.get("/{id}/tables", summary="查询表列表", response_model=ResponseSchema[list[DbObjectSchema]])
async def list_db_tables_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:query:execute"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
    database: Annotated[str | None, Query(max_length=128, description="库/schema 名")] = None,
) -> JSONResponse:
    result = await DbConsoleService(auth, db).list_tables(id=id, database=database)
    return SuccessResponse(data=result, msg="查询表列表成功")


@DbConsoleRouter.post("/{id}/query", summary="执行 SQL（只读校验；写需 confirmed）", response_model=ResponseSchema[DbQueryResultSchema])
async def run_db_query_controller(
    auth: Annotated[AuthSchema, Security(AuthPermission(["module_ops:dbconsole:query:execute"]))],
    db: Annotated[AsyncSession, Depends(db_getter)],
    id: Annotated[int, Path(description="连接ID", ge=1)],
    data: Annotated[DbQuerySchema, Body(description="SQL 与确认标记")],
) -> JSONResponse:
    result = await DbConsoleService(auth, db).run_query(id=id, sql=data.sql, confirmed=data.confirmed)
    return SuccessResponse(data=result, msg="执行成功")
