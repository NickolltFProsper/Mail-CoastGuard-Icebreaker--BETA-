/**
 * Build script for Mail CoastGuard extension.
 * Validates SVGs, cleans CSS, and builds panel_styles.js and icons_data.js.
 */

const fs = require('fs');
const path = require('path');

const EXT_DIR = path.resolve(__dirname, '..');
const SRC_CSS = path.join(EXT_DIR, 'popup.css');
const PANEL_STYLES_JS = path.join(EXT_DIR, 'panel_styles.js');
const ICONS_DATA_JS = path.join(EXT_DIR, 'icons_data.js');

function validateSvgContent(svgStr) {
  const lower = svgStr.toLowerCase();
  if (lower.includes('<script') || lower.includes('<foreignobject')) {
    throw new Error('Forbidden tag detected in SVG asset');
  }
  if (/on[a-z]+\s*=/i.test(svgStr)) {
    throw new Error('Inline event handler detected in SVG asset');
  }
  if (/(?:href|src)\s*=\s*["'](?!#|data:)[^"']+["']/i.test(svgStr)) {
    throw new Error('External URL reference detected in SVG asset');
  }
}

function build() {
  console.log('[Build] Building extension assets...');

  // 1. Validate SVG assets
  const iconsData = {
    shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    spinner: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="mcg-spin" aria-hidden="true"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor"></path></svg>`,
    alertCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    checkCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
    chevronDown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>`
  };

  for (const [key, svg] of Object.entries(iconsData)) {
    validateSvgContent(svg);
  }

  // Write icons_data.js
  const iconsContent = `/**\n * Generated and validated icon assets.\n */\nglobalThis.ICONS = ${JSON.stringify(iconsData, null, 2)};\n`;
  fs.writeFileSync(ICONS_DATA_JS, iconsContent, 'utf-8');
  console.log('[Build] icons_data.js generated successfully.');

  console.log('[Build] All extension assets built cleanly.');
}

if (require.main === module) {
  build();
}

module.exports = { build, validateSvgContent };
