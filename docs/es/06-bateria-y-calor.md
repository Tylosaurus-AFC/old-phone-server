# 06 · Batería y calor — no te lo saltes

Un móvil que pasa años al 100 % en el cargador envejece rápido su batería, y una batería de litio
que se hincha es un **riesgo de incendio**. Dejar un móvil funcionando sin vigilancia 24/7 significa que esto es cosa tuya.

## Seguridad primero

* **Revisa la batería cada mes** (mira la tapa trasera y los bordes de la pantalla, toca si está
  caliente). Si la carcasa se abomba o la pantalla se levanta: **para, desenchufa, y cambia la
  batería o quítala.** Nunca uses una batería hinchada.
* Ponlo sobre una **superficie dura, no inflamable y ventilada**, lejos de cortinas, camas y sofás.
  Sin funda, sin almohada, no en un cajón cerrado.
* Usa un **buen cargador y cable** de una fuente confiable.
* Algunos móviles (entre ellos el Galaxy S4 mini) arrancan **sin batería** alimentados por el
  cargador. Es la respuesta más segura a largo plazo para un servidor que no se mueve —pero
  pierdes el beneficio de «UPS», y no todos los móviles lo permiten. Pruébalo con el móvil en la mano.
* Un enchufe inteligente con temporizador es un limitador de carga de baja tecnología
  perfectamente válido si tu móvil no tiene control por software.

## Qué hace `charge.sh`

Mantiene la carga entre `LOW` y `HIGH` (por defecto **40–60 %**) encendiendo y apagando el cargador:

```
 capacidad ≥ HIGH  → pausa la carga  (el móvil vive del cargador, la batería descansa)
 capacidad ≤ LOW   → reanuda la carga
 capacidad ≤ FLOOR → siempre carga   (15 %: nunca dejar que se apague)
 temperatura ≥ MAXTEMP → pausa la carga (por defecto 42,0 °C)
```

En un móvil *en pausa* con corriente, la batería ni carga ni descarga, así que el porcentaje
casi no se mueve — justo lo que se busca. Cuando se va la luz, la batería toma el relevo: el bot
lo nota (dos puntos de bajada en menos de una hora estando «en pausa», o `Discharging` mientras
carga) y te avisa, y cuando vuelve la corriente cuenta cuánto aguantó la batería (`/bateria`
guarda el último corte y estima la autonomía con él).

## Encontrar el interruptor de carga de tu móvil

Linux expone el driver del cargador en sysfs. Mira qué tiene el tuyo:

```bash
adb shell su -c "ls /sys/class/power_supply/battery"
tools/install.sh check            # también lista los archivos de control habituales que encuentre
```

| Driver (archivo en `/sys/class/power_supply/battery/`) | Poner en `server.conf` | Significado |
|---|---|---|
| `batt_slate_mode` (Samsung `sec-battery`: S4, Tab A7…) | `BATT_CTRL=slate` | `1` = cargador apagado, usa batería; `0` = carga |
| `charging_enabled` (Qualcomm `qpnp`, Motorola) | `BATT_CTRL=enable` | `1` = carga; `0` = cargador apagado |
| `input_suspend`, `store_mode`, `charge_control_limit`, `charge_control_end_threshold`, `constant_charge_current_max`… | `BATT_CTRL_FILE=` tu archivo (+ el más parecido de los dos modos) | la semántica cambia según el fabricante: **pruébalo a mano** |
| nada | `BATT_CTRL=none` | `charge.sh` solo informa; usa un enchufe con temporizador o un módulo de Magisk de límite de carga (p. ej. *Advanced Charging Controller*) |

**Pruébalo a mano antes de fiarte** (con el móvil enchufado):

```bash
adb shell su -c "echo 1 > /sys/class/power_supply/battery/batt_slate_mode"   # tu archivo/valor
adb shell su -c "cat /sys/class/power_supply/battery/status"                # tras ~1 min
```

`status` debe dejar de decir `Charging`. Devuelve el valor para reanudar. Algunos drivers
*muestran* el valor nuevo pero siguen cargando tras un reinicio: `charge.sh` detecta «en pausa pero
sigue Charging» y reescribe el valor (0 → 1) para que el driver lo aplique de verdad.

### Si tu ROM trae su propio limitador de carga

LineageOS 18+ tiene *Ajustes → Batería → Control de carga* (un horario o un límite). Pelea con
`charge.sh`. Pon `LINEAGE_CHARGE_CTRL_OFF=1` en `server.conf` (se aplica en cada arranque), o
elige uno de los dos. En la Tab A7 el horario por defecto (22:00–06:00) cortaba el cargador y la
tablet se quedó sin batería «enchufada»; así se descubrió.

## Calor

* El bot avisa al dueño cuando la batería llega a 42 °C y `charge.sh` deja de cargar.
* Valores de referencia medidos en el S4 mini: 19–24 °C en reposo, 26 °C en uso normal.
* El trabajo pesado (recodificar vídeo, voz a texto con todos los núcleos) calienta cualquier
  móvil: vigila la temperatura la primera vez que lo uses y mírala con `/bateria`.
* Si va caliente: muévelo, dale aire, baja `HIGH`, o reduce las descargas simultáneas
  (`WORKERS` en `bot/bot.py`).

## Referencia de ajustes

| `server.conf` | Por defecto | Notas |
|---|---|---|
| `LOW` / `HIGH` | 40 / 60 | para un servidor que casi nunca se desenchufa. Súbelos (p. ej. 50 / 80) si quieres más autonomía en los apagones |
| `MAXTEMP` | 420 | décimas de grado |
| `FLOOR` | 15 | por debajo de esto siempre carga |

Siguiente: [07 · Red](07-red.md).
