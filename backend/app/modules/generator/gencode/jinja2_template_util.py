import copy
import re
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

from app.common.constant import GenConstant
from app.config.path_conf import TEMPLATE_DIR
from app.config.setting import settings
from app.utils.common_util import CamelCaseUtil, SnakeCaseUtil, compute_menu_route_first_segment
from app.utils.string_util import StringUtil

from .gen_util import GenUtils
from .schema import (
    GenTableColumnOutSchema,
    GenTableOutSchema,
)
from .template_safety import (
    DIALECT_TYPE_IMPORTS,
    column_type_base,
    escape_template_text,
    html_attr,
    pick_sqlalchemy_type,
    safe_ident,
    safe_python_type,
    vue_label,
)

# 哨兵文本：用于「用哨兵值渲染同一模板，得到结构骨架」的落盘前比对
# （见 template_safety.assert_python_structure / assert_text_structure）
SENTINEL_TEXT = "__SAFE_TEXT__"

# 自由文本字段：哨兵化只针对它们（保证结构比对有意义）；标识符/类型/开关/长度等
# 必须保持真实值，否则模板分支会与骨架不一致，产生误报
_SENTINEL_TABLE_TEXT_FIELDS = ("table_name", "table_comment", "function_name", "business_name", "sub_table_name", "description")
_SENTINEL_COLUMN_TEXT_FIELDS = ("column_comment", "dict_type")


class Jinja2TemplateUtil:
    """模板处理工具类
    """

    @classmethod
    def normalize_db_column_type_for_mapping(cls, column_type: str | None) -> str:
        """与 ``GenUtils.get_db_type`` 一致地去掉 COLLATE / UNSIGNED，便于与 ``DB_TO_SQLALCHEMY`` 键匹配。

        参数:
        - column_type (str | None): 原始列类型字符串。

        返回:
        - str: 规范化后的类型片段；空输入返回空字符串。
        """
        ct = (column_type or "").strip()
        if not ct:
            return ""
        collate_pattern = re.compile(r"\s+COLLATE\s+", re.IGNORECASE)
        if collate_pattern.search(ct):
            ct = collate_pattern.split(ct)[0].strip()
        unsigned_pattern = re.compile(r"\s+UNSIGNED", re.IGNORECASE)
        if unsigned_pattern.search(ct):
            ct = unsigned_pattern.sub("", ct).strip()
        return ct

    # 项目路径
    FRONTEND_PROJECT_PATH = "frontend/web"
    BACKEND_PROJECT_PATH = "backend"

    # 环境对象
    _env = None

    @classmethod
    def get_env(cls):
        """获取模板环境对象。

        参数:
        - 无

        返回:
        - Environment: Jinja2 环境对象。
        """
        try:
            if cls._env is None:
                cls._env = Environment(
                    loader=FileSystemLoader(TEMPLATE_DIR),
                    autoescape=False,  # 自动转义HTML
                    trim_blocks=True,  # 删除多余的空行
                    lstrip_blocks=True,  # 删除行首空格
                    keep_trailing_newline=True,  # 保留行尾换行符
                    enable_async=True,  # 开启异步支持
                )
                cls._env.filters.update(
                    {
                        "camel_to_snake": SnakeCaseUtil.camel_to_snake,
                        "snake_to_camel": CamelCaseUtil.snake_to_camel,
                        "get_sqlalchemy_type": cls.get_sqlalchemy_type,
                        "python_to_ts_type": cls.python_type_to_ts_type,
                        # 模板内按上下文安全化（详见 template_safety.py）：
                        # 绝大多数值已在 prepare_context 统一处理，模板里可按需显式调用
                        "py_text": escape_template_text,
                        "py_ident": safe_ident,
                        "py_type": safe_python_type,
                        "vue_label": vue_label,
                        # 静态 HTML 属性值：实体转义（展示保真，不用 \uXXXX）
                        "html_attr": html_attr,
                    },
                )
            return cls._env
        except Exception as e:
            raise RuntimeError(f"初始化Jinja2模板引擎失败: {e}")

    @classmethod
    def get_template(cls, template_path: str) -> Template:
        """获取模板。

        参数:
        - template_path (str): 模板路径。

        返回:
        - Template: Jinja2 模板对象。

        异常:
        - TemplateNotFound: 模板未找到时抛出。
        """
        return cls.get_env().get_template(template_path)

    @classmethod
    def business_name_to_slug(cls, business_name: str | None) -> str:
        """业务路径可含斜杠（如 ``demo/subdir``）用于目录与路由前缀；
        Python 函数/方法名仅使用最后一段并规范为合法 snake_case 片段。

        参数:
        - business_name (str | None): 业务路径或名称。

        返回:
        - str: 用于 Python 标识的 slug，默认 entity。
        """
        s = (business_name or "").strip().strip("/")
        if not s:
            return "entity"
        if "/" in s:
            s = s.split("/")[-1]
        s = re.sub(r"[^a-zA-Z0-9_]", "_", s)
        if not s:
            return "entity"
        if s[0].isdigit():
            s = "_" + s
        return s

    @classmethod
    def business_name_to_path(cls, business_name: str | None) -> str:
        """把 business_name 规范为可用于目录/路由的多段路径（保留 `/`）。

        约定：`business_name` 允许 `a/b/c` 表示多级菜单目录。
        - 目录/路由：使用完整多段
        - 文件名/route_name：使用最后一段 slug（见 `business_name_to_slug`）

        参数:
        - business_name (str | None): 业务路径或名称。

        返回:
        - str: 多段路径字符串（小写 slug），默认 entity。
        """
        s = (business_name or "").strip().strip("/")
        if not s:
            return "entity"
        # 每段都做一次轻度规范（与 schema 的 slug 规则一致：a-z0-9_）
        segs = []
        for raw in [p for p in s.split("/") if p]:
            seg = re.sub(r"[^a-zA-Z0-9_]", "_", raw).lower()
            seg = re.sub(r"_+", "_", seg).strip("_") or "entity"
            if seg[0].isdigit():
                seg = "_" + seg
            segs.append(seg)
        return "/".join(segs) if segs else "entity"

    @classmethod
    def safe_render_schema(cls, gen_table: GenTableOutSchema) -> GenTableOutSchema:
        """构造「仅用于模板渲染」的安全副本。

        生成物是会被执行/被构建链消费的源码（``.py`` 会被 ``app/core/discover.py`` 启动时 import），
        因此所有用户可控文本必须按所处上下文安全化后才能进模板。此处统一处理，
        避免逐个模板/逐个字段遗漏；``autoescape=True`` 不适用（会把生成的代码本身转义坏）。

        **从 schema 进入模板的值按四类显式处理**（实现见 template_safety.py）：
        1. 字符串类（注释/描述/功能名/表名…）→ ``escape_template_text``（``\\uXXXX``，仅用于字符串/注释上下文）；
        2. 标识符类（列名/类名/模块名/python_field）→ ``safe_ident``（含关键字与保留字排除）；
        3. 代码位置类（SQLAlchemy 类型、长度/精度）→ ``pick_sqlalchemy_type``：**只从常量白名单派生**，不接收自由文本；
        4. 路径类（包名/模块名/业务路径/文件名）→ slug/白名单规范化（``business_name_to_path`` 等），不含 ``..`` 与分隔符。
        展示位置（``.vue`` 文本节点与静态属性）另有 ``vue_label``/``html_attr``：HTML 实体转义，保真且不破坏标记结构。

        参数:
        - gen_table (GenTableOutSchema): 原始生成配置（不会被修改）。

        返回:
        - GenTableOutSchema: 深拷贝并按上下文安全化后的副本。
        """
        safe_table = copy.deepcopy(gen_table)
        cls._sanitize_schema_in_place(safe_table, set())
        return safe_table

    @classmethod
    def sentinel_render_schema(cls, gen_table: GenTableOutSchema) -> GenTableOutSchema:
        """构造「哨兵值」副本：自由文本换成固定哨兵（空值保持为空），用于生成结构骨架。

        与 :meth:`safe_render_schema` 的区别：这里不追求可展示/可用，只要求**结构中性**——
        值里不含任何可能改变模板分支或语法结构的字符。用它渲染同一模板得到的 AST/行结构
        即为「该模板的规范骨架」，落盘前与真实产物比对（见 template_safety 的结构闸门）。

        参数:
        - gen_table (GenTableOutSchema): 已安全化的渲染配置。

        返回:
        - GenTableOutSchema: 自由文本字段被替换为哨兵的深拷贝。
        """
        sentinel_table = copy.deepcopy(gen_table)
        cls._sentinelize_schema_in_place(sentinel_table, set())
        return sentinel_table

    @classmethod
    def _sentinelize_schema_in_place(cls, table: GenTableOutSchema, seen: set[int]) -> None:
        """就地哨兵化自由文本字段（标识符/类型/开关/长度保持不变），带环保护。"""
        if table is None or id(table) in seen:
            return
        seen.add(id(table))
        for field in _SENTINEL_TABLE_TEXT_FIELDS:
            if hasattr(table, field):
                setattr(table, field, _sentinelize_value(getattr(table, field)))
        for column in table.columns or []:
            cls._sentinelize_column_in_place(column, seen)
        if table.pk_column is not None:
            cls._sentinelize_column_in_place(table.pk_column, seen)
        if table.sub_table is not None:
            cls._sentinelize_schema_in_place(table.sub_table, seen)

    @staticmethod
    def _sentinelize_column_in_place(column: GenTableColumnOutSchema, seen: set[int]) -> None:
        """就地哨兵化字段级自由文本（列名/类型/长度等保持原值）。"""
        if column is None or id(column) in seen:
            return
        seen.add(id(column))
        for field in _SENTINEL_COLUMN_TEXT_FIELDS:
            if hasattr(column, field):
                setattr(column, field, _sentinelize_value(getattr(column, field)))

    @classmethod
    def iter_free_text_values(cls, gen_table: GenTableOutSchema) -> list[str]:
        """枚举本次渲染里会进入模板的**自由文本值**（与哨兵化字段一一对应，按同样顺序）。

        供 ``.vue``/``.ts`` 的行结构比对使用：把真实值与哨兵都抹成占位符后再逐行比较。

        参数:
        - gen_table (GenTableOutSchema): 已安全化的渲染配置。

        返回:
        - list[str]: 非空自由文本值列表。
        """
        values: list[str] = []
        seen: set[int] = set()

        def walk(table: GenTableOutSchema) -> None:
            if table is None or id(table) in seen:
                return
            seen.add(id(table))
            for field in _SENTINEL_TABLE_TEXT_FIELDS:
                text = getattr(table, field, None)
                if text:
                    values.append(str(text))
            for column in table.columns or []:
                collect_column(column)
            if table.pk_column is not None:
                collect_column(table.pk_column)
            if table.sub_table is not None:
                walk(table.sub_table)

        def collect_column(column: GenTableColumnOutSchema) -> None:
            if column is None or id(column) in seen:
                return
            seen.add(id(column))
            for field in _SENTINEL_COLUMN_TEXT_FIELDS:
                text = getattr(column, field, None)
                if text:
                    values.append(str(text))

        walk(gen_table)
        return values

    @classmethod
    def iter_render_dynamic_values(cls, gen_table: GenTableOutSchema) -> list[str]:
        """返回真实产物里可能出现的**所有动态文本形态**（原值 / 转义值 / 展示形态）。

        供 ``.vue``/``.ts`` 的行结构比对把动态部分抹成占位符：同一个值可能以
        ``escape_template_text``（JS 字符串）、``html_attr``（静态属性）、``vue_label``（文本节点）
        三种形态出现，三者都要抹掉，否则会与骨架产生假阳性。

        参数:
        - gen_table (GenTableOutSchema): 已安全化的渲染配置。

        返回:
        - list[str]: 动态文本形态列表。
        """
        tokens: list[str] = []
        for value in cls.iter_free_text_values(gen_table):
            text = str(value)
            tokens.extend([text, escape_template_text(text), html_attr(text), vue_label(text)])
        return tokens

    @classmethod
    def _sanitize_schema_in_place(cls, table: GenTableOutSchema, seen: set[int]) -> None:
        """就地安全化一张表（表级文本 + 全部字段 + 子表），带环保护。

        参数:
        - table (GenTableOutSchema): 待处理的安全副本（会被修改）。
        - seen (set[int]): 已处理对象 id 集合（主/子表互相引用时防重入）。

        返回:
        - None
        """
        if table is None or id(table) in seen:
            return
        seen.add(id(table))

        # 落进字符串字面量/注释/文档字符串的文本
        table.table_name = escape_template_text(table.table_name)
        table.table_comment = escape_template_text(table.table_comment)
        table.function_name = escape_template_text(table.function_name)
        # 落进标识符位置的值（类名 / 模块名 / 包名 / 外键列名）
        table.class_name = safe_ident(table.class_name, default="")
        table.module_name = safe_ident(table.module_name, default="")
        table.package_name = safe_ident(table.package_name, default="")
        table.sub_table_fk_name = safe_ident(table.sub_table_fk_name, default="")
        # 业务名允许 a/b 多段，且参与目录派生，按文本处理即可（派生见 prepare_context）
        table.business_name = escape_template_text(table.business_name)
        table.sub_table_name = escape_template_text(table.sub_table_name)

        for column in table.columns or []:
            cls._sanitize_column_in_place(column, seen)
        # pk_column 通常就是 columns 里的同一个对象（见 set_pk_column），必须靠 seen 去重，
        # 否则同一字段被转义两次（\u0027 → \u005cu0027），产物里的文本会变形
        if table.pk_column is not None:
            cls._sanitize_column_in_place(table.pk_column, seen)
        if table.sub_table is not None:
            cls._sanitize_schema_in_place(table.sub_table, seen)

    @staticmethod
    def _sanitize_column_in_place(column: GenTableColumnOutSchema, seen: set[int]) -> None:
        """就地安全化单个字段：列名/类型注解按标识符处理，注释/字典类型按文本转义。

        参数:
        - column (GenTableColumnOutSchema): 待处理的安全副本（会被修改）。
        - seen (set[int]): 已处理对象 id 集合（同一字段被 columns 与 pk_column 同时引用时防重复转义）。

        返回:
        - None
        """
        if column is None or id(column) in seen:
            return
        seen.add(id(column))
        column.column_name = safe_ident(column.column_name, default="")
        column.python_type = safe_python_type(column.python_type)
        column.python_field = safe_ident(column.python_field, default="")
        column.column_comment = escape_template_text(column.column_comment)
        column.dict_type = escape_template_text(column.dict_type)

    @classmethod
    def prepare_context(cls, gen_table: GenTableOutSchema) -> dict[str, Any]:
        """准备模板变量。

        参数:
        - gen_table (GenTableOutSchema): 生成表的配置信息。

        返回:
        - Dict[str, Any]: 模板上下文字典。
        """
        # 处理options为None的情况
        # if not gen_table.options:
        #     raise ValueError('请先完善生成配置信息')
        # 目录/文件名派生值仍按原始业务名计算，保证既有产物路径不变；
        # 其余进入模板的内容一律取安全副本（详见 template_safety.py）。
        business_name_raw = (gen_table.business_name or "").strip()
        business_path = cls.business_name_to_path(business_name_raw)
        business_name_slug = cls.business_name_to_slug(business_name_raw)
        gen_table = cls.safe_render_schema(gen_table)

        class_name = gen_table.class_name or ""
        package_name = (gen_table.package_name or "").strip()
        module_name = (gen_table.module_name or "").strip()
        business_name = (gen_table.business_name or "").strip()
        function_name = gen_table.function_name or ""

        # 生成规则（对齐 module_example/demo）：
        # - 分系统根：package_name = module_xxx
        # - 目录固定为：module_xxx / module_name（不再额外使用业务名作为目录层级）
        # - 权限前缀固定为：module_xxx:module_name（操作在模板里再拼 :query/:create...）
        permission_prefix = ":".join([s for s in [package_name, module_name] if s])
        api_route_prefix = cls.get_api_route_prefix(package_name)

        _cols = gen_table.columns or []
        table_column_names = frozenset(c.column_name for c in _cols if getattr(c, "column_name", None))
        has_dict_column = any(getattr(c, "dict_type", None) for c in _cols)
        has_image_column = any(getattr(c, "html_type", None) == "imageUpload" for c in _cols)
        has_json_column = any(getattr(c, "python_type", None) == "dict" for c in _cols)

        sub_class_name = ""
        sub_model_class_name = ""
        sub_rel_list_name = ""
        parent_rel_name = ""
        if gen_table.sub and gen_table.sub_table:
            st = gen_table.sub_table
            scn = (st.class_name or GenUtils.convert_class_name(gen_table.sub_table_name or "")).strip()
            sub_class_name = scn
            sub_model_class_name = f"{scn}Model"
            sub_rel_list_name = f"{SnakeCaseUtil.camel_to_snake(scn)}_list"
            parent_rel_name = SnakeCaseUtil.camel_to_snake(gen_table.class_name or "")

        context = {
            "table_name": gen_table.table_name or "",
            "table_comment": gen_table.table_comment or "",
            "function_name": function_name if StringUtil.is_not_empty(function_name) else "【请填写功能名称】",
            "class_name": class_name,
            "module_name": module_name,
            "business_name": business_name,
            "business_path": business_path,
            "business_file": business_name_slug,
            "business_name_slug": business_name_slug,
            "base_package": cls.get_package_prefix(package_name),
            "package_name": package_name,
            "plugin_name": package_name.removeprefix("module_"),
            "menu_route_first_segment": cls.get_menu_route_first_segment(gen_table),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pk_column": gen_table.pk_column,
            "model_import_list": cls.get_model_import_list(gen_table),
            "schema_import_list": cls.get_schema_import_list(gen_table),
            "permission_prefix": permission_prefix,
            "api_route_prefix": api_route_prefix,
            "columns": gen_table.columns or [],
            "table_column_names": table_column_names,
            "table": gen_table,
            "dicts": cls.get_dicts(gen_table),
            "db_type": settings.DATABASE_TYPE,
            "column_not_add_show": GenConstant.COLUMNNAME_NOT_ADD_SHOW,
            "column_not_edit_show": GenConstant.COLUMNNAME_NOT_EDIT_SHOW,
            "parent_menu_id": int(gen_table.parent_menu_id) if gen_table.parent_menu_id else None,
            "is_sub_entity": False,
            "sub_class_name": sub_class_name,
            "sub_model_class_name": sub_model_class_name,
            "sub_module_name": (gen_table.sub_table.module_name if gen_table.sub and gen_table.sub_table else ""),
            "sub_rel_list_name": sub_rel_list_name,
            "parent_rel_name": parent_rel_name,
            "parent_list_rel_name": "",
            "parent_table_name": "",
            "parent_model_class_name": "",
            # 数据表实际主键列名（用于生成前端行键等；ModelMixin 仍默认带 id 字段）
            "pk_column_name": (gen_table.pk_column.column_name if gen_table.pk_column else None) or "id",
            "parent_pk_column_name": (gen_table.pk_column.column_name if gen_table.pk_column else None) or "id",
            "sub_table_fk_name": "",
            "has_dict_column": has_dict_column,
            "has_image_column": has_image_column,
            "has_json_column": has_json_column,
        }

        return context

    @classmethod
    def get_menu_route_first_segment(cls, gen_table: GenTableOutSchema) -> str:
        """前端页面路由首段（与写入菜单 ``route_path`` 第一段一致）：始终为 ``module_xxx``。"""
        pid = int(gen_table.parent_menu_id) if gen_table.parent_menu_id is not None else None
        return compute_menu_route_first_segment(
            pid,
            gen_table.package_name or "",
            gen_table.module_name,
        )

    @classmethod
    def prepare_sub_render_context(cls, parent: GenTableOutSchema, sub: GenTableOutSchema) -> dict[str, Any]:
        """子表业务代码渲染上下文（与主表同模块、独立业务目录）。

        参数:
        - parent (GenTableOutSchema): 主表配置。
        - sub (GenTableOutSchema): 子表配置。

        返回:
        - dict[str, Any]: 子表模板上下文字典。
        """
        ctx = cls.prepare_context(sub)
        # 父表字段同样进入模板（parent_* / relationship 实参），必须取自安全副本
        parent_safe = cls.safe_render_schema(parent)
        sub_safe = cls.safe_render_schema(sub)
        scn = (sub_safe.class_name or GenUtils.convert_class_name(sub_safe.table_name or "")).strip()
        ctx["is_sub_entity"] = True
        ctx["parent_class_name"] = parent_safe.class_name or ""
        ctx["parent_model_class_name"] = f"{parent_safe.class_name}Model"
        ctx["parent_table_name"] = parent_safe.table_name or ""
        ctx["parent_pk_column_name"] = (parent_safe.pk_column.column_name if parent_safe.pk_column else None) or "id"
        ctx["parent_rel_name"] = SnakeCaseUtil.camel_to_snake(parent_safe.class_name or "parent")
        ctx["parent_list_rel_name"] = f"{SnakeCaseUtil.camel_to_snake(scn)}_list"
        ctx["sub_table_fk_name"] = (parent_safe.sub_table_fk_name or "").strip()
        ctx["model_import_list"] = cls.get_model_import_list(sub_safe, is_sub_entity=True)
        ctx["schema_import_list"] = cls.get_schema_import_list(sub_safe)
        return ctx

    @classmethod
    def get_template_list(cls):
        """获取主表模板列表。

        参数:
        - 无
        返回:
        - List[str]: 模板路径列表。
        """
        templates = [
            "python/controller.py.jinja2",
            "python/service.py.jinja2",
            "python/crud.py.jinja2",
            "python/schema.py.jinja2",
            "python/model.py.jinja2",
            "python/__init__.py.jinja2",
            "python/package_init.py.jinja2",
            "python/plugin.toml.jinja2",
            "ts/api.ts.jinja2",
            "vue/index.vue.jinja2",
        ]
        return templates

    @classmethod
    def get_sub_table_template_list(cls):
        """获取子表模板列表（仅 model / schema / __init__，不含 controller/service/crud/vue/api）。

        参数:
        - 无

        返回:
        - List[str]: 子表模板路径列表。
        """
        return [
            "python/model.py.jinja2",
            "python/schema.py.jinja2",
            "python/__init__.py.jinja2",
        ]

    @classmethod
    def get_file_name(cls, template: str, gen_table: GenTableOutSchema):
        """根据模板生成文件名。

        参数:
        - template (str): 模板路径字符串。
        - gen_table (GenTableOutSchema): 生成表的配置信息。

        返回:
        - str: 模板生成的文件名。

        异常:
        - ValueError: 当无法生成有效文件名时抛出。
        """
        package_name = (gen_table.package_name or "").strip()
        module_name = (gen_table.module_name or "").strip()

        if not package_name:
            raise ValueError(f"无法为模板 {template} 生成文件名：包名未设置")
        if not module_name:
            raise ValueError(f"无法为模板 {template} 生成文件名：模块名未设置")

        # 目录固定为：module_xxx/{module_name}
        backend_base = f"{cls.BACKEND_PROJECT_PATH}/app/plugin/{package_name}"
        frontend_view_base = f"{cls.FRONTEND_PROJECT_PATH}/src/views/{package_name}"
        frontend_api_base = f"{cls.FRONTEND_PROJECT_PATH}/src/api/{package_name}"

        backend_dir = f"{backend_base}/{module_name}"
        view_dir = f"{frontend_view_base}/{module_name}"
        api_path = f"{frontend_api_base}/{module_name}.ts"

        template_mapping = {
            "controller.py.jinja2": f"{backend_dir}/controller.py",
            "service.py.jinja2": f"{backend_dir}/service.py",
            "crud.py.jinja2": f"{backend_dir}/crud.py",
            "schema.py.jinja2": f"{backend_dir}/schema.py",
            "model.py.jinja2": f"{backend_dir}/model.py",
            "__init__.py.jinja2": f"{backend_dir}/__init__.py",
            "package_init.py.jinja2": f"{backend_base}/__init__.py",
            "plugin.toml.jinja2": f"{backend_base}/plugin.toml",
            "api.ts.jinja2": api_path,
            "index.vue.jinja2": f"{view_dir}/index.vue",
        }

        # 查找匹配的模板路径
        for key, path in template_mapping.items():
            if key in template:
                return path

        # 遍历完所有映射都没找到匹配项，才抛出异常
        raise ValueError(f"未找到模板 '{template}' 的路径映射")

    @classmethod
    def get_package_prefix(cls, package_name: str) -> str:
        """获取包前缀。

        参数:
        - package_name (str): 包名。

        返回:
        - str: 包前缀。
        """
        # 修复：当包名中不存在'.'时，直接返回原包名
        return package_name[: package_name.rfind(".")] if "." in package_name else package_name

    @classmethod
    def get_schema_import_list(cls, gen_table: GenTableOutSchema):
        """获取 schema 模板所需的 Python 导入语句集合。

        参数:
        - gen_table (GenTableOutSchema): 生成表配置（含主子表列）。

        返回:
        - set[str]: 导入语句字符串集合。
        """
        columns = gen_table.columns or []
        import_list = set()
        has_datetime_import = False
        has_date_import = False
        has_time_import = False

        for column in columns:
            # 处理datetime类型的导入
            if column.python_type and column.python_type in GenConstant.TYPE_DATE:
                if column.python_type == "datetime":
                    has_datetime_import = True
                elif column.python_type == "date":
                    has_date_import = True
                elif column.python_type == "time":
                    has_time_import = True
            elif column.python_type == GenConstant.TYPE_DECIMAL:
                import_list.add("from decimal import Decimal")

        if gen_table.sub and gen_table.sub_table and gen_table.sub_table.columns:
            sub_columns = gen_table.sub_table.columns or []
            for sub_column in sub_columns:
                # 处理datetime类型的导入
                if sub_column.python_type and sub_column.python_type in GenConstant.TYPE_DATE:
                    if sub_column.python_type == "datetime":
                        has_datetime_import = True
                    elif sub_column.python_type == "date":
                        has_date_import = True
                    elif sub_column.python_type == "time":
                        has_time_import = True
                elif sub_column.python_type == GenConstant.TYPE_DECIMAL:
                    import_list.add("from decimal import Decimal")

        # 添加datetime导入
        if has_datetime_import:
            import_list.add("from datetime import datetime")
        if has_date_import:
            import_list.add("from datetime import date")
        if has_time_import:
            import_list.add("from datetime import time")

        return import_list

    @classmethod
    def get_model_import_list(cls, gen_table: GenTableOutSchema, *, is_sub_entity: bool = False) -> list[str]:
        """获取 model 模板所需的 Python 导入语句列表（含合并后的 sqlalchemy 导入）。

        参数:
        - gen_table (GenTableOutSchema): 生成表配置。
        - is_sub_entity (bool): 是否为子表独立生成（含外键与 relationship）。

        返回:
        - list[str]: 导入语句列表。
        """
        columns = gen_table.columns or []
        import_list = set()
        has_datetime_import = False
        has_date_import = False
        has_time_import = False

        # 基类 ModelMixin/UserMixin 已定义的列，无需导入 SQLAlchemy 类型
        _BASE_MODEL_COLUMNS = {
            "id",
            "uuid",
            "created_time",
            "updated_time",
            "created_id",
            "updated_id",
            "is_deleted",
            "deleted_time",
            "deleted_id",
        }

        for column in columns:
            if column.column_name in _BASE_MODEL_COLUMNS:
                # id 列类型与基类主键(Integer)不一致时（如 MySQL bigint 自增/雪花 ID），
                # 模板会显式覆盖 id 字段，此处需补上对应 SQLAlchemy 类型的导入；
                # 其余基类字段（uuid/审计字段等）由 ModelMixin/UserMixin 提供，无需导入
                if column.column_name == "id" and column.is_pk:
                    pk_type_import = cls.get_sqlalchemy_type(column).split("(")[0].strip()
                    if pk_type_import and pk_type_import != "Integer":
                        import_list.add(f"from sqlalchemy import {pk_type_import}")
                continue
            if column.column_type:
                sa_type = cls.get_sqlalchemy_type(column)
                # ARRAY(item) 的 item 也必须导入，否则生成模型 import 失败（PG text[]/int[]）
                if sa_type.startswith("ARRAY("):
                    import_list.add("from sqlalchemy import ARRAY")
                    item_type = sa_type[6:-1].split("(", 1)[0].strip()
                    if item_type:
                        import_list.add(f"from sqlalchemy import {item_type}")
                data_type = cls.get_db_type(column.column_type)
                # 非顶层导出的类型（JSONB/INET/CIDR/MACADDR/BIT/TSVECTOR/TSQUERY/Geometry 等）
                # 走明确的模块映射，绝不再拼 `from sqlalchemy import <方言类型>`（非法语句）
                mapped = StringUtil.get_mapping_value_by_key_ignore_case(GenConstant.DB_TO_SQLALCHEMY, data_type)
                module, type_name = DIALECT_TYPE_IMPORTS.get(mapped, ("sqlalchemy", mapped))
                import_list.add(f"from {module} import {type_name}")
            # 处理datetime类型的导入
            if column.python_type and column.python_type in GenConstant.TYPE_DATE:
                if column.python_type == "datetime":
                    has_datetime_import = True
                elif column.python_type == "date":
                    has_date_import = True
                elif column.python_type == "time":
                    has_time_import = True
            # 处理Decimal类型的导入
            elif column.python_type == GenConstant.TYPE_DECIMAL:
                import_list.add("from decimal import Decimal")
        # 子实体独立生成时才需要外键导入（主表仅声明 relationship，无需 ForeignKey；子表列的 SQLAlchemy
        # 类型由其自身模型渲染时通过 columns 循环导入）
        if is_sub_entity:
            import_list.add("from sqlalchemy import ForeignKey")

        # 添加datetime导入
        if has_datetime_import:
            import_list.add("from datetime import datetime")
        if has_date_import:
            import_list.add("from datetime import date")
        if has_time_import:
            import_list.add("from datetime import time")

        merged = cls.merge_same_imports(list(import_list), "from sqlalchemy import")
        if gen_table.sub or is_sub_entity:
            merged.append("from sqlalchemy.orm import relationship")
        return merged

    @classmethod
    def get_db_type(cls, column_type: str) -> str:
        """获取数据库字段类型。

        参数:
        - column_type (str): 字段类型字符串。

        返回:
        - str: 数据库类型（去除长度等修饰）。
        """
        # 移除 COLLATE 子句（处理带引号和不带引号的情况，不区分大小写）
        collate_pattern = re.compile(r"\s+COLLATE\s+", re.IGNORECASE)
        if collate_pattern.search(column_type):
            column_type = collate_pattern.split(column_type)[0].strip()

        # 移除 UNSIGNED 标记（不区分大小写）
        unsigned_pattern = re.compile(r"\s+UNSIGNED", re.IGNORECASE)
        if unsigned_pattern.search(column_type):
            column_type = unsigned_pattern.sub("", column_type).strip()

        # 处理PostgreSQL数组类型（如 integer[], text[]）
        if "[]" in column_type:
            return "array"

        # 提取基本类型：走严格基名提取（只允许 [A-Za-z][A-Za-z0-9_ ]*，剔除 unsigned 等修饰词），
        # 不直接 split 原始文本，避免把括号前的任意内容当作类型名带出去
        return column_type_base(column_type)

    @classmethod
    def merge_same_imports(cls, imports: list[str], import_start: str) -> list[str]:
        """合并相同的导入语句。

        参数:
        - imports (list[str]): 导入语句列表。
        - import_start (str): 导入语句的起始字符串。

        返回:
        - list[str]: 合并后的导入语句列表。
        """
        merged_imports = []
        imports_ = []
        for import_stmt in imports:
            if import_stmt.startswith(import_start):
                imported_items = import_stmt.split("import")[1].strip()
                imports_.extend(imported_items.split(", "))
            else:
                merged_imports.append(import_stmt)

        if imports_:
            # 去重并过滤空字符串，然后用逗号连接
            unique_imports = [item for item in imports_ if item]
            if len(unique_imports) > 0:
                merged_datetime_import = f"{import_start} {', '.join(unique_imports)}"
                merged_imports.append(merged_datetime_import)

        return merged_imports

    @classmethod
    def get_dicts(cls, gen_table: GenTableOutSchema):
        """获取字典列表。

        参数:
        - gen_table (GenTableOutSchema): 生成表的配置信息。

        返回:
        - str: 以逗号分隔的字典类型字符串。
        """
        columns = gen_table.columns or []
        dicts = set()
        cls.add_dicts(dicts, columns)
        # 处理sub_table为None的情况
        if gen_table.sub_table is not None:
            # 处理sub_table.columns为None的情况
            sub_columns = gen_table.sub_table.columns or []
            cls.add_dicts(dicts, sub_columns)
        return ", ".join(dicts)

    @classmethod
    def add_dicts(cls, dicts: set[str], columns: list[GenTableColumnOutSchema]) -> None:
        """添加字典类型到集合。

        参数:
        - dicts (set[str]): 字典类型集合。
        - columns (list[GenTableColumnOutSchema]): 字段列表。

        返回:
        - set[str]: 更新后的字典类型集合。
        """
        for column in columns:
            super_column = column.super_column if column.super_column is not None else "0"
            dict_type = column.dict_type or ""
            html_type = column.html_type or ""

            if (
                super_column != "1"
                and StringUtil.is_not_empty(dict_type)
                and StringUtil.equals_any_ignore_case(
                    html_type,
                    [
                        GenConstant.HTML_SELECT,
                        GenConstant.HTML_RADIO,
                        GenConstant.HTML_CHECKBOX,
                    ],
                )
            ):
                dicts.add(f"'{dict_type}'")

    @classmethod
    def get_permission_prefix(cls, module_name: str | None, business_name: str | None) -> str:
        """获取权限前缀。

        参数:
        - module_name (str | None): 模块名。
        - business_name (str | None): 业务名。

        返回:
        - str: 权限前缀字符串。
        """
        mn = (module_name or "").strip()
        bn = (business_name or "").strip().replace("/", ":")
        if not bn:
            return mn
        return f"{mn}:{bn}"

    @classmethod
    def python_type_to_ts_type(cls, python_type: str | None) -> str:
        """将列上的 Python 类型（`get_db_type` + `DB_TO_PYTHON` 映射结果）转为前端 TS 类型片段。

        与 JSON 序列化习惯一致：Decimal、日期时间多为字符串；dict/list 用宽松类型。

        参数:
        - python_type (str | None): Python 类型名。

        返回:
        - str: 前端 TypeScript 类型片段。
        """
        if not python_type or not str(python_type).strip():
            return "string"
        p = str(python_type).strip()
        mapping: dict[str, str] = {
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "Decimal": "string",
            "date": "string",
            "time": "string",
            "datetime": "string",
            "timedelta": "string",
            "dict": "Record<string, unknown>",
            "list": "unknown[]",
            "bytes": "string",
            "str": "string",
        }
        return mapping.get(p, "string")

    @classmethod
    def get_api_route_prefix(cls, module_name: str | None) -> str:
        """获取前端 API 路径首段，与 `discover` 中插件路由前缀一致（`module_xxx` → `xxx`）。

        参数:
        - module_name (str | None): 模块名，如 ``module_example``。

        返回:
        - str: 路由前缀，如 ``example``。
        """
        if not module_name:
            return ""
        if module_name.startswith("module_"):
            return module_name[7:]
        return module_name

    @classmethod
    def get_sqlalchemy_type(cls, column: Any) -> str:
        """获取 SQLAlchemy 类型（**代码位置** → 一律由常量白名单派生，见 template_safety）。

        类型名只能来自 ``GenConstant.DB_TO_SQLALCHEMY`` 的值，长度/精度只能来自
        ``column_length.isdigit()`` 或 ``column_type`` 括号内的**数字捕获**；
        不再使用 ``column_type.split("(")[1]`` 这类字符串切分（会把任意内容带进产物）。

        参数:
        - column (Any): 列对象或列类型字符串。

        返回:
        - str: SQLAlchemy 类型字符串（如 ``String(64)`` / ``Numeric(10,2)`` / ``DateTime``）。
        """
        column_type: Any = column
        column_length: Any = None
        if hasattr(column, "column_type"):
            column_type = getattr(column, "column_type", "") or ""
            column_length = getattr(column, "column_length", None) or None

        # 先按既有口径去掉 COLLATE / UNSIGNED，便于与常量表的键匹配
        column_type = cls.normalize_db_column_type_for_mapping(column_type)
        return pick_sqlalchemy_type(column_type, column_length)


def _sentinelize_value(value: Any) -> Any:
    """把非空文本替换为哨兵文本（空值/None 原样保留，避免改变模板的真值分支）。

    参数:
    - value (Any): 原始值。

    返回:
    - Any: 哨兵文本或原值。
    """
    if value is None:
        return None
    text = str(value)
    return SENTINEL_TEXT if text else text
