"""Local fake-provider server for browser verification only; no API calls."""
import base64
import json
from pathlib import Path
import sys
import time
import os
import uuid

sys.path.insert(0, os.environ.get('GPTAPPS_FIXTURE_RUNTIME_ROOT',str(Path(__file__).resolve().parents[1])))
from gptapps.runtime import Runtime
from gptapps.knowledge import KnowledgeManager
import gptapps.web as web


def input_text(content):
    if isinstance(content,str):return content
    return '\n'.join(part['text'] for part in content if part.get('type')=='input_text')


class FakeClient:
    def create(self, payload):
        capture=os.environ.get('GPTAPPS_CAPTURE_REQUESTS')
        if capture:Path(capture).write_text(json.dumps(payload))
        if payload.get("text", {}).get("format", {}).get("name") == "setup_reply":
            context = json.loads(input_text(payload["input"][0]["content"]))
            field, reply = context["field"], context["reply"]
            if reply == "slow-setup":
                time.sleep(1)
            status, value, message = "accept", reply, "Understood."
            if reply == "setup-fail":
                raise ValueError("Test setup provider failed; your draft has not changed")
            if field == "name":
                value = reply.removeprefix("Call it ")
            elif field == "description":
                value = "" if reply == "skip" else reply
            elif field == "starters":
                value = [] if "no " in reply.lower() or reply == "none" else reply.splitlines()
            elif field == "tools":
                value = ["web_search"]
            elif field == "model":
                value = None if "default" in reply.lower() else reply
            elif field == "knowledge_files":
                value = []
                if "not sure" in reply.lower():
                    status, value, message = "clarify", None, "Do you have any knowledge files, or should I leave the inventory empty?"
            elif field == "actions":
                value = []
                if reply == "not-json":
                    status, value, message = "clarify", None, "Provide Actions as a JSON array, or say that you have no Actions."
            elif field == "review":
                status, value, message = "create", None, "Creating your application."
            return {"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps({"status": status, "value": value, "message": message})}]}]}
        text = input_text(payload["input"][-1]["content"])
        if text == "fail":
            return {"status": "incomplete", "output": []}
        answer = "Test provider response: " + text
        content=payload['input'][-1]['content']
        if isinstance(content,list):
            filenames=[part['filename'] for part in content if part.get('type')=='input_file']
            if filenames:answer+='\n\n**Offline attachment check:** '+', '.join(filenames)+' received together with your message.'
        if text in ("markdown", "slow-markdown"):
            answer = """Here are some **basic Spanish greetings** for travel:

### Common greetings

- **Hola** = Hello
- **Buenos días** = Good morning
- **Buenas noches** = Good evening / Good night

### Asking how someone is

1. *¿Cómo estás?* — informal
2. *¿Cómo está?* — formal

| Spanish | English |
| --- | --- |
| Bien | Well |
| Muchas gracias | Thank you very much |

> Practise these phrases aloud.

Use `hola` in your first sentence.

```python
print("¡Hola!")
```

[Practice reference](https://example.com)
"""
        elif text == "gated-stream":
            answer = "First chunk. Final chunk."
        elif text == "long-answer":
            return {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                    "usage": {"output_tokens": payload["max_output_tokens"]},
                    "output": [{"type": "message", "role": "assistant", "status": "incomplete", "content": [
                        {"type": "output_text", "text": "### A detailed answer\n\nThis is the **saved first part** of a longer explanation.\n\n1. Start with a clear goal.\n2. Break the work into manageable steps.", "annotations": []}]}]}
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": answer,
             "annotations": [{"type": "url_citation", "title": "Example source", "url": "https://example.com"}]}]}]}

    def stream(self, payload):
        text = input_text(payload["input"][-1]["content"])
        if text == "stream-fail":
            yield {"type": "response.output_text.delta", "delta": "Partial response", "output_index": 0, "content_index": 0}
            raise ValueError("Test streaming response was incomplete; no conversation turn was saved")
        response = self.create(payload)
        if response["status"] != "completed" and response.get("incomplete_details", {}).get("reason") != "max_output_tokens":
            yield {"type": "response.incomplete", "response": response}
            return
        answer = response["output"][0]["content"][0]["text"]
        if text == "gated-stream":
            yield {"type": "response.output_text.delta", "delta": "First chunk. ", "output_index": 0, "content_index": 0}
            gate = os.environ.get("GPTAPPS_STREAM_GATE")
            deadline = time.monotonic() + 10
            while gate and not Path(gate).exists() and time.monotonic() < deadline:
                time.sleep(.02)
            yield {"type": "response.output_text.delta", "delta": "Final chunk.", "output_index": 0, "content_index": 0}
        else:
            for index in range(0, len(answer), 24):
                yield {"type": "response.output_text.delta", "delta": answer[index:index+24], "output_index": 0, "content_index": 0}
                time.sleep(.12 if text == "slow-markdown" else .025)
        yield {"type": "response." + response["status"], "response": response}


class FakeKnowledgeClient:
    def __init__(self, data_dir):
        self.uploads = {}
        self.data_dir = Path(data_dir)
        self.batches = {}

    def create_store(self):
        return {"id": "vs_fixture" + uuid.uuid4().hex}

    def upload_file(self, name, data):
        file_id = "file-fixture" + uuid.uuid4().hex
        self.uploads[file_id] = (name, data)
        return {"id": file_id}

    def create_batch(self, store, files):
        batch_id = "vsfb_fixture" + uuid.uuid4().hex
        self.batches[batch_id] = (store, files)
        return {"id": batch_id, "vector_store_id": store, "status": "in_progress",
                "file_counts": {"total": len(files), "in_progress": len(files), "completed": 0, "failed": 0, "cancelled": 0}}

    def get_batch(self, store, batch):
        if batch in self.batches:
            _, files = self.batches[batch]
            broken = any(self.uploads[file][0] == "broken.txt" for file in files)
        else:
            record = next(json.loads(path.read_text()) for path in (self.data_dir / 'knowledge-uploads').glob('*.json')
                          if json.loads(path.read_text()).get('batch_id') == batch)
            files = record['files']
            broken = any(file['name'] == 'broken.txt' for file in files)
        return {"id": batch, "vector_store_id": store, "status": "completed",
                "file_counts": {"total": len(files), "in_progress": 0, "completed": len(files) - int(broken),
                                "failed": int(broken), "cancelled": 0}}


web.Runtime = lambda data_dir, registry=None: Runtime(data_dir, FakeClient(), registry)
web.KnowledgeManager = lambda data_dir: KnowledgeManager(data_dir, FakeKnowledgeClient(data_dir))
web.serve(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), builder="--standalone" not in sys.argv)
