import json
from pathlib import Path
import tempfile
import unittest
from gptapps.version import VERSION, build_info
from gptapps.build import build_app
from test_framework import app

class PublicBuildInfoTests(unittest.TestCase):
    def test_source_build_is_stable_and_exports_get_unique_numbers(self):
        self.assertEqual(build_info(),build_info())
        self.assertEqual(build_info()['version'],VERSION)
        self.assertTrue(build_info()['build'].isdigit())
        with tempfile.TemporaryDirectory() as folder:
            one=Path(folder)/'one';two=Path(folder)/'two'
            build_app(app(),one);build_app(app(),two)
            first=json.loads((one/'gptapps/build-info.json').read_text())
            second=json.loads((two/'gptapps/build-info.json').read_text())
            self.assertNotEqual(first['build'],second['build'])
            self.assertEqual(first['version'],VERSION)
            self.assertIn('release-info',(one/'gptapps/chat.html').read_text())
