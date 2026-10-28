# 14 · Modo sin root: funcionar 24/7 — límites, defensas, comprobaciones

Esta página explica **qué puede parar un servidor sin root**, qué hace el proyecto con cada causa,
qué tienes que hacer tú a mano y cómo comprobarlo. Complementa a [12 · Modo sin root](12-modo-sin-root.md)
(la guía de instalación). La versión inglesa ([`docs/en/14-no-root-reliability.md`](../en/14-no-root-reliability.md))
es la de referencia si difieren.

**Primero, la verdad.** Android está hecho para parar el trabajo en segundo plano y ahorrar batería.
Sin root nada puede *garantizar* que Android o el fabricante nunca paren Termux. Lo que el proyecto sí
hace: pedir todas las exenciones que Android ofrece, volver a aplicar las que se deshacen, notar cuando
algo se para, recuperarlo cuando el sistema lo permite y decirte claramente cuando no puede. Solo un
móvil (Realme 12+ 5G, Android 16) se ha probado de punta a punta; mira la matriz de abajo.

## Comprobación rápida: `doctor.sh`

```bash
tools/noroot-doctor.sh            # desde el PC
~/server/doctor.sh                # o en Termux, en el móvil
```

Es de solo lectura y marca cada requisito como **OK**, **WARN** (funciona, pero menos fiable o sin
alguna función) o **FAIL** (el servidor no funcionará o no volverá tras un reinicio), cada uno con qué
hacer. Primera línea: `RESULT: ok | degraded | broken`. El vigilante lo ejecuta cada hora (la primera
vez a los 10 min de arrancar) y el bot muestra el peor problema en **`/salud`** («Android/Termux») y la
lista completa en **`/diagnostico`**.

Comprueba: versión de Android y CPU; de dónde viene Termux (avisa si es de Google Play); el arranque
automático, la sintaxis de `server.conf`, el contenedor Debian y el Python del bot; el token si el bot
está activado; vigilante, servicio del bot y señal de vida; `sshd`; espacio libre; y a través de
Shizuku: Termux:Boot instalado y **no «detenido»** (nunca abierto o forzado a detenerse → no arranca al
encender), Termux:API, exención de la optimización de batería, actividad en segundo plano permitida,
grupo de espera de la app, el «phantom process killer», el wake lock de Termux y la depuración inalámbrica.

## Qué puede parar el servidor y qué pasa

| Causa | Lo detecta | Lo previene | ¿Se recupera solo? | Tienes que |
|---|---|---|---|---|
| **Doze / optimización de batería** congela Termux con la pantalla apagada | doctor (Shizuku) | batería de Termux «Sin restricciones»; el vigilante vuelve a meter las apps de Termux en la lista blanca de Doze y ejecuta `dumpsys deviceidle disable` cuando aparece Shizuku y cada 30 min | sí, con Shizuku | poner «Sin restricciones» una vez (paso 2 de [12](12-modo-sin-root.md)) |
| **Grupo de espera** «raro/restringido» limita tareas y red | doctor | el vigilante pone el grupo `active` cada 30 min | sí, con Shizuku | — |
| **Actividad en segundo plano** denegada (`RUN_ANY_IN_BACKGROUND`) | doctor | el vigilante la pone en `allow` | sí, con Shizuku | — |
| **Phantom process killer** (Android 12+) mata procesos de Termux: más de 32 hijos *sumando todas las apps* o «uso excesivo de CPU» | doctor | 12L+: `settings_enable_monitor_phantom_procs=false` (también la opción de desarrollador «Desactivar restricciones de procesos secundarios»); 12: se sube `max_phantom_processes`. Se vuelve a aplicar cada 30 min porque Google Play Services puede restablecer el valor de Android 12; el proyecto **no** desactiva la sincronización de configuración de Android, que también impediría a RescueParty deshacer configuraciones malas | sí, con Shizuku; en Android 12 puede haber unos minutos tras un restablecimiento | — |
| **La CPU se duerme** con la pantalla apagada | doctor (¿wake lock de Termux?) | `termux-wake-lock` al arrancar (wake lock parcial: CPU encendida, pantalla apagada) | — | dejar la notificación de Termux; no pulsar «release wakelock» |
| **Gestor de tareas del fabricante** (Xiaomi, Huawei, Vivo, Oppo/Realme, Samsung…) | indirectamente: falta el vigilante o el bot, `/historial` | ajustes del fabricante (perfiles abajo) | en parte: guard.sh reabre Termux (probado en Realme) | aplicar los ajustes de tu marca |
| **Termux cerrado o quitado de recientes** | guard.sh (sin `sshd` 2 min) | wake lock + exenciones | **sí, con Shizuku**: guard.sh abre Termux y `~/.bashrc` relanza el servidor (Realme: 2 min 9 s, con «forzar detención»). Volver a ejecutar el arranque ya no crea un segundo bucle vigilante | — |
| **Termux:Boot forzado a detenerse o nunca abierto** | doctor (`stopped=true` / `notLaunched=true`) | — | **no**: Android no entrega el aviso de arranque a una app detenida | abrir Termux:Boot una vez |
| **Reinicio normal**, por fallo o por actualización | `/historial` «el móvil se encendió» | Termux:Boot; Shizuku (fork de thedjchi) arranca solo por depuración inalámbrica en Android 11+ | sí (Realme: bot a los 54–104 s) | evitar actualizaciones automáticas nocturnas del sistema (pueden cambiar ajustes) |
| **Batería agotada / móvil apagado** | se detectan los cortes de luz mientras funciona; nada mientras está apagado | tenerlo enchufado; límite de carga del fabricante | **no**: casi todos los móviles se quedan apagados (o en la pantalla de carga) hasta pulsar el botón. Encender solo necesita el bootloader desbloqueado o una opción del fabricante | pulsar el botón; después todo lo anterior se aplica |
| **Se pierde el Wi-Fi / Internet** | vigilante cada minuto; bucle del bot | — | sí: el bot espera y sigue; 5 min sin red → reinicia el Wi-Fi (Shizuku o Termux:API) | revisar el router si dura |
| **Shizuku parado** (raro; Wi-Fi apagado al arrancar, depuración inalámbrica apagada) | evento del vigilante; doctor | guard.sh mantiene la depuración inalámbrica | el fork se reinicia solo con la depuración inalámbrica activa | abrir Shizuku y arrancarlo |
| **Almacenamiento lleno** | doctor (< 1 GB aviso, < 300 MB fallo); `/salud` | el bot no actualiza con menos de 300 MB; borra descargas temporales al arrancar | en parte | liberar espacio |
| **Sin memoria** (Android mata el proceso más grande) | `bot.sh` (evento de caída), señal de vida | — | sí: `bot.sh` lo relanza con esperas crecientes; el vigilante relanza `bot.sh` | si se repite, menos descargas en paralelo o plugins |
| **Bot congelado** | señal de vida de más de 5 min | — | sí: se mata y se relanza | — |

## Avisos automáticos (Telegram)

El bot (en modo root y sin root) evalúa el estado real cada 5 min y escribe al dueño **solo cuando
cambia** (`bot/alerts.py`):

* **broken** — el servidor no puede hacer su trabajo: sin Internet (se comprueban TCP y DNS), < 300 MB
  libres, yt-dlp/gallery-dl no arrancan (se ejecutan de verdad, cada 30 min), un `FAIL` de `doctor.sh`.
  **degraded** — funciona con límites: < 1 GB libre, ≥ 3 reinicios del bot en 6 h, ≥ 5 descargas
  fallidas en 1 h, un `WARN` de `doctor.sh`. **ok** — nada confirmado.
* Un problema cuenta tras 2 comprobaciones y 5 min (broken) / 10 min (degraded): los cortes de un minuto
  se ignoran. Todo lo nuevo va en **un** mensaje con el impacto y qué hacer; los cambios de nivel y las
  recuperaciones (tras 5 min sin verlo) se cuentan una vez; lo broken se recuerda cada 12 h.
* Un mensaje solo cuenta como entregado cuando Telegram devuelve su id. Si Telegram (o Internet) falla,
  los reintentos se espacian (1, 2, 5, 10, 30 min) sin cola de mensajes viejos: el siguiente cuenta el
  estado actual, cuánto se retrasó y lo que pasó mientras. `/salud` muestra el estado del canal. El estado
  se guarda en disco (un reinicio no repite nada) y los textos pasan por el filtro de `/diagnostico`.
* Límites: un bot muerto no puede enviar nada (el mensaje del vigilante para ese caso sigue en la rama de
  desarrollo), y nada de esto está verificado aún en un móvil.

### proot frente al chroot con root

proot intercepta llamadas al sistema con `ptrace`: funciona sin root pero añade coste por llamada (no
se nota en el móvil probado), no puede usar `mount` real, sockets raw ni acceso a hardware, y todo corre
dentro del árbol de procesos de la app Termux — así que **todo lo que para Termux para también Debian**.
Con root (chroot) el servidor lo arranca el propio sistema y los asesinos de apps de Android no le
afectan. Si un móvil se puede rootear, el modo root sigue siendo la opción más robusta.

### Alternativas evaluadas

| Opción | Veredicto |
|---|---|
| **proot-distro (actual)** | Se mantiene. El mismo Debian y el mismo `bot.py` que el modo root, probado en un móvil real. Su punto débil es que Android mate Termux, y a eso apuntan las defensas de arriba. |
| Solo paquetes de Termux (sin Debian) | Posible más adelante: sin coste de proot y menos procesos, pero otro conjunto de dependencias que mantener (Python, ffmpeg, yt-dlp de Termux) y otras rutas. No compensa sin pruebas de que el propio proot cause caídas. |
| Terminal Linux / Virtualization Framework de Android (Android 15+) | Una máquina virtual Debian de verdad, pero solo en pocos móviles (Pixel) y muy nueva; este proyecto va de móviles *viejos*. A revisar. |
| adb inalámbrico a sí mismo en vez de Shizuku | Descartado: Android apaga la depuración inalámbrica al cambiar de punto de acceso ([12](12-modo-sin-root.md)); el servicio de Shizuku sobrevive. |
| Desactivar la sincronización de configuración (`set_sync_disabled_for_tests persistent`) | Descartado: también impide a RescueParty y a las reversiones deshacer configuraciones malas. Basta con volver a aplicar el valor. |

## Perfiles por fabricante

Los nombres de los ajustes cambian entre versiones y modelos. **Solo Realme lo ha verificado este
proyecto**; el resto son los nombres habituales que reporta la comunidad (busca tu marca en
[dontkillmyapp.com](https://dontkillmyapp.com)) y **no están verificados**. Aplícalos a Termux,
Termux:Boot, Termux:API y Shizuku.

| Fabricante | Ajustes habituales (no verificados salvo que se diga) |
|---|---|
| Todos | Batería → Sin restricciones; desactivar actualizaciones automáticas nocturnas; Opciones de desarrollador: depuración inalámbrica activada, «Desactivar tiempo de espera de autorización de adb»; Android 14+: «Desactivar restricciones de procesos secundarios» |
| **Realme / OPPO / OnePlus (ColorOS) — verificado en Realme 12+** | Batería → ajustes de ahorro: optimización en reposo desactivada; Opciones de desarrollador → «Desactivar supervisión de permisos» activado; límite de carga en Salud de la batería; `OEM=oplus` en `server.conf` |
| Samsung (One UI) | Batería → límites de uso en segundo plano: añadir las apps a «Aplicaciones que nunca entran en suspensión»; «Suspender apps no usadas» desactivado |
| Xiaomi / Redmi / POCO | Info de la app: «Inicio automático» activado; ahorro de batería «Sin restricciones»; bloquear Termux en recientes |
| Huawei / Honor | Inicio de apps: gestionar manualmente; permitir inicio automático, inicio secundario y ejecución en segundo plano |
| Vivo / iQOO | Batería: permitir alto consumo en segundo plano; permitir inicio automático |
| Google Pixel / Android puro | Batería → Sin restricciones suele bastar |

## Matriz de compatibilidad y fiabilidad

Clases: **V** verificado en un móvil real · **S** verificado solo con pruebas automáticas/simulación ·
**D** esperado según la documentación de Android/Termux, pendiente de validar en un móvil · **N** no
compatible o no garantizable.

| Capacidad | Android 7–10 | Android 11 | Android 12 | Android 12L–15 | Android 16 (Realme 12+, arm64) |
|---|---|---|---|---|---|
| Termux + Debian en proot, el bot funciona | D | D | D | D | **V** |
| Arranque tras reiniciar (Termux:Boot) | D | D | D | D | **V** |
| Shizuku arranca solo al encender | N (arranque manual) | D | D | D | **V** |
| guard.sh reabre un Termux cerrado | N sin Shizuku | D | D | D | **V** |
| Ajustes anti-cierre reaplicados | N sin Shizuku | S | S | S | S (nuevo; falta prueba física) |
| Phantom killer controlado | no hace falta | no hace falta | S (límite reaplicado) | S (ajuste) | S |
| `doctor.sh` / línea de `/salud` | S | S | S | S | S (falta ejecución física) |
| Un solo bucle vigilante al reabrir Termux | S | S | S | S | S |
| Recuperación tras agotar la batería | N | N | N | N | N |
| Móviles ARMv7 (32 bits) | D | D | D | D | — |

## Pruebas reproducibles en hardware real

Una prueba de segundos no demuestra nada sobre 24/7. Apunta en cada prueba: móvil, Android, versiones de
Termux, salida de `doctor.sh` antes y después, hora de inicio y fin, y el `/historial` del bot.

| Prueba | Cómo | Pasa si |
|---|---|---|
| Pantalla apagada, larga | enchufado, pantalla apagada ≥ 12 h (mejor 72 h); manda un enlace cada pocas horas | todos los enlaces contestados; `/historial` sin «colgado»/«caída» sin motivo; doctor sigue en `ok` |
| Coste del wake lock | `adb shell dumpsys batterystats --reset`, 12 h pantalla apagada y enchufado, luego `dumpsys batterystats \| grep -i termux` | tiempo de wake lock parcial ≈ el periodo (esperado) y ningún wake lock que encienda la pantalla |
| Reinicio | `/reiniciar confirmar` y reinicio con el botón | SSH y bot vuelven sin tocar el móvil; anotar el tiempo |
| Termux cerrado | quitarlo de recientes; y Ajustes → Forzar detención | vuelve en ~3 min (guard.sh) |
| Termux:Boot detenido | forzar detención de Termux:Boot y ejecutar doctor | doctor marca FAIL con «open the Termux:Boot app once» |
| Ajuste deshecho | `adb shell dumpsys deviceidle whitelist -com.termux`; esperar ≤ 30 min | doctor vuelve a `ok` sin tocar nada |
| Phantom killer | Android 12+: volver a poner `settings_enable_monitor_phantom_procs` en `true`; esperar ≤ 30 min | vuelve a `false` |
| Red | router apagado 10 min | se informa «sin conexión de … a …»; las descargas siguen |
| Almacenamiento | llenar el móvil hasta < 300 MB libres | doctor FAIL; el bot no actualiza; sin bucle de caídas |
| Memoria | abrir apps pesadas mientras descarga | si lo matan, `bot.sh` lo relanza; no se pierde configuración |
| Corte de luz | desenchufar una hora con el bot en marcha | el corte aparece en `/historial` y `/bateria`; todo sigue con la batería |

## Desactivar los ajustes automáticos

`KEEPALIVE=0` en `~/server/server.conf` hace que el vigilante deje de reaplicar los ajustes anti-cierre
(no los deshace: usa Ajustes, o `dumpsys deviceidle whitelist -com.termux`,
`settings delete global settings_enable_monitor_phantom_procs`,
`device_config delete activity_manager max_phantom_processes`).
