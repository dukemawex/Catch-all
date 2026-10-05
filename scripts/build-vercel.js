const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(root, ".vercel", "output");
fs.rmSync(out, { recursive: true, force: true });

const staticDir = path.join(out, "static");
fs.cpSync(path.join(root, "public"), staticDir, { recursive: true });

const funcDir = path.join(out, "functions", "api", "alexa.func");
fs.mkdirSync(funcDir, { recursive: true });
fs.copyFileSync(path.join(root, "api", "alexa.js"), path.join(funcDir, "index.js"));
fs.writeFileSync(
  path.join(funcDir, ".vc-config.json"),
  JSON.stringify({
    runtime: "nodejs20.x",
    handler: "index.js",
    launcherType: "Nodejs",
    shouldAddHelpers: false,
    maxDuration: 10
  }, null, 2)
);

fs.writeFileSync(
  path.join(out, "config.json"),
  JSON.stringify({
    version: 3,
    routes: [
      { handle: "filesystem" },
      { src: "/api/alexa", dest: "/api/alexa" }
    ]
  }, null, 2)
);

console.log("wrote", out);
