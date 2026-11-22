#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CloudDrop - 口令保护的临时文件快递：上传设口令+有效期，接收方凭口令下载，到期自动销毁。"""

import os
import time
import hmac
import hashlib
import json
import uuid
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
FILES = DATA / "files"
META = DATA / "meta.json"
STATIC = BASE / "static"
FILES.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "500")) * 1024 * 1024
CLEAN_INTERVAL = int(os.getenv("CLEAN_INTERVAL_SEC", "60"))  # 后台清理周期
ALLOWED_TTL = {"1h": 3600, "6h": 21600, "24h": 86400, "72h": 259200}
MAX_PASSCODE_TRIES = 5

app = FastAPI(title="CloudDrop", docs_url=None, redoc_url=None)
_lock = threading.Lock()


# ---------- 元数据 ----------
def load_meta():
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_meta(meta):
    tmp = META.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(META)


def pass_hash(passcode, salt):
    return hashlib.pbkdf2_hmac("sha256", passcode.encode(), bytes.fromhex(salt), 120000).hex()


# ---------- 过期清理 ----------
def purge_expired():
    """删除过期包裹：文件 + 元数据。带锁，供后台线程与请求前调用。"""
    now = time.time()
    with _lock:
        meta = load_meta()
        removed = []
        for pid, pkg in list(meta.items()):
            if now >= pkg.get("expires_at", 0):
                for f in pkg.get("files", []):
                    (FILES / f["stored"]).unlink(missing_ok=True)
                del meta[pid]
                removed.append(pid)
        if removed:
            save_meta(meta)
        return removed


def cleaner_loop():
    while True:
        try:
            purge_expired()
        except Exception:
            pass
        time.sleep(CLEAN_INTERVAL)


threading.Thread(target=cleaner_loop, daemon=True).start()


def valid_pid(pid):
    return bool(pid) and len(pid) == 32 and all(c in "0123456789abcdef" for c in pid)


# ---------- 页面 ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/config")
async def config():
    return JSONResponse({"maxFileSize": MAX_FILE_SIZE, "ttlOptions": list(ALLOWED_TTL.keys())})


# ---------- 发送方：创建包裹 ----------
@app.post("/api/send")
async def send(request: Request, files: list[UploadFile] = File(...)):
    purge_expired()
    form = await request.form()
    passcode = str(form.get("passcode", "")).strip()
    ttl_key = str(form.get("ttl", "24h"))
    if not passcode:
        raise HTTPException(status_code=400, detail="请设置提取口令")
    if len(passcode) > 64:
        raise HTTPException(status_code=400, detail="口令过长")
    if ttl_key not in ALLOWED_TTL:
        raise HTTPException(status_code=400, detail="有效期无效")

    pid = uuid.uuid4().hex
    salt = secrets.token_hex(16)
    now = time.time()
    saved = []
    for f in files:
        if not f.filename:
            continue
        safe_name = Path(f.filename).name
        stored = uuid.uuid4().hex
        path = FILES / stored
        size = 0
        try:
            with path.open("wb") as out:
                while True:
                    chunk = await f.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        raise HTTPException(status_code=413, detail="文件超过大小限制")
                    out.write(chunk)
            saved.append({"name": safe_name, "size": size, "stored": stored})
        except Exception:
            path.unlink(missing_ok=True)
            raise

    if not saved:
        raise HTTPException(status_code=400, detail="没有有效文件")

    with _lock:
        meta = load_meta()
        meta[pid] = {
            "id": pid,
            "salt": salt,
            "pass_hash": pass_hash(passcode, salt),
            "created_at": now,
            "expires_at": now + ALLOWED_TTL[ttl_key],
            "ttl": ttl_key,
            "files": saved,
            "tries": 0,
            "locked": False,
        }
        save_meta(meta)

    return JSONResponse({
        "ok": True,
        "id": pid,
        "expires_at": meta[pid]["expires_at"],
        "file_count": len(saved),
    })


# ---------- 接收方：查看包裹信息（无需口令，仅展示） ----------
@app.get("/api/info/{pid}")
async def info(pid: str):
    purge_expired()
    if not valid_pid(pid):
        raise HTTPException(status_code=400, detail="链接无效")
    meta = load_meta()
    pkg = meta.get(pid)
    if not pkg:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    return JSONResponse({
        "file_count": len(pkg["files"]),
        "total_size": sum(f["size"] for f in pkg["files"]),
        "files": [{"name": f["name"], "size": f["size"]} for f in pkg["files"]],
        "expires_at": pkg["expires_at"],
        "remaining": max(0, int(pkg["expires_at"] - time.time())),
    })


# ---------- 接收方：校验口令 ----------
@app.post("/api/unlock/{pid}")
async def unlock(pid: str, request: Request):
    purge_expired()
    if not valid_pid(pid):
        raise HTTPException(status_code=400, detail="链接无效")
    body = await request.json()
    passcode = str(body.get("passcode", ""))

    with _lock:
        meta = load_meta()
        pkg = meta.get(pid)
        if not pkg:
            raise HTTPException(status_code=404, detail="文件不存在或已过期")
        if pkg.get("locked"):
            raise HTTPException(status_code=429, detail="口令错误次数过多，包裹已锁定")

        ok = hmac.compare_digest(pass_hash(passcode, pkg["salt"]), pkg["pass_hash"])
        if not ok:
            pkg["tries"] = pkg.get("tries", 0) + 1
            if pkg["tries"] >= MAX_PASSCODE_TRIES:
                pkg["locked"] = True
            save_meta(meta)
            left = MAX_PASSCODE_TRIES - pkg["tries"]
            raise HTTPException(status_code=401, detail=f"口令错误，还可尝试 {max(0,left)} 次")

        pkg["tries"] = 0
        # 签发短期下载令牌（15分钟），避免口令反复传输
        token_exp = time.time() + 900
        token_payload = f"{pid}|{int(token_exp)}"
        token_sig = hmac.new(BASE.joinpath("data/.secret").read_bytes().strip(),
                             token_payload.encode(), hashlib.sha256).hexdigest()
        token = f"{int(token_exp)}.{token_sig}"
        save_meta(meta)

    return JSONResponse({"ok": True, "token": token, "files": pkg["files"]})


def verify_token(pid, token):
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
        if time.time() > exp:
            return False
        payload = f"{pid}|{exp_s}"
        expected = hmac.new(BASE.joinpath("data/.secret").read_bytes().strip(),
                            payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


# ---------- 接收方：下载 ----------
@app.get("/api/download/{pid}/{stored}")
async def download(pid: str, stored: str, request: Request):
    purge_expired()
    if not valid_pid(pid):
        raise HTTPException(status_code=400, detail="链接无效")
    token = request.query_params.get("token", "")
    if not verify_token(pid, token):
        raise HTTPException(status_code=401, detail="下载凭证无效或已过期，请重新输入口令")

    meta = load_meta()
    pkg = meta.get(pid)
    if not pkg:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    target = None
    for f in pkg["files"]:
        if f["stored"] == stored:
            target = f
            break
    path = FILES / stored
    if not target or not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=target["name"])


# 初始化令牌密钥（持久化，服务重启后已签发的令牌仍有效）
secret_file = BASE / "data" / ".secret"
if not secret_file.exists():
    secret_file.write_bytes(secrets.token_hex(32).encode())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
