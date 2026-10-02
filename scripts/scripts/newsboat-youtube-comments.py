#!/usr/bin/env python3
"""A comments-only YouTube window, sized by the shared Hyprland chat rule."""
import sys
from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QStackedLayout
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings

SCRIPT = r'''
(() => {
  if (!location.hostname.endsWith('youtube.com')) return;
  document.documentElement.setAttribute('dark','');
  const style = document.createElement('style');
  style.textContent = `html,body {background:#0f0f0f!important} ytd-comments {display:block!important; margin:0!important; padding:8px!important; width:auto!important} #comments {visibility:visible!important} ytd-watch-flexy #primary {min-width:0!important; max-width:none!important; width:100%!important; margin:0!important; padding:0!important} ytd-watch-flexy #columns {margin:0!important; padding:0!important} ytd-watch-flexy {margin:0!important; padding:0!important} #masthead-container, #secondary, #player, #player-container-outer, ytd-miniplayer {display:none!important}`;
  document.head.append(style);
  let prepared = false, revealing = false;
  window.__newsboatCommentsReady = false;
  function update() {
    for (const video of document.querySelectorAll('video')) {video.muted=true; video.pause();}
    const comments = document.querySelector('ytd-comments#comments');
    if (!comments) return;
    if (prepared) {
      const content = comments.querySelector('ytd-comment-thread-renderer, ytd-message-renderer');
      if (!revealing && content && content.getBoundingClientRect().height > 0) {
        revealing = true;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          setTimeout(() => {window.__newsboatCommentsReady = true;}, 200);
        }));
      }
      return;
    }
    // Keep the live comments subtree and its ancestors intact so replies,
    // sorting and infinite scrolling continue to work normally.
    for (let node=comments; node && node!==document.body; node=node.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling!==node && !['SCRIPT','STYLE','LINK','YTD-POPUP-CONTAINER'].includes(sibling.tagName)) sibling.style.setProperty('display','none','important');
      }
      node.style.setProperty('margin-top','0','important');
    }
    comments.scrollIntoView();
    prepared=true;
    update();
  }
  new MutationObserver(update).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('play',e=>{if(e.target.tagName==='VIDEO'){e.target.muted=true;e.target.pause();}},true);
  update();
})();
'''


def main(url):
    from newsboat_media import identity
    key=identity(url)
    if not key or key[0]!='youtube':raise ValueError('Expected a YouTube video')
    app=QApplication([sys.argv[0]])
    app.setDesktopFileName('newsboat-youtube-comments')
    app.setApplicationName('newsboat-youtube-comments')
    window=QMainWindow();window.setWindowTitle('YouTube comments')
    container=QWidget();layout=QVBoxLayout(container);layout.setContentsMargins(0,0,0,0)
    status=QLabel('YouTube comments');status.setWordWrap(True)
    status.setStyleSheet('padding:8px;color:#ddd;background:#181818')
    view=QWebEngineView();view.setZoomFactor(.9);view.page().setAudioMuted(True)
    view.page().setBackgroundColor(QColor('#0f0f0f'))
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,True)
    script=QWebEngineScript();script.setName('comments-only')
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    script.setSourceCode(SCRIPT);view.page().scripts().insert(script)
    # Keep the renderer sized and active underneath an opaque native cover.
    # Hiding the web view itself can delay YouTube's lazy-loaded comments.
    body=QWidget();stack=QStackedLayout(body)
    stack.setContentsMargins(0,0,0,0)
    stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
    cover=QLabel('Loading comments…');cover.setWordWrap(True)
    cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cover.setStyleSheet('background:#0f0f0f;color:#ddd;padding:12px;')
    stack.addWidget(view);stack.addWidget(cover);stack.setCurrentWidget(cover)
    layout.addWidget(status);layout.addWidget(body);window.setCentralWidget(container)
    container.setStyleSheet('background:#0f0f0f;')
    frames=('⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏')
    spinner=QTimer(window);spinner.setInterval(90)
    spin_index=0
    def spin():
        nonlocal spin_index
        cover.setText(frames[spin_index % len(frames)]+'  Loading comments…')
        spin_index+=1
    spinner.timeout.connect(spin)
    poll=QTimer(window);poll.setInterval(100)
    deadline=QTimer(window);deadline.setSingleShot(True)
    def reveal(ready):
        if ready is True:
            poll.stop();deadline.stop();spinner.stop();cover.hide();stack.setCurrentWidget(view)
    def started():
        spin();spinner.start();cover.show();stack.setCurrentWidget(cover)
        poll.start();deadline.start(30000)
    def failed():
        spinner.stop()
        cover.setText('Comments could not load. Close this window and press Mod+C to retry.')
    poll.timeout.connect(lambda: view.page().runJavaScript(
        'window.__newsboatCommentsReady === true',
        QWebEngineScript.ScriptWorldId.ApplicationWorld, reveal))
    deadline.timeout.connect(failed)
    view.loadStarted.connect(started)
    view.loadFinished.connect(lambda ok: None if ok else failed())
    view.setUrl(QUrl('https://www.youtube.com/watch?v='+key[1]))
    window.resize(384,821);window.show()
    return app.exec()


if __name__=='__main__':sys.exit(main(sys.argv[1]))
