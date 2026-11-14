// Assigned to a global variable of the content script isolated world.
globalThis.SITES = [
  {
    id: "test-webmail",
    origins: ["http://127.0.0.1:8000", "http://localhost:8000"],
    selectors: {
      reading: "[data-msg-reading]",
      sender: '[data-field="sender"]',
      displayName: '[data-field="display-name"]',
      replyTo: '[data-field="reply-to"]',
      subject: '[data-field="subject"]',
      body: '[data-field="body"]',
      attachment: '[data-field="attachment"]',
      anchor: '[data-anchor="notices"]'
    }
  }
];
