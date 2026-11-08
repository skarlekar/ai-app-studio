"""Optional browser test: requires Playwright and Chromium; provider is mocked."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import zipfile

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gptapps.spec import import_export

ROOT = Path(__file__).resolve().parents[1]
PORT = 8877


def main():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        apps = folder / "apps"
        apps.mkdir()
        for app in import_export(json.loads((ROOT / "examples" / "minimal-export.json").read_text())):
            (apps / (app["id"] + ".json")).write_text(json.dumps(app))
        app_count = len(list(apps.glob("*.json")))
        env = {**os.environ, "OPENAI_MODEL": "test-model"}
        server = subprocess.Popen([sys.executable, str(ROOT / "tests" / "serve_fixture.py"),
                                   str(apps), str(folder / "data"), str(PORT)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        base = f"http://127.0.0.1:{PORT}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/api/apps", timeout=1).close()
                    break
                except (urllib.error.URLError, TimeoutError):
                    if server.poll() is not None:
                        raise RuntimeError(server.stderr.read().decode())
                    time.sleep(.1)
            else:
                raise RuntimeError("Local test server did not start")
            with sync_playwright() as p:
                executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
                browser = p.chromium.launch(**({"executable_path": executable} if executable else {}), headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"])
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                expect(page.locator("#apps option")).to_have_count(app_count)
                payload = "<img src=x onerror=alert('unsafe')> <script>alert('unsafe')</script> [unsafe](javascript:alert(1))"
                page.locator("#input").fill(payload)
                page.locator("#send").click()
                expect(page.locator(".message.assistant .body")).to_contain_text("Test provider response:")
                assert page.locator(".message img").count() == 0
                assert page.locator(".message.assistant script,.message.assistant iframe,.message.assistant svg").count() == 0
                assert page.locator(".message.assistant a[href^='javascript:']").count() == 0
                expect(page.locator(".sources a")).to_have_attribute("href", "https://example.com")
                expect(page.locator("#sessions button")).to_have_count(1)
                page.reload()
                page.locator("#sessions button").click()
                expect(page.locator(".message.user .body")).to_have_text(payload)
                page.locator("#input").fill("fail")
                page.locator("#send").click()
                expect(page.locator("#error")).to_contain_text("incomplete")
                expect(page.locator("#input")).to_have_value("fail")
                expect(page.locator(".message.user")).to_have_count(1)
                page.locator("#new").click()
                page.locator("#input").fill("slow-markdown")
                page.locator("#send").click()
                expect(page.locator(".message.assistant.streaming .body strong").first).to_have_text("basic Spanish greetings")
                expect(page.locator("#send")).to_be_disabled()
                expect(page.locator("#status")).to_have_text("Ready")
                expect(page.locator(".message.assistant .body h3").first).to_have_text("Common greetings")
                expect(page.locator(".message.assistant .body table")).to_have_count(1)
                expect(page.locator(".message.assistant .body pre code")).to_contain_text('print("¡Hola!")')
                expect(page.locator(".message.assistant .body a")).to_have_attribute("rel", "noopener noreferrer")
                page.reload()
                page.locator("#sessions button").last.click()
                expect(page.locator(".message.assistant .body table")).to_have_count(1)
                page.locator("#new").click()
                page.locator("#input").fill("long-answer")
                page.locator("#send").click()
                expect(page.locator(".response-notice")).to_contain_text("partial answer is saved")
                expect(page.get_by_role("button", name="Continue response", exact=True)).to_be_enabled()
                page.reload()
                page.get_by_role("button", name="long-answer", exact=True).click()
                expect(page.locator(".response-notice")).to_be_visible()
                page.locator("#input").fill("An unsent draft")
                page.get_by_role("button", name="Continue response", exact=True).click()
                expect(page.locator("#input")).to_have_value("An unsent draft")
                expect(page.locator("#error")).to_contain_text("Send or clear your draft")
                page.locator("#input").fill("")
                page.get_by_role("button", name="Continue response", exact=True).click()
                expect(page.locator(".message.assistant")).to_have_count(2)
                expect(page.locator("#status")).to_have_text("Ready")
                expect(page.get_by_role("button", name="Continue response", exact=True)).to_be_disabled()
                page.locator("#create").click()
                expect(page.locator("#messages")).to_contain_text("What is the name")
                preview = ROOT / "preview"
                preview.mkdir(exist_ok=True)
                page.screenshot(path=str(preview / "setup.png"), full_page=True)
                values = ["Call it Reusable Study Assistant", "Helps students learn concepts.",
                          "  Teach carefully.\nAsk one question at a time.\n", "Explain this concept\nQuiz me",
                          "Enable web search but no images or code", "Use the default model", "I'm not sure about files"]
                for value in values:
                    page.locator("#input").fill(value)
                    page.locator("#send").click()
                expect(page.locator("#messages")).to_contain_text("should I leave the inventory empty")
                page.locator("#input").fill("No knowledge files needed")
                page.locator("#send").click()
                page.locator("#input").fill("not-json")
                page.locator("#send").click()
                expect(page.locator("#messages")).to_contain_text("JSON array")
                page.locator("#input").fill("No actions required.")
                page.locator("#send").click()
                expect(page.locator("#messages")).to_contain_text("Review your application")
                page.locator("#input").fill("Looks good, go ahead")
                page.locator("#send").click()
                expect(page.locator("#messages")).to_contain_text("Application created")
                expect(page.locator("#apps option")).to_have_count(app_count + 1)
                with page.expect_download() as download:
                    page.locator("#download").click()
                data = Path(download.value.path()).read_bytes()
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert "run.py" in archive.namelist()
                    assert "gptapps/chat.html" in archive.namelist()
                    spec = json.loads(archive.read("app.json"))
                    assert spec["name"] == "Reusable Study Assistant"
                    assert spec["instructions"] == values[2]
                    assert spec["runtime"]["hosted_tools"] == ["web_search"]
                    assert spec["requirements"]["knowledge_files"] == []
                    assert spec["requirements"]["actions"] == []
                    assert json.loads(archive.read("compatibility.json"))["runtime_ready"]
                    assert not any("sessions.sqlite" in name or name.endswith(".env") for name in archive.namelist())
                page.locator("#input").fill("markdown")
                page.locator("#send").click()
                expect(page.locator(".message.assistant")).to_have_count(1)
                expect(page.locator("#status")).to_have_text("Ready")
                page.screenshot(path=str(preview / "chat.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
                page.screenshot(path=str(preview / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            # Protect local mutation from cross-origin browser requests.
            request = urllib.request.Request(base + "/api/apps", data=b"{}", method="POST",
                headers={"Content-Type": "application/json", "Origin": "https://example.com"})
            try:
                urllib.request.urlopen(request)
                raise AssertionError("Cross-origin mutation was accepted")
            except urllib.error.HTTPError as error:
                assert error.code == 403
            print("PASS: app catalog, live streaming, Markdown, safe HTML/links, persistence, sources, error recovery, conversational setup, ZIP download, mobile layout and origin checks")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
