# 12 · Modo sin root (Termux + proot + Shizuku)

Para móviles que **no puedes rootear** (bootloader bloqueado sin forma de desbloquearlo, un fabricante
que se niega, o simplemente no quieres). El mismo Debian, el mismo bot, la misma idea de vigilante — pero
corriendo dentro de **Termux** en vez de un chroot, con **Shizuku** dando los pocos poderes de sistema que
necesita el vigilante.

Se construyó y probó de punta a punta en un **Realme 12+ 5G** (Android 16, Realme UI 7, Dimensity 7050,
bootloader bloqueado: el intento de root falló). Todo lo de esta página se verificó ahí.

## ¿Modo root o modo sin root?

| | Modo root (chroot) | **Modo sin root (Termux + proot)** |
|---|---|---|
| Necesita | root ([02](02-root.md)) | nada especial; se recomienda Android **13+** (11–12 funcionan, pero tras cada reinicio hay que pulsar *Permitir* para la depuración inalámbrica) |
| Velocidad | nativa | proot añade coste por llamada al sistema; en un móvil moderno no se nota (Realme: mismos tiempos de descarga que la tablet con root) |
| Control de carga | el script conmuta el cargador | **solo el límite del propio fabricante** (p. ej. «limitar al 80 %»); el script lo informa |
| Leer batería, Wi-Fi, tiempo encendido | directo de `/sys`, `iw` | las apps no pueden: lo lee Shizuku y `charge.sh` se lo pasa al bot |
| Reiniciar / reiniciar Wi-Fi desde el bot | sí | sí **con Shizuku**; sin él, no se puede reiniciar el móvil |
| Sobrevive a un reinicio | lanzador de arranque como root | Termux:Boot (hay que abrirlo una vez a mano) |
| Android mata apps en segundo plano | no | *puede*: el guardián vuelve a abrir Termux (probado) |
| Móviles viejos | **sí, hasta Android 4.4** | no: Termux pide Android 7+, que Shizuku arranque solo tras reiniciar pide 13+ (11–12: un toque en cada reinicio) |

Regla práctica: **móvil viejo (≤ Android 10) → modo root. Móvil moderno que no puedes o no quieres
rootear → esta página.** (Para un servidor sin root y sin bot, mira también los proyectos de
[00 · Resumen](00-resumen.md).)

## Cómo funciona

```
 Android (sin root, pantalla apagada, enchufado)
  │
  ├─ Termux:Boot ─► 00-server.sh   wake-lock · sshd (:8022) · bot.sh · bucle de charge.sh
  │                    │
  │                    ├─► bot.sh      reinicia el bot con esperas crecientes (como en modo root)
  │                    └─► charge.sh   cada minuto: lee batería/Wi-Fi/uptime A TRAVÉS DE SHIZUKU y lo
  │                                    escribe en /opt/bot/sys; señal de vida; Wi-Fi/Internet;
  │                                    /reiniciar; servicios opcionales del disco USB
  │
  ├─ Shizuku (poderes del usuario shell, arranca solo al encender por depuración inalámbrica)
  │     └─ guard.sh  corre como usuario shell: si Android cierra Termux, lo vuelve a abrir
  │
  └─ Termux → contenedor de proot-distro «bot» = Debian 13 → /opt/bot  (bot.py + plugins)
       enter.sh monta /opt/bot/sys/{battery,uptime,loadavg} donde el bot los espera,
       así que bot.py es exactamente el mismo archivo que en modo root
```

¿Por qué Shizuku? Una app normal no puede leer `/sys/class/power_supply`, ejecutar `svc wifi` ni reiniciar.
Shizuku corre un pequeño servicio con los permisos del usuario `shell` de Android (el que tiene `adb shell`)
y deja que Termux le pida comandos con `rish`. ¿Y por qué no la depuración inalámbrica a sí mismo? Android
apaga la depuración inalámbrica cada vez que el móvil salta entre puntos de acceso (router ↔ repetidor):
*«Detected wifi network change. Disabling adbwifi»*. El servicio de Shizuku sigue vivo.

## Instalación, paso a paso

Los comandos del PC son `tools/noroot-*.sh`; hablan con Termux por **SSH** (puerto 8022), no por adb.

### 1. Instala las apps de Termux (no desde Google Play)

Instala **Termux**, **Termux:Boot** y **Termux:API** de la misma fuente — las tres tienen que estar firmadas
con la misma clave para compartir usuario. Usa las [versiones de GitHub](https://github.com/termux/termux-app/releases)
o F-Droid. (La compilación de Google Play ya no se mantiene.) Las versiones probadas fueron las compilaciones de
GitHub: Termux 0.118.3, Boot 0.8.1, API 0.53.0, instaladas con `adb install -g` (lo que además les concede
`WRITE_SECURE_SETTINGS`). Abre Termux:Boot **una vez** a mano.

### 2. Evita que Android mate Termux

* *Ajustes → Apps → Termux → Batería*: **sin restricciones / permitir actividad en segundo plano** (cubre
  las tres apps: comparten usuario).
* Desde tu PC con adb (USB o inalámbrico), una vez:
  ```bash
  adb shell dumpsys deviceidle whitelist +com.termux
  adb shell settings put global settings_enable_monitor_phantom_procs false
  adb shell device_config put activity_manager max_phantom_processes 2147483647
  ```
  Las dos últimas impiden que Android 12+ mate los procesos hijos de Termux.
* Ajustes de energía del fabricante: apaga la «optimización de espera durante el sueño» (Realme: *Batería →
  Ajustes de ahorro de energía*), desactiva las actualizaciones automáticas del sistema y «actualizar de noche».
* **Opciones de desarrollador → Depuración inalámbrica: activada**, y «Desactivar tiempo límite de
  autorización de adb».
* Solo Realme/OPPO: **Opciones de desarrollador → Disable permission monitoring: On** (sin eso ColorOS limita
  los permisos de adb/Shizuku).

### 3. SSH a Termux

En Termux: `pkg install openssh`, luego `whoami` (es `u0_aNNN`) y `sshd`. En tu PC:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/phone_ed25519          # sin frase de paso si los scripts deben correr solos
# pon la línea .pub en ~/.ssh/authorized_keys del móvil (escríbela en Termux, o desde un PC con
# adb:  adb shell run-as com.termux ... — las apps de GitHub son compilaciones debug, así que run-as funciona)
```

`~/.ssh/config` en el PC:

```
Host phone
    HostName 192.168.1.50       # la IP del móvil; resérvala en tu router
    Port 8022
    User u0_a123                # lo que dijo `whoami` en Termux
    IdentityFile ~/.ssh/phone_ed25519
```

Pon `NOROOT_SSH=phone`, `NOROOT_IP=…` en `config.sh`. En `$PREFIX/etc/ssh/sshd_config` pon
`PasswordAuthentication no` (solo clave). `ssh phone echo ok` debe funcionar.

### 4. Shizuku

1. Instala el **fork de thedjchi de Shizuku** (GitHub `thedjchi/Shizuku`; probado: 13.7.0). La Shizuku oficial
   (v13.6.0, mayo de 2025) también arranca al encender por depuración inalámbrica en Android 13+, pero lo
   intenta una sola vez, nada más arrancar y sin esperar al Wi-Fi; el fork espera al Wi-Fi, reintenta, tiene
   watchdog y un aviso START. Las dos usan el mismo paquete, `moe.shizuku.privileged.api` (la versión del fork
   termina en `-thedjchi`); están firmadas distinto, así que para cambiar hay que desinstalar la otra antes.
2. En Shizuku: *Iniciar por depuración inalámbrica* (empareja una vez) y activa **iniciar al arrancar**.
3. En Shizuku: *Usar Shizuku en apps de terminal* → exporta `rish` y `rish_shizuku.dex`; autoriza a **Termux**.
4. Copia los dos archivos a una carpeta de tu PC y ejecuta:
   ```bash
   tools/noroot-install.sh rish ruta/a/la/carpeta    # imprime «test: uid=2000(shell)…» cuando funciona
   ```
   (Android 14+ exige que el `.dex` sea de solo lectura y esté en el directorio propio de la app: el script lo hace.)
5. Para que Shizuku vuelva **solo** (detalles y límites en [14](14-sin-root-fiabilidad.md#shizuku-qué-se-puede-recuperar-y-qué-no)):
   * desde el PC, una vez: `adb shell pm grant moe.shizuku.privileged.api android.permission.WRITE_SECURE_SETTINGS`
     (el fork lo necesita para encender la depuración inalámbrica al arrancar);
   * Ajustes → Apps → **Shizuku** → Batería → **Sin restricciones** (si está congelada, `rish` no responde);
   * en los ajustes de Shizuku activa su **watchdog** y copia el valor `auth` que aparece en **View intents**
     en `~/server/server.conf` como `SHIZUKU_AUTH=…`: así el vigilante del servidor puede pedirle que arranque
     (**experimental**: solo el fork de thedjchi, de momento probado en simulación, no en un móvil);
   * cuando Android pregunte si permitir la depuración inalámbrica en tu Wi-Fi, elige **Permitir siempre en esta red**.

Sin Shizuku el vigilante sigue funcionando: recurre a Termux:API para la batería y el Wi-Fi, y el
`/reiniciar confirmar` del bot avisa de que no puede reiniciar el móvil.

### 5. Debian + el bot

```bash
tools/noroot-install.sh check             # ¿puede este móvil? se para con Android < 7 o < 1 GB libre
tools/noroot-install.sh packages          # proot-distro, openssh, termux-api, jq…
tools/noroot-install.sh container         # Debian 13 en un contenedor de proot-distro («bot»; desde Docker Hub)
tools/noroot-install.sh provision         # entorno Python, yt-dlp, ffmpeg…  (el mismo script que en modo root)
tools/noroot-install.sh scripts           # ~/server/*.sh, server.conf, gancho de Termux:Boot
tools/noroot-bot.sh token                 # token de @BotFather
tools/noroot-deploy.sh                    # código del bot + plugins + scripts
tools/noroot-bot.sh enable                # ¡a andar!; luego /start en Telegram: eres el dueño
```

Verificado desde cero en el Realme para esta versión: `container` (la imagen `debian:trixie` de Docker Hub) tardó uno o dos
minutos, `provision` **7 min 25 s**, y las 24 pruebas unitarias del bot pasaron después dentro del contenedor nuevo
(Python 3.13.5, aarch64); el `charge.sh`, `sa.sh` y `enter.sh` genéricos se probaron contra el Shizuku real (batería,
Wi-Fi, disco USB, montajes).

Notas:

* `container` acepta un archivo rootfs en vez de la imagen de Docker: `tools/noroot-install.sh container
  ruta/a/imagen.tar.gz` (por ejemplo una imagen arm64 hecha con `tools/make-image.sh` en un móvil con root; así se
  construyó el Realme original).
* Edita `~/server/server.conf` en el móvil (`ssh phone nano ~/server/server.conf`): `OEM=oplus` para
  Realme/OPPO/OnePlus, `CONTAINER`, y los opcionales `SERVICES`/`NIGHTLY` de [13 · Recetas multimedia](13-recetas-multimedia.md).
* Notas de voz: `tools/noroot-install.sh voice`.
* `tools/noroot-deploy.sh` es el equivalente de `tools/deploy.sh`; el bot es el mismo código.

### 6. El límite de carga — a mano

Sin root nada de aquí puede conmutar el cargador. Activa el limitador del propio fabricante (Realme: *Ajustes →
Batería → Salud de la batería → Límite de carga personalizado → 80 %*; «Proteger batería» de Samsung; «Limitar al
80 %» de Pixel; «Protección de batería» de Xiaomi). `charge.sh` nota «enchufado pero sin cargar» y lo informa como
carga en pausa, así que `/estado` y `/bateria` dicen *«en pausa, vive del cargador»* y los apagones se detectan
igual que en modo root. Lee [06 · Batería y calor](06-bateria-y-calor.md): los consejos de seguridad son idénticos.

### 7. Quitar basura (opcional)

`adb shell pm uninstall -k --user 0 <paquete>` quita una app **para el usuario actual sin borrarla del sistema**:
se revierte con `adb shell cmd package install-existing <paquete>`. Al Realme se le quitaron 142 paquetes; nueve
los protege ColorOS y no se pueden quitar ni desactivar desde adb (`co.sitic.pp`, `com.coloros.assistantscreen`,
`com.coloros.bootreg`, `com.coloros.lockassistant`, `com.nearme.instant.platform`, `com.oplus.aiunit`,
`com.oplus.ota`, `com.oplus.pay`, `com.oplus.sau`). Conserva: la app de batería, Ajustes, el lanzador, SystemUI,
Wi-Fi/red, el controlador de permisos, WebView, el teclado y Google Play Services si quieres apps de Google.
Realme además bloquea desde adb `cmd appops set`, `pm grant` y `pm disable-user` para las apps Oplus protegidas:
cámbialo en la interfaz de Ajustes (`~/server/ui.sh dump` / `ui.sh tap "Texto"` pueden manejar la pantalla).

## Qué hacen los scripts

| Archivo (`~/server/`) | Función |
|---|---|
| `boot.sh` → `~/.termux/boot/00-server.sh` | al encender: wake-lock, `sshd`, `bot.sh`, el bucle de `charge.sh` |
| `bot.sh` | reinicia el bot con esperas 10 s → 10 min (igual que en modo root) |
| `charge.sh` | vigilante. Escribe batería/uptime/Wi-Fi en `/opt/bot/sys`; señal de vida (5 min congelado → mata); `/reiniciar`; recuperación de Wi-Fi/Internet; lanza `guard.sh`; servicios opcionales del disco USB |
| `enter.sh` | `proot-distro login` con los montajes de `/opt/bot/sys` (y el disco USB en `/mnt/disk`) |
| `sa.sh 'órdenes'` | ejecuta órdenes como usuario shell por `rish` y devuelve la salida de forma fiable (ver abajo) |
| `guard.sh` → `/data/local/tmp/srv-guard.sh` | guardián del lado shell: mantiene encendida la depuración inalámbrica; si el `sshd` de Termux falta 2 vueltas, abre la ventana de Termux para que `~/.bashrc` reinicie el servidor |
| `doctor.sh` | comprobación de solo lectura: OK/WARN/FAIL con qué hacer (`tools/noroot-doctor.sh` desde el PC; cada hora en `/salud`). Ver [14](14-sin-root-fiabilidad.md) |
| `ui.sh` | tocar y leer la pantalla del propio móvil por Shizuku |
| `server.conf` | ajustes (nombre del contenedor, `OEM`, servicios, trabajo nocturno, `NET_HOSTS` para comprobar Internet, `KEEPALIVE`) |

### Trampas que costaron tiempo de verdad (para que te las saltes)

* **`rish` pierde líneas de la salida al azar y no devuelve códigos de salida.** `sa.sh` hace que el lado shell
  escriba en un archivo del almacenamiento compartido y lo lee de ahí. Las órdenes `cmd` (`settings`, `pm`,
  `cmd wifi`) fallan si su salida *es* ese archivo: ponlas dentro de `$(…)` o de una tubería con `2>&1`.
* **Dentro de scripts llama siempre a `rish`/`sa.sh` con `</dev/null`**: `rish` lee la entrada estándar y se
  come el resto del script.
* **`guard.sh` tiene que vivir en su propia sesión (`setsid`).** Si cuelga del `rish` que lo lanzó, Shizuku lo
  mata junto con Termux. Así murió exactamente el primer guardián.
* **Termux:Boot hay que abrirlo a mano una vez.** La primera prueba de reinicio falló por eso.
* `pkill -f patrón` dentro de `ssh host "…"` se mata a sí mismo (la línea de comandos contiene el patrón):
  escribe `[p]atrón`.
* **Android puede cerrar Termux** (pasó una vez en una noche). `guard.sh` lo reabre; una prueba con
  `am force-stop com.termux` recuperó SSH y el bot en **2 min 9 s**.

## Supervisión, probada (Realme)

| Prueba | Resultado |
|---|---|
| `kill -9` al bot | `bot.sh` lo relanza en **11 s** |
| muere `bot.sh` | `charge.sh` lo relanza; bot de vuelta en **31 s** |
| bot congelado (`kill -STOP` al bot **y a su proot**) | se mata a los **302 s** sin señal de vida y se relanza 10 s después |
| `/reiniciar confirmar` (por Shizuku) | el móvil se apaga a los 45 s, Android arriba a los 85 s, SSH a los 100 s, **bot en marcha a los 104 s**; Shizuku ~70 s tras el arranque y Doze vuelve a quedar apagado solo |
| `am force-stop com.termux` | SSH y bot de vuelta en **2 min 9 s** |
| corte de Internet de 90 s | el bot informa «sin conexión de 07:49 a 07:51» |
| reinicio con todos los extras activados | SSH y bot a los **54 s**, Jellyfin a los 78 s, depuración inalámbrica otra vez activa a los 2 min 45 s |

Prueba completa de funciones con el bot de pruebas: enlaces (YouTube, Instagram, Facebook, TikTok, Dailymotion),
carruseles, `/original`, `/mp3`, subidas grandes por MTProto, bajar a 720p si pasa de 2 GB, caché, seis descargas
en paralelo, reanudar tras un reinicio, notas de voz, `/pdf`, `/sticker`, `/seguir`…`/dejar`, `/actualizar`,
`/estado`, `/bateria`, `/salud`, `/velocidad`, `/reiniciar wifi|confirmar` — todo OK. **Sin cubrir todavía:** un
corte de luz real, grupos, y varios días seguidos sin intervención.

## Control remoto sin tocar el móvil

* `ssh phone` (solo clave).
* adb inalámbrico desde tu PC: empareja una vez, `guard.sh` lo mantiene encendido; `tools/noroot-adb.sh` encuentra
  el puerto cambiante (mDNS, o un barrido de 30000–50000) y conecta:
  `adb -s "$(tools/noroot-adb.sh | tail -1)" shell …`. Tras apagarlo a mano, el PC reconectó solo en 51 s.
* Si Termux está caído: `adb … shell am start -n com.termux/.app.TermuxActivity` (o `reboot`).

## Pasar de un modo a otro

Los respaldos son intercambiables: `tools/backup.sh` (root) o `tools/noroot-backup.sh`, y luego
`tools/noroot-restore.sh backup/<fecha>` (o `tools/restore-config.sh` en un móvil con root). **Apaga antes el bot
en el móvil viejo** — el mismo token en dos móviles da el error 409 de Telegram y descargas duplicadas.

**Comprueba la instalación** cuando quieras con `tools/noroot-doctor.sh`. Qué puede seguir parando el
servidor, qué vuelve a aplicar solo el vigilante (exenciones de batería, el «phantom process killer»…) y
cómo probarlo durante días: [14 · Sin root 24/7](14-sin-root-fiabilidad.md).

Siguiente: [13 · Recetas multimedia](13-recetas-multimedia.md) (un NAS y servidor multimedia en el mismo móvil).
