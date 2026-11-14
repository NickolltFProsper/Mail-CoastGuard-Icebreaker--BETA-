/**
 * Mail CoastGuard — Core validation and pure functions
 * Browser extension utility module.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.MailCoastGuardCore = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const LEVEL_RANKS = {
    GREEN: 1,
    YELLOW: 2,
    RED: 3,
    BLACK: 4
  };

  const LEVEL_CONFIG = {
    BLACK: {
      code: 'BLACK',
      badgeText: 'NEG',
      badgeColor: '#111111',
      labelText: 'NEGRO · ADJUNTO PELIGROSO',
      labelColor: '#111111',
      textColor: '#FFFFFF',
      bgColor: '#ECECEC',
      borderColor: '#111111',
      message: 'Adjunto peligroso: no lo abra.'
    },
    RED: {
      code: 'RED',
      badgeText: 'ROJ',
      badgeColor: '#D32F2F',
      labelText: 'ROJO · POSIBLE PHISHING',
      labelColor: '#D32F2F',
      textColor: '#FFFFFF',
      bgColor: '#FDECEA',
      borderColor: '#D32F2F',
      message: 'Posible phishing: no haga clic ni responda.'
    },
    YELLOW: {
      code: 'YELLOW',
      badgeText: 'AMA',
      badgeColor: '#F9A825',
      labelText: 'AMARILLO · REVISE CON CUIDADO',
      labelColor: '#F9A825',
      textColor: '#1F2937',
      bgColor: '#FFF8E1',
      borderColor: '#F9A825',
      message: 'Revise con cuidado antes de actuar.'
    },
    GREEN: {
      code: 'GREEN',
      badgeText: 'VER',
      badgeColor: '#2E7D32',
      labelText: 'VERDE · SIN INDICIOS DETECTADOS',
      labelColor: '#2E7D32',
      textColor: '#FFFFFF',
      bgColor: '#E8F5E9',
      borderColor: '#2E7D32',
      message: 'Sin indicios detectados. Esto no garantiza que el correo sea seguro.'
    }
  };

  function stripControlChars(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/[\x00-\x1F\x7F]/g, '');
  }

  function validateEmail(obj) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
      return null;
    }

    if (typeof obj.sender !== 'string') {
      return null;
    }

    const cleanSender = obj.sender.slice(0, 320);
    const cleanDisplayName = typeof obj.display_name === 'string' ? obj.display_name.slice(0, 200) : '';
    const cleanReplyTo = typeof obj.reply_to === 'string' ? obj.reply_to.slice(0, 320) : '';
    const cleanSubject = typeof obj.subject === 'string' ? obj.subject.slice(0, 500) : '';
    const cleanBody = typeof obj.body === 'string' ? obj.body.slice(0, 50000) : '';

    const cleanAttachments = [];
    if (Array.isArray(obj.attachments)) {
      for (const item of obj.attachments.slice(0, 50)) {
        if (typeof item === 'string') {
          cleanAttachments.push(item.slice(0, 255));
        }
      }
    }

    return {
      sender: cleanSender,
      display_name: cleanDisplayName,
      reply_to: cleanReplyTo,
      subject: cleanSubject,
      body: cleanBody,
      attachments: cleanAttachments
    };
  }

  function isPrivateIpv4(ip) {
    const parts = ip.split('.').map(Number);
    if (parts.length !== 4 || parts.some(isNaN) || parts.some(p => p < 0 || p > 255)) {
      return false;
    }
    // 10.0.0.0/8
    if (parts[0] === 10) return true;
    // 172.16.0.0/12
    if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
    // 192.168.0.0/16
    if (parts[0] === 192 && parts[1] === 168) return true;
    // Loopback 127.0.0.0/8
    if (parts[0] === 127) return true;

    return false;
  }

  function validateBackendUrl(text) {
    if (typeof text !== 'string') return false;
    const trimmed = text.trim();
    if (!trimmed) return false;

    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return false;
      }
      if (parsed.username || parsed.password) {
        return false;
      }
      if (parsed.pathname && parsed.pathname !== '/') {
        return false;
      }
      if (parsed.search || parsed.hash) {
        return false;
      }

      const host = parsed.hostname.toLowerCase();
      if (host === 'localhost' || host === '127.0.0.1') {
        return true;
      }

      // Check if host is IPv4
      if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host)) {
        return isPrivateIpv4(host);
      }

      // Domain names and public addresses are rejected
      return false;
    } catch (_) {
      return false;
    }
  }

  function sanitizeResponse(json) {
    if (!json || typeof json !== 'object' || Array.isArray(json)) {
      return null;
    }

    const validLevels = ['GREEN', 'YELLOW', 'RED', 'BLACK'];
    if (!validLevels.includes(json.final_level)) {
      return null;
    }

    if (!Array.isArray(json.layers)) {
      return null;
    }

    const sanitizedLayers = [];
    for (const layer of json.layers) {
      if (!layer || typeof layer !== 'object') return null;
      if (typeof layer.name !== 'string' || !validLevels.includes(layer.level)) {
        return null;
      }
      if (!Array.isArray(layer.reasons)) {
        return null;
      }

      const cleanReasons = [];
      for (const r of layer.reasons) {
        if (typeof r === 'string') {
          cleanReasons.push(stripControlChars(r).slice(0, 500));
        }
      }

      sanitizedLayers.push({
        name: stripControlChars(layer.name).slice(0, 50),
        level: layer.level,
        reasons: cleanReasons,
        score: typeof layer.score === 'number' ? layer.score : null
      });
    }

    let sanitizedLayer3 = null;
    if (json.layer3 && typeof json.layer3 === 'object') {
      const l3 = json.layer3;
      const validVerdicts = ['phishing', 'suspicious', 'no_indicators'];
      if (!validVerdicts.includes(l3.verdict) || !['RED', 'YELLOW', 'GREEN'].includes(l3.level)) {
        return null;
      }
      if (!Array.isArray(l3.reasons)) {
        return null;
      }
      const l3Reasons = [];
      for (const r of l3.reasons) {
        if (typeof r === 'string') {
          l3Reasons.push(stripControlChars(r).slice(0, 500));
        }
      }
      sanitizedLayer3 = {
        verdict: l3.verdict,
        level: l3.level,
        reasons: l3Reasons,
        confidence: typeof l3.confidence === 'number' ? Math.max(0, Math.min(1, l3.confidence)) : 0
      };
    }

    return {
      status: json.status === 'unavailable' ? 'unavailable' : 'ok',
      notice: typeof json.notice === 'string' ? stripControlChars(json.notice).slice(0, 500) : null,
      final_level: json.final_level,
      message: typeof json.message === 'string' ? stripControlChars(json.message).slice(0, 500) : '',
      layers: sanitizedLayers,
      layer3: sanitizedLayer3
    };
  }

  function fingerprint(email) {
    if (!email) return '';
    const atts = Array.isArray(email.attachments) ? email.attachments.join(',') : '';
    const raw = [
      email.sender || '',
      email.display_name || '',
      email.reply_to || '',
      email.subject || '',
      email.body || '',
      atts
    ].join('|||');

    let hash = 0;
    for (let i = 0; i < raw.length; i++) {
      const char = raw.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash |= 0;
    }
    return String(hash);
  }

  function levelBadge(level) {
    return LEVEL_CONFIG[level] || LEVEL_CONFIG.GREEN;
  }

  function maxLevel(a, b) {
    const rankA = LEVEL_RANKS[a] || 0;
    const rankB = LEVEL_RANKS[b] || 0;
    return rankA >= rankB ? a : b;
  }

  return {
    validateEmail,
    validateBackendUrl,
    sanitizeResponse,
    fingerprint,
    levelBadge,
    maxLevel,
    LEVEL_CONFIG,
    LEVEL_RANKS
  };
});
