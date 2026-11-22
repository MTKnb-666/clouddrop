# CloudDrop · 口令文件快递

一个**临时、安全**的文件传输工具：发送方上传文件时设置**提取口令**和**有效期**，生成分享链接；接收方打开链接、输入正确口令才能下载；文件到期后**自动从云端永久删除**。文件不长期留存。

> 在线预览（临时）：https://webview.e2b.bj2.sandbox.cloudstudio.club/?x-cs-sandbox-id=852d955c3b8042a2aa71827447f5b0b1&x-cs-sandbox-port=8000

---

## 一、怎么用

**发送方：**
1. 打开网站，选择/拖拽文件（支持多选）
2. 设置一个**提取口令**（如 `abc123`）
3. 选有效期：1小时 / 6小时 / 24小时 / 3天
4. 点「生成分享链接」，得到**链接**和**口令**
5. **通过不同渠道分别发送**链接和口令（更安全）

**接收方：**
1. 打开链接 → 能看到文件数量和大小，但看不到内容
2. 输入对方告知的口令 → 验证通过后下载
3. 口令连错 5 次包裹锁定；下载凭证 15 分钟过期

---

## 二、安全机制

- 口令用 **PBKDF2-HMAC-SHA256**（12 万次迭代）加盐哈希存储，绝不存明文
- 验证通过后签发**短期下载令牌**（15 分钟），口令不反复传输
- 口令错误次数限制，防暴力破解
- 分享链接用 32 位随机 ID，不可枚举
- **到期自动销毁**：后台每 60 秒扫描 + 请求前惰性清理，双保险删除文件

## 三、配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_FILE_SIZE_MB` | 500 | 单文件大小上限（MB） |
| `CLEAN_INTERVAL_SEC` | 60 | 过期清理扫描周期（秒） |
| `PORT` | 8000 | 监听端口 |

---

## 四、部署到 GitHub + 免费云主机（长期公网可用）

GitHub 仓库只存代码；文件传输需要能跑 Python 的主机。推荐：

### 1. 建 GitHub 仓库
```bash
cd filetransfer
git init
git add .
git commit -m "CloudDrop 口令文件快递"
git remote add origin https://github.com/<你的用户名>/clouddrop.git
git branch -M main
git push -u origin main
```
（推送前需在 GitHub 网页新建一个空仓库 `clouddrop`）

### 2. 部署到 Render（免费，最简单）
1. 注册 [render.com](https://render.com) → New → **Web Service** → 连接 GitHub 仓库
2. 配置：
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
3. 免费套餐休眠后首次访问稍慢，但可长期免费使用。

> ⚠️ 注意：Render 免费套餐无持久磁盘，服务重启会清空正在传输的文件。若需可靠持久化，用 Cloudflare R2 / 付费磁盘，把存储层从本地磁盘改为对象存储。

### 3. 其他可选平台
- **Fly.io**：免费额度含 3GB 持久卷，适合本应用
- **Railway**：免费试用额度，部署简单
- **自有 VPS**：`uvicorn app:app --host 0.0.0.0 --port 8000`，前面挂 Nginx + HTTPS

---

## 五、本地运行

```bash
cd filetransfer
pip install -r requirements.txt
python app.py
# 打开 http://localhost:8000
```

## 六、目录结构

```
filetransfer/
├── app.py                 # 后端（口令校验+过期清理+下载令牌）
├── requirements.txt
├── static/index.html      # 前端（发送/接收双视图）
└── data/                  # 运行时生成
    ├── files/             # 临时文件（到期自动删）
    ├── meta.json          # 包裹元数据
    └── .secret            # 下载令牌签名密钥
```
