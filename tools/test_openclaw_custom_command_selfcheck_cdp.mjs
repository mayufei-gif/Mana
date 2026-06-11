import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";

const edgePath = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const url = process.argv[2] ?? "https://inforadar.mana-mana.top/#openclaw";
const port = Number(process.env.CDP_PORT ?? 9362);
const profileDir = await mkdtemp(join(tmpdir(), "openclaw-selfcheck-edge-"));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const edge = spawn(edgePath, [
  "--headless=new",
  "--disable-gpu",
  "--disable-sync",
  "--disable-features=msEdgeEnableNurturingFramework,msShowSignin",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profileDir}`,
  url
], { stdio: "ignore" });

async function fetchJson(path) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`);
  if (!response.ok) throw new Error(`CDP HTTP ${response.status} for ${path}`);
  return response.json();
}

async function waitForTarget() {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const targets = await fetchJson("/json/list");
      const page = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl);
      if (page) return page;
    } catch {
      // Edge is still starting.
    }
    await sleep(250);
  }
  throw new Error("Timed out waiting for Edge CDP target");
}

const target = await waitForTarget();
const ws = new WebSocket(target.webSocketDebuggerUrl);
let nextId = 1;
const pending = new Map();

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", reject, { once: true });
});

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 920,
    height: 760,
    deviceScaleFactor: 1,
    mobile: false
  });
  await send("Page.navigate", { url });
  await sleep(3000);

  const commandName = `codexapp-selfcheck-${Date.now().toString(36)}`;
  const expression = `(${async function (targetName) {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const waitUntil = async (predicate, timeout = 60000) => {
      const deadline = Date.now() + timeout;
      while (Date.now() < deadline) {
        const value = predicate();
        if (value) return value;
        await sleep(250);
      }
      return null;
    };

    const form = await waitUntil(() => document.querySelector("#openclawCommandForm"));
    if (!form) {
      return {
        ok: false,
        reason: "OpenClaw form not found",
        body: document.body.textContent?.replace(/\\s+/g, " ").trim().slice(0, 500)
      };
    }

    document.querySelector("#openclawCommandName").value = "自检临时指令";
    document.querySelector("#openclawCustomTarget").value = targetName;
    document.querySelector("#openclawPurpose").value = "自动化红绿自检专用通道";
    document.querySelector("#openclawPrompt").value = "只做联通性自检，不投递真实业务任务。";
    document.querySelector("#openclawSession").value = "codex-qa";
    ["openclawCommandName", "openclawCustomTarget", "openclawPurpose", "openclawPrompt", "openclawSession"].forEach((id) => {
      document.querySelector(`#${id}`).dispatchEvent(new Event("input", { bubbles: true }));
      document.querySelector(`#${id}`).dispatchEvent(new Event("change", { bubbles: true }));
    });

    document.querySelector("#openclawSelfCheckBtn").click();
    const log = await waitUntil(() => {
      const text = document.querySelector("#openclawSelfCheckLog")?.textContent || "";
      return text.includes("[RESULT]") ? text : null;
    }, 90000);
    const options = [...document.querySelectorAll("#openclawTarget option")].map((item) => item.value);
    return {
      ok: Boolean(log?.includes("[RESULT] PASS") && options.includes(targetName)),
      targetName,
      options,
      log
    };
  }})(${JSON.stringify(commandName)})`;

  const result = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true
  });
  const value = result.result.value;
  console.log(JSON.stringify(value, null, 2));
  if (!value?.ok) process.exitCode = 1;
} finally {
  ws.close();
  edge.kill();
  await sleep(1000);
  await rm(profileDir, { recursive: true, force: true }).catch(() => {});
}
