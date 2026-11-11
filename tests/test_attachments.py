import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gptapps.attachments import validate_attachments, input_content, MAX_TOTAL_BYTES
from gptapps.runtime import Runtime
from gptapps.setup import SetupInterpreter
from gptapps.build import build_app
from test_framework import app, FakeClient, response
from test_setup import interpretation


def attached(name='notes.txt', raw=b'The project code is AMBER-42.'):
    return {'name': name, 'data': base64.b64encode(raw).decode()}


class AttachmentTests(unittest.TestCase):
    def test_validates_bytes_and_builds_document_and_image_inputs(self):
        files=validate_attachments([attached(),attached('image.png',b'\x89PNG\r\n\x1a\nimage')])
        parts=input_content('Use these together',files)
        self.assertEqual(parts[0],{'type':'input_text','text':'Use these together'})
        self.assertEqual(parts[1]['filename'],'notes.txt')
        self.assertEqual(base64.b64decode(parts[1]['file_data'].split(',',1)[1]),b'The project code is AMBER-42.')
        self.assertEqual(parts[-1]['type'],'input_image')
        self.assertTrue(parts[-1]['image_url'].startswith('data:image/png;base64,'))

    def test_rejects_invalid_files_before_provider(self):
        invalid=[{},'bad',[attached('../private.txt')],[attached('a.exe')],[attached('a.txt',b'')],
                 [{'name':'a.txt','data':'!!!'}],[attached('a.png',b'not png')],[attached()]*6,
                 [attached('a\n.txt')],[{'name':'x.txt','data':'a'* (14*1024*1024)}]]
        for value in invalid:
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):validate_attachments(value)

    @patch.dict(os.environ,{'OPENAI_MODEL':'test-model'})
    def test_runtime_sends_combined_content_replays_files_and_hides_raw_data(self):
        client=FakeClient(response('First'),response('Follow up'))
        with tempfile.TemporaryDirectory() as directory:
            runtime=Runtime(directory,client)
            result=runtime.chat(app(),'Find the code',attachments=[attached()])
            original=copy.deepcopy(client.requests[0]['input'][0])
            self.assertEqual(original['content'][0]['text'],'Find the code')
            self.assertEqual(original['content'][1]['filename'],'notes.txt')
            runtime.chat(app(),'What was it?',result['session_id'])
            self.assertEqual(client.requests[1]['input'][0],original)
            visible=runtime.get_session(app()['id'],result['session_id'])
            self.assertEqual(visible['messages'][0]['attachments'][0]['name'],'notes.txt')
            self.assertNotIn(attached()['data'],json.dumps(visible))
            self.assertNotIn('file_data',json.dumps(visible))

    @patch.dict(os.environ,{'OPENAI_MODEL':'test-model'})
    def test_attachment_only_turn_and_failed_request_is_not_saved(self):
        client=FakeClient(response('File answer'),{'status':'failed'})
        with tempfile.TemporaryDirectory() as directory:
            runtime=Runtime(directory,client)
            result=runtime.chat(app(),'',attachments=[attached()])
            self.assertIn('notes.txt',runtime.list_sessions(app()['id'])[0]['title'])
            before=runtime.get_session(app()['id'],result['session_id'])
            with self.assertRaises(ValueError):runtime.chat(app(),'fail',result['session_id'],attachments=[attached()])
            self.assertEqual(runtime.get_session(app()['id'],result['session_id']),before)

    @patch.dict(os.environ,{'OPENAI_MODEL':'test-model','OPENAI_SETUP_MODEL':'setup-model'})
    def test_setup_passes_files_and_reply_to_interpretation_api(self):
        client=FakeClient(interpretation('An app based on the file'))
        SetupInterpreter(client).interpret('description','Use this document',attachments=[attached('brief.pdf',b'%PDF-1.4 document')])
        content=client.requests[0]['input'][0]['content']
        self.assertEqual(json.loads(content[0]['text'])['reply'],'Use this document')
        self.assertEqual(content[1]['filename'],'brief.pdf')

    def test_setup_preserves_text_instructions_and_action_schema(self):
        interpreter=SetupInterpreter(FakeClient())
        result=interpreter.interpret('instructions','Additional rule.',attachments=[attached('rules.md',b'  Follow this exactly.\n')])
        self.assertEqual(result['value'],'Additional rule.\n\n  Follow this exactly.\n')
        with self.assertRaisesRegex(ValueError,'text|UTF-8'):
            interpreter.interpret('instructions','Use this',attachments=[attached('rules.pdf',b'%PDF')])
        action=[{'name':'Lookup','auth_type':'none','schema':{'openapi':'3.1.0','info':{'title':'Lookup','version':'1.0'},'paths':{}}}]
        result=interpreter.interpret('actions','Use this',attachments=[attached('actions.json',json.dumps(action).encode())])
        self.assertEqual(result['value'],action)

    def test_cumulative_attachment_limit_rejects_before_provider(self):
        client=FakeClient(response('First'))
        with tempfile.TemporaryDirectory() as directory,patch('gptapps.runtime.MAX_ATTACHMENT_BYTES',40):
            runtime=Runtime(directory,client)
            result=runtime.chat(app(),'First',attachments=[attached()])
            with self.assertRaisesRegex(ValueError,'Conversation attachment limit'):
                runtime.chat(app(),'Second',result['session_id'],attachments=[attached()])
            self.assertEqual(len(client.requests),1)

    def test_export_includes_shared_file_intake_and_no_runtime_history(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'app';build_app(app(),target)
            self.assertTrue((target/'gptapps/attachments.py').is_file())
            self.assertTrue((target/'gptapps/attachments.js').is_file())
            self.assertIn('chat-files',(target/'gptapps/chat.html').read_text())
            self.assertFalse(list(target.rglob('*.sqlite3')))
