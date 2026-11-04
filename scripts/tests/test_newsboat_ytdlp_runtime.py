import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('runtime',Path(__file__).resolve().parents[1]/'scripts/newsboat-yt-dlp.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)

class RuntimeTests(unittest.TestCase):
    def test_cache_preserves_code_and_rebuilds_after_update(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'yt-dlp';cache=root/'cache'
            def write(code):
                with zipfile.ZipFile(source,'w') as archive:
                    archive.writestr('__main__.py',code)
                    archive.writestr('yt_dlp/__init__.py','')
            write('print("version one")')
            first=runtime.runtime(source,cache)
            self.assertEqual(first.read_text(),'print("version one")')
            self.assertEqual(runtime.runtime(source,cache),first)
            write('print("version two updated")')
            second=runtime.runtime(source,cache)
            self.assertNotEqual(first,second)
            self.assertEqual(second.read_text(),'print("version two updated")')

    def test_nonzip_package_is_used_directly(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'yt-dlp';source.write_text('#!/usr/bin/python\n')
            self.assertEqual(runtime.runtime(source,Path(d)/'cache'),source)

    def test_invalid_archive_cannot_escape_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'yt-dlp'
            with zipfile.ZipFile(source,'w') as archive:
                archive.writestr('__main__.py','')
                archive.writestr('yt_dlp/__init__.py','')
                archive.writestr('../../escape','bad')
            with self.assertRaises(ValueError):runtime.runtime(source,root/'cache')
            self.assertFalse((root/'escape').exists())
