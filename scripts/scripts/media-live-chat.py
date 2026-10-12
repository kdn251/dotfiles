#!/usr/bin/env python3
"""A dedicated, persistent browser window for official stream pop-out chats."""
import sys
from media_chat_live import valid_chat_url
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

YOUTUBE_DARK = r'''
(() => {
  if (!["youtube.com", "www.youtube.com"].includes(location.hostname)) return;
  function apply() {
    const root = document.documentElement;
    if (!root) return;
    if (!root.hasAttribute("dark")) root.setAttribute("dark", "");
    root.style.colorScheme = "dark";
  }
  apply();
  new MutationObserver(apply).observe(document, {childList:true, subtree:true, attributes:true, attributeFilter:["dark"]});
})();
'''


def main(url, title):
    if not valid_chat_url(url):raise ValueError('Unsupported live chat URL')
    from PyQt6.QtCore import QUrl, QTimer, Qt
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QStackedLayout
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
    app=QApplication([sys.argv[0]])
    app.setDesktopFileName('newsboat-live-chat');app.setApplicationName('newsboat-live-chat')
    window=QMainWindow();window.setWindowTitle(title)
    view=QWebEngineView()
    profile=QWebEngineProfile('media-live-chat',window)
    view.setPage(QWebEnginePage(profile,view));view.page().setAudioMuted(True)
    view.page().setBackgroundColor(QColor('#0f0f0f'))
    if urlparse(url).hostname in ('youtube.com','www.youtube.com'):
        parsed=urlparse(url)
        query=dict(parse_qsl(parsed.query));query['dark_theme']='1'
        url=urlunparse(parsed._replace(query=urlencode(query)))
        script=QWebEngineScript();script.setName('youtube-live-chat-dark')
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode(YOUTUBE_DARK);view.page().scripts().insert(script)
    body=QWidget();stack=QStackedLayout(body);stack.setContentsMargins(0,0,0,0)
    stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
    cover=QLabel();cover.setAlignment(Qt.AlignmentFlag.AlignCenter);cover.setWordWrap(True)
    cover.setStyleSheet('background:#0f0f0f;color:#ddd;padding:8px')
    stack.addWidget(view);stack.addWidget(cover);stack.setCurrentWidget(cover)
    spinner=QTimer(window);spinner.setInterval(90)
    frames=iter(())
    def spin():
        nonlocal frames
        import itertools
        try:frame=next(frames)
        except StopIteration:frames=itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏');frame=next(frames)
        cover.setText(frame+' Loading '+title+'…')
    def started():
        cover.show();stack.setCurrentWidget(cover);spin();spinner.start()
    def finished(ok):
        spinner.stop()
        if ok:cover.hide();stack.setCurrentWidget(view)
        else:cover.setText('Chat could not load. Press Ctrl+R to retry.')
    from PyQt6.QtGui import QShortcut, QKeySequence
    retry=QShortcut(QKeySequence('Ctrl+R'),window);retry.activated.connect(view.reload)
    spinner.timeout.connect(spin);view.loadStarted.connect(started);view.loadFinished.connect(finished)
    window.setCentralWidget(body);window.resize(260,600);view.setUrl(QUrl(url));window.show()
    result=app.exec()
    view.setPage(QWebEnginePage(view));return result


if __name__=='__main__':sys.exit(main(sys.argv[1],sys.argv[2]))
