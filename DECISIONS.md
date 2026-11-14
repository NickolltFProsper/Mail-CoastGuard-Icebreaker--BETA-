# Mail CoastGuard — Architectural & Design Decisions (DECISIONS.md)

This document records architectural, design, and implementation decisions taken during development in accordance with `Specs.md` Section 0, `security.md`, `Specs_Web.md`, and `Specs_Extension.md`.

---

## 1. AI Models and Providers
- **Gemini Default Model (`GEMINI_MODEL`):** Set to `gemini-2.5-flash` (with backwards compatibility fallback to `gemini-1.5-flash` / `gemini-3-flash-preview`). `gemini-2.5-flash` is Google's current production flagship model for fast structured JSON responses.
- **DeepSeek Default Model (`DEEPSEEK_MODEL`):** Set to `deepseek-chat` with default config alias `deepseek-v4-flash`. The API endpoint is fixed at `https://api.deepseek.com/chat/completions`.
- **Ollama Default Model (`OLLAMA_MODEL`):** `llama3.1:8b` running locally at `http://localhost:11434` for sovereign air-gapped deployments. Anti-SSRF validation strictly enforces loopback (`127.0.0.1`, `localhost`) or RFC 1918 private IPv4 addresses.

## 2. Python and Dependency Versions
- Python target: 3.14 (compatible with 3.11+).
- Core dependencies in `requirements.txt`:
  - `fastapi==0.115.8`
  - `uvicorn[standard]==0.34.0`
  - `pydantic==2.10.6`
  - `google-genai==1.3.0`
  - `httpx==0.28.1`
  - `python-dotenv==1.0.1`
  - `pytest==8.3.4`
- Standard library usage for security components: `hashlib`, `hmac`, `secrets`, `ipaddress`, `unicodedata`, `os`, `json`, `re`.

## 3. Extension Icons Mapping (`iconos/` -> `extension/icons/`)
Icons provided in `Iconos/`:
- `apple-touch-icon.png` -> Used for `extension/icons/icon-128.png` and `extension/icons/icon-48.png`
- `favicon.ico` -> Multi-resolution icon source
- `icon-192.png` -> Main product icon and source for `extension/icons/icon-32.png` and `extension/icons/icon-16.png`
- `icon-512.png` -> High-resolution asset
- In the absence of a distinct standalone SVG shield file in `Iconos/`, an inline SVG shield symbol matching the institutional palette is bundled for the Deep Analysis button in `icons_data.js`.

## 4. UI Design Tokens and Palette
Tokens derived from `Referencias/paleta de colores de la interfaz .png` and `Specs_Web.md`:
- Institutional Navy: `#1D2B5B`
- Accent Turquoise: `#22A7B4`
- Primary Action Orange: `#F15A24`
- Amber / Yellow: `#FBB827`
- Institutional Purple: `#5E2D79`
- Institutional Green: `#3FA535`
- Background: `#F4F6FA`
- Card Surfaces: `#FFFFFF`
- Border: `#E1E5EE`
- Text Primary: `#1F2937`
- Text Secondary: `#6B7280`

Badge and Level Colors (defined in `Specs_Extension.md` Section 9.4):
- `BLACK`: `#111111` / background `#ECECEC`
- `RED`: `#D32F2F` / background `#FDECEA`
- `YELLOW`: `#F9A825` / background `#FFF8E1`
- `GREEN`: `#2E7D32` / background `#E8F5E9`

## 5. Security & Isolation Architecture
- The frontend (`index.html`) is strictly isolated from verification logic. It communicates zero data to backend verification endpoints and relies purely on DOM attributes conforming to Section 7 contract.
- The browser extension mounts within a closed Shadow DOM (`attachShadow({mode: 'closed'})`) to completely prevent web page or malicious email styles/scripts from tampering with the security panel.
- All dynamic insertions use `textContent` exclusively; `innerHTML`, `eval`, and unsafe DOM manipulations are strictly forbidden.
- Admin API is disabled by default (`ADMIN_API_ENABLED=false`) and enforces token comparison with constant-time `hmac.compare_digest` against `ADMIN_API_KEY_SHA256`.
