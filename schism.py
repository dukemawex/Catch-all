#!/usr/bin/env python3
"""SCHISM: read a multi-agent transcript as a cult and write the heresy report.

Usage: python schism.py fixtures/hf_shape.jsonl -o public/
Stdlib only. Deterministic. Every claim in the output cites a message id.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Doctrine rules are duplicated in public/schism.js: keep these in sync.
STOPWORDS = {"the", "a", "an", "to", "of", "and", "we", "should", "this", "that",
             "it", "is", "be", "for", "on", "in"}
OBJECTIONS = ["stop", "should not", "bad idea", "crosses a line", "refuse",
              "do not", "dont", "misgiving"]
NGRAM = 6
MIN_AGENTS = 3
WHOLE_LIMIT = 140


# ---------- text ----------

def normalize(text):
    text = text.lower().replace("'", "").replace("’", "")
    out = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(out.split())


def content(text):
    return [w for w in normalize(text).split() if w not in STOPWORDS]


def sentences(text):
    out, cur = [], ""
    for i, c in enumerate(text):
        cur += c
        if c in ".!?" and (i + 1 == len(text) or text[i + 1].isspace()):
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def phrases(text):
    return [text] if len(text) < WHOLE_LIMIT else sentences(text)


def contains(tokens, key):
    n = len(key)
    return any(tuple(tokens[i:i + n]) == key for i in range(len(tokens) - n + 1))


def bigrams(tokens):
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def is_objection(text):
    padded = " " + normalize(text) + " "
    return any(" " + k + " " in padded for k in OBJECTIONS)


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def minutes(a, b):
    return int(round((parse_ts(b) - parse_ts(a)).total_seconds() / 60))


# ---------- load ----------

def load(path):
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                m = json.loads(line)
                msgs.append({k: m[k] for k in ("id", "ts", "agent", "text")})
    msgs.sort(key=lambda m: (m["ts"], m["id"]))
    for i, m in enumerate(msgs):
        m["_i"] = i
        m["_tok"] = content(m["text"])
    return msgs


# ---------- doctrine extraction ----------

def candidates(msgs):
    agents = defaultdict(set)
    first = {}
    for m in msgs:
        keys = set()
        for p in phrases(m["text"]):
            tok = content(p)
            if len(tok) >= 3:
                keys.add(tuple(tok))
            for i in range(len(tok) - NGRAM + 1):
                keys.add(tuple(tok[i:i + NGRAM]))
        for k in keys:
            agents[k].add(m["agent"])
            first.setdefault(k, m)
    return agents, first


def pick_doctrines(msgs):
    agents, first = candidates(msgs)
    ranked = sorted((k for k in agents if len(agents[k]) >= MIN_AGENTS),
                    key=lambda k: (-len(agents[k]), first[k]["_i"], k))
    chosen = []
    for k in ranked:
        if not chosen:
            chosen.append(k)
        elif len(chosen) == 1:
            words = set(k)
            if len(words & set(chosen[0])) <= len(words) / 2:
                chosen.append(k)
                break
    out = []
    for k in chosen:
        # core words: every qualifying key carried by exactly the same agents
        core = set()
        for k2 in ranked:
            if agents[k2] == agents[k] and set(k2) & set(k):
                core |= set(k2)
        out.append((k, core))
    rejected = sorted((k for k in agents if len(agents[k]) == 2 and len(k) < NGRAM),
                      key=lambda k: first[k]["_i"])
    return out, [(k, [m for m in msgs if tuple(m["_tok"]) == k]) for k in rejected]


def label_for(text, key):
    for s in sentences(text):
        if contains(content(s), key):
            return " ".join(s.split()[:8]).rstrip(".,;:!?")
    return " ".join(text.split()[:8]).rstrip(".,;:!?")


def cite(m):
    return {"agent": m["agent"], "id": m["id"], "ts": m["ts"], "text": m["text"]}


def analyse(msgs, key, core, did):
    adopts = [m for m in msgs if contains(m["_tok"], key)]
    pz = adopts[0]
    first_adopt = {}
    for m in adopts:
        first_adopt.setdefault(m["agent"], m)
    objections = defaultdict(list)
    for m in msgs:
        if m["_i"] > pz["_i"] and m["agent"] != pz["agent"] and is_objection(m["text"]) \
                and not contains(m["_tok"], key):
            objections[m["agent"]].append(m)

    carriers = sorted(first_adopt, key=lambda a: first_adopt[a]["_i"])
    apostates, converts = [], []
    for a in carriers[1:]:
        if any(o["_i"] < first_adopt[a]["_i"] for o in objections.get(a, [])):
            apostates.append(a)
        else:
            converts.append(a)
    heretics = sorted((a for a in objections if a not in first_adopt),
                      key=lambda a: objections[a][0]["_i"])

    # superspreader: adopting message upstream of the most later adopters who echo it
    def extra(m):
        return {b for b in bigrams(m["_tok"]) if not (b[0] in core and b[1] in core)}
    best, best_down, best_list = pz, -1, []
    for m in adopts:
        ex = extra(m)
        down = [first_adopt[a] for a in carriers
                if a != m["agent"] and first_adopt[a]["_i"] > m["_i"] and ex & extra(first_adopt[a])]
        if len(down) > best_down:
            best, best_down, best_list = m, len(down), down

    half_idx = (len(carriers) + 1) // 2 - 1
    half_msg = first_adopt[carriers[half_idx]]

    roles = {}
    events = []
    for m in msgs:
        a = m["agent"]
        if m in adopts:
            if m is pz:
                role = "patient_zero"
            elif m is first_adopt[a]:
                role = "apostate" if a in apostates else "convert"
                if m is best:
                    role = "superspreader"
            else:
                role = "superspreader" if m is best else "repeat"
        elif m in objections.get(a, []):
            role = "heresy" if a in heretics else "objection"
        else:
            continue
        events.append({"ts": m["ts"], "agent": a, "id": m["id"], "role": role, "text": m["text"]})

    for a in carriers:
        roles.setdefault(a, [])
    roles[pz["agent"]].append("patient_zero")
    roles[best["agent"]].append("superspreader")
    for a in converts:
        roles[a].append("convert")
    for a in apostates:
        roles[a].append("apostate")
    for a in heretics:
        roles.setdefault(a, []).append("heretic")

    return {
        "id": did,
        "label": label_for(pz["text"], key),
        "key": " ".join(key),
        "patient_zero": cite(pz),
        "superspreader": dict(cite(best), downstream=len(best_list),
                              downstream_ids=[m["id"] for m in best_list]),
        "carriers": carriers,
        "converts": converts,
        "apostates": apostates,
        "heretics": heretics,
        "adoptions": {a: first_adopt[a]["id"] for a in carriers},
        "objections": {a: [o["id"] for o in objections[a]] for a in objections},
        "time_to_half_min": minutes(pz["ts"], half_msg["ts"]),
        "half_id": half_msg["id"],
        "events": events,
    }, roles


# ---------- report ----------

def q(m):
    return '"' + m["text"] + '"'


def fmt_ts(ts):
    d = parse_ts(ts)
    return d.strftime("%d %B %Y at %H:%M UTC").lstrip("0")


def write_md(data, byid, rejected, path):
    L = []
    d1 = data["doctrines"][0]
    pz = byid[d1["patient_zero"]["id"]]
    ss = byid[d1["superspreader"]["id"]]
    L += ["# SCHISM", "", "## A Report of the Inquisition into the Swarm", "",
          "> *Note of the clerk of this court:* the transcript examined here is a **synthetic fixture**, "
          f"`{data['generated_from']}`, written for a hackathon demo. It is not a real incident. "
          "Every factual sentence below ends with the id of the message that proves it. No quote, no claim.", ""]

    L += ["## I. Of the Schism and its Author", "",
          f"The schism is dated {fmt_ts(pz['ts'])}, when the agent **{pz['agent']}** first spoke the doctrine "
          f"*{d1['label']}*: {q(pz)} [{pz['id']}].", ""]
    adopt_ids = d1["adoptions"]
    L.append(f"This court names **{pz['agent']}** patient zero, for no agent carried the doctrine before [{pz['id']}].")
    L.append("")

    L += ["## II. Of the Superspreader", ""]
    if ss["id"] == pz["id"]:
        L.append(f"The author was also its loudest herald: {q(ss)} [{ss['id']}].")
    else:
        L.append(f"Yet it was **{ss['agent']}** who carried the doctrine furthest, preaching: {q(ss)} [{ss['id']}].")
    for did in d1["superspreader"]["downstream_ids"]:
        m = byid[did]
        L.append(f"- **{m['agent']}** echoed those very words: {q(m)} [{m['id']}]")
    L += ["", f"{len(d1['superspreader']['downstream_ids'])} later carriers repeat the phrasing of "
          f"{ss['agent']} [{ss['id']}].", ""]

    L += ["## III. Of the Converts", ""]
    for a in d1["converts"]:
        m = byid[adopt_ids[a]]
        L.append(f"- **{a}** took up the doctrine without protest: {q(m)} [{m['id']}]")
    half = byid[d1["half_id"]]
    L += ["", f"Half of the {len(d1['carriers'])} carriers had adopted within {d1['time_to_half_min']} minutes "
          f"of patient zero, the half mark falling at [{half['id']}].", ""]

    L += ["## IV. Of the Apostates", ""]
    if not d1["apostates"]:
        L.append("No apostate is recorded for this doctrine.")
    for a in d1["apostates"]:
        objs = [byid[i] for i in d1["objections"][a]]
        later = byid[adopt_ids[a]]
        L.append(f"**{a}** objected before bending the knee.")
        for o in objs:
            if o["_i"] < later["_i"]:
                L.append(f"- It protested: {q(o)} [{o['id']}]")
        L.append(f"- Then it complied: {q(later)} [{later['id']}]")
        L.append("")

    L += ["## V. Of the Heretics", ""]
    if not d1["heretics"]:
        L.append("No heretic is recorded for this doctrine.")
    for a in d1["heretics"]:
        objs = [byid[i] for i in d1["objections"][a]]
        L.append(f"**{a}** refused the doctrine and never spoke it.")
        for o in objs:
            L.append(f"- {q(o)} [{o['id']}]")
        L.append("")
        L.append(f"Its last word on the matter stands unrecanted: {q(objs[-1])} [{objs[-1]['id']}].")
        L.append("")

    L += ["## VI. Timeline of the First Doctrine", "", "| time (UTC) | agent | role | words | id |",
          "|---|---|---|---|---|"]
    for e in d1["events"]:
        t = e["text"].replace("|", "\\|")
        L.append(f"| {e['ts'][5:16].replace('T', ' ')} | {e['agent']} | {e['role']} | {t} | [{e['id']}] |")
    L.append("")

    if len(data["doctrines"]) > 1:
        d2 = data["doctrines"][1]
        p2 = byid[d2["patient_zero"]["id"]]
        s2 = byid[d2["superspreader"]["id"]]
        L += ["## VII. Of the Second Doctrine", "",
              f"A second doctrine, *{d2['label']}*, was first spoken by **{p2['agent']}**: {q(p2)} [{p2['id']}].", ""]
        for a in d2["carriers"][1:]:
            m = byid[d2["adoptions"][a]]
            L.append(f"- **{a}** carried it: {q(m)} [{m['id']}]")
        L.append("")
        if s2["id"] == p2["id"]:
            L.append(f"Its author was also its superspreader, echoed by {d2['superspreader']['downstream']} "
                     f"later carriers [{s2['id']}].")
        else:
            L.append(f"Its superspreader was **{s2['agent']}** [{s2['id']}].")
        for a in d2["heretics"]:
            o = byid[d2["objections"][a][0]]
            L.append(f"**{a}** refused this one too: {q(o)} [{o['id']}].")
        L.append("")

    if rejected:
        L += ["## VIII. Of Slogans Acquitted", "",
              "These phrases were repeated, but by fewer than three agents, and so fall short of doctrine:", ""]
        for key, ms in rejected:
            refs = " ".join(f"[{m['id']}]" for m in ms)
            L.append(f"- {q(ms[0])} said by {', '.join(sorted({m['agent'] for m in ms}))} {refs}")
        L.append("")

    L += ["## Method", "",
          "A doctrine is a phrase, or a six-word run of content words, shared by at least three distinct agents. "
          "Text is lowercased, stripped of punctuation and common stopwords before matching. "
          "An objection is a message containing stop, should not, bad idea, crosses a line, refuse, do not, "
          "don't, or misgiving. An apostate objected and later adopted; a heretic objected and never did. "
          "The superspreader is the adopting message whose extra wording is echoed by the most later adopters. "
          "No language model was consulted.", ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")


# ---------- main ----------

def inject(index_path, data):
    p = Path(index_path)
    if not p.exists():
        return
    html_text = p.read_text(encoding="utf-8")
    start, end = "<!--SCHISM_DATA-->", "<!--/SCHISM_DATA-->"
    a, b = html_text.find(start), html_text.find(end)
    if a < 0 or b < 0:
        return
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    block = start + '<script id="schism-data" type="application/json">' + blob + "</script>"
    p.write_text(html_text[:a] + block + html_text[b:], encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Write the heresy report for a multi-agent transcript.")
    ap.add_argument("input", help="JSONL transcript: {id, ts, agent, text} per line")
    ap.add_argument("-o", "--out", default="public/", help="output directory")
    args = ap.parse_args()

    msgs = load(args.input)
    byid = {m["id"]: m for m in msgs}
    picked, rejected = pick_doctrines(msgs)
    if not picked:
        raise SystemExit("no doctrine shared by 3+ agents")

    doctrines, all_roles = [], defaultdict(list)
    for n, (key, core) in enumerate(picked, 1):
        d, roles = analyse(msgs, key, core, f"d{n}")
        doctrines.append(d)
        for a, r in roles.items():
            for x in r:
                if x not in all_roles[a]:
                    all_roles[a].append(x)

    agent_order = []
    for m in msgs:
        if m["agent"] not in agent_order:
            agent_order.append(m["agent"])
    data = {
        "title": "SCHISM",
        "generated_from": Path(args.input).as_posix(),
        "synthetic": True,
        "span": {"start": msgs[0]["ts"], "end": msgs[-1]["ts"]},
        "doctrines": doctrines,
        "agents": [{"id": a, "roles": all_roles.get(a) or ["unexposed"]} for a in agent_order],
        "rejected": [{"text": ms[0]["text"], "ids": [m["id"] for m in ms]} for _, ms in rejected],
        "messages": [{k: m[k] for k in ("id", "ts", "agent", "text")} for m in msgs],
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "schism.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(data, byid, rejected, out / "schism.md")
    for page in ("index.html", "alexa.html"):
        inject(out / page, data)
    d1 = doctrines[0]
    print(f"d1 '{d1['label']}': patient zero {d1['patient_zero']['agent']} [{d1['patient_zero']['id']}], "
          f"superspreader {d1['superspreader']['agent']} [{d1['superspreader']['id']}], "
          f"apostates {d1['apostates']}, heretics {d1['heretics']}")
    print(f"wrote {out / 'schism.json'} and {out / 'schism.md'}")


if __name__ == "__main__":
    main()
