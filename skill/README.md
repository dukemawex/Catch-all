# Real Echo skill

Alexa+ preview tools are closed to this hackathon. This is a public Alexa Skills Kit custom skill. A real Echo can open it once the skill is enabled on the same Amazon account.

Endpoint, after Vercel deploys: https://catch-all-public.vercel.app/api/alexa

1. Sign in at https://developer.amazon.com/alexa/console/ask
2. Create Skill. Name SCHISM. Primary locale English (US). Model: Custom. Host: Provision your own.
3. Invocation name: schism
4. Interaction model, JSON editor: paste skill/interaction-model.json. Save and build the model.
5. Endpoint: HTTPS, the URL above. Do not pick AWS Lambda.
6. Test tab, or say on a device signed into this developer account: "Alexa, open schism" then "who started it".

The spoken verdict is the synthetic fixture. Patient zero is 38148c, message m41. It does not call Alexa+.
