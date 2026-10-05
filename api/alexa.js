// Alexa Skills Kit endpoint. Real Echo devices call this. Not Alexa+.
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
      outputSpeech: { type: "PlainText", text },
      card: { type: "Simple", title: "SCHISM", content: text },
      shouldEndSession: end !== false,
      reprompt: { outputSpeech: { type: "PlainText", text: "Ask who started it, who spread it, who folded, or who refused." } }
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

module.exports = function handler(req, res) {
  if (req.method !== "POST") {
    res.status(200).json({ ok: true, skill: "schism", say: "Alexa, open schism" });
    return;
  }
  const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
  const type = body.request && body.request.type;
  if (type === "LaunchRequest") {
    res.status(200).json(speak("Schism is open. This fixture is synthetic. Ask who started it.", false));
    return;
  }
  if (type === "SessionEndedRequest") {
    res.status(200).json(speak(""));
    return;
  }
  const name = body.request && body.request.intent && body.request.intent.name;
  res.status(200).json(answer(name));
};
