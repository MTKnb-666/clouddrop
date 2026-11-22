# 交接说明（给新对话）

## 项目现状
CloudDrop —— 口令保护的临时文件快递工具，已完成开发、测试并本地提交。

- 代码目录：`/workspace/filetransfer/`
- git 状态：已 `git init` 并提交，commit `a3e444f`，工作区干净
- 已提交文件：`.gitignore` / `README.md` / `app.py` / `push.sh` / `requirements.txt` / `static/index.html`
- 服务：运行于 0.0.0.0:8000，健康检查 200
- 在线预览：`https://webview.e2b.bj2.sandbox.cloudstudio.club/?x-cs-sandbox-id=852d955c3b8042a2aa71827447f5b0b1&x-cs-sandbox-port=8000`

## 用户需求（已实现）
不是"进网站输密码"，而是：
- 发送方：选文件 + 设提取口令 + 选有效期（1h/6h/24h/72h）→ 生成分享链接
- 接收方：打开链接 → 输入正确口令 → 下载；文件到期自动从云端销毁
- 安全：PBKDF2 加盐哈希存口令、连错5次锁定、15分钟短期下载令牌、到期自动清理

## 待完成（唯一卡点）
推送代码到用户 GitHub 并部署到免费云主机。

**卡点原因**：旧沙箱会话失效，授权代理 `agentoshook.auth-proxy.local` 返回 401「登录态已失效」，`get_token.sh` 拿不到 GITHUB_TOKEN。用户已在手机 App 重新登录，但 CLI 沙箱会话不同步。用户选择：重开新对话刷新会话。

**新对话要做的事**：
1. 先测 token 是否恢复：
   ```bash
   source /root/.codebuddy/skills/github-connector/scripts/get_token.sh github
   ```
   若成功（无 401），用 `curl -H "Authorization: Bearer ${GITHUB_TOKEN}" https://api.github.com/user` 拿到用户名（login 字段）。
2. 推送：
   ```bash
   cd /workspace/filetransfer
   bash push.sh <用户GitHub用户名> clouddrop
   ```
   （push.sh 会自动检查/创建仓库并推送）
3. 部署到 Render：连接该仓库，Build=`pip install -r requirements.txt`，Start=`uvicorn app:app --host 0.0.0.0 --port $PORT`
4. 若 token 仍是 401，问用户要 GitHub Personal Access Token（需 repo 权限）或让用户自己在本地执行 git push。

## 注意
- 推送前确认 `.gitignore` 生效，`data/` 运行时数据不会被提交（含上传文件、meta.json、.secret）
- 不要在任何输出里打印 token 明文
