"""Exercise actual launchers with synthetic configuration; no OpenAI requests."""
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile

from gptapps.build import build_app
from gptapps.spec import import_export


ROOT = Path(__file__).resolve().parents[1]


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={} if body is None else {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=3)


def wait_ready(process, base, logfile, timeout=20, builder=True):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("Launcher exited early: " + logfile.read_text())
        try:
            with request(base, "/api/config") as response:
                if json.load(response).get("builder_enabled") is builder:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.05)
    raise AssertionError("Launcher did not become ready: " + logfile.read_text())


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class LauncherTests(unittest.TestCase):
    def test_generated_launcher_uses_its_own_code_and_manifest_model(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            app = import_export(json.loads((ROOT / "examples" / "minimal-export.json").read_text()))[0]
            app["runtime"]["model"] = "test-model"
            standalone = folder / "generated application"
            build_app(app, standalone)
            port = unused_port()
            base = f"http://127.0.0.1:{port}"
            env = {key: value for key, value in os.environ.items()
                   if key not in ("OPENAI_MODEL", "OPENAI_SETUP_MODEL", "PYTHONPATH")}
            env.update(OPENAI_API_KEY="test-only-not-a-real-key", GPTAPPS_PYTHON=sys.executable)
            logfile = folder / "generated.log"
            for script in ("start.sh", "docker-start.sh"):
                self.assertTrue(os.access(standalone / script, os.X_OK))
                help_result = subprocess.run(["bash", str(standalone / script), "--help"],
                                             env=env, capture_output=True, text=True)
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
            with logfile.open("w") as log:
                process = subprocess.Popen(["bash", str(standalone / "start.sh"), "--port", str(port),
                    "--data", "custom history", "--no-browser"], cwd=folder, env=env, stdout=log, stderr=log)
                try:
                    wait_ready(process, base, logfile, builder=False)
                    with request(base, "/api/apps") as response:
                        self.assertEqual([item["id"] for item in json.load(response)], [app["id"]])
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        request(base, "/api/setup", {"field": "name", "message": "Hello"})
                    self.assertEqual(failure.exception.code, 403)
                    failure.exception.close()
                finally:
                    stop(process)
            self.assertTrue((standalone / "custom history" / "sessions.sqlite3").exists())
            self.assertNotIn(env["OPENAI_API_KEY"], logfile.read_text())
            # Rebuilding with only the generated code must retain its launcher resources.
            rebuilt = subprocess.run([sys.executable, "-m", "gptapps", "build", "app.json", "--out", str(folder / "rebuilt")],
                                     cwd=standalone, env=env, capture_output=True, text=True)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertTrue((folder / "rebuilt" / "docker-start.sh").is_file())

    def test_help_and_invalid_options_require_no_credentials(self):
        for script in ("start.sh", "docker-start.sh", "run.sh"):
            result = subprocess.run(["bash", str(ROOT / script), "--help"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--port", result.stdout)
        for port in ("0", "65536", "not-a-port", "-1"):
            result = subprocess.run(["bash", str(ROOT / "start.sh"), "--port", port], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Port must", result.stderr)

    def test_local_launcher_opens_correct_url_and_cleans_up_server(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            mocks = folder / "mock commands"
            mocks.mkdir()
            for name, content in {"uname": '#!/bin/sh\necho Darwin\n',
                                  "open": '#!/bin/sh\nprintf "%s" "$1" > "$BROWSER_RECORD"\n'}.items():
                file = mocks / name
                file.write_text(content)
                file.chmod(0o755)
            port = unused_port()
            base = f"http://127.0.0.1:{port}"
            logfile, browser = folder / "server.log", folder / "opened-url.txt"
            env = {**os.environ, "GPTAPPS_PYTHON": sys.executable,
                   "PATH": str(mocks) + os.pathsep + os.environ.get("PATH", ""),
                   "BROWSER_RECORD": str(browser), "OPENAI_API_KEY": "test-only-not-a-real-key",
                   "OPENAI_MODEL": "test-model"}
            catalog, data = folder / "app catalog", folder / "history data"
            with logfile.open("w") as log:
                process = subprocess.Popen(["bash", str(ROOT / "start.sh"), "--port", str(port),
                    "--apps", str(catalog), "--data", str(data)], cwd=folder, env=env, stdout=log, stderr=log)
                try:
                    wait_ready(process, base, logfile)
                    deadline = time.monotonic() + 3
                    while not browser.exists() and time.monotonic() < deadline:
                        time.sleep(.05)
                    self.assertEqual(browser.read_text(), base)
                    raw = "  Preserve my exact instructions.\n"
                    with request(base, "/api/setup", {"field": "instructions", "message": raw}) as response:
                        self.assertEqual(json.load(response)["value"], raw)
                    with request(base, "/api/apps", {"name": "Synthetic app", "instructions": raw,
                                                      "knowledge_files": [], "actions": []}) as response:
                        saved = json.load(response)
                    self.assertTrue(saved["report"]["runtime_ready"])
                    with request(base, "/api/build?app=" + saved["id"]) as response:
                        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                            self.assertIn("LICENSE", archive.namelist())
                            self.assertTrue(json.loads(archive.read("compatibility.json"))["runtime_ready"])
                    req = urllib.request.Request(base + "/api/setup", data=b"{}", headers={
                        "Content-Type": "application/json", "Origin": "https://example.com"})
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        urllib.request.urlopen(req)
                    self.assertEqual(failure.exception.code, 403)
                    failure.exception.close()
                finally:
                    stop(process)
            self.assertTrue(list(catalog.glob("*.json")))
            self.assertTrue((data / "sessions.sqlite3").exists())
            with socket.socket() as sock:
                self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0, "Server survived launcher shutdown")
            self.assertNotIn(env["OPENAI_API_KEY"], logfile.read_text())

    @unittest.skipUnless(shutil.which("git"), "Git is needed to check publication ignore rules")
    def test_private_outputs_are_ignored_but_public_examples_are_not(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            subprocess.run(["git", "init", "--quiet", str(folder)], check=True)
            shutil.copyfile(ROOT / ".gitignore", folder / ".gitignore")
            private = [".env", ".env.local", "apps/private.json", "migrated/apps/private.json",
                       ".gptapps-data/sessions.sqlite3", "dist/app/app.json", "knowledge/guide.pdf", "app.zip"]
            public = [".env.example", "examples/minimal-export.json", "gptapps/setup.py", "LICENSE", "Dockerfile"]
            result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=folder,
                input="\n".join(private + public) + "\n", capture_output=True, text=True)
            self.assertEqual(set(result.stdout.splitlines()), set(private))


@unittest.skipUnless(os.environ.get("GPTAPPS_TEST_DOCKER") == "1", "Set GPTAPPS_TEST_DOCKER=1 for real Docker verification")
class DockerLauncherTests(unittest.TestCase):
    def test_generated_docker_launcher_runs_without_host_python_or_default_model(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            app = import_export(json.loads((ROOT / "examples" / "minimal-export.json").read_text()))[0]
            app["runtime"]["model"] = "test-model"
            standalone = folder / "generated app"
            build_app(app, standalone)
            port = unused_port()
            base = f"http://127.0.0.1:{port}"
            name = f"gptapps-generated-test-{port}"
            env = {key: value for key, value in os.environ.items() if key not in ("OPENAI_MODEL", "OPENAI_SETUP_MODEL")}
            env.update(OPENAI_API_KEY="test-only-not-a-real-key", GPTAPPS_PYTHON="/no-host-python-needed",
                       GPTAPPS_CONTAINER_NAME=name, GPTAPPS_DOCKER_IMAGE="gpt-generated-app:test")
            command = ["bash", str(standalone / "docker-start.sh"), "--port", str(port), "--no-browser"]
            for run in range(2):
                logfile = folder / f"generated-docker-{run}.log"
                with logfile.open("w") as log:
                    process = subprocess.Popen(command, cwd=folder, env=env, stdout=log, stderr=log)
                    try:
                        wait_ready(process, base, logfile, timeout=90, builder=False)
                        for asset, kind in (("chat.js", "text/javascript"), ("knowledge.js", "text/javascript"), ("chat.css", "text/css"),
                                            ("icons/plus.svg", "image/svg+xml"),
                                            ("vendor/marked.umd.js", "text/javascript"), ("vendor/purify.min.js", "text/javascript")):
                            with request(base, "/static/" + asset) as response:
                                self.assertIn(kind, response.headers["Content-Type"])
                                self.assertGreater(len(response.read()), 100)
                        if run == 0:
                            probe = "import pathlib, sqlite3, json; " \
                                "assert pathlib.Path('/app/gptapps/templates/start.sh').is_file(); " \
                                "assert not pathlib.Path('/app/app.json').exists(); " \
                                "db = sqlite3.connect('/data/sessions.sqlite3'); " \
                                "db.execute('INSERT INTO sessions VALUES (?,?,?,?)', " + repr((
                                    "fixture-session", app["id"], "fixture-fingerprint",
                                    json.dumps([{"role": "user", "content": "Persistent fixture"}])
                                )) + "); db.commit(); db.close()"
                            subprocess.run(["docker", "exec", name, "python", "-c", probe], check=True,
                                           capture_output=True, text=True)
                        else:
                            with request(base, "/api/sessions?app=" + app["id"]) as response:
                                self.assertEqual(json.load(response)[0]["title"], "Persistent fixture")
                    finally:
                        stop(process)
                self.assertNotIn(env["OPENAI_API_KEY"], logfile.read_text())
            self.assertTrue((standalone / ".gptapps-data" / "sessions.sqlite3").exists())

    def test_container_python_readiness_ports_build_and_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            port = unused_port()
            base = f"http://127.0.0.1:{port}"
            name = f"gptapps-test-{port}"
            env = {**os.environ, "OPENAI_API_KEY": "test-only-not-a-real-key", "OPENAI_MODEL": "test-model",
                   "GPTAPPS_CONTAINER_NAME": name}
            command = ["bash", str(ROOT / "docker-start.sh"), "--port", str(port), "--no-browser",
                       "--apps", str(folder / "apps"), "--data", str(folder / "data")]
            saved_id = None
            for run in range(2):
                logfile = folder / f"docker-{run}.log"
                with logfile.open("w") as log:
                    process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
                    try:
                        wait_ready(process, base, logfile, timeout=90)
                        if run == 0:
                            probe = subprocess.run(["docker", "exec", name, "python", "-c",
                                "import sys, pathlib; assert sys.version_info >= (3,11); "
                                "assert pathlib.Path('/app/gptapps/LICENSE').is_file(); "
                                "assert not pathlib.Path('/app/.env').exists(); "
                                "assert not pathlib.Path('/app/migrated').exists(); print(sys.version.split()[0])"],
                                capture_output=True, text=True, check=True)
                            self.assertTrue(probe.stdout.startswith("3.13."))
                            with request(base, "/api/apps", {"name": "Docker fixture", "instructions": "Help"}) as response:
                                saved_id = json.load(response)["id"]
                            with request(base, "/api/build?app=" + saved_id) as response:
                                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                                    self.assertIn("LICENSE", archive.namelist())
                        else:
                            with request(base, "/api/apps") as response:
                                self.assertIn(saved_id, [app["id"] for app in json.load(response)])
                    finally:
                        stop(process)
                self.assertNotIn(env["OPENAI_API_KEY"], logfile.read_text())
            self.assertTrue((folder / "apps" / (saved_id + ".json")).exists())
            self.assertTrue((folder / "data" / "sessions.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
