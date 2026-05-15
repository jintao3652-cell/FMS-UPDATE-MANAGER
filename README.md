# FMS UPDATE MANAGER

FMS UPDATE MANAGER 是一个面向 Microsoft Flight Simulator 的 AIRAC 数据更新工具，主要用于批量管理机型导航数据库（cycle.json）并执行一键更新。

## 主要功能

- 支持 `MSFS 2020` 与 `MSFS 2024`
- 支持 `Steam` 与 `Xbox/MS Store` 两种平台目录结构
- 自动识别并显示机型当前 AIRAC 期号
- 一键安装与手动安装两种更新流程
- 支持从 OpenList 与 DATA 认证下载源获取导航数据
- 启动时自动检查 GitHub Releases 更新，支持跳过与失败倒计时
- 设置页手动检查更新，并显示当前版本号
- 可配置 Community 路径、Community2024 路径、WASM 扫描路径
- 支持缓存目录与自动清理周期配置
- 内置日志面板与安装状态面板

## 默认支持机型（内置）

- Fenix A320
- PMDG 737 系列（600/700/800/900）
- PMDG 777 系列（77W/77F/77ER/77L）
- TFDi MD-11
- Flight Sim Labs A321
- Just Flight RJ Professional
- FSS ERJ
- CSS 737CL
- FYCYC C919
- iFly 737 MAX8

## 目录说明

- `main_flet.py`：桌面客户端主程序
- `assets/`：图标等静态资源
- `installer/`：安装器相关文件
- `deploy/`：服务器端部署（FastAPI + MySQL + Docker Compose）
  - `deploy/backup_auth/`：认证 API（内部 17306）
  - `deploy/admin_panel/`：管理后台 UI（1145）
  - `deploy/register_ui/`：用户注册页 + 同源反向代理（3090）

## 运行环境

- Windows 10/11
- Python 3.11+
- 已安装 Microsoft Flight Simulator（2020/2024）

## 本地运行

```powershell
python main_flet.py
```

## 打包

项目提供了多个 `.spec` 文件，可使用 PyInstaller 打包。

示例：

```powershell
pyinstaller FMS_UPDATE_MANAGER.spec
```

## 更新检查配置

客户端支持通过环境变量覆盖更新源配置：

- `FMS_APP_VERSION`：当前应用版本号（建议语义化版本，如 `1.0.4`）
- `FMS_GITHUB_REPO`：更新仓库（格式：`owner/repo`）
- `FMS_GITHUB_TOKEN`：可选，GitHub API Token（用于提高 API 限额）

默认更新仓库：

- `jintao3652-cell/FMS-UPDATE-MANAGER`

更新检查逻辑：

- 优先请求 GitHub Releases API
- API 被限流或失败时回退到 `releases.atom`

## 状态文件与日志

程序默认会在用户目录生成运行数据：

- Roaming：`%APPDATA%\FMS UPDATE MANAGER`
- Local：`%LOCALAPPDATA%\FMS UPDATE MANAGER`

其中包含：

- `state.json`：本地配置与状态
- `logs/`：运行日志
- `extracted/`、`backups/`：缓存与备份数据

## 服务器端部署（可选）

后端由三个 FastAPI 服务组成，统一编排在 `deploy/docker-compose.yml`：

| 端口 | 服务 | 说明 |
|---|---|---|
| 17306 | `auth_api` | 认证 / 注册接口（**仅内部**，v1.0.5 起不再对外暴露） |
| 1145 | `admin_panel` | 管理后台 UI |
| 3090 | `register_ui` | 用户注册页 + 同源反代 `/api/*` 到 `auth_api` |

快速启动：

```bash
cd deploy
cp .env.example .env
docker compose up -d --build
```

详细说明请参考：

- 顶层 `服务器部署教程.md`
- `deploy/README.md`
- `CHANGELOG.md`

如需随服务器开机自动启动，参考 `deploy/backup_auth/AUTO_START.md` 与 `deploy/backup_auth/fms-backup-auth.service`。

## 免责声明

本工具仅用于合法授权的数据管理与更新流程。请在遵守相关服务条款与法律法规的前提下使用。
