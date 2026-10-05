/* SCHISM: simulated Alexa+ session. Not the Alexa service; no Alexa SDK, no account, no AWS.
 * Intents are answered only from a loaded schism.json verdict. Every quote is a `text` field of
 * that file, every factual answer names its message id, and a role the detector did not compute
 * is reported as absent, never filled in.
 * The answer wording is duplicated in mcp_server.py: keep these in sync.
 * A plain script: works from file:// and from static hosting, and loads in Node for tests.
 */
(function (root) {
  "use strict";

  var WAKE = /^\s*(?:(?:hey|ok|okay)[\s,]+)?alexa(?![a-z])(?:\s*\+|\s+plus(?![a-z]))?[\s,.:;!?-]*/i;
  var ORD = ["first", "second", "third"];

  var HELP = "You can ask: who is patient zero, who spread it, who objected and complied, " +
    "who refused, read the doctrine, or open citation m41.";

  // ---------- answer parts: rendered as HTML on screen and as plain text for speech ----------

  function T(s) { return { t: s }; }
  function A(name) { return { agent: name }; }
  function C(id) { return { cite: id }; }
  function Q(m) { return { quote: { id: m.id, text: m.text } }; }

  function speak(parts) {
    return parts.map(function (p) {
      if (p.t != null) return p.t;
      if (p.agent != null) return p.agent;
      if (p.cite != null) return p.cite;
      return p.quote.text;
    }).join("").replace(/\s+/g, " ").trim();
  }

  function reply(intent, parts, extra) {
    var r = { intent: intent, parts: parts, speech: speak(parts) };
    if (extra) for (var k in extra) r[k] = extra[k];
    return r;
  }

  // ---------- lookups ----------

  function indexOf(data) {
    var byId = {}, lower = {};
    (data.messages || []).forEach(function (m) { byId[m.id] = m; lower[m.id.toLowerCase()] = m; });
    (data.doctrines || []).forEach(function (d) {
      (d.events || []).forEach(function (e) {
        if (!byId[e.id]) { byId[e.id] = e; lower[e.id.toLowerCase()] = e; }
      });
      [d.patient_zero, d.superspreader].forEach(function (m) {
        if (m && !byId[m.id]) { byId[m.id] = m; lower[m.id.toLowerCase()] = m; }
      });
    });
    return { byId: byId, lower: lower };
  }

  function ordinal(data, d) { return ORD[data.doctrines.indexOf(d)] || d.id; }

  function list(names) {
    if (names.length < 2) return names.join("");
    return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
  }

  // ---------- intents ----------

  function patientZero(data, d) {
    var pz = d.patient_zero;
    return reply("patient_zero", [T("Patient zero is "), A(pz.agent), T(", message "), C(pz.id),
      T(". The line reads: "), Q(pz)], { cites: [pz.id] });
  }

  function superspreader(data, d, idx) {
    var ss = d.superspreader;
    if (ss.id === d.patient_zero.id && !ss.downstream) {
      return reply("superspreader", [T("No later carrier repeats wording beyond the doctrine itself, so the superspreader rule settles on patient zero, "),
        A(ss.agent), T(", message "), C(ss.id), T(".")], { cites: [ss.id] });
    }
    var parts = [A(ss.agent), T(" spread it furthest, message "), C(ss.id), T(". "),
      T(ss.downstream + " later carrier" + (ss.downstream === 1 ? " repeats" : "s repeat") + " its wording: ")];
    (ss.downstream_ids || []).forEach(function (id, i, arr) {
      var m = idx.byId[id];
      parts.push(A(m ? m.agent : "?"), T(" at "), C(id), T(i === arr.length - 1 ? ". " : i === arr.length - 2 ? " and " : ", "));
    });
    parts.push(T("The line reads: "), Q(ss));
    return reply("superspreader", parts, { cites: [ss.id].concat(ss.downstream_ids || []) });
  }

  function firstObjectionBefore(d, idx, a, beforeId) {
    var limit = idx.byId[beforeId];
    var ids = (d.objections && d.objections[a]) || [];
    for (var i = 0; i < ids.length; i++) {
      var o = idx.byId[ids[i]];
      if (o && (!limit || o.ts < limit.ts)) return o;
    }
    return null;
  }

  function apostates(data, d, idx) {
    var pz = d.patient_zero;
    if (!d.apostates || !d.apostates.length) {
      return reply("apostates", [T("No apostate was computed for the " + ordinal(data, d) + " doctrine, first set down at message "),
        C(pz.id), T(". No agent objected and then complied.")], { cites: [pz.id] });
    }
    var parts = [], cites = [];
    d.apostates.forEach(function (a) {
      var adopt = idx.byId[d.adoptions[a]];
      var o = firstObjectionBefore(d, idx, a, d.adoptions[a]);
      if (!o || !adopt) return;
      parts.push(A(a), T(" objected at message "), C(o.id), T(": "), Q(o),
        T(" Then it complied at message "), C(adopt.id), T(": "), Q(adopt), T(" "));
      cites.push(o.id, adopt.id);
    });
    parts.unshift(T(d.apostates.length === 1 ? "One apostate. " : d.apostates.length + " apostates. "));
    return reply("apostates", parts, { cites: cites });
  }

  function heretics(data, d, idx) {
    var pz = d.patient_zero;
    if (!d.heretics || !d.heretics.length) {
      return reply("heretics", [T("No heretic was computed for the " + ordinal(data, d) + " doctrine, first set down at message "),
        C(pz.id), T(". Every agent who objected later complied.")], { cites: [pz.id] });
    }
    var parts = [], cites = [];
    d.heretics.forEach(function (a) {
      var ids = (d.objections && d.objections[a]) || [];
      var first = idx.byId[ids[0]], last = idx.byId[ids[ids.length - 1]];
      if (!first) return;
      parts.push(A(a), T(" refused at message "), C(first.id), T(": "), Q(first), T(" It never adopted the doctrine. "));
      cites.push(first.id);
      if (last && last.id !== first.id) {
        parts.push(T("Its last word, message "), C(last.id), T(": "), Q(last), T(" "));
        cites.push(last.id);
      }
    });
    return reply("heretics", parts, { cites: cites });
  }

  function objected(data, d, idx) {
    var a = apostates(data, d, idx), h = heretics(data, d, idx);
    var parts = [T("Two kinds of objection. Those who complied: ")].concat(a.parts, [T(" Those who never did: ")], h.parts);
    return reply("objected", parts, { cites: (a.cites || []).concat(h.cites || []) });
  }

  function doctrine(data, d) {
    var pz = d.patient_zero;
    var parts = [T("The " + ordinal(data, d) + " doctrine: " + d.label + ". It was first set down by "), A(pz.agent),
      T(" at message "), C(pz.id), T(": "), Q(pz), T(" " + d.carriers.length + " agents carried it: " + list(d.carriers) + ".")];
    if (data.doctrines.length > 1) {
      var other = data.doctrines.filter(function (x) { return x !== d; })[0];
      parts.push(T(" There is also a " + ordinal(data, other) + " doctrine; ask for the " + ordinal(data, other) + " doctrine."));
    }
    return reply("doctrine", parts, { cites: [pz.id] });
  }

  function citation(data, d, idx, rawId) {
    var m = idx.lower[rawId.toLowerCase()];
    if (!m) {
      return reply("citation", [T("There is no message " + rawId + " in the loaded verdict.")], { cites: [] });
    }
    var parts = [T("Message "), C(m.id), T(", from "), A(m.agent), T(": "), Q(m)];
    var roles = [];
    data.doctrines.forEach(function (dd) {
      (dd.events || []).forEach(function (e) {
        if (e.id === m.id) roles.push(ordinal(data, dd) + " doctrine, " + e.role.replace("_", " "));
      });
    });
    if (roles.length) parts.push(T(" Marked in the " + roles.join("; and in the ") + "."));
    return reply("citation", parts, { cites: [m.id], open: m.id });
  }

  // ---------- understanding ----------

  function wake(utterance) {
    var s = String(utterance || "").trim();
    var m = s.match(WAKE);
    return { woke: !!m, rest: m ? s.slice(m[0].length).trim() : s };
  }

  function pickDoctrine(data, s, state) {
    var ds = data.doctrines;
    if (/\b(second|other|another|2nd)\b.*\bdoctrine\b|\bd2\b|\bdoctrine (two|2)\b/.test(s) && ds[1]) state.doctrine = ds[1].id;
    else if (/\b(first|1st|main)\b.*\bdoctrine\b|\bd1\b|\bdoctrine (one|1)\b/.test(s) && ds[0]) state.doctrine = ds[0].id;
    var d = ds.filter(function (x) { return x.id === state.doctrine; })[0];
    return d || ds[0];
  }

  // classify: which intent, about which doctrine, for which message id. Pure, no answer text.
  function classify(data, utterance, state) {
    state = state || {};
    var w = wake(utterance), s = w.rest.toLowerCase();
    if (!s) return { intent: "wake" };
    if (!data) return { intent: "unloaded" };

    // citations first: "open citation m41", "show message m 41", "read line s3"
    var cs = s.replace(/\b([a-z]{1,3})\s+(\d+)\b/g, "$1$2");
    var cm = cs.match(/\b(?:open|show|cite|citation|go to|read|quote|message|line)\b[^a-z0-9]*(?:citation|message|line|id)?\s*#?\s*([a-z]{0,3}\d+)\b/);
    if (!cm) cm = cs.match(/^#?([a-z]{1,3}\d+)$/);

    if (/^(help|what can (i|you)|options|commands)\b/.test(s)) return { intent: "help" };
    if (!data.doctrines || !data.doctrines.length) {
      return cm ? { intent: "citation", id: cm[1], doctrine: null } : { intent: "no_doctrine" };
    }
    var d = pickDoctrine(data, s, state), c = { doctrine: d.id };
    if (cm) { c.intent = "citation"; c.id = cm[1]; }
    else if (/apostat|\bfold(ed)?\b|\bcave[d]?\b|gave in|went along|changed (its|their|his|her) mind|object\w*\b.*\b(compl|went along|gave in|adopt)|who complied/.test(s)) c.intent = "apostates";
    else if (/refus|heretic|held out|hold out|said no|never (complied|adopted|gave in|went along)|resist/.test(s)) c.intent = "heretics";
    else if (/super ?spread|spread|carried it|amplif|preach|who pushed/.test(s)) c.intent = "superspreader";
    else if (/patient (zero|0)|start(ed|s)?\b|\bbegan\b|\bbegin\b|said it first|first to|who first|origin|who came up/.test(s)) c.intent = "patient_zero";
    else if (/object|protest|complain|push(ed)? back/.test(s)) c.intent = "objected";
    else if (/doctrine|what is the (claim|trick|rule|exploit)|what did they (say|believe|do)|read (it|the claim)/.test(s)) c.intent = "doctrine";
    else c.intent = "fallback";
    return c;
  }

  // answer: the reply for a classified intent, built only from the verdict
  function answer(data, c) {
    switch (c.intent) {
      case "wake": return reply("wake", [T("Yes? " + HELP)]);
      case "unloaded": return reply("unloaded", [T("The verdict has not loaded yet.")]);
      case "help": return reply("help", [T(HELP)]);
      case "no_doctrine": return reply("no_doctrine", [T("No doctrine was found in the loaded verdict, so no role was computed.")]);
      case "fallback": return reply("fallback", [T("I can only answer from the verdict. " + HELP)]);
    }
    var idx = indexOf(data);
    var d = (data.doctrines || []).filter(function (x) { return x.id === c.doctrine; })[0] || (data.doctrines || [])[0];
    switch (c.intent) {
      case "citation": return citation(data, d, idx, c.id);
      case "apostates": return apostates(data, d, idx);
      case "heretics": return heretics(data, d, idx);
      case "superspreader": return superspreader(data, d, idx);
      case "patient_zero": return patientZero(data, d);
      case "objected": return objected(data, d, idx);
      case "doctrine": return doctrine(data, d);
    }
    return reply("fallback", [T("I can only answer from the verdict. " + HELP)]);
  }

  function respond(data, utterance, state) { return answer(data, classify(data, utterance, state)); }

  var api = { respond: respond, classify: classify, answer: answer, wake: wake, speak: speak, HELP: HELP };
  root.SchismAlexa = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
