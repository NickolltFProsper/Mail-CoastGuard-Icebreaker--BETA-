/**
 * Static security checks for browser extension code and manifest.
 * Run with: node --test extension/tests/static_checks.test.js
 */

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const EXT_DIR = path.resolve(__dirname, '..');

test('X-01: manifest.json is MV3, minimal permissions and all icons exist', () => {
  const manifestPath = path.join(EXT_DIR, 'manifest.json');
  assert.ok(fs.existsSync(manifestPath), 'manifest.json must exist');

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  assert.strictEqual(manifest.manifest_version, 3, 'Must be MV3');
  assert.deepStrictEqual(manifest.permissions, ['storage'], 'Must declare only storage');
  assert.strictEqual(manifest.web_accessible_resources, undefined, 'No web_accessible_resources allowed');

  // Verify all icon files declared exist on disk
  const iconPaths = [
    ...Object.values(manifest.icons || {}),
    ...Object.values(manifest.action.default_icon || {})
  ];

  for (const relPath of iconPaths) {
    const fullPath = path.join(EXT_DIR, relPath);
    assert.ok(fs.existsSync(fullPath), `Icon file ${relPath} must exist on disk`);
  }
});

test('X-02: forbidden APIs and external origins check in extension files', () => {
  const filesToCheck = [
    'core.js',
    'background.js',
    'content.js',
    'panel.js',
    'popup.js',
    'popup.html'
  ];

  const forbiddenTerms = [
    'innerHTML',
    'outerHTML',
    'insertAdjacentHTML',
    'eval(',
    'new Function',
    'document.write',
    'localStorage'
  ];

  for (const file of filesToCheck) {
    const filePath = path.join(EXT_DIR, file);
    if (!fs.existsSync(filePath)) continue;

    const content = fs.readFileSync(filePath, 'utf-8');
    for (const term of forbiddenTerms) {
      assert.ok(
        !content.includes(term),
        `Forbidden term "${term}" found in ${file}`
      );
    }
  }
});
