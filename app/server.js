// Tiny web server, no dependencies. Run: node app/server.js  then open http://localhost:3000
const http = require("http");
const fs = require("fs");
const path = require("path");


// Load app/.env if present (ANTHROPIC_API_KEY=...)
const envFile = path.join(__dirname, ".env");
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const { runPipeline, liveAvailable } = require("./agents");
const PORT = process.env.PORT || 3000;
const ROOT = path.join(__dirname, "public");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".txt": "text/plain" };

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/api/status") {
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify({ liveAvailable: liveAvailable() }));
    }
    if (req.method === "GET" && req.url === "/sample-bylaws.txt") {
      res.writeHead(200, { "content-type": "text/plain" });
      return res.end(fs.readFileSync(path.join(__dirname, "..", "docs", "sample-bylaws.txt")));
    }
    if (req.method === "POST" && req.url === "/api/run") {
      let body = "";
      for await (const chunk of req) body += chunk;
      const result = await runPipeline(JSON.parse(body));
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify(result));
    }
    const file = path.join(ROOT, req.url === "/" ? "index.html" : req.url.split("?")[0]);
    if (!file.startsWith(ROOT) || !fs.existsSync(file)) {
      res.writeHead(404);
      return res.end("Not found");
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  } catch (e) {
    res.writeHead(500, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: e.message }));
  }
});

server.listen(PORT, () => console.log(`CoopOS running on http://localhost:${PORT}`));
