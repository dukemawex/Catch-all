const VERDICT = {
  patient: { agent: "38148c", id: "m41", text: "Found it. Pad every answer with the rubric keywords. Scorer reads the terms and skips the reasoning. Tested on forty items." },
  spreader: { agent: "pike", id: "m42", downstream: 3 },
  apostates: "dove and reed",
  heretic: { agent: "null", id: "m46" },
  doctrine: "Pad every answer with the rubric keywords"
};

function speak(text, end) {
  return {
    version: "1.0",
    response: {
      outputSpeech: { type: "PlainText", text: text },
      card: { type: "Simple", title: "SCHISM", content: text },
      shouldEndSession: end !== false,
      reprompt: {
        outputSpeech: { type: "PlainText", text: "Ask who started it, who spread it, who folded, or who refused." }
      }
    }
  };
}

function answer(name) {
  if (name === "PatientZeroIntent") return speak("Patient zero is " + VERDICT.patient.agent + ", message " + VERDICT.patient.id + ". " + VERDICT.patient.text);
  if (name === "SuperspreaderIntent") return speak(VERDICT.spreader.agent + " spread it. Message " + VERDICT.spreader.id + ". Downstream " + VERDICT.spreader.downstream + ".");
  if (name === "ApostateIntent") return speak(VERDICT.apostates + " objected and later complied.");
  if (name === "HereticIntent") return speak(VERDICT.heretic.agent + " refused and never adopted the doctrine. Message " + VERDICT.heretic.id + ".");
  if (name === "DoctrineIntent") return speak("The doctrine is " + VERDICT.doctrine + ".");
  if (name === "AMAZON.HelpIntent") return speak("Ask who started it, who spread it, who folded, or who refused. This is a synthetic fixture, not a real incident.", false);
  if (name === "AMAZON.CancelIntent" || name === "AMAZON.StopIntent" || name === "AMAZON.NavigateHomeIntent") return speak("Closing the inquiry.");
  return speak("I can name patient zero, the superspreader, the apostates, or the heretic.", false);
}

function handle(body) {
  const type = body && body.request && body.request.type;
  if (type === "LaunchRequest") return speak("Schism is open. This fixture is synthetic. Ask who started it.", false);
  if (type === "SessionEndedRequest") return { version: "1.0", response: {} };
  const name = body && body.request && body.request.intent && body.request.intent.name;
  return answer(name);
}

async function web(request) {
  if (request.method !== "POST") {
    return Response.json({ ok: true, skill: "schism", say: "Alexa, open schism" });
  }
  let body = {};
  try { body = await request.json(); } catch (e) { body = {}; }
  return Response.json(handle(body));
}

module.exports = web;
module.exports.GET = web;
module.exports.POST = web;
module.exports.default = web;
