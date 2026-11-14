/**
 * Logic for extension popup window.
 */

(function () {
  'use strict';

  const Core = globalThis.MailCoastGuardCore;

  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const toggleActive = document.getElementById('toggle-active');
  const backendUrlInput = document.getElementById('backend-url');
  const btnSaveUrl = document.getElementById('btn-save-url');
  const urlFeedback = document.getElementById('url-feedback');

  function checkServiceStatus() {
    chrome.runtime.sendMessage({ type: 'STATUS' }, (res) => {
      if (res && res.ok) {
        statusDot.className = 'status-dot online';
        statusText.textContent = 'Conectado';
      } else {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'Sin conexión con el servicio';
      }
    });
  }

  function loadSettings() {
    chrome.storage.local.get({
      active: true,
      backendUrl: 'http://127.0.0.1:8000'
    }, (items) => {
      toggleActive.checked = items.active;
      backendUrlInput.value = items.backendUrl;
    });
  }

  function saveActiveToggle() {
    const isActive = toggleActive.checked;
    chrome.storage.local.set({ active: isActive });
  }

  function saveBackendUrl() {
    const rawVal = backendUrlInput.value.trim();
    if (!Core.validateBackendUrl(rawVal)) {
      urlFeedback.className = 'msg-feedback error';
      urlFeedback.textContent = 'Use una dirección local o de la red interna.';
      return;
    }

    const cleanUrl = rawVal.replace(/\/+$/, '');
    const origin = new URL(cleanUrl).origin;

    // Check optional permissions if needed
    if (chrome.permissions) {
      chrome.permissions.contains({ origins: [origin + '/*'] }, (hasPerm) => {
        if (hasPerm) {
          commitUrl(cleanUrl);
        } else {
          chrome.permissions.request({ origins: [origin + '/*'] }, (granted) => {
            if (granted) {
              commitUrl(cleanUrl);
            } else {
              urlFeedback.className = 'msg-feedback error';
              urlFeedback.textContent = 'Permiso denegado por el usuario.';
            }
          });
        }
      });
    } else {
      commitUrl(cleanUrl);
    }
  }

  function commitUrl(url) {
    chrome.storage.local.set({ backendUrl: url }, () => {
      urlFeedback.className = 'msg-feedback success';
      urlFeedback.textContent = 'Guardado correctamente.';
      checkServiceStatus();
      setTimeout(() => {
        urlFeedback.textContent = '';
      }, 3000);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    checkServiceStatus();

    toggleActive.addEventListener('change', saveActiveToggle);
    btnSaveUrl.addEventListener('click', saveBackendUrl);
  });
})();
