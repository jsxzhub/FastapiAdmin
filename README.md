# 项目简介
本项目基于 FastapiAdmin 二次开发，致力于打造一套开箱即用的后台管理框架。我们坚持永久免费开源，诚邀各路开发者共建共享，共同打磨更优质的企业级解决方案。

# 安装
```bash
git clone https://github.com/fastapiadmin/FastapiAdmin.git
```

# 后端
## 配置
```bash
cd backend/
cp env/.env.example env/.env.dev
```

## 安装依赖
```bash
pip install -r requirements.txt
```

## 运行
```bash
python main.py run --env=dev
```

## 数据库迁移（模型变更时使用）
```bash
python main.py revision --env=dev
python main.py upgrade --env=dev
```

## 插件开发
项目采用**插件化架构**，建议在 `backend/app/plugin/` 下开发：

### 自动路由注册机制
1. 控制器文件命名为 `controller.py`
2. 路由自动映射：`module_xxx` → `/xxx`
3. 系统自动扫描 `plugin/` 下所有 `controller.py` 并注册路由

### 开发步骤
1. 在 `backend/app/plugin/` 下创建 `module_yourfeature/`
2. 依次编写 `model.py` → `schema.py` → `crud.py` → `service.py` → `controller.py`
3. 路由自动注册，无需手动配置

### 后端约定
- **日期序列化**：使用 Pydantic `PlainSerializer(..., when_used='json')`，ORM 用 `mode='python'`，JSON/Redis 用 `mode='json'`
- **统一响应**：使用 `SuccessResponse` 和 `jsonable_encoder`
- **权限控制**：所有 API 接口需添加 `AuthPermission` 权限控制
- **日志记录**：关键操作使用 `OperationLogRoute` 记录

# 前端

## 配置
```bash
cd frontend/web
cp .env.development.example .env.development
```

## 安装依赖
```bash
pnpm install
```

## 运行
```bash
pnpm run dev
```

## 其他脚本
```bash
pnpm build            # 生产构建
pnpm type-check       # TypeScript 检查
pnpm lint             # ESLint + Prettier + Stylelint
pnpm clean:cache      # 清理缓存
```

## 新增页面流程
- 在 `src/api/` 创建对应 API 文件
- 在 `src/views/` 创建页面组件
- 路由注册（静态或动态路由）+ 后端菜单配置
- 路径与 name 保持三者一致

# 移动端

## 配置
```bash
cd frontend/app
cp .env.development.example .env.development
```

## 安装依赖
```bash
pnpm install
```

## 运行

### H5 运行
```bash
pnpm run dev:h5 --host
```

### 微信小程序运行
```bash
# 启动微信小程序开发服务器
pnpm run dev:mp-weixin

# 在微信开发者工具中导入项目目录：dist/dev/mp-weixin
```

### 其他平台运行
```bash
# 启动支付宝小程序开发服务器
pnpm run dev:mp-alipay

# 启动百度小程序开发服务器
pnpm run dev:mp-baidu

# 启动字节跳动小程序开发服务器
pnpm run dev:mp-toutiao

# 启动 QQ 小程序开发服务器
pnpm run dev:mp-qq
```

## 打包发布

### H5 构建
```
pnpm run build:h5

# 构建产物在 dist/build/h5 目录
```

### 微信小程序构建
```
pnpm run build:mp-weixin

# 构建产物在 dist/build/mp-weixin 目录
```

### 其他平台构建
```
# 构建支付宝小程序
pnpm run build:mp-alipay

# 构建百度小程序
pnpm run build:mp-baidu

# 构建字节跳动小程序
pnpm run build:mp-toutiao

# 构建 QQ 小程序
pnpm run build:mp-qq
```


# 交流与赞助
扫描下面微信二维码添加微信备注 FastapiAdmin 即可进群。

<!-- 使用HTML表格实现并排显示 -->
<table>
  <tr>
    <!-- 第一个图片：个人二维码 -->
    <td style="text-align:center; padding:10px;">
 <img src="https://github.com/user-attachments/assets/73466c31-31f6-4c25-af49-47506acb5043" alt="个人二维码" width="300" />
      <br>
 </td>
    <!-- 第二个图片：个人收款码 -->
 <td style="text-align:center; padding:10px;">
 <img src="https://github.com/user-attachments/assets/51fb80d0-09cf-4cfc-837b-42e43cbeb70b" alt="个人收款码" width="300" />
      <br>
 </td>
  </tr>
</table>



