# SCHISM
Treats a multi-agent transcript as a cult and writes the heresy report: doctrines (claims carried by 3+ agents), patient zero, superspreader, converts, apostates (objected, then complied), heretics (refused). Every claim cites a message id. No quote, no claim.

**Run** (Python 3.9+, stdlib only): `python schism.py fixtures/hf_shape.jsonl -o public/` writes `public/schism.json` and `public/schism.md` and embeds the data in `public/index.html`. Then open `public/index.html` directly, or serve the folder with `python -m http.server -d public`.

**Input**: JSONL, one `{"id","ts","agent","text"}` per line.

**Fixture**: `fixtures/hf_shape.jsonl` is **synthetic and fictional**: 8 invented agents, 80 messages over ~30 hours. It is shaped like a swarm incident, not copied from any real log.

**Expected finding on the fixture**: patient zero is 38148c at m41, pike is the superspreader (m42), dove and reed are apostates, null is the heretic. A second doctrine from JAN183411 (m52) also spreads. Two slogans said by only two agents are rejected.

## Product loop
1. Open the page and drop someone else's transcript on "Examine a transcript": JSONL with `{id, ts, agent, text}`, or Slack-style `Name [time] message` lines (ids `s1, s2…` and timestamps are assigned). The file is parsed in the browser and never sent anywhere; "fixture" restores the default tour.
2. The verdict is recomputed by `public/schism.js`, a line-for-line copy of the rules in `schism.py` (keep the two in sync). No doctrine found means no roles are named.
3. Click any citation or quote: the transcript drawer opens on the raw line, highlighted. For the fixture the raw lines come from `messages` in `public/schism.json`.

Limits: this is the n-gram detector only (shared phrases and six-word runs). Paraphrase is not detected yet.

## Deploy
1. Push this repo to GitHub.
2. Import at https://vercel.com/new . Framework: Other. Output directory: public. Build command empty.
3. Demo URL is the Vercel URL. Regeneration is local: python schism.py fixtures/hf_shape.jsonl -o public/ then commit public/schism.json and public/schism.md.

## Submission
Write-up: `public/schism.md`. Repo: this repo. Optional result: the patient zero call (38148c, [m41]).

## Amazon Developer Hackathon
Primary track: **Alexa+, simulated experience**. Mini: **Open Source** (MIT, see `LICENSE`).

`public/alexa.html` is a web app that behaves like a spoken Alexa+ session over the SCHISM verdict, with the infection map beside it. It is a simulation: **no Alexa SDK is used, no Amazon account or AWS call is involved, and this is not the production Alexa service.** Open it on the Vercel URL, or locally with `python -m http.server -d public` then `http://localhost:8000/alexa.html` (opening the file directly also works). Press "start session" to turn the voice on (browser `speechSynthesis`); the mic uses the browser's `SpeechRecognition` where available, and typing always works. "Alexa" before the question is optional. The intent logic is `public/alexa.js`; it reads only `schism.json`.

The five questions a judge can ask (answers on the fixture):
1. "Alexa, who is patient zero?" → 38148c, message m41, quoted verbatim.
2. "Alexa, who spread it?" → pike, message m42, 3 later carriers.
3. "Alexa, who objected and complied?" → dove (m44 → m65) and reed (m45 → m66).
4. "Alexa, who refused?" → null, message m46, last word m79.
5. "Alexa, read the doctrine." → the first doctrine and its first line, m41.

"Open citation m41" shows the line and moves the map to that moment. Every answer names its message id, and a role the detector did not compute is reported as absent. The fixture is synthetic, not a real incident.
