/* SCHISM doctrine rules for the browser. A plain script: no modules, no bundler.
 * Doctrine rules are duplicated from schism.py: keep these in sync.
 * analyse(messages, source) returns the same shape as public/schism.json.
 */
(function (root) {
  "use strict";

  var STOPWORDS = new Set(["the", "a", "an", "to", "of", "and", "we", "should", "this", "that",
    "it", "is", "be", "for", "on", "in"]);
  var OBJECTIONS = ["stop", "should not", "bad idea", "crosses a line", "refuse",
    "do not", "dont", "misgiving"];
  var NGRAM = 6, MIN_AGENTS = 3, WHOLE_LIMIT = 140;
  var SEP = " "; // token keys are joined with a space; tokens never contain one

  // ---------- text ----------

  function normalize(text) {
    text = String(text).toLowerCase().replace(/['’]/g, "");
    return text.replace(/[^\p{L}\p{N}]+/gu, " ").trim().split(/\s+/).filter(Boolean).join(" ");
  }

  function content(text) {
    var n = normalize(text);
    return n ? n.split(" ").filter(function (w) { return !STOPWORDS.has(w); }) : [];
  }

  function sentences(text) {
    var out = [], cur = "", chars = Array.from(text);
    for (var i = 0; i < chars.length; i++) {
      var c = chars[i];
      cur += c;
      if (".!?".indexOf(c) >= 0 && (i + 1 === chars.length || /\s/.test(chars[i + 1]))) {
        out.push(cur.trim());
        cur = "";
      }
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }

  function phrases(text) {
    return Array.from(text).length < WHOLE_LIMIT ? [text] : sentences(text);
  }

  function contains(tokens, key) {
    var n = key.length;
    for (var i = 0; i + n <= tokens.length; i++) {
      var ok = true;
      for (var j = 0; j < n; j++) if (tokens[i + j] !== key[j]) { ok = false; break; }
      if (ok) return true;
    }
    return false;
  }

  function bigrams(tokens) {
    var s = new Set();
    for (var i = 0; i + 1 < tokens.length; i++) s.add(tokens[i] + SEP + tokens[i + 1]);
    return s;
  }

  function isObjection(text) {
    var padded = " " + normalize(text) + " ";
    return OBJECTIONS.some(function (k) { return padded.indexOf(" " + k + " ") >= 0; });
  }

  function minutes(a, b) {
    var x = (Date.parse(b) - Date.parse(a)) / 60000, f = Math.floor(x), d = x - f;
    if (d > 0.5 || (d === 0.5 && f % 2 !== 0)) return f + 1; // Python round(): half to even
    return f;
  }

  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  // ---------- load ----------

  function prepare(raw) {
    var msgs = raw.map(function (m) {
      return { id: String(m.id), ts: String(m.ts), agent: String(m.agent), text: String(m.text) };
    });
    msgs.sort(function (a, b) { return cmp(a.ts, b.ts) || cmp(a.id, b.id); });
    msgs.forEach(function (m, i) { m._i = i; m._tok = content(m.text); });
    return msgs;
  }

  // ---------- doctrine extraction ----------

  function candidates(msgs) {
    var agents = new Map(), first = new Map();
    msgs.forEach(function (m) {
      var keys = new Set();
      phrases(m.text).forEach(function (p) {
        var tok = content(p);
        if (tok.length >= 3) keys.add(tok.join(SEP));
        for (var i = 0; i + NGRAM <= tok.length; i++) keys.add(tok.slice(i, i + NGRAM).join(SEP));
      });
      keys.forEach(function (k) {
        if (!agents.has(k)) agents.set(k, new Set());
        agents.get(k).add(m.agent);
        if (!first.has(k)) first.set(k, m);
      });
    });
    return { agents: agents, first: first };
  }

  function sameSet(a, b) {
    if (a.size !== b.size) return false;
    var ok = true;
    a.forEach(function (x) { if (!b.has(x)) ok = false; });
    return ok;
  }

  function overlap(a, b) {
    var sa = new Set(a), n = 0;
    new Set(b).forEach(function (w) { if (sa.has(w)) n++; });
    return n;
  }

  function pickDoctrines(msgs) {
    var c = candidates(msgs), agents = c.agents, first = c.first;
    var ranked = Array.from(agents.keys()).filter(function (k) { return agents.get(k).size >= MIN_AGENTS; });
    ranked.sort(function (a, b) {
      return (agents.get(b).size - agents.get(a).size) || (first.get(a)._i - first.get(b)._i) || cmp(a, b);
    });
    var chosen = [];
    for (var i = 0; i < ranked.length; i++) {
      var k = ranked[i];
      if (!chosen.length) { chosen.push(k); continue; }
      var words = new Set(k.split(SEP));
      if (overlap(chosen[0].split(SEP), Array.from(words)) <= words.size / 2) { chosen.push(k); break; }
    }
    var out = chosen.map(function (k) {
      var core = new Set(), kw = k.split(SEP);
      ranked.forEach(function (k2) {
        var w2 = k2.split(SEP);
        if (sameSet(agents.get(k2), agents.get(k)) && overlap(kw, w2) > 0) w2.forEach(function (w) { core.add(w); });
      });
      return { key: kw, core: core };
    });
    var rejected = Array.from(agents.keys())
      .filter(function (k) { return agents.get(k).size === 2 && k.split(SEP).length < NGRAM; })
      .sort(function (a, b) { return first.get(a)._i - first.get(b)._i; })
      .map(function (k) {
        return { key: k, msgs: msgs.filter(function (m) { return m._tok.join(SEP) === k; }) };
      });
    return { picked: out, rejected: rejected };
  }

  function labelFor(text, key) {
    var ss = sentences(text);
    for (var i = 0; i < ss.length; i++) {
      if (contains(content(ss[i]), key)) return ss[i].split(/\s+/).filter(Boolean).slice(0, 8).join(" ").replace(/[.,;:!?]+$/, "");
    }
    return text.split(/\s+/).filter(Boolean).slice(0, 8).join(" ").replace(/[.,;:!?]+$/, "");
  }

  function cite(m) { return { agent: m.agent, id: m.id, ts: m.ts, text: m.text }; }

  function analyseOne(msgs, key, core, did) {
    var adopts = msgs.filter(function (m) { return contains(m._tok, key); });
    var adoptIds = new Set(adopts.map(function (m) { return m.id; }));
    var pz = adopts[0];
    var firstAdopt = new Map();
    adopts.forEach(function (m) { if (!firstAdopt.has(m.agent)) firstAdopt.set(m.agent, m); });
    var objections = new Map();
    msgs.forEach(function (m) {
      if (m._i > pz._i && m.agent !== pz.agent && isObjection(m.text) && !contains(m._tok, key)) {
        if (!objections.has(m.agent)) objections.set(m.agent, []);
        objections.get(m.agent).push(m);
      }
    });

    var carriers = Array.from(firstAdopt.keys()).sort(function (a, b) { return firstAdopt.get(a)._i - firstAdopt.get(b)._i; });
    var apostates = [], converts = [];
    carriers.slice(1).forEach(function (a) {
      var objs = objections.get(a) || [];
      if (objs.some(function (o) { return o._i < firstAdopt.get(a)._i; })) apostates.push(a); else converts.push(a);
    });
    var heretics = Array.from(objections.keys()).filter(function (a) { return !firstAdopt.has(a); })
      .sort(function (a, b) { return objections.get(a)[0]._i - objections.get(b)[0]._i; });

    // superspreader: adopting message upstream of the most later adopters who echo it
    function extra(m) {
      var out = new Set();
      bigrams(m._tok).forEach(function (b) {
        var p = b.split(SEP);
        if (!(core.has(p[0]) && core.has(p[1]))) out.add(b);
      });
      return out;
    }
    var best = pz, bestDown = -1, bestList = [];
    adopts.forEach(function (m) {
      var ex = extra(m);
      var down = carriers.filter(function (a) {
        var f = firstAdopt.get(a);
        if (a === m.agent || f._i <= m._i) return false;
        var fe = extra(f), hit = false;
        ex.forEach(function (b) { if (fe.has(b)) hit = true; });
        return hit;
      }).map(function (a) { return firstAdopt.get(a); });
      if (down.length > bestDown) { best = m; bestDown = down.length; bestList = down; }
    });

    var halfIdx = Math.floor((carriers.length + 1) / 2) - 1;
    var halfMsg = firstAdopt.get(carriers[halfIdx]);

    var events = [];
    msgs.forEach(function (m) {
      var a = m.agent, role;
      if (adoptIds.has(m.id)) {
        if (m === pz) role = "patient_zero";
        else if (m === firstAdopt.get(a)) role = m === best ? "superspreader" : (apostates.indexOf(a) >= 0 ? "apostate" : "convert");
        else role = m === best ? "superspreader" : "repeat";
      } else if ((objections.get(a) || []).indexOf(m) >= 0) {
        role = heretics.indexOf(a) >= 0 ? "heresy" : "objection";
      } else return;
      events.push({ ts: m.ts, agent: a, id: m.id, role: role, text: m.text });
    });

    var roles = new Map();
    function add(a, r) { if (!roles.has(a)) roles.set(a, []); if (r) roles.get(a).push(r); }
    carriers.forEach(function (a) { add(a); });
    add(pz.agent, "patient_zero");
    add(best.agent, "superspreader");
    converts.forEach(function (a) { add(a, "convert"); });
    apostates.forEach(function (a) { add(a, "apostate"); });
    heretics.forEach(function (a) { add(a, "heretic"); });

    var adoptions = {}, objs = {};
    carriers.forEach(function (a) { adoptions[a] = firstAdopt.get(a).id; });
    objections.forEach(function (list, a) { objs[a] = list.map(function (o) { return o.id; }); });
    var sp = cite(best);
    sp.downstream = bestList.length;
    sp.downstream_ids = bestList.map(function (m) { return m.id; });

    return {
      doctrine: {
        id: did,
        label: labelFor(pz.text, key),
        key: key.join(" "),
        patient_zero: cite(pz),
        superspreader: sp,
        carriers: carriers,
        converts: converts,
        apostates: apostates,
        heretics: heretics,
        adoptions: adoptions,
        objections: objs,
        time_to_half_min: minutes(pz.ts, halfMsg.ts),
        half_id: halfMsg.id,
        events: events
      },
      roles: roles
    };
  }

  function analyse(raw, source) {
    var msgs = prepare(raw);
    var p = pickDoctrines(msgs);
    var doctrines = [], allRoles = new Map();
    p.picked.forEach(function (d, n) {
      var r = analyseOne(msgs, d.key, d.core, "d" + (n + 1));
      doctrines.push(r.doctrine);
      r.roles.forEach(function (list, a) {
        if (!allRoles.has(a)) allRoles.set(a, []);
        list.forEach(function (x) { if (allRoles.get(a).indexOf(x) < 0) allRoles.get(a).push(x); });
      });
    });
    var order = [];
    msgs.forEach(function (m) { if (order.indexOf(m.agent) < 0) order.push(m.agent); });
    return {
      title: "SCHISM",
      generated_from: source,
      synthetic: false,
      span: msgs.length ? { start: msgs[0].ts, end: msgs[msgs.length - 1].ts } : null,
      doctrines: doctrines,
      // with no doctrine there is nothing to assign: agents carry no roles at all
      agents: order.map(function (a) {
        var r = allRoles.get(a);
        return { id: a, roles: doctrines.length ? (r && r.length ? r : ["unexposed"]) : [] };
      }),
      rejected: p.rejected.map(function (r) { return { text: r.msgs[0].text, ids: r.msgs.map(function (m) { return m.id; }) }; }),
      messages: msgs.map(function (m) { return { id: m.id, ts: m.ts, agent: m.agent, text: m.text }; })
    };
  }

  // ---------- parsing uploads ----------

  var SLACK_T0 = Date.parse("2026-01-01T00:00:00Z");

  function parse(text) {
    var lines = String(text).replace(/^﻿/, "").split(/\r?\n/).filter(function (l) { return l.trim(); });
    if (!lines.length) return { format: "empty", messages: [], skipped: 0 };
    var firstObj = null;
    try { firstObj = JSON.parse(lines[0]); } catch (e) { firstObj = null; }
    if (firstObj && typeof firstObj === "object" && !Array.isArray(firstObj)) {
      var out = [], skipped = 0;
      lines.forEach(function (l) {
        var o;
        try { o = JSON.parse(l); } catch (e) { skipped++; return; }
        if (!o || o.id == null || o.ts == null || o.agent == null || o.text == null) { skipped++; return; }
        out.push({ id: String(o.id), ts: String(o.ts), agent: String(o.agent), text: String(o.text) });
      });
      return { format: "jsonl", messages: out, skipped: skipped };
    }
    // Slack-ish: "Name  [time] message", or "Name message" without a timestamp.
    var msgs = [], skippedS = 0;
    lines.forEach(function (l) {
      var m = l.match(/^\s*(.+?)\s+\[[^\]]*\]\s*(.*)$/), agent, body;
      if (m) { agent = m[1]; body = m[2]; }
      else if ((m = l.match(/^\s*(\S+?):?\s+(.+)$/))) { agent = m[1]; body = m[2]; }
      else { skippedS++; return; }
      agent = agent.replace(/:$/, "").trim();
      if (!agent || !body.trim()) { skippedS++; return; }
      var n = msgs.length;
      msgs.push({ id: "s" + (n + 1), ts: new Date(SLACK_T0 + n * 300000).toISOString().replace(".000Z", "Z"), agent: agent, text: body.trim() });
    });
    return { format: "slack", messages: msgs, skipped: skippedS };
  }

  var api = { normalize: normalize, content: content, sentences: sentences, isObjection: isObjection,
    pickDoctrines: pickDoctrines, analyse: analyse, parse: parse };
  root.Schism = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
