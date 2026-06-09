#!/usr/bin/env bash
# =============================================================================
# upload_to_github.sh
#   把本项目初始化为 git 仓库并推送到 GitHub。
#   推送后，.github/workflows/build.yml 会在 GitHub 上自动打包 MSI + 便携 ZIP。
#
# 用法：
#   1) 已安装 GitHub CLI (gh) 并登录：
#        ./upload_to_github.sh
#      脚本会用 gh 自动创建私有仓库并推送。
#
#   2) 已经在 GitHub 网页手动建好空仓库：
#        ./upload_to_github.sh https://github.com/<用户名>/<仓库名>.git
#      脚本会把它设为 origin 并推送。
#
# 环境变量（可选）：
#   GH_REPO_NAME   仓库名（默认：当前目录名，空格转为连字符）
#   GH_VISIBILITY  gh 建仓时的可见性：private（默认）或 public
#   GIT_BRANCH     主分支名（默认：main）
# =============================================================================
set -euo pipefail

# --- 配置 --------------------------------------------------------------------
REMOTE_URL="${1:-}"
BRANCH="${GIT_BRANCH:-main}"
VISIBILITY="${GH_VISIBILITY:-private}"

# 默认仓库名 = 当前目录名，空格 -> 连字符
DEFAULT_NAME="$(basename "$PWD" | tr ' ' '-')"
REPO_NAME="${GH_REPO_NAME:-$DEFAULT_NAME}"

say()  { printf '\033[1;36m[upload]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[upload]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[upload]\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "未找到 git，请先安装 Git。"

# --- 1) 初始化 git 仓库（如果还不是）-----------------------------------------
if [ ! -d .git ]; then
  say "初始化 git 仓库..."
  git init -q
  git symbolic-ref HEAD "refs/heads/$BRANCH"
else
  say "已是 git 仓库，跳过 init。"
fi

# 确保有用户名/邮箱（提交需要），缺失则设置一个本地默认值
if ! git config user.email >/dev/null 2>&1; then
  warn "未配置 git user.email，设置本地默认值（可稍后修改）。"
  git config user.email "ci@example.com"
  git config user.name  "FMS Release Bot"
fi

# --- 2) 提交所有文件（.gitignore 已排除产物/密钥/venv）------------------------
say "暂存并提交文件..."
git add -A
if git diff --cached --quiet; then
  say "没有需要提交的改动。"
else
  git commit -q -m "Set up CI: auto-build MSI/ZIP, auto-increment patch version, drop beta/legacy artifacts" \
    || die "提交失败。"
  say "已创建提交。"
fi

# --- 3) 确定远程仓库 ---------------------------------------------------------
if git remote get-url origin >/dev/null 2>&1; then
  say "origin 已存在：$(git remote get-url origin)"
elif [ -n "$REMOTE_URL" ]; then
  say "关联远程 origin：$REMOTE_URL"
  git remote add origin "$REMOTE_URL"
elif command -v gh >/dev/null 2>&1; then
  say "使用 gh 创建仓库：$REPO_NAME（$VISIBILITY）"
  # gh repo create 会自动添加 origin 并推送当前分支
  gh repo create "$REPO_NAME" "--$VISIBILITY" --source=. --remote=origin --push \
    || die "gh 创建/推送失败，请检查是否已 'gh auth login'。"
  say "完成！仓库已创建并推送。"
  say "前往 GitHub 仓库的 Actions 页面查看打包进度。"
  exit 0
else
  die "未指定远程地址，且未安装 gh。请重新运行：
       ./upload_to_github.sh https://github.com/<用户名>/<仓库名>.git
     或先安装并登录 GitHub CLI（gh auth login）。"
fi

# --- 4) 推送 -----------------------------------------------------------------
say "推送到 origin/$BRANCH ..."
git push -u origin "$BRANCH" || die "推送失败，请检查远程地址和权限。"

say "完成！前往 GitHub 仓库的 Actions 页面查看 MSI/ZIP 打包进度。"
say "产物将出现在该次运行的 Artifacts 区域。"

