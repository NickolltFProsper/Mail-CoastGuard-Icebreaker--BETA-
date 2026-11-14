/**
 * Verification panel component for Mail CoastGuard.
 * Mounts in a closed Shadow DOM to enforce total isolation from page styles/scripts.
 */

(function (root) {
  'use strict';

  const Core = root.MailCoastGuardCore;

  class VerificationPanel {
    constructor(callbacks = {}) {
      this.callbacks = callbacks; // onDeepAnalysis, onRetry
      this.hostEl = null;
      this.shadowRoot = null;
      this.loadingTimer = null;
      this.currentState = null;
    }

    createSvgNode(svgString) {
      try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(svgString, 'image/svg+xml');
        return document.importNode(doc.documentElement, true);
      } catch (_) {
        const fallback = document.createElement('span');
        return fallback;
      }
    }

    mount(anchorElement) {
      if (this.hostEl && this.hostEl.parentNode) {
        this.hostEl.parentNode.removeChild(this.hostEl);
      }

      // Purge any existing elements in anchorElement to prevent duplicate/stale panels
      if (anchorElement) {
        while (anchorElement.firstChild) {
          anchorElement.removeChild(anchorElement.firstChild);
        }
      }

      this.hostEl = document.createElement('div');
      this.hostEl.className = 'mcg-host-container';
      this.shadowRoot = this.hostEl.attachShadow({ mode: 'closed' });

      // Adopt compiled styles
      try {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(globalThis.PANEL_CSS || '');
        this.shadowRoot.adoptedStyleSheets = [sheet];
      } catch (_) {
        // Fallback for older browsers
        const style = document.createElement('style');
        style.textContent = globalThis.PANEL_CSS || '';
        this.shadowRoot.appendChild(style);
      }

      anchorElement.appendChild(this.hostEl);
    }

    render(data) {
      if (!this.shadowRoot) return;
      this.currentState = data;
      this.clearLoadingTimer();

      // Clean shadow contents (keeping adoptedStyleSheets)
      while (this.shadowRoot.firstChild) {
        this.shadowRoot.removeChild(this.shadowRoot.firstChild);
      }

      const level = data.final_level || 'GREEN';
      const config = Core.levelBadge(level);
      const isComplete = Boolean(data.layer3);

      const panel = document.createElement('div');
      panel.className = `mcg-panel mcg-level-${level}`;

      // 1. Header
      const header = document.createElement('div');
      header.className = 'mcg-header';

      const titleGroup = document.createElement('div');
      titleGroup.className = 'mcg-title-group';

      const mainTitle = document.createElement('span');
      mainTitle.className = 'mcg-main-title';
      mainTitle.textContent = 'Verificación de seguridad del mensaje';
      titleGroup.appendChild(mainTitle);

      const tag = document.createElement('span');
      tag.className = 'mcg-tag';
      tag.textContent = isComplete ? 'Verificación completa' : 'Verificación automática';
      titleGroup.appendChild(tag);
      header.appendChild(titleGroup);

      // Deep analysis button
      const btnDeep = document.createElement('button');
      btnDeep.type = 'button';
      btnDeep.className = 'mcg-btn-deep';
      btnDeep.setAttribute('aria-label', 'Análisis profundo del mensaje');

      const btnIcon = document.createElement('span');
      btnIcon.className = 'mcg-btn-icon';
      btnIcon.appendChild(this.createSvgNode(globalThis.ICONS.shield));
      btnDeep.appendChild(btnIcon);

      const btnText = document.createElement('span');
      btnText.className = 'mcg-btn-text';

      if (isComplete) {
        btnText.textContent = 'Análisis completado';
        btnDeep.disabled = true;
      } else if (data.status === 'unavailable') {
        btnText.textContent = 'Reintentar análisis';
        btnDeep.disabled = false;
        btnDeep.addEventListener('click', () => {
          if (this.callbacks.onDeepAnalysis) {
            this.setLoadingState(btnDeep, btnText, btnIcon);
            this.callbacks.onDeepAnalysis();
          }
        });
      } else {
        btnText.textContent = 'Análisis profundo';
        btnDeep.addEventListener('click', () => {
          if (this.callbacks.onDeepAnalysis) {
            this.setLoadingState(btnDeep, btnText, btnIcon);
            this.callbacks.onDeepAnalysis();
          }
        });
      }
      btnDeep.appendChild(btnText);
      header.appendChild(btnDeep);
      panel.appendChild(header);

      // 2. Verdict line (Badge + Message)
      const verdictLine = document.createElement('div');
      verdictLine.className = 'mcg-verdict-line';

      const badge = document.createElement('span');
      badge.className = 'mcg-badge';
      badge.style.backgroundColor = config.labelColor;
      badge.style.color = config.textColor;
      badge.textContent = config.labelText;
      verdictLine.appendChild(badge);

      const message = document.createElement('span');
      message.className = 'mcg-message';
      message.textContent = data.message || config.message;
      verdictLine.appendChild(message);
      panel.appendChild(verdictLine);

      // 3. Reasons grouped by layer
      const reasonsBlock = document.createElement('div');
      reasonsBlock.className = 'mcg-reasons-block';
      let hasAnyReasons = false;

      // Layer 1
      const layer1 = data.layers ? data.layers.find(l => l.name === 'layer1') : null;
      if (layer1 && layer1.reasons && layer1.reasons.length > 0) {
        hasAnyReasons = true;
        reasonsBlock.appendChild(this.createLayerSection('Remitente y adjuntos', layer1.reasons));
      }

      // Layer 2
      const layer2 = data.layers ? data.layers.find(l => l.name === 'layer2') : null;
      if (layer2 && layer2.reasons && layer2.reasons.length > 0) {
        hasAnyReasons = true;
        reasonsBlock.appendChild(this.createLayerSection('Contenido', layer2.reasons));
      }

      // Layer 3
      if (data.layer3 && data.layer3.reasons && data.layer3.reasons.length > 0) {
        hasAnyReasons = true;
        const confPercent = Math.round((data.layer3.confidence || 0) * 100);
        const l3Title = `Análisis profundo`;
        reasonsBlock.appendChild(this.createLayerSection(l3Title, data.layer3.reasons));
      }

      if (hasAnyReasons) {
        panel.appendChild(reasonsBlock);
      }

      // Notice banner (if AI was unavailable)
      if (data.status === 'unavailable' && data.notice) {
        const noticeBanner = document.createElement('div');
        noticeBanner.className = 'mcg-notice-banner';
        noticeBanner.textContent = data.notice;
        panel.appendChild(noticeBanner);
      }

      this.shadowRoot.appendChild(panel);
    }

    createLayerSection(titleText, reasons) {
      const section = document.createElement('div');
      section.className = 'mcg-layer-section';

      const title = document.createElement('span');
      title.className = 'mcg-layer-title';
      title.textContent = titleText;
      section.appendChild(title);

      const ul = document.createElement('ul');
      ul.className = 'mcg-reasons-list';
      reasons.forEach(r => {
        const li = document.createElement('li');
        li.className = 'mcg-reason-item';
        li.textContent = r;
        ul.appendChild(li);
      });
      section.appendChild(ul);
      return section;
    }

    setLoadingState(btn, textEl, iconEl) {
      btn.disabled = true;
      iconEl.innerHTML = '';
      iconEl.appendChild(this.createSvgNode(globalThis.ICONS.spinner));
      textEl.textContent = 'Analizando…';

      this.loadingTimer = setTimeout(() => {
        textEl.textContent = 'Analizando… puede tardar un poco más';
      }, 8000);
    }

    clearLoadingTimer() {
      if (this.loadingTimer) {
        clearTimeout(this.loadingTimer);
        this.loadingTimer = null;
      }
    }

    showError(errorCode) {
      this.clearLoadingTimer();
      if (!this.shadowRoot) return;

      const errorMessages = {
        NETWORK: 'No se pudo contactar con el servicio de verificación.',
        TIMEOUT: 'La verificación tardó demasiado. Intente de nuevo.',
        '422': 'Los datos del mensaje no son válidos.',
        '413': 'El mensaje es demasiado grande.',
        '429': 'Demasiadas solicitudes. Espere unos segundos e intente de nuevo.',
        INVALID: 'No se pudo completar la verificación.',
        OTHER: 'No se pudo completar la verificación.'
      };

      const msg = errorMessages[errorCode] || errorMessages.OTHER;

      // Find existing error banner or create one
      let banner = this.shadowRoot.querySelector('.mcg-error-banner');
      if (!banner) {
        banner = document.createElement('div');
        banner.className = 'mcg-error-banner';
        const panel = this.shadowRoot.querySelector('.mcg-panel');
        if (panel) panel.appendChild(banner);
      }

      banner.innerHTML = '';
      const textSpan = document.createElement('span');
      textSpan.textContent = msg;
      banner.appendChild(textSpan);

      const btnRetry = document.createElement('button');
      btnRetry.type = 'button';
      btnRetry.className = 'mcg-btn-retry';
      btnRetry.textContent = 'Reintentar análisis';
      btnRetry.addEventListener('click', () => {
        if (this.callbacks.onRetry) {
          this.callbacks.onRetry();
        }
      });
      banner.appendChild(btnRetry);
    }

    remove() {
      this.clearLoadingTimer();
      if (this.hostEl && this.hostEl.parentNode) {
        this.hostEl.parentNode.removeChild(this.hostEl);
      }
      this.hostEl = null;
      this.shadowRoot = null;
    }
  }

  root.MailCoastGuardPanel = VerificationPanel;
})(typeof globalThis !== 'undefined' ? globalThis : this);
