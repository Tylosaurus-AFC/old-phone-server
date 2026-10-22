# 02 · Root

> **Este es el paso más arriesgado de todo el proyecto, y el único que este repositorio no
> puede automatizar.** El root es distinto en cada modelo. Puede borrar el móvil, anular la
> garantía y, en el peor caso, dejarlo sin arrancar. Hazlo solo en un móvil que puedas permitirte
> perder. Esta guía te dice qué ruta elegir y qué comprobar; las instrucciones concretas para tu
> modelo están en sus hilos de la comunidad (XDA, la wiki de LineageOS, la documentación de Magisk).

Al resto del proyecto solo le hace falta una cosa de este paso: **una shell de root que pueda
ejecutar `chroot`, `mount` y escribir en `/sys`**, accesible con `adb`.

## Elige una ruta

```
¿Puedes desbloquear el bootloader?
(Ajustes → Opciones de desarrollador → «Desbloqueo OEM», y luego el procedimiento fastboot/modo descarga del fabricante)
│
├─ SÍ ─► ¿Tu modelo tiene soporte de LineageOS (u otra ROM actual)?   ver wiki.lineageos.org
│          ├─ SÍ ─► instálala ─► luego Magisk (ruta A)       ← lo mejor: Android actual, sin bloatware
│          └─ NO ─► deja la ROM de fábrica y parchea su imagen de arranque con Magisk (ruta A)
│
└─ NO (bloqueado por operador, p. ej. muchos Samsung/Verizon de EE. UU.)
           ─► un root por exploit que funcione en ese firmware exacto (ruta B)
```

### Ruta A — Magisk (la recomendada siempre que se pueda)

[Magisk](https://github.com/topjohnwu/Magisk) es de código abierto y es la forma estándar de
rootear un móvil con bootloader desbloqueable. El procedimiento general (lee antes la
[guía oficial de instalación](https://topjohnwu.github.io/Magisk/install.html)):

1. Desbloquea el bootloader (**borra el móvil**).
2. Consigue la imagen de arranque de tu firmware (`boot.img`, o `init_boot.img` en equipos nuevos),
   parchéala con la app de Magisk y vuelve a flashearla (`fastboot flash boot` / Odin en Samsung).
3. Abre Magisk una vez. En *Superusuario* asegúrate de que **«Apps y ADB»** (shell) esté permitido.

Usada aquí en una Galaxy Tab A7 (LineageOS 23 / Android 16 + Magisk 30.7). Lanzador de arranque:
`BOOT_MODE=magisk`.

### Ruta B — root por exploit con bootloader bloqueado

Así se hizo el Galaxy S4 mini (Verizon, Android 4.4.2, bootloader bloqueado), con **KingRoot**.
Sé realista con esto:

* KingRoot es de **código cerrado** y tiene un historial de enviar datos y de instalar extras.
  Úsalo **solo en un móvil borrado y dedicado a esto**, sin ninguna cuenta personal, nunca.
* **Nunca actualices Android, nunca desinstales KingRoot, nunca lo cambies por otro gestor de
  root** en un móvil con bootloader bloqueado. Si pierdes el root puede que no haya vuelta.
  Reflashear el firmware de fábrica (Odin) rescata el móvil, pero quizá ya no puedas rootearlo.
* Comprueba que KingRoot funciona en *tu firmware/compilación exactos* antes de depender de él.

Lanzador de arranque: `BOOT_MODE=kingroot`.

### Ruta C — ROM personalizada con `adb root` (sin `su`)

Una compilación **userdebug** de LineageOS da `adb root` en lugar de un binario `su`. Usada aquí
en un Moto X2 (LineageOS 18.1, Android 11, bootloader desbloqueado). Pon `ROOT_MODE=adbroot` y
`BOOT_MODE=initrc`. Ojo: hay que ejecutar `adb root` tras cada reinicio (los scripts lo hacen),
y hay que remontar `/` en escritura para instalar archivos.

## Comprueba que tienes root

```bash
adb shell su -c id          # ROOT_MODE=su:      debe salir  uid=0(root) ...
adb root && adb shell id    # ROOT_MODE=adbroot: debe salir  uid=0(root) ...
```

Con Magisk, el primer comando muestra un aviso «¿Conceder superusuario a Shell?» **en la pantalla
del móvil**: acéptalo (marca *Recordar*).

## Después, quitar basura (opcional, hazlo al final)

Un servidor no necesita ninguna de las apps preinstaladas. Desactivarlas libera 300–500 MB de
RAM (medido: 698 MB → 1050 MB disponibles en la tablet) y estabiliza los tiempos. Pero hazlo
**cuando todo lo demás funcione**, por lotes y reiniciando entre uno y otro:
[`phone/extras/debloat-candidates.txt`](../../phone/extras/debloat-candidates.txt) lista los
candidatos seguros y los paquetes que jamás debes desactivar (sobre todo
`com.android.permissioncontroller`: al desactivarlo, `system_server` se cayó en bucle al arrancar en el Moto X2).

## Si no puedes rootear

Muchos móviles no se pueden rootear: bootloaders bloqueados por el operador sin exploit público, fabricantes que ya
no desbloquean (el Realme 12+ del modo sin root tiene el bootloader bloqueado y Realme no ofrece la app de «Deep
Testing» para desbloquearlo en ese modelo; el intento de root falló). **No es el fin del camino:**
[12 · Modo sin root](12-modo-sin-root.md) corre el mismo Debian y bot en Termux, usando Shizuku para los pocos
poderes de sistema que hacen falta. Pierdes el control del cargador (lo hace el limitador del fabricante) y el soporte
para Android anterior a ~11, y conservas todo lo demás.

Siguiente: [03 · Instalación](03-instalacion.md) (modo root), o [12 · Modo sin root](12-modo-sin-root.md).
