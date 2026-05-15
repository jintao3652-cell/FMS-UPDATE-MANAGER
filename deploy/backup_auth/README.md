# FMS Backup Power Auth API

**纯 API 服务**（端口 17306）。本服务只提供 JSON 接口，不再提供 HTML 页面。

- 注册页 HTML 由独立服务 `register_ui` (端口 3090) 提供
- 管理后台 UI 由独立服务 `admin_panel` (端口 1145) 提供

## 路由

- `GET /healthz`
- `GET /api/public/turnstile_site_key` —— 公开接口，仅返回 site_key（不含 secret_key）
- `POST /api/auth/register/code`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/me`
- `GET /api/admin/users`、`POST /api/admin/users`、`PATCH /api/admin/users/{id}`、`PATCH /api/admin/users/{id}/password`、`DELETE /api/admin/users/{id}`

## 部署

合并到根目录统一部署，请使用 `deploy/docker-compose.yml`：

```bash
cd deploy
cp .env.example .env
chmod 600 .env
docker compose up -d --build
```

## 配置

- 基础环境变量（DB / JWT / 管理员账号 / 注册风控）由 `deploy/.env` 提供。
- SMTP 与 Cloudflare Turnstile 配置改为存放于数据库 `app_settings` 表，统一在 admin_panel 后台中编辑。
- 未配置 SMTP 时，请求验证码接口返回 503。
- 未配置 Turnstile secret_key 时跳过人机校验，注册页也不渲染 widget。
