# 05 · Servicios y arranque

Cómo arranca solo el servidor tras un apagón y qué lo mantiene vivo.

## La cadena de arranque

```
enciende → Android arranca
   └─ lanzador de arranque  (UNO de estos, según cómo esté rooteado el móvil)
        ├─ Magisk   : /data/adb/service.d/server.sh        (Magisk lo ejecuta como root)
        ├─ KingRoot : /system/bin/ddexe → /system/xbin/server-boot   (un gancho, ver abajo)
        └─ initrc   : /system/etc/init/server-boot.rc → /data/local/tmp/server-boot.sh
             └─ start.sh   (/data/debian/start.sh, como root)
                  ├─ espera a sys.boot_completed (máx. 2 min)
                  ├─ wake-lock (CPU despierta con pantalla apagada) · Wi-Fi: nunca dormir
                  ├─ opcional: Doze apagado, control de carga de LineageOS apagado
                  ├─ adb por Wi-Fi en :5555 (reinicia adbd)
                  ├─ bot.sh   — solo si existe /data/debian/BOT_ENABLED
                  └─ para siempre:  charge.sh ; sleep 60   (se relanza si muere)
```

(**El modo sin root tiene su propia cadena, más simple** — Termux:Boot → `00-server.sh` → `bot.sh` + `charge.sh` — descrita en [12](12-modo-sin-root.md).)

Cada lanzador son unas pocas líneas cuyo único trabajo es ejecutar `start.sh` como root. Instala
el de tu móvil con `tools/install.sh boot` (lee `BOOT_MODE` de `config.sh`).

## Magisk

Nada que pensar. `tools/install.sh boot` copia el lanzador a `/data/adb/service.d/server.sh`
(modo 755). Magisk ejecuta como root cada script de esa carpeta al arrancar.

## KingRoot (Android 4.4/5)

Por qué un gancho tan raro: en el Galaxy S4 mini, SELinux bloquea `/system/etc/install-recovery.sh`
(el punto de autoarranque clásico en Android 4.4). Lo que *sí* corre al arrancar como root es el
envoltorio propio de KingRoot, `/system/bin/ddexe`, un script de shell corto protegido con
`chattr +i +a`. El truco es añadirle una línea que lance nuestro script.

> ⚠ **`ddexe` forma parte del arranque del móvil.** Un error en él puede impedir que Android
> arranque, y en un móvil con bootloader bloqueado las opciones de recuperación son limitadas.
> Trabaja despacio, guarda una copia del original y revisa la sintaxis antes de reiniciar.

```bash
tools/install.sh boot         # instala /system/xbin/server-boot (e imprime los pasos siguientes)

# luego, a mano:
adb pull /system/bin/ddexe ddexe.orig            # ¡guárdalo bien!
cp ddexe.orig ddexe.new                          # edita ddexe.new (¡finales de línea Unix!)
```

En `ddexe.new` añade esta línea **antes** de la que ejecuta `ddexe_real`:

```sh
/system/xbin/server-boot &
```

Revísalo, instálalo y **verifica** antes de reiniciar:

```bash
sh -n ddexe.new                                  # revisión de sintaxis en el PC: no debe imprimir nada
adb push ddexe.new /data/local/tmp/ddexe.new
adb shell
su
mount -o rw,remount /system
/system/xbin/busybox-deb chattr -ia /system/bin/ddexe
cp /data/local/tmp/ddexe.new /system/bin/ddexe
chmod 755 /system/bin/ddexe
/system/xbin/busybox-deb chattr +ia /system/bin/ddexe
mount -o ro,remount /system
grep -n server-boot /system/bin/ddexe            # debe mostrar tu línea, antes de ddexe_real
```

Luego `adb reboot` y espera ~2 minutos: `/data/debian/boot.log` debe mostrar «server start-up» y
(si está activado) el bot arranca. El lanzador espera hasta 5 min a que `su` responda, porque
KingRoot levanta el root tarde.

## initrc (ROM personalizada con `adb root`, sin `su`)

Copia `phone/boot/initrc/server-boot.rc` a `/system/etc/init/` y `server-boot.sh` a
`/data/local/tmp/` (`tools/install.sh boot` hace las dos cosas, remontando `/` en escritura).
**Edita antes `server-boot.sh`**: su lista de servicios a parar y el zram de 1 GB son de un
Moto X2 y dependen de la ROM. Recuerda que `init` mata los hijos de un servicio cuando este
termina, por eso el script hace `exec` de `start.sh`, que nunca regresa.

## Qué hace `charge.sh`, cada minuto

| Comprobación | Acción |
|---|---|
| `bot.sh` no corre y existe `BOT_ENABLED` | lo relanza (cuenta como caída en `/historial`, salvo que `tools/deploy.sh` lo parara a propósito) |
| bot vivo pero **sin señal de vida en 5 min** | `kill -9`; `bot.sh` levanta uno nuevo. 10 min de gracia después |
| el bot pidió `/reiniciar adb \| wifi \| confirmar` | reinicia adbd · cicla el Wi-Fi · reinicia el móvil |
| ahorro de energía del Wi-Fi activo | lo apaga (con la pantalla apagada el chip se duerme y el móvil desaparece de la red local) |
| señal por debajo de `WIFI_MIN` durante 5 min | cicla el Wi-Fi para volver a buscar el punto de acceso más fuerte |
| 5 min sin Internet | cicla el Wi-Fi |
| adaptador USB-Ethernet conectado | lo anota en `/historial`; deja el Wi-Fi en paz mientras el cable tenga enlace |
| batería fuera de `LOW`–`HIGH`, demasiado caliente o bajo `FLOOR` | conmuta el cargador ([06](06-bateria-y-calor.md)) |
| anuncia su IP con ARP gratuito | para que el PC y los routers de malla sepan siempre dónde está |

Y `bot.sh` reinicia el bot tras una caída con esperas de 10 s → 20 s → 40 s … → 10 min (vuelve a
10 s cuando el bot aguanta 2 minutos), y al siguiente arranque te dice cuántas caídas hubo y el último error.

Los dos scripts son procesos separados que se vigilan entre sí, así que `tools/deploy.sh` puede
sustituir cualquiera sin riesgo: lo mata y el otro lo relanza con el código nuevo.

## Referencia de `server.conf`

Shell plano, en el móvil en `/data/debian/server.conf`; edítalo con `tools/edit-conf.sh`.
Lista completa y comentada: [`phone/server.conf.example`](../../phone/server.conf.example).

| Ajuste | Por defecto | Significado |
|---|---|---|
| `BATT`, `BATT_CTRL`, `BATT_CTRL_FILE` | `/sys/class/power_supply/battery`, `slate` | interruptor del cargador: `slate` · `enable` · `none` |
| `LOW`, `HIGH`, `MAXTEMP`, `FLOOR` | 40, 60, 420, 15 | reanuda con ≤ LOW %, pausa con ≥ HIGH %, pausa sobre 42,0 °C, siempre carga bajo FLOOR % |
| `WIFI_IFACE`, `WIFI_MIN` | `wlan0`, -75 | interfaz; umbral de señal débil (dBm) |
| `FIX_ROUTE` | 0 | `1` en Android 11+ si root recibe *Network is unreachable* |
| `ADB_TCP_PORT`, `ADB_TCP_PROP`, `ADB_RESTART` | 5555, `service.adb.tcp.port`, `stop adbd; …` | adb por Wi-Fi; Android más nuevo usa `persist.adb.tcp.port` y `setprop ctl.restart adbd` |
| `DOZE_OFF` | 0 | `1` = `dumpsys deviceidle disable` (Android 6+) |
| `LINEAGE_CHARGE_CTRL_OFF` | 0 | `1` = desactivar el «Control de carga» de LineageOS (corta el cargador por horario y pelea con `charge.sh`) |
| `BOT_CMD`, `PING_HOST` | python del venv + `bot.py`, `api.telegram.org` | lo que ejecuta `bot.sh`, y lo que espera poder alcanzar |

Siguiente: [06 · Batería y calor](06-bateria-y-calor.md).
