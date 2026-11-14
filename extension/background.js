/**
 * Service Worker background script for Mail CoastGuard extension.
 * The ONLY component authorized to communicate with backend endpoints over HTTP.
 */

importScripts('core.js', 'sites.js');

const Core = globalThis.MailCoastGuardCore;

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';

function getBackendUrl(callback) {
  chrome.storage.local.get({ backendUrl: DEFAULT_BACKEND_URL }, (items) => {
    const url = items.backendUrl || DEFAULT_BACKEND_URL;
    if (Core.validateBackendUrl(url)) {
      callback(url.replace(/\/+$/, ''));
    } else {
      callback(DEFAULT_BACKEND_URL);
    }
  });
}

function updateBadge(tabId, level) {
  if (!tabId) return;

  if (!level) {
    chrome.action.setBadgeText({ text: '', tabId });
    return;
  }

  const badgeConfig = Core.levelBadge(level);
  chrome.action.setBadgeText({ text: badgeConfig.badgeText, tabId });
  chrome.action.setBadgeBackgroundColor({ color: badgeConfig.badgeColor, tabId });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Validate sender authenticity
  if (!sender || sender.id !== chrome.runtime.id) {
    return false;
  }

  // Handle popup status check request
  if (message && message.type === 'STATUS') {
    getBackendUrl((backendUrl) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);

      fetch(`${backendUrl}/health`, {
        method: 'GET',
        credentials: 'omit',
        redirect: 'error',
        signal: controller.signal
      })
        .then(res => {
          clearTimeout(timer);
          if (res.ok) {
            sendResponse({ ok: true });
          } else {
            sendResponse({ ok: false, status: res.status });
          }
        })
        .catch(() => {
          clearTimeout(timer);
          sendResponse({ ok: false });
        });
    });
    return true; // Keep channel open for async response
  }

  // For content script messages, ensure sender has valid tab and origin
  if (!sender.tab || !sender.tab.url) {
    return false;
  }

  let senderOrigin = '';
  try {
    senderOrigin = new URL(sender.tab.url).origin;
  } catch (_) {
    return false;
  }

  const allowedOrigins = (globalThis.SITES || []).flatMap(s => s.origins);
  if (!allowedOrigins.includes(senderOrigin)) {
    return false;
  }

  const tabId = sender.tab.id;

  if (message.type === 'CLEAR') {
    updateBadge(tabId, null);
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === 'ANALYZE' || message.type === 'DEEP_ANALYSIS') {
    const validatedEmail = Core.validateEmail(message.email);
    if (!validatedEmail) {
      sendResponse({ ok: false, code: '422' });
      return false;
    }

    const isDeep = message.type === 'DEEP_ANALYSIS';
    const endpointPath = isDeep ? '/deep-analysis' : '/analyze';
    const timeoutMs = isDeep ? 70000 : 10000;

    getBackendUrl((backendUrl) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      fetch(`${backendUrl}${endpointPath}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validatedEmail),
        credentials: 'omit',
        redirect: 'error',
        signal: controller.signal
      })
        .then(async (response) => {
          clearTimeout(timer);

          if (!response.ok) {
            updateBadge(tabId, null);
            let code = 'OTHER';
            if (response.status === 422) code = '422';
            else if (response.status === 413) code = '413';
            else if (response.status === 429) code = '429';
            sendResponse({ ok: false, code });
            return;
          }

          // Enforce 200 KB response limit
          const text = await response.text();
          if (text.length > 204800) {
            updateBadge(tabId, null);
            sendResponse({ ok: false, code: '413' });
            return;
          }

          let json;
          try {
            json = JSON.parse(text);
          } catch (_) {
            updateBadge(tabId, null);
            sendResponse({ ok: false, code: 'INVALID' });
            return;
          }

          const sanitized = Core.sanitizeResponse(json);
          if (!sanitized) {
            updateBadge(tabId, null);
            sendResponse({ ok: false, code: 'INVALID' });
            return;
          }

          updateBadge(tabId, sanitized.final_level);
          sendResponse({ ok: true, data: sanitized });
        })
        .catch((err) => {
          clearTimeout(timer);
          updateBadge(tabId, null);
          const code = err.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK';
          sendResponse({ ok: false, code });
        });
    });

    return true; // Keep channel open for async fetch
  }

  return false;
});
