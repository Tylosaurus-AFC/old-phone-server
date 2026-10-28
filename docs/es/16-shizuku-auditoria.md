# 16 · Shizuku sin root — auditoría, compatibilidad y matriz de recuperación

Octubre de 2026. Versión española de [`docs/en/16-shizuku-audit.md`](../en/16-shizuku-audit.md) (manda la
inglesa si difieren). Etiquetas de evidencia: **[src]** leído en el código fuente (repositorio y versión
indicados), **[wiki]** la wiki del propio fork, **[doc]** documentación de Android, **[sim]** cubierto por una
prueba automática con simuladores (no un móvil), **[V]** verificado en un móvil real (solo lo que la guía del
proyecto ya recogía del Realme 12+ 5G, Android 16, fork 13.7.0). Nada de esta página se verificó en un móvil
durante esta auditoría.

## Qué Shizuku

| | Shizuku oficial | Fork de thedjchi |
|---|---|---|
| Origen | [RikkaApps/Shizuku](https://github.com/RikkaApps/Shizuku) — última versión **v13.6.0 (25-05-2025)**, último commit 18-06-2025 [src] | [thedjchi/Shizuku](https://github.com/thedjchi/Shizuku) — versiones `v13.6.0.rNNNN-thedjchi` … **v13.7.0-thedjchi**; último commit 14-07-2026; el autor ha pausado el mantenimiento [src] |
| Paquete | `moe.shizuku.privileged.api` | **el mismo** `moe.shizuku.privileged.api` [src] |
| Cómo distinguirlas | `versionName` del tipo `13.6.0.r<commits>.<hash>` | el `versionName` termina en `-thedjchi` [src]; firma distinta: hay que desinstalar una para instalar la otra |
| `versionCode` | número de commits de git (`gitCommitCount`) [src] | mismo esquema, otros números [src] |
| Formas de iniciar | root; depuración inalámbrica (Android 11+); adb desde PC | las mismas y además **modo TCP** (equivale a `adb tcpip`) [src][wiki] |
| Arranque al encender sin root | **Android 13+** y `WRITE_SECURE_SETTINGS`: un intento en `LOCKED_BOOT_COMPLETED`/`BOOT_COMPLETED`, enciende la depuración inalámbrica, espera **3 s** al puerto por mDNS, sin esperar al Wi-Fi ni reintentar [src v13.6.0 `BootCompleteReceiver`] | Android 11+ y `WRITE_SECURE_SETTINGS`: una tarea de WorkManager tras `BOOT_COMPLETED` que **espera al Wi-Fi**, enciende la depuración inalámbrica, busca el puerto por mDNS (15 s) y **reintenta** [src `AdbStartWorker`]; «puede tardar unos minutos» [wiki] |
| Antes del primer desbloqueo | su receptor de arranque es `directBootAware` (puede iniciar Shizuku antes de desbloquear) [src] | solo tras desbloquear (`BOOT_COMPLETED`) [src] |
| Watchdog (reiniciar si el servicio muere) | no | sí, servicio en primer plano opcional [src][wiki] |
| Intents para otras apps | ninguno para iniciarla | `ManualStartReceiver` exportado, acción `moe.shizuku.privileged.api.START` (y STOP), extra `auth` = un secreto que aparece en *View intents* [src] |

**Consecuencia para el proyecto**: el rearranque automático desde el servidor (`SHIZUKU_AUTH`,
`shizuku.sh start`) solo existe con el fork. El vigilante anota qué variante ve (`variant=` en
`/opt/bot/sys/shizuku`) y nunca manda START a la oficial [sim]; `doctor.sh` indica la variante y sus límites [sim].

## Tres operaciones distintas

1. **Iniciar el servicio de Shizuku sin root** — Shizuku se conecta al demonio adb del propio móvil
   (depuración inalámbrica, o `adb` desde un PC) y ejecuta su servidor como usuario `shell`. Requiere la
   depuración inalámbrica emparejada una vez (código de emparejamiento) o un PC. El servicio es un proceso:
   **muere en cada reinicio**, al apagar la depuración USB o las opciones de desarrollador y —según el fork—
   al cambiar el modo USB (Android Auto por cable, cambiar el modo USB) [wiki].
2. **Recuperarlo tras un reinicio** — alguien tiene que volver a iniciarlo: la app al arrancar (arriba), la
   tarea o el watchdog del fork, la orden START del servidor (fork) o el usuario. Condiciones: Android 11+
   (fork) / 13+ (oficial), `WRITE_SECURE_SETTINGS`, que Shizuku se iniciara la última vez por adb (no por
   root), Wi-Fi conectado y la red **autorizada** para la depuración inalámbrica.
3. **Volver a activar / autorizar la depuración inalámbrica** — encenderla es un ajuste (`adb_wifi_enabled`):
   Shizuku con `WRITE_SECURE_SETTINGS` puede hacerlo [src], Termux no (no tiene permiso). **Autorizar una red**
   («Permitir siempre en esta red») es un diálogo que solo puede contestar una persona. Android 11–12 olvidan
   las redes permitidas en cada reinicio; Android 13 lo corrigió (cambio de AOSP 2128832, citado en el código de
   ambas apps; el fork avisa de ello) [src]. Volver a emparejar tras «Revocar autorizaciones de depuración USB»
   o un restablecimiento también exige a una persona.

## Permisos

| Permiso / ajuste | Cómo se concede | ¿Sobrevive al reinicio? | Notas |
|---|---|---|---|
| `WRITE_SECURE_SETTINGS` para Shizuku | una vez desde un PC: `adb shell pm grant moe.shizuku.privileged.api android.permission.WRITE_SECURE_SETTINGS` [wiki] | sí: un permiso de desarrollo concedido se mantiene hasta desinstalar o borrar datos (modelo de permisos de Android; no verificado en el Realme) | MIUI necesita «Depuración USB (ajustes de seguridad)»; ColorOS/Realme, «Desactivar supervisión de permisos» [wiki] |
| Termux autorizado en Shizuku | Shizuku → Aplicaciones autorizadas | sí (lo guarda Shizuku) | si se revoca, rish dice «Permission denied» [src] |
| Tiempo de espera de autorización adb desactivado | Opciones de desarrollador → «Desactivar tiempo de espera de autorización de adb», o Shizuku pone `adb_allowed_connection_time=0` al iniciarse con `WRITE_SECURE_SETTINGS` [src] | sí (ajuste global) | si no, las claves adb sin usar caducan a los días y el siguiente inicio falla [wiki] |
| Batería: Shizuku sin restricciones, segundo plano permitido | Ajustes, o `cmd appops set moe.shizuku.privileged.api RUN_IN_BACKGROUND/RUN_ANY_IN_BACKGROUND allow` [wiki] | normalmente; algunos fabricantes los restablecen | el vigilante los reaplica por Shizuku cada 30 min [sim] |

Termux, Termux:Boot y Termux:API se compilan con **targetSdk 28** [src `gradle.properties` de termux-app/boot/api]:
las restricciones de Android 14–16 ligadas a un targetSdk más nuevo (tipos de servicio en primer plano, límites
de Android 15 al arrancar) no les afectan; Doze, App Standby, el phantom process killer y los gestores de los
fabricantes, sí. Termux:Boot no es `directBootAware`: nada del servidor corre antes del primer desbloqueo [src].

## Matriz de recuperación

«Sola» = se recupera sin una persona, si se cumplen las condiciones indicadas.

| Escenario | Lo detecta | ¿Se recupera sola? | Acción mínima del usuario |
|---|---|---|---|
| Reinicio normal, Android 13–16, fork, WSS concedido, red autorizada | vigilante (`state=`), `/historial` | **sí** — la tarea del fork tras el Wi-Fi [src]; [V] en Realme Android 16 (bot a los 54–104 s) | — |
| Reinicio normal, Android 13–16, oficial v13.6.0 | igual | **un solo intento**; falla si el Wi-Fi no está listo a los pocos segundos del arranque [src] | abrir Shizuku → Iniciar |
| Reinicio normal, Android 11–12(L) | igual | **no**: hay que volver a permitir la red en cada reinicio [src] | desbloquear y pulsar **Permitir**; Shizuku arranca después |
| Reinicio con PIN/patrón/contraseña, antes del primer desbloqueo | no puede correr nada (datos de Termux cifrados) | **no** [doc] | desbloquear una vez |
| Servicio de Shizuku caído / parado | `shizuku.sh probe` → `not-running` [sim] | fork: su watchdog [src] y la orden START del servidor con `SHIZUKU_AUTH` (2, 5, 10, 30 min…) [sim]; oficial: no | oficial: abrir Shizuku → Iniciar |
| Shizuku parado a propósito por el usuario | igual | el watchdog del fork / nuestro START lo reiniciarían [wiki] | pararlo con el intent STOP y `touch ~/server/no-shizuku-restart` [sim] |
| App Shizuku congelada / forzada a detenerse | rish «Request timeout» → `app-unreachable` [sim] | el aviso START con `--include-stopped-packages` puede despertarla (fork) — sin verificar | abrir Shizuku una vez; batería sin restricciones |
| Termux sin autorizar en Shizuku | rish «Permission denied» → `not-authorized` [sim] | no | Shizuku → Aplicaciones autorizadas → Termux |
| Diálogo de permiso esperando en pantalla | rish se queda tras «Entering shell» → `awaiting-permission` [sim] | no | desbloquear y pulsar Permitir |
| Depuración inalámbrica apagada (usuario, o Android tras cambiar de red) con Shizuku en marcha | doctor (`adb_wifi_enabled`), guard.sh | guard.sh (corre como usuario `shell`, lanzado vía Shizuku) la vuelve a encender cada minuto **mientras guard.sh siga vivo** [src del proyecto]; que guard.sh y el servicio sobrevivan al apagado está **sin verificar** | — |
| Cambio de red / IP / puerto | — | el puerto se busca por mDNS en cada inicio, sin IP ni puerto fijos [src]; una **red nueva sin permitir** bloquea el inicio; con el móvil bloqueado el fork espera al desbloqueo [src] | permitir la red nueva una vez |
| Autorización adb perdida (revocada, caducada, restablecimiento) | el inicio falla en silencio; probe → `not-running` | no | volver a emparejar Shizuku por depuración inalámbrica |
| Cambio de modo USB (cable a un PC/hub, Android Auto) | probe → `not-running` | watchdog del fork / nuestro START [wiki][sim] | poner *Configuración USB predeterminada* en «Solo carga» |
| Termux detenido o eliminado | guard.sh (sin `sshd` 2 min) | **sí con Shizuku**: guard.sh reabre Termux [V en Realme: 2 min 9 s] | — |
| Termux:Boot nunca abierto / forzado a detenerse | doctor (`stopped=`/`notLaunched=`) [sim] | **no** [doc] | abrir Termux:Boot una vez |
| Falta `WRITE_SECURE_SETTINGS` | doctor (`dumpsys package`) [sim] | no | el comando `pm grant` desde un PC |
| Restricciones de batería en Termux o Shizuku | doctor [sim] | se reaplican cada 30 min mientras Shizuku funciona [sim]; un rechazo se avisa una vez | Ajustes → Batería → Sin restricciones |

Por versión de Android:

| | Android 11 | Android 12–12L | Android 13–14 | Android 15–16 |
|---|---|---|---|---|
| Depuración inalámbrica (Shizuku sin PC) | sí | sí | sí | sí |
| Arranque desatendido tras reiniciar | no (pulsar Permitir) | no (pulsar Permitir) | fork: sí; oficial: un intento | fork: sí [V Realme 16]; oficial: un intento |
| Phantom process killer | — | 12: límite (se reaplica); 12L: ajuste | ajuste | ajuste; opción de desarrollador «Desactivar restricciones de procesos secundarios» (14+) |
| Verificado en un móvil | — | — | — | Realme 12+ 5G, Android 16, fork 13.7.0 (guía del proyecto) |

## Qué recoger en un móvil (solo lectura, se puede compartir)

Desde un PC con adb (USB o inalámbrico). Solo muestran versiones y estados; **no compartas** `SHIZUKU_AUTH`,
códigos de emparejamiento, direcciones IP, números de serie ni claves adb.

```bash
adb shell getprop ro.build.version.release; adb shell getprop ro.build.version.sdk
adb shell getprop ro.build.display.id                      # compilación de la ROM, p. ej. RMX3867_...
adb shell "dumpsys package moe.shizuku.privileged.api | grep -E 'versionName|versionCode|WRITE_SECURE_SETTINGS'"
adb shell cmd appops get moe.shizuku.privileged.api RUN_ANY_IN_BACKGROUND
adb shell "dumpsys deviceidle whitelist | grep -E 'shizuku|termux'"
adb shell settings get global adb_wifi_enabled
adb shell settings get global adb_allowed_connection_time
adb shell "dumpsys package com.termux.boot | grep -E 'versionName|stopped=|notLaunched='"
adb shell "dumpsys package com.termux | grep -E 'versionName|targetSdk'"
```

Con el servidor instalado desde la rama de desarrollo, `tools/noroot-doctor.sh` muestra casi todo esto. Después,
para comprobar la recuperación (cada paso es reversible): (1) en Shizuku pulsa Detener, espera 3 min y ejecuta el
doctor; (2) reinicia con el bloqueo de pantalla que uses normalmente, anota cuándo vuelven Shizuku y el bot y
desbloquea si hace falta; (3) apaga la depuración inalámbrica 2 min y mira si Shizuku y guard.sh se recuperan.
