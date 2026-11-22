#!/bin/bash
# 一键推送到 GitHub（使用 CodeBuddy 连接器的 OAuth token，不落明文）
# 用法: bash push.sh <你的GitHub用户名> [仓库名，默认 clouddrop]
set -e

OWNER="${1:?用法: bash push.sh <GitHub用户名> [仓库名]}"
REPO="${2:-clouddrop}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> 获取 GitHub 授权"
source /root/.codebuddy/skills/github-connector/scripts/get_token.sh github

echo "==> 检查/创建远端仓库 $OWNER/$REPO"
CODE=$(curl -s -o /tmp/gh_repo_check.json -w "%{http_code}" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/$OWNER/$REPO")
if [ "$CODE" = "404" ]; then
  echo "仓库不存在，正在创建..."
  curl -s -X POST -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Content-Type: application/json" \
    "https://api.github.com/user/repos" \
    -d "{\"name\":\"$REPO\",\"private\":false,\"description\":\"口令保护的临时文件快递工具\"}" \
    > /tmp/gh_repo_create.json
  grep -q '"full_name"' /tmp/gh_repo_create.json && echo "仓库创建成功" || { echo "创建失败:"; cat /tmp/gh_repo_create.json; exit 1; }
elif [ "$CODE" = "200" ]; then
  echo "仓库已存在，直接使用"
else
  echo "检查仓库失败(HTTP $CODE):"; cat /tmp/gh_repo_check.json; exit 1
fi

cd "$SCRIPT_DIR"
echo "==> 配置本地 git"
git init -q 2>/dev/null || true
git config user.name "$(curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" https://api.github.com/user | python3.11 -c 'import sys,json;print(json.load(sys.stdin).get("name") or json.load(sys.stdin).get("login"))' 2>/dev/null || echo CloudDrop)"
git config user.email "$(curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" https://api.github.com/user | python3.11 -c 'import sys,json;print(json.load(sys.stdin).get("email") or "noreply@github.com")' 2>/dev/null || echo noreply@github.com)"
git add .
git commit -m "CloudDrop: 口令文件快递（口令保护+到期自毁）" -q || echo "无新改动"
git branch -M main

echo "==> 推送代码"
git remote remove origin 2>/dev/null || true
git remote add origin "https://oauth2:${GITHUB_TOKEN}@github.com/${OWNER}/${REPO}.git"
git push -u origin main

echo "==> 完成！仓库地址: https://github.com/$OWNER/$REPO"
