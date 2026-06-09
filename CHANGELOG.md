# Changelog

## 1.1.0 - 2026-05-27

### 客户端

- **「更新导航数据」按钮强制 OpenList 模式**：点击后仅支持从 OpenList 自动下载，不再 fallback 到手动选包。未登录或机型不支持自动下载时直接报错提示（[main_flet.py:2211-2216](main_flet.py#L2211-L2216)）。
- **修复 `run_blocking_with_feedback` kwargs 传递**：支持 `**kwargs` 透传给被包装函数，修复 `expected_sha256` 参数无法传递导致的 `unexpected keyword argument` 错误（[main_flet.py:2895](main_flet.py#L2895)）。

## 1.0.9 - 2026-05-27

### 客户端

- **登录密码本地缓存**：DATA 登录账号密码使用 Windows DPAPI（CurrentUser 范围）加密保存到 `state.json` 的 `backup_power_password_enc` 字段，下次打开登录对话框自动回填。换 Windows 用户或换机器都解不开（[utils.py](utils.py) `encrypt_secret`/`decrypt_secret`，[main_flet.py:3632](main_flet.py#L3632)、[main_flet.py:3827](main_flet.py#L3827)）。非 Windows 平台回退到 base64（无加密保护）。
- **移除 access token 自动续期**：原本 token 过期后会用 refresh_token 静默续期；现在 token 失效直接弹"请重新登录"，配合服务端 token TTL 缩短为 10 分钟，登录态边界更明确（[main_flet.py:4368](main_flet.py#L4368)）。
- **隐藏 cmd 控制台窗口**：[FMS_UPDATE_MANAGER_beta.spec](FMS_UPDATE_MANAGER_beta.spec) 切换为 `console=False`，启动时不再附带黑色命令行窗口。崩溃信息仍由 [crash_report.py](crash_report.py) 写入文件日志。

### 服务器

- **`APP_JWT_EXPIRE_MINUTES` 默认值 60 → 10**（仅 `auth_api`，admin_panel 后台保持 120）。需要重启 `auth_api` 容器生效。已经在 `.env` 显式设置过该变量的部署不受影响。

### 安装包 / 便携版

- **去除 Beta 字样**：产品名、开始菜单文件夹、注册表键、安装目录默认值统一为 `FMS Update Manager`。文件名规范：MSI = `FMS Update Manager <版本>.msi`，便携版 = `FMS Update Manager <版本> 便携版.zip`。
- **安装目录可选 + 记忆历史路径**：MSI 切换为 `WixUI_InstallDir` 对话框集，安装时显示"目标文件夹"页面，用户可改路径。安装目录写入 `HKLM\Software\CNRPG\FMS Update Manager\InstallFolder`，下次升级时优先读取该值作为默认路径。
- **桌面快捷方式可选**：保留为可勾选的 Feature。
- **「所有应用」开始菜单**：[installer/FMS_UPDATE_MANAGER_beta.wxs](installer/FMS_UPDATE_MANAGER_beta.wxs) 注册到 `ProgramMenuFolder\FMS Update Manager`，Windows 开始菜单 → 所有应用列表中可见。
- **不再签名**：本版本不进行 Authenticode 签名，SmartScreen 会拦截首次安装（点"仍要运行"绕过）。

### 构建

- **PyInstaller 切换为目录模式**：[FMS_UPDATE_MANAGER_beta.spec](FMS_UPDATE_MANAGER_beta.spec) 加入 COLLECT，产物从单 exe 变为 `dist\FMS_UPDATE_MANAGER\` 目录树，便携 zip 与增量更新（manifest diff）才能正常工作。
- [installer/build_signed.bat](installer/build_signed.bat) 修复多项：
  - `FMS_SKIP_SIGN_EXE=1` + `FMS_SKIP_SIGN_MSI=1` 时跳过 PFX 检查（无证书也能构建）
  - WiX 命令补 `-ext WixToolset.Util.wixext -ext WixToolset.UI.wixext` 加载 util/ui 扩展
  - 路径基准修复：`SourceDir` 与 `ProjectDir` 改用绝对路径变量，避免 WiX 把 `..\` 解析为相对于 wxs 文件位置
  - `FMS_APP_VERSION` 默认值 1.0.8 → 1.0.9
- 新增 [installer/license.rtf](installer/license.rtf)（`WixUI_InstallDir` 强制要求 license 页面）。

## 1.0.8 - 2026-05-25

### 客户端

- **首次启动语言选择**：state.json 不存在 `locale` 键时弹出语言选择卡片（中/英），写入 state 后进入正常流程；覆盖 MSI / 便携 zip / 解压版所有分发渠道（[main_flet.py:444](main_flet.py#L444)）。
- **便携模式**：exe 同级存在 `portable.flag` 时，自动把 `ROAMING_DIR` / `LOCAL_DIR` / `STATE_FILE` / `BACKUP_DIR` / `LOG_DIR` / `EXTRACTED_DIR` 重定向到 `data/{roaming,local}/`（[state.py:21](state.py#L21)）。标题栏追加 "便携模式 / Portable" 标识。构建脚本同时产出 `*_portable.zip`。
- **7z 解压精细进度条**：在原 `-bsp1` 文本输出基础上新增正则解析 `42% xxx` 并实时驱动 `ProgressBar`；100% 立即收起，下次解压自动重置（[main_flet.py:2240](main_flet.py#L2240)）。
- **实时日志面板美化**：根据日志内容自动识别严重级别（error/warn/success/info/default），分别染色：红/黄/绿/蓝/默认；活动日志面板、安装状态面板、底部 log_list 三处统一应用。
- **CSS 不使用 Community2024**：[catalog.py:addon_uses_community_2024](catalog.py#L285)；CSS 安装/扫描只走主 Community 路径。
- **A346 OpenList 命名识别增强**：硬规则新增 `as346 / aerosoft+a346 / aerosoft+a340 / a346`，hints 加入 `as346 / a346 / aerosofta346 / aerosoft`；`AS346_NavData_2506.zip`、`AerosoftA346_xxx.zip` 等命名都能精确匹配（[openlist.py:46](openlist.py#L46)）。
- **AIRAC 空值自动重试**：`refresh_cycle_async` 拿到空 / `--` / `UNKNOWN` 时后台自动重试，3 次，间隔 3/8/20s；只刷 cycle，不影响其他控件（[main_flet.py:2685](main_flet.py#L2685)）。
- **增量更新机制**（仅便携模式）：
  - 文件级 diff：客户端下载 `manifest.json` + Ed25519 签名 → 验签 → 对比本地 sha256 → 仅从 `release.zip` 抽取改动文件
  - **updater 模式复用主 exe**：主程序以 `--updater <install_dir> <staging_dir> <pid>` 模式启动一个临时副本，等主进程退出后替换文件、启动新版本、30s 心跳检测、失败自动回滚到 `.update_backup/`，成功后清理（[incremental_update.py](incremental_update.py)）
  - **纯 Python Ed25519 验签**（RFC8032 实现），客户端不引入 cryptography 运行时依赖
  - 失败回退到原有 MSI 强更流程
  - MSI 安装模式跳过增量更新（兼容性，避免 MSI 数据库失同步）

### 客户端打包

- **`build_signed.bat` 新增 manifest + release.zip 生成**：PyInstaller / 签名 / WiX / MSI 签名之后追加便携 zip + manifest.json + manifest.json.sig + release.zip 步骤；私钥从 `FMS_MANIFEST_PRIVKEY` 环境变量读取；`FMS_SKIP_PORTABLE=1` / `FMS_SKIP_INCREMENTAL=1` 可单独跳过。
- **新增工具脚本**：[tools/gen_keys.py](tools/gen_keys.py) 生成 Ed25519 密钥对；[tools/build_manifest.py](tools/build_manifest.py) 扫 dist 出 manifest+签名。
- **发布说明**：[installer/INCREMENTAL_UPDATE.md](installer/INCREMENTAL_UPDATE.md)。

## 1.0.7 - 2026-05-25

### 客户端

- **版本号显示**：窗口标题在“本软件正在测试中”之后追加当前版本号（[main_flet.py:356](main_flet.py#L356)），便于截图反馈时一眼看到版本。
- **CSS 737CL 导航数据路径修正**：`Community\css-core\Data\NavData\Inactive` 路径写入与扫描适配 MSFS 2020/2024（注意是 Community 路径，不是 wasm）。
- **修复**：`main_flet.py` 中 `_normalize_path_list` 引用未导入的问题，从 `catalog` 一并 re-export。

### 服务器

- **后台「待审核用户」新增「拒绝并删除」按钮**：复用 `DELETE /api/users/{id}`，二次确认；之前只有「通过」没有「拒绝」（[deploy/admin_panel/app/ui.py](deploy/admin_panel/app/ui.py)）。
- **独立的「重置密码」站点（端口 3091）**：从注册页拆出，新增 [deploy/register_ui/app/reset.py](deploy/register_ui/app/reset.py)，复用 `_proxy_to_auth` 转发到 `auth_api`；含 Cloudflare Turnstile 校验、邮箱→验证码→新密码三步流程。`docker-compose.yml` 增 `reset_ui` 服务（镜像复用 `./register_ui`），暴露 3091 端口；Dockerfile `EXPOSE 3090 3091`。注册页底部加“前往重置密码页面”链接（自动用当前 hostname + 3091）。

## 1.0.6 - 2026-05-18

### 客户端

- **#10 main_flet 代码瘦身**：8288 → 4654 行；与 archive/catalog/network/openlist/state/targets/utils/maintenance 重复的 144 处定义被合并/搬迁到对应模块，文件末尾遗留的 120 行 `X = mod.X` 覆盖块也清空。仅纯函数级抽取，未触碰 `def main` 闭包。
- **#7 下载断点续传**：OpenList 压缩包下载与强制更新 MSI 下载均改为 `.part` + `Range: bytes=N-`；服务器不返回 206、416 时自动回退到从头下载，完成后原子 rename 为最终文件。
- **#12 崩溃上报**：新增 [crash_report.py](crash_report.py)，挂 `sys.excepthook` + asyncio loop exception handler；本地落盘 `logs/crash_*.log`；设置中加“匿名上传崩溃报告”开关（默认关），开启后后台 POST 到后端 `/api/crash`。生成首次启动持久化的 `install_id`，不上传路径/账号等敏感信息。
- **#3 客户端静默续期**：登录响应保存 `refresh_token`；`/api/me` 校验失败时先用 refresh_token 调 `/api/auth/refresh` 续期，成功则保持登录；登出与“清除 token”按钮一并清空 refresh。

### 服务器

- **#14 OpenList 期数监控**：admin_panel 新增 [openlist_client.py](deploy/admin_panel/app/openlist_client.py)，登录 token 缓存 ~110 分钟；新增 `GET /api/openlist/cycles` 与 `GET /api/openlist/cycles/{id}/msfs`；admin_panel UI 加“OpenList 期数”标签页，可查看最新期数与各期下 MSFS 压缩包列表。
- **#15 限流可配置化**：backup_auth 加 `load_rate_limits(db)`，所有限流参数（登录窗口/上限、注册尝试/成功窗口、验证码 IP 冷却、崩溃上报窗口/上限）从 `app_settings` 表 JSON 读取，admin_panel 后台改后立即生效，无需重启。admin_panel UI 加“限流设置”标签页。
- **#16 SMTP 失败重试队列**：新增 `email_outbox` 表（pending/sent/failed + attempts + next_attempt_at + last_error）；后台 worker daemon 线程每 15s 扫一次到期 pending 行；退避序列 30s / 2m / 10m / 30m / 1h（5 次后标 failed）。验证码发送失败不再返回 502 阻塞用户，邮件由 worker 重试。admin 接口 `GET /api/admin/outbox` + `POST /api/admin/outbox/{id}/retry`，admin_panel UI 加“邮件 Outbox”标签页。
- **#13 邀请码 + 注册审核**：新增 `invite_codes` 表与 `register_policy` 配置（`require_invite_code` / `require_admin_approval` 两个独立开关）。注册页根据 `/api/public/register_policy` 自动显示邀请码输入框；启用审核后新用户 `enabled=False`，admin_panel “注册策略” 页面列出待审核用户一键启用；“邀请码”页面支持生成/启用禁用/删除（可设最大次数与过期时间）。
- **#3 后端 refresh token**：backup_auth 与 admin_panel 登录响应均下发 `refresh_token`（默认 30 天）；新增 `POST /api/auth/refresh`；admin_panel 前端 `apiFetch` 在 401 时自动调 refresh 然后透明重试请求。
- **#12 崩溃上报后端**：新增 `crash_reports` 表；`POST /api/crash`（每 IP 每 60s 限 20 条）；admin 接口 `GET /api/admin/crashes` + `GET /api/admin/crashes/{id}`；admin_panel UI 加“崩溃日志”标签页（版本/异常类型过滤 + 详情展开）。
- **#4 数据库每日备份**：docker-compose 新增 `backup` 服务（基于 `mysql:8.4` 复用 `mysqldump`），每天 `BACKUP_HOUR_UTC` 默认 19:00 UTC（北京 03:00）dump 到 `BACKUP_HOST_DIR`，按 `BACKUP_RETAIN_DAYS` 保留 30 天；`--single-transaction` 不锁表。详见 [deploy/backup/README.md](deploy/backup/README.md)。

### 客户端打包

- **#11 MSI 代码签名脚手架**：新增 [installer/sign_msi.bat](installer/sign_msi.bat) 调 `signtool sign /fd SHA256 /td SHA256` + 自动 verify；证书路径与密码走 `FMS_SIGN_PFX` / `FMS_SIGN_PWD` 环境变量。[installer/build_signed.bat](installer/build_signed.bat) 串联 PyInstaller → 签 EXE → WiX 打 MSI → 签 MSI 全流程；MSI 版本号从 `FMS_APP_VERSION` 注入到 `*.wxs`。

### 修复

- **拆分后遗漏的导入**：`_addon_from_dict` / `enabled_simulators` / `addon_key` / `addon_status` / `compute_filtered_addon_entries` / `resolve_target_dir` / `resolve_wasm_target_by_folder_name` / `is_valid_community_path` / `is_valid_community2024_path` / `clear_cycle_json_scan_cache` / `custom_wasm_scan_paths` / `read_cycle_from_dir` / `cycle_json_scan_bases` / `default_community_base` / `wasm_base_candidates` 统一从对应 sibling 模块补回 `from state/catalog import (...)`，修复一系列 `NameError` 启动崩溃。
- **GitHub 通信容错**：`network.github_api_json` 加 3 次重试 + 指数退避（0.8s / 1.6s），timeout 8s → 15s；`fetch_current_cycle` 同样加 3 次重试，抵御 `SSL: UNEXPECTED_EOF_WHILE_READING` 这类瞬时连接中断。
- **本地源目录不再只识别 `*.zip`**：扫描改用 `is_supported_archive_file`，覆盖 zip / 7z / rar / tar / tar.gz / tar.bz2 / tar.xz / SFX exe，与底层解压能力一致。
- **直播模式按钮文案**：路径可见时按钮显示"隐藏路径"，路径已隐藏时显示"显示路径"（之前两处文案反了）。
- **默认窗口尺寸**：1260×700 → 1400×750。

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
