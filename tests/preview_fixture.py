"""Isolated UI fixture: python -m tests.preview_fixture (no model/network calls)."""

import os
import json
from pathlib import Path
import tempfile
import time

import uvicorn
import requests


def main():
    with tempfile.TemporaryDirectory(prefix="hermes-ui-") as directory:
        os.environ["HERMES_DB_PATH"] = str(Path(directory) / "fixture.db")
        import web_app
        import web_store

        web_app.WEB_TOKEN = ""
        web_app.MODEL_NAME = "demo"
        web_app.installed_models = lambda: ["demo:latest", "code:latest"]

        def reply(prompt, model, options_override=None):
            time.sleep(2)
            if "จำลองข้อผิดพลาด" in prompt:
                raise requests.ConnectionError("UI fixture failure")
            if "coding agent" in prompt:
                if "งานนี้เป็นเว็บไซต์" in prompt:
                    return json.dumps({
                        "summary": "สร้างเว็บไซต์ทดสอบแล้ว",
                        "files": [
                            {"path": "index.html", "content": '<!doctype html><html lang="th"><head><meta charset="utf-8"><title>Build Test</title><link rel="stylesheet" href="styles.css"></head><body><main><h1>เว็บไซต์พร้อมใช้งาน</h1><button id="action">ทดสอบ</button><p id="result"></p></main><script src="app.js"></script></body></html>'},
                            {"path": "styles.css", "content": "body{font-family:sans-serif;padding:2rem;background:#eef7f1;color:#173b2c}"},
                            {"path": "app.js", "content": 'document.querySelector("#action").onclick=()=>document.querySelector("#result").textContent="ทำงานแล้ว";'},
                        ],
                        "command": "",
                    }, ensure_ascii=False)
                return '{"summary":"สร้างโปรแกรมทดสอบแล้ว","files":[{"path":"main.py","content":"print(42)\\n"}],"command":"python3 main.py"}'
            return "นี่คือคำตอบจากระบบทดสอบ UI\n\nข้อความภาษาไทยแสดงผลถูกต้อง และยังเก็บประวัติไว้เมื่อสลับแชท"

        web_app.call_ollama = reply
        web_app.resource_snapshot = lambda: {"gpus": [], "memory": {"used": 2048, "total": 8192, "percent": 25}, "load": 0.4}
        project = web_store.create_project("UI test workspace")
        web_store.create_conversation(project["id"], "ทดสอบการใช้งาน", "auto")
        uvicorn.run(web_app.app, host="127.0.0.1", port=8092)


if __name__ == "__main__":
    main()
