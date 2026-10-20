# 07 · Red

La mayoría de los «el servidor desapareció» son problemas de red, y el Android viejo tiene
varios muy particulares. Esta página los reúne.

## Lo básico

* **Reserva una IP fija** para el móvil en tu router (reserva DHCP por MAC). Ponla en `PHONE_IP`
  en `config.sh`. Los scripts la usan para adb por Wi-Fi.
* **Solo salida.** El bot habla *con* Telegram; nada se conecta *al* móvil desde Internet. **No**
  necesitas abrir puertos, DDNS ni IP pública, y no deberías crearlos. (El único puerto abierto
  es adb en :5555, solo en tu red local; ver abajo.)
* Prefiere **5 GHz** donde la señal lo permita (ver «Fijar la banda»); los 2,4 GHz en un edificio
  saturado pueden ir muchas veces más lento. Medido en una tablet en la misma habitación:
  5,5 Mbps en la red de 2,4 GHz saturada frente a ~82 Mbps en la de 5 GHz, incluso con −78 dBm.

## adb por Wi-Fi

`start.sh` lo activa al arrancar (`setprop service.adb.tcp.port 5555` y reinicia adbd). Los
scripts usan USB si está enchufado y Wi-Fi si no. Para conectar a mano:

```bash
adb connect 192.168.1.50:5555
```

Cosas que conviene saber:

* Sigue exigiendo la **clave RSA que aceptaste** en el móvil, así que solo entran PCs autorizados.
  No expongas el :5555 a Internet.
* **El adbd de Android 4.4 atiende una sola conexión de red a la vez** y se cuelga si esa conexión
  se corta (p. ej. al mover el móvil). Cura: manda `/reiniciar adb` al bot (reinicia adbd en menos
  de un minuto, sin tocar el bot). Nunca ejecutes `stop adbd; start adbd` desde una sesión de
  `adb shell`: el `stop` mata tu propia sesión antes de que corra el `start`, y adb queda muerto
  hasta reiniciar.
* Android 11+ también trae «Depuración inalámbrica» nativa. El método con `setprop` que se usa
  aquí también funcionó en los equipos probados con Android 11 y 16; allí pon
  `ADB_TCP_PROP=persist.adb.tcp.port` (11) o deja el valor por defecto (16) y
  `ADB_RESTART="setprop ctl.restart adbd"`.

## Ahorro de energía del Wi-Fi: el móvil «desaparece» de noche

Con la pantalla apagada el chip Wi-Fi entra en ahorro de energía y deja de contestar al tráfico
de la red local (ARP). El bot sigue llegando a Telegram (él inicia el tráfico), pero `ping` y adb
desde tu PC se agotan. `charge.sh` apaga el ahorro con `iw` cada minuto (Android lo vuelve a
encender al reconectar) y anuncia la dirección del móvil con un ARP gratuito. El ajuste
`wifi_sleep_policy=2` de `start.sh` mantiene el Wi-Fi encendido con la pantalla apagada.

## Puntos de acceso «pegajosos» (Android viejo)

Android 4.4 se une al primer punto de acceso que encuentra y **nunca cambia a uno más fuerte**
mientras siga conectado. Tras un reinicio, un móvil se quedó a −84 dBm / 9 Mbps con una red a
−69 dBm / 40–60 Mbps disponible. `charge.sh` lo resuelve: si la señal está por debajo de
`WIFI_MIN` (por defecto −75 dBm) durante 5 minutos, cicla el Wi-Fi, lo que fuerza una búsqueda nueva.
Si tu única señal utilizable es débil, baja `WIFI_MIN` (p. ej. `-85`) o se pasará reconectando.

## Escalera de recuperación

Cuando no puedes alcanzar el móvil:

1. ¿Contesta el bot en Telegram? Entonces el móvil está bien y tiene Internet.
2. `ping <IP del móvil>` — en Windows solo cuenta una respuesta con `TTL=`; *Host de destino
   inaccesible* no es una respuesta.
3. El ping contesta pero adb no → `/reiniciar adb`.
4. El ping no contesta pero el bot sí → `/reiniciar wifi`.
5. Tampoco contesta el bot → revisa corriente, batería y Wi-Fi en el móvil; luego `/reiniciar confirmar`
   si logras llegar al bot, o apaga y enciende físicamente.

## Android 11+: «Network is unreachable» como root

Android 11 ya no consulta la tabla de rutas `main` para los procesos de root, así que el chroot
(y el bot) se queda sin ruta de salida. Pon `FIX_ROUTE=1` en `server.conf`: `charge.sh` mantiene
una regla `ip rule … lookup <tabla de wlan>` (encuentra el número de tabla solo, porque `netd` lo asigna).

## Fijar la banda (LineageOS / Android 12+, opcional)

Android se queda en 2,4 GHz siempre que puede, porque su umbral para unirse a 5 GHz es −77 dBm.
`phone/extras/wifi-band.sh` quita la conexión automática de la red de 2,4 GHz (sigue guardada)
editando `WifiConfigStore.xml`. Pon `WIFI_2G_SSID` y `WIFI_5G_SSID` en `server.conf`, instálalo con
`tools/deploy.sh` (viaja con los scripts) y ejecuta
`adb shell su -c "sh /data/debian/wifi-band.sh 5g"`. Si el móvil no tiene Internet en 5 GHz
durante 10 minutos, `charge.sh` llama solo a `wifi-band.sh 2g`. Cada cambio reinicia el framework de
Android (~1 min sin red; el chroot y el bot siguen). `2g` lo deshace.

## Ethernet (hub USB-C o micro-USB)

Preparado pero **todavía sin probar con hardware real**. La mayoría de kernels incluyen los
drivers USB-Ethernet habituales (Realtek RTL8152/8153, ASIX AX88179, CDC-ECM/NCM) y Android
nombra la interfaz `eth0` o `usb0`. `charge.sh` nota el cable, lo registra y deja el Wi-Fi en paz mientras
haya enlace; `/velocidad` del bot informa «Conectado por cable». Ojo: muchos móviles no pueden
cargar **y** hacer de anfitrión USB por el mismo puerto; puede hacer falta un hub con paso de
corriente. Compruébalo con tu hub, y cuéntanos cómo te fue.

Siguiente: [08 · Operación](08-operacion.md).
