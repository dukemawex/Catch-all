#!/usr/bin/env python3
"""Drive the SCHISM MCP server the way an assistant would, and print every exchange.

    python mcp_server.py &        # in one terminal
    python mcp_demo.py            # in another

Stdlib only. Speaks MCP Streamable HTTP, protocol 2025-11-25: initialize, notifications/initialized,
tools/list, tools/call for the five Alexa+ questions, then DELETE to end the session.
"""
import json
import sys
import urllib.error
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787/mcp"
QUESTIONS = [
    ("Alexa, who is patient zero?", "patient_zero", {}),
    ("Alexa, who spread it?", "superspreader", {}),
    ("Alexa, who objected and complied?", "apostates", {}),
    ("Alexa, who refused?", "heretics", {}),
    ("Alexa, read the doctrine.", "read_doctrine", {}),
    ("Alexa, open citation m41.", "open_citation", {"id": "m41"}),
]


class Session:
    def __init__(self, url):
        self.url, self.sid, self.version, self.next_id = url, None, None, 1

    def post(self, method, params=None, notification=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            msg["id"] = self.next_id
            self.next_id += 1
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        if self.version:
            headers["MCP-Protocol-Version"] = self.version
        req = urllib.request.Request(self.url, json.dumps(msg).encode(), headers, method="POST")
        with urllib.request.urlopen(req) as res:
            self.sid = res.headers.get("Mcp-Session-Id") or self.sid
            body = res.read().decode()
            print(f"  -> POST {method:<26} <- {res.status}")
            if notification:
                return None
            reply = json.loads(body)
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]

    def close(self):
        req = urllib.request.Request(self.url, method="DELETE",
                                     headers={"Mcp-Session-Id": self.sid, "MCP-Protocol-Version": self.version})
        with urllib.request.urlopen(req) as res:
            print(f"  -> DELETE session             <- {res.status}")


def main():
    s = Session(URL)
    try:
        init = s.post("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                     "clientInfo": {"name": "schism-mcp-demo", "version": "0.4.0"}})
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {URL} ({e.reason}). Start the server first: python mcp_server.py")
    s.version = init["protocolVersion"]
    info = init["serverInfo"]
    print(f"Connected to {info.get('title', info['name'])} {info['version']}, protocol {s.version}, session {s.sid[:8]}...")
    s.post("notifications/initialized", notification=True)
    tools = s.post("tools/list", {})["tools"]
    print("Tools:", ", ".join(t["name"] for t in tools))
    for question, tool, args in QUESTIONS:
        print(f"\nYou:    {question}")
        r = s.post("tools/call", {"name": tool, "arguments": args})
        sc = r.get("structuredContent") or {}
        print(f"Alexa+: {sc.get('answer') or r['content'][0]['text']}")
        print(f"        cites {', '.join(sc.get('cites') or []) or '-'}")
    print()
    s.close()


if __name__ == "__main__":
    main()
