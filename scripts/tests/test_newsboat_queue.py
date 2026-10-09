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
        with patch('newsboat_queue_time.start_worker'),patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_URLS_FILE=str(urls),NEWSBOAT_CACHE=str(root/'missing'),NEWSBOAT_PLAYLIST_CONTEXT=''),patch.object(media,'STATE',root/'newsboat'),patch.object(queue,'metadata',side_effect=lambda url:dict(url=url,title='Video'+str(URLS.index(url)),source='Creator')):
            yield root,urls

class QueueTests(unittest.TestCase):
    def test_stop_marker_set_clear_move_and_native_keys(self):
        with isolated() as (root,urls):
            for url in URLS[:2]:queue.change('add',url)
            (root/'scripts').symlink_to(queue.SCRIPTS,target_is_directory=True)
            view=root/'view';view.mkdir();_,config=queue.prepare_view(view)
            env=dict(NEWSBOAT_QUEUE_VIEW='1',NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'))
            with reader(root,config.read_text()+'run-on-startup open\n',(view/'urls').read_text(),env) as (_,screen,send,wait):
                wait(lambda s:'Video0' in s and 'Video1' in s)
                send('z');wait(lambda s:'💤' in screen.display[1])
                self.assertTrue(autoplay.plan(URLS[0])['stop_after_current'])
                send('Z');wait(lambda s:'💤' not in s)
                self.assertFalse(any(r.get('stop_after') for r in queue.entries()))
                send('jz');wait(lambda s:'💤' in screen.display[2])
                queue.change('move-before',URLS[1],URLS[0])
                wait(lambda s:'Video1' in screen.display[1] and '💤' in screen.display[1])
                queue.change('stop-after',URLS[0])
                wait(lambda s:'💤' in screen.display[2] and '💤' not in screen.display[1])
                self.assertEqual(sum(bool(r.get('stop_after')) for r in queue.entries()),1)

    def test_real_mpv_honors_stop_set_and_clear_while_open(self):
        self.run_real_mpv(natural_end=True,stop_mode='set')
        self.run_real_mpv(natural_end=True,stop_mode='clear')

    def test_fifo_dedup_membership_and_success_only_consumption(self):
        with isolated() as (root,urls):
            queue.change('add',URLS[2]);queue.change('add',URLS[1]);queue.change('add','https://youtu.be/'+'2'*11)
            self.assertEqual([r['url'] for r in queue.entries()],[URLS[2],URLS[1]])
            self.assertTrue(urls.read_text().startswith('"query:📺 Queue:'))
            token=queue.entries()[0]['queue_token']
            queue.change('started',URLS[2],'wrong-token')
            self.assertEqual(len(queue.entries()),2)
            queue.change('started',URLS[2],token)
            self.assertEqual(len(queue.entries()),2)
            queue.change('finished',URLS[2],token)
            self.assertEqual([r['url'] for r in queue.entries()],[URLS[1]])
            queue.change('remove',URLS[1]);self.assertNotIn('Queue',urls.read_text())
            queue.change('add',URLS[2]);queue.change('finished',URLS[2],token)
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
                queue.change('finished',URLS[0],queue.entries()[0]['queue_token'])
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
                queue.change('add',URLS[0]);wait(lambda s:'Queue' in s and 'time unavailable' in s)
                self.assertIn('Queue',screen.display[1]);self.assertIn('New',screen.display[2])
                queue.change('add',URLS[1]);wait(lambda s:'Queue' in s and len(queue.entries())==2)
                queue.change('remove',URLS[0]);queue.change('remove',URLS[1]);wait(lambda _:not any('Queue' in row for row in screen.display[1:-3]))

    def run_real_mpv(self, natural_end=False, stop_mode=None):
        import shutil,subprocess,time,wave
        with isolated() as (root,urls):
            scripts=root/'scripts';scripts.mkdir();ipc_flag=root/'go';calls=root/'calls';ready=root/'ready'
            for name in ('newsboat_autoplay.py','newsboat_queue.py'):
                (scripts/name).symlink_to(queue.SCRIPTS/name)
            shutil.copyfile(queue.SCRIPTS/'newsboat-playlist-playback.lua',scripts/'newsboat-playlist-playback.lua')
            (scripts/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            (scripts/'newsboat-playback-started.py').write_text('pass\n')
            (scripts/'newsboat-playback-target.py').write_text(
                'import json,sys\nfrom pathlib import Path\nimport newsboat_autoplay\n'
                'Path('+repr(str(calls))+').write_text(sys.argv[1])\n'
                'print(json.dumps({"url":sys.argv[1],"path":'+repr(str(root/'audio.wav'))+',"title":sys.argv[2],"local":True,"plan":newsboat_autoplay.plan(sys.argv[1])}))\n')
            source=root/'audio.wav'
            with wave.open(str(source),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*(8000 if natural_end else 160000))
            driver=root/'driver.lua'
            driver.write_text('mp.register_event("file-loaded",function() local f=io.open('+json.dumps(str(ready))+',"w");f:write("ready");f:close() end)\n'+
                'mp.add_periodic_timer(.1,function() local f=io.open('+json.dumps(str(ipc_flag))+',"r");if f then f:close();os.remove('+json.dumps(str(ipc_flag))+');'+('mp.set_property_native("pause",false)' if stop_mode else 'mp.commandv("keypress",">")')+' end end)\n'+
                'mp.add_timeout(15,function() mp.commandv("quit") end)\n')
            manifest=root/'playlist.json';manifest.write_text(json.dumps(dict(rows=[dict(url=u,title=u) for u in URLS[:2]])))
            queue.change('add',URLS[0])
            if natural_end:queue.change('add',URLS[3])
            env=dict(os.environ,NEWSBOAT_MEDIA_URL=URLS[0],NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_PLAYLIST_CONTEXT=str(manifest))
            process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause='+('no' if natural_end and not stop_mode else 'yes'),'--script='+str(scripts/'newsboat-playlist-playback.lua'),'--script='+str(driver),str(source)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+4
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(ready.exists())
                if stop_mode:
                    queue.change('stop-after',URLS[0])
                    time.sleep(.7)
                    if stop_mode=='clear':
                        queue.change('clear-stop',URLS[0]);time.sleep(.7)
                    ipc_flag.touch()
                if not natural_end:
                    self.assertTrue(any(row['url']==URLS[0] for row in queue.entries()),'starting a video keeps it queued')
                if not natural_end:
                    queue.change('add',URLS[2]);queue.change('add',URLS[3])
                    time.sleep(.8)
                    queue.change('remove',URLS[2])
                    time.sleep(.8)
                    ipc_flag.touch()
                deadline=time.monotonic()+(7 if natural_end else 3)
                while not calls.exists() and time.monotonic()<deadline:time.sleep(.05)
                if stop_mode=='set':
                    self.assertFalse(calls.exists(),'stop marker must prevent autoplay')
                    self.assertIsNone(process.poll(),'player should remain paused at the end')
                    self.assertEqual([r['url'] for r in queue.entries()],[URLS[3]])
                    return
                self.assertTrue(calls.exists())
                self.assertEqual(calls.read_text(),URLS[3],'edited queue takes priority over playlist episode 1')
                self.assertEqual(len(queue.entries()),1 if natural_end else 2,'only natural EOF consumes the current item')
            finally:
                process.terminate();process.communicate(timeout=3)
            if not natural_end:
                self.assertTrue(any(row['url']==URLS[0] for row in queue.entries()),'closing mpv early keeps the item queued')

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
            with patch('newsboat_queue_time.start_worker'),patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_CACHE=str(cache),NEWSBOAT_URLS_FILE=str(root/'missing'),NEWSBOAT_PLAYLIST_CONTEXT=''),patch.object(media,'STATE',st):
                queue.change('refresh')
                row=queue.entries()[0]
                self.assertEqual(row['source'],'Actual channel')
                self.assertEqual(row['queue_token'],'original-token')
                (st/'feed-titles.json').write_text('{}')
                self.assertEqual(queue.metadata(URLS[0])['source'],'Fallback author')

    def test_queue_navigation_follows_visible_order_and_skips_completed(self):
        with isolated() as (root,_):
            for url in URLS:queue.change('add',url)
            middle=autoplay.plan(URLS[1])
            self.assertTrue(middle['queue'])
            self.assertEqual(middle['next']['url'],URLS[2])
            self.assertEqual(middle['queue_next']['url'],URLS[2])
            self.assertEqual(middle['previous']['url'],URLS[0])
            queue.change('finished',URLS[0],queue.entries()[0]['queue_token'])
            self.assertIsNone(autoplay.plan(URLS[1])['previous'])
            queue.change('remove',URLS[2])
            self.assertEqual(autoplay.plan(URLS[1])['queue_next']['url'],URLS[3])
            self.assertIsNone(autoplay.plan(URLS[3])['queue_next'],'manual next never wraps to earlier queued videos')
            with patch.dict(os.environ,NEWSBOAT_QUEUE_PLAYBACK='1'):
                self.assertIsNone(autoplay.plan(URLS[0])['previous'])
                self.assertEqual(autoplay.plan(URLS[0])['queue_next']['url'],URLS[1])

    def test_manual_next_skips_completed_history_not_visible_in_queue(self):
        with isolated():
            for url in URLS:queue.change('add',url)
            autoplay.plan(URLS[0])  # Record playback navigation history.
            completed = queue.entries()[1]
            queue.change('finished',URLS[1],completed['queue_token'])
            self.assertEqual(autoplay.plan(URLS[0])['queue_next']['url'],URLS[2])
            self.assertEqual(autoplay.plan(URLS[2])['previous']['url'],URLS[0])
            queue.change('move-before',URLS[3],URLS[2])
            self.assertEqual(autoplay.plan(URLS[0])['queue_next']['url'],URLS[3])
            self.assertEqual(autoplay.plan(URLS[3])['previous']['url'],URLS[0])
            self.assertEqual(autoplay.plan(URLS[2])['previous']['url'],URLS[3])
            self.assertIsNone(autoplay.plan(URLS[0])['previous'])
            self.assertIsNone(autoplay.plan(URLS[2])['queue_next'])

    def test_mpv_arrow_keys_use_queue_neighbors_even_with_autoplay_off(self):
        import subprocess
        harness=r'''
local keys, launched = {}, nil
local plan={enabled=false,queue=true,playlist=false,
 next={url='automatic',queue_token='a'},
 queue_next={url='next',queue_token='n'}, previous={url='previous',queue_token='p'}}
package.preload['mp.utils']=function() return {
 split_path=function() return '/tmp/' end,
 parse_json=function() return plan end
} end
mp={
 command_native_async=function(cmd) launched=cmd.args;return 1 end,
 command_native=function(cmd)
  if cmd.args and cmd.args[2]:match('newsboat_autoplay.py$') then return {status=0,stdout='plan'} end
  if cmd.args and cmd.args[2]:match('newsboat%-play%-video.py$') then launched=cmd.args end
  return {status=0}
 end,
 get_property=function(_,default) return default end,
 get_property_native=function() return false end,
 set_property=function() end,set_property_native=function() end,
 commandv=function() end,osd_message=function() end,
 add_forced_key_binding=function(key,_,callback) keys[key]=callback end,
 observe_property=function() end,register_event=function() end,
 add_periodic_timer=function() return {kill=function() end} end
}
dofile(arg[1])
assert(keys['<'] and keys['>'],'both directions bound outside a creator playlist')
keys[arg[2]]()
assert(launched[5]=='queue','preserve queue context inside the player')
assert(launched[3]==arg[3],'use the adjacent queue entry, not the autoplay fallback')
'''
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'test.lua';script.write_text(harness)
            for key,expected in [('>','next'),('<','previous')]:
                subprocess.run(['lua',str(script),str(queue.SCRIPTS/'newsboat-playlist-playback.lua'),key,expected],env=dict(os.environ,NEWSBOAT_MEDIA_URL=URLS[1]),check=True,capture_output=True)
