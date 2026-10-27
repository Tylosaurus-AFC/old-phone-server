"""Avisos automaticos al dueño cuando cambia el estado del servidor.

El bot reune cada pocos minutos la lista de problemas actuales (ver collect_problems() en
bot.py) y se la pasa a Alerts.update(). Este modulo decide que contar, sin repetirse:

  * Estado global: "ok" (sin problemas confirmados), "degraded" (algo falla pero el
    servidor sigue haciendo su trabajo principal) o "broken" (una funcion esencial no
    esta disponible). Es el peor nivel entre los problemas confirmados.
  * Un problema cuenta cuando se ha visto en 2 evaluaciones seguidas y dura al menos
    CONFIRM[nivel] segundos: un fallo de un minuto no molesta al dueño.
  * Se avisa una vez al confirmarse, otra si cambia de nivel y otra al resolverse (tras
    RECOVER s sin verlo). Lo "broken" que sigue se recuerda cada REMIND s.
  * Todo lo de una evaluacion va en UN mensaje, junto con los problemas ya vistos dos veces
    seguidas aunque no hayan cumplido su tiempo minimo (asi no llegan dos mensajes seguidos).
  * Solo se da por avisado lo que Telegram confirmo (send() devolvio True). Si falla, se
    reintenta con esperas crecientes (BACKOFF) y sin cola de mensajes viejos: el siguiente
    mensaje cuenta el estado de ese momento, cuanto tiempo no se pudo avisar y lo que paso
    y se resolvio mientras tanto.
  * El estado se guarda en disco (escritura atomica): tras un reinicio no se repiten
    avisos ya dados; si el archivo esta dañado se empieza de cero.

Un problema es un dict: {"id": "disk", "level": "broken"|"degraded", "title": "...",
"impact": "...", "fix": "..."}. Los textos pasan por `clean` (quitar secretos) antes de
enviarse.
"""
import html
import json
import os
import threading
import time
from pathlib import Path

LEVELS = {"ok": 0, "degraded": 1, "broken": 2}
CONFIRM = {"degraded": 600, "broken": 300}
RECOVER = 300
REMIND = 12 * 3600
BACKOFF = (60, 120, 300, 600, 1800)
MAX_ITEMS = 8
HEAD = {"ok": "✅ Servidor: todo en orden", "degraded": "🟡 Servidor: funciona con avisos",
        "broken": "🔴 Servidor: falla algo importante"}
NAME = {"ok": "todo en orden", "degraded": "con avisos", "broken": "con fallos"}
ICON = {"degraded": "⚠️", "broken": "❌"}


def _hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def _span(seconds):
    m = int(seconds) // 60
    return f"{m} min" if m < 120 else f"{m / 60:.1f} h"


class Alerts:
    def __init__(self, path, send, clean=lambda s: s, now=time.time):
        self.path, self.send, self.clean, self.now = Path(path), send, clean, now
        self.state = self._load()
        self._lock = threading.Lock()      # una evaluacion cada vez: sin avisos dobles

    # ---- persistence ----------------------------------------------------------------
    def _empty(self):
        return {"v": 1, "problems": {}, "level": "ok", "resolved": [], "missed": [],
                "pending_since": None, "fails": 0, "next_try": 0, "last_ok_send": None}

    def _load(self):
        try:
            st = json.loads(self.path.read_text(encoding="utf-8"))
            if st.get("v") == 1 and isinstance(st.get("problems"), dict):
                return {**self._empty(), **st}
        except (OSError, ValueError, AttributeError):
            pass
        return self._empty()

    def _save(self):
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass            # disco lleno: se sigue en memoria; nunca bloquear al bot

    # ---- evaluation -----------------------------------------------------------------
    def level(self):
        """Estado global confirmado ahora mismo."""
        conf = [p["level"] for p in self.state["problems"].values() if p.get("confirmed")]
        return max(conf, key=LEVELS.get, default="ok")

    def update(self, problems):
        """Registra la evaluacion actual y, si hay algo que contar, intenta avisar.
        Devuelve el texto enviado (o que se intento enviar), o None."""
        with self._lock:
            return self._update(problems)

    def _update(self, problems):
        now, st = self.now(), self.state
        seen = set()
        for p in problems:
            if p.get("level") not in CONFIRM or not p.get("id"):
                continue
            seen.add(p["id"])
            cur = st["problems"].get(p["id"])
            if cur is None:
                cur = st["problems"][p["id"]] = {"first": now, "count": 0, "confirmed": False,
                                                 "notified_level": None, "last_notified": None}
            cur.update(level=p["level"], title=p.get("title", p["id"]), impact=p.get("impact", ""),
                       fix=p.get("fix", ""), last_seen=now, gone_since=None)
            cur["count"] += 1
            if not cur["confirmed"] and cur["count"] >= 2 and now - cur["first"] >= CONFIRM[p["level"]]:
                cur["confirmed"] = True
        for pid in list(st["problems"]):
            if pid in seen:
                continue
            cur = st["problems"][pid]
            if cur.get("notified_level"):
                cur["gone_since"] = cur.get("gone_since") or now
                if now - cur["gone_since"] >= RECOVER:
                    st["resolved"].append({"title": cur["title"], "first": cur["first"], "end": cur["gone_since"]})
                    del st["problems"][pid]
            else:
                if cur["confirmed"]:     # confirmado pero nunca avisado (canal caido): se resume
                    st["missed"].append({"title": cur["title"], "first": cur["first"], "end": now})
                del st["problems"][pid]
        st["resolved"], st["missed"] = st["resolved"][-MAX_ITEMS:], st["missed"][-MAX_ITEMS:]
        text = self._message(now)
        if text and now >= st["next_try"]:
            self._deliver(text, now)
        self._save()
        return text

    def _message(self, now):
        st = self.state
        probs = st["problems"].values()
        new = [p for p in probs if p["confirmed"] and not p["notified_level"]]
        changed = [p for p in probs if p["notified_level"] and p["notified_level"] != p["level"]
                   and p.get("gone_since") is None]
        remind = [p for p in probs if p["notified_level"] == "broken" and p["level"] == "broken"
                  and p.get("gone_since") is None and now - (p["last_notified"] or now) >= REMIND]
        if not (new or changed or remind or st["resolved"] or st["missed"]):
            return None
        # A message goes out anyway: take along the problems already seen twice in a row
        # that have not reached their minimum time yet (grouping instead of a second message)
        for p in probs:
            if not p["confirmed"] and p["count"] >= 2:
                p["confirmed"] = True
                new.append(p)
        lvl, before = self.level(), st["level"]
        out = [HEAD[lvl] + (f" (antes: {NAME[before]})" if before != lvl else "")]
        if st["pending_since"]:
            out.append(f"<i>Aviso con retraso: no pude enviarlo desde las {_hm(st['pending_since'])}.</i>")
        for title, items in (("Nuevo", new), ("Ha cambiado", changed), ("Sigue sin resolverse", remind)):
            if not items:
                continue
            out.append(f"\n<b>{title}:</b>")
            for p in sorted(items, key=lambda p: -LEVELS[p["level"]])[:MAX_ITEMS]:
                out.append(f"{ICON[p['level']]} {self._esc(p['title'])} · desde las {_hm(p['first'])}")
                if p.get("impact"):
                    out.append(f"   Impacto: {self._esc(p['impact'])}")
                if p.get("fix"):
                    out.append(f"   Qué hacer: {self._esc(p['fix'])}")
        if st["resolved"]:
            out.append("\n<b>Resuelto:</b>")
            out += [f"✅ {self._esc(r['title'])} (duró {_span(r['end'] - r['first'])})" for r in st["resolved"]]
        if st["missed"]:
            out.append("\n<b>Pasó mientras no podía avisar (ya resuelto):</b>")
            out += [f"• {self._esc(m['title'])}, de {_hm(m['first'])} a {_hm(m['end'])}" for m in st["missed"]]
        known = [p for p in probs if p["notified_level"] and p not in changed and p not in remind
                 and p.get("gone_since") is None]
        if known:
            out.append(f"\nSiguen {len(known)} problema(s) ya avisados: /salud")
        return "\n".join(out)[:3800]

    def _esc(self, s):
        return html.escape(self.clean(str(s)))

    def _deliver(self, text, now):
        st = self.state
        try:
            ok = bool(self.send(text))
        except Exception:
            ok = False
        if ok:
            for p in st["problems"].values():
                if p["confirmed"] and p.get("gone_since") is None and (
                        p["notified_level"] != p["level"] or not p["notified_level"]
                        or now - (p["last_notified"] or now) >= REMIND):
                    p["notified_level"], p["last_notified"] = p["level"], now
            st.update(resolved=[], missed=[], pending_since=None, fails=0, next_try=0,
                      level=self.level(), last_ok_send=now)
        else:
            st["fails"] += 1
            st["pending_since"] = st["pending_since"] or now
            st["next_try"] = now + BACKOFF[min(st["fails"], len(BACKOFF)) - 1]

    def summary(self):
        """Una linea para /salud: estado y si hay avisos sin poder entregar."""
        st = self.state
        line = f"estado {NAME[self.level()]}"
        if st["pending_since"]:
            line += f"; no puedo avisar desde las {_hm(st['pending_since'])} (reintento automático)"
        elif st["last_ok_send"]:
            line += f"; último aviso {time.strftime('%d/%m %H:%M', time.localtime(st['last_ok_send']))}"
        return line
