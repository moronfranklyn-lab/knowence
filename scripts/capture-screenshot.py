#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Chrome DevTools Protocol 走真实登录流程并截图。

不用探针页/localStorage 注入 —— 直接驱动真实登录表单，
拿到的就是真实用户会看到的界面。

用法：
    /tmp/bp-venv/bin/python cdp_shot.py \
        --url http://127.0.0.1:8081 \
        --email admin@knowence.local --password '...' \
        --chat 87c85d5b-336d-4850-ba9c-25289aef7154 \
        --out docs/images/chat-with-citations.png
"""
import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333


async def cdp(ws, method, params=None, timeout=30):
    mid = cdp._id = getattr(cdp, "_id", 0) + 1
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
        msg = json.loads(raw)
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(f"{method} 失败: {msg['error']}")
            return msg.get("result", {})
        # 忽略事件
    raise TimeoutError(method)


async def evaluate(ws, expr, timeout=30):
    r = await cdp(ws, "Runtime.evaluate",
                  {"expression": expr, "awaitPromise": True, "returnByValue": True},
                  timeout=timeout)
    return (r.get("result") or {}).get("value")


async def wait_for(ws, expr, timeout=30, interval=0.7, label=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if await evaluate(ws, expr, timeout=8):
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    print(f"    ⚠️ 等待超时: {label or expr[:60]}")
    return False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--chat", default="", help="要打开的会话 ID，留空则截工作台")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--wait", type=float, default=12.0, help="页面渲染额外等待秒数")
    ap.add_argument("--model", default="", help="要切换到的模型名（模糊匹配下拉项）")
    a = ap.parse_args()

    profile = "/tmp/cdp-profile"
    subprocess.run(["rm", "-rf", profile], check=False)
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
        "--no-sandbox", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
        f"--window-size={a.width},{a.height}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        ws_url = None
        for _ in range(40):
            await asyncio.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3) as r:
                    targets = json.loads(r.read())
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                continue
        if not ws_url:
            print("❌ 连不上 Chrome 调试端口")
            return 1
        print("    Chrome 已就绪")

        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            await cdp(ws, "Page.enable")
            await cdp(ws, "Runtime.enable")
            await cdp(ws, "Emulation.setDeviceMetricsOverride", {
                "width": a.width, "height": a.height,
                "deviceScaleFactor": 2, "mobile": False,
            })

            # ---- 1) 打开登录页 ----
            print("  → 打开登录页")
            await cdp(ws, "Page.navigate", {"url": f"{a.url}/login"})
            await asyncio.sleep(4)
            await wait_for(ws, "!!document.querySelector('input[type=password]')", 25, label="登录表单出现")

            # 提前标记所有引导为"已看过" —— 必须在登录前做，
            # 登录后再写 localStorage 会干扰 SPA 的登录态
            await evaluate(ws, """
              (() => {
                ['kb-list:v2','kb-create:v3','tenant-models:v1','kb-detail:v1',
                 'chat:v1','agent-list:v1','agent-create:v1'].forEach(k =>
                   localStorage.setItem('weknora:contextual-guide-' + k, '1'));
                return 'ok';
              })()
            """)
            print("    已预置引导标记（登录前）")

            # ---- 2) 填表并提交 ----
            print("  → 填写账号密码并提交")
            filled = await evaluate(ws, f"""
              (() => {{
                const inputs = [...document.querySelectorAll('input')];
                const pwd = document.querySelector('input[type=password]');
                const email = inputs.find(i => i !== pwd && (i.type==='text'||i.type==='email'||!i.type));
                if (!email || !pwd) return 'no-inputs';
                const setter = Object.getOwnPropertyDescriptor(
                  window.HTMLInputElement.prototype, 'value').set;
                setter.call(email, {json.dumps(a.email)});
                email.dispatchEvent(new Event('input', {{bubbles:true}}));
                email.dispatchEvent(new Event('change', {{bubbles:true}}));
                setter.call(pwd, {json.dumps(a.password)});
                pwd.dispatchEvent(new Event('input', {{bubbles:true}}));
                pwd.dispatchEvent(new Event('change', {{bubbles:true}}));
                return 'ok';
              }})()
            """)
            if filled != "ok":
                print(f"    ⚠️ 填表结果: {filled}")
            await asyncio.sleep(1)

            clicked = await evaluate(ws, """
              (() => {
                const btns = [...document.querySelectorAll('button')];
                const b = btns.find(x => /登\\s*录|登录|Sign in|Login/i.test(x.textContent||''));
                if (!b) return 'no-button';
                b.click(); return 'clicked';
              })()
            """)
            print(f"    提交: {clicked}")

            # ---- 3) 等登录完成 ----
            ok = await wait_for(ws, "location.pathname.startsWith('/platform')", 40,
                                label="跳转到 /platform")
            print(f"    登录{'成功' if ok else '未确认'}，当前路径: "
                  f"{await evaluate(ws, 'location.pathname')}")

            # ---- 4) 打开目标会话 ----
            if a.chat:
                print(f"  → 打开会话 {a.chat[:8]}…")
                await cdp(ws, "Page.navigate", {"url": f"{a.url}/platform/chat/{a.chat}"})
                await asyncio.sleep(4)
                # 兜底：若仍有引导浮层，点掉它（只点关闭按钮，不碰 localStorage）
                await evaluate(ws, """
                  (() => { document.querySelectorAll('.guide__close, .guide__skip')
                             .forEach(b => b.click()); return 'ok'; })()
                """)
                await asyncio.sleep(1)
                await wait_for(ws, "document.body.innerText.length > 200", 30, label="聊天内容加载")
                # 等答案流式渲染完（引用标记出现）
                await wait_for(ws, "/kb doc=|<kb |引用|参考资料/.test(document.body.innerText)",
                               30, label="引用出现")
                # 若指定了模型，切换下拉到它
                if a.model:
                    print(f"  → 切换模型到「{a.model}」")
                    for attempt in range(4):
                        opened = await evaluate(ws, """
                          (() => {
                            const t = document.querySelector('.model-selector-trigger');
                            if (!t) return 'no-trigger';
                            t.click(); return 'clicked';
                          })()
                        """)
                        await asyncio.sleep(1.5)
                        picked = await evaluate(ws, f"""
                          (() => {{
                            const opts = [...document.querySelectorAll('.model-option')];
                            if (!opts.length) return 'no-options';
                            const t = opts.find(o => (o.textContent||'').includes({json.dumps(a.model)}));
                            if (!t) return 'not-found';
                            t.click(); return 'picked';
                          }})()
                        """)
                        print(f"      第 {attempt+1} 次: {opened} / {picked}")
                        if picked == 'picked':
                            break
                        await asyncio.sleep(1)
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(3)

            print(f"  → 额外等待 {a.wait}s 让页面稳定")
            await asyncio.sleep(a.wait)

            # ---- 5) 截图 ----
            shot = await cdp(ws, "Page.captureScreenshot",
                             {"format": "png", "captureBeyondViewport": False}, timeout=60)
            data = base64.b64decode(shot["data"])
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            with open(a.out, "wb") as f:
                f.write(data)
            print(f"\n✅ 截图已保存: {a.out}  ({len(data)} 字节)")
            return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
