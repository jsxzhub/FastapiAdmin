-- 运维管理按钮权限增量补丁（MySQL 8+）
-- 背景：SQL 控制台 / SSH 运维代码已定义 create/update/delete/execute/terminal 等权限，
--       但旧种子菜单只有菜单级 query 权限，普通角色无法在后台勾选，操作会 403。
-- 用法：在目标库执行一次；脚本幂等，可重复执行。
-- 执行后到「角色管理 → 分配权限」勾选对应按钮。

CREATE TEMPORARY TABLE tmp_ops_menu_buttons (
    parent_title VARCHAR(50) NOT NULL,
    name VARCHAR(64) NOT NULL,
    permission VARCHAR(100) NOT NULL,
    ord INT NOT NULL,
    description TEXT NULL
);

INSERT INTO tmp_ops_menu_buttons (parent_title, name, permission, ord, description) VALUES
('SQL 控制台', '新增连接', 'module_ops:dbconsole:conn:create', 1, 'SQL 控制台新增外部数据库连接'),
('SQL 控制台', '修改连接', 'module_ops:dbconsole:conn:update', 2, 'SQL 控制台修改外部数据库连接'),
('SQL 控制台', '删除连接', 'module_ops:dbconsole:conn:delete', 3, 'SQL 控制台删除外部数据库连接'),
('SQL 控制台', '执行查询', 'module_ops:dbconsole:query:execute', 4, 'SQL 控制台执行只读查询或确认写'),
('SSH 运维', '新增主机', 'module_ops:ssh:create', 1, 'SSH 运维新增主机'),
('SSH 运维', '修改主机', 'module_ops:ssh:update', 2, 'SSH 运维修改主机'),
('SSH 运维', '删除主机', 'module_ops:ssh:delete', 3, 'SSH 运维删除主机'),
('SSH 运维', '终端会话', 'module_ops:ssh:terminal', 4, 'SSH 运维打开终端会话'),
('SSH 运维', '批量执行', 'module_ops:ssh:exec', 5, 'SSH 运维批量执行命令'),
('SSH 运维', '查询片段', 'module_ops:snippet:query', 6, '查询 SSH 命令片段'),
('SSH 运维', '新增片段', 'module_ops:snippet:create', 7, '新增 SSH 命令片段'),
('SSH 运维', '修改片段', 'module_ops:snippet:update', 8, '修改 SSH 命令片段'),
('SSH 运维', '删除片段', 'module_ops:snippet:delete', 9, '删除 SSH 命令片段');

INSERT INTO sys_menu
    (name, type, `order`, permission, icon, route_name, route_path, component_path, redirect,
     hidden, keep_alive, always_show, title, params, affix, link, is_iframe, is_hide_tab,
     active_path, show_badge, show_text_badge, scope, status, description, parent_id, uuid,
     is_deleted, created_time, updated_time, deleted_time)
SELECT b.name, 3, b.ord, b.permission, NULL, NULL, NULL, NULL, NULL,
       0, 1, 0, b.name, NULL, 0, NULL, 0, 0, NULL, 0, NULL, 'web', 0,
       b.description, p.id, UUID(), 0, NOW(), NOW(), NULL
FROM tmp_ops_menu_buttons b
JOIN sys_menu p ON p.title = b.parent_title AND p.type = 2 AND p.is_deleted = 0
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu m
    WHERE m.permission = b.permission AND m.is_deleted = 0
);

DROP TEMPORARY TABLE tmp_ops_menu_buttons;
