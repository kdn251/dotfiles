import importlib.util,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from test_newsboat_reconnect import reader,BINARY
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('global_search',SCRIPTS/'newsboat-global-search.py')
search=importlib.util.module_from_spec(spec);spec.loader.exec_module(search)

class GlobalSearchTests(unittest.TestCase):
    def test_real_config_parses_without_contacting_miniflux(self):
        import subprocess
        source=SCRIPTS.parents[1]/'newsboat/.newsboat/config'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            config=root/'config'
            config.write_text('include '+json.dumps(str(source))+'\nurls-source local\n')
            urls=root/'urls';urls.write_text('https://example.org/feed\n')
            result=subprocess.run([str(BINARY),'-C',str(config),'-u',str(urls),'-c',str(root/'cache'),'-x','print-unread'],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_saved_items_survive_cache_expiry_and_duplicate_links_merge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';state.mkdir();cache=root/'cache'
            db=sqlite3.connect(cache)
            db.executescript('CREATE TABLE rss_feed(rssurl,title);CREATE TABLE rss_item(id,guid,url,title,content,author,pubDate,unread,feedurl,deleted);INSERT INTO rss_feed VALUES("https://feed","Creator");')
            url='https://www.youtube.com/watch?v=abc123DEF45'
            db.execute('INSERT INTO rss_item VALUES(1,"1",?,"Excellent episode","some body", "",100,1,"https://feed",0)',(url,));db.commit();db.close()
            (state/'starred-items.json').write_text(json.dumps([dict(id=1,url='https://youtu.be/abc123DEF45',title='Excellent episode',feed={'title':'Creator'},content='some body'),dict(id=2,url='https://example.org/expired',title='Saved essay',feed={'title':'Writer'},content='Rareword buried in the article')]))
            for name in ['favorites','commentary']:
                db=sqlite3.connect(state/(name+'.db'));db.execute('CREATE TABLE items(url,title,source,content,saved)');db.execute('INSERT INTO items VALUES(?,?,?,?,?)',(url,'Excellent episode','Creator','some body',101));db.commit();db.close()
            (state/'downloads').mkdir();video=root/'video.mp4';video.write_bytes(b'test')
            (state/'downloads/job.json').write_text(json.dumps(dict(url=url,title='Excellent episode',creator='Creator',status='done',files=[str(video)])))
            before=cache.read_bytes()
            rows=search.search('CREATOR episode',cache,state)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['published'],100)  # Saving/downloading must not replace publication date.
            self.assertEqual(rows[0]['labels'],['New','Starred','Downloads','Favorites','Commentary'])
            self.assertEqual(search.search('rareword',cache,state)[0]['title'],'Saved essay')
            self.assertEqual(search.search('no match whatever',cache,state),[])
            self.assertEqual(cache.read_bytes(),before)
            video.unlink()
            self.assertNotIn('Downloads',search.search('episode',cache,state)[0]['labels'])

    def test_native_rows_labels_original_titles_search_and_open(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source'
            binding=next(line for line in (SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text().splitlines() if line.startswith('bind / feedlist '))
            source.write_text('bind-key j down\nbind-key k up\ndatetime-format "%Y-%m-%d"\n'+binding+'\n')
            rows=[dict(url='https://example.org/one',title='Excellent episode',source='Creator',content='Readable body',saved=1735732800,published=1704110400,guid='1',labels=['Starred','Downloads'])]
            _,config=search.prepare(root,'Excellent',rows,source)
            cfg=config.read_text()+'run-on-startup open\n'
            with reader(root,cfg,(root/'urls').read_text(),{'NEWSBOAT_SEARCH_LABELS':str(root/'labels')}) as (_,screen,send,wait):
                wait(lambda s:'Excellent episode' in s and 'Starred, Downloads' in s and 'Creator' in s)
                self.assertIn('1 results',screen.display[0])
                self.assertIn('2024-01-01',screen.display[1])
                self.assertNotIn('2025-01-01',screen.display[1])
                send('\n');wait(lambda s:'Readable body' in s)
                self.assertIn("Article 'Excellent episode'",screen.display[0])
                send('q');wait(lambda s:'1 results' in screen.display[0])
                send('/Excellent\n');wait(lambda s:'Filter search results' in screen.display[0])

    def test_deleted_downloads_do_not_create_spinners(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';(state/'downloads').mkdir(parents=True)
            snapshot=[]
            for i,status in enumerate(['deleted','unexpected','done','failed','downloading']):
                url=f'https://example.org/{i}'
                snapshot.append(dict(id=i,url=url,title='Saved '+status,feed={'title':'Source'}))
                file=root/(str(i)+'.mp4');file.write_bytes(b'test')
                (state/'downloads'/f'{i}.json').write_text(json.dumps(dict(url=url,title='Saved '+status,status=status,files=[str(file)])))
            (state/'starred-items.json').write_text(json.dumps(snapshot))
            rows=search.search('Saved',root/'missing-cache',state)
            by_title={row['title']:row for row in rows}
            for status in ['deleted','unexpected']:
                self.assertNotIn('Downloads',by_title['Saved '+status]['labels'])
                self.assertNotIn('download_badge',by_title['Saved '+status])
            self.assertEqual(by_title['Saved done']['download_badge'],'📥')
            self.assertEqual(by_title['Saved failed']['download_badge'],'✕')
            self.assertEqual(by_title['Saved downloading']['download_badge'],'…')
            view=root/'view';view.mkdir();search.ResultBadges(rows,state,view,{})
            badges=(view/'downloads').read_text()
            self.assertNotIn('https://example.org/0',badges)
            self.assertNotIn('https://example.org/1',badges)
            self.assertIn('https://example.org/2\t📥',badges)

    def test_results_are_newest_first_in_native_view(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_text('datetime-format "%Y-%m-%d"\n')
            rows=[dict(url='https://example.org/'+name,title=name,source='Creator',content='',saved=date,published=date,guid=name,labels=['Feeds'])
                  for name,date in [('Older result',1704110400),('Newest result',1735732800),('Middle result',1719835200)]]
            _,config=search.prepare(root,'result',rows,source)
            with reader(root,config.read_text()+'run-on-startup open\n',(root/'urls').read_text()) as (_,screen,send,wait):
                wait(lambda s:all(row['title'] in s for row in rows))
                self.assertIn('Newest result',screen.display[1])
                self.assertIn('Middle result',screen.display[2])
                self.assertIn('Older result',screen.display[3])

    def test_badge_projection_aliases_fallback_and_removal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';state.mkdir();view=root/'view';view.mkdir()
            canonical='https://www.youtube.com/watch?v=abc123DEF45'
            alias='https://youtu.be/abc123DEF45'
            other='https://example.org/other'
            (state/'starred-urls.txt').write_text(alias+'\n'+other+'\n')
            (state/'download-status.tsv').write_text(alias+'\t📥\n')
            rows=[dict(url=canonical,labels=['Starred','Downloads','Commentary','Favorites'])]
            env={};projection=search.ResultBadges(rows,state,view,env)
            self.assertIn(canonical,(view/'stars').read_text())
            self.assertIn(other,(view/'stars').read_text())
            self.assertIn(canonical+'\t📥',(view/'downloads').read_text())
            self.assertIn(canonical,(view/'stars.commentary').read_text())
            self.assertIn(canonical,(view/'stars.favorites').read_text())
            (state/'starred-urls.txt').write_text(other+'\n')
            (state/'starred-urls.txt.commentary').write_text('')
            (state/'starred-urls.txt.favorites').write_text('')
            (state/'download-status.tsv').write_text(alias+'\t50%\n')
            projection.refresh()
            self.assertNotIn(canonical,(view/'stars').read_text())
            self.assertNotIn(canonical,(view/'stars.commentary').read_text())
            self.assertNotIn(canonical,(view/'stars.favorites').read_text())
            self.assertIn(canonical+'\t50%',(view/'downloads').read_text())

    def test_result_badges_update_live(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_text('datetime-format "%Y-%m-%d"\n')
            url='https://example.org/one'
            rows=[dict(url=url,title='Marked result',source='Creator',content='Body',saved=1704110400,guid='1',labels=['Starred','Downloads','Commentary','Favorites'])]
            _,config=search.prepare(root,'Marked',rows,source)
            stars=root/'stars';stars.write_text(url+'\n')
            (root/'stars.commentary').write_text(url+'\n');(root/'stars.favorites').write_text(url+'\n')
            downloads=root/'downloads';downloads.write_text(url+'\t📥\n')
            env={'NEWSBOAT_STARRED_STATUS':str(stars),'NEWSBOAT_DOWNLOAD_STATUS':str(downloads),'NEWSBOAT_SEARCH_LABELS':str(root/'labels')}
            with reader(root,config.read_text()+'run-on-startup open\n',(root/'urls').read_text(),env) as (_,screen,send,wait):
                wait(lambda s:'Marked result' in s)
                for icon in ['󰓎','📥','📣','']:self.assertIn(icon,screen.display[1])
                (root/'stars.commentary').write_text('')
                wait(lambda s:'📣' not in screen.display[1])

    def test_home_request_and_local_feed_search(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);request=root/'request';rss=root/'feed.xml'
            rss.write_text('<rss version="2.0"><channel><title>Creator</title><link>https://example.org</link><description>test</description><item><title>Needle</title><guid>1</guid><link>https://example.org/1</link></item></channel></rss>')
            with reader(root,'show-read-feeds yes\nshow-read-articles yes\n',rss.as_uri()+'\n',{'NEWSBOAT_GLOBAL_SEARCH_REQUEST':str(request)}) as (_,screen,send,wait):
                wait(lambda s:'Creator' in s)
                send('/');wait(lambda s:'Search everything:' in s)
                send('needle "quotes"\n');wait(lambda s:request.exists())
                self.assertEqual(request.read_text(),'needle "quotes"');request.unlink()
                send('\n');wait(lambda s:'Needle' in s)
                send('/Needle\n');wait(lambda s:'Search results' in screen.display[0])
                self.assertFalse(request.exists())

    def test_home_wrapper_end_to_end(self):
        import fcntl,pty,select,shutil,signal,struct,subprocess,sys,termios,time,pyte
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfgdir=root/'.newsboat';cfgdir.mkdir();state=root/'state/newsboat';state.mkdir(parents=True)
            bindir=root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True);(bindir/'newsboat').symlink_to(BINARY)
            for filename in ['newsboat-session.py','newsboat-global-search.py']:shutil.copy(SCRIPTS/filename,root/filename)
            rss=root/'feed.xml';rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description><item><title>Normal</title><guid>1</guid><link>https://example.org/1</link></item></channel></rss>')
            (cfgdir/'urls').write_text(rss.as_uri()+'\n')
            (cfgdir/'config').write_text('feedlist-title-format "HOMESCREEN"\nshow-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\n')
            (state/'starred-items.json').write_text(json.dumps([dict(id=3,url='https://example.org/archived',title='Archived special essay',content='Archived body',feed={'title':'Writer'})]))
            subprocess.run([str(BINARY),'-C',str(cfgdir/'config'),'-u',str(cfgdir/'urls'),'-c',str(cfgdir/'cache.db'),'-x','reload'],capture_output=True,check=True)
            env=dict(os.environ,HOME=d,TERM='xterm-256color',XDG_STATE_HOME=str(root/'state'))
            for key in list(env):
                if key.startswith('NEWSBOAT_'):env.pop(key)
            pid,fd=pty.fork()
            if pid==0:os.execve(sys.executable,[sys.executable,str(root/'newsboat-session.py')],env)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,140,0,0));screen=pyte.Screen(140,24);stream=pyte.ByteStream(screen)
            def wait(text):
                until=time.monotonic()+7
                while time.monotonic()<until:
                    if select.select([fd],[],[],.03)[0]:
                        try:stream.feed(os.read(fd,65536))
                        except OSError:break
                    if text in '\n'.join(screen.display):return
                self.fail('\n'.join(screen.display))
            try:
                wait('HOMESCREEN');os.write(fd,b'/special\n');wait('Archived special essay')
                self.assertIn('Starred','\n'.join(screen.display));self.assertIn('Writer','\n'.join(screen.display))
                self.assertIn('󰓎',screen.display[1])
                os.write(fd,b'\n');wait('Archived body')
                os.write(fd,b'q');wait('1 results')
                os.write(fd,b'q');wait('HOMESCREEN')
                os.write(fd,b'/nothingmatches\n');wait('No matches')
                os.write(fd,b'q');wait('HOMESCREEN')
            finally:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
