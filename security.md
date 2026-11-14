# Mail CoastGuard — security.md

> Instrucciones de seguridad independientes para la herramienta de IA que desarrolla el MVP.
> Complementa a `Specs.md`, `Specs_Web.md` y `Specs_Extension.md`. **Ante cualquier conflicto entre ellos y este documento, prevalece este.**
> Versión 1.2 · Idioma del documento: español. Todo el código (identificadores, comentarios, docstrings, rutas, claves JSON) se escribe en inglés; los textos dirigidos al funcionario, en español.

---

## 0. Cómo usar este documento

1. Lee este documento completo **antes** de escribir código y cúmplelo en cada tarea de `Specs.md`, `Specs_Web.md` y `Specs_Extension.md`.
2. Cada requisito aquí tiene una prueba en `tests/test_security.py` (sección 12). Una tarea no está terminada si esa prueba falla.
3. Si durante el desarrollo encuentras una vulnerabilidad que no está en este documento, **primero agrégala a la sección 14** (hallazgo, riesgo, mitigación y prueba) y luego corrige el código. No parches a ciegas.
4. Principios que guían todo: **mínima superficie expuesta, mínimo privilegio, fallar de forma segura, no confiar en ninguna entrada** (incluido el contenido del correo y la respuesta de la IA).

---

## 1. Secretos y configuración (`.env`)

### Reglas

- **Ninguna clave, token, contraseña, URL interna ni código secreto** puede estar escrito en el código fuente, en los archivos de datos ni en el frontend.
- Todo valor sensible o dependiente del entorno se lee **solo** de variables de entorno, cargadas desde un archivo `.env` con `python-dotenv` (única dependencia adicional autorizada).
- La carga de configuración vive **únicamente** en `backend/config.py`. Ningún otro módulo llama a `os.environ` ni a `load_dotenv`.
- Las claves de Gemini y de DeepSeek **nunca** se envían al navegador. El frontend y la extensión jamás llaman a Gemini, DeepSeek ni Ollama: todo pasa por el backend.
- Nunca imprimir, registrar ni devolver en errores el valor de una clave. Si hay que mencionarla, mostrar solo `***`.
- Los secretos **no tienen valor por defecto** en el código. Si falta `GEMINI_API_KEY` o `DEEPSEEK_API_KEY`, el adaptador correspondiente falla **antes de hacer cualquier petición** y se aplica la degradación controlada de `Specs.md` (el sistema sigue funcionando con las capas locales).
- Si una clave llegó a escribirse alguna vez en un archivo o commit, se considera comprometida y debe **rotarse**.

### Variables de entorno

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `AI_PROVIDER` | `gemini`, `deepseek`, `ollama` o `mock`. Un valor desconocido impide el arranque. | `gemini` |
| `GEMINI_API_KEY` | Clave de Gemini (secreta) | *(ninguno)* |
| `GEMINI_MODEL` | Modelo de Gemini (verificar en la documentación oficial que no esté deprecado) | `gemini-3-flash-preview` |
| `DEEPSEEK_API_KEY` | Clave de DeepSeek (secreta) | *(ninguno)* |
| `DEEPSEEK_MODEL` | Modelo de DeepSeek (verificar en la documentación oficial) | `deepseek-v4-flash` |
| `OLLAMA_URL` | URL del servidor Ollama (ver sección 5) | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo local | `llama3.1:8b` |
| `OLLAMA_NUM_CTX` | Tamaño de contexto del modelo local | `6144` |
| `OLLAMA_NUM_PREDICT` | Máximo de tokens de la respuesta | `300` |
| `OLLAMA_KEEP_ALIVE` | Tiempo que el modelo permanece cargado | `30m` |
| `AI_TIMEOUT_SECONDS` | Tiempo máximo de la IA | `60` |
| `AI_MAX_CONCURRENT` | Llamadas simultáneas a la IA | `1` |
| `APP_HOST` | Interfaz de red donde escucha | `127.0.0.1` |
| `APP_PORT` | Puerto | `8000` |
| `CORS_ORIGINS` | Orígenes permitidos separados por coma; vacío = sin CORS | *(vacío)* |
| `MAX_REQUEST_SIZE_BYTES` | Tamaño máximo del cuerpo HTTP | `204800` |
| `RATE_LIMIT_PER_MINUTE` | Límite general por IP | `30` |
| `DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE` | Límite de `/deep-analysis` por IP | `6` |
| `AI_MAX_CALLS_PER_HOUR` | Tope global de llamadas a la IA | `100` |
| `ADMIN_API_ENABLED` | Activa la Admin API (sección 2.2). Desactivada por defecto. | `false` |
| `ADMIN_API_KEY_SHA256` | Hash SHA-256 (hex) de la clave de administración (secreto; nunca la clave en claro) | *(ninguno)* |
| `ADMIN_ALLOWED_IPS` | IP o redes CIDR autorizadas para la Admin API, separadas por coma (solo loopback o RFC 1918) | `127.0.0.1,::1` |
| `ADMIN_RATE_LIMIT_PER_MINUTE` | Límite de peticiones por IP a la Admin API | `20` |
| `ADMIN_MAX_FAILED_ATTEMPTS` | Intentos fallidos de autenticación por IP antes del bloqueo | `5` |
| `ADMIN_LOCKOUT_MINUTES` | Duración del bloqueo tras exceder los intentos fallidos | `15` |

Las URL de Gemini y DeepSeek **no son configurables** (constantes en `config.py`).

### Archivos obligatorios

`.gitignore` (debe incluir como mínimo):

```
.env
.env.*
!.env.example
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.log
logs/
node_modules/
```

`.env.example`: contiene los nombres de todas las variables de la tabla. **Los secretos van vacíos** (`GEMINI_API_KEY=`, `DEEPSEEK_API_KEY=`, `ADMIN_API_KEY_SHA256=`). Nunca valores reales.

### Escaneo de secretos (prueba `SEC-01`)

`tests/test_security.py` recorre todos los archivos `.py`, `.html`, `.js` y `.json` del proyecto (excepto `tests/test_security.py` y `node_modules/`) y falla si encuentra:

- `AIza[0-9A-Za-z_\-]{35}` (clave de Google)
- `sk-[0-9A-Za-z]{20,}` (clave con formato de DeepSeek u OpenAI)
- `-----BEGIN [A-Z ]*PRIVATE KEY-----`
- `(?i)(api[_-]?key|secret|token|passw(or)?d|clave)\s*[:=]\s*["'][^"']{6,}["']`
- Cadenas de conexión con usuario y contraseña (`://user:password@`)
- `Bearer\s+[A-Za-z0-9_\-]{32,}` (clave de administración escrita en un archivo)

---

## 2. Rutas administrativas y superficie expuesta

### 2.1 Rutas públicas permitidas (lista blanca exacta, rutas fijas sin comodines)

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/` | `index.html` |
| `GET` | `/inbox_emails.json` | Correos de la bandeja |
| `GET` | `/email_templates.json` | Ejemplos rápidos del simulador de correo |
| `GET` | `/assets/uneti_logo.png` | Logo de la UNETI (ruta fija) |
| `GET` | `/health` | Estado (solo `{"status": "ok"}`) |
| `POST` | `/analyze` | Capas 1 y 2 |
| `POST` | `/deep-analysis` | Capa 3 |

**Cualquier otra ruta o método (salvo la Admin API de la sección 2.2, solo si está activada) responde `404`** con el cuerpo genérico `{"detail": "Not found"}`. Se usa 404 (no 403) para no revelar qué existe. Se permiten además `HEAD` y `OPTIONS` solo sobre las rutas anteriores.

### Reglas generales

- **No existe ningún panel web ni endpoint de depuración, carga de archivos, consulta o edición de configuración, ni de ejecución de comandos.** La **única** administración remota es la Admin API de la sección 2.2, que está desactivada por defecto y solo permite gestionar las tres listas de `backend/data/`. Sin ella, las listas se editan solo en el servidor, a mano.
- Crear la app FastAPI así: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)`. Quedan deshabilitados `/docs`, `/redoc` y `/openapi.json`.
- **No montar `StaticFiles`.** Servir el frontend con las rutas explícitas de la tabla (`FileResponse` con rutas fijas). Así no hay listado de directorios ni acceso a otros archivos.
- Agregar un *middleware* que responda `404` a cualquier ruta que no esté en la lista blanca, y en especial a:
  `/admin`, `/administrator`, `/wp-admin`, `/phpmyadmin`, `/console`, `/debug`, `/config`, `/actuator`, `/server-status`, `/docs`, `/redoc`, `/openapi.json`, cualquier ruta con un segmento que empiece por `.` (`/.env`, `/.git/...`), cualquier ruta bajo `/backend`, `/data`, `/tests`, `/evaluation`, `/extension`, y cualquier ruta que contenga `..`, `%2e`, `%2f`, `\` o caracteres de control.
- La Admin API vive bajo `/api/admin/v1/` (nunca bajo `/admin`, que sigue bloqueado como señuelo). Con `ADMIN_API_ENABLED=false` esas rutas responden el mismo `404` genérico que cualquier ruta inexistente.
- Los archivos `.env`, `*.py`, `backend/data/*.json` y `Specs*.md`/`security.md` **nunca** se sirven por HTTP.
- La app escucha en `127.0.0.1` por defecto. Exponerla a otras máquinas (por ejemplo en la red de la sede) es una decisión consciente: se hace cambiando `APP_HOST` y solo en una red de confianza.
- Ejecutar con `uvicorn ... --no-server-header` (no revelar el servidor). `--reload` solo en desarrollo.
- Registrar los bloqueos solo con la **ruta recortada a 100 caracteres y sin caracteres de control**, nunca con datos de correos.


### 2.2 Admin API segura (opcional, desactivada por defecto)

Permite al equipo de seguridad actualizar las listas de detección (`official_domains.json`, `dangerous_extensions.json`, `phishing_phrases.json`) sin entrar al servidor. **No** da acceso a correos (el sistema no los guarda), a claves, a variables de entorno, a archivos arbitrarios ni a ejecución de código. Está pensada para un cliente de línea de comandos (por ejemplo `curl`), no para navegadores.

#### Endpoints (lista blanca; solo existen si `ADMIN_API_ENABLED=true`)

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/api/admin/v1/status` | Estado operativo sin datos sensibles: tiempo activo, proveedor y modelo de IA configurados (sin claves), llamadas a la IA en la última hora y, por cada lista, número de entradas y versión. |
| `GET` | `/api/admin/v1/lists/{list_name}` | Contenido de una lista y su `version`. |
| `PUT` | `/api/admin/v1/lists/{list_name}` | Reemplaza una lista completa (validada). |
| `POST` | `/api/admin/v1/lists/reload` | Relee las tres listas desde disco y las valida. |
| `GET` | `/api/admin/v1/audit` | Últimas 200 acciones administrativas (en memoria). |

- `list_name` solo admite exactamente `official_domains`, `dangerous_extensions` o `phishing_phrases` (lista cerrada). Cualquier otro valor, y cualquier intento de ruta (`..`, `/`, `%2e`, extensiones), responde `404`. **Nunca** se construye una ruta de archivo con datos de la petición: la correspondencia nombre → archivo es una constante.
- No hay endpoints para cambiar variables de entorno, claves, proveedor o modelo de IA, ni para subir, descargar o borrar archivos.

#### Autenticación y autorización (todas las capas se aplican, en este orden)

1. **Interruptor:** con `ADMIN_API_ENABLED=false` (por defecto) todas las rutas responden `404` genérico, indistinguible de una ruta inexistente.
2. **Origen de red:** la IP del cliente se toma del socket (nunca de `X-Forwarded-For`) y debe estar en `ADMIN_ALLOWED_IPS`. Si no, `404`. Solo se aceptan direcciones de bucle local o privadas (RFC 1918): si `ADMIN_ALLOWED_IPS` contiene una red pública, la Admin API **no se activa** (la app arranca sin ella y registra `Admin API disabled: invalid configuration`).
3. **Sin contexto de navegador:** una petición con cabecera `Origin` o `Sec-Fetch-Site` se rechaza con `403` genérico. No se envían cabeceras CORS en estas rutas (la Admin API no se abre a páginas web ni a la extensión).
4. **Clave de administración:** cabecera `Authorization: Bearer <clave>` (nunca en la URL, en la consulta ni en el cuerpo). La clave se genera con `python -m backend.admin_keygen` (`secrets.token_urlsafe(32)` o más), que la muestra **una sola vez** junto con su hash SHA-256 para `ADMIN_API_KEY_SHA256`; la clave en claro no se guarda en ningún archivo. La comprobación calcula el SHA-256 de la clave recibida y lo compara con `hmac.compare_digest` (comparación en tiempo constante). Si `ADMIN_API_KEY_SHA256` falta o no es un hex de 64 caracteres, la Admin API no se activa.
5. **Fallo de autenticación:** `401` con `{"detail": "Unauthorized"}` y `WWW-Authenticate: Bearer`, idéntico para clave ausente, mal formada o incorrecta.
6. **Bloqueo por fuerza bruta:** tras `ADMIN_MAX_FAILED_ATTEMPTS` fallos desde una IP, esa IP recibe `429` con `Retry-After` durante `ADMIN_LOCKOUT_MINUTES`, **incluso si luego envía la clave correcta**.
7. **Limitación de frecuencia propia:** `ADMIN_RATE_LIMIT_PER_MINUTE` por IP, independiente de los límites de la API pública.
8. **Transporte:** en bucle local basta `http`. Si la Admin API se abre a una red interna (IP privada en `ADMIN_ALLOWED_IPS`), debe ir detrás de un proxy inverso con **HTTPS**; sin TLS, la clave viajaría en claro.

#### Validación de las escrituras (`PUT`)

- `Content-Type: application/json` (si no, `415`); cuerpo máximo de 256 KB (si no, `413`); forma `{"data": <contenido de la lista>}` sin campos adicionales.
- **Control de concurrencia:** la cabecera `If-Match` debe traer la `version` actual de la lista (SHA-256 del JSON canónico). Si no coincide, `412`; si falta, `428`.
- Se aplican las mismas comprobaciones de estructura que al arrancar (sección 6) y estas, con expresiones regulares **fijas**:
  - `official_domains`: claves exactamente `domains` (1 a 200 elementos; minúsculas, ASCII o punycode, máximo 253 caracteres, formato `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$`) e `institutional_terms` (1 a 200 elementos de máximo 100 caracteres, en minúsculas y sin tildes).
  - `dangerous_extensions`: claves exactamente `prohibited`, `suspicious` y `common_documents`, cada una con 1 a 200 elementos de formato `^\.[a-z0-9]{1,10}$`; una extensión no puede estar a la vez en `prohibited` y en `common_documents`.
  - `phishing_phrases`: lista de 1 a 1.000 objetos con exactamente `phrase` (1 a 200 caracteres, **ya normalizada** como en `Specs.md` 8.1, sin caracteres de control), `weight` (entero de 1 a 10) y `type` (texto de 1 a 60 caracteres); sin frases repetidas.
- Un error de validación responde `422` con un mensaje genérico, **sin repetir el contenido recibido**, y no modifica nada.
- **Escritura atómica y reversible:** bajo un cerrojo (una escritura a la vez), escribir un archivo temporal en la misma carpeta con permisos `0600`, copiar la versión vigente a `<archivo>.bak` (una sola copia anterior), reemplazar con `os.replace` y cambiar la referencia en memoria de la lista de forma atómica. Si algo falla, se conserva la versión anterior y el sistema sigue funcionando con ella. Las peticiones en curso usan la copia anterior; las siguientes, la nueva.
- Ninguna escritura puede dejar una lista vacía (el mínimo de elementos arriba lo impide).

#### Auditoría y privacidad de la Admin API

- Cada acción administrativa y cada intento fallido se registran con: hora, acción, nombre de la lista, resultado (código) e IP del cliente, y se guardan en un registro circular en memoria de 200 entradas (`GET /audit`). También se emite una línea de log con esos mismos campos.
- **Nunca** se registran ni devuelven la clave, su hash, el contenido de las listas ni cabeceras de autorización. Las respuestas llevan `Cache-Control: no-store` y las cabeceras de seguridad de la sección 4.
- Un error interno de la Admin API devuelve `500` con `{"detail": "Internal error"}` y sin texto de la excepción.

#### Operación

- Activarla solo cuando haga falta: definir `ADMIN_API_KEY_SHA256` y `ADMIN_API_ENABLED=true` en `.env` y reiniciar. Con la Admin API activa, `backend/data/` debe ser escribible por el usuario de la app; si está desactivada, esa carpeta queda de solo lectura (sección 6).
- **Rotación de la clave:** generar una nueva con `python -m backend.admin_keygen`, sustituir el hash en `.env` y reiniciar. Rotar de inmediato ante cualquier sospecha de exposición.
- Sin dependencias nuevas: se usan `hashlib`, `hmac`, `secrets`, `ipaddress` y `os` de la biblioteca estándar.

---

## 3. Validación de entrada y límites (anti-abuso)

### Validación del modelo `EmailInput`

- `model_config` con `extra="forbid"` (rechazar campos desconocidos).
- Longitudes máximas: `sender` 320, `display_name` 200, `reply_to` 320, `subject` 500, `body` 50.000, `attachments` máximo 50 elementos de máximo 255 caracteres cada uno.
- Todos los campos son `str` (o lista de `str`); rechazar cualquier otro tipo.
- Un exceso de longitud o un campo desconocido devuelve `422` con un mensaje genérico. **Nunca** devolver el valor recibido en el mensaje de error.

> Nota: un `body` mayor a 50.000 caracteres se **rechaza** con `422` (no se recorta). El recorte a 8.000 caracteres para la IA se mantiene.

### Límites de la petición

- Tamaño máximo del cuerpo HTTP: `MAX_REQUEST_SIZE_BYTES`. Comprobar `Content-Length` y también cortar la lectura al exceder el límite. Respuesta `413`.
- `Content-Type` debe ser `application/json` en los `POST`. Si no, `415`.
- Los `POST` sin cuerpo o con JSON inválido devuelven `422`.

### Limitación de frecuencia (sin dependencias nuevas)

- Implementar un limitador en memoria de ventana deslizante por IP: `RATE_LIMIT_PER_MINUTE` en general y `DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE` para `/deep-analysis`. Al exceder: `429` con cabecera `Retry-After`.
- **No confiar en `X-Forwarded-For`** salvo que se configure explícitamente un proxy de confianza. (La Admin API **nunca** lo usa: ver 2.2.)
- Tope global de llamadas a la IA: `AI_MAX_CALLS_PER_HOUR`. Al excederlo, se aplica la degradación controlada (`unavailable`), no un error. Protege la cuota y el costo.
- Máximo `AI_MAX_CONCURRENT` llamadas simultáneas a la IA (semáforo; por defecto **1**, porque un servidor local con un modelo de 8B no soporta carga concurrente y las cuotas de los planes gratuitos en la nube son bajas). Las demás esperan o se degradan.

### Anti-ReDoS y rendimiento

- Prohibido construir expresiones regulares con datos del usuario. Solo expresiones fijas y simples.
- Antes de calcular Levenshtein, descartar la comparación si la diferencia de longitud supera el umbral, y limitar los dominios a 253 caracteres.
- Todo acceso a red (IA) tiene tiempo máximo.

---

## 4. Errores, cabeceras y CORS

### Errores

- Registrar un manejador global: cualquier excepción no controlada devuelve `500` con `{"detail": "Internal error"}`. **Sin trazas, sin rutas de archivos y sin texto de la excepción** en la respuesta.
- En los registros de errores de la IA, guardar solo el **nombre de la clase de la excepción**, no su mensaje (puede contener el correo o la clave).

### Cabeceras de seguridad (todas las respuestas)

| Cabecera | Valor |
|---|---|
| `Content-Security-Policy` | `default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Cache-Control` | `no-store` (en todas las respuestas de la API) |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

> `'unsafe-inline'` en scripts y estilos solo se permite porque `Specs_Web.md` exige un único `index.html`. Se compensa con: nada de `innerHTML`, `eval` ni `document.write`, y ninguna librería de terceros.

### CORS

- Por defecto **no se activa CORS** (el frontend y la API comparten origen). Las peticiones de la extensión las hace su *service worker* con permisos de host, por lo que tampoco requieren CORS.
- Prohibido `allow_origins=["*"]`. Si `CORS_ORIGINS` tiene valores, usar exactamente esa lista, sin credenciales.

---

## 5. Seguridad de la IA (LLM)

- **La respuesta de la IA es una entrada no confiable.** Se valida estrictamente (ver `Specs.md`, sección 9.4: solo se acepta un objeto JSON, sin texto ni caracteres fuera de él) y además:
  - Cada motivo se recorta a **200 caracteres** y se eliminan caracteres de control.
  - Nunca se usa la respuesta para decidir rutas, URL, comandos ni nombres de archivo.
- La IA **no tiene herramientas**: no habilitar búsqueda web, ejecución de código, llamadas a funciones ni acceso a archivos en la configuración de ningún proveedor (no pasar `tools` en Gemini ni en DeepSeek).
- **Prompt de la Capa 3:** va íntegramente en inglés, exige responder **solo** con un objeto JSON y exige que los `reasons` estén en español (`Specs.md`, sección 9.2). El contenido del correo siempre va entre delimitadores y se declara como datos no confiables.
- **Minimización de datos:** enviar solo los campos necesarios del correo. Nunca enviar claves, cabeceras internas ni el contenido de adjuntos (solo sus nombres).
- El proveedor de IA se elige **solo por `AI_PROVIDER`**. El cliente no puede elegir proveedor, modelo ni parámetros en la petición.
- **Proveedor del MVP: Gemini (nube).** Gemini y DeepSeek son servicios de terceros: los planes gratuitos pueden usar los datos enviados para mejorar sus productos, y los datos salen de la red interna. Por eso, mientras el proveedor sea `gemini` o `deepseek`, se usan **solo correos sintéticos**; nunca correos reales de funcionarios. Incluir esta advertencia en el `README.md`.
- **Despliegue con datos reales:** exige `AI_PROVIDER=ollama` (Llama 3.1 8B local), de modo que el contenido de los correos no salga de la red interna. Documentarlo en el `README.md`.
- **Sin conmutación automática entre proveedores:** si el proveedor configurado falla, se aplica la degradación controlada. **Nunca** se reenvía el correo a otro proveedor por cuenta del programa (sería una fuga silenciosa de datos).
- **Destinos fijos de la nube:** las URL de Gemini (las del SDK `google-genai`) y de DeepSeek (`https://api.deepseek.com/chat/completions`, constante en `config.py`) no se leen del entorno ni de la petición. Solo `https`, tiempo máximo y sin seguir redirecciones a otros hosts.
- **Anti-SSRF (Ollama):** `OLLAMA_URL` se lee solo del entorno, debe usar `http` o `https` y apuntar a `localhost`, `127.0.0.1` o una dirección privada (RFC 1918). Si es un nombre de host, se resuelve al iniciar y **todas** las direcciones obtenidas deben ser privadas o de bucle local. Si no cumple, el adaptador de Ollama falla de forma segura.
- **El servidor Ollama no tiene autenticación:** debe escuchar solo en la red interna, con el puerto 11434 restringido por cortafuegos a las máquinas del proyecto. Nunca exponerlo a internet.
- **CoastGuard nunca visita enlaces ni abre o descarga adjuntos.** Solo analiza texto y nombres de archivo. No agregar nunca funciones que hagan peticiones a URL contenidas en un correo.

---

## 6. Endurecimiento de la detección (contra evasión)

Las capas locales son la base de seguridad del sistema; un atacante intentará evadirlas. Reglas obligatorias (ya reflejadas en `Specs.md`, secciones 7 y 8):

1. **Dirección manipulada:** el remitente debe tener exactamente un `@`, sin espacios, caracteres de control ni `<` `>`. Si no, mínimo `YELLOW`.
2. **Suplantación en el nombre visible:** si `display_name` incluye una dirección o dominio oficial y el remitente real no es oficial → `RED`.
3. **Extensiones disfrazadas:** quitar espacios, puntos y caracteres de control al final de los nombres de adjunto antes de evaluar. Los caracteres de dirección de texto (U+202A a U+202E, U+2066 a U+2069) en un nombre de adjunto → `BLACK`.
4. **Texto ofuscado:** en la Capa 2, normalizar con NFKC, eliminar caracteres invisibles (U+200B a U+200F, U+2060, U+FEFF) y convertir letras cirílicas o griegas confundibles a latinas antes de buscar frases.
5. **Dominios internacionales:** dominios con caracteres no ASCII o `xn--` → mínimo `YELLOW`.

### Integridad de las listas de datos

- Al iniciar, validar los tres JSON de `backend/data/` (que existan, que sean JSON válido, que tengan la estructura esperada y que no estén vacíos). Si falta o está corrupto alguno, **la aplicación no arranca** y muestra un mensaje claro. Nunca continuar con listas vacías: una lista de dominios vacía volvería sospechoso a todo, y una de frases vacía daría `GREEN` a todo.
- Cargar las listas **una sola vez** al iniciar y mantenerlas en memoria (solo lectura).
- Con la Admin API desactivada, los archivos de `backend/data/` deben tener permisos de solo lectura para el usuario que ejecuta la app. Con la Admin API activa, solo esa carpeta es escribible, y únicamente a través de la Admin API (sección 2.2), que valida cada cambio antes de aplicarlo.
- Las listas que se cambian por la Admin API pasan por las mismas validaciones que al arrancar; una lista inválida **nunca** reemplaza a la vigente.

### Fallar de forma segura

Si una de las Capas 1 o 2 lanza una excepción inesperada con un correo concreto, el resultado es `YELLOW` con el motivo `No se pudo analizar el correo por completo. Revíselo con cuidado.` Nunca `GREEN` y nunca un error `500` que oculte el análisis.

---

## 7. Registro (logs) y privacidad

- Se registra únicamente: hora, ruta, código de respuesta y `final_level` (más la auditoría de la Admin API descrita en 2.2). **Jamás** remitente, asunto, cuerpo, nombres de adjuntos, ni respuestas de la IA.
- Neutralizar la inyección en los registros: eliminar saltos de línea y caracteres de control de cualquier texto externo que llegue a un log (por ejemplo, la ruta bloqueada).
- No escribir correos en archivos temporales, no guardar en bases de datos y **no usar cachés** (`lru_cache`, diccionarios globales) que retengan contenido de correos.
- El análisis es *stateless*: cada petición se procesa y se descarta.

---

## 8. Dependencias y cadena de suministro

- **Backend:** solo las dependencias de `Specs.md` más `python-dotenv`. Usar los nombres **oficiales** exactos: `fastapi`, `uvicorn[standard]`, `pydantic`, `google-genai`, `httpx`, `python-dotenv`, `pytest` (cuidado con paquetes de nombre parecido). DeepSeek se consume con `httpx`: **no** se agrega ninguna librería para él.
- Trabajar en Python 3.14 y en un entorno virtual (`.venv`).
- La Admin API y su generador de claves usan solo la biblioteca estándar (`hashlib`, `hmac`, `secrets`, `ipaddress`, `os`): no se agrega ninguna dependencia.
- Instalar las últimas versiones estables de `fastapi` y `uvicorn` y, tras instalar y comprobar que las pruebas pasan, **fijar las versiones exactas** en `requirements.txt` (`pip freeze` de esas dependencias).
- Antes de entregar, ejecutar `pip-audit` (si está disponible) y corregir las vulnerabilidades conocidas. Las herramientas de análisis (`pip-audit`, `bandit`) son opcionales y **no** se agregan a `requirements.txt`.
- **Extensión (solo desarrollo):** `tailwindcss` (serie 3.4, versión exacta fijada) es la única dependencia de `extension/package.json`, no se incluye en tiempo de ejecución y se instala con `npm install` desde el registro oficial. El CSS compilado se revisa antes de versionarlo. Prohibido cargar Tailwind o cualquier recurso desde un CDN.
- El frontend y la extensión **no usan** CDN, fuentes externas, scripts de terceros ni imágenes remotas.

---

## 9. Seguridad del frontend

- Todo texto dinámico (correos, motivos, avisos, respuestas de la IA) se inserta con `textContent`. **Prohibido** `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` y `new Function`.
- Las URL dentro de un correo se muestran como **texto plano, nunca como enlaces clicables**.
- No guardar contenido de correos en `localStorage`, `sessionStorage` ni cookies.
- No incluir claves, rutas internas ni comentarios con información sensible en `index.html`.
- Los errores de red se muestran con un mensaje genérico, sin detalles técnicos.

---

## 10. Ejecución y despliegue

**Desarrollo local:**

```
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --no-server-header
```

**Demostración o producción:**

```
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-server-header
```

- Sin `--reload`. Ejecutar con un usuario sin privilegios de administrador.
- El archivo `.env` con permisos restringidos (lectura solo para el usuario de la app).
- Despliegue real (fuera del MVP): colocar la app detrás de un proxy inverso con **HTTPS** (TLS) y un cortafuegos que solo exponga ese proxy.

---

## 11. Principios de seguridad que no se pueden romper

1. Ningún secreto en el código.
2. Ninguna ruta fuera de la lista blanca.
3. La IA nunca baja un nivel de riesgo ni ejecuta acciones.
4. Ningún contenido de correo se almacena ni se registra.
5. Ante la duda, fallar hacia `YELLOW`, nunca hacia `GREEN`.
6. Ningún correo real sale de la red interna hacia un proveedor en la nube.
7. La Admin API está desactivada por defecto, solo se alcanza desde IP autorizadas, exige clave y nunca expone correos, claves ni archivos fuera de las tres listas.

---

## 12. Pruebas de seguridad (`tests/test_security.py`)

Todas sin red, con `MockAdapter` o doblados.

| ID | Criterio |
|---|---|
| SEC-01 | El escaneo de secretos de la sección 1 no encuentra coincidencias. |
| SEC-02 | `.gitignore` contiene `.env`; `.env.example` existe y los secretos están vacíos. |
| SEC-03 | Responden `404` genérico: `/admin`, `/administrator`, `/docs`, `/redoc`, `/openapi.json`, `/.env`, `/.git/config`, `/backend/main.py`, `/backend/data/official_domains.json`, `/%2e%2e/.env`, `/Specs.md`, `/Specs_Web.md`, `/Specs_Extension.md`, `/assets/`, `/assets/..%2f.env`. |
| SEC-04 | Métodos no permitidos (`PUT`, `DELETE`, `PATCH`, `TRACE`) y rutas desconocidas responden `404` o `405` sin detalles. |
| SEC-05 | Cuerpo mayor al límite → `413`; campo demasiado largo, campo extra o tipo incorrecto → `422`; `Content-Type` distinto de JSON → `415`; el mensaje de error no repite el valor enviado. |
| SEC-06 | Superado el límite de frecuencia → `429` con `Retry-After`. |
| SEC-07 | Una excepción forzada devuelve `500` con `{"detail": "Internal error"}` sin traza ni texto de la excepción. |
| SEC-08 | Las respuestas incluyen las cabeceras de la sección 4. |
| SEC-09 | No hay CORS con comodín (`*`) por defecto. |
| SEC-10 | `GET /health` devuelve solo `{"status": "ok"}`. |
| SEC-11 | Si la Capa 1 o 2 lanza una excepción, el resultado es `YELLOW` con el motivo de la sección 6. |
| SEC-12 | Con un JSON de `data/` ausente, corrupto o vacío, la aplicación no arranca. |
| SEC-13 | Adjuntos `gnp.exe` con caracteres de inversión (U+202E), `factura.exe .` y `factura.pdf.exe ` producen `BLACK`. |
| SEC-14 | Remitentes `a@mincyt.gov.ve@evil.com` y `<a@evil.com>` producen al menos `YELLOW`; nombre visible `soporte@mincyt.gov.ve` con remitente externo produce `RED`. |
| SEC-15 | El texto `cambio de contraseña` con un carácter invisible o letras cirílicas intercaladas sigue sumando puntaje en la Capa 2. |
| SEC-16 | Una respuesta de la IA con etiquetas HTML o más de 200 caracteres por motivo sale recortada y sin caracteres de control; `index.html` no contiene `innerHTML`, `eval(`, `document.write` ni `insertAdjacentHTML`. |
| SEC-17 | Tras analizar un correo, los logs no contienen su remitente, asunto, cuerpo ni adjuntos, y no hay saltos de línea inyectados. |
| SEC-18 | `OLLAMA_URL` con un esquema o host no permitido (incluido un nombre de host que resuelva a una dirección pública) hace fallar al adaptador de Ollama de forma segura. |
| SEC-19 | No se ejecutan más llamadas simultáneas a la IA que `AI_MAX_CONCURRENT`; superado `AI_MAX_CALLS_PER_HOUR` se devuelve `unavailable`. |
| SEC-20 | Si el adaptador del proveedor configurado falla (sea `gemini`, `deepseek` u `ollama`), no se hace ninguna petición a ningún otro proveedor (sin conmutación automática). |
| SEC-21 | El precalentamiento del modelo (Ollama) no bloquea el arranque y, si falla, no registra detalles de la excepción. |
| SEC-22 | Se cumplen los criterios X-01 a X-05, X-16, X-19 y X-20 de `Specs_Extension.md` (permisos mínimos, sin código remoto ni `eval`, validación de entradas, `backendUrl` local o privada, sin peticiones a otros orígenes, iconos validados y Tailwind compilado sin CDN). |
| SEC-23 | Sin `GEMINI_API_KEY` o sin `DEEPSEEK_API_KEY`, el adaptador correspondiente falla sin hacer ninguna petición; ningún log, respuesta ni mensaje de error contiene el valor de una clave; las URL de Gemini y DeepSeek no se pueden cambiar por entorno ni por petición. |
| SEC-24 | Una respuesta de la IA con cercos de código markdown, texto antes o después del objeto JSON, o campos adicionales se rechaza como inválida y activa la degradación controlada. |
| SEC-25 | Con `ADMIN_API_ENABLED` ausente o `false`, todas las rutas de `/api/admin/v1/` responden `404` genérico, idéntico al de una ruta inexistente. |
| SEC-26 | Sin clave, con clave incorrecta o con la clave en la URL → `401` genérico con `WWW-Authenticate`; con la clave correcta → `200`. La comparación usa `hmac.compare_digest`. |
| SEC-27 | Tras `ADMIN_MAX_FAILED_ATTEMPTS` fallos, la IP recibe `429` con `Retry-After`, incluso con la clave correcta, hasta que pasa `ADMIN_LOCKOUT_MINUTES`; el límite `ADMIN_RATE_LIMIT_PER_MINUTE` también devuelve `429`. |
| SEC-28 | Una IP fuera de `ADMIN_ALLOWED_IPS` recibe `404` aun con la clave correcta; `X-Forwarded-For` se ignora; una red pública en `ADMIN_ALLOWED_IPS` deja la Admin API desactivada. |
| SEC-29 | Una petición con `Origin` o `Sec-Fetch-Site` → `403`; las rutas de administración no devuelven cabeceras CORS. |
| SEC-30 | `PUT` de listas inválidas (vacías, estructura o tipos incorrectos, exceso de tamaño o de elementos, frase sin normalizar, extensión en `prohibited` y `common_documents`) → `422`/`413` y los archivos **no cambian**; `list_name` desconocido o con `..`, `/` o `%2e` → `404`; `If-Match` distinto → `412`, ausente → `428`. |
| SEC-31 | Un `PUT` válido escribe de forma atómica (con `.bak`), actualiza la lista en memoria sin reiniciar y queda en `GET /audit`; si falla la escritura se conserva la versión anterior. |
| SEC-32 | Ni las respuestas, ni los logs, ni la auditoría contienen la clave, su hash, cabeceras `Authorization` o el contenido de las listas; la clave sin hash válido (`ADMIN_API_KEY_SHA256` ausente o mal formado) deja la Admin API desactivada sin impedir el arranque. |
| SEC-33 | La Admin API no expone ninguna ruta distinta de las cinco de 2.2: no hay endpoints de configuración, claves, archivos ni comandos, y la correspondencia nombre de lista → archivo es una constante. |

---

## 13. Lista de verificación antes de entregar

- [ ] `grep` del repositorio sin claves ni contraseñas (más `SEC-01` en verde).
- [ ] `.env` fuera del repositorio; `.env.example` sin secretos.
- [ ] Solo existen las siete rutas públicas de la lista blanca (más las cinco de la Admin API únicamente si está activada); `/docs` y `/openapi.json` deshabilitados.
- [ ] La Admin API está desactivada por defecto, exige clave, IP autorizada y bloqueo por fuerza bruta, y la clave en claro no está en ningún archivo.
- [ ] No hay `StaticFiles`, `innerHTML`, `eval` ni CORS con comodín.
- [ ] Límites de tamaño, validación y limitación de frecuencia activos.
- [ ] Errores genéricos y cabeceras de seguridad presentes.
- [ ] Logs sin contenido de correos.
- [ ] Listas de datos validadas al iniciar; la app no arranca si faltan.
- [ ] No existe conmutación automática entre proveedores de IA, y con Gemini o DeepSeek solo se usaron correos sintéticos.
- [ ] La respuesta de la IA solo se acepta como objeto JSON puro.
- [ ] La extensión cumple la sección 15 y los criterios X de `Specs_Extension.md`.
- [ ] Versiones fijadas en `requirements.txt` y `pip-audit` sin hallazgos (si está disponible).
- [ ] `tests/test_security.py` en verde (SEC-01 a SEC-33).
- [ ] La sección 14 está actualizada con cualquier hallazgo nuevo.

---

## 14. Registro de hallazgos (documento vivo)

Hallazgos de la revisión de diseño de `Specs.md`. Los marcados «Parchado» ya se corrigieron en las especificaciones.

| ID | Hallazgo | Riesgo | Mitigación | Estado |
|---|---|---|---|---|
| H-01 | `/health` devolvía el proveedor de IA | Filtración de información de configuración | Devolver solo `{"status": "ok"}` | Parchado |
| H-02 | Montaje de `StaticFiles` sobre la carpeta del frontend | Listado de directorios, acceso a archivos no previstos | Rutas explícitas para cada archivo estático | Parchado |
| H-03 | Los motivos de la IA podían insertarse como HTML | XSS desde respuestas manipuladas del modelo | `textContent` en todo texto dinámico; recorte y limpieza de motivos | Parchado |
| H-04 | Extracción del dominio sin validar la dirección (varios `@`, `<>`) | Evasión de la Capa 1 | Validación estricta; mínimo `YELLOW` si es inválida | Parchado |
| H-05 | Nombre visible con la dirección oficial de otra persona | Suplantación visual | Regla `RED` en encabezados | Parchado |
| H-06 | Extensiones disfrazadas (U+202E, espacios o puntos finales) | Ejecutables que parecen documentos | Limpieza del nombre y regla `BLACK` | Parchado |
| H-07 | Texto con caracteres invisibles o cirílicos | Evasión de la Capa 2 | Normalización NFKC, eliminación de invisibles y confundibles | Parchado |
| H-08 | Sin límites de tamaño, frecuencia ni concurrencia | Denegación de servicio y consumo de cuota de la IA | Límites de la sección 3 | En security.md |
| H-09 | Sin rutas de administración bloqueadas explícitamente | Exposición de `/docs`, `/openapi.json` y archivos sensibles | Lista blanca y middleware de la sección 2 | En security.md |
| H-10 | Listas de datos vacías o corruptas producirían `GREEN` o todo sospechoso | Fallo silencioso inseguro | La app no arranca sin listas válidas | En security.md |
| H-11 | Excepción en una capa podía resultar en `500` o `GREEN` | Fallo inseguro | Resultado `YELLOW` con motivo explícito | En security.md |
| H-12 | Datos reales enviados a Gemini o DeepSeek (el MVP usa un proveedor en la nube por defecto) | Pérdida de soberanía y privacidad de datos | Solo correos sintéticos con proveedores en la nube; advertencia en el `README.md`; `AI_PROVIDER=ollama` obligatorio para datos reales | En security.md |
| H-13 | `OLLAMA_URL` configurable sin restricciones | SSRF | Validación de esquema y host | En security.md |
| H-14 | Mensajes de excepción de la IA en los logs | Filtración del correo o de la clave | Registrar solo el nombre de la clase de la excepción | En security.md |
| H-15 | Posible reenvío automático a otro proveedor si falla el configurado | Fuga silenciosa de datos | Sin conmutación automática; cambio solo manual | En security.md |
| H-16 | Servidor Ollama sin autenticación accesible en la red | Uso no autorizado del modelo y consumo de recursos | Escucha solo en red interna, puerto restringido por cortafuegos | En security.md |
| H-17 | Modelo pequeño o poco fiable ante inyección de instrucciones | Respuestas manipulables o mal formadas | Esquema JSON estricto, validación estricta, asimetría y ejemplos en el prompt | Parchado |
| H-18 | Un correo con HTML o texto podría imitar el panel de verificación (falso «GREEN») | Falsa sensación de seguridad | Shadow DOM cerrado, panel fuera del cuerpo del mensaje e indicador en la barra del navegador | En security.md |
| H-19 | Mensajes al *service worker* desde páginas o scripts ajenos | Uso no autorizado del backend | Validación de `sender.id`, origen, tipo y esquema | En security.md |
| H-20 | `backendUrl` apuntando a un servidor externo | Exfiltración del contenido de los correos | Solo localhost o IPv4 privada; permiso de un único origen | En security.md |
| H-21 | Permisos amplios o recursos accesibles desde la web | Mayor superficie de ataque y detección de la extensión | Solo `storage`; sin `web_accessible_resources` | En security.md |
| H-22 | Claves de Gemini o DeepSeek filtradas por logs, errores o repositorio | Uso fraudulento de la cuenta y consumo de cuota | Claves solo en `.env`, nunca registradas ni devueltas; el adaptador falla sin hacer peticiones si falta la clave; `SEC-01` y `SEC-23` | En security.md |
| H-23 | Respuesta de la IA con texto o markdown alrededor del JSON | Interpretación ambigua o contenido inesperado | Prompt que exige solo JSON, modos JSON/esquema de cada proveedor y validación estricta que rechaza cualquier carácter fuera del objeto | En security.md |
| H-24 | Cadena de suministro de la interfaz de la extensión (Tailwind, iconos y SVG) | Código o estilos maliciosos incluidos en la extensión | Tailwind solo en desarrollo y con versión fijada, sin CDN, CSS compilado y revisado; SVG de `iconos/` validados por el script de construcción y nunca insertados con `innerHTML` | En security.md |

| H-25 | Sin vía segura para actualizar las listas de detección, el equipo editaría archivos a mano en el servidor (errores, acceso directo al host) o se tentaría a crear un panel inseguro | Listas erróneas o endpoints administrativos sin protección | Admin API mínima, desactivada por defecto, con interruptor, IP autorizada, clave con hash, bloqueo, validación y auditoría (2.2) | En security.md |
| H-26 | Clave de administración débil, filtrada o comparada de forma insegura | Toma de control de las listas de detección | Clave aleatoria de 32 bytes o más, solo su SHA-256 en `.env`, `hmac.compare_digest`, nunca en URL ni logs, rotación documentada; `SEC-01`, `SEC-26` y `SEC-32` | En security.md |
| H-27 | Fuerza bruta o abuso de la Admin API; uso desde un navegador (CSRF o pivote desde una página) | Adivinar la clave o ejecutar cambios sin intención del administrador | Bloqueo por IP, límite propio, rechazo de `Origin`/`Sec-Fetch-Site`, sin CORS, IP desde el socket | En security.md |
| H-28 | Una edición de listas que deje vacías o corruptas las listas, o apunte a archivos arbitrarios | Todo `GREEN`, todo sospechoso o escritura fuera de `backend/data/` | Lista cerrada de nombres, validación estricta, escritura atómica con respaldo, versión con `If-Match`, nunca se construyen rutas con datos de la petición | En security.md |
| H-29 | Que la Admin API se convierta en canal de fuga de información (claves, configuración o contenido de listas en logs) | Filtración de secretos | `status` sin secretos, auditoría sin contenido, sin endpoints de configuración; `SEC-32` y `SEC-33` | En security.md |

*(Agregar aquí cada nuevo hallazgo, con su mitigación y su prueba, antes de corregir el código.)*

---

## 15. Extensión del navegador (intermediario entre la página y el motor)

La extensión (`Specs_Extension.md`) lee el contenido de los correos desde la página y lo envía al backend, por lo que es una pieza sensible. Reglas obligatorias:

### Amenazas consideradas

- Un correo malicioso intenta **imitar el panel** (por ejemplo, un falso «GREEN») dentro de la página.
- Una página o un script ajeno intenta enviar mensajes al *service worker* para usar el backend.
- La extensión se configura (o manipula) para enviar el contenido de los correos a un servidor externo.
- El backend, o algo que se haga pasar por él, devuelve texto con HTML o contenido inesperado.
- Permisos excesivos que amplíen el daño si algo falla.
- Estilos, iconos o dependencias de interfaz (Tailwind, SVG) que introduzcan código remoto o ejecutable.

### Reglas

1. **Permisos mínimos:** solo `storage`, más `host_permissions` del backend y `matches` del sitio de prueba. Prohibido `tabs`, `activeTab`, `scripting`, `webRequest`, `cookies`, `history` y `<all_urls>`. Sin `web_accessible_resources` ni `externally_connectable`.
2. **Sin código remoto:** nada de `eval`, `new Function`, scripts externos ni CSP propia más laxa que la predeterminada. Los estilos de Tailwind van **compilados** (sin CDN) y se aplican con hoja construible, sin `<style>` en línea.
3. **Un solo canal de red:** únicamente el *service worker* habla con el backend. El script de contenido no hace peticiones. Las peticiones usan `credentials: "omit"` y `redirect: "error"`, con tiempo máximo.
4. **Validación de cada mensaje** que recibe el *service worker*: `sender.id` propio, origen de la pestaña incluido en `sites.js`, `type` conocido y `email` con el esquema y los límites de longitud de este documento y de `Specs.md`. Lo demás se rechaza.
5. **Destino restringido:** `backendUrl` solo puede ser `localhost`, `127.0.0.1` o una IPv4 privada (RFC 1918), con `http` o `https`, sin credenciales, ruta ni consulta. Nunca nombres de dominio ni direcciones públicas. Se solicita permiso para **un único origen**, con un gesto del usuario.
6. **La respuesta del backend es no confiable:** se valida la forma, se recorta a 500 caracteres por texto y se eliminan caracteres de control. En el panel se inserta solo con `textContent`.
7. **Datos:** no se persiste contenido de correos en ningún almacenamiento; en `chrome.storage.local` solo van `backendUrl` y `active`. Sin telemetría, analítica ni registros con contenido (ni siquiera en `console.log`).
8. **Interfaz aislada:** panel en Shadow DOM **cerrado**, montado en el ancla (nunca dentro del cuerpo del mensaje), con hoja de estilos construible y sin atributos de eventos en línea.
9. **Segundo canal de confianza:** el nivel también se muestra en el indicador (*badge*) del icono de la extensión, que el contenido de un correo no puede falsificar.
10. **Minimización:** se extraen solo los seis campos del contrato y se envían solo esos.
11. **Control del usuario:** el interruptor «Verificación activada» detiene toda lectura y envío.
12. **Distribución:** se carga descomprimida solo desde el repositorio del equipo, tras revisar el código. No se instala desde otras fuentes ni se habilita en perfiles personales.
13. **El backend no confía en la extensión:** la API sigue validando todo, con límites de tamaño y de frecuencia (secciones 3 y 4). La extensión no es una frontera de autenticación.
14. **Iconos y estilos de la interfaz:** los iconos salen de `iconos/` y se validan en la construcción (sin `<script`, `<foreignObject`, atributos `on…=` ni referencias externas); los SVG se insertan con `DOMParser` e `importNode`, nunca con `innerHTML`. Los recursos del diseño (`Referencias/`) son solo material de consulta y no se incluyen en la extensión.
