# FMS UPDATE MANAGER - 打包与发布说明

## 1. Release 里看到安装包，但安装后没有开始菜单/自定义注册表，为什么？
当前 MSI 来自 `installer/FMS_UPDATE_MANAGER.wxs`，核心安装定义只有：
- 安装目录：`INSTALLFOLDER`
- 文件复制：`<Files Include="$(var.SourceDir)\\**" />`

这表示安装器当前只负责“把文件装到目标目录”。

### 1.1 现状结论
- 能看到 MSI 安装包：正常。
- 安装包 Hash 校验完整：只代表文件传输完整，不代表功能配置完整。
- 安装后没有开始菜单快捷方式：当前未定义 `Shortcut` 相关组件。
- 安装后没看到业务自定义注册表：当前未定义 `RegistryValue` 组件。

### 1.2 关于“注册表”的误区
MSI 一般会写入 Windows Installer 自身的产品登记信息（用于“应用和功能”管理），
但这不等同于应用自己的业务注册表项（例如 `HKLM\\Software\\YourApp`）。

## 2. Release 建议产物
每次发布建议至少包含：
- `FMS_UPDATE_MANAGER_Installer.msi`
- `FMS_UPDATE_MANAGER.zip`（可选便携包）
- `SHA256SUMS.txt`（或 `*.sha256`）

Hash 生成示例（PowerShell）：

```powershell
Get-FileHash .\dist\FMS_UPDATE_MANAGER_Installer.msi -Algorithm SHA256
```

## 3. 必测项目（发布门禁）
下面项目必须全部覆盖并记录结果（通过/失败/备注）。

### 3.1 安装与升级链路
- 干净机器全新安装
- 升级（从旧版本到新版本）
- 修复（Repair）
- 卸载（是否卸载干净）

### 3.2 安装方式
- 图形安装（可修改安装目录）
- 静默安装：

```powershell
msiexec /i FMS_UPDATE_MANAGER_Installer.msi /quiet /norestart
```

### 3.3 系统与权限维度
- Windows 10 / Windows 11
- 64 位系统（当前包为 x64）
- 管理员用户 / 标准用户
- 32 位系统（如需支持，需额外产出 x86 包；当前 x64 包应视为不支持）

### 3.4 自修复（Self-Healing）
- 删除关键文件后触发修复是否能恢复
- 入口方式：控制面板 Repair 或重新执行 MSI（维护模式）
- 修复后程序是否可正常启动

### 3.5 结果核验
- 程序可启动、主功能可用
- 安装目录正确
- 升级后配置/数据迁移符合预期
- 卸载后残留目录、残留注册信息是否符合设计
- 静默安装返回码为 0

## 4. 已知限制（当前打包脚本）
当前 `installer/FMS_UPDATE_MANAGER.wxs` 未定义：
- 开始菜单快捷方式组件
- 桌面快捷方式组件
- 自定义注册表写入组件

如果需要上述能力，需要在 WiX 脚本中补充 `Component + Shortcut + RegistryValue + RemoveFolder` 等定义。

## 5. 建议的发布前检查单（可复制到 Issue）
- [ ] MSI 可安装且可自定义安装目录
- [ ] 全新安装通过
- [ ] 升级通过
- [ ] Repair 通过
- [ ] 卸载通过（残留符合预期）
- [ ] 静默安装通过
- [ ] Win10/Win11 覆盖完成
- [ ] 管理员/标准用户覆盖完成
- [ ] Self-Healing 验证通过
- [ ] Release 附带 SHA256 校验信息
