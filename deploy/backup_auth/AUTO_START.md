# 开机自动启动验证接口

目标：服务器启动后自动拉起 `auth_api`（`/api/auth/login`）和 `db`，无需手动执行 `docker compose up`。

## 1. 前提

- 部署目录为：`/opt/fms-backup-auth`
- 已能手动启动成功一次：

```bash
cd /opt/fms-backup-auth
docker compose up -d --build
```

## 2. 安装 systemd 服务

```bash
sudo cp /opt/fms-backup-auth/fms-backup-auth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fms-backup-auth.service
sudo systemctl start fms-backup-auth.service
```

## 3. 验证

```bash
systemctl status fms-backup-auth.service --no-pager
docker compose -f /opt/fms-backup-auth/docker-compose.yml ps
curl -s http://127.0.0.1:17306/healthz
```

返回示例：

```json
{"ok":true,"service":"fms-backup-auth"}
```

## 4. 说明

- `docker-compose.yml` 已设置 `restart: always`，容器异常退出会自动重启。
- `fms-backup-auth.service` 负责服务器开机后自动执行 `docker compose up -d`，确保接口服务可用。
