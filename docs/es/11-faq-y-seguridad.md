# 11 · FAQ y seguridad

## Seguridad

**Batería.** Una batería de litio vieja en el cargador 24/7 es el principal riesgo físico. Lee
[06](06-bateria-y-calor.md): mantenla entre 40–60 %, revísala cada mes, nunca uses una hinchada,
dale aire. Ante la duda, desenchufa y cámbiala.

**Rootear.** Puede borrar tus datos, anular la garantía e inutilizar el móvil. KingRoot (la ruta para
móviles con bootloader bloqueado) es software de código cerrado con reputación dudosa: úsalo solo
en un móvil dedicado y borrado, sin cuentas personales. Ver [02](02-root.md).

**Secretos.** El token del bot, las claves de API, las cookies y la sesión de Telegram son credenciales.
Viven en `/opt/bot` con modo 600, nunca en git. `.gitignore` excluye `config.sh`, `backup/` y los
nombres de archivo habituales; `make-image.sh` los deja fuera de la imagen. Si se filtra un token,
revócalo en @BotFather (`/revoke`) y pon uno nuevo con `tools/set-token.sh`.

**Quién controla el bot.** La primera cuenta que manda `/start` por privado queda como dueña.
Hazlo tú mismo justo después de activar el bot ([04](04-bot-telegram.md)). El bot ignora a todo el
que no esté autorizado, y se va de los grupos a los que lo añada alguien que no sea el dueño.

**Cookies.** Usa una cuenta secundaria, nunca la principal. Un archivo de cookies es una sesión
iniciada. El bot borra tu mensaje de subida tras guardarlo y deja el archivo en modo 600.

**Shizuku y depuración inalámbrica (modo sin root).** Shizuku da a Termux los poderes del usuario `shell` de Android (leer
el estado del sistema, `svc`, reiniciar, instalar/desinstalar apps): autoriza **solo a Termux**, y trata a cualquiera con
una clave SSH a tu Termux como si tuviera esos poderes. Mantén SSH solo con clave (`PasswordAuthentication no`) y en tu
red local. La depuración inalámbrica es una segunda puerta: empareja solo PCs que controles y nunca redirijas su puerto.

**Exposición de red.** Nada necesita un puerto de entrada. Mantén adb (:5555) en tu red local,
protegido por su clave RSA. No lo redirijas desde el router.

**Plugins y código.** Un plugin corre con los privilegios del bot. Instala solo plugins que hayas leído.

## Legal

* Descargar contenido de redes sociales puede infringir sus términos de servicio y, según lo que
  descargues y dónde vivas, la ley de derechos de autor. Este proyecto es una herramienta; **tú**
  eres responsable de lo que descargas y de tener derecho a hacerlo. Úsalo con contenido tuyo,
  con licencia para ello, o que de otro modo te esté permitido conservar.
* No lo uses para saltarte muros de pago, DRM o controles de acceso, ni uses cuentas ajenas.
* Los autores no dan ninguna garantía (ver [LICENSE](../../LICENSE)).

## Preguntas frecuentes

**¿Funciona sin root?**
Sí, en móviles modernos: [12 · Modo sin root](12-modo-sin-root.md) (Termux + proot + Shizuku), probado de punta a punta
en un Realme 12+. Pierdes el control del cargador y el soporte para móviles anteriores a ~Android 11. El modo root sigue
siendo la opción para los más viejos.

**¿Por qué ofrecer un chroot si proot funciona sin root?**
Velocidad nativa (proot traduce cada llamada al sistema), control directo del cargador y del Wi-Fi, y funciona en versiones
de Android que el Termux y el Shizuku actuales ya no soportan. En un móvil moderno, el modo sin root es más simple y casi
igual de rápido.

**¿Y los iPhone?**
No. iOS no puede correr esto.

**¿La pantalla puede estar apagada? ¿Necesito SIM?**
Pantalla apagada, sí (un wake-lock mantiene la CPU despierta). No hace falta SIM; solo Wi-Fi.

**¿Cuánta energía gasta?** Unos pocos watts, comparable a una computadora de placa única pequeña. Mídelo
con un medidor de consumo de enchufe; varía con el móvil y la carga.

**¿Cuánta gente puede usar el bot?** Tantos como autorices; las descargas corren de tres en tres
y el resto hace cola (`WORKERS` en `bot/bot.py`). Lo que de verdad carga un móvil de 2 núcleos
es el uso intenso de la transcripción de voz.

**¿Puedo correr otra cosa que no sea el bot?**
Sí. Tras la [05](05-servicios-y-arranque.md) tienes Debian en un chroot con vigilante y control de
carga. Deja `BOT_ENABLED` sin crear y usa los pasos de `tools/install.sh` como base para cualquier
servicio (`BOT_CMD` en `server.conf` puede ejecutar cualquier comando al arrancar).

**¿Cómo traduzco el bot?**
Los textos visibles están en español y viven en `bot/bot.py` (y en los plugins). Una capa de
traducción de verdad sería una gran contribución; mientras tanto puedes editar los textos directamente.

**El bot dice que mi móvil es «S4 mini» / tiene otra batería.**
`/opt/bot/device.json` personaliza los textos de `/estado`, `/bateria` y `/acerca`; copia
`phone/device.example.json` como `device.json` en la raíz del repositorio y ejecuta `tools/deploy.sh`.

**Funcionaba y después de semanas dejó de hacerlo.** Los sospechosos más probables, en orden: yt-dlp
necesita actualizarse (`/actualizar`), las cookies caducaron (`/cookies`), problemas de señal/punto
de acceso del Wi-Fi ([07](07-red.md)), una app o la ROM se actualizó sola, la batería se calentó
demasiado. `/salud` y `/historial` revisan todos.

## Créditos y licencias

Escrito por gente que necesitaba darles uso a móviles viejos. Construido sobre software libre excelente:
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [gallery-dl](https://github.com/mikf/gallery-dl)
(GPL-2.0, ejecutado como programa aparte), [Telethon](https://github.com/LonamiWebs/Telethon) (MIT),
[TgCrypto](https://github.com/pyrogram/tgcrypto) (LGPL-3.0), [ytmusicapi](https://github.com/sigma67/ytmusicapi) (MIT),
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT), [Vosk](https://alphacephei.com/vosk/) (Apache-2.0),
Debian, busybox (GPL-2.0), Magisk (GPL-3.0). El código de este repositorio tiene licencia MIT.
Revisa la licencia de cada herramienta que instales.
