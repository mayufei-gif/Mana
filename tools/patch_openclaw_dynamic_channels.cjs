#!/usr/bin/env node
"use strict";

const fs = require("fs");

const target = process.env.OPENCLAW_SLASH_COMMANDS_FILE || "/root/.openclaw/extensions/openclaw-weixin/dist/src/messaging/slash-commands.js";

function timestamp() {
  return new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
}

function fail(message) {
  throw new Error(`[openclaw dynamic channels patch] ${message}`);
}

if (!fs.existsSync(target)) {
  fail(`target not found: ${target}`);
}

const source = fs.readFileSync(target, "utf8");

if (source.includes("MANA_OPENCLAW_DYNAMIC_CHANNELS_PATCH_V1")) {
  console.log("already patched: MANA_OPENCLAW_DYNAMIC_CHANNELS_PATCH_V1");
  process.exit(0);
}

if (!/function\s+handleCodex|async\s+function\s+handleCodex/.test(source)) {
  fail("handleCodex() was not found; refusing to patch an unexpected file shape");
}

if (!/switch\s*\(\s*command\s*\)/.test(source)) {
  fail("switch(command) was not found; refusing to patch an unexpected file shape");
}

const helper = String.raw`

// MANA_OPENCLAW_DYNAMIC_CHANNELS_PATCH_V1
const MANA_OPENCLAW_CHANNELS_URL = process.env.MANA_OPENCLAW_CHANNELS_URL || process.env.OPENCLAW_CHANNELS_URL || "https://inforadar.mana-mana.top/api/openclaw/channels/public";
let manaOpenClawChannelsCache = { at: 0, rows: [] };

function manaNormalizeOpenClawTarget(value) {
  return String(value || "").trim().replace(/^\/+/, "").toLowerCase();
}

async function manaFetchOpenClawChannels() {
  const now = Date.now();
  if (now - manaOpenClawChannelsCache.at < 15000) return manaOpenClawChannelsCache.rows;
  try {
    const res = await fetch(MANA_OPENCLAW_CHANNELS_URL, { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const rows = Array.isArray(data && data.channels) ? data.channels : [];
    manaOpenClawChannelsCache = { at: now, rows };
    return rows;
  } catch (err) {
    console.error("[mana-openclaw] dynamic channels fetch failed:", err && err.message ? err.message : err);
    return manaOpenClawChannelsCache.rows || [];
  }
}

async function manaHandleDynamicOpenClawCommand(ctx, command, args) {
  const target = manaNormalizeOpenClawTarget(command);
  if (!target) return false;
  const rows = await manaFetchOpenClawChannels();
  const item = rows.find((row) => row && row.enabled !== false && manaNormalizeOpenClawTarget(row.target || row.name) === target);
  if (!item) return false;
  const baseTarget = manaNormalizeOpenClawTarget(item.base_target || item.baseTarget || "codexapp1");
  const threadKey = item.thread_key || item.threadKey || ({ codexapp: "default", codexapp1: "app1", codexapp2: "app2", codexapp3: "app3" }[baseTarget] || "app1");
  const label = target;
  const policy = item.policy || "hold";
  const prefixLines = [];
  if (item.name || item.label) prefixLines.push("快捷指令：" + (item.name || item.label));
  if (item.purpose) prefixLines.push("功能说明：" + item.purpose);
  if (item.prompt) prefixLines.push(String(item.prompt));
  const joinedArgs = Array.isArray(args) ? args.join(" ") : String(args || "");
  const nextText = [policy, ...prefixLines, joinedArgs].filter(Boolean).join("\n");
  const nextArgs = nextText.split(/\s+/).filter(Boolean);
  await handleCodex(ctx, nextArgs, true, threadKey, label);
  return true;
}
`;

let patched = source;
const handleCodexMatch = patched.match(/(\n\s*(?:async\s+)?function\s+handleCodex\b|\n\s*const\s+handleCodex\s*=)/);
if (!handleCodexMatch) {
  fail("could not find a safe helper insertion point before handleCodex");
}
patched = patched.slice(0, handleCodexMatch.index) + helper + patched.slice(handleCodexMatch.index);

const switchMatch = patched.match(/(\n(\s*)switch\s*\(\s*command\s*\)\s*\{\s*)/);
if (!switchMatch) {
  fail("could not find switch(command) insertion point");
}
const indent = switchMatch[2] || "";
const dynamicBranch = `\n${indent}  if (await manaHandleDynamicOpenClawCommand(ctx, command, args)) {\n${indent}    return { handled: true };\n${indent}  }\n`;
patched = patched.replace(switchMatch[1], `${switchMatch[1]}${dynamicBranch}`);

if (!patched.includes("MANA_OPENCLAW_DYNAMIC_CHANNELS_PATCH_V1") || !patched.includes("manaHandleDynamicOpenClawCommand(ctx, command, args)")) {
  fail("internal verification failed after patch");
}

const backup = `${target}.bak-mana-openclaw-dynamic-${timestamp()}`;
fs.copyFileSync(target, backup);
fs.writeFileSync(target, patched, "utf8");

console.log(`patched: ${target}`);
console.log(`backup: ${backup}`);
