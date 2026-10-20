# 06 · Battery and heat — do not skip this

A phone that spends years at 100 % charge on a charger ages its battery fast, and a lithium
battery that swells is a **fire hazard**. Running a phone unattended 24/7 means this is your job.

## Safety first

* **Inspect the battery every month** (look at the back cover and screen edges, feel for warmth).
  If the phone's case is bulging or the screen lifts: **stop, unplug, and replace the battery or
  remove it.** Never run a swollen battery.
* Put it on a **hard, non-flammable, ventilated surface**, away from curtains, beds and sofas.
  No case, no pillow, not in a closed drawer.
* Use a **good charger and cable** from a reputable source.
* Some phones (the Galaxy S4 mini among them) boot with **no battery at all** when powered by the
  charger. That is the safest long-term answer for a never-moved server — but you lose the
  "UPS" benefit, and not every phone allows it. Test it with the phone in your hand.
* A switched smart plug on a timer is a perfectly good low-tech charge limiter if your phone has
  no software control.

## What `charge.sh` does

It keeps the charge between `LOW` and `HIGH` (default **40–60 %**) by switching the charger
on and off:

```
 capacity ≥ HIGH  → pause charging  (the phone runs from the charger, the battery rests)
 capacity ≤ LOW   → resume charging
 capacity ≤ FLOOR → always charge   (15 %: never let it die)
 temperature ≥ MAXTEMP → pause charging (default 42.0 °C)
```

On a *paused* phone with mains power the battery neither charges nor discharges, so the
percentage barely moves — which is the point. When the power goes off, the battery takes over:
the bot notices (two points of drop within an hour while "paused", or `Discharging` while
charging) and tells you, then reports how long the battery lasted when the power returns
(`/bateria` keeps the last cut and estimates the autonomy from it).

## Finding your phone's charge switch

Linux exposes the charger driver in sysfs. Look at what your phone has:

```bash
adb shell su -c "ls /sys/class/power_supply/battery"
tools/install.sh check            # also lists the usual control files it finds
```

| Driver (file in `/sys/class/power_supply/battery/`) | Set in `server.conf` | Semantics |
|---|---|---|
| `batt_slate_mode` (Samsung `sec-battery`: S4, Tab A7…) | `BATT_CTRL=slate` | `1` = charger off, battery used; `0` = charges |
| `charging_enabled` (Qualcomm `qpnp`, Motorola) | `BATT_CTRL=enable` | `1` = charges; `0` = charger off |
| `input_suspend`, `store_mode`, `charge_control_limit`, `charge_control_end_threshold`, `constant_charge_current_max`… | `BATT_CTRL_FILE=` your file (+ the closest of the two modes) | semantics differ per vendor: **test by hand** |
| nothing | `BATT_CTRL=none` | `charge.sh` only reports; use a timer plug or a Magisk charge-limit module (e.g. *Advanced Charging Controller*) |

**Test by hand before trusting it** (with the phone plugged in):

```bash
adb shell su -c "echo 1 > /sys/class/power_supply/battery/batt_slate_mode"   # your file/value
adb shell su -c "cat /sys/class/power_supply/battery/status"                # after ~1 min
```

`status` should stop saying `Charging`. Put the value back to resume. Some drivers *show* the
new value but keep charging after a reboot: `charge.sh` detects "paused but still Charging" and
rewrites the value (0 → 1) so the driver really applies it.

### If your ROM has its own charge limiter

LineageOS 18+ has *Settings → Battery → Charging control* (a schedule or a limit). It fights
`charge.sh`. Set `LINEAGE_CHARGE_CTRL_OFF=1` in `server.conf` (done at every boot), or choose
one of the two. On the Tab A7 the default schedule (22:00–06:00) was cutting the charger
and the tablet ran flat while "plugged in"; that is how this was found.

## Heat

* The bot alerts the owner when the battery reaches 42 °C and `charge.sh` stops charging.
* Reference values measured on the S4 mini: 19–24 °C idle, 26 °C in normal use.
* Heavy work (video re-encoding, speech-to-text on all cores) warms any phone: watch the
  temperature the first time you run it and use `/bateria` to see it.
* If it runs hot, move it, add airflow, lower `HIGH`, or lower the number of simultaneous
  downloads (`WORKERS` in `bot/bot.py`).

## Settings reference

| `server.conf` | Default | Notes |
|---|---|---|
| `LOW` / `HIGH` | 40 / 60 | for a server that is rarely unplugged. Raise both (e.g. 50 / 80) if you want more ride-through autonomy during power cuts |
| `MAXTEMP` | 420 | tenths of a degree |
| `FLOOR` | 15 | below this it always charges |

Next: [07 · Network](07-network.md).
