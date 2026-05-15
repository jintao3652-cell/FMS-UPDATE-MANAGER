# Changelog

## 1.0.5 - 2026-05-15

### 后端部署架构调整

- **`register_ui` 新增同源反向代理**：`/api/auth/*` 与 `/api/public/*` 由 `register_ui` 透传到内部 `auth_api`，浏览器不再直连 17306，注册页和验证码接口走同源请求，无跨域问题。
- **`auth_api` 不再向宿主机暴露 17306 端口**：仅在 Docker 内部网络监听，公网攻击面进一步收敛。
- **简化配置**：`APP_REGISTER_PUBLIC_AUTH_URL` 默认留空即可正常工作（旧版本必须填写公网可达 URL，否则前端会请求到 `register_ui` 自身导致 `{"detail":"Not Found"}`）。
- 修复 `register_ui` 前端 fetch URL 中误用反斜杠（`'\api\auth\register'`）触发 Python 字符串转义、导致请求路径异常的隐患（已在源码中以正斜杠重写）。

### 注册流程安全加固

- **Turnstile token 服务端去重**：`verify_turnstile` 通过 Cloudflare 校验后会把 token 记入内存（10 分钟 TTL），同一 token 二次提交直接返回 400 `turnstile token already used`，杜绝前端 reset 失败时的 token 复用。
- **验证码发送同 IP 60 秒冷却**：同一来源 IP 在 60 秒内只允许发送一次验证码，超过返回 429 并提示剩余等待秒数。
- **验证码发送同邮箱按 `per_email_window_seconds` 限流**（默认 60 秒，可在 SMTP 配置中调整），防止针对单个邮箱的轰炸。
- **前端在每次提交后自动 `turnstile.reset()`**，并在 token 为空时直接提示用户先完成人机验证，避免无意义请求。

### 文档

- `服务器部署教程.md`、`deploy/README.md`、`README.md` 同步说明新架构、Cloudflare Turnstile hostname 白名单与本地测试密钥。

### 升级提示

```bash
cd deploy
git pull
docker compose up -d --build
```

升级后建议在 `.env` 中清空 `APP_REGISTER_PUBLIC_AUTH_URL`；若使用 Nginx / 防火墙限制了 17306 入站，本次升级后可直接移除该规则。

## 1.0.4 - 2026-04-21

- 修复安装后在 Windows 开始菜单中偶发无法直接找到程序的问题，补充并稳定开始菜单快捷方式。
- 安装向导新增可选项：可在安装时选择是否创建桌面图标。
- 安装 UI 调整为可选择功能树，便于按需安装快捷方式组件。
- 统一客户端与安装器版本号为 `1.0.4`。

## 1.0.3 - 2026-04-20

- 修复一键安装场景下窗口关闭后可能触发的会话销毁异常（`An attempt to fetch destroyed session`）。
- 优化一键安装统计逻辑，区分"未安装"与"云盘无数据"等状态。
- 新增"最新周期跳过下载"策略：本地已是最新 AIRAC 时直接跳过下载。
- 优化 DATA 登录错误提示：当接口返回 `401 invalid credentials` 时给出更明确引导。
- 版本升级至 `1.0.3`。
