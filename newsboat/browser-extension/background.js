// Only extension content scripts can invoke this bridge. Use the browser's URL,
// not an arbitrary URL supplied by the page or message.
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (!sender.tab || sender.frameId !== 0 || !/^https?:/.test(sender.url || '') ||
      !['get', 'save'].includes(message.action)) return;
  chrome.runtime.sendNativeMessage('local.newsboat.reading', {
    action: message.action, url: sender.url, position: message.position
  }, result => {
    const error = chrome.runtime.lastError;
    reply(error ? {tracked: false} : result);
  });
  return true;
});
