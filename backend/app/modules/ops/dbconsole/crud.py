from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_crud import CRUDBase
from app.core.base_schema import AuthSchema

from .model import DbConnectionModel
from .schema import DbConnectionCreateSchema, DbConnectionUpdateSchema


class DbConnectionCRUD(CRUDBase[DbConnectionModel, DbConnectionCreateSchema, DbConnectionUpdateSchema]):
    """SQL 控制台连接数据层"""

    def __init__(self, auth: AuthSchema, db: AsyncSession) -> None:
        super().__init__(model=DbConnectionModel, auth=auth, db=db)
