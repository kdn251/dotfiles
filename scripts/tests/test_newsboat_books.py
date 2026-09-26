"""Local book inventory, reader dispatch and native list integration."""
import importlib.util,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_newsboat_reconnect import reader,pyte,BINARY
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('books',SCRIPTS/'newsboat-books.py')
books=importlib.util.module_from_spec(spec);spec.loader.exec_module(books)

class BooksTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.library=self.root/'Books';self.library.mkdir()
        self.patches=[patch.object(books,'DIRECTORY',self.library),patch.object(books,'STATE',self.root/'state'),patch.object(books.media,'STATE',self.root/'downloads'),patch.object(books.media,'URLS',self.root/'urls')]
        for p in self.patches:p.start()
        (self.root/'urls').write_text('"query:🎬 VODs:link = \\"empty\\""\n"query: Favorites:link = \\"empty\\""\n"query:🌎 All:link = \\"empty\\""\n')
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_scan_formats_subfolders_dedup_and_order(self):
        (self.library/'sub').mkdir()
        (self.library/'sub/Z book.EPUB').write_text('book')
        (self.library/'A book.pdf').write_text('book')
        (self.library/'ignore.txt').write_text('no')
        (self.library/'alias.pdf').symlink_to(self.library/'A book.pdf')
        (self.root/'outside.pdf').write_text('outside')
        (self.library/'outside.pdf').symlink_to(self.root/'outside.pdf')
        rows=books.rebuild()
        self.assertEqual(len(rows),2)
        self.assertEqual({r['kind'] for r in rows},{'PDF','EPUB'})
        lines=(self.root/'urls').read_text().splitlines()
        self.assertIn('VODs',lines[0]);self.assertIn('Books',lines[1]);self.assertIn('Favorites',lines[2])
        self.assertEqual((self.root/'state/starred-urls.txt.books.count').read_text(),'2\n')
        books.rebuild();self.assertEqual((self.root/'urls').read_text().splitlines(),lines)
    def test_open_is_detached_and_restricts_paths(self):
        p=self.library/'A book.pdf';p.write_text('book')
        with patch.object(books.subprocess,'Popen') as opened:
            books.open_book(p.as_uri())
            self.assertEqual(opened.call_args.args[0],['zathura',str(p)])
            self.assertTrue(opened.call_args.kwargs['start_new_session'])
            with self.assertRaises(ValueError):books.open_book((self.root/'outside.pdf').as_uri())
            with self.assertRaises(ValueError):books.open_book('https://example.org/book.pdf')
    @unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
    def test_empty_books_visible_in_real_home_filter(self):
        home_filter=next(line for line in (SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text().splitlines()
                         if line.startswith('run-on-startup set-filter'))
        config='show-read-feeds yes\nconfirm-exit no\nfeedlist-format "%t | %v %k"\n'+home_filter+'\n'
        books.rebuild()
        with reader(self.root,config,(self.root/'urls').read_text(),
                    dict(NEWSBOAT_STARRED_STATUS=str(self.root/'state/starred-urls.txt'))) as (_,screen,send,wait):
            wait(lambda s:'Books | 0 items' in s)
            self.assertIn('VODs','\n'.join(screen.display))

    @unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
    def test_native_book_list_and_search(self):
        (self.library/'A book.pdf').write_text('book')
        (self.library/'Z book.epub').write_text('book')
        view=self.root/'view';view.mkdir()
        books.prepare_view(view,books.entries())
        config=(view/'config').read_text()
        opener=view/'open.sh'
        opener.write_text('#!/bin/sh\nprintf "%s" "$1" > '+str(view/'opened')+'\n')
        opener.chmod(0o755)
        config += 'browser "'+str(opener)+' %u"\n'
        with reader(view,config,(view/'urls').read_text(),dict(NEWSBOAT_DOWNLOAD_STATUS=str(view/'status'))) as (_,screen,send,wait):
            wait(lambda s:'Books' in s);send('\n')
            wait(lambda s:'A book' in s and 'Z book' in s and 'PDF' in s and 'EPUB' in s)
            self.assertEqual(screen.display[0].strip(),'📚 Books')
            send('\n');wait(lambda s:(view/'opened').exists())
            self.assertEqual((view/'opened').read_text(),(self.library/'A book.pdf').as_uri())
            self.assertIn('Z book','\n'.join(screen.display))
            (view/'status.read').write_text((self.library/'Z book.epub').as_uri()+'\t45%\n')
            wait(lambda s:'45%' in s and 'Z book' in screen.display[1])
            self.assertIn('A book',screen.display[screen.cursor.y])
            send(':1\n');wait(lambda s:'Z book' in screen.display[screen.cursor.y])
            send(':2\n');wait(lambda s:'A book' in screen.display[screen.cursor.y])
            (view/'status.read').write_text((self.library/'Z book.epub').as_uri()+'\t100%\n')
            wait(lambda s:'100%' in s and 'A book' in screen.display[1])
            send('/Z book\n');wait(lambda s:'Search' in screen.display[0] and 'Z book' in s)
            self.assertNotIn('A book','\n'.join(screen.display))

class BookProgressTests(unittest.TestCase):
    def test_foliate_encoded_identity_and_resume_state_untouched(self):
        from urllib.parse import quote
        progress=books.progress
        with tempfile.TemporaryDirectory() as d, patch.object(progress,'DATA',Path(d)):
            root=Path(d)/'com.github.johnfactotum.Foliate';(root/'library').mkdir(parents=True)
            book=Path(d)/'book.epub';book.touch()
            ident='urn:isbn:123/test'
            (root/'library/uri-store.json').write_text(json.dumps({'uris':[[ident,book.as_uri()]]}))
            location=root/(quote(ident,safe="~()*!.'-")+'.json')
            location.write_text(json.dumps(dict(progress=[45,100],lastLocation='epubcfi(/6/2)')))
            before=location.read_bytes()
            self.assertEqual(progress.foliate_positions()[book.as_uri()],.45)
            self.assertEqual(location.read_bytes(),before)
    def test_progress_is_persistent_and_does_not_decrease_on_review(self):
        progress=books.progress
        with tempfile.TemporaryDirectory() as d, patch.object(progress,'STATE',Path(d)), patch.object(progress,'pdf_positions',return_value={}),patch.object(progress,'foliate_positions') as positions:
            rows=[dict(url='file:///Books/book.epub')]
            positions.return_value={rows[0]['url']:.6}
            progress.publish(rows)
            positions.return_value={rows[0]['url']:.2}
            progress.publish(rows)
            self.assertIn('60%',(Path(d)/'status.tsv.read').read_text())
            progress.publish(rows,refresh=False)
            self.assertIn('60%',(Path(d)/'status.tsv.read').read_text())
