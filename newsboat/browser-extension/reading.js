(() => {
  if (window !== window.top || location.hostname === '127.0.0.1') return;
  const send = message => new Promise(resolve => {
    chrome.runtime.sendMessage(message, result => {
      const error = chrome.runtime.lastError;
      resolve(error ? null : result);
    });
  });
  const top = el => el.getBoundingClientRect().top + scrollY;
  const text = el => (el?.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 240);
  let ready = false, engaged = false, touched = false, timer, furthest = 0;
  let content, blocks = [];
  function locate() {
    // Reddit's article is the self-post, not the complete comment thread.
    content = document.querySelector('.entry .usertext-body, [itemprop="articleBody"], article, main, [role="main"]') || document.body;
    blocks = [...content.querySelectorAll('p,h1,h2,h3,li,pre,blockquote')].filter(el => el.getBoundingClientRect().height > 0);
  }
  function snapshot() {
    const start = top(content), end = start + content.getBoundingClientRect().height;
    let fraction = engaged ? Math.max(0, Math.min(1, (scrollY + innerHeight * .8 - start) / Math.max(1, end - start))) : 0;
    if (engaged && scrollY + innerHeight >= end - 8) fraction = 1;
    furthest = Math.max(furthest, fraction);
    let anchor = -1;
    for (let i = 0; i < blocks.length; i++) if (top(blocks[i]) <= scrollY + 16) anchor = i;
    return {fraction: furthest, y: scrollY, anchor, offset: anchor < 0 ? 0 : scrollY - top(blocks[anchor]), text: text(blocks[anchor])};
  }
  function save() {
    clearTimeout(timer);
    if (ready && engaged) send({action: 'save', position: snapshot()});
  }
  function engage(e) {
    if (e.type === 'keydown' && !['j','k','g','G',' ','PageDown','PageUp','ArrowDown','ArrowUp','End','Home','d','u'].includes(e.key)) return;
    touched = true;
    if (ready) engaged = true;
  }
  for (const event of ['wheel','touchmove','pointerdown','keydown']) addEventListener(event, engage, {passive: true});
  send({action: 'get'}).then(state => {
    if (!state?.tracked) return;
    furthest = state.fraction || 0;
    const position = state.position || {};
    function restore() {
      locate();
      if (!touched && !location.hash) {
        // Ignore our own scroll event, including retries after fonts/images load.
        ready = false;
        const block = position.text ? blocks.find(el => text(el) === position.text) : blocks[position.anchor];
        scrollTo({top: block ? top(block) + (position.offset || 0) : (position.y || 0), behavior: 'instant'});
      }
      requestAnimationFrame(() => requestAnimationFrame(() => {ready = true;}));
    }
    restore();
    // Fonts/images and lazy content can move the paragraph after initial load.
    if (document.readyState !== 'complete') addEventListener('load', restore, {once: true});
    setTimeout(restore, 1000);
    setTimeout(restore, 2500);
    addEventListener('scroll', () => {
      if (!ready) return;
      // Vimium consumes j/k before this script sees keydown. The resulting
      // scroll is the reliable signal, and must also cancel delayed restores.
      touched = true;
      engaged = true;
      clearTimeout(timer); timer = setTimeout(save, 250);
    }, {passive: true});
    const periodic = setInterval(save, 3000);
    addEventListener('pagehide', () => {save(); clearInterval(periodic);});
    document.addEventListener('visibilitychange', () => {if (document.hidden) save();});
  });
})();
