/**
 * Content script for Mail CoastGuard browser extension.
 * Monitors the DOM for open messages, extracts data, and coordinates verification.
 */

(function () {
  'use strict';

  const Core = globalThis.MailCoastGuardCore;
  const Panel = globalThis.MailCoastGuardPanel;

  // Find matching site adapter
  const currentOrigin = window.location.origin;
  const site = (globalThis.SITES || []).find(s => s.origins.includes(currentOrigin));
  if (!site) {
    return; // Origin not supported
  }

  let activePanel = null;
  let currentMsgId = null;
  let currentFingerprint = null;
  let currentRequestId = 0;
  const automaticCache = new Map(); // key: msgId -> local layer result
  const deepCache = new Map();      // key: msgId -> deep analysis result

  let debounceTimer = null;

  // Immediate cleanup when switching messages in inbox list
  document.addEventListener('click', (e) => {
    const row = e.target && e.target.closest && e.target.closest('.email-row');
    if (row && activePanel) {
      activePanel.remove();
      activePanel = null;
      currentMsgId = null;
      currentFingerprint = null;
    }
  }, true);

  function isExtensionActive(callback) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get({ active: true }, (items) => {
        callback(items.active);
      });
    } else {
      callback(true);
    }
  }

  function extractEmailFromDOM() {
    const readingEl = document.querySelector(site.selectors.reading);
    if (!readingEl) return null;

    const msgId = readingEl.getAttribute('data-msg-id');
    if (!msgId) return null;

    const senderEl = readingEl.querySelector(site.selectors.sender);
    let sender = senderEl ? senderEl.textContent : '';
    // Strip surrounding brackets if present in raw view: <user@domain>
    if (sender.startsWith('<') && sender.endsWith('>')) {
      sender = sender.slice(1, -1);
    }

    const nameEl = readingEl.querySelector(site.selectors.displayName);
    const displayName = nameEl ? nameEl.textContent : '';

    const replyToEl = readingEl.querySelector(site.selectors.replyTo);
    const replyTo = replyToEl ? replyToEl.textContent : '';

    const subjEl = readingEl.querySelector(site.selectors.subject);
    const subject = subjEl ? subjEl.textContent : '';

    const bodyEl = readingEl.querySelector(site.selectors.body);
    const body = bodyEl ? bodyEl.textContent : '';

    const attEls = readingEl.querySelectorAll(site.selectors.attachment);
    const attachments = [];
    attEls.forEach(el => {
      const val = el.textContent ? el.textContent.trim() : '';
      if (val) attachments.push(val);
    });

    const rawEmail = {
      sender,
      display_name: displayName,
      reply_to: replyTo,
      subject,
      body,
      attachments
    };

    const validEmail = Core.validateEmail(rawEmail);
    if (!validEmail) return null;

    return {
      msgId,
      email: validEmail,
      readingEl
    };
  }

  function checkOpenMessage() {
    isExtensionActive((active) => {
      if (!active) {
        if (activePanel) {
          activePanel.remove();
          activePanel = null;
        }
        chrome.runtime.sendMessage({ type: 'CLEAR' });
        return;
      }

      const extracted = extractEmailFromDOM();
      if (!extracted) {
        if (activePanel) {
          activePanel.remove();
          activePanel = null;
        }
        currentMsgId = null;
        currentFingerprint = null;
        chrome.runtime.sendMessage({ type: 'CLEAR' });
        return;
      }

      const { msgId, email, readingEl } = extracted;
      const fp = Core.fingerprint(email);

      if (msgId === currentMsgId && fp === currentFingerprint && activePanel) {
        return; // Already verified this message
      }

      // If message ID changed, wipe old panel completely
      if (activePanel) {
        activePanel.remove();
        activePanel = null;
      }

      currentMsgId = msgId;
      currentFingerprint = fp;

      // Anchor element for mounting panel
      let anchor = readingEl.querySelector(site.selectors.anchor);
      if (!anchor) {
        anchor = readingEl.firstElementChild;
      }

      activePanel = new Panel();
      activePanel.callbacks = {
        onDeepAnalysis: runDeepAnalysis,
        onRetry: triggerAnalysis
      };
      activePanel.mount(anchor);

      // Prioritize deep analysis if already performed for this message
      if (deepCache.has(msgId)) {
        activePanel.render(deepCache.get(msgId));
        return;
      }

      // Show cached automatic analysis if available
      if (automaticCache.has(msgId)) {
        activePanel.render(automaticCache.get(msgId));
        return;
      }

      triggerAnalysis();
    });
  }

  function triggerAnalysis() {
    const current = extractEmailFromDOM();
    if (!current) return;
    const { msgId, email } = current;
    const reqId = ++currentRequestId;

    chrome.runtime.sendMessage({ type: 'ANALYZE', email }, (response) => {
      if (reqId !== currentRequestId) return; // Discard stale response

      // STRICT IDENTITY CHECK: Ensure user is still looking at the exact same message
      const latest = extractEmailFromDOM();
      if (!latest || latest.msgId !== msgId) return;

      if (!response || !response.ok) {
        if (activePanel) {
          activePanel.showError(response ? response.code : 'NETWORK');
        }
        return;
      }

      const sanitized = Core.sanitizeResponse(response.data);
      if (!sanitized) {
        if (activePanel) activePanel.showError('INVALID');
        return;
      }

      automaticCache.set(msgId, sanitized);
      if (activePanel) {
        activePanel.render(sanitized);
      }
    });
  }

  function runDeepAnalysis() {
    const current = extractEmailFromDOM();
    if (!current) return;
    const { msgId, email } = current;
    const reqId = ++currentRequestId;

    chrome.runtime.sendMessage({ type: 'DEEP_ANALYSIS', email }, (response) => {
      if (reqId !== currentRequestId) return; // Stale

      // STRICT IDENTITY CHECK: Ensure user is still looking at the exact same message
      const latest = extractEmailFromDOM();
      if (!latest || latest.msgId !== msgId) return;

      if (!response || !response.ok) {
        if (activePanel) {
          activePanel.showError(response ? response.code : 'NETWORK');
        }
        return;
      }

      const sanitized = Core.sanitizeResponse(response.data);
      if (!sanitized) {
        if (activePanel) activePanel.showError('INVALID');
        return;
      }

      deepCache.set(msgId, sanitized);
      if (activePanel) {
        activePanel.render(sanitized);
      }
    });
  }

  // MutationObserver with 300ms debounce
  const observer = new MutationObserver(() => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(checkOpenMessage, 300);
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-msg-id', 'data-msg-reading']
  });

  // Listen to storage changes (e.g. extension toggled active/inactive from popup)
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && changes.active) {
        checkOpenMessage();
      }
    });
  }

  // Initial check once document is ready
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    checkOpenMessage();
  } else {
    document.addEventListener('DOMContentLoaded', checkOpenMessage);
  }
})();
