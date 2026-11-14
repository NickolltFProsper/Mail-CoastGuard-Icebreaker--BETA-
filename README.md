# Mail CoastGuard — Icebreaker Edition

> **Sistema inteligente de verificación de correos electrónicos institucionales y mitigación de amenazas de phishing y adjuntos peligrosos.**  
> Diseñado bajo arquitectura de tres capas, principios de soberanía tecnológica e interfaz de usuario asistida por extensión de navegador.

---

## 1. Descripción General

**Mail CoastGuard** es una solución de ciberseguridad desarrollada para instituciones públicas, orientada a proteger a los funcionarios frente a vectores de ataque basados en ingeniería social, suplantación de identidad (*phishing*) y distribución de malware a través de archivos adjuntos maliciosos.

A diferencia de un antivirus o filtro perimetral tradicional que bloquea correos de forma opaca:
- **CoastGuard es un verificador pedagógico y no intrusivo:** analiza el correo y presenta al funcionario un semáforo de riesgo con los motivos técnicos comprensibles en español.
- **El humano mantiene el control:** la decisión final de interacción siempre corresponde al usuario; el sistema no elimina ni altera mensajes.
- **Arquitectura Local-First:** el 100 % de los correos entrantes se audita localmente en microsegundos sin llamadas a la red.
- **La IA actúa con asimetría defensiva:** el modelo de lenguaje de última generación (Gemini, DeepSeek u Ollama local) solo puede **elevar** el nivel de sospecha, jamás disminuirlo.
- **Privacidad estricta y sin persistencia:** el servidor no almacena correos en disco ni en base de datos; los registros (*logs*) no contienen información personal identificable (PII) ni contenidos de mensajes.

---

## 2. Arquitectura del Sistema

El ecosistema de Mail CoastGuard está conformado por tres componentes desacoplados:

```
┌────────────────────────┐         DOM Reading         ┌───────────────────────────┐
│ Webmail Institucional  │ ──────────────────────────▶ │  Extensión de Navegador   │
│ (Frontend Simulado)    │ ◀────────────────────────── │  (Closed Shadow DOM)      │
└────────────────────────┘        Injected Panel       └─────────────┬─────────────┘
                                                             Message │ (Single Channel)
                                                                     ▼
                                                       ┌───────────────────────────┐
                                                       │  Service Worker           │
                                                       │  (Background isolated)    │
                                                       └─────────────┬─────────────┘
                                                                HTTP │ (Local / Private)
                                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             BACKEND DE VALIDACIÓN                                │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │ Capa 1: Validación Heurística de Remitente, Encabezados y Adjuntos       │   │
│   │ (Pura, sin red, Levenshtein, detección de homóglifos y extensiones)      │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │                                        │
│   ┌─────────────────────────────────────▼────────────────────────────────────┐   │
│   │ Capa 2: Puntuación de Contenido y Patrones de Phishing                   │   │
│   │ (Normalización NFKC, eliminación de caracteres invisibles y cirílicos)   │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │                                        │
│   ┌─────────────────────────────────────▼────────────────────────────────────┐   │
│   │ Capa 3: Análisis Profundo Asistido por Inteligencia Artificial           │   │
│   │ [Bajo Demanda] (Gemini Cloud | DeepSeek | Ollama Llama 3.1 8B Soberano)  │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │                                        │
│                                         ▼                                        │
│           Regla de Combinación: max(Capa 1, Capa 2, Capa 3)                      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Componentes Principales

1. **Capa 1 (Remitente, Encabezados y Adjuntos):**
   - Validación estricta de la dirección de correo (detección de direcciones manipuladas con múltiples `@` o caracteres especiales).
   - Identificación de dominios institucionales oficiales (`mincyt.gov.ve`, `uneti.edu.ve`), subdominios engañosos y dominios parecidos (*lookalike/typosquatting*) mediante distancia Levenshtein y variantes de sustitución confusa (`rn` $\to$ `m`, `vv` $\to$ `w`, etc.).
   - Análisis de encabezados (`display_name`, `reply_to`) contra suplantación institucional.
   - Detección de adjuntos ejecutables de alto riesgo (`.exe`, `.scr`, `.bat`, etc.), dobles extensiones encubiertas (`factura.pdf.exe`) y caracteres de inversión direccional bidireccional (BIDI U+202E).

2. **Capa 2 (Heurística de Contenido):**
   - Se ejecuta en **todos** los correos, sin importar que el remitente sea oficial (mitigación contra cuentas institucionales comprometidas).
   - Motor de normalización profunda: Unicode NFKC, eliminación de caracteres invisibles de ancho cero (U+200B a U+200F, U+FEFF), conversión de homóglifos cirílicos y griegos a alfabeto latino y remoción de tildes (NFD).
   - Puntuación acumulativa de frases extorsivas, peticiones de credenciales, amenazas y urgencia artificial.

3. **Capa 3 (Análisis Profundo con IA):**
   - Ejecución bajo demanda mediante adaptador polimórfico:
     - **Gemini (Cloud):** integración con SDK `google-genai` mediante esquema JSON forzado.
     - **DeepSeek (Cloud):** vía peticiones HTTP directas a su endpoint estándar con modo JSON estricto.
     - **Ollama (Soberano):** ejecución con modelo local `llama3.1:8b` (o `llama3.2:3b`), sin que ningún byte salga de la red de la institución.
     - **Mock:** analizador determinista para entornos de pruebas automatizadas y demostraciones sin conexión.
   - Blindaje contra inyección de instrucciones (*Prompt Injection*): el contenido del correo se delimita como datos no confiables y cualquier intento de ordenar a la IA que lo declare seguro eleva de inmediato el nivel de riesgo.

4. **Extensión de Navegador (Chromium Manifest V3):**
   - Interfaz visual basada en **Closed Shadow DOM**, asegurando que ningún estilo o script del webmail o de un correo malicioso pueda leer ni alterar el panel de seguridad.
   - Distintivo en el icono de la barra del navegador (*badge*) fuera del alcance del DOM de la página.
   - Canal de red unificado y aislado: exclusivamente el *service worker* tiene comunicación HTTP hacia el backend local.

5. **Webmail Institucional de Demostración (Frontend):**
   - Simulación realista del correo de la UNETI con bandeja de entrada, carpetas, lectura y simulador flotante de correos entrantes para pruebas en vivo.
   - Desacople absoluto: la página web no contiene lógica de verificación ni realiza peticiones a la API del motor; expone los datos según contrato DOM de la sección 7.

---

## 3. Semáforo de Riesgo y Mensajes al Funcionario

| Rango | Código | Significado | Mensaje Exacto al Usuario |
|:---:|:---:|:---|:---|
| **4** | `BLACK` | Adjunto de alto riesgo o ejecutable | `Adjunto peligroso: no lo abra.` |
| **3** | `RED` | Phishing o suplantación confirmada | `Posible phishing: no haga clic ni responda.` |
| **2** | `YELLOW` | Señales sospechosas / remitente externo | `Revise con cuidado antes de actuar.` |
| **1** | `GREEN` | Sin indicios detectados | `Sin indicios detectados. Esto no garantiza que el correo sea seguro.` |

> [!IMPORTANT]
> El estado `GREEN` **nunca** se presenta como «seguro» ni garantiza inmunidad. Todo hallazgo viene acompañado de los motivos que lo originaron.

---

## 4. Requisitos del Sistema

- **Sistema Operativo:** Windows 10/11, Linux (Debian, Ubuntu, RHEL, CentOS), macOS.
- **Python:** Versión **3.14** (totalmente compatible con Python 3.11+).
- **Navegador Web:** Google Chrome, Microsoft Edge o cualquier navegador Chromium 110+.
- **Servidor Ollama (Opcional, para Despliegue Soberano):** 
  - Con GPU (6-8 GB VRAM): latencia de 2 a 6 segundos por análisis.
  - Con CPU (16 GB RAM): latencia de 10 a 40 segundos por análisis.

---

## 5. Instalación y Configuración Paso a Paso

### 5.1. Clonación o Preparación del Workspace
```bash
git clone <url-del-repositorio>
cd "Mail CoastGuard Icebreaker (BETA)"
```

### 5.2. Creación del Entorno Virtual de Python
En Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

En Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5.3. Instalación de Dependencias
```bash
pip install -r requirements.txt
```

Las dependencias fijadas en `requirements.txt` corresponden a las versiones oficiales estables:
- `fastapi==0.115.8`
- `uvicorn[standard]==0.34.0`
- `pydantic==2.10.6`
- `google-genai==1.3.0`
- `httpx==0.28.1`
- `python-dotenv==1.0.1`
- `pytest==8.3.4`

### 5.4. Configuración del Archivo de Entorno (`.env`)
Copie la plantilla de variables de entorno:
```bash
cp .env.example .env
```

Edite `.env` según el proveedor de IA deseado:

```ini
# Proveedor: gemini | deepseek | ollama | mock
AI_PROVIDER=gemini

# Si utiliza Gemini (nube):
GEMINI_API_KEY=tu_clave_de_api_gemini
GEMINI_MODEL=gemini-2.5-flash

# Si utiliza DeepSeek (nube):
DEEPSEEK_API_KEY=tu_clave_de_api_deepseek
DEEPSEEK_MODEL=deepseek-chat

# Si utiliza Ollama local (soberano sin conexión a internet):
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# Parámetros del servidor HTTP
APP_HOST=127.0.0.1
APP_PORT=8000
AI_TIMEOUT_SECONDS=60
AI_MAX_CONCURRENT=1
```

> [!WARNING]
> **Aviso de Privacidad (Proveedores Cloud):** Gemini y DeepSeek son servicios en la nube. Durante fases de prueba o hackathon utilice **únicamente correos sintéticos**. Para despliegues en producción institucional con datos reales, active **Ollama** (`AI_PROVIDER=ollama`) para garantizar soberanía absoluta y cero fuga de datos.

---

## 6. Puesta en Marcha y Ejecución

### 6.1. Iniciar el Backend
Inicie el servidor Uvicorn en modo seguro:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-server-header --reload
```

El servidor quedará disponible en `http://127.0.0.1:8000`:
- **Webmail Simulado (Frontend):** `http://127.0.0.1:8000/`
- **Comprobación de Estado:** `http://127.0.0.1:8000/health`
- **API de Verificación:** `POST http://127.0.0.1:8000/analyze`
- **API de Análisis Profundo:** `POST http://127.0.0.1:8000/deep-analysis`

### 6.2. Cargar la Extensión de Navegador
1. Abra su navegador Chromium (Google Chrome o Microsoft Edge).
2. Diríjase a la URL `chrome://extensions` o `edge://extensions`.
3. Active el interruptor **«Modo de desarrollador»** (esquina superior derecha).
4. Haga clic en el botón **«Cargar descomprimida»** (*Load unpacked*).
5. Seleccione la carpeta `extension/` ubicada dentro del workspace del proyecto.
6. La extensión **Mail CoastGuard** quedará instalada y visible en su barra de extensiones.

### 6.3. Uso de la Aplicación
1. Acceda a `http://127.0.0.1:8000/` en el navegador donde instaló la extensión.
2. Seleccione cualquiera de los 5 correos precargados en la bandeja de entrada para observar cómo la extensión monta automáticamente el panel de verificación dentro del Shadow DOM y asigna el distintivo (*badge*) en la barra superior.
3. Haga clic en **«Análisis profundo»** para consultar la Capa 3 y obtener la explicación detallada de la IA con porcentaje de confianza.
4. Para probar ataques personalizados o nuevos vectores, haga clic en el botón naranja **«Simular correo»**:
   - Rellene el remitente, asunto, mensaje y adjuntos ficticios (o elija una plantilla de los ejemplos rápidos).
   - Presione **«Recibir en bandeja»**: el correo se inyectará instantáneamente y la extensión lo auditará en vivo.

---

## 7. Despliegue Soberano con Ollama (Local y Aislado)

Para instituciones que requieren cumplimiento de leyes de protección de datos y soberanía tecnológica:

1. **Instalar Ollama** en la estación de trabajo o servidor interno desde [ollama.com](https://ollama.com).
2. **Descargar el modelo institucional:**
   ```bash
   ollama pull llama3.1:8b
   ```
   *(En máquinas con menos de 8 GB de RAM o sin GPU dedicada, puede emplearse la alternativa ligera `ollama pull llama3.2:3b`).*
3. **Verificar que Ollama esté en ejecución:**
   ```bash
   ollama list
   ```
4. **Configurar `.env`:**
   ```ini
   AI_PROVIDER=ollama
   OLLAMA_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1:8b
   ```
5. Al iniciar el backend, se lanzará automáticamente una rutina de precalentamiento (*warm-up*) en segundo plano para precargar los pesos del modelo en memoria, reduciendo la latencia de las consultas posteriores.

---

## 8. Admin API Segura (Gestión de Listas de Amenazas)

La Admin API es un componente opcional desactivado por defecto (`ADMIN_API_ENABLED=false`). Permite al equipo de seguridad actualizar las listas de dominios, extensiones y frases de phishing de forma remota sin requerir acceso SSH al servidor.

### 8.1. Generar la Clave de Administración
Ejecute el generador criptográfico seguro:
```bash
python -m backend.admin_keygen
```
El script generará una clave aleatoria de 32 bytes y su hash SHA-256. Agregue el hash a su `.env`:
```ini
ADMIN_API_ENABLED=true
ADMIN_API_KEY_SHA256=a1b2c3d4...
ADMIN_ALLOWED_IPS=127.0.0.1,::1
```

### 8.2. Endpoints Administrativos (`/api/admin/v1/`)
- `GET /api/admin/v1/status`: estado de listas y llamadas.
- `GET /api/admin/v1/lists/{list_name}`: consulta una lista y su versión SHA-256 actual.
- `PUT /api/admin/v1/lists/{list_name}`: reemplazo atómico de una lista validada con cabecera `If-Match`.
- `POST /api/admin/v1/lists/reload`: recarga desde disco bajo demanda.
- `GET /api/admin/v1/audit`: registro circular de las últimas 200 operaciones administrativas.

---

## 9. Estructura del Proyecto

```
mail-coastguard/
├── .env.example                    # Plantilla de configuración de entorno
├── .gitignore                      # Exclusiones de Git (secretos, logs, venv)
├── DECISIONS.md                    # Registro de decisiones técnicas de diseño
├── README.md                       # Documentación técnica completa
├── requirements.txt                # Dependencias fijadas del backend
├── security.md                     # Directrices y matriz de seguridad
├── Specs.md                        # Especificación técnica del backend y motor
├── Specs_Extension.md              # Especificación técnica de la extensión
├── Specs_Web.md                    # Especificación técnica del webmail simulado
│
├── backend/                        # Núcleo del servidor y motor de validación
│   ├── __init__.py
│   ├── admin_api.py                # Admin API opcional de alta seguridad
│   ├── admin_keygen.py             # Generador de credenciales administrativas
│   ├── ai_adapter.py               # Adaptadores para Gemini, DeepSeek, Ollama y Mock
│   ├── config.py                   # Carga centralizada de configuración y constantes
│   ├── main.py                     # Aplicación FastAPI, rutas fijas y middlewares
│   ├── models.py                   # Modelos de datos Pydantic estrictos
│   ├── validation_engine.py        # Capas 1 y 2, Levenshtein, combinación de niveles
│   └── data/                       # Listas de detección en memoria (JSON)
│       ├── dangerous_extensions.json
│       ├── official_domains.json
│       └── phishing_phrases.json
│
├── frontend/                       # Webmail institucional simulado (UNETI)
│   ├── email_templates.json        # Ejemplos rápidos para el simulador
│   ├── inbox_emails.json           # 5 correos sintéticos de demostración
│   ├── index.html                  # Aplicación de página única (HTML/CSS/JS puro)
│   └── assets/
│       └── uneti_logo.png          # Logotipo institucional
│
├── extension/                      # Extensión Chromium (Manifest V3)
│   ├── background.js               # Service Worker: único canal de red hacia el backend
│   ├── content.js                  # Script de contenido y observación del DOM
│   ├── core.js                     # Funciones puras de validación, sanitización y niveles
│   ├── icons_data.js               # Activos SVG higienizados
│   ├── manifest.json               # Manifiesto MV3 con permisos mínimos (storage)
│   ├── package.json                # Entorno de desarrollo para Tailwind CSS
│   ├── panel.js                    # Componente visual montado en Closed Shadow DOM
│   ├── panel_styles.js             # Estilos CSS compilados para el panel
│   ├── popup.css                   # Estilos de la ventana emergente
│   ├── popup.html                  # Interfaz de la ventana emergente
│   ├── popup.js                    # Lógica de configuración de la extensión
│   ├── sites.js                    # Adaptador de selectores del sitio de prueba
│   ├── tailwind.config.js          # Tokens de diseño y colores institucionales
│   ├── icons/                      # Iconos en resoluciones 16, 32, 48 y 128 px
│   ├── scripts/
│   │   └── build.js                # Compilador de estilos e iconos de la extensión
│   ├── src/
│   │   └── input.css               # Directivas de entrada de Tailwind
│   └── tests/                      # Pruebas automatizadas de la extensión (node --test)
│       ├── core.test.js
│       └── static_checks.test.js
│
├── evaluation/                     # Conjunto de evaluación y métricas
│   ├── evaluation_emails.json      # 30 correos sintéticos (15 legítimos / 15 maliciosos)
│   └── evaluate.py                 # Script de evaluación de tasa de detección y falsos positivos
│
└── tests/                          # Suite completa de pruebas automatizadas del backend
    ├── test_api.py                 # Pruebas de endpoints HTTP y degradación
    ├── test_combination.py         # Pruebas de combinación y asimetría de niveles
    ├── test_demo.py                # Verificación de los 5 correos de la bandeja
    ├── test_layer1.py              # Pruebas de dominio, encabezados y adjuntos
    ├── test_layer2.py              # Pruebas de heurística de contenido y normalización
    ├── test_layer3.py              # Pruebas de adaptadores de IA y delimitadores
    └── test_security.py            # Verificación de criterios SEC-01 a SEC-33
```

---

## 10. Pruebas Automatizadas y Evaluación de Rendimiento

### 10.1. Ejecución de la Suite de Pruebas (Pytest)
Para ejecutar todas las pruebas unitarias y de seguridad del backend en modo aislado (sin conexión a internet):
```bash
pytest -v
```

Las pruebas cubren los criterios de aceptación CA-01 a CA-26 y los requerimientos de seguridad SEC-01 a SEC-33:
- Escaneo estático de secretos y tokens en el código fuente.
- Detección de evasiones por homóglifos, caracteres de inversión BIDI y dobles extensiones.
- Regla de asimetría (la IA jamás puede reducir el riesgo obtenido por las capas locales).
- Neutralización de intentos de inyección de instrucciones en el correo.
- Control de tamaño de peticiones, limitación de frecuencia (*rate limiting*) y aislamiento de logs.
- Validación de que los 5 correos sintéticos de demostración coinciden con sus resultados esperados.

### 10.2. Ejecución de Pruebas de la Extensión (Node.js)
```bash
cd extension
npm test
```
Ejecuta las pruebas de funciones puras (`core.test.js`) y las comprobaciones estáticas de manifiesto, permisos mínimos y ausencia de métodos inseguros (`static_checks.test.js`).

### 10.3. Evaluación contra el Conjunto de 30 Correos Sintéticos
Ejecute el script de métricas sobre las Capas 1 y 2:
```bash
python evaluation/evaluate.py
```

Para incluir la Capa 3 (con el proveedor de IA configurado en `.env`):
```bash
python evaluation/evaluate.py --ai
```

El script genera una tabla con:
- **Tasa de Detección (Meta $\ge 90\,\%$):** porcentaje de correos maliciosos clasificados en `YELLOW`, `RED` o `BLACK`.
- **Falsos Positivos Fuertes (Meta $\le 10\,\%$):** porcentaje de correos legítimos catalogados incorrectamente como `RED` o `BLACK`.
- **Falsos Positivos Totales:** porcentaje de correos legítimos en nivel `YELLOW` o superior (valor informativo).
- **Latencia media y percentil 95 (P95)** del análisis profundo con IA.

---

## 11. Licencia y Créditos

Proyecto desarrollado en el marco del **UNETI IA Hackathon 2026** (Eje Temático: Ciberseguridad e Inteligencia Artificial).  
Diseñado para la protección proactiva de la infraestructura de comunicaciones de las instituciones públicas.
