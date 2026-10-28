"""代码生成模板的输入安全处理。

背景（见 backend/audit-backend.md 的 B1）
======================================
代码生成器把「表/列元数据」渲染成 ``.py`` / ``.vue`` / ``.ts`` / ``.toml`` 源文件，产物会被写进
仓库，其中 ``backend/app/plugin/**`` 会在应用启动时被 ``app/core/discover.py`` 逐个
``import_module`` 执行。因此任何用户可控文本（表注释、列注释、字段名、功能名……）都不能原样
进入模板——否则「有代码生成权限」就等于「能在服务器上执行任意代码」。

为什么不用 ``autoescape=True``
=============================
生成物的目标是**代码**而不是 HTML：全局开启 autoescape 会把 ``<`` ``>`` ``&`` 变成 ``&lt;`` 等，
直接把生成出来的 Python / Vue 源码写坏。正确做法是**按上下文处理**：

- 落进「字符串字面量 / 注释 / 文档字符串」的文本 → :func:`escape_template_text`
  （转义 ``\\ ' " 换行 反引号`` 等，Python / JS / TOML 的字符串都会把它解析回原字符，保真；
  但源码层面不再出现能闭合字面量或换行的字符，因而无法逃出当前语法上下文）。
- 落进「标识符位置」的值（列名、类名、类型注解……）→ :func:`safe_ident`。
- 落进 ``.vue`` 模板「文本节点」的展示文本 → :func:`vue_label`（额外去掉尖括号与花括号）。

两层防线
========
1. 口径层：``gencode/schema.py`` 对 ``column_name`` 做白名单校验（拒绝非法标识符）；
2. 渲染层：本模块的转义在 :meth:`Jinja2TemplateUtil.prepare_context` 统一施加，
   即使数据来自物理库反射（绕过表单校验）也不会产出可执行注入。
"""

import ast
import keyword
import re
from collections.abc import Iterable

from app.common.constant import GenConstant

# 需要转义的字符 → \uXXXX 形式。
# 该形式在 Python 字符串（含三引号文档字符串）、JS 字符串 / 模板字符串、TOML basic string
# 中都会被解析回原字符，因此既安全又保真。
_ESCAPE_MAP: dict[str, str] = {
    "\\": "\\u005c",  # 反斜杠必须先处理，避免二次转义
    "'": "\\u0027",  # Python 单引号 / JS 单引号
    '"': "\\u0022",  # Python 双引号 / JS 双引号 / TOML basic string 定界符
    "\n": "\\u000a",
    "\r": "\\u000d",
    "\t": "\\u0009",
    "\v": "\\u000b",
    "\f": "\\u000c",
    "\0": "\\u0000",
    "`": "\\u0060",  # JS 模板字符串定界符
    # U+2028/U+2029（行/段分隔符）：在 JS 里被当作换行，可用来断行逃逸；在 Python 字符串里合法
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}

# 其余控制字符：C0（换行/制表等已在 _ESCAPE_MAP 中显式处理）+ DEL(7F) + C1 控制符(80-9F)
_CONTROL_RE = re.compile(r"[\x01-\x08\x0e-\x1f\x7f-\x9f]")

# \uXXXX 转义的反解（展示位置使用）
_UNESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")

# JS 模板字符串插值起始序列：$ 后紧跟 { 时必须打断，否则 ${...} 会被当成表达式执行
_JS_INTERPOLATION_RE = re.compile(r"\$\{")

# 合法标识符（Python / JS 通用子集）
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 标识符规范化：去掉所有非 [A-Za-z0-9_]
_IDENT_STRIP_RE = re.compile(r"[^A-Za-z0-9_]")

# Vue 文本节点额外需要剔除的字符：尖括号与花括号会改变标记结构 / 触发 Vue 插值
_VUE_LABEL_STRIP_RE = re.compile(r"[<>{}]")

# HTML 文本/属性位置的实体转义（保真：浏览器渲染回原字符，而不是把 \uXXXX 当字面量显示）
_HTML_ESCAPE_MAP: dict[str, str] = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}

# 标识符长度上限（MySQL 标识符上限 64）
_IDENTIFIER_MAX_LENGTH = 64

# Python 关键字/软关键字：作为字段名会直接语法错误（如 column_name="class"）
_PYTHON_RESERVED: frozenset[str] = frozenset(keyword.kwlist) | frozenset(keyword.softkwlist)

# JS/TS 保留字与字面量：作为裸标识符会语法错误或改变语义
_JS_RESERVED: frozenset[str] = frozenset(
    {
        "abstract", "arguments", "await", "boolean", "break", "byte", "case", "catch", "char", "class",
        "const", "continue", "debugger", "default", "delete", "do", "double", "else", "enum", "eval",
        "export", "extends", "false", "final", "finally", "float", "for", "function", "goto", "if",
        "implements", "import", "in", "instanceof", "int", "interface", "let", "long", "native", "new",
        "null", "package", "private", "protected", "public", "return", "short", "static", "super",
        "switch", "synchronized", "this", "throw", "throws", "transient", "true", "try", "typeof",
        "undefined", "var", "void", "volatile", "while", "with", "yield",
    },
)

# 保留字命中时的前缀（保证仍是合法标识符，同时避免与关键字冲突）
_RESERVED_PREFIX = "_"


def escape_template_text(value: object) -> str:
    """把任意文本转义为「放进字符串字面量/注释/文档字符串都安全」的形式。

    参数:
    - value (object): 原始值（None 视为空串）。

    返回:
    - str: 转义后的文本；内容不含可闭合字符串字面量、可换行或可开启 JS 插值的字符。
    """
    if value is None:
        return ""
    text = str(value)
    for raw, escaped in _ESCAPE_MAP.items():
        text = text.replace(raw, escaped)
    text = _CONTROL_RE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)
    # ${ 打断为 \u0024{，避免在 JS 模板字符串里变成插值表达式
    # 注意：替换值用 lambda 返回，re.sub 的字符串替换会把 \u 当成非法转义
    return _JS_INTERPOLATION_RE.sub(lambda m: "\\u0024{", text)


def safe_ident(value: object, default: str = "entity") -> str:
    """把任意值规范为合法标识符（用于列名、类名、类型注解等位置）。

    参数:
    - value (object): 原始值。
    - default (str): 空值/规范化后为空的兜底标识符。

    返回:
    - str: 形如 ``[A-Za-z_][A-Za-z0-9_]*`` 的标识符，长度不超过 64。
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return default
    # 只替换非法字符，不改动已有合法标识符（避免 a__b / _x 这类名字被“规范化”后与库中列名不一致）
    text = _IDENT_STRIP_RE.sub("_", text)
    if text[0].isdigit():
        text = f"_{text}"
    # 关键字/保留字（Python + JS）不能作为裸标识符：加前缀而不是报错（用于类名/模块名/字段名等位置）
    if text in _PYTHON_RESERVED or text in _JS_RESERVED:
        text = f"{_RESERVED_PREFIX}{text}"
    return text[:_IDENTIFIER_MAX_LENGTH]


def is_safe_identifier(value: object) -> bool:
    """判断值是否本身即为合法标识符（无需规范化）。

    同时排除 Python 关键字与 JS/TS 保留字：它们作为裸标识符会出现语法错误
    （如列名 ``class`` 会生成 ``class: Mapped[...]``）。

    参数:
    - value (object): 待判断的值。

    返回:
    - bool: 合法返回 True。
    """
    if value is None:
        return False
    text = str(value).strip()
    if not text or len(text) > _IDENTIFIER_MAX_LENGTH:
        return False
    if text in _PYTHON_RESERVED or text in _JS_RESERVED:
        return False
    return bool(_IDENTIFIER_RE.match(text))


def reserved_word_reason(value: object) -> str | None:
    """若值命中 Python 关键字或 JS 保留字，返回原因文案（供报错信息使用），否则 None。

    参数:
    - value (object): 待判断的值。

    返回:
    - str | None: 命中原因（"Python 关键字" / "JS 保留字"）。
    """
    text = "" if value is None else str(value).strip()
    if text in _PYTHON_RESERVED:
        return "Python 关键字"
    if text in _JS_RESERVED:
        return "JS/TS 保留字"
    return None


def unescape_template_text(value: object) -> str:
    """还原 :func:`escape_template_text` 产生的 ``\\uXXXX`` 转义（展示位置专用）。

    HTML 文本/属性里不会解析 ``\\uXXXX``，若不还原就会被用户看成字面量。转义本身是**可逆**的
    （原文本里的反斜杠也被转义为 ``\\u005c``），因此这里单趟还原即可精确拿回原文。

    参数:
    - value (object): 已转义的文本。

    返回:
    - str: 还原后的文本。
    """
    if value is None:
        return ""
    return _UNESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), str(value))


def html_escape(value: object) -> str:
    """HTML 实体转义（用于 ``.vue`` 的文本节点与静态属性值）。

    与 :func:`escape_template_text` 的区别：这里追求**展示保真**——先还原 ``\\uXXXX``（HTML 不解析该转义），
    再用实体转义，浏览器渲染回原字符。

    参数:
    - value (object): 文本（可能已带 ``\\uXXXX`` 转义）。

    返回:
    - str: 实体转义后的文本。
    """
    if value is None:
        return ""
    text = unescape_template_text(value)
    for raw, escaped in _HTML_ESCAPE_MAP.items():
        text = text.replace(raw, escaped)
    return text


def html_attr(value: object) -> str:
    """静态 HTML 属性值的安全化（还原转义 + 实体转义，保留引号语义与展示保真）。

    参数:
    - value (object): 文本。

    返回:
    - str: 可直接放进 ``attr="..."`` 的文本。
    """
    return html_escape(value)


def vue_label(value: object) -> str:
    """把展示文本处理为可安全放进 ``.vue`` **文本节点**的形式。

    策略（与 JS/Python 字符串上下文不同，见模块文档的「按上下文四类」）：
    - 先还原 ``\\uXXXX``（HTML 不解析该转义，否则用户会看到字面量）；
    - 剔除 ``< > { }``：改变标记结构 / 触发 Vue 插值的字符直接去掉；
    - 其余字符用 **HTML 实体**转义：浏览器渲染回原字符，展示保真。

    参数:
    - value (object): 原始展示文本。

    返回:
    - str: 可安全放进文本节点的文本。
    """
    if value is None:
        return ""
    return html_escape(_VUE_LABEL_STRIP_RE.sub("", unescape_template_text(value)))


# python_type 只允许这些真实类型名；不能复用 safe_ident，否则 int/float 会被
# 当成 JS 保留字改写成 _int/_float，而生成文件里并没有对应导入，直接 ImportError。
_PYTHON_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "str", "int", "float", "bool", "bytes", "dict", "list", "tuple", "set",
        "datetime", "date", "time", "timedelta", "Decimal", "Any",
    }
)


def safe_python_type(value: object, default: str = "str") -> str:
    """把 ``python_type`` 规范为合法类型注解片段。

    ``python_type`` 会直接落在 ``Mapped[{{ column.python_type }}]`` 这类注解位置，
    只能取白名单中的真实类型名，避免把自由文本注入代码。

    参数:
    - value (object): 原始值。
    - default (str): 兜底类型。

    返回:
    - str: 白名单内的类型名，或兜底类型。
    """
    text = "" if value is None else str(value).strip()
    return text if text in _PYTHON_TYPE_NAMES else default


def assert_python_syntax(content: str, *, filename: str = "<generated>") -> None:
    """断言渲染产物是语法合法的 Python。

    作为「转义/白名单是否仍然完备」的最后一道网：任何模板改动导致注入或语法破损时，
    在**写盘前**就报错，而不是把坏文件写进会被启动期 import 的目录。

    参数:
    - content (str): 渲染后的源码文本。
    - filename (str): 产物相对路径（用于报错定位）。

    返回:
    - None

    异常:
    - SyntaxError: 产物无法被 ast.parse 解析时抛出。
    """
    try:
        ast.parse(content)
    except SyntaxError as exc:
        raise SyntaxError(f"{filename} 渲染结果不是合法的 Python 代码：{exc.msg}（第 {exc.lineno} 行）") from exc


# ══════════════════════════════════════════════════════════════════════════════
# 「代码位置」类值：一律由**常量白名单**派生，不接收自由文本
# ══════════════════════════════════════════════════════════════════════════════

# column_type 的形状白名单（结构化，不含引号/分号/换行等可注入字符）
_COLUMN_TYPE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_ ]*(\(\s*\d+(\s*,\s*\d+)?\s*\))?(\[\])*(\s+unsigned)?$",
)
# MySQL ENUM/SET 列表（合法的库类型，但含引号）：整体归一化为基名后再做形状校验
_ENUM_SET_RE = re.compile(r"^(enum|set)\s*\(.*\)$", re.IGNORECASE)
# 从 column_type 的括号里取参数（只接受数字，绝不拼接原始子串）
_TYPE_PARAMS_RE = re.compile(r"\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\)")
# 取出类型基名（字母/数字/下划线/空格，遇括号或方括号即止）
_TYPE_BASE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*")
# 基名里需要剔除的修饰词（它们不属于类型名，参与查表会导致 miss）
_BASE_MODIFIER_RE = re.compile(r"\s+(unsigned|zerofill)$", re.IGNORECASE)

# 映射常量值的白名单（类型名只能取自这里，杜绝自由文本进产物）。
# Boolean 由 MySQL tinyint(1) 规则显式产出（常量表中未必有该值），此处一次成型，
# 避免对全大写常量二次赋值（类型检查会报 reportConstantRedefinition，也是不必要的可变性）。
_SQLALCHEMY_TYPE_WHITELIST: frozenset[str] = frozenset(GenConstant.DB_TO_SQLALCHEMY.values()) | {"Boolean"}

# 非顶层 sqlalchemy 导出的类型 → (模块, 类名)。
# 生成器只按此表拼 import，避免产出 `from sqlalchemy import JSONB` 这类非法语句：
# JSONB / INET / CIDR / MACADDR / BIT / TSVECTOR / TSQUERY 实际位于
# sqlalchemy.dialects.postgresql；JSONType 是基类提供的跨方言类型；Geometry 位于 geoalchemy2。
DIALECT_TYPE_IMPORTS: dict[str, tuple[str, str]] = {
    "JSONType": ("app.core.base_model", "JSONType"),
    "INET": ("sqlalchemy.dialects.postgresql", "INET"),
    "CIDR": ("sqlalchemy.dialects.postgresql", "CIDR"),
    "MACADDR": ("sqlalchemy.dialects.postgresql", "MACADDR"),
    "BIT": ("sqlalchemy.dialects.postgresql", "BIT"),
    "TSVECTOR": ("sqlalchemy.dialects.postgresql", "TSVECTOR"),
    "TSQUERY": ("sqlalchemy.dialects.postgresql", "TSQUERY"),
    "Geometry": ("geoalchemy2", "Geometry"),
}


def _lookup_sqlalchemy_type(base: str) -> str:
    """按基名（大小写不敏感）在常量白名单中查表。

    参数:
    - base (str): 类型基名（已小写）。

    返回:
    - str: 命中的常量值；未命中返回空串。
    """
    for key, value in GenConstant.DB_TO_SQLALCHEMY.items():
        if str(key).lower() == base:
            return str(value)
    return ""


def normalize_column_type(column_type: object) -> str:
    """归一化列类型：去空白、把 ENUM/SET 列表压成基名。

    参数:
    - column_type (object): 原始列类型（如 ``VARCHAR(64)`` / ``ENUM('a','b')``）。

    返回:
    - str: 归一化后的类型文本（ENUM/SET 仅保留基名）。
    """
    text = "" if column_type is None else str(column_type).strip()
    if _ENUM_SET_RE.match(text):
        # 不假定 _TYPE_BASE_RE 一定命中：None 安全处理，命中不了就原样返回，
        # 交给 is_valid_column_type 的形状白名单继续拦截（不在这里静默放行）。
        base_match = _TYPE_BASE_RE.match(text)
        if base_match is not None:
            return base_match.group(0).strip()
    return text


def is_valid_column_type(column_type: object) -> bool:
    """列类型形状校验：只允许「基名 + 可选(n)/(n,m) + 可选[] + 可选 unsigned」。

    参数:
    - column_type (object): 原始列类型。

    返回:
    - bool: 合法返回 True。
    """
    text = normalize_column_type(column_type)
    if not text:
        return False
    return bool(_COLUMN_TYPE_RE.match(text))


def column_type_base(column_type: object) -> str:
    """取列类型基名（用于白名单查表，不参与最终产物拼接）。

    参数:
    - column_type (object): 原始列类型。

    返回:
    - str: 基名（如 ``VARCHAR``）；无法识别时为空串。
    """
    text = normalize_column_type(column_type)
    match = _TYPE_BASE_RE.match(text)
    if not match:
        return ""
    base = _BASE_MODIFIER_RE.sub("", match.group(0).strip())
    return base.strip()


def extract_type_params(column_type: object, column_length: object = None) -> tuple[str, ...]:
    """提取「长度/精度」参数，只接受纯数字。

    取数优先级：``column_length.isdigit()`` → ``column_type`` 括号内正则捕获的数字。
    **不对 column_type 做字符串切分拼接**（``split("(")[1]`` 会把任意内容带进产物）。

    参数:
    - column_type (object): 列类型。
    - column_length (object): 列长度（表单/反射字段）。

    返回:
    - tuple[str, ...]: 形如 ("64",) 或 ("10", "2")；无有效参数时为空元组。
    """
    length = "" if column_length is None else str(column_length).strip()
    if length.isdigit():
        return (length,)
    text = normalize_column_type(column_type)
    match = _TYPE_PARAMS_RE.search(text)
    if not match:
        return ()
    return tuple(part for part in match.groups() if part is not None)


def pick_sqlalchemy_type(column_type: object, column_length: object = None, *, db_type: str | None = None) -> str:
    """由常量白名单派生 SQLAlchemy 类型字符串（代码位置，不接收自由文本）。

    规则：
    - 类型名只能来自 ``GenConstant.DB_TO_SQLALCHEMY`` 的**值**（未命中回落 ``String``）；
    - 长度/精度只能来自 ``column_length.isdigit()`` 或 ``column_type`` 括号内的数字捕获；
    - MySQL 下 ``tinyint(1)`` 保持 ``Boolean`` 语义。

    参数:
    - column_type (object): 列类型。
    - column_length (object): 列长度。
    - db_type (str | None): 数据库类型（默认取 settings.DATABASE_TYPE）。

    返回:
    - str: 形如 ``String(64)`` / ``Numeric(10,2)`` / ``DateTime`` 的类型字符串。
    """
    from app.config.setting import settings  # 延迟导入避免模块级循环

    dialect = (db_type or settings.DATABASE_TYPE or "").lower()
    text = normalize_column_type(column_type)
    # PostgreSQL 数组：保留元素类型，生成 ARRAY(<item_type>)；裸 ARRAY 无元素信息时用 String 兜底
    if text.endswith("[]") or text.upper().startswith("ARRAY["):
        item_text = text[:-2].strip() if text.endswith("[]") else text[text.find("[") + 1 : text.rfind("]")].strip()
        item_sa = pick_sqlalchemy_type(item_text, None, db_type=dialect) if item_text else "String"
        if not item_sa or item_sa == "ARRAY":
            item_sa = "String"
        return f"ARRAY({item_sa})"

    base = column_type_base(column_type)
    params = extract_type_params(column_type, column_length)
    lowered = base.lower()

    # MySQL：仅 tinyint(1) 映射为 Boolean（与既有行为一致）
    if dialect != "postgres" and lowered == "tinyint" and params[:1] == ("1",):
        return "Boolean"

    # 查表（大小写不敏感）：命中值必须落在白名单内
    mapped = _lookup_sqlalchemy_type(lowered)
    if not mapped and lowered == "character":
        mapped = _lookup_sqlalchemy_type("char")
    if mapped not in _SQLALCHEMY_TYPE_WHITELIST:
        mapped = "String"  # 白名单兜底

    # 长度/精度：仅对需要参数的字符串与数值类型附加（数字已校验）
    if params:
        if mapped in {"String", "CHAR"}:
            return f"{mapped}({params[0]})"
        if mapped in {"Numeric", "DECIMAL"} and len(params) >= 2:
            return f"{mapped}({params[0]},{params[1]})"
    if mapped in {"String", "CHAR"}:
        return f"{mapped}(255)"
    return mapped


# ══════════════════════════════════════════════════════════════════════════════
# 落盘前的「结构闸门」：仅 ast.parse 不足以发现注入，必须比对骨架结构
# ══════════════════════════════════════════════════════════════════════════════

# 允许出现在生成产物里的顶层语句类型（白名单）；出现其它类型即拒绝
_ALLOWED_TOP_LEVEL_NODES: tuple[type[ast.AST], ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Assign,
    ast.AnnAssign,
    ast.Expr,
    ast.If,
    ast.Try,
    ast.Pass,
)


def _node_structure(node: ast.AST) -> object:
    """把 AST 节点归一化为「结构签名」：保留节点类型与层级，抹掉具体取值/标识符。

    参数:
    - node (ast.AST): 待归一化的节点。

    返回:
    - object: 可比较的结构签名（元组树）。
    """
    if isinstance(node, ast.Constant):
        return ("Constant", type(node.value).__name__)
    if isinstance(node, ast.Name):
        return ("Name",)  # 标识符具体名字不参与比较
    if isinstance(node, ast.Attribute):
        return ("Attribute", _node_structure(node.value))
    if isinstance(node, ast.arg):
        return ("arg", node.arg)  # 形参名由模板决定，参与比较
    if isinstance(node, ast.keyword):
        return ("keyword", node.arg, _node_structure(node.value))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return (
            type(node).__name__,
            node.name,
            tuple(_node_structure(item) for item in node.body),
            tuple(_node_structure(item) for item in node.decorator_list),
            tuple(_node_structure(item) for item in node.args.args),
            tuple(_node_structure(item) for item in node.args.kwonlyargs),
            node.args.vararg.arg if node.args.vararg else None,
            node.args.kwarg.arg if node.args.kwarg else None,
        )
    if isinstance(node, ast.ClassDef):
        return (
            "ClassDef",
            node.name,
            tuple(_node_structure(item) for item in node.bases),
            tuple(_node_structure(item) for item in node.body),
            tuple(_node_structure(item) for item in node.decorator_list),
        )

    fields: list[object] = [type(node).__name__]
    for _field_name, value in ast.iter_fields(node):
        if isinstance(value, list):
            fields.append(tuple(_node_structure(item) for item in value if isinstance(item, ast.AST)))
        elif isinstance(value, ast.AST):
            fields.append(_node_structure(value))
        else:
            fields.append(type(value).__name__)
    return tuple(fields)


def python_structure(content: str) -> tuple[object, ...]:
    """解析源码并返回顶层结构签名（供骨架比对）。

    参数:
    - content (str): Python 源码。

    返回:
    - tuple[object, ...]: 顶层语句的结构签名序列。
    """
    tree = ast.parse(content)
    return tuple(_node_structure(node) for node in tree.body)


def assert_python_structure(content: str, reference: str, *, filename: str = "<generated>") -> None:
    """落盘前的语义/AST 闸门：真实产物必须与「哨兵值骨架」结构一致。

    只做 ``ast.parse`` 不能作为安全网（注入出来的代码本身语法合法）。这里要求：
    1. 产物语法合法；
    2. 顶层语句类型必须在白名单内（Import/ClassDef/AnnAssign…）；
    3. 与用哨兵值渲染同一模板得到的**骨架**逐节点结构一致（语句数量、类型、装饰器、
       形参、关键字参数名全部一致），任何因值而新增/改写的语句都会被发现。

    参数:
    - content (str): 真实渲染产物。
    - reference (str): 哨兵值渲染产出的骨架。
    - filename (str): 产物相对路径（报错定位）。

    返回:
    - None

    异常:
    - SyntaxError: 语法非法或结构不一致时抛出。
    """
    try:
        ast.parse(content)
    except SyntaxError as exc:
        raise SyntaxError(f"{filename} 渲染结果不是合法的 Python 代码：{exc.msg}（第 {exc.lineno} 行）") from exc

    real_tree = ast.parse(content)
    banned = [type(node).__name__ for node in real_tree.body if not isinstance(node, _ALLOWED_TOP_LEVEL_NODES)]
    if banned:
        raise SyntaxError(f"{filename} 出现白名单之外的顶层语句：{sorted(set(banned))}")

    real = python_structure(content)
    skeleton = python_structure(reference)
    if real != skeleton:
        raise SyntaxError(
            f"{filename} 渲染产物结构与模板骨架不一致（疑似模板注入或转义缺口）："
            f"真实 {len(real)} 条顶层语句 / 骨架 {len(skeleton)} 条",
        )


_STR_LITERAL_RE = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")


def _normalize_text_line(line: str, tokens: tuple[str, ...]) -> str:
    """把一行里的「值」抹成占位符，只留下骨架（供 .vue/.ts 的粗粒度护栏比对）。

    参数:
    - line (str): 待归一化的行。
    - tokens (tuple[str, ...]): 需要抹掉的动态值（哨兵 + 真实值，按长度降序）。

    返回:
    - str: 归一化后的行骨架。
    """
    normalized = line
    for token in tokens:
        if token:
            normalized = normalized.replace(token, "«»")
    return _STR_LITERAL_RE.sub(lambda m: f"{m.group(0)[0]}«»{m.group(0)[0]}", normalized)


def assert_text_structure(
    content: str,
    reference: str,
    *,
    sentinel: str,
    dynamic_values: Iterable[str] = (),
    filename: str = "<generated>",
) -> None:
    """``.vue`` / ``.ts`` / ``.toml`` 产物的粗粒度结构护栏。

    这些产物没有 AST 可比，退化为「行结构一致」：把每行的字符串字面量与哨兵值抹成占位符后，
    真实产物与骨架的行数与逐行骨架必须完全一致。任何因值而新增的行（注入的 script/标签/语句）
    或在一行内跑出字符串字面量的注入都会导致不一致。

    参数:
    - content (str): 真实渲染产物。
    - reference (str): 哨兵值渲染产出的骨架。
    - sentinel (str): 哨兵文本。
    - dynamic_values (object): 真实值集合（会出现在真实产物里的动态文本，一并抹成占位符）。
    - filename (str): 产物相对路径（报错定位）。

    返回:
    - None

    异常:
    - ValueError: 行结构不一致时抛出。
    """
    tokens = tuple(sorted({sentinel, *[str(item) for item in dynamic_values if item]}, key=len, reverse=True))
    real_lines = content.splitlines()
    ref_lines = reference.splitlines()
    if len(real_lines) != len(ref_lines):
        raise ValueError(f"{filename} 产物行数与模板骨架不一致（{len(real_lines)} vs {len(ref_lines)}），疑似注入")
    for index, (real_line, ref_line) in enumerate(zip(real_lines, ref_lines, strict=True), 1):
        if _normalize_text_line(real_line, tokens) != _normalize_text_line(ref_line, tokens):
            raise ValueError(f"{filename} 第 {index} 行结构偏离模板骨架，疑似注入：{real_line.strip()[:120]!r}")
