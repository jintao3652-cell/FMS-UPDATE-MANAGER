# FMS UPDATE MANAGER 部署

三服务 + MySQL，统一编排，共用同一个数据库。

## 端口职责

| 端口 | 服务 | 暴露 | 职责 |
|---|---|---|---|
| 17306 | `auth_api` | **仅内部** | 登录、注册、Turnstile 校验、admin REST |
| 1145 | `admin_panel` | 公网 | 完整管理后台 UI |
| 3090 | `register_ui` | 公网 | 用户注册页 + 同源反代 `/api/*` 到 `auth_api` |

`db`：仅容器内部 3306，不对外暴露。

> v1.0.5 起 `auth_api` 不再暴露端口。浏览器对 `/api/*` 的请求由 `register_ui` 同源反代，因此不需要跨域配置，也不需要 `APP_REGISTER_PUBLIC_AUTH_URL`。

## 首次部署

```bash
cd deploy
cp .env.example .env
chmod 600 .env
# 必改：MYSQL_*、APP_JWT_SECRET、APP_ADMIN_PASSWORD
docker compose up -d --build
```

## 完成注册功能配置

SMTP 与 Cloudflare Turnstile 配置存放在数据库 `app_settings` 表，统一在管理后台填写：

1. 浏览器打开 `http://<server>:1145/`
2. 使用 `APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD` 登录
3. **SMTP**：填主机/用户名/密码/发件人，保存后可"发送测试邮件"验证
4. **Turnstile**：填 site_key / secret_key（可选；不填则注册流程跳过人机校验）

未配置 SMTP 前，注册接口请求验证码会返回 503。

## 访问入口

- 用户注册：`http://<server>:3090/`
- 管理后台：`http://<server>:1145/`
- 健康检查：`curl http://<server>:3090/healthz`

`auth_api` 已不对外，需要直接探活时：

```bash
docker compose exec auth_api curl -sf http://127.0.0.1:17306/healthz
```

## 升级 / 重置

```bash
docker compose pull
docker compose up -d --build
```

彻底清空数据库（会丢失所有用户和后台设置）：

```bash
docker compose down -v
docker compose up -d --build
```

## 重要环境变量

- `APP_REGISTER_PUBLIC_AUTH_URL`：**v1.0.5 起留空**。前端会请求同源 `/api/*`，由 `register_ui` 反代到 `auth_api`。仅当你希望前端绕过反代直连外部 auth_api 时才需要填写。
- `APP_ALLOWED_ORIGINS`：默认 `*`。由于走同源反代，已无跨域诉求；如需收紧，可只允许 `register_ui` 与 `admin_panel` 所在域名。
