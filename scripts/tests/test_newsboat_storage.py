"""List-title storage totals exclude missing files, caches, and scheduled VODs."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_media as media
import newsboat_storage as storage
from test_newsboat_reconnect import reader, pyte, BINARY


class StorageTests(unittest.TestCase):
    def test_inventory_membership_dedup_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state/newsboat/downloads';state.mkdir(parents=True)
            videos=root/'videos';videos.mkdir();cache=root/'cache';cache.mkdir()
            groups=state.parent/'youtube-playlists/playthroughs';groups.mkdir(parents=True)
            url='https://youtu.be/abc123DEF45'
            (groups/'playlist.json').write_text(json.dumps({'selected_urls':[url]}))
            files={videos/'Part [abc123DEF45].mp4':2048,videos/'Other [abc123DEF46].mp4':1024,
                   videos/'twitch-vods/VOD [1234567890].mp4':4096,cache/'Cached [abc123DEF47].mp4':8192}
            for path,size in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'x'*size)
            index={str(path):{'valid':True} for path in files}
            index[str(videos/'missing [abc123DEF48].mp4')]={'valid':True}
            (state/'.media-index.json').write_text(json.dumps(index))
            (state/'done.json').write_text(json.dumps({'url':url,'status':'done','files':[str(videos/'Part [abc123DEF45].mp4')]}))
            article=root/'article.html';article.write_bytes(b'x'*500)
            (state/'article.json').write_text(json.dumps({'url':'https://example.com/article','status':'done','files':[str(article)]}))
            with patch.multiple(media,ROOT=videos,CACHE=cache):
                self.assertEqual(storage.publish(state),{'downloads':1524,'playthroughs':2048})
                self.assertIn('playthroughs\t2.0 KiB',(state.parent/'starred-urls.txt.storage').read_text())
                (videos/'Part [abc123DEF45].mp4').unlink()
                self.assertEqual(storage.publish(state)['playthroughs'],0)

    @unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
    def test_only_list_titles_show_and_update_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stars=root/'stars';sizes=root/'stars.storage'
            sizes.write_text('downloads\t1.5 GiB\nplaythroughs\t2.0 GiB\n')
            urls=[]
            for i,title in enumerate(('📥 Downloads','Playlists · 🎮 Playthroughs')):
                rss=root/f'feed{i}.xml'
                rss.write_text(f'<rss version="2.0"><channel><title>{title}</title><link>https://example.com</link><description>test</description><item><title>Item</title><guid>{i}</guid><link>https://example.com/{i}</link></item></channel></rss>')
                urls.append(rss.as_uri())
            config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nfeedlist-format "%t"\narticlelist-title-format " %T"\nbind-key j down\n'
            with reader(root,config,'\n'.join(urls)+'\n',{'NEWSBOAT_STARRED_STATUS':str(stars)}) as (_,screen,send,wait):
                wait(lambda s:'Downloads' in s and 'Playthroughs' in s)
                self.assertNotIn('GiB','\n'.join(screen.display))
                send('\n');wait(lambda s:'Downloads  ·  1.5 GiB' in screen.display[0])
                sizes.write_text('downloads\t0 B\nplaythroughs\t3.0 GiB\n')
                wait(lambda s:'Downloads  ·  0 B' in screen.display[0])
                send('q');wait(lambda s:'Playthroughs' in s)
                self.assertNotIn('GiB','\n'.join(screen.display))
                send('j\n');wait(lambda s:'Playthroughs  ·  3.0 GiB' in screen.display[0])
