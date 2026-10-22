"""Registro de actividad del bot en SQLite (/opt/bot/bot.db), para /stats.

Una fila por descarga y otra por nota de voz. SQLite viene con Python: un solo archivo,
sin servidor. Escriben varios hilos: una conexion por llamada y un candado. Diario
clasico (no WAL): el archivo siempre esta completo, asi los respaldos lo copian tal cual.
Un fallo aqui nunca debe tumbar el bot: todo va en try/except.
"""
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

DB = Path("/opt/bot/bot.db")
log = logging.getLogger("bot")
_lock = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS descargas (
  id INTEGER PRIMARY KEY,
  t INTEGER NOT NULL,          -- epoch
  chat INTEGER, uid INTEGER, quien TEXT,
  red TEXT, url TEXT, modo TEXT,
  resultado TEXT,              -- ok | cache | fallo | cancelado | nas
  bytes INTEGER DEFAULT 0, segundos REAL DEFAULT 0, error TEXT);
CREATE INDEX IF NOT EXISTS descargas_t ON descargas(t);
CREATE TABLE IF NOT EXISTS voz (
  id INTEGER PRIMARY KEY,
  t INTEGER NOT NULL, chat INTEGER, uid INTEGER, quien TEXT,
  audio_seg REAL, tardo_seg REAL, motor TEXT, ok INTEGER);
CREATE INDEX IF NOT EXISTS voz_t ON voz(t);
-- Cache de enlaces ya enviados y archivo local (solo con device.json "sqlite": true;
-- si no, el bot sigue con cache.json y archivo/indice.json)
CREATE TABLE IF NOT EXISTS cache (
  clave TEXT PRIMARY KEY, items TEXT NOT NULL, titulo TEXT, t INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS cache_t ON cache(t);
CREATE TABLE IF NOT EXISTS archivo (
  id INTEGER PRIMARY KEY, t INTEGER NOT NULL, chat INTEGER, url TEXT, titulo TEXT,
  modo TEXT, dir TEXT, archivos TEXT);
CREATE INDEX IF NOT EXISTS archivo_url ON archivo(url);
CREATE TABLE IF NOT EXISTS archivo_msgs (
  archivo INTEGER REFERENCES archivo(id) ON DELETE CASCADE, chat INTEGER, msg INTEGER);
CREATE INDEX IF NOT EXISTS archivo_msgs_m ON archivo_msgs(chat, msg);
"""


_ready = []                    # las tablas se crean la primera vez


def _run(sql, params=()):
    with _lock:
        con = sqlite3.connect(DB, timeout=15)
        try:
            if not _ready:
                con.executescript(SCHEMA)
                _ready.append(True)
            cur = con.execute(sql, params)
            rows = cur.fetchall()
            con.commit()
            return rows
        finally:
            con.close()


def descarga(chat, uid, quien, red, url, modo, resultado, nbytes=0, segundos=0, error=None):
    try:
        _run("INSERT INTO descargas (t, chat, uid, quien, red, url, modo, resultado, bytes, "
             "segundos, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
             (int(time.time()), chat, uid, quien or None, red, url, modo, resultado,
              int(nbytes or 0), round(segundos or 0, 1), (error or None) and str(error)[:300]))
    except Exception as e:
        log.warning("db descarga: %s", e)


def voz(chat, uid, quien, audio_seg, tardo_seg, motor, ok):
    try:
        _run("INSERT INTO voz (t, chat, uid, quien, audio_seg, tardo_seg, motor, ok) "
             "VALUES (?,?,?,?,?,?,?,?)",
             (int(time.time()), chat, uid, quien or None, round(audio_seg or 0, 1),
              round(tardo_seg or 0, 1), motor, int(bool(ok))))
    except Exception as e:
        log.warning("db voz: %s", e)


def query(sql, params=()):
    return _run(sql, params)


def script(fn):
    """fn(con) dentro de una transaccion (varias sentencias de golpe)."""
    with _lock:
        con = sqlite3.connect(DB, timeout=15)
        try:
            if not _ready:
                con.executescript(SCHEMA)
                _ready.append(True)
            con.execute("PRAGMA foreign_keys = ON")
            with con:
                return fn(con)
        finally:
            con.close()


# ---- Cache de enlaces (el bot la usa en vez de cache.json si device.json "sqlite")

def cache_get(clave):
    rows = _run("SELECT items, titulo, t FROM cache WHERE clave = ?", (clave,))
    if not rows:
        return None
    items, titulo, t = rows[0]
    # json -> listas: igual que lo que devolvia cache.json
    return {"items": json.loads(items), "title": titulo, "t": t}


def cache_put(claves, items, titulo, maximo):
    t = int(time.time())
    def fn(con):
        con.executemany("INSERT OR REPLACE INTO cache (clave, items, titulo, t) VALUES (?,?,?,?)",
                        [(k, json.dumps(items, ensure_ascii=False), titulo, t) for k in claves])
        # Tope: fuera lo anterior a la entrada numero `maximo` (por el indice de t: rapido
        # aunque este llena; si hay menos, la subconsulta da NULL y no borra nada)
        con.execute("DELETE FROM cache WHERE t < "
                    "(SELECT t FROM cache ORDER BY t DESC LIMIT 1 OFFSET ?)", (maximo,))
    script(fn)


def cache_drop(clave):
    _run("DELETE FROM cache WHERE clave = ?", (clave,))


def import_cache(path: Path):
    """cache.json -> tabla cache (una vez: luego se renombra a .importado)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    script(lambda con: con.executemany(
        "INSERT OR IGNORE INTO cache (clave, items, titulo, t) VALUES (?,?,?,?)",
        [(k, json.dumps(v["items"], ensure_ascii=False), v.get("title"), v.get("t", 0))
         for k, v in data.items() if v.get("items")]))
    path.rename(path.with_name(path.name + ".importado"))
    return len(data)


# ---- Indice del archivo de 7 dias

def _archivo_row(r):
    i, t, chat, url, titulo, modo, d, archivos, msgs = r
    return {"id": i, "t": t, "chat": chat, "url": url, "title": titulo, "mode": modo,
            "dir": d, "files": json.loads(archivos),
            "msgs": [list(map(int, m.split(":"))) for m in (msgs or "").split(",") if m]}


_ARCH_SQL = ("SELECT a.id, a.t, a.chat, a.url, a.titulo, a.modo, a.dir, a.archivos, "
             "(SELECT group_concat(chat || ':' || msg) FROM archivo_msgs WHERE archivo = a.id) "
             "FROM archivo a ")


def archivo_put(t, chat, msgs, url, titulo, modo, d, archivos):
    def fn(con):
        cur = con.execute("INSERT INTO archivo (t, chat, url, titulo, modo, dir, archivos) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (t, chat, url, titulo, modo, d, json.dumps(archivos, ensure_ascii=False)))
        con.executemany("INSERT INTO archivo_msgs (archivo, chat, msg) VALUES (?,?,?)",
                        [(cur.lastrowid, c, m) for c, m in msgs])
    script(fn)


def archivo_buscar(chat, msg_id=None, url=None):
    """Entradas candidatas, de la mas reciente a la mas antigua."""
    rows = []
    if msg_id:
        rows += _run(_ARCH_SQL + "WHERE a.id IN (SELECT archivo FROM archivo_msgs WHERE chat = ? "
                     "AND msg = ?) ORDER BY a.t DESC", (chat, msg_id))
    if url:
        rows += _run(_ARCH_SQL + "WHERE a.url = ? ORDER BY a.t DESC", (url,))
    return [_archivo_row(r) for r in rows]


def archivo_viejos(limite):
    """Borra del indice lo anterior a `limite` y devuelve sus carpetas."""
    def fn(con):
        ds = [r[0] for r in con.execute("SELECT dir FROM archivo WHERE t < ?", (limite,))]
        con.execute("DELETE FROM archivo WHERE t < ?", (limite,))
        return ds
    return script(fn)


def import_archivo(path: Path):
    idx = json.loads(path.read_text(encoding="utf-8"))
    for e in idx:
        archivo_put(e["t"], e["chat"], e.get("msgs", []), e.get("url"), e.get("title"),
                    e.get("mode", "video"), e["dir"], e["files"])
    path.rename(path.with_name(path.name + ".importado"))
    return len(idx)
