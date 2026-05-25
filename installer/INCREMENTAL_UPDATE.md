# 增量更新（Incremental Update）发布流程

## 概念
- 仅便携 zip 用户享受增量更新；MSI 安装版继续走 MajorUpgrade（兼容性原因）
- 客户端通过 Ed25519 公钥验签 manifest，公钥硬编码在 [update_keys.py](../update_keys.py)
- 每次发布 GitHub Release 必须包含 4 个 asset：
  - `manifest.json`
  - `manifest.json.sig`
  - `release.zip`（dist 目录整体打包）
  - `*.msi`（MSI 安装包，老逻辑保留）

## 一次性准备
1. 生成密钥对（仅做一次）：
   ```
   .venv\Scripts\python tools\gen_keys.py
   ```
2. 把 `tools/keys/manifest_priv.pem` 备份到安全位置（U 盘/密码管理器），**永远不要提交或上传**
3. `tools/keys/manifest_pub.pem` 中的公钥已经写入 [update_keys.py](../update_keys.py) 的 `PUBLIC_KEY_HEX`，客户端用它验签
4. **如私钥泄露**：重新跑 `gen_keys.py` → 替换 `update_keys.py` 中的 `PUBLIC_KEY_HEX` → 发新版本客户端 → 旧版本以后将无法再增量更新（必须用 MSI 全量升级一次）

## 每次发版
1. 设置环境变量：
   ```
   set FMS_SIGN_PFX=C:\path\to\codesign.pfx
   set FMS_SIGN_PWD=...
   set FMS_MANIFEST_PRIVKEY=C:\path\to\manifest_priv.pem
   set FMS_APP_VERSION=1.0.8
   ```
2. 跑构建：
   ```
   installer\build_signed.bat beta
   ```
3. 产出：
   - `dist_beta\FMS_UPDATE_MANAGER_beta\` —— 程序目录
   - `installer\FMS_UPDATE_MANAGER_beta_Installer.msi` —— 已签名 MSI
   - `installer\FMS_UPDATE_MANAGER_beta_Installer_portable.zip` —— 便携 zip（含 portable.flag）
   - `installer\manifest.json` + `installer\manifest.json.sig` —— 增量清单 + 签名
   - `installer\release.zip` —— 整包 zip（不含 portable.flag，供增量更新抽取改动文件）

4. 上传到 GitHub Release：
   - `*.msi`
   - `*_portable.zip`
   - `manifest.json`
   - `manifest.json.sig`
   - `release.zip`

   命名固定，客户端按文件名匹配。

## 跳过开关
- `set FMS_SKIP_PORTABLE=1` —— 不打便携 zip
- `set FMS_SKIP_INCREMENTAL=1` —— 不生成 manifest / release.zip
- `set FMS_SKIP_SIGN_EXE=1` / `set FMS_SKIP_SIGN_MSI=1` —— 跳过签名

## 客户端行为
- 启动检查发现新版本时：
  - 便携模式 + Release 含 `manifest.json` → 走 [incremental_update.py](../incremental_update.py)：下载 manifest → 验签 → diff → 下载 release.zip → 抽取改动文件到 `<install>/.update_staging/` → 启动 updater 副本 → 主进程退出
  - updater 副本：等主进程退出 → 备份原文件到 `<install>/.update_backup/` → 应用 staging → 启动新主进程 → 30s 心跳检测
  - 失败：自动回滚到 `.update_backup/`，重启旧版本
  - 成功：清理 `.update_backup/` 和 `.update_staging/`
- MSI 安装模式：走原有 MSI MajorUpgrade 流程，不变

## 故障排查
- updater 日志：`<install>/.update_log`
- 心跳文件：`<install>/.update_heartbeat`（updater 等这个文件出现来判定新版本启动成功）
- 如果用户安装目录里出现 `.update_staging/` 或 `.update_backup/` 残留，说明上次更新中途崩溃，可手动删除。
