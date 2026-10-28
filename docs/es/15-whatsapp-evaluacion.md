# 15 · WhatsApp como segundo canal — evaluación técnica

**Estado: solo evaluación. No hay nada implementado y la instalación básica no depende de WhatsApp.**
Escrito en octubre de 2026; la versión inglesa ([`docs/en/15-whatsapp-evaluation.md`](../en/15-whatsapp-evaluation.md))
es la de referencia. Lo verificado y cómo se indica en cada punto; precios y límites cambian a menudo y
hay que volver a comprobarlos antes de construir nada.

## Qué se busca

Los mismos avisos que llegan por Telegram ([14](14-sin-root-fiabilidad.md)) y unas pocas consultas de
solo lectura (estado, salud, historial) por WhatsApp, **además de** Telegram. El servidor debe arrancar,
funcionar, diagnosticarse y recuperarse sin él; si WhatsApp falla, Telegram sigue.

## A. Un puente independiente sobre WhatsApp Web (whatsmeow)

Referencia: [quauhtlimtz/whatsapp-mcp](https://github.com/quauhtlimtz/whatsapp-mcp), fork mantenido de
lharries/whatsapp-mcp. **Leído de su código (clonado el 27-10-2026):**

| Punto | Resultado |
|---|---|
| Estructura | Un programa Go (`whatsapp-bridge/main.go`, ~1 560 líneas) que habla con WhatsApp, más un servidor MCP en Python aparte. El puente funciona solo: no hace falta MCP para usarlo. |
| Librería | [whatsmeow](https://github.com/tulir/whatsmeow) (protocolo multidispositivo de WhatsApp Web, obtenido por ingeniería inversa; mantenida, último commit 27-10-2026). |
| Almacenamiento | SQLite con `mattn/go-sqlite3` → **necesita CGO y compilador de C**. `store/whatsapp.db` guarda las claves de sesión (= acceso a la cuenta); `store/messages.db`, el historial. |
| Interfaz | HTTP en `:<puerto>` = **todas las interfaces de red**, **sin autenticación**: `/api/send`, `/api/download`, `/api/monitor`. Cualquiera en la Wi-Fi de casa podría enviar mensajes en tu nombre. Así no sirve en un móvil servidor: habría que limitarlo a `127.0.0.1` y añadir un token, es decir, mantener un fork. |
| Inicio de sesión | Código QR desde la app de WhatsApp; reconecta sin QR mientras la sesión vale. Su README dice que puede pedir volver a vincular a los ~20 días y que WhatsApp caduca versiones viejas del cliente cada 3–4 meses (error 405) → hay que actualizar whatsmeow. |
| Herramientas | `go 1.26` en `go.mod`. |
| Condiciones | El propio README: automatizar una cuenta personal va contra las condiciones de WhatsApp y puede costar el bloqueo del número; usar un número dedicado y poco volumen. |

Viabilidad en los móviles del proyecto (**razonada, no medida**: el entorno de la evaluación no permitía
compilar código externo, así que RAM, CPU y tamaño son desconocidos):

* Go compila para `linux/arm` (ARMv7) y `linux/arm64`; un binario estático corre en Termux directamente o
  dentro del Debian. El obstáculo es SQLite con CGO: compilar en el móvil (`golang` + `clang` de Termux,
  pesado y lento) o pasar a un SQLite en Go puro (`modernc.org/sqlite`, con un fallo reportado en ARM de 32
  bits en una versión antigua, o `ncruces/go-sqlite3` sobre wasm), lo que exige cambiar código.
* Riesgos que no desaparecen: restricción o bloqueo de la cuenta, cambios de protocolo que lo rompen sin
  aviso, volver a vincular cada cierto tiempo y una base de datos tan sensible como la cuenta.

Otras librerías: **Baileys** (Node.js; mismo riesgo; Node existe en Termux) y **whatsapp-web.js** (maneja
Chromium con Puppeteer — descartada: demasiado pesada para ARMv7/proot y frágil).

## B. WhatsApp Business Platform (API oficial en la nube)

Datos de fuentes secundarias encontradas en la búsqueda; las páginas de Meta (developers.facebook.com) no
se pudieron abrir desde el entorno de la evaluación: **comprueba cada cifra allí**.

* Requiere una app de desarrollador de Meta y una cartera comercial, un número que no se use en la app
  normal de WhatsApp, un nombre visible aprobado, un token de acceso que mantener vigente y un medio de pago
  para los mensajes de pago.
* Desde el 1 de julio de 2025 se cobra **por mensaje**, según categoría (marketing, utilidad, autenticación)
  y país del destinatario; tarifas de utilidad vistas: desde una fracción de céntimo de dólar hasta unos
  céntimos. Las fuentes no coinciden en si las respuestas dentro de la ventana de 24 h siguen siendo gratis
  a finales de 2026.
* Un aviso lo inicia la empresa: fuera de la ventana de 24 h necesita una **plantilla aprobada**.
* Los mensajes entrantes llegan por **webhook**: Meta tiene que alcanzar una URL HTTPS pública. Un móvil
  tras el router de casa necesita un túnel (otro servicio, otra dependencia). No hay forma de consultar.

Veredicto: cumple las normas y es estable, pero cada usuario tendría que montar una cuenta comercial de Meta,
plantillas, un túnel para el webhook y quizá pagar. Demasiado para un proyecto comunitario por defecto; solo
como opción avanzada.

## C. Otras opciones

| Opción | Bidireccional | Coste / dependencia | Veredicto |
|---|---|---|---|
| **SMS por Termux:API** (`termux-sms-send`, `termux-sms-list`) | sí (leer la bandeja, solo del número del dueño) | una SIM con SMS; permiso de SMS de Termux:API; sin Internet | **El complemento más interesante**: funciona justo cuando no hay Internet, el caso en que Telegram (y WhatsApp) no pueden. Sin terceros. Sin probar aún. |
| CallMeBot (WhatsApp gratis a ti mismo) | no | servicio gratuito de terceros mantenido por un voluntario; usuarios reportan límites (~25 mensajes / 4 h), caídas y cambios de número | Vale como canal opcional, solo de envío, no crítico, para quien acepte que un tercero lea los avisos. |
| ntfy / Gotify | en parte | servidor público o propio; otra app | Ligero y gratis, pero no es WhatsApp. |
| Correo (SMTP) | en parte | una cuenta SMTP y su contraseña en el móvil | Sencillo, lento de notar. |
| Signal (signal-cli), puentes Matrix | sí | Java / un servidor: pesado | Descartado para móviles viejos. |
| Automatizar la interfaz de WhatsApp | — | — | Descartado: frágil, y la pantalla está apagada. |

## D. Arquitectura propuesta (cuando se añada un segundo canal)

1. **Un diagnóstico, varios canales.** `collect_problems()` ya da la lista de problemas. Cada canal tiene **su
   propia** instancia de `alerts.Alerts` y su archivo de estado (`alerts-<canal>.json`): un canal caído nunca
   bloquea al otro ni marca nada como entregado en su lugar; cada uno confirma sus propias entregas.
2. **Un canal es un adaptador `send(texto) -> bool`** (True solo si el servicio confirmó la entrega). Telegram
   va de serie; los demás viven en `/opt/bot/plugins/` y registran su adaptador, como los ganchos actuales.
3. **Un puente es un servicio aparte y opcional**, vigilado como los `SERVICES` (su proceso, sus logs, lo
   relanza el vigilante), accesible solo en `127.0.0.1` con un token aleatorio en un archivo `chmod 600`. El
   bot nunca lo espera al arrancar.
4. **Consultas entrantes**: solo de un remitente permitido (número / ID de chat), solo órdenes de lectura
   (`/estado`, `/salud`, `/historial`), con límite de frecuencia, sin texto libre que llegue a un shell y sin
   reinicios, actualizaciones ni borrados desde un canal secundario salvo que se activen a propósito.

## Recomendación

1. **No** meter WhatsApp en la instalación básica.
2. Siguiente paso con valor real: el adaptador multicanal de D (pequeño y comprobable) y luego un **canal SMS
   por Termux:API** como vía alternativa cuando no hay Internet — a validar en un móvil.
3. WhatsApp, si se quiere: un plugin opcional para **un número secundario dedicado**, primero solo de envío,
   con whatsmeow accesible solo en local, con token y SQLite en Go puro, y con el riesgo de bloqueo y la
   revinculación periódica escritos en la guía. Habrá que actualizarlo cada pocos meses. CallMeBot es la
   alternativa sin mantenimiento para quien acepte un tercero.
4. La API oficial, solo como opción avanzada para quien ya tenga una cuenta comercial de Meta.

Fuentes: los repositorios citados (código leído), el de whatsmeow, resúmenes de precios de Meta de Zoho,
CleverTap y otros sitios (octubre de 2026), testimonios de usuarios de CallMeBot en los foros de Homey y
simon42, y comparativas entre la API oficial y las librerías no oficiales.
