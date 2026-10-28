"""菜单权限种子与公共文件权限回归测试。"""

import json
from pathlib import Path

MENU_SEED = Path(__file__).resolve().parents[1] / "sql" / "sys_menu.json"


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("children") or [])


def test_common_file_permissions_are_assignable() -> None:
    permissions = {n.get("permission") for n in _walk(json.loads(MENU_SEED.read_text(encoding="utf-8")))}
    assert "module_common:file:upload" in permissions
    assert "module_common:file:download" in permissions


def test_detail_permissions_exist() -> None:
    permissions = {n.get("permission") for n in _walk(json.loads(MENU_SEED.read_text(encoding="utf-8")))}
    assert "module_system:log:detail" in permissions
    assert "module_monitor:cache:detail" in permissions


def test_ops_permission_buttons_exist() -> None:
    permissions = {n.get("permission") for n in _walk(json.loads(MENU_SEED.read_text(encoding="utf-8")))}
    expected = {
        "module_ops:dbconsole:conn:create",
        "module_ops:dbconsole:conn:update",
        "module_ops:dbconsole:conn:delete",
        "module_ops:dbconsole:query:execute",
        "module_ops:ssh:create",
        "module_ops:ssh:update",
        "module_ops:ssh:delete",
        "module_ops:ssh:terminal",
        "module_ops:ssh:exec",
        "module_ops:snippet:query",
        "module_ops:snippet:create",
        "module_ops:snippet:update",
        "module_ops:snippet:delete",
    }
    assert expected <= permissions
