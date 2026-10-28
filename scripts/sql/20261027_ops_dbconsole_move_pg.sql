-- SQL 控制台迁移到运维域（PostgreSQL）
-- 与 20261027_ops_dbconsole_move.sql 等价；幂等。
UPDATE sys_menu
SET permission = REPLACE(permission, 'module_dbconsole:', 'module_ops:dbconsole:'),
    component_path = REPLACE(component_path, 'module_dbconsole/', 'module_ops/dbconsole/')
WHERE is_deleted = false
  AND (permission LIKE 'module_dbconsole:%' OR component_path LIKE 'module_dbconsole/%');

UPDATE sys_menu
SET component_path = 'module_ops/dbconsole/index'
WHERE is_deleted = false
  AND type = 2
  AND (name = 'SQL 控制台' OR route_name = 'DbConsole')
  AND (component_path IS NULL OR component_path = '' OR component_path LIKE 'module_dbconsole/%');
