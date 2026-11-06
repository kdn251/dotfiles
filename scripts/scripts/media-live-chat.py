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

RUMBLE_DARK = r'''
(() => {
  if (!["rumble.com", "www.rumble.com"].includes(location.hostname)) return;
  function apply() {
    const root = document.documentElement;
    if (!root) return;
    // Use Rumble's native dark palette, including inputs and chat messages.
    if (root.getAttribute("data-theme") !== "dark") root.setAttribute("data-theme", "dark");
    root.style.colorScheme = "dark";
  }
  apply();
  new MutationObserver(apply).observe(document, {childList:true, subtree:true, attributes:true, attributeFilter:["data-theme"]});
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
    from media_chat_live import watch_preload_owner
    watch_preload_owner(app)
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
    elif urlparse(url).hostname in ('rumble.com','www.rumble.com'):
        script=QWebEngineScript();script.setName('rumble-live-chat-dark')
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode(RUMBLE_DARK);view.page().scripts().insert(script)
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
    import os
    from pathlib import Path
    ready=Path(os.environ.get("XDG_RUNTIME_DIR","/tmp"))/f"media-chat-ready-{os.getpid()}"
    app.aboutToQuit.connect(lambda:ready.unlink(missing_ok=True))
    generation=0
    render_timer=QTimer(window);render_timer.setInterval(100)
    def started():
        nonlocal generation
        generation+=1;render_timer.stop()
        ready.unlink(missing_ok=True)
        cover.show();stack.setCurrentWidget(cover);spin();spinner.start()
    def reveal(token):
        if token!=generation:return
        render_timer.stop();spinner.stop()
        cover.hide();stack.setCurrentWidget(view)
        # Let Qt paint the revealed web view before dropping the external
        # screenshot cover. loadFinished alone precedes Kick's client rendering.
        QTimer.singleShot(150,lambda:ready.touch() if token==generation else None)
    def rendered():
        token=generation
        view.page().runJavaScript(
            "Boolean(document.body && document.body.innerText.trim().length > 20)",
            lambda visible:reveal(token) if visible else None)
    def finished(ok):
        if ok:
            render_timer.start();rendered()
        else:
            spinner.stop();cover.setText('Chat could not load. Press Ctrl+R to retry.')
            token=generation
            QTimer.singleShot(150,lambda:ready.touch() if token==generation else None)
    render_timer.timeout.connect(rendered)
    from PyQt6.QtGui import QShortcut, QKeySequence
    retry=QShortcut(QKeySequence('Ctrl+R'),window);retry.activated.connect(view.reload)
    spinner.timeout.connect(spin);view.loadStarted.connect(started);view.loadFinished.connect(finished)
    window.setCentralWidget(body);window.resize(260,600);view.setUrl(QUrl(url));window.show()
    result=app.exec()
    view.setPage(QWebEnginePage(view));return result


if __name__=='__main__':sys.exit(main(sys.argv[1],sys.argv[2]))
