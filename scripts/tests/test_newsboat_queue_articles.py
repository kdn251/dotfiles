"""Mixed reading/viewing queues must not send articles to MPV or yt-dlp."""
import os
import unittest
from unittest.mock import patch
from test_newsboat_queue import isolated, URLS
import newsboat_queue as queue
import newsboat_queue_time as timing
import newsboat_queue_panel as panel
import newsboat_autoplay as autoplay

ARTICLE='https://example.org/essay'

class ArticleQueueTests(unittest.TestCase):
    def add_article(self):
        with patch.object(queue,'metadata',return_value=dict(url=ARTICLE,title='An essay',source='Example')):
            queue.change('add',ARTICLE)

    def test_article_persists_deduplicates_and_supports_undo(self):
        with isolated():
            self.add_article();self.add_article()
            self.assertEqual(len(queue.entries()),1)
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='remove-article'):
                queue.change('remove',ARTICLE)
            self.assertEqual(queue.entries(),[])
            queue.change('restore',ARTICLE,'remove-article')
            self.assertEqual(queue.entries()[0]['title'],'An essay')
            self.assertEqual(queue.entries()[0]['source'],'Example')
            self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text(),'1 link\n')
            self.assertEqual(timing.remaining(queue.entries()),(0,[]))
            self.assertIsNone(panel.snapshot(queue.entries()))

    def test_video_autoplay_navigation_and_menu_skip_articles(self):
        with isolated():
            queue.change('add',URLS[0]);self.add_article();queue.change('add',URLS[1])
            self.assertEqual(queue.navigation(URLS[1])[0]['url'],URLS[0])
            self.assertEqual(queue.navigation(URLS[0])[1]['url'],URLS[1])
            self.assertEqual([r['url'] for r in queue.menu_rows()],[URLS[1],URLS[0]])
            with patch.dict(os.environ,NEWSBOAT_QUEUE_PLAYBACK='1'):
                plan=autoplay.plan(URLS[1])
            self.assertEqual(plan['next']['url'],URLS[0])
            self.assertEqual(plan['queue_position']['total'],2)
            self.assertEqual(len(queue.entries()),3)

    def test_open_queue_head_routes_article_through_normal_opener(self):
        with isolated(),patch.dict(os.environ),patch.object(queue.subprocess,'call',return_value=0) as call,patch('newsboat_resume.launch') as launch:
            self.add_article();self.assertEqual(queue.resume(),0)
            self.assertEqual(call.call_args.args[0][-2:],[str(queue.SCRIPTS/'newsboat-open.py'),ARTICLE])
            launch.assert_not_called()

    def test_mixed_queue_feed_contains_article_and_header_uses_video_url(self):
        import xml.etree.ElementTree as ET
        with isolated() as (root,_):
            queue.change('add',URLS[0]);self.add_article()
            view=root/'view';view.mkdir()
            queue.prepare_view(view)
            items=ET.parse(view/'history.xml').findall('./channel/item')
            self.assertEqual([item.findtext('link') for item in items],[ARTICLE,URLS[0]])
            self.assertEqual(items[0].findtext('title'),'An essay')
            header=panel.Header();header.update()
            self.assertTrue(header.path.read_text().rstrip().endswith(URLS[0]))
            self.assertNotIn(ARTICLE,header.path.read_text())

    def test_invalid_non_web_urls_are_rejected(self):
        with isolated():
            for url in ('javascript:alert(1)','file:///etc/passwd','https://','https://example.org/\nfoo'):
                with self.assertRaises(ValueError):queue.change('add',url)
