/**
 * Compiled panel styles exposed to content script Shadow DOM.
 * Conforms to Tailwind CSS 3.4 design tokens and closed Shadow DOM isolation.
 */
globalThis.PANEL_CSS = `
:host {
  display: block;
  font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
  margin-bottom: 16px;
  box-sizing: border-box;
}

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

.mcg-panel {
  border-left-width: 6px;
  border-left-style: solid;
  border-radius: 8px;
  padding: 16px 20px;
  transition: all 0.2s ease-in-out;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

/* Severity Level Themes */
.mcg-level-BLACK {
  background-color: #ECECEC;
  border-left-color: #111111;
  color: #111111;
}

.mcg-level-RED {
  background-color: #FDECEA;
  border-left-color: #D32F2F;
  color: #7F1D1D;
}

.mcg-level-YELLOW {
  background-color: #FFF8E1;
  border-left-color: #F9A825;
  color: #78350F;
}

.mcg-level-GREEN {
  background-color: #E8F5E9;
  border-left-color: #2E7D32;
  color: #14532D;
}

/* Header Area */
.mcg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.mcg-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mcg-main-title {
  font-size: 15px;
  font-weight: 700;
  color: #1D2B5B;
  letter-spacing: -0.2px;
}

.mcg-tag {
  font-size: 11px;
  font-weight: 600;
  background-color: rgba(29, 43, 91, 0.1);
  color: #1D2B5B;
  padding: 2px 8px;
  border-radius: 12px;
  text-transform: uppercase;
}

/* Deep Analysis Button */
.mcg-btn-deep {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background-color: #5F5F5F;
  color: #FFFFFF;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 16px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  transition: background-color 0.15s ease, transform 0.05s ease;
  user-select: none;
}

.mcg-btn-deep:hover:not(:disabled) {
  background-color: #4A4A4A;
}

.mcg-btn-deep:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px #22A7B4;
}

.mcg-btn-deep:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.mcg-btn-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mcg-btn-icon svg {
  width: 100%;
  height: 100%;
}

/* Badge and Verdict Line */
.mcg-verdict-line {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.mcg-badge {
  font-size: 12px;
  font-weight: 800;
  padding: 4px 10px;
  border-radius: 6px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  display: inline-block;
}

.mcg-message {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

/* Reasons Container */
.mcg-reasons-block {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  padding-top: 10px;
}

.mcg-layer-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mcg-layer-title {
  font-size: 12px;
  font-weight: 700;
  color: #374151;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.mcg-reasons-list {
  list-style-type: disc;
  margin-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mcg-reason-item {
  font-size: 13px;
  line-height: 1.4;
  color: #1F2937;
}

/* Notices and Error Banners */
.mcg-notice-banner {
  background-color: #FEF3C7;
  color: #92400E;
  border: 1px solid #FCD34D;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mcg-error-banner {
  background-color: #FEE2E2;
  color: #991B1B;
  border: 1px solid #FCA5A5;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mcg-btn-retry {
  background: transparent;
  border: 1px solid #B91C1C;
  color: #B91C1C;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.mcg-btn-retry:hover {
  background: #B91C1C;
  color: #FFF;
}

/* Animations */
@keyframes mcg-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.mcg-spin {
  animation: mcg-spin 1s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .mcg-spin {
    animation: none;
  }
}
`;
