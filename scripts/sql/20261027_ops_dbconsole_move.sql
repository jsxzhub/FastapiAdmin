-- SQL 控制台迁移到运维域（MySQL 8+）
-- 目的：菜单权限 module_dbconsole:* → module_ops:dbconsole:*，
--       前端组件 module_dbconsole/index → module_ops/dbconsole/index。
-- 幂等：可重复执行。
UPDATE sys_menu
SET permission = REPLACE(permission, 'module_dbconsole:', 'module_ops:dbconsole:'),
    component_path = REPLACE(component_path, 'module_dbconsole/', 'module_ops/dbconsole/')
WHERE is_deleted = 0
  AND (permission LIKE 'module_dbconsole:%' OR component_path LIKE 'module_dbconsole/%');

-- 兼容之前遗漏的 SQL 控制台菜单行（按路由/名称定位）
UPDATE sys_menu
SET component_path = 'module_ops/dbconsole/index'
WHERE is_deleted = 0
  AND type = 2
  AND (name = 'SQL 控制台' OR route_name = 'DbConsole')
  AND (component_path IS NULL OR component_path = '' OR component_path LIKE 'module_dbconsole/%');
