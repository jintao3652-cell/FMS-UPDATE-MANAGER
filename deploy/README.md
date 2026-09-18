# FMS UPDATE MANAGER 部署

`auth_api` + `web` + MySQL + 备份，统一编排，共用同一个数据库。

## 端口职责

| 端口 | 服务 | 暴露 | 职责 |
|---|---|---|---|
| 17306 | `auth_api` | 公网 | 登录、注册、Turnstile 校验、admin REST。**桌面客户端直连此端口**，不可变更 |
| 3090 | `web` | 公网 | 注册页 `/register`(`/zhuce`)、重置密码页 `/resetpsw`(`/resetpassword`)、管理后台 `/admin`。`/api/*` 同源反代到 `auth_api` |

`db`：仅容器内部 3306，不对外暴露。

> 注册/重置/admin 已合并到单一 `web` 容器（端口 3090）。浏览器对注册/重置相关 `/api/*` 的请求由 `web` 同源反代到 `auth_api`，因此不需要跨域配置，`APP_REGISTER_PUBLIC_AUTH_URL` 留空即可。
> `auth_api` 仍单独暴露 17306 供桌面客户端使用。

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

1. 浏览器打开 `http://<server>:3090/admin`
2. 使用 `APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD` 登录
3. **SMTP**：填主机/用户名/密码/发件人，保存后可"发送测试邮件"验证
4. **Turnstile**：填 site_key / secret_key（可选；不填则注册流程跳过人机校验）

未配置 SMTP 前，注册接口请求验证码会返回 503。

## 访问入口

- 用户注册：`http://<server>:3090/register`（别名 `/zhuce`）
- 重置密码：`http://<server>:3090/resetpsw`（别名 `/resetpassword`）
- 管理后台：`http://<server>:3090/admin`
- 健康检查：`curl http://<server>:3090/healthz`
- auth_api（桌面客户端）：`curl http://<server>:17306/healthz`

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

- `APP_AUTH_API_URL`：`web` 容器反代注册/重置 `/api/*` 的目标，默认 `http://auth_api:17306`（容器内网），一般无需改。
- `APP_REGISTER_PUBLIC_AUTH_URL`：**留空**。注册/重置页请求同源 `/api/*`，由 `web` 反代到 `auth_api`。
- `APP_ALLOWED_ORIGINS`：默认 `*`。由于走同源反代，已无跨域诉求；如需收紧，可只允许 `web` 所在域名。
