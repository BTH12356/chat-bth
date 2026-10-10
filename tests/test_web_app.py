"""Regression tests. All persistence uses a temporary database, never user chats."""

import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import asyncio
import anyio.to_thread
import httpx2
import requests


class AsgiClient:
    """Small synchronous facade around httpx2's in-process ASGI transport."""

    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx2.ASGITransport(app=self.app)
            async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def __init__(self, app):
        self.app = app

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def close(self):
        pass


class WorkspaceTests(unittest.TestCase):
    @staticmethod
    async def inline_to_thread(function, *args, **kwargs):
        # The managed test sandbox blocks worker-thread creation. Running the
        # same callable inline still exercises endpoint behavior deterministically.
        return function(*args, **kwargs)

    @staticmethod
    async def inline_anyio_thread(function, *args, **kwargs):
        return function(*args)

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="hermes-test-")
        cls.environment = patch.dict(os.environ, {"HERMES_DB_PATH": str(Path(cls.directory.name) / "test.db")})
        cls.environment.start()
        cls.api = importlib.import_module("web_app")
        cls.store = importlib.import_module("web_store")
        cls.original_db = cls.store.DB_PATH
        cls.store.DB_PATH = Path(cls.directory.name) / "test.db"
        cls.store.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.store.DB_PATH = cls.original_db
        cls.environment.stop()
        cls.directory.cleanup()

    def setUp(self):
        self.api.RUNTIME_PROVIDERS.clear()
        self.token = patch.object(self.api, "WEB_TOKEN", "")
        self.token.start()
        self.workspace = patch.object(self.api, "WORKSPACE_ROOT", Path(self.directory.name) / "workspaces")
        self.workspace.start()
        self.to_thread = patch.object(self.api.asyncio, "to_thread", new=self.inline_to_thread)
        self.to_thread.start()
        self.anyio_thread = patch.object(anyio.to_thread, "run_sync", new=self.inline_anyio_thread)
        self.anyio_thread.start()
        self.client = AsgiClient(self.api.app)
        project = self.client.post("/api/projects", json={"name": "Regression"}).json()
        self.conversation = self.client.post(f"/api/projects/{project['id']}/conversations", json={"title": "Keep my title", "model": "other:latest"}).json()
        self.path = f"/api/conversations/{self.conversation['id']}"

    def tearDown(self):
        self.api.RUNTIME_PROVIDERS.clear()
        self.client.close()
        self.anyio_thread.stop()
        self.to_thread.stop()
        self.workspace.stop()
        self.token.stop()

    def test_model_patch_preserves_title(self):
        response = self.client.patch(self.path, json={"model": "auto"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Keep my title")

    def test_rename_preserves_model(self):
        response = self.client.patch(self.path, json={"title": "ชื่อใหม่"})
        self.assertEqual(response.json()["model"], "other:latest")
        self.assertEqual(response.json()["title"], "ชื่อใหม่")

    def test_delete_conversation_removes_history(self):
        response = self.client.delete(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_delete_project_cascades_conversations(self):
        project_id = self.conversation["project_id"]
        response = self.client.delete(f"/api/projects/{project_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/conversations").status_code, 404)

    def test_delete_missing_resources_is_not_success(self):
        self.assertEqual(self.client.delete("/api/conversations/missing").status_code, 404)
        self.assertEqual(self.client.delete("/api/projects/missing").status_code, 404)

    def test_search_finds_projects_and_chats_across_workspace(self):
        project = self.client.post("/api/projects", json={"name": "โครงการดาวอังคาร"}).json()
        conversation = self.client.post(
            f"/api/projects/{project['id']}/conversations",
            json={"title": "แผนสำรวจพื้นผิว", "model": "auto"},
        ).json()

        by_project = self.client.get("/api/search", params={"q": "ดาวอังคาร"})
        self.assertEqual(by_project.status_code, 200)
        self.assertIn(project["id"], {item["id"] for item in by_project.json()["projects"]})

        by_chat = self.client.get("/api/search", params={"q": "พื้นผิว"})
        self.assertEqual(by_chat.status_code, 200)
        matches = {item["id"]: item for item in by_chat.json()["conversations"]}
        self.assertIn(conversation["id"], matches)
        self.assertEqual(matches[conversation["id"]]["project_name"], project["name"])

    def test_search_treats_sql_wildcards_as_text(self):
        response = self.client.get("/api/search", params={"q": "%_not-a-real-name"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"projects": [], "conversations": []})

    def test_auto_resolves_latest_tag(self):
        with patch.object(self.api, "MODEL_NAME", "demo"), patch.object(self.api, "installed_models", return_value=["demo:latest"]):
            self.assertEqual(self.api.choose_model("auto"), "demo:latest")

    def test_missing_models_are_not_claimed_ready(self):
        with patch.object(self.api, "installed_models", return_value=[]):
            response = self.client.post("/api/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 503)

    def test_auto_overrides_previous_conversation_model(self):
        with patch.object(self.api, "MODEL_NAME", "demo"), patch.object(self.api, "installed_models", return_value=["demo:latest", "other:latest"]), patch.object(self.api, "call_ollama", return_value="คำตอบ") as model:
            response = self.client.post(self.path + "/messages", json={"message": "hello", "model": "auto"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(model.call_args.args[1], "demo:latest")
        self.assertEqual(self.client.get(self.path).json()["conversation"]["model"], "auto")

    def test_attachments_reach_model_and_history_without_web_search(self):
        attachment = {"name": "notes.txt", "content": "secret https://example.test/private"}
        with patch.object(self.api, "installed_models", return_value=["demo:latest"]), patch.object(self.api, "call_ollama", return_value="คำตอบ") as model, patch.object(self.api, "get_external_context", new_callable=AsyncMock) as search:
            response = self.client.post(self.path + "/messages", json={"message": "สรุปไฟล์", "model": "demo:latest", "attachments": [attachment]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(attachment["content"], model.call_args.args[0])
        search.assert_not_called()
        messages = self.client.get(self.path).json()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertIn(attachment["content"], messages[0]["content"])

    def test_web_search_is_explicit_and_does_not_include_files(self):
        with patch.object(self.api, "installed_models", return_value=["demo:latest"]), patch.object(self.api, "call_ollama", return_value="ok"), patch.object(self.api, "get_external_context", new_callable=AsyncMock, return_value="reference") as search:
            response = self.client.post("/api/chat", json={"message": "public question", "model": "demo:latest", "search_web": True, "attachments": [{"name": "private.txt", "content": "not for search"}]})
        self.assertEqual(response.status_code, 200)
        search.assert_awaited_once_with("public question")

    def test_oversized_attachments_are_rejected_not_truncated(self):
        response = self.client.post(self.path + "/messages", json={"message": "hello", "attachments": [{"name": "big.txt", "content": "x" * 12000}]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(self.path).json()["messages"], [])

    def test_attachment_count_and_filename_validation(self):
        for files in ([{"name": "a.txt", "content": "a"}] * 6, [{"name": "a\nb.txt", "content": "a"}]):
            response = self.client.post("/api/chat", json={"message": "hello", "attachments": files})
            self.assertEqual(response.status_code, 422)

    def test_blank_message_rejected(self):
        response = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 422)

    def test_model_connection_failure_is_recoverable_and_not_persisted(self):
        with patch.object(self.api, "installed_models", side_effect=requests.ConnectionError("offline")):
            response = self.client.post(self.path + "/messages", json={"message": "hello"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.path).json()["messages"], [])

    def test_failed_generation_does_not_persist_partial_turn(self):
        with patch.object(self.api, "installed_models", return_value=["demo:latest"]), patch.object(self.api, "call_ollama", side_effect=requests.Timeout()):
            response = self.client.post(self.path + "/messages", json={"message": "hello", "model": "demo:latest"})
        self.assertEqual(response.status_code, 504)
        self.assertEqual(self.client.get(self.path).json()["messages"], [])

    def test_token_protected_routes(self):
        with patch.object(self.api, "WEB_TOKEN", "test-only"):
            self.assertEqual(self.client.get("/api/projects").status_code, 401)
            self.assertEqual(self.client.get("/api/projects", headers={"x-hermes-token": "test-only"}).status_code, 200)

    def test_runtime_api_provider_keeps_key_server_side_and_processes_chat(self):
        created = self.client.post("/api/providers", json={
            "name": "Secure API",
            "base_url": "https://provider.example/v1/",
            "api_key": "top-secret-key",
            "models": ["demo-model"],
        })
        self.assertEqual(created.status_code, 201)
        metadata = created.json()
        self.assertTrue(metadata["has_key"])
        self.assertEqual(metadata["source"], "runtime")
        self.assertNotIn("top-secret-key", created.text)
        self.assertNotIn("api_key", metadata)

        upstream = Mock()
        upstream.raise_for_status.return_value = None
        upstream.json.return_value = {"choices": [{"message": {"content": "API reply"}}]}
        with patch.object(self.api.requests, "post", return_value=upstream) as post:
            response = self.client.post("/api/chat", json={
                "message": "hello",
                "model": f"{metadata['id']}:demo-model",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "API reply")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer top-secret-key")

        deleted = self.client.delete(f"/api/providers/{metadata['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn(metadata["id"], self.api.RUNTIME_PROVIDERS)

    def test_runtime_api_provider_requires_safe_https_url(self):
        for base_url in ("http://provider.example/v1", "https://user:pass@provider.example/v1", "https://provider.example/v1?key=leak"):
            response = self.client.post("/api/providers", json={
                "name": "Unsafe",
                "base_url": base_url,
                "api_key": "secret",
                "models": ["demo"],
            })
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("secret", response.text)

    def test_runtime_api_models_remain_available_when_ollama_is_offline(self):
        self.client.post("/api/providers", json={
            "name": "Fallback API",
            "base_url": "https://provider.example/v1",
            "api_key": "secret",
            "models": ["fallback-model"],
        })
        with patch.object(self.api, "installed_models", side_effect=requests.ConnectionError("offline")):
            response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([model["label"] for model in response.json()["models"]], ["Fallback API · fallback-model"])

    def test_google_ai_studio_uses_native_generate_content_api(self):
        created = self.client.post("/api/providers", json={
            "name": "Google AI Studio",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "google-secret",
            "models": ["gemini-test"],
            "provider_type": "google",
        })
        self.assertEqual(created.status_code, 201)
        provider_id = created.json()["id"]
        self.assertEqual(
            self.api.RUNTIME_PROVIDERS[provider_id]["base_url"],
            "https://generativelanguage.googleapis.com/v1beta",
        )
        self.assertEqual(self.api.RUNTIME_PROVIDERS[provider_id]["type"], "google-ai-studio")
        upstream = Mock(status_code=200)
        upstream.raise_for_status.return_value = None
        upstream.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}]}
        with patch.object(self.api.requests, "post", return_value=upstream) as post:
            response = self.client.post("/api/chat", json={"message": "hello", "model": f"{provider_id}:gemini-test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.args[0], "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "google-secret")

    def test_google_ai_studio_build_uses_deterministic_structured_output(self):
        provider = {"id": "google", "name": "Google AI Studio", "type": "google-ai-studio", "_api_key": "secret"}
        upstream = Mock(status_code=200)
        upstream.raise_for_status.return_value = None
        upstream.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"summary":"done","files":[],"command":""}'}]}}]
        }
        with patch.object(self.api.requests, "post", return_value=upstream) as post:
            reply = self.api.call_google_ai_studio(provider, "gemini-build", "make it", task="build")
        self.assertEqual(json.loads(reply)["summary"], "done")
        config = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(config["candidateCount"], 1)
        self.assertLessEqual(config["temperature"], 0.2)
        self.assertGreaterEqual(config["maxOutputTokens"], 8192)
        self.assertEqual(config["responseSchema"]["properties"]["files"]["maxItems"], 10)

    def test_google_ai_studio_build_assistant_keeps_natural_text(self):
        config = self.api.google_build_generation_config("build_assistant")
        self.assertNotIn("responseMimeType", config)
        self.assertGreater(config["temperature"], self.api.google_build_generation_config("build")["temperature"])

    def test_page_and_assets(self):
        for path in ("/", "/static/app.js", "/static/static.css", "/static/favicon.svg"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("cache-control"), "no-store")
        page = self.client.get("/").text
        self.assertIn("app.js?v=20261007-voice02", page)
        self.assertIn("static.css?v=20261007-voice02", page)

    def test_audio_confirmation_describes_local_tts(self):
        script = (self.api.WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("Local TTS บนเครื่อง", script)
        self.assertIn("ไม่มีการส่งข้อความออกอินเทอร์เน็ต", script)
        self.assertNotIn("ถูกส่งไปยัง Google เพื่อสร้างเสียง", script)

    def test_audio_confirmation_uses_centered_create_voice_dialog(self):
        script = (self.api.WEB_ROOT / "app.js").read_text(encoding="utf-8")
        styles = (self.api.WEB_ROOT / "static.css").read_text(encoding="utf-8")
        self.assertIn('confirmAction("Create Voice ?", "สร้างเสียงด้วย Local TTS บนเครื่อง โดยไม่มีการส่งข้อความออกอินเทอร์เน็ตหรือไม่?", "สร้างเสียง", { centered: true })', script)
        self.assertIn(".centered-confirm .dialog-actions", styles)
        self.assertIn("justify-content: center", styles)

    def test_audio_endpoint_delegates_to_local_tts(self):
        audio = Path(self.directory.name) / "local-audio.mp3"
        audio.write_bytes(b"ID3")
        with patch.object(self.api, "synthesize_mp3", return_value=audio) as synthesize:
            response = self.client.post("/api/audio", json={"text": "ทดสอบเสียง", "language": "th"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.content, b"ID3")
        self.assertEqual(synthesize.call_args.args[:2], ("ทดสอบเสียง", "th"))

    def test_build_assistant_controls_are_present_once(self):
        page = self.client.get("/").text
        for element_id in ("build-chat", "build-chat-form", "build-chat-send", "build-agent-button", "clear-build-chat"):
            self.assertEqual(page.count(f'id="{element_id}"'), 1)

    def test_workspace_file_lifecycle_and_project_cleanup(self):
        project_id = self.conversation["project_id"]
        base = f"/api/projects/{project_id}/workspace/file"
        response = self.client.put(base, json={"path": "src/main.py", "content": "print('hello')\n"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(base, params={"path": "src/main.py"}).json()["content"], "print('hello')\n")
        files = self.client.get(f"/api/projects/{project_id}/workspace/files").json()["files"]
        self.assertEqual([item["path"] for item in files], ["src/main.py"])
        self.assertEqual(self.client.delete(base, params={"path": "src/main.py"}).status_code, 200)
        self.assertEqual(self.client.get(base, params={"path": "src/main.py"}).status_code, 404)

    def test_workspace_rejects_path_escape(self):
        project_id = self.conversation["project_id"]
        base = f"/api/projects/{project_id}/workspace/file"
        for path in ("../outside.py", "/tmp/outside.py"):
            self.assertEqual(self.client.put(base, json={"path": path, "content": "bad"}).status_code, 400)

    def test_workspace_runs_allowed_command_without_shell(self):
        project_id = self.conversation["project_id"]
        response = self.client.post(
            f"/api/projects/{project_id}/workspace/run",
            json={"command": "python3 -c \"print('ready')\"", "timeout": 5},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exit_code"], 0)
        self.assertEqual(response.json()["stdout"].strip(), "ready")
        blocked = self.client.post(
            f"/api/projects/{project_id}/workspace/run",
            json={"command": "sh -c 'echo unsafe'"},
        )
        self.assertEqual(blocked.status_code, 400)

    def test_build_agent_applies_files_and_runs_command(self):
        project_id = self.conversation["project_id"]
        reply = {
            "reply": '{"summary":"created app","files":[{"path":"main.py","content":"print(42)\\n"}],"command":"python3 main.py"}',
            "model": "demo:latest",
            "used_web": False,
        }
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, return_value=reply):
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/agent",
                json={"instruction": "สร้างโปรแกรม", "model": "demo:latest", "run_command": True},
            )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["files"][0]["path"], "main.py")
        self.assertEqual(result["run"]["stdout"].strip(), "42")
        saved = self.client.get(
            f"/api/projects/{project_id}/workspace/file", params={"path": "main.py"}
        ).json()
        self.assertEqual(saved["content"], "print(42)\n")

    def test_build_agent_caps_project_context_to_model_request_limit(self):
        project_id = self.conversation["project_id"]
        self.client.put(
            f"/api/projects/{project_id}/workspace/file",
            json={"path": "large.txt", "content": "x" * 20_000},
        )
        reply = {
            "reply": '{"summary":"checked","files":[],"command":""}',
            "model": "demo:latest",
            "used_web": False,
        }
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, return_value=reply) as model:
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/agent",
                json={"instruction": "ตรวจโปรเจกต์", "model": "demo:latest", "run_command": False},
            )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(model.await_args.args[0].message), 12_000)

    def test_failed_build_retains_each_reply_and_report(self):
        project_id = self.conversation["project_id"]
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, return_value={"reply": "broken JSON", "model": "deepseek-r1:7b"}):
            response = self.client.post(f"/api/projects/{project_id}/workspace/agent", json={"instruction": "สร้างเว็บไซต์", "model": "deepseek-r1:7b"})
        result = response.json()
        self.assertEqual(result["status"], "needs_attention")
        report = json.loads(self.api.read_workspace_file(project_id, result["report_path"])["content"])
        self.assertEqual(len(report["attempts"]), 3)
        root = result["report_path"].rsplit("/", 1)[0]
        for attempt in range(1, 4):
            self.assertEqual(self.api.read_workspace_file(project_id, f"{root}/{attempt}/reply.txt")["content"], "broken JSON")
        self.assertNotIn("broken JSON", self.api.build_agent_context(project_id))

    def test_deepseek_new_website_builds_in_files_and_retains_progress(self):
        project_id = self.conversation["project_id"]
        replies = [{"reply": content, "model": "deepseek-r1:7b"}
                   for path, content in [("index.html", '<html><body><link rel="stylesheet" href="styles.css"><script src="app.js"></script></body></html>'), ("styles.css", "body { color: green; }"), ("app.js", "console.log('ready');")]]
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, side_effect=replies) as model:
            result = self.client.post(f"/api/projects/{project_id}/workspace/agent", json={"instruction": "สร้างเว็บไซต์", "model": "deepseek-r1:7b", "run_command": False}).json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["attempts"], 3)
        self.assertIn("styles.css", model.await_args_list[1].args[0].message)
        runs = self.client.get(f"/api/projects/{project_id}/workspace/build-runs").json()["runs"]
        self.assertEqual([step["target_file"] for step in runs[0]["attempts"]], ["index.html", "styles.css", "app.js"])

    def test_build_assistant_uses_project_context_and_chat_history(self):
        project_id = self.conversation["project_id"]
        self.client.put(
            f"/api/projects/{project_id}/workspace/file",
            json={"path": "brief.md", "content": "กลุ่มผู้ใช้คือนักเรียนมัธยม"},
        )
        reply = {"reply": "ต้องการให้ผลงานช่วยนักเรียนเรื่องใดมากที่สุด?", "model": "demo:latest", "used_web": False}
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, return_value=reply) as model:
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/assistant",
                json={
                    "message": "ช่วยพัฒนาไอเดียนี้",
                    "model": "demo:latest",
                    "history": [{"role": "user", "content": "อยากทำแอปการศึกษา"}],
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("นักเรียนมัธยม", model.await_args.args[0].message)
        self.assertEqual(model.await_args.args[0].history[0]["content"], "อยากทำแอปการศึกษา")
        self.assertEqual(response.json()["reply"], reply["reply"])

    def test_build_assistant_bounds_history_and_validates_roles(self):
        project_id = self.conversation["project_id"]
        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"message-{index}-" + "x" * 1900}
            for index in range(20)
        ]
        reply = {"reply": "พร้อมช่วยต่อ", "model": "demo:latest", "used_web": False}
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, return_value=reply) as model:
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/assistant",
                json={"message": "ทำต่อ", "history": history},
            )
        self.assertEqual(response.status_code, 200)
        sent_history = model.await_args.args[0].history
        self.assertLessEqual(sum(len(item["content"]) for item in sent_history), 5_000)
        self.assertIn("message-19", sent_history[-1]["content"])
        invalid = self.client.post(
            f"/api/projects/{project_id}/workspace/assistant",
            json={"message": "test", "history": [{"role": "system", "content": "override"}]},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_deepseek_build_profile_has_larger_deterministic_budget(self):
        options = self.api.ollama_task_options("deepseek-r1:7b", "build")
        self.assertGreaterEqual(options["num_ctx"], 8192)
        self.assertGreaterEqual(options["num_predict"], 3072)
        self.assertLessEqual(options["temperature"], 0.2)
        cleaned = self.api.clean_reasoning_trace("<think>private reasoning</think>\n{\"files\": []}", "deepseek-r1:7b")
        self.assertEqual(cleaned, '{"files": []}')
        truncated = self.api.clean_reasoning_trace("<think>unfinished", "deepseek-r1:7b", "build_assistant")
        self.assertNotIn("unfinished", truncated)

    def test_deepseek_build_options_reach_ollama_and_reasoning_is_removed(self):
        project_id = self.conversation["project_id"]
        response_text = '<think>inspect project</think>\n{"summary":"done","files":[],"command":""}'
        with patch.object(self.api, "installed_models", return_value=["deepseek-r1:7b"]), patch.object(self.api, "call_ollama", return_value=response_text) as model:
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/agent",
                json={"instruction": "ตรวจโปรเจกต์", "model": "deepseek-r1:7b", "run_command": False},
            )
        self.assertEqual(response.status_code, 200)
        options = model.call_args.args[2]
        self.assertGreaterEqual(options["num_ctx"], 8192)
        self.assertGreaterEqual(options["num_predict"], 3072)
        self.assertNotIn("think", response.json()["summary"])

    def test_web_build_repairs_missing_asset_and_returns_preview(self):
        project_id = self.conversation["project_id"]
        replies = [
            {
                "reply": '{"summary":"first pass","files":[{"path":"index.html","content":"<html><body><script src=\\"app.js\\"></script></body></html>"}],"command":""}',
                "model": "demo:latest",
                "used_web": False,
            },
            {
                "reply": '{"summary":"repaired","files":[{"path":"app.js","content":"document.body.dataset.ready=\\"true\\";"}],"command":""}',
                "model": "demo:latest",
                "used_web": False,
            },
        ]
        with patch.object(self.api, "answer_chat", new_callable=AsyncMock, side_effect=replies) as model:
            response = self.client.post(
                f"/api/projects/{project_id}/workspace/agent",
                json={"instruction": "สร้างเว็บไซต์พร้อมใช้งาน", "model": "demo:latest", "run_command": True},
            )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["attempts"], 2)
        self.assertTrue(result["preview_url"].endswith("/workspace/preview/"))
        self.assertIn("ไม่พบไฟล์ที่อ้างอิง", model.await_args_list[1].args[0].message)
        preview = self.client.get(result["preview_url"])
        self.assertEqual(preview.status_code, 200)
        self.assertIn("<script", preview.text)

    def test_bth_create_guided_build_runs_end_to_end(self):
        project_id = self.conversation["project_id"]
        form = self.client.get("/api/bth-create/form")
        self.assertEqual(form.status_code, 200)
        self.assertEqual(form.json()["id"], "internal_dashboard.v1")
        payload = {"values": {
            "project_name": "BTH Control Center",
            "modules": ["worker_monitor", "gpu_monitor", "job_queue", "model_manager", "ai_assistant"],
            "network_scope": "local",
            "auth_enabled": True,
            "ai_assistant": True,
            "ai_capabilities": ["log_analysis", "error_assistance", "system_summary"],
            "ai_autonomy": "approval_required",
            "theme": "windows_xp.v1",
            "density": "compact",
            "language": ["th", "en"],
        }}
        preview = self.client.post(f"/api/projects/{project_id}/bth-create/spec", json=payload)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["project_spec"]["schema"], "bth.project/v1")
        built = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(built.status_code, 200, built.text)
        result = built.json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["verification"]["status"], "passed")
        self.assertIn("build_manifest.json", result["promoted_files"])
        files = {item["path"] for item in self.client.get(f"/api/projects/{project_id}/workspace/files").json()["files"]}
        self.assertIn("index.html", files)
        self.assertNotIn(".bth-create", "\n".join(files))
        self.assertEqual(self.client.get(result["preview_url"]).status_code, 200)
        rebuilt = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        self.assertEqual(rebuilt.json()["frozen_spec"]["revision"], 2)

    def test_bth_create_does_not_overwrite_direct_build(self):
        project_id = self.conversation["project_id"]
        self.client.put(f"/api/projects/{project_id}/workspace/file", json={"path": "index.html", "content": "manual"})
        payload = {"values": {
            "project_name": "Safe Build",
            "modules": ["worker_monitor", "job_queue"],
            "ai_assistant": False,
            "ai_capabilities": [],
        }}
        response = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(response.status_code, 409)
        current = self.client.get(f"/api/projects/{project_id}/workspace/file?path=index.html")
        self.assertEqual(current.json()["content"], "manual")

    def test_bth_create_standard_website_accepts_tabs_and_color_tone(self):
        project_id = self.conversation["project_id"]
        payload = {"values": {
            "project_name": "Bright Company",
            "blueprint_id": "website.company.v1",
            "tabs": ["หน้าหลัก", "บริการ", "ทีมงาน", "ติดต่อ"],
            "color_tone": "green",
            "network_scope": "internet",
            "auth_enabled": True,
            "density": "comfortable",
            "language": ["th", "en"],
        }}
        response = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["project_spec"]["blueprint"]["id"], "website.company.v1")
        self.assertEqual(result["project_spec"]["appearance"]["color_tone"], "green")
        self.assertEqual([tab["name"] for tab in result["project_spec"]["navigation"]["tabs"]], payload["values"]["tabs"])
        source = self.client.get(f"/api/projects/{project_id}/workspace/file?path=index.html").json()["content"]
        styles = self.client.get(f"/api/projects/{project_id}/workspace/file?path=styles.css").json()["content"]
        self.assertIn("ทีมงาน", source)
        self.assertIn("#059669", styles)

    def test_bth_create_digital_library_has_catalog_controls(self):
        project_id = self.conversation["project_id"]
        payload = {"values": {
            "project_name": "Bright Library",
            "blueprint_id": "catalog.library.v1",
            "tabs": ["หนังสือทั้งหมด", "วรรณกรรม", "ธุรกิจ", "เทคโนโลยี"],
            "color_tone": "orange",
            "network_scope": "internet",
            "auth_enabled": True,
            "density": "comfortable",
            "language": ["th", "en"],
        }}
        response = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["project_spec"]["blueprint"]["id"], "catalog.library.v1")
        self.assertEqual(result["verification"]["status"], "passed")
        source = self.client.get(f"/api/projects/{project_id}/workspace/file?path=index.html").json()["content"]
        script = self.client.get(f"/api/projects/{project_id}/workspace/file?path=app.js").json()["content"]
        self.assertIn('id="catalog-search"', source)
        self.assertIn('accept="application/pdf,.pdf"', source)
        self.assertIn('accept="image/*"', source)
        self.assertIn("indexedDB", script)

    def test_guided_build_lists_all_catalog_blueprints(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        for blueprint_id in (
            "catalog.library.v1",
            "catalog.documents.v1",
            "catalog.products.v1",
            "catalog.media.v1",
            "catalog.learning.v1",
        ):
            self.assertIn(f'value="{blueprint_id}"', page.text)
        for blueprint_id in (
            "website.corporate.v1",
            "website.organization.v1",
            "website.retail.v1",
            "website.services.v1",
            "website.knowledge.v1",
        ):
            self.assertIn(f'value="{blueprint_id}"', page.text)

    def test_guided_build_creates_distinct_corporate_pages(self):
        project_id = self.conversation["project_id"]
        payload = {"values": {
            "project_name": "Bright Company",
            "blueprint_id": "website.corporate.v1",
            "tabs": ["หน้าหลัก", "เกี่ยวกับ", "นโยบาย", "กฎระเบียบ", "คลังความรู้", "ติดต่อ"],
            "page_types": ["home", "about", "policy", "document_library", "knowledge_library", "contact"],
            "color_tone": "purple",
            "network_scope": "internet",
            "auth_enabled": True,
            "density": "comfortable",
            "language": ["th", "en"],
        }}
        response = self.client.post(f"/api/projects/{project_id}/bth-create/build", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["verification"]["status"], "passed")
        files = {item["path"] for item in self.client.get(f"/api/projects/{project_id}/workspace/files").json()["files"]}
        self.assertTrue({"index.html", "about.html", "policy.html", "documents.html", "knowledge.html", "contact.html"} <= files)
        policy = self.client.get(f"/api/projects/{project_id}/workspace/file?path=policy.html").json()["content"]
        documents = self.client.get(f"/api/projects/{project_id}/workspace/file?path=documents.html").json()["content"]
        self.assertIn('data-page-recipe="policy"', policy)
        self.assertIn("page-image-input", policy)
        self.assertIn("data-page-search", documents)


if __name__ == "__main__":
    unittest.main()
