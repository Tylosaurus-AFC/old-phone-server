# Contributing

Thank you for helping old phones get a second life.

## The most useful contributions

1. **Your phone** (either mode). Add a section to [`docs/en/10-tested-devices.md`](docs/en/10-tested-devices.md)
   (and `docs/es/10-moviles-probados.md` if you can): model, Android version, ABI, root route,
   `BB_PATH`, `BATT_CTRL`, what you had to change, a few measurements. Failures are valuable too.
2. **Bug reports.** Say: phone model, Android version, `tools/install.sh check` output, which step
   failed, and the relevant lines of `service.log` / `bot.log` / `boot.log`.
   **Remove tokens, cookies, IPs and serial numbers first.**
3. **Translations of the bot.** The messages are Spanish and sit in `bot/bot.py` and
   `extras/plugins/`. A small i18n layer (`strings_<lang>.py`) would be ideal.
4. **Plugins.** See [`docs/en/09-plugins.md`](docs/en/09-plugins.md).
5. **Other charge drivers** for `phone/charge.sh` (a new `BATT_CTRL` mode, with a test in
   `tests/test_charge.sh`).

## Ground rules

* **Never commit secrets or personal data**: tokens, API keys, cookies, `config.sh`, backups, IP
  addresses of your network, Wi-Fi names, serial numbers. `.gitignore` covers the usual file names, but
  read your diff. If you leak a token, revoke it in @BotFather before anything else.
* Shell scripts must stay POSIX `sh`-compatible on the phone in root mode (Android's `sh` is `mksh`; no bashisms in
  `phone/*.sh`). Termux scripts (`phone/noroot/`) and the PC tools (`tools/*.sh`) are bash. Always LF line endings (`.gitattributes`).
* Run `tests/run.sh` before sending a pull request (`pip install requests`). Add a test when you fix a bug.
  It checks shell syntax, scans tracked files for bot tokens/private keys, runs the shell tests
  against a fake battery and a fake Shizuku, and the bot's unit tests (no phone or network
  needed, ~30 s). GitHub Actions runs the same script on every push and pull request
  (`.github/workflows/tests.yml`). Passing tests do **not** prove a phone works: say what you
  checked on real hardware.
* Bug reports: attach the output of `/diagnostico` (see `docs/en/08-operations.md`).
* Keep the documentation honest: say what was tested on which hardware and what was not.
