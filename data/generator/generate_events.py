#!/usr/bin/env python3
"""Gerador determinístico de eventos de segurança sintéticos (Sentinel-AI).

Lê os dados de referência (zones.yaml, devices.yaml, users.xml) e produz:
  data/raw/access_logs.csv              controlo de acessos (CSV, com problemas de qualidade)
  data/raw/sensor_events.json           sensores (JSON, servido depois pela API /gateway)
  data/test_scenarios/ground_truth.csv  etiqueta esperada por evento (definida à priori)
  data/test_scenarios/scenarios.md      catálogo de cenários com a justificação de cada etiqueta

As etiquetas vêm do catálogo de cenários abaixo e NÃO das regras do motor de regras.
Os IDs dos eventos são atribuídos por ordem cronológica, para não revelarem o cenário.

Uso: python3 data/generator/generate_events.py   (sem dependências externas)
"""
import csv
import json
import random
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta
from pathlib import Path

SEED = 42
DAYS = [date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)]  # segunda a quarta
ROOT = Path(__file__).resolve().parents[2]
RAW, TS = ROOT / "data" / "raw", ROOT / "data" / "test_scenarios"

rnd = random.Random(SEED)


# ----------------------------------------------------------------------------- referência
def read_yaml_docs(path):
    """Leitor mínimo de YAML multi-documento plano (chave: valor)."""
    docs, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("---"):
            cur = {}
            docs.append(cur)
        elif cur is not None and ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip().strip('"')
    return docs


def norm_id(raw, prefix, width):
    return prefix + re.sub(r"[^0-9]", "", raw).zfill(width)


def hhmm(s):
    h, m = s.split(":")
    return time(int(h), int(m))


ZONES = {z["zone_id"]: z for z in read_yaml_docs(RAW / "zones.yaml")}
DEVICES = read_yaml_docs(RAW / "devices.yaml")
DOORS = {}
MOTION = {}
for d in DEVICES:
    if d["device_kind"] == "DOOR":
        DOORS.setdefault(d["zone_id"], []).append(d["device_id"])
    elif d["device_type"] == "MOTION":
        MOTION[d["zone_id"]] = d["device_id"]

USERS = {}
for u in ET.parse(RAW / "users.xml").getroot().findall("user"):
    uid = norm_id(u.get("id"), "U", 3)
    USERS[uid] = {
        "start": hhmm(u.findtext("schedule_start").zfill(5)),
        "end": hhmm(u.findtext("schedule_end").zfill(5)),
        "active": u.findtext("active").strip().lower() in ("true", "yes", "1"),
        "zones": sorted({norm_id(z.text, "Z", 2) for z in u.find("allowed_zones")}),
    }

# ----------------------------------------------------------------------------- eventos
events = []  # dicts: source, ts, scenario, suspicious, + campos da fonte


def access(ts, user, door, status, scenario="NORMAL", suspicious=False):
    zone = next(z for z, ds in DOORS.items() if door in ds)
    events.append(dict(source="ACCESS", ts=ts, user=user, door=door, zone=zone,
                       status=status, scenario=scenario, suspicious=suspicious))


def sensor(ts, sensor_id, zone, scenario="NORMAL", suspicious=False, value=True, etype="MOTION"):
    events.append(dict(source="SENSOR", ts=ts, sensor=sensor_id, zone=zone, etype=etype,
                       value=value, scenario=scenario, suspicious=suspicious))


def at(day_idx, hh, mm, ss=0):
    return datetime.combine(DAYS[day_idx], time(hh, mm, ss))


# ----------------------------------------------------------------------------- catálogo
# Cada cenário: (id, etiqueta, risco esperado, título, justificação). Definido ANTES das regras.
SCENARIOS = []


def scenario(sid, suspicious, risk, title, why):
    SCENARIOS.append(dict(id=sid, suspicious=suspicious, risk=risk, title=title, why=why))
    return sid, suspicious


# --- Suspeitos
s = scenario("S01", True, "HIGH", "Intrusão noturna no laboratório",
             "Utilizador sem permissão para Z03 tenta entrar às 02:13 (recusado) e há movimento dentro da zona 1 minuto depois: alguém entrou por outra via ou forçou a porta.")
access(at(0, 2, 13, 5), "U041", "D03", "DENIED", *s)
sensor(at(0, 2, 14, 10), "M03", "Z03", *s)
sensor(at(0, 2, 16, 40), "M03", "Z03", *s)

s = scenario("S02", True, "HIGH", "Tentativas repetidas na sala de servidores",
             "Quatro recusas em menos de 3 minutos na porta da zona CRITICAL por um utilizador sem permissão: padrão de tentativa de acesso forçado ou cartão clonado.")
for i, sec in enumerate([0, 40, 95, 150]):
    access(at(1, 14, 32, 0) + timedelta(seconds=sec), "U041", "D05", "DENIED", *s)

s = scenario("S03", True, "HIGH", "Acesso concedido sem permissão a zona crítica",
             "Prestador externo (U045) recebe acesso à sala de servidores, para a qual não tem permissão; seguido de movimento. Indica erro de configuração do controlador ou cartão adulterado.")
access(at(2, 15, 5, 12), "U045", "D06", "GRANTED", *s)
sensor(at(2, 15, 6, 0), "M05", "Z05", *s)

s = scenario("S04", True, "MEDIUM", "Movimento noturno no arquivo sem qualquer acesso",
             "Três deteções de movimento no arquivo (RESTRICTED) às 03:40, zona fechada, sem nenhum registo de acesso: presença não autorizada.")
for mm, ss in [(40, 2), (41, 30), (43, 15)]:
    sensor(at(1, 3, mm, ss), "M04", "Z04", *s)

s = scenario("S05", True, "MEDIUM", "Ex-colaborador a tentar entrar",
             "Utilizador inativo (U044) tenta entrar duas vezes nos escritórios antes da abertura: credencial que devia estar revogada.")
access(at(2, 7, 48, 20), "U044", "D02", "DENIED", *s)
access(at(2, 7, 49, 5), "U044", "D02", "DENIED", *s)

s = scenario("S06", True, "HIGH", "Tailgating na sala de servidores",
             "Utilizador sem permissão (U024) é recusado e, 30 s depois, um administrador entra; a porta abre duas vezes e há movimento: o recusado entrou à boleia.")
access(at(0, 10, 2, 0), "U024", "D05", "DENIED", *s)
access(at(0, 10, 2, 30), "U036", "D05", "GRANTED", *s)
sensor(at(0, 10, 2, 35), "C05", "Z05", *s, etype="DOOR_OPEN")
sensor(at(0, 10, 2, 50), "C05", "Z05", *s, etype="DOOR_OPEN")
sensor(at(0, 10, 3, 20), "M05", "Z05", *s)

s = scenario("S07", True, "MEDIUM", "Acesso noturno ao laboratório fora do horário do utilizador",
             "Investigadora com permissão (U003, horário 09–18) entra no laboratório às 23:40 com a zona fechada e permanece (movimento): acesso fora do horário autorizado que exige verificação.")
access(at(1, 23, 40, 10), "U003", "D03", "GRANTED", *s)
sensor(at(1, 23, 41, 0), "M03", "Z03", *s)
sensor(at(1, 23, 44, 30), "M03", "Z03", *s)

# --- Benignos (ambíguos de propósito)
s = scenario("B01", False, "NONE", "Cartão mal lido",
             "Recusa seguida de acesso concedido 20 s depois, mesmo utilizador e porta, dentro do horário e com permissão: leitura falhada do cartão.")
access(at(0, 9, 15, 0), "U001", "D04", "DENIED", *s)
access(at(0, 9, 15, 20), "U001", "D04", "GRANTED", *s)
sensor(at(0, 9, 16, 0), "M04", "Z04", *s)

s = scenario("B02", False, "NONE", "Investigadora após o fecho do laboratório, dentro do seu turno",
             "U033 tem horário 10–19; entra no laboratório às 18:30 (zona fecha às 18:00) dentro do seu turno e com permissão.")
access(at(1, 18, 30, 0), "U033", "D03", "GRANTED", *s)
sensor(at(1, 18, 31, 10), "M03", "Z03", *s)

s = scenario("B03", False, "NONE", "Operador do turno noturno na sala de servidores",
             "U018 (it_operator, turno 20:00–08:00, com permissão para Z05) entra às 03:10: atividade esperada no seu turno.")
access(at(2, 3, 10, 0), "U018", "D05", "GRANTED", *s)
sensor(at(2, 3, 11, 0), "M05", "Z05", *s)

s = scenario("B04", False, "NONE", "Ronda de segurança noturna",
             "U012 (security, 24h, todas as zonas) entra no arquivo às 01:30 durante a ronda.")
access(at(0, 1, 30, 0), "U012", "D04", "GRANTED", *s)
sensor(at(0, 1, 30, 40), "M04", "Z04", *s)

s = scenario("B05", False, "NONE", "Limpeza antes da abertura",
             "U021 (limpeza externa, turno 06–09, permissão Z02) entra nos escritórios às 06:20.")
access(at(1, 6, 20, 0), "U021", "D02", "GRANTED", *s)
sensor(at(1, 6, 21, 30), "M02", "Z02", *s)

s = scenario("B06", False, "LOW", "Deteção isolada no armazém",
             "Uma única deteção de movimento no armazém (INTERNAL) às 21:05, sem repetição nem acessos: falso alarme típico do sensor.")
sensor(at(2, 21, 5, 0), "M07", "Z07", *s)

s = scenario("B07", False, "NONE", "Administrador no NOC à noite",
             "U002 (it_admin, permissão Z06) entra às 23:00 no NOC, que funciona 24/7.")
access(at(0, 23, 0, 0), "U002", "D07", "GRANTED", *s)
sensor(at(0, 23, 1, 0), "M06", "Z06", *s)

s = scenario("B08", False, "NONE", "Porta errada durante o dia",
             "U041 tenta uma vez a porta do laboratório às 11:00 (sem permissão), sem movimento e sem repetição: engano de porta.")
access(at(2, 11, 0, 0), "U041", "D03", "DENIED", *s)

scenario_events = list(events)


# ----------------------------------------------------------------------------- tráfego normal
def too_close(ts, zone, margin=timedelta(minutes=15)):
    return any(e["zone"] == zone and abs(e["ts"] - ts) <= margin for e in scenario_events)


for di, day in enumerate(DAYS):
    for uid, u in sorted(USERS.items()):
        if not u["active"] or u["start"] > u["end"]:  # turno noturno: só nos cenários
            continue
        zones = [z for z in u["zones"] if z in DOORS and z != "Z01"] or ["Z01"]
        for _ in range(rnd.randint(1, 3)):
            zone = rnd.choice(zones)
            zn = ZONES[zone]
            lo = max(u["start"], hhmm(zn["open_time"]))
            hi = min(u["end"], hhmm(zn["close_time"]))
            lo_m, hi_m = lo.hour * 60 + lo.minute + 10, hi.hour * 60 + hi.minute - 20
            if hi_m <= lo_m:
                continue
            for _try in range(10):
                m = rnd.randint(lo_m, hi_m)
                ts = datetime.combine(day, time(m // 60, m % 60, rnd.randint(0, 59)))
                if not too_close(ts, zone):
                    break
            else:
                continue
            access(ts, uid, rnd.choice(DOORS[zone]), "GRANTED")
            if zone in MOTION and rnd.random() < 0.75:
                sensor(ts + timedelta(seconds=rnd.randint(20, 150)), MOTION[zone], zone)

# leituras "sem deteção" (heartbeat, value=false) — filtradas no ETL, fora do ground truth
for di in range(len(DAYS)):
    for zone, sid in sorted(MOTION.items()):
        if rnd.random() < 0.5:
            ts = datetime.combine(DAYS[di], time(rnd.randint(0, 23), rnd.randint(0, 59), 0))
            if not too_close(ts, zone, timedelta(minutes=30)):
                sensor(ts, sid, zone, value=False)

# ----------------------------------------------------------------------------- IDs cronológicos
events.sort(key=lambda e: (e["ts"], e["source"]))
counters = {"ACCESS": 0, "SENSOR": 0}
for e in events:
    counters[e["source"]] += 1
    e["id"] = ("ACC" if e["source"] == "ACCESS" else "SEN") + f"{counters[e['source']]:04d}"


# ----------------------------------------------------------------------------- sujidade
def dirty_user(uid):
    n = int(uid[1:])
    return rnd.choices([uid, uid.lower(), f"u-{n}", f" {uid} ", f"user{n}"], [60, 10, 10, 10, 10])[0]


def dirty_ts(ts):
    fmt = rnd.choices(["%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"], [50, 25, 25])[0]
    return ts.strftime(fmt)


def dirty_zone(z):
    return rnd.choices([z, "", f"z{int(z[1:])}"], [70, 20, 10])[0]


def dirty_status(st):
    return rnd.choice([st, st.lower(), st.capitalize()])


acc_rows = []
for e in (x for x in events if x["source"] == "ACCESS"):
    eid = e["id"] if rnd.random() > 0.1 else e["id"].lower()
    acc_rows.append([eid, dirty_ts(e["ts"]), dirty_user(e["user"]), e["door"], dirty_zone(e["zone"]),
                     dirty_status(e["status"])])

# registos inválidos (rejeitados no ETL; não entram no ground truth)
bad_id = counters["ACCESS"]
def next_bad():
    global bad_id
    bad_id += 1
    return f"ACC{bad_id:04d}"
acc_rows += [
    [next_bad(), "", "U002", "D07", "Z06", "GRANTED"],                       # sem timestamp
    [next_bad(), "2026-10-13T12:00:00", "", "D02", "Z02", "GRANTED"],         # sem utilizador
    [next_bad(), "2026-10-13T12:05:00", "U036", "D99", "", "GRANTED"],        # porta inexistente
    [next_bad(), "2026-13-45 10:00:00", "U001", "D02", "Z02", "GRANTED"],     # data impossível
    [next_bad(), "2026-10-14T16:00:00", "U024", "D02", "Z02", "UNKNOWN"],     # estado inválido
]
# duplicados exatos (reenvio do controlador)
for row in rnd.sample(acc_rows[:-5], 6):
    acc_rows.append(list(row))
rnd.shuffle(acc_rows)

with open(RAW / "access_logs.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["event_id", "timestamp", "user_id", "door_id", "zone_id", "access_status"])
    w.writerows(acc_rows)


def dirty_value(v):
    if v is False:
        return rnd.choice([False, "false", 0])
    return rnd.choice([True, True, "true", 1, "on"])


sen_docs = []
for e in (x for x in events if x["source"] == "SENSOR"):
    ts = e["ts"].strftime("%Y-%m-%dT%H:%M:%S") + rnd.choice(["", "+01:00"])
    doc = {"event_id": e["id"], "timestamp": ts, "sensor_id": e["sensor"],
           "event_type": rnd.choice([e["etype"], e["etype"].lower()]), "value": dirty_value(e["value"])}
    if rnd.random() > 0.15:
        doc["zone_id"] = e["zone"]
    sen_docs.append(doc)
bad_sen = counters["SENSOR"]
sen_docs.append({"event_id": f"SEN{bad_sen + 1:04d}", "timestamp": "2026-10-13T10:00:00",
                 "sensor_id": "M99", "event_type": "MOTION", "value": True})          # sensor inexistente
sen_docs.append({"event_id": f"SEN{bad_sen + 2:04d}", "sensor_id": "M02",
                 "event_type": "MOTION", "value": True})                               # sem timestamp
for d in rnd.sample(sen_docs[:-2], 4):
    sen_docs.append(dict(d))                                                           # duplicados
rnd.shuffle(sen_docs)
(RAW / "sensor_events.json").write_text(json.dumps(sen_docs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# ----------------------------------------------------------------------------- ground truth
TS.mkdir(parents=True, exist_ok=True)
why = {s["id"]: s["title"] for s in SCENARIOS}
with open(TS / "ground_truth.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["event_id", "scenario_id", "expected_suspicious", "rationale"])
    for e in events:
        if e["source"] == "SENSOR" and e["value"] is False:
            continue
        w.writerow([e["id"], e["scenario"], str(e["suspicious"]).lower(),
                    why.get(e["scenario"], "Tráfego normal: utilizador autorizado, dentro do horário")])

lines = ["# Catálogo de cenários de teste (etiquetas definidas à priori)", "",
         "Gerado por `data/generator/generate_events.py` (semente fixa). As etiquetas foram definidas "
         "a partir do contexto de cada cenário, **antes** e **independentemente** do motor de regras.", "",
         "| ID | Suspeito | Risco esperado | Cenário | Justificação |", "|---|---|---|---|---|"]
for s in SCENARIOS:
    lines.append(f"| {s['id']} | {'sim' if s['suspicious'] else 'não'} | {s['risk']} | {s['title']} | {s['why']} |")
n_acc = sum(1 for e in events if e["source"] == "ACCESS")
n_sen = sum(1 for e in events if e["source"] == "SENSOR")
lines += ["", "## Volume gerado", "",
          f"- Eventos de acesso válidos: {n_acc}; linhas no CSV (com inválidos e duplicados): {len(acc_rows)}",
          f"- Eventos de sensor: {n_sen} (inclui leituras sem deteção); documentos no JSON: {len(sen_docs)}",
          f"- Eventos de cenário: {len(scenario_events)}; dias: {', '.join(str(d) for d in DAYS)}"]
(TS / "scenarios.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines[-3:]))
