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
