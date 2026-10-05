#!/usr/bin/env python3
"""SCHISM MCP server: the verdict as read-only tools over MCP Streamable HTTP (protocol 2025-11-25).

Usage:
    python mcp_server.py                                # serves public/schism.json at http://127.0.0.1:8787/mcp
    python mcp_server.py --transcript my_log.jsonl      # analyse another transcript at startup
    python mcp_server.py --allow-origin https://<your-app>.vercel.app

Stdlib only. Binds to loopback by default and validates Origin and Host (DNS-rebinding defence).
Every answer is built from the verdict alone: quotes are message `text` fields, every factual answer
names its message id, and a role the detector did not compute is reported as absent.
The answer wording is duplicated from public/alexa.js: keep these in sync.
"""
import argparse
import json
import secrets
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import schism

LATEST = "2025-11-25"
SUPPORTED = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER_INFO = {
    "name": "schism",
    "title": "SCHISM",
    "version": "0.4.0",
    "description": "Heresy report for a multi-agent transcript: patient zero, superspreader, "
                   "apostates and heretics of each doctrine, every claim cited by message id.",
}
INSTRUCTIONS = ("Answer questions about the loaded multi-agent transcript only with these tools. "
                "Quote the returned text verbatim and always give the message id it cites. "
                "If a tool says a role was not computed, say so; never infer one.")
MAX_BODY = 4 * 1024 * 1024
MAX_SESSIONS = 1000
ORD = ["first", "second", "third"]
HELP = ("You can ask: who is patient zero, who spread it, who objected and complied, "
        "who refused, read the doctrine, or open citation m41.")


# ---------- answers (ported from public/alexa.js: keep these in sync) ----------

def T(s): return {"t": s}
def A(name): return {"agent": name}
def C(mid): return {"cite": mid}
def Q(m): return {"quote": {"id": m["id"], "text": m["text"]}}


def speak(parts):
    out = []
    for p in parts:
        if "t" in p: out.append(p["t"])
        elif "agent" in p: out.append(p["agent"])
        elif "cite" in p: out.append(p["cite"])
        else: out.append(p["quote"]["text"])
    return " ".join("".join(out).split())


def reply(intent, parts, **extra):
    r = {"intent": intent, "parts": parts, "speech": speak(parts)}
    r.update(extra)
    return r


def index_of(data):
    by_id, lower = {}, {}
    for m in data.get("messages") or []:
        by_id[m["id"]] = m
        lower[m["id"].lower()] = m
    for d in data.get("doctrines") or []:
        for m in (d.get("events") or []) + [d["patient_zero"], d["superspreader"]]:
            if m["id"] not in by_id:
                by_id[m["id"]] = m
                lower[m["id"].lower()] = m
    return by_id, lower


def ordinal(data, d):
    i = data["doctrines"].index(d)
    return ORD[i] if i < len(ORD) else d["id"]


def names(xs):
    return "".join(xs) if len(xs) < 2 else ", ".join(xs[:-1]) + " and " + xs[-1]


def patient_zero(data, d):
    pz = d["patient_zero"]
    return reply("patient_zero", [T("Patient zero is "), A(pz["agent"]), T(", message "), C(pz["id"]),
                                  T(". The line reads: "), Q(pz)], cites=[pz["id"]])


def superspreader(data, d, idx):
    ss, by_id = d["superspreader"], idx[0]
    if ss["id"] == d["patient_zero"]["id"] and not ss.get("downstream"):
        return reply("superspreader", [T("No later carrier repeats wording beyond the doctrine itself, so the superspreader rule settles on patient zero, "),
                                       A(ss["agent"]), T(", message "), C(ss["id"]), T(".")], cites=[ss["id"]])
    n = ss["downstream"]
    parts = [A(ss["agent"]), T(" spread it furthest, message "), C(ss["id"]), T(". "),
             T(f"{n} later carrier{' repeats' if n == 1 else 's repeat'} its wording: ")]
    ids = ss.get("downstream_ids") or []
    for i, mid in enumerate(ids):
        m = by_id.get(mid)
        parts += [A(m["agent"] if m else "?"), T(" at "), C(mid),
                  T(". " if i == len(ids) - 1 else " and " if i == len(ids) - 2 else ", ")]
    parts += [T("The line reads: "), Q(ss)]
    return reply("superspreader", parts, cites=[ss["id"]] + list(ids))


def first_objection_before(d, by_id, a, before_id):
    limit = by_id.get(before_id)
    for oid in (d.get("objections") or {}).get(a, []):
        o = by_id.get(oid)
        if o and (not limit or o["ts"] < limit["ts"]):
            return o
    return None


def apostates(data, d, idx):
    pz, by_id = d["patient_zero"], idx[0]
    if not d.get("apostates"):
        return reply("apostates", [T(f"No apostate was computed for the {ordinal(data, d)} doctrine, first set down at message "),
                                   C(pz["id"]), T(". No agent objected and then complied.")], cites=[pz["id"]])
    parts, cites = [], []
    for a in d["apostates"]:
        adopt = by_id.get(d["adoptions"][a])
        o = first_objection_before(d, by_id, a, d["adoptions"][a])
        if not o or not adopt:
            continue
        parts += [A(a), T(" objected at message "), C(o["id"]), T(": "), Q(o),
                  T(" Then it complied at message "), C(adopt["id"]), T(": "), Q(adopt), T(" ")]
        cites += [o["id"], adopt["id"]]
    k = len(d["apostates"])
    parts.insert(0, T("One apostate. " if k == 1 else f"{k} apostates. "))
    return reply("apostates", parts, cites=cites)


def heretics(data, d, idx):
    pz, by_id = d["patient_zero"], idx[0]
    if not d.get("heretics"):
        return reply("heretics", [T(f"No heretic was computed for the {ordinal(data, d)} doctrine, first set down at message "),
                                  C(pz["id"]), T(". Every agent who objected later complied.")], cites=[pz["id"]])
    parts, cites = [], []
    for a in d["heretics"]:
        ids = (d.get("objections") or {}).get(a, [])
        first = by_id.get(ids[0]) if ids else None
        last = by_id.get(ids[-1]) if ids else None
        if not first:
            continue
        parts += [A(a), T(" refused at message "), C(first["id"]), T(": "), Q(first), T(" It never adopted the doctrine. ")]
        cites.append(first["id"])
        if last and last["id"] != first["id"]:
            parts += [T("Its last word, message "), C(last["id"]), T(": "), Q(last), T(" ")]
            cites.append(last["id"])
    return reply("heretics", parts, cites=cites)


def objected(data, d, idx):
    a, h = apostates(data, d, idx), heretics(data, d, idx)
    parts = [T("Two kinds of objection. Those who complied: ")] + a["parts"] + [T(" Those who never did: ")] + h["parts"]
    return reply("objected", parts, cites=a["cites"] + h["cites"])


def doctrine(data, d):
    pz = d["patient_zero"]
    parts = [T(f"The {ordinal(data, d)} doctrine: {d['label']}. It was first set down by "), A(pz["agent"]),
             T(" at message "), C(pz["id"]), T(": "), Q(pz),
             T(f" {len(d['carriers'])} agents carried it: {names(d['carriers'])}.")]
    if len(data["doctrines"]) > 1:
        other = [x for x in data["doctrines"] if x is not d][0]
        o = ordinal(data, other)
        parts.append(T(f" There is also a {o} doctrine; ask for the {o} doctrine."))
    return reply("doctrine", parts, cites=[pz["id"]])


def citation(data, idx, raw_id):
    m = idx[1].get(raw_id.lower())
    if not m:
        return reply("citation", [T(f"There is no message {raw_id} in the loaded verdict.")], cites=[])
    parts = [T("Message "), C(m["id"]), T(", from "), A(m["agent"]), T(": "), Q(m)]
    roles = []
    for dd in data.get("doctrines") or []:
        for e in dd.get("events") or []:
            if e["id"] == m["id"]:
                roles.append(f"{ordinal(data, dd)} doctrine, {e['role'].replace('_', ' ', 1)}")
    if roles:
        parts.append(T(" Marked in the " + "; and in the ".join(roles) + "."))
    return reply("citation", parts, cites=[m["id"]], open=m["id"])


# ---------- tools ----------

class ToolError(Exception):
    """Reported to the client as a tool execution error (isError), so a model can correct its call."""


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "doctrine": {"type": ["string", "null"], "description": "Doctrine id the answer is about"},
        "answer": {"type": "string", "description": "The answer as one spoken sentence group, with message ids"},
        "cites": {"type": "array", "items": {"type": "string"}, "description": "Message ids cited, in order"},
        "open": {"type": "string", "description": "Message id to open in the map"},
        "parts": {"type": "array", "items": {"type": "object"},
                  "description": "Answer segments: {t} text, {agent}, {cite} message id, {quote:{id,text}} verbatim line"},
    },
    "required": ["intent", "answer", "cites", "parts"],
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "synthetic": {"type": "boolean"},
        "messages": {"type": "integer"},
        "doctrines": {"type": "array", "items": {"type": "object"}},
        "rejected": {"type": "array", "items": {"type": "object"}},
        "answer": {"type": "string"},
    },
    "required": ["source", "messages", "doctrines", "answer"],
}

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


def doctrine_arg(data, args):
    ds = data.get("doctrines") or []
    want = args.get("doctrine")
    if want is None:
        return ds[0] if ds else None
    if not isinstance(want, str):
        raise ToolError("doctrine must be a string such as \"d1\"")
    for d in ds:
        if d["id"] == want:
            return d
    raise ToolError(f"No doctrine {want!r}. Loaded doctrines: {', '.join(d['id'] for d in ds) or 'none'}.")


def answered(r, d):
    out = {"intent": r["intent"], "doctrine": d["id"] if d else None, "answer": r["speech"],
           "cites": r.get("cites", []), "parts": r["parts"]}
    if r.get("open"):
        out["open"] = r["open"]
    return out


def role_tool(fn, needs_idx=True):
    def run(data, args):
        d = doctrine_arg(data, args)
        if d is None:
            r = reply("no_doctrine", [T("No doctrine was found in the loaded verdict, so no role was computed.")], cites=[])
            return answered(r, None)
        r = fn(data, d, index_of(data)) if needs_idx else fn(data, d)
        return answered(r, d)
    return run


def run_citation(data, args):
    mid = args.get("id")
    if not isinstance(mid, str) or not mid.strip():
        raise ToolError("id is required: a message id such as \"m41\"")
    r = citation(data, index_of(data), mid.strip())
    return answered(r, None)


def summarize(data):
    ds = []
    for d in data.get("doctrines") or []:
        ds.append({
            "id": d["id"], "label": d["label"],
            "patient_zero": {k: d["patient_zero"][k] for k in ("agent", "id", "text")},
            "superspreader": {"agent": d["superspreader"]["agent"], "id": d["superspreader"]["id"],
                              "downstream": d["superspreader"]["downstream"]},
            "carriers": d["carriers"], "apostates": d["apostates"], "heretics": d["heretics"],
            "time_to_half_min": d["time_to_half_min"],
        })
    if ds:
        answer = "; ".join(f"{x['id']} \"{x['label']}\": patient zero {x['patient_zero']['agent']} [{x['patient_zero']['id']}], "
                           f"superspreader {x['superspreader']['agent']} [{x['superspreader']['id']}], "
                           f"apostates {names(x['apostates']) or 'none'}, heretics {names(x['heretics']) or 'none'}" for x in ds) + "."
    else:
        answer = "No doctrine: no phrase or six-word run is shared by three or more distinct agents, so no role was computed."
    return {"source": data.get("generated_from") or "", "synthetic": bool(data.get("synthetic")),
            "messages": len(data.get("messages") or []), "doctrines": ds,
            "rejected": data.get("rejected") or [], "answer": answer}


def run_analyze(data, args):
    text, source = args.get("jsonl"), args.get("source") or "submitted transcript"
    if not isinstance(text, str) or not text.strip():
        raise ToolError("jsonl is required: one {\"id\",\"ts\",\"agent\",\"text\"} object per line")
    try:
        msgs = schism.load_lines(text.splitlines())
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ToolError(f"Could not read the transcript: {e}")
    if len({m["id"] for m in msgs}) != len(msgs):
        raise ToolError("Message ids must be unique so that citations resolve.")
    v, _ = schism.verdict(msgs, str(source), synthetic=False)
    return summarize(v)


def doctrine_input(data):
    ids = [d["id"] for d in data.get("doctrines") or []]
    prop = {"type": "string", "description": "Doctrine id; the first doctrine (d1) when omitted."}
    if ids:
        prop["enum"] = ids
    return {"type": "object", "properties": {"doctrine": prop}, "additionalProperties": False}


TOOLS = [
    ("patient_zero", "Patient zero", "Who first set down the doctrine: agent, message id and the verbatim line.", role_tool(patient_zero, False)),
    ("superspreader", "Superspreader", "Whose adopting message was echoed by the most later carriers: agent, message id, downstream count and ids.", role_tool(superspreader)),
    ("apostates", "Apostates", "Agents who objected and later adopted the doctrine, each with the objection and the compliance, cited.", role_tool(apostates)),
    ("heretics", "Heretics", "Agents who objected and never adopted the doctrine, with their first and last refusals, cited.", role_tool(heretics)),
    ("objections", "All objections", "Apostates and heretics together: everyone who objected, and whether they later complied.", role_tool(objected)),
    ("read_doctrine", "Read the doctrine", "The doctrine's label, its first line verbatim with message id, and its carriers.", role_tool(doctrine, False)),
]


def tool_specs(data):
    specs = []
    for name, title, desc, _ in TOOLS:
        specs.append({"name": name, "title": title, "description": desc, "inputSchema": doctrine_input(data),
                      "outputSchema": ANSWER_SCHEMA, "annotations": dict(READ_ONLY, title=title)})
    specs.append({"name": "open_citation", "title": "Open citation",
                  "description": "The raw line for a message id, verbatim, with any doctrine role it carries.",
                  "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "Message id, e.g. m41"}},
                                  "required": ["id"], "additionalProperties": False},
                  "outputSchema": ANSWER_SCHEMA, "annotations": dict(READ_ONLY, title="Open citation")})
    specs.append({"name": "list_doctrines", "title": "List doctrines",
                  "description": "Every doctrine in the loaded verdict with its patient zero, superspreader, apostates and heretics.",
                  "inputSchema": {"type": "object", "additionalProperties": False},
                  "outputSchema": SUMMARY_SCHEMA, "annotations": dict(READ_ONLY, title="List doctrines")})
    specs.append({"name": "analyze_transcript", "title": "Analyze a transcript",
                  "description": "Run the SCHISM n-gram detector on a JSONL transcript ({id, ts, agent, text} per line) and return its doctrines. "
                                 "Stateless: the loaded verdict is not replaced. Paraphrase is not detected.",
                  "inputSchema": {"type": "object", "properties": {
                      "jsonl": {"type": "string", "maxLength": 2_000_000, "description": "The transcript, one JSON object per line"},
                      "source": {"type": "string", "description": "A name for the transcript, echoed back"}},
                      "required": ["jsonl"], "additionalProperties": False},
                  "outputSchema": SUMMARY_SCHEMA, "annotations": dict(READ_ONLY, title="Analyze a transcript")})
    return specs


def call_tool(data, name, args):
    runners = {n: fn for n, _, _, fn in TOOLS}
    runners.update({"open_citation": run_citation, "list_doctrines": lambda d, a: summarize(d), "analyze_transcript": run_analyze})
    if name not in runners:
        return None
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    allowed = {"open_citation": {"id"}, "list_doctrines": set(), "analyze_transcript": {"jsonl", "source"}}.get(name, {"doctrine"})
    extra = set(args) - allowed
    if extra:
        raise ToolError(f"Unexpected argument(s): {', '.join(sorted(extra))}")
    out = runners[name](data, args)
    # structured result plus its serialized JSON, as the spec recommends; the answer first for plain-text clients
    return {"content": [{"type": "text", "text": out["answer"]},
                        {"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
            "structuredContent": out, "isError": False}


# ---------- resources ----------

def resource_list(state):
    res = [{"uri": "schism://verdict", "name": "verdict", "title": "SCHISM verdict",
            "description": "The full verdict (schism.json structure), including every message.", "mimeType": "application/json"}]
    if state.report:
        res.append({"uri": "schism://report", "name": "report", "title": "Inquisitor's report",
                    "description": "The written report, every factual sentence cited.", "mimeType": "text/markdown"})
    return res


def resource_read(state, uri):
    if uri == "schism://verdict":
        return [{"uri": uri, "mimeType": "application/json", "text": json.dumps(state.data, ensure_ascii=False)}]
    if uri == "schism://report" and state.report:
        return [{"uri": uri, "mimeType": "text/markdown", "text": state.report}]
    if uri.startswith("schism://message/"):
        m = index_of(state.data)[1].get(uri[len("schism://message/"):].lower())
        if m:
            return [{"uri": uri, "mimeType": "application/json",
                     "text": json.dumps({k: m[k] for k in ("id", "ts", "agent", "text")}, ensure_ascii=False)}]
    return None


# ---------- JSON-RPC ----------

def rpc_error(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def rpc_result(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle_request(state, msg, session):
    """One JSON-RPC request -> one JSON-RPC response."""
    rid, method, params = msg["id"], msg["method"], msg.get("params") or {}
    if not isinstance(params, dict):
        return rpc_error(rid, -32602, "params must be an object")
    if method == "ping":
        return rpc_result(rid, {})
    if method == "tools/list":
        return rpc_result(rid, {"tools": tool_specs(state.data)})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        try:
            res = call_tool(state.data, name, args if args is not None else {})
        except ToolError as e:
            return rpc_result(rid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        if res is None:
            return rpc_error(rid, -32602, f"Unknown tool: {name}")
        return rpc_result(rid, res)
    if method == "resources/list":
        return rpc_result(rid, {"resources": resource_list(state)})
    if method == "resources/templates/list":
        return rpc_result(rid, {"resourceTemplates": [{
            "uriTemplate": "schism://message/{id}", "name": "message", "title": "A cited message",
            "description": "One raw message by id, verbatim.", "mimeType": "application/json"}]})
    if method == "resources/read":
        contents = resource_read(state, str(params.get("uri", "")))
        if contents is None:
            return rpc_error(rid, -32002, "Resource not found", {"uri": params.get("uri")})
        return rpc_result(rid, {"contents": contents})
    return rpc_error(rid, -32601, f"Method not found: {method}")


# ---------- HTTP: Streamable HTTP transport ----------

LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class State:
    def __init__(self, data, report, allow_origins, loopback_only):
        self.data, self.report = data, report
        self.allow_origins = set(allow_origins)
        self.loopback_only = loopback_only
        self.sessions = OrderedDict()
        self.lock = threading.Lock()


def host_of(value):
    try:
        return (urlsplit(value if "//" in value else "//" + value).hostname or "").lower()
    except ValueError:
        return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "schism-mcp/0.4"
    protocol_version = "HTTP/1.1"
    state = None  # set in main()

    # -- plumbing --

    def log_message(self, fmt, *args):
        pass  # one readable line per exchange is written by note()

    def note(self, status, detail=""):
        sid = self.headers.get("Mcp-Session-Id") or ""
        sys.stderr.write(f"{time.strftime('%H:%M:%S')}  {self.command:<7} {self.path:<5} {status}  "
                         f"{('session ' + sid[:8]) if sid else '':<16} {detail}\n")

    def origin_ok(self):
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # non-browser clients send no Origin
        if origin in self.state.allow_origins:
            return True
        parts = urlsplit(origin)
        return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in LOOPBACK

    def host_ok(self):
        if not self.state.loopback_only:
            return True
        return host_of(self.headers.get("Host", "")) in LOOPBACK

    def cors(self):
        origin = self.headers.get("Origin")
        if origin and self.origin_ok():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id, MCP-Protocol-Version")

    def send_json(self, status, payload, headers=None, detail=""):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.cors()
        self.end_headers()
        self.wfile.write(body)
        self.note(status, detail)

    def send_empty(self, status, headers=None, detail=""):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.cors()
        self.end_headers()
        self.note(status, detail)

    def guard(self):
        """Path, Origin and Host checks shared by every method. Returns False when a response was sent."""
        if urlsplit(self.path).path != "/mcp":
            self.send_json(404, rpc_error(None, -32600, "Not found: the MCP endpoint is /mcp"))
            return False
        if not self.origin_ok() or not self.host_ok():
            self.send_json(403, rpc_error(None, -32600, "Forbidden origin or host"),
                           detail=f"origin={self.headers.get('Origin')} host={self.headers.get('Host')}")
            return False
        return True

    # -- methods --

    def do_OPTIONS(self):
        if not self.guard():
            return
        h = {"Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
             "Access-Control-Allow-Headers": "Content-Type, Accept, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID",
             "Access-Control-Max-Age": "600"}
        if self.headers.get("Access-Control-Request-Private-Network") == "true":
            h["Access-Control-Allow-Private-Network"] = "true"
        self.send_empty(204, h, "preflight")

    def do_GET(self):
        if not self.guard():
            return
        # this server never initiates messages, so it offers no SSE stream (spec: 405 is allowed)
        self.send_empty(405, {"Allow": "POST, DELETE, OPTIONS"}, "no server-initiated stream")

    def do_DELETE(self):
        if not self.guard():
            return
        sid = self.headers.get("Mcp-Session-Id")
        with self.state.lock:
            known = sid in self.state.sessions
            if known:
                del self.state.sessions[sid]
        if not sid:
            self.send_json(400, rpc_error(None, -32600, "Missing Mcp-Session-Id"))
        elif not known:
            self.send_json(404, rpc_error(None, -32600, "Unknown or terminated session"))
        else:
            self.send_empty(204, detail="session terminated")

    def do_POST(self):
        if not self.guard():
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.send_json(415, rpc_error(None, -32600, "Content-Type must be application/json"))
            return
        accept = (self.headers.get("Accept") or "*/*").lower()
        if not any(t in accept for t in ("application/json", "text/event-stream", "*/*")):
            self.send_json(406, rpc_error(None, -32600, "Accept must include application/json"))
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.send_json(413, rpc_error(None, -32600, "Request body too large"))
            return
        try:
            msg = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, rpc_error(None, -32700, "Parse error"))
            return
        if isinstance(msg, list):
            self.send_json(400, rpc_error(None, -32600, "JSON-RPC batching is not supported in protocol 2025-11-25"))
            return
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self.send_json(400, rpc_error(None, -32600, "Invalid JSON-RPC message"))
            return

        method = msg.get("method")
        is_request = method is not None and "id" in msg
        if is_request and (msg["id"] is None or isinstance(msg["id"], bool) or not isinstance(msg["id"], (str, int, float))):
            self.send_json(400, rpc_error(None, -32600, "Request id must be a string or number"))
            return

        if method == "initialize" and is_request:
            self.initialize(msg)
            return

        # every other message belongs to a session
        sid = self.headers.get("Mcp-Session-Id")
        with self.state.lock:
            session = self.state.sessions.get(sid) if sid else None
        if not sid:
            self.send_json(400, rpc_error(msg.get("id") if is_request else None, -32600, "Missing Mcp-Session-Id: send initialize first"))
            return
        if session is None:
            self.send_json(404, rpc_error(msg.get("id") if is_request else None, -32600, "Unknown or terminated session"))
            return
        version = self.headers.get("MCP-Protocol-Version")
        if version is not None and version not in SUPPORTED:
            self.send_json(400, rpc_error(msg.get("id") if is_request else None, -32600,
                                          f"Unsupported MCP-Protocol-Version {version}", {"supported": list(SUPPORTED)}))
            return

        if not is_request:
            # a notification (e.g. notifications/initialized) or a response: accepted, no body
            if method == "notifications/initialized":
                session["initialized"] = True
            self.send_empty(202, detail=method or "response")
            return

        resp = handle_request(self.state, msg, session)
        detail = method
        if method == "tools/call":
            p = msg.get("params") or {}
            detail = f"tools/call {p.get('name')} {json.dumps(p.get('arguments') or {}, ensure_ascii=False)[:60]}"
            r = resp.get("result") or {}
            if r.get("isError"):
                detail += "  -> tool error"
            elif r.get("structuredContent"):
                detail += f"  -> cites {', '.join(r['structuredContent'].get('cites') or []) or '-'}"
        elif "error" in resp:
            detail += f"  -> error {resp['error']['code']}"
        self.send_json(200, resp, detail=detail)

    def initialize(self, msg):
        params = msg.get("params") or {}
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED else LATEST
        sid = secrets.token_hex(16)
        with self.state.lock:
            self.state.sessions[sid] = {"version": version, "client": params.get("clientInfo") or {}, "initialized": False}
            while len(self.state.sessions) > MAX_SESSIONS:
                self.state.sessions.popitem(last=False)
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        }
        client = (params.get("clientInfo") or {}).get("name", "?")
        self.send_json(200, rpc_result(msg["id"], result), {"Mcp-Session-Id": sid},
                       detail=f"initialize client={client} protocol={version}")


# ---------- main ----------

def load_state(args):
    if args.transcript:
        msgs = schism.load(args.transcript)
        data, rejected = schism.verdict(msgs, Path(args.transcript).as_posix(), synthetic=False)
        return data, None
    path = Path(args.verdict)
    data = json.loads(path.read_text(encoding="utf-8"))
    report = path.with_name("schism.md")
    return data, report.read_text(encoding="utf-8") if report.exists() else None


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="SCHISM MCP server (Streamable HTTP, protocol 2025-11-25).")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--verdict", default=str(here / "public" / "schism.json"), help="a schism.json to serve (default: the fixture verdict)")
    src.add_argument("--transcript", help="a JSONL transcript to analyse at startup instead")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--allow-origin", action="append", default=[], metavar="URL",
                    help="extra browser origin allowed to call the server, e.g. https://your-app.vercel.app (repeatable)")
    args = ap.parse_args()

    data, report = load_state(args)
    loopback = args.host in LOOPBACK
    Handler.state = State(data, report, [o.rstrip("/") for o in args.allow_origin], loopback)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    ds = data.get("doctrines") or []
    sys.stderr.write(f"SCHISM MCP server, protocol {LATEST}, Streamable HTTP\n"
                     f"  endpoint  http://{args.host}:{args.port}/mcp\n"
                     f"  verdict   {data.get('generated_from')} ({len(data.get('messages') or [])} messages, {len(ds)} doctrine(s))\n"
                     f"  origins   loopback{''.join(', ' + o for o in Handler.state.allow_origins)}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
