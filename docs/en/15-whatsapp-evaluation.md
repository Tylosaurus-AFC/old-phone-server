# 15 · WhatsApp as a second channel — technical evaluation

**Status: evaluation only. Nothing here is implemented, and the base install has no WhatsApp
dependency.** Written October 2026. What was verified, and how, is marked; prices and service
limits change often and must be re-checked before anyone builds on them.

## What we want

Alerts (the same ones Telegram gets, see [14](14-no-root-reliability.md)) and a few read-only
admin queries (status, health, history) over WhatsApp, **in addition to** Telegram. The server must
start, run, diagnose and recover without it; if WhatsApp breaks, Telegram keeps working.

## A. A standalone bridge on WhatsApp Web (whatsmeow)

Reference: [quauhtlimtz/whatsapp-mcp](https://github.com/quauhtlimtz/whatsapp-mcp), a maintained fork of
lharries/whatsapp-mcp. **Read from its source (cloned 2026-10-27):**

| Item | Finding |
|---|---|
| Structure | A Go program (`whatsapp-bridge/main.go`, ~1 560 lines) that talks to WhatsApp, plus a separate Python MCP server. The bridge runs on its own: MCP is not needed to use it. |
| Library | [whatsmeow](https://github.com/tulir/whatsmeow) (WhatsApp Web multi-device protocol, reverse-engineered; actively maintained, last commit 2026-10-27). |
| Storage | SQLite through `mattn/go-sqlite3` → **CGO and a C compiler required**. `store/whatsapp.db` holds the session keys (= access to the account); `store/messages.db` keeps message history. |
| Interface | HTTP on `:<port>` = **all network interfaces**, **no authentication**: `/api/send`, `/api/download`, `/api/monitor`. Anyone on the home Wi-Fi could send messages as you. Unusable as is on a phone server: it would need loopback-only binding and a token, i.e. a patched fork to maintain. |
| Login | QR code scanned from the WhatsApp app; reconnects without QR while the session is valid. The README says re-authentication may be needed after ~20 days, and that WhatsApp expires old client versions every 3–4 months (error 405) → whatsmeow must be updated. |
| Toolchain | `go 1.26` in `go.mod`. |
| Terms | The README itself: automating a personal account is against WhatsApp's terms and can get the number banned; use a dedicated number, low volume. |

Feasibility on this project's phones (**reasoned, not measured** — building external code was not
allowed in the evaluation environment, so RAM/CPU/size are unknown):

* Go cross-compiles to `linux/arm` (ARMv7) and `linux/arm64`; a static binary runs in Termux directly
  (no proot needed) or inside the Debian container. The obstacle is CGO SQLite: either build on the phone
  (Termux `golang` + `clang`, large and slow) or switch to a pure-Go SQLite (`modernc.org/sqlite`, with a
  reported crash on 32-bit ARM in an older version, or `ncruces/go-sqlite3` on wasm) — a code change.
* Risks that do not go away: account restriction/ban, protocol changes that break it without warning,
  periodic re-login, and a database that is as sensitive as the account.

Other WhatsApp Web libraries: **Baileys** (Node.js; same terms/ban risk; Node is available in Termux)
and **whatsapp-web.js** (drives Chromium through Puppeteer — rejected: far too heavy for ARMv7/proot and
fragile).

## B. WhatsApp Business Platform (official Cloud API)

Facts below come from secondary sources found by search; Meta's own pages
(developers.facebook.com) could not be opened from the evaluation environment, so **re-check every
figure there**.

* Requires a Meta developer app and business portfolio, a phone number not in use on the normal
  WhatsApp app, an approved display name, an access token to keep valid, and a payment method for
  paid messages.
* Since 1 July 2025 billing is **per message**, by category (marketing, utility, authentication) and
  recipient country; example utility rates seen: a fraction of a US cent to a few cents. Sources
  disagree on whether replies inside the 24 h customer-service window are still free in late 2026.
* An alert is a business-initiated message: outside the 24 h window it must use a **pre-approved
  template**.
* Incoming messages arrive by **webhook**: Meta must reach a public HTTPS URL. A phone behind home NAT
  needs a tunnel (another service, another dependency). There is no polling API.

Verdict: compliant and stable, but every user would have to set up a Meta business account, templates,
a webhook tunnel and possibly pay. Too heavy as a default for a community project; acceptable only as an
advanced, optional channel.

## C. Other options

| Option | Two-way | Cost/dependency | Verdict |
|---|---|---|---|
| **SMS through Termux:API** (`termux-sms-send`, `termux-sms-list`) | yes (poll the inbox, allow-list the owner's number) | a SIM with SMS; Termux:API SMS permission; no Internet needed | **Most interesting complement**: it works exactly when Internet is down, the case where Telegram (and WhatsApp) cannot. No third party. Not tested yet. |
| CallMeBot (free WhatsApp messages to yourself) | no | a free third-party service run by a volunteer; user reports of rate limits (~25 messages / 4 h), outages, number changes | Fine as an optional, send-only, non-critical channel for people who accept a third party reading the alerts. |
| ntfy / Gotify push | partly | public server or self-hosted; an extra app | Light and free, not WhatsApp. |
| E-mail (SMTP) | partly | an SMTP account and its password on the phone | Simple, slow to notice. |
| Signal (signal-cli), Matrix bridges | yes | Java / a homeserver: heavy | Rejected for old phones. |
| UI automation of WhatsApp (accessibility, taps) | — | — | Rejected: fragile, and the phone's screen is off. |

## D. Proposed architecture (when a second channel is added)

1. **Diagnosis once, channels many.** `collect_problems()` already produces the list of problems. Each
   channel gets **its own** `alerts.Alerts` instance and state file (`alerts-<channel>.json`): one
   channel down never blocks or marks as delivered the other; each confirms its own delivery.
2. **A channel is a `send(text) -> bool` adapter** (True only when the service confirmed delivery).
   Telegram is the built-in one; others live in `/opt/bot/plugins/` and register an adapter, like the
   existing plugin hooks.
3. **A bridge runs as a separate, optional service**, supervised like the `SERVICES` extras (its own
   process, its own logs, relaunched by the watchdog), reachable only on `127.0.0.1` with a random token
   in a `chmod 600` file. The bot never waits on it at start-up.
4. **Incoming admin queries**: only from an allow-listed sender (phone number / chat ID), only a
   read-only command set (`/estado`, `/salud`, `/historial`), rate-limited, no free text reaching a
   shell, no restarts/updates/deletes from a secondary channel unless explicitly enabled.

## Recommendation

1. Do **not** put WhatsApp in the base install.
2. Next step with real value: the multi-channel adapter of D (small, testable), then an **SMS
   channel through Termux:API** as the out-of-band path for "Internet is down" — to be validated on a
   phone.
3. WhatsApp, if wanted: an optional plugin for **a dedicated secondary number**, starting send-only,
   based on whatsmeow with loopback-only access, a token and a pure-Go SQLite, with the ban risk and the
   periodic re-login written in the install guide. Expect to update it every few months. CallMeBot is the
   zero-maintenance alternative for those who accept a third party.
4. The official Cloud API only as an advanced option for users who already have a Meta business setup.

Sources consulted: the repositories above (source code read), whatsmeow's repository, Meta pricing
summaries from Zoho, CleverTap and other secondary sites (October 2026), CallMeBot user reports on the
Homey and simon42 forums, and comparisons of the Cloud API with unofficial libraries.
