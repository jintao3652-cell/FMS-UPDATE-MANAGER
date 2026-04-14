# FMS 后备隐藏能源登录服务部署（MySQL）

固定登录接口：

- `POST http://data.cnrpg.top:17306/api/auth/login`

新增页面：

- 注册页：`http://data.cnrpg.top:17306/register`
- 管理页：`http://data.cnrpg.top:17306/admin`

## 1. 准备

1. 域名 `data.cnrpg.top` 解析到服务器公网 IP
2. 安装 Docker + Docker Compose（或 1Panel 编排）
3. 放行端口 `17306/tcp`

## 2. 配置环境变量

```bash
cd /opt/fms-backup-auth
cp .env.example .env
```

修改 `.env`（至少）：

- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `APP_JWT_SECRET`
- `APP_ADMIN_PASSWORD`
- SMTP（邮箱验证码必需）：
  - `APP_SMTP_HOST`
  - `APP_SMTP_PORT`
  - `APP_SMTP_USER`
  - `APP_SMTP_PASSWORD`
  - `APP_SMTP_SENDER`
  - `APP_SMTP_USE_SSL` / `APP_SMTP_USE_TLS`

## 3. 启动

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f auth_api
```

## 4. 接口验证

```bash
curl -X POST "http://data.cnrpg.top:17306/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<你的管理员密码>","client":"FMS UPDATE MANAGER"}'
```

## 5. 客户端请求格式

```json
{
  "username": "xxx",
  "password": "xxx",
  "client": "FMS UPDATE MANAGER",
  "timestamp": "2026-..."
}
```

返回格式兼容：

```json
{
  "success": true,
  "message": "ok",
  "token": "xxxxx"
}
```

## 6. Build 失败排查（pip 拉包）

如遇：

- `No matching distribution found`
- `from versions: none`

执行无缓存重建：

```bash
docker compose build --no-cache auth_api
docker compose up -d
```

如需改阿里镜像源：

```bash
docker compose build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  --build-arg PIP_TRUSTED_HOST=mirrors.aliyun.com \
  --no-cache auth_api
docker compose up -d
```
