# 01 · Preparación: PC, móvil y ajustes

## Qué necesitas

**Hardware**

* El móvil y un **buen cargador y cable**. Va a estar enchufado para siempre.
* Un lugar con buen Wi-Fi, cerca del router si se puede (una señal débil es la causa más
  común de problemas, ver [07 · Red](07-red.md)), sobre una superficie dura y ventilada.
* Una **batería sana**: ni hinchada ni caliente. Lee [06 · Batería y calor](06-bateria-y-calor.md)
  antes de dejar un móvil funcionando sin vigilancia.

**En tu PC** (Windows, Linux o macOS)

| Herramienta | Para qué | Dónde |
|---|---|---|
| `adb` (Android platform-tools) | hablar con el móvil | <https://developer.android.com/tools/releases/platform-tools> |
| `bash` | correr los scripts de `tools/` | Linux/macOS: ya viene. Windows: **Git Bash** (incluido en [Git para Windows](https://git-scm.com/download/win)) |
| `curl`, `xz`, `gzip`, `sha256sum` | descargar y preparar Debian | vienen con Git Bash y casi todo Linux/macOS |
| Python 3 + `pip install requests` | solo para correr las pruebas (opcional) | |

**Cuentas**: una cuenta de Telegram (para hablar con @BotFather y con el bot). Nada más.

## 1. Descarga el repositorio

```bash
git clone https://github.com/Tylosaurus-AFC/old-phone-server.git
cd old-phone-server
```

## 2. Activa la depuración USB en el móvil

1. *Ajustes → Acerca del teléfono* → toca **Número de compilación** 7 veces («Ahora eres desarrollador»).
2. *Ajustes → Opciones de desarrollador* → activa **Depuración USB**.
   (En Android 4.4 *Opciones de desarrollador* está en *Ajustes → Más*.)
3. Conecta el móvil al PC y acepta el aviso «¿Permitir depuración USB?» (marca *Permitir siempre*).
4. Comprueba:

```bash
adb devices          # tu móvil debe salir como "device", no como "unauthorized"
```

## 3. Averigua qué tienes

```bash
adb shell getprop ro.product.cpu.abilist
adb shell getprop ro.build.version.release
```

| `cpu.abilist` contiene | Debian que instalar (`ARCH`) |
|---|---|
| solo `armeabi-v7a` (y quizá `armeabi`) | **`armhf`** (32 bits) |
| `arm64-v8a` | **`arm64`** |
| `x86`/`x86_64` | no probado aquí |

La versión de Android te dice qué ruta de root y qué lanzador de arranque usarás
([02 · Root](02-root.md)). Cuando el móvil ya tenga root, `tools/install.sh check` muestra todo
esto y además qué archivos de control de batería existen en tu móvil.

## 4. Crea `config.sh`

```bash
cp config.example.sh config.sh
```

Abre `config.sh` y ajusta al menos:

| Ajuste | Qué poner |
|---|---|
| `ADB` | `adb`, o en Windows la ruta completa, p. ej. `/c/Users/tu/AppData/Local/Android/Sdk/platform-tools/adb.exe` |
| `ARCH` | `armhf` o `arm64` (tabla de arriba) |
| `PHONE_IP` | la IP Wi-Fi del móvil; **resérvala en tu router** (reserva DHCP) para que nunca cambie |
| `USB_SERIAL` | el número de serie que muestra `adb devices` (permite que los scripts prefieran USB sobre Wi-Fi) |
| `ROOT_MODE` | `su` (casi siempre) o `adbroot` (ROM personalizada con `adb root` pero sin `su`) |
| `BOOT_MODE` | `magisk`, `kingroot` o `initrc`: se decide en [02](02-root.md) y [05](05-servicios-y-arranque.md) |
| `BB_PATH` | `/data/debian/busybox-deb`, **salvo** en kernels Samsung viejos, ver [03](03-instalacion.md#3-busybox) |
| `TZ_NAME` | tu zona horaria, p. ej. `Europe/Madrid`, `America/Mexico_City` |

`config.sh` está en `.gitignore`. Déjalo así.

> **Consejo para Windows.** Corre todo desde *Git Bash*, no desde PowerShell ni cmd. Los scripts
> ponen `MSYS_NO_PATHCONV=1` para que Git Bash no convierta las rutas `/data/...` en `C:/...`.

## 5. Comprueba que las pruebas pasan en tu equipo (opcional, pero barato)

```bash
pip install requests
tests/run.sh
```

Revisa la sintaxis de todos los scripts, prueba la lógica de la batería contra una batería
falsa y verifica la carga de plugins y el despacho de comandos del bot. No hace falta el móvil.

Siguiente: [02 · Root](02-root.md).
