"""FIFO persistence, alias dedup, live UI membership and autoplay priority."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_queue as queue
import newsboat_autoplay as autoplay
import newsboat_media as media
from test_newsboat_reconnect import reader

URLS=['https://www.youtube.com/watch?v='+str(i)*11 for i in range(4)]

@contextmanager
def isolated():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);urls=root/'urls';urls.write_text('"query:📬 New:unread = \\"yes\\""\n')
        with patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_URLS_FILE=str(urls),NEWSBOAT_CACHE=str(root/'missing'),NEWSBOAT_PLAYLIST_CONTEXT=''),patch.object(media,'STATE',root/'newsboat'),patch.object(queue,'metadata',side_effect=lambda url:dict(url=url,title='Video'+str(URLS.index(url)),source='Creator')):
            yield root,urls

class QueueTests(unittest.TestCase):
    def test_fifo_dedup_membership_and_success_only_consumption(self):
        with isolated() as (root,urls):
            queue.change('add',URLS[2]);queue.change('add',URLS[1]);queue.change('add','https://youtu.be/'+'2'*11)
            self.assertEqual([r['url'] for r in queue.entries()],[URLS[2],URLS[1]])
            self.assertTrue(urls.read_text().startswith('"query:📺 Queue:'))
            token=queue.entries()[0]['queue_token']
            queue.change('started',URLS[2],'wrong-token')
            self.assertEqual(len(queue.entries()),2)
            queue.change('started',URLS[2],token)
            self.assertEqual([r['url'] for r in queue.entries()],[URLS[1]])
            queue.change('remove',URLS[1]);self.assertNotIn('Queue',urls.read_text())
            queue.change('add',URLS[2]);queue.change('started',URLS[2],token)
            self.assertEqual(len(queue.entries()),1,'stale playback callback must not remove a requeued video')

    def test_autoplay_queue_overrides_playlist_and_random_without_popping(self):
        with isolated() as (root,_):
            manifest=root/'playlist.json';manifest.write_text(json.dumps(dict(rows=[dict(url=u,title=u) for u in URLS[:2]])))
            queue.change('add',URLS[2]);queue.change('add',URLS[3])
            with patch.dict(os.environ,NEWSBOAT_PLAYLIST_CONTEXT=str(manifest)),patch.object(autoplay,'download_candidates') as random:
                self.assertEqual(autoplay.plan(URLS[0])['next']['url'],URLS[2])
                self.assertEqual(autoplay.plan(URLS[2])['next']['url'],URLS[3])
                self.assertEqual(len(queue.entries()),2)
                media.atomic_write(autoplay.preference(),'{"enabled":false}')
                self.assertFalse(autoplay.plan(URLS[0])['enabled'])
                queue.change('remove',URLS[2]);queue.change('remove',URLS[3])
                self.assertEqual(autoplay.plan(URLS[0])['next']['url'],URLS[1])
                random.assert_not_called()

    def test_queue_view_live_removal_fifo_and_sequential_numbers(self):
        with isolated() as (root,_):
            for i in (2,0,1):queue.change('add',URLS[i])
            view=root/'view';view.mkdir();_,config=queue.prepare_view(view)
            # Use a minimal native config but the actual queue feed and status.
            text='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order title-desc\narticlelist-format "%4i %p %t"\nrun-on-startup open\n'
            status=queue.state()/'viewing-queue.tsv'
            with reader(view,text,(view/'history.xml').as_uri()+'\n',dict(NEWSBOAT_QUEUE_STATUS=str(status),NEWSBOAT_QUEUE_VIEW='1')) as (_,screen,send,wait):
                def rows():return [row for row in screen.display[1:-3] if 'Video' in row]
                wait(lambda _:len(rows())==3 and 'Video2' in rows()[0] and 'Video0' in rows()[1])
                self.assertEqual([row.strip()[0] for row in rows()],list('123'))
                queue.change('remove',URLS[2])
                wait(lambda _:len(rows())==2 and 'Video0' in rows()[0])
                queue.change('started',URLS[0],queue.entries()[0]['queue_token'])
                wait(lambda _:len(rows())==1 and 'Video1' in rows()[0])
                queue.change('remove',URLS[1]);wait(lambda _:not rows())

    def test_home_row_appears_above_new_counts_and_disappears(self):
        with isolated() as (root,urls):
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description></channel></rss>')
            original=urls.read_text()+feed.as_uri()+'\n'
            text='show-read-feeds yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format "%t %v %k"\n'
            home_config=queue.SCRIPTS.parents[1]/'newsboat/.newsboat/config'
            text+=next(line for line in home_config.read_text().splitlines() if line.startswith('run-on-startup set-filter '))+'\n'
            env=dict(NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_STARRED_STATUS=str(queue.state()/'starred-urls.txt'),NEWSBOAT_LIVE_QUERIES=str(urls))
            with reader(root,text,original,env) as (_,screen,send,wait):
                wait(lambda s:'New' in s)
                queue.change('add',URLS[0]);wait(lambda s:'Queue 1 items' in s)
                self.assertIn('Queue',screen.display[1]);self.assertIn('New',screen.display[2])
                queue.change('add',URLS[1]);wait(lambda s:'Queue 2 items' in s)
                queue.change('remove',URLS[0]);queue.change('remove',URLS[1]);wait(lambda _:not any('Queue' in row for row in screen.display[1:-3]))

    def run_real_mpv(self, natural_end=False):
        import shutil,subprocess,time,wave
        with isolated() as (root,urls):
            scripts=root/'scripts';scripts.mkdir();ipc_flag=root/'go';calls=root/'calls';ready=root/'ready'
            for name in ('newsboat_autoplay.py','newsboat_queue.py'):
                (scripts/name).symlink_to(queue.SCRIPTS/name)
            shutil.copyfile(queue.SCRIPTS/'newsboat-playlist-playback.lua',scripts/'newsboat-playlist-playback.lua')
            (scripts/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            (scripts/'newsboat-play-video.py').write_text('import sys\nfrom pathlib import Path\nPath('+repr(str(calls))+').write_text(sys.argv[1])\n')
            source=root/'audio.wav'
            with wave.open(str(source),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*(8000 if natural_end else 160000))
            driver=root/'driver.lua'
            driver.write_text('mp.register_event("file-loaded",function() local f=io.open('+json.dumps(str(ready))+',"w");f:write("ready");f:close() end)\n'+
                'mp.add_periodic_timer(.1,function() local f=io.open('+json.dumps(str(ipc_flag))+',"r");if f then f:close();os.remove('+json.dumps(str(ipc_flag))+');mp.commandv("keypress",">") end end)\n'+
                'mp.add_timeout(8,function() mp.commandv("quit") end)\n')
            manifest=root/'playlist.json';manifest.write_text(json.dumps(dict(rows=[dict(url=u,title=u) for u in URLS[:2]])))
            queue.change('add',URLS[0])
            if natural_end:queue.change('add',URLS[3])
            env=dict(os.environ,NEWSBOAT_MEDIA_URL=URLS[0],NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_PLAYLIST_CONTEXT=str(manifest))
            process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause='+('no' if natural_end else 'yes'),'--script='+str(scripts/'newsboat-playlist-playback.lua'),'--script='+str(driver),str(source)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+4
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(ready.exists())
                deadline=time.monotonic()+2
                while any(row['url']==URLS[0] for row in queue.entries()) and time.monotonic()<deadline:time.sleep(.05)
                self.assertFalse(any(row['url']==URLS[0] for row in queue.entries()),'successful playback consumes its entry')
                if not natural_end:
                    queue.change('add',URLS[2]);queue.change('add',URLS[3])
                    time.sleep(.8)
                    queue.change('remove',URLS[2])
                    time.sleep(.8)
                    ipc_flag.touch()
                deadline=time.monotonic()+(7 if natural_end else 3)
                while not calls.exists() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(calls.exists())
                self.assertEqual(calls.read_text(),URLS[3],'edited queue takes priority over playlist episode 1')
                self.assertEqual(len(queue.entries()),1,'launch request alone must not consume the queued video')
            finally:
                process.terminate();process.communicate(timeout=3)

    def test_real_mpv_notices_queue_edits_during_playback(self):self.run_real_mpv()
    def test_real_mpv_autoplays_queue_at_eof(self):self.run_real_mpv(natural_end=True)

    def test_visual_enqueue_keeps_selection_order(self):
        with isolated() as (root,_):
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Videos</title><link>https://example.org</link><description>Test</description>'+''.join(f'<item><title>Video{i}</title><link>{url}</link><guid>{i}</guid></item>' for i,url in enumerate(URLS))+'</channel></rss>')
            config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order title-asc\nrun-on-startup open\nbind-key j down\nbind V articlelist visual-rows\nmacro w set browser "python3 '+str(queue.SCRIPTS/'newsboat_queue.py')+' add %u" ; open-in-browser-noninteractively\n'
            env=dict(XDG_STATE_HOME=str(root),NEWSBOAT_URLS_FILE=str(root/'urls'),NEWSBOAT_CACHE=str(root/'cache'),NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'))
            with reader(root,config,feed.as_uri()+'\n',env) as (_,screen,send,wait):
                wait(lambda s:'Video3' in s)
                send('Vj,w')
                wait(lambda s:len(queue.entries())==2)
                self.assertEqual([row['url'] for row in queue.entries()],URLS[:2])

    def test_missing_feed_title_uses_cached_channel_and_repairs_saved_queue(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=root/'cache';st=root/'newsboat';st.mkdir()
            with sqlite3.connect(cache) as db:
                db.execute('CREATE TABLE rss_feed(rssurl TEXT,title TEXT)')
                db.execute('CREATE TABLE rss_item(id INTEGER,url TEXT,title TEXT,feedurl TEXT,author TEXT)')
                db.execute('INSERT INTO rss_feed VALUES (?,?)',('59',''))
                db.execute('INSERT INTO rss_item VALUES (1,?,?,?,?)',(URLS[0],'Test video','59','Fallback author'))
            (st/'feed-titles.json').write_text(json.dumps({'59':'Actual channel'}))
            (st/'viewing-queue.json').write_text(json.dumps([dict(url=URLS[0],title='Test video',source='',queue_token='original-token')]))
            with patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_CACHE=str(cache),NEWSBOAT_URLS_FILE=str(root/'missing'),NEWSBOAT_PLAYLIST_CONTEXT=''),patch.object(media,'STATE',st):
                queue.change('refresh')
                row=queue.entries()[0]
                self.assertEqual(row['source'],'Actual channel')
                self.assertEqual(row['queue_token'],'original-token')
                (st/'feed-titles.json').write_text('{}')
                self.assertEqual(queue.metadata(URLS[0])['source'],'Fallback author')
