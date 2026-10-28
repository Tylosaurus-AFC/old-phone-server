# Failure catalog → automated tests

Each scenario the project tries to survive, the test that covers it, what that test fakes, and what
only a real phone can confirm. All tests run with `tests/run.sh` (no phone, no network, ~4 min); `LONG=1 bash tests/test_longrun.sh` adds 12/24/48/72 h simulations (~30 min). Simulated hours test the logic, not a phone.
"Caught" = the test was run against the previous code or a deliberately broken copy and failed.

| Scenario | Test | What is faked | Caught | Needs a real phone for |
|---|---|---|---|---|
| Watchdog pass with Shizuku down and Termux:API empty | `test_noroot.sh` "no Shizuku, empty Termux:API" | Shizuku, Termux:API | yes (old code aborted the pass) | Termux:API timing |
| Corrupt heartbeat file | `test_noroot.sh` "corrupt heartbeat" | file content | yes | — |
| Termux reopened many times (duplicate watchdog loops) | `test_noroot.sh` boot.sh | sshd, charge.sh | yes (3 loops) | real Termux reopen |
| Keep-alive settings applied / refused by Android | `test_noroot.sh`, `test_shizuku.sh` | `sa.sh` answers | yes (mutations) | that Android really keeps them |
| Shizuku stopped / app frozen / not authorised / dialog / writable dex / missing | `test_shizuku.sh` probe | `rish` output (texts from Shizuku's sources) | — | real `rish` behaviour per Android version |
| Shizuku restart: backoff, boot grace, offline, no auth | `test_shizuku.sh` charge.sh | clock, `am`, network (local TCP listener) | yes (3 mutations) | that the fork starts on the broadcast |
| Shizuku checks thinned out while down | `test_shizuku.sh` | clock | yes | battery cost |
| Termux:Boot never opened / force-stopped / missing | `test_doctor.sh` | `dumpsys` output | — | real `dumpsys package` format |
| Battery optimisation, background, standby bucket, phantom killer, wake lock | `test_doctor.sh` | `dumpsys`/`settings` output | — | real formats, OEM differences |
| PIN lock (no start before unlock) | `test_doctor.sh` | `dumpsys lock_settings` format (unverified) | — | **everything**: format and behaviour |
| Out of space | `test_doctor.sh`, `test_bot.py` ProblemCollection, `test_bot.py` SafeUpdate | `df`, `disk_usage` | yes (update skipped) | real low-space behaviour |
| Config missing / invalid (`config.sh`, `server.conf`) | `test_tools.sh`, `test_doctor.sh` | adb/ssh | yes (11 failures on old tools) | Windows Git Bash paths |
| Phone unreachable (adb, SSH) | `test_tools.sh` | adb/ssh | — | — |
| Android too old / low space before installing | `test_tools.sh` preflight (executed) | getprop, df | — | — |
| Restore reports success after a failed extract (no space, missing container) | `test_tools.sh` noroot-restore (remote command really executed in a fake phone) | ssh | yes ("Done", exit 0 before) | — |
| Root restore counts failed copies as restored | `test_tools.sh` restore-config (generated script executed) | adb | yes | — |
| Backup without the token reported as a backup (both modes) | `test_tools.sh` backup.sh / noroot-backup.sh | adb/ssh | yes | — |
| Backup/restore loses files | `test_backup_lists.sh`, `test_tools.sh` | adb/ssh | yes | restore on a spare phone |
| Downloader update fails / tools broken afterwards | `test_bot.py` SafeUpdate | pip | yes | real pip on ARM |
| Internet / DNS down | `test_bot.py` ProblemCollection, alerts end-to-end | `internet_ok` | — | real outage |
| Reboot with an old heartbeat on disk: false "bot dead" alarm | `test_botdown.sh` | clock, curl | yes (previous code alarmed in the first pass) | — |
| Bot dead or crash-looping (cannot report itself) | `test_botdown.sh` | clock, curl, network | yes (3 mutations) | curl/TLS in Termux |
| Telegram down, slow or failing during an incident | `test_alerts.py`, `test_botdown.sh` | `send()` / curl | yes | real Bot API errors |
| Alert storms, flapping, ok→degraded→broken→degraded→ok | `test_alerts.py` | clock | yes (no transient filter) | — |
| Restart during an incident, corrupt alert state | `test_alerts.py` | file | yes (state not saved) | — |
| Concurrent evaluations (duplicate alerts) | `test_alerts.py` | threads | — | — |
| Secrets in diagnostics, alerts, events | `test_bot.py` Diagnostics, `test_alerts.py`, `test_shizuku.sh`, `test_botdown.sh` | content | — | review a real `/diagnostico` |
| Token on a process command line | `test_botdown.sh` | curl | yes (mutation) | — |
| Owner-only admin commands and buttons | `test_bot.py` Dispatch, Buttons | Telegram | yes (buttons) | — |
| Long Internet outage: Wi-Fi restarted every 5 min forever (288/day) | `test_longrun.sh` A, `test_charge.sh` (root) | network (TCP listener driven by a schedule), clock | yes (old code: 58 in 5 h; root 72 in 6 h) | — |
| Chained failures: Shizuku down + no Internet + Telegram down + bot dead + Termux:API empty, overlapping | `test_longrun.sh` B | schedule-driven shims | yes (arithmetic abort reintroduced: run stops at 1 h) | real interplay of Android services |
| Random faults over 4 h (72 h with `LONG=1`), reproducible seed | `test_longrun.sh` C | schedule-driven shims | partly (event storm of the old Wi-Fi logic) | — |
| Official Shizuku vs fork, deliberate stop | `test_shizuku.sh`, `test_doctor.sh` | `dumpsys` versionName | yes (2 mutations) | real versionName strings |
| Long screen-off running, wake-lock cost, real reboots, power cuts | — | — | — | **docs/*/14-***, long tests |

Simulators do not reproduce Android's scheduling, Doze, the phantom-process killer, OEM killers,
timing of Shizuku/Termux at boot, or radio behaviour. Formats of `dumpsys` output were written from
Android/Termux sources and documentation; an unexpected format produces a WARN or a missing line,
never a crash (tested by feeding unknown values).
