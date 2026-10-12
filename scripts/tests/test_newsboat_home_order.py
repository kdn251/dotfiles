"""Homepage row moves survive restart, filtering and query changes."""
import json
import tempfile
import unittest
from pathlib import Path
from test_newsboat_reconnect import reader

class HomeOrderTests(unittest.TestCase):
 def test_moves_restart_hidden_rows_and_source_navigation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   source=root/'source.xml'
   source.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description></channel></rss>')
   names=['📬 New','⭐ Starred','📥 Downloads','🌎 All']
   def urls(names,rule='link = "none"'):
    return '\n'.join(json.dumps('query:'+name+':'+rule,ensure_ascii=False) for name in names)+'\n'+source.as_uri()+'\n'
   startup=next(l for l in (Path(__file__).resolve().parents[2]/'newsboat/.newsboat/config').read_text().splitlines() if l.startswith('run-on-startup '))
   cfg='auto-reload no\nsuppress-first-reload yes\nshow-read-feeds yes\nprepopulate-query-feeds yes\nconfirm-exit no\nfeedlist-format "%t"\nbind-key j down\nbind-key k up\nbind yy feedlist undo-checkpoint home-yank\nbind P feedlist set browser "playlist-browser-test"\n'+startup+'\n'
   env={'NEWSBOAT_HOME_ORDER':str(root/'state/home-order')}
   def rows(screen):
    return [name for line in screen.display[1:8] for name in names if name in line.replace("📪", "📬")]
   with reader(root,cfg,urls(names),env) as (_,screen,send,wait):
    wait(lambda s:rows(screen)==names)
    send('p');wait(lambda s:'yy first' in s)
    send('yy');wait(lambda s:'Home row picked up' in s)
    send('jjp');wait(lambda s:rows(screen)==[names[i] for i in [1,2,0,3]] and screen.cursor.y==3)
    send('k');wait(lambda s:screen.cursor.y==2)
    send('P');wait(lambda s:rows(screen)==[names[i] for i in [1,0,2,3]] and screen.cursor.y==2)
    self.assertEqual((root/'state/home-order').read_text().splitlines(),['Starred','New','Downloads','All'])
    send('jj\n');wait(lambda s:'Source' in s and not rows(screen))
    send('P');send('q');wait(lambda s:rows(screen)==[names[i] for i in [1,0,2,3]])
   with reader(root,cfg,urls([names[i] for i in [0,2,3]],'title = "changed"'),env) as (_,screen,send,wait):
    wait(lambda s:rows(screen)==[names[i] for i in [0,2,3]])
   with reader(root,cfg,urls(names),env) as (_,screen,send,wait):
    wait(lambda s:rows(screen)==[names[i] for i in [1,0,2,3]])
