# FMS Admin Panel

管理后台（默认端口 1145）。

## 部署

已合并到根目录统一部署，请使用 `deploy/docker-compose.yml`：

```bash
cd deploy
cp .env.example .env
chmod 600 .env
docker compose up -d --build
```

访问 `http://<server>:1145/admin` 登录后台。

## 集中管理项

- SMTP 配置（之前是 backup_auth 的 .env，现在改为后台 UI 写入数据库 app_settings）。
- Cloudflare Turnstile site_key / secret_key（同上）。
- 用户、登录日志、邮件日志、管理审计、注册风控、邮箱域名黑白名单。
