/**
 * Unit tests for extension core pure functions.
 * Run with: node --test extension/tests/core.test.js
 */

const test = require('node:test');
const assert = require('node:assert');
const Core = require('../core.js');

test('X-03: validateEmail retains only 6 fields and enforces length limits', () => {
  const input = {
    sender: 'user@uneti.edu.ve',
    display_name: 'Test User',
    reply_to: 'reply@uneti.edu.ve',
    subject: 'Important Subject',
    body: 'A'.repeat(60000), // Exceeds 50,000 limit
    attachments: ['file1.pdf', 'file2.exe', 12345],
    extra_field: 'malicious_injection'
  };

  const validated = Core.validateEmail(input);
  assert.ok(validated);
  assert.strictEqual(validated.sender, 'user@uneti.edu.ve');
  assert.strictEqual(validated.display_name, 'Test User');
  assert.strictEqual(validated.reply_to, 'reply@uneti.edu.ve');
  assert.strictEqual(validated.subject, 'Important Subject');
  assert.strictEqual(validated.body.length, 50000);
  assert.deepStrictEqual(validated.attachments, ['file1.pdf', 'file2.exe']);
  assert.strictEqual(validated.extra_field, undefined);

  // Reject invalid non-object or missing sender
  assert.strictEqual(Core.validateEmail(null), null);
  assert.strictEqual(Core.validateEmail('string'), null);
  assert.strictEqual(Core.validateEmail({ sender: 1234 }), null);
});

test('X-04: validateBackendUrl accepts local/private IPv4 and rejects external/public/malformed', () => {
  // Allowed
  assert.strictEqual(Core.validateBackendUrl('http://127.0.0.1:8000'), true);
  assert.strictEqual(Core.validateBackendUrl('http://localhost:8000'), true);
  assert.strictEqual(Core.validateBackendUrl('http://192.168.1.20:11434'), true);
  assert.strictEqual(Core.validateBackendUrl('http://10.0.0.5'), true);
  assert.strictEqual(Core.validateBackendUrl('http://172.16.5.1:8000'), true);

  // Rejected
  assert.strictEqual(Core.validateBackendUrl('https://ejemplo.com'), false);
  assert.strictEqual(Core.validateBackendUrl('http://8.8.8.8'), false);
  assert.strictEqual(Core.validateBackendUrl('http://user:pass@127.0.0.1:8000'), false);
  assert.strictEqual(Core.validateBackendUrl('http://127.0.0.1:8000/api/extra'), false);
  assert.strictEqual(Core.validateBackendUrl('file:///etc/passwd'), false);
  assert.strictEqual(Core.validateBackendUrl(''), false);
  assert.strictEqual(Core.validateBackendUrl(null), false);
});

test('X-05: sanitizeResponse cleans and enforces schema on backend responses', () => {
  const rawResponse = {
    final_level: 'RED',
    message: 'Posible phishing: \x00no haga clic.\x1F',
    layers: [
      {
        name: 'layer1\x00',
        level: 'RED',
        reasons: ['Subdominio \x07engañoso.', 'A'.repeat(600)],
        score: null
      }
    ],
    layer3: {
      verdict: 'phishing',
      level: 'RED',
      reasons: ['Razón \x00limpia'],
      confidence: 0.95
    }
  };

  const sanitized = Core.sanitizeResponse(rawResponse);
  assert.ok(sanitized);
  assert.strictEqual(sanitized.final_level, 'RED');
  assert.strictEqual(sanitized.message, 'Posible phishing: no haga clic.');
  assert.strictEqual(sanitized.layers[0].reasons[0], 'Subdominio engañoso.');
  assert.strictEqual(sanitized.layers[0].reasons[1].length, 500);
  assert.strictEqual(sanitized.layer3.verdict, 'phishing');
  assert.strictEqual(sanitized.layer3.confidence, 0.95);

  // Rejects invalid levels or broken formats
  assert.strictEqual(Core.sanitizeResponse({ final_level: 'UNKNOWN' }), null);
  assert.strictEqual(Core.sanitizeResponse(null), null);
  assert.strictEqual(Core.sanitizeResponse({ final_level: 'GREEN', layers: 'not_an_array' }), null);
});

test('Fingerprint and MaxLevel tests', () => {
  const email1 = { sender: 'a@b.com', body: 'test' };
  const email2 = { sender: 'a@b.com', body: 'test' };
  const email3 = { sender: 'c@d.com', body: 'different' };

  assert.strictEqual(Core.fingerprint(email1), Core.fingerprint(email2));
  assert.notStrictEqual(Core.fingerprint(email1), Core.fingerprint(email3));

  assert.strictEqual(Core.maxLevel('GREEN', 'YELLOW'), 'YELLOW');
  assert.strictEqual(Core.maxLevel('RED', 'YELLOW'), 'RED');
  assert.strictEqual(Core.maxLevel('RED', 'BLACK'), 'BLACK');
});
