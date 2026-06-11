const CODEX_SESSION_NAME_KEY = "inforadar_codex_session_names_v1";
const CODEX_SESSION_DEFAULT_NAMES = {
  codex: "主 Codex 会话",
  "codex-research": "研究/资料会话",
  "codex-build": "构建/部署会话",
  "codex-qa": "日志/测试会话",
};
const CODEX_TERMINAL_FOLLOW_INTERVAL_MS = 100;
const CODEX_TERMINAL_FOLLOW_TIMEOUT_MS = 10 * 60 * 1000;
const CODEX_TERMINAL_IDLE_STABLE_TICKS = 8;
const OPENCLAW_COMMANDS_KEY = "mana_openclaw_quick_commands_v1";
const OPENCLAW_TARGETS_KEY = "mana_openclaw_custom_targets_v1";
const OPENCLAW_SELF_CHECK_LOG_KEY = "mana_openclaw_selfcheck_log_v1";
const OPENCLAW_BASE_TARGETS = ["codexapp", "codexapp1", "codexapp2", "codexapp3"];
const WEB_TAB_NONCE_KEY = "inforadar_web_tab_nonce_v1";
const LEGACY_WEB_TOKEN_KEY = "inforadar_web_token";
const FOLO_SOURCE_TIMELINE_KEY = "folo_hive_source_timeline_v1";
const FOLO_MANUAL_ENTRIES_KEY = "folo_hive_manual_entries_v1";
const FOLO_RESOURCE_POOL_KEY = "folo_hive_resource_pool_v1";
const FOLO_INSPECTION_INTERVAL_KEY = "folo_hive_inspection_interval_v1";
const OPENCLAW_COMMAND_PRESETS = [
  {
    name: "主管待定",
    target: "codexapp1",
    policy: "hold",
    session: "codex",
    prompt: "登记这个任务，等我确认后再决定是否排队执行：",
  },
  {
    name: "排队执行",
    target: "codexapp3",
    policy: "queue",
    session: "codex-build",
    prompt: "排队处理这个任务，完成后给出结果、文件路径和验证方式：",
  },
  {
    name: "立即测试",
    target: "codexapp3",
    policy: "now",
    session: "codex-qa",
    prompt: "立即做一次最小验证，只返回结论和证据：",
  },
  {
    name: "项目落盘",
    target: "codexapp1",
    policy: "queue",
    session: "codex-build",
    prompt: "在当前授权项目目录内完成这个任务，并把结果写入项目报告：",
  },
];

function defaultOpenClawCommands() {
  return OPENCLAW_COMMAND_PRESETS.map((item, index) => ({ ...item, id: `preset-${index + 1}` }));
}

function loadOpenClawCommands() {
  try {
    const rows = JSON.parse(localStorage.getItem(OPENCLAW_COMMANDS_KEY) || "[]");
    return Array.isArray(rows) && rows.length ? rows : defaultOpenClawCommands();
  } catch {
    return defaultOpenClawCommands();
  }
}

function saveOpenClawCommands(rows) {
  localStorage.setItem(OPENCLAW_COMMANDS_KEY, JSON.stringify(rows || []));
}

function loadOpenClawTargets() {
  try {
    const rows = JSON.parse(localStorage.getItem(OPENCLAW_TARGETS_KEY) || "[]");
    return Array.isArray(rows) ? rows.filter((item) => item && typeof item === "object") : [];
  } catch {
    return [];
  }
}

function saveOpenClawTargets(rows) {
  localStorage.setItem(OPENCLAW_TARGETS_KEY, JSON.stringify(rows || []));
}

function loadOpenClawSelfCheckLogs() {
  try {
    const rows = JSON.parse(localStorage.getItem(OPENCLAW_SELF_CHECK_LOG_KEY) || "[]");
    return Array.isArray(rows) ? rows.slice(-20) : [];
  } catch {
    return [];
  }
}

function saveOpenClawSelfCheckLogs(rows) {
  localStorage.setItem(OPENCLAW_SELF_CHECK_LOG_KEY, JSON.stringify((rows || []).slice(-20)));
}

function loadCodexSessionNames() {
  try {
    return JSON.parse(localStorage.getItem(CODEX_SESSION_NAME_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function saveCodexSessionNames(names) {
  localStorage.setItem(CODEX_SESSION_NAME_KEY, JSON.stringify(names || {}));
}

function loadLocalJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function saveLocalJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

const state = {
  authenticated: false,
  latest: null,
  latestHealth: null,
  itemStats: null,
  radarSearch: { query: "", scope: "all", offset: 0, limit: 30, total: 0 },
  protected: true,
  totpRequired: true,
  tabBound: true,
  agenthub: null,
  selectedAgentId: "",
  agentRefreshTimer: null,
  headerCollapseTimer: null,
  lastHeaderScrollY: 0,
  headerScrollPinnedUntil: 0,
  codexTerminalTimer: null,
  codexSession: "codex",
  codexSessionNames: loadCodexSessionNames(),
  codexTerminalLoading: false,
  codexTerminalSending: false,
  codexTerminalFollowActive: false,
  codexTerminalFollowToken: "",
  codexTerminalFollowSignature: "",
  codexTerminalFollowStableTicks: 0,
  codexTerminalFollowDeadline: 0,
  locatorItems: {},
  currentApiHiveItems: [],
  currentHiveItems: [],
  currentHiveMetrics: null,
  foloSourceTimeline: loadLocalJson(FOLO_SOURCE_TIMELINE_KEY, []),
  manualHiveEntries: loadLocalJson(FOLO_MANUAL_ENTRIES_KEY, []),
  manualHiveStats: null,
  manualHiveWechatResults: null,
  manualHiveWechatLoading: false,
  manualFeedProbe: null,
  collectorAdapterStats: null,
  collectorAdapterEntries: [],
  resourcePoolEntries: loadLocalJson(FOLO_RESOURCE_POOL_KEY, []),
  resourceHiveStats: null,
  resourceHiveCandidates: [],
  resourceArchivePlan: null,
  openclawCommands: loadOpenClawCommands(),
  openclawTargets: loadOpenClawTargets(),
  openclawSelfCheckLogs: loadOpenClawSelfCheckLogs(),
  codex: null,
  codexLogs: [],
  projects: [
    {
      id: "inforadar",
      name: "Folo 信息蜂巢",
      status: "在线",
      description: "通过 Folo 让所有优质订阅信息自己找上你",
      accent: "green",
      active: true,
    },
    {
      id: "CourseMindNAS",
      name: "NAS 视频字幕学习库",
      status: "MVP",
      description: "CourseMind NAS 视频字幕与学习播放器：课程视频、字幕、章节、重点和笔记入口。",
      accent: "blue",
      active: true,
      publicHostname: "/coursemind/",
      actionText: "进入学习库",
    },
    {
      id: "nas-pipeline",
      name: "NAS Pipeline",
      status: "规划中",
      description: "NAS 存储、同步、归档和附件回传位。",
      accent: "amber",
    },
    {
      id: "personal-site",
      name: "个人官网",
      status: "预留",
      description: "后续可放个人介绍、项目导航、链接集合与公开页。",
      accent: "slate",
    },
    {
      id: "NextProjectSlot",
      name: "下一个项目工位",
      status: "规划中",
      description: "预留给后续新项目，可继续接入自然语言任务入口、安全执行队列和网页入口。",
      accent: "slate",
    },
  ],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function currentTabNonce() {
  try {
    return sessionStorage.getItem(WEB_TAB_NONCE_KEY) || "";
  } catch {
    return "";
  }
}

function setTabNonce(value = "") {
  try {
    if (value) {
      sessionStorage.setItem(WEB_TAB_NONCE_KEY, value);
    } else {
      sessionStorage.removeItem(WEB_TAB_NONCE_KEY);
    }
  } catch {
    // sessionStorage may be blocked in hardened browser modes; in that case the tab must re-authenticate.
  }
}

function clearLegacyAuthState() {
  try {
    localStorage.removeItem(LEGACY_WEB_TOKEN_KEY);
  } catch {
    // Ignore storage errors; the backend no longer accepts legacy frontend tokens.
  }
}

function headers(extra = {}) {
  const next = { "Content-Type": "application/json", ...extra };
  const tabNonce = currentTabNonce();
  if (tabNonce) next["X-InfoRadar-Tab-Nonce"] = tabNonce;
  return next;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2200);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function codexSessionDisplayName(id, fallback = "") {
  return state.codexSessionNames[id] || CODEX_SESSION_DEFAULT_NAMES[id] || fallback || id;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { ...headers(options.headers || {}), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    const message = text || `HTTP ${res.status}`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

function fileUrl(path, download = false) {
  const params = new URLSearchParams({ path });
  if (download) params.set("download", "true");
  return `/api/file?${params.toString()}`;
}

function foloSearchUrl(parts, meta = {}) {
  const query = (parts || []).filter(Boolean).join(" ").trim();
  const params = new URLSearchParams();
  const title = meta.title || meta["标题"] || parts?.[0] || "";
  const source = meta.source || meta["来源名称"] || meta["Folo订阅源名称"] || parts?.[1] || "";
  const folder = meta.folo_folder || meta["Folo文件夹路径"] || "";
  const searchText = title || query;
  if (searchText) params.set("q", searchText);
  if (title) params.set("ir_title", title);
  if (source) params.set("ir_source", source);
  if (folder) params.set("ir_folder", folder);
  params.set("ir_autolocate", "1");
  return `https://app.folo.is/${params.toString() ? `?${params.toString()}` : ""}`;
}

function foloLocatorUrl(url, meta = {}, target = "article") {
  if (!url) return "";
  if (target === "source" && !meta.folo_matched && !meta["folo_matched"]) return "";
  const title = meta.title || meta["标题"] || "";
  const source = meta.source || meta["来源名称"] || meta["Folo订阅源名称"] || "";
  const folder = meta.folo_folder || meta["Folo文件夹路径"] || "";
  try {
    const nextUrl = new URL(url);
    return nextUrl.toString();
  } catch (_) {
    return url;
  }
}

function locatorId(prefix, idx) {
  return `${prefix}-${idx}-${Date.now().toString(36)}`;
}

function storeLocatorItem(id, item) {
  if (!id) return;
  state.locatorItems[id] = item || {};
}

function linkButton(url, label, extraClass = "secondary") {
  const href = String(url || "").trim();
  const cls = href ? extraClass : "disabled";
  return `<a class="${escapeHtml(cls)}" href="${escapeHtml(href || "#")}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function locatorField(label, value) {
  return `
    <div class="locator-field">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "待补充")}</strong>
    </div>
  `;
}

function looksLikeFilePath(value) {
  const text = String(value || "").trim();
  return Boolean(text && (/^(\/|[A-Za-z]:[\\/])/.test(text) || text.includes("inforadar-return") || text.includes("NAS回传")));
}

function openLocator(id) {
  const item = state.locatorItems[id];
  const panel = $("#locatorPanel");
  const box = $("#locatorDetail");
  if (!item || !panel || !box) return;
  const payload = item.payload || item;
  const title = item.title || payload.title || payload["标题"] || payload.name || payload["name"] || "未命名";
  const source = payload.source || payload["来源名称"] || payload["Folo订阅源名称"] || item.source || "";
  const folder = payload.folo_folder || payload["Folo文件夹路径"] || "";
  const articleUrl = payload.official_url || payload.article_url || payload["官方原文链接"] || payload["原文URL"] || item.url || "";
  const foloSearch = payload.folo_article_url || "";
  const foloSourceBase = payload.folo_source_url || (item.folo_matched ? item.folo_url : "") || "";
  const foloSource = foloLocatorUrl(foloSourceBase, { title, source, folo_folder: folder, folo_matched: payload.folo_matched || item.folo_matched }, "source");
  const filePath = payload.source_file || payload.path || payload["path"] || item.body || "";
  const readableFilePath = looksLikeFilePath(filePath) ? filePath : "";
  const row = payload.source_row || payload.index || payload["序号"] || "";
  const publishedAt = formatBeijingDateTimeLoose(payload.published_at || payload["发布时间"] || payload.modified_at || "", true);
  box.innerHTML = `
    <div class="locator-title">${escapeHtml(title)}</div>
    <div class="locator-grid">
      ${locatorField("来源", source)}
      ${locatorField("发布时间", publishedAt)}
      ${locatorField("Folo 文件夹", folder)}
      ${locatorField("来源行", row)}
      ${locatorField("来源文件", filePath)}
    </div>
    <div class="locator-actions">
      ${linkButton(articleUrl, "原文核验", "")}
      ${linkButton(foloSearch, payload.folo_article_url ? "Folo 原条" : "Folo 原条待补")}
      ${linkButton(foloSource, "Folo 源列表")}
      ${readableFilePath ? linkButton(fileUrl(readableFilePath), "查看来源文件") : ""}
    </div>
  `;
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setAppVisible(visible) {
  $("#lockScreen").classList.toggle("hidden", visible);
  $("#appShell").classList.toggle("hidden", !visible);
  if (visible) {
    showAppHeader();
    scheduleAppHeaderCollapse(1800);
  } else if (state.headerCollapseTimer) {
    window.clearTimeout(state.headerCollapseTimer);
    state.headerCollapseTimer = null;
  }
}

function showAppHeader() {
  const shell = $("#appShell");
  if (!shell) return;
  shell.classList.remove("header-collapsed");
  if (state.headerCollapseTimer) {
    window.clearTimeout(state.headerCollapseTimer);
    state.headerCollapseTimer = null;
  }
}

function pinAppHeader(ms = 900) {
  state.headerScrollPinnedUntil = Date.now() + ms;
}

function scheduleAppHeaderCollapse(delay = 700) {
  const shell = $("#appShell");
  if (!shell || shell.classList.contains("hidden")) return;
  if (state.headerCollapseTimer) window.clearTimeout(state.headerCollapseTimer);
  state.headerCollapseTimer = window.setTimeout(() => {
    shell.classList.add("header-collapsed");
    state.headerCollapseTimer = null;
  }, delay);
}

function headerVisibilityForScroll(previousY, currentY, options = {}) {
  const threshold = Number(options.threshold ?? 10);
  const topReveal = Number(options.topReveal ?? 24);
  const prev = Math.max(0, Number(previousY) || 0);
  const current = Math.max(0, Number(currentY) || 0);
  if (current <= topReveal) return "show";
  const delta = current - prev;
  if (Math.abs(delta) < threshold) return "keep";
  return delta > 0 ? "hide" : "show";
}

function bindHeaderDrawer() {
  const header = $(".site-header");
  const zone = $("#headerHoverZone");
  if (!header || !zone) return;

  const open = () => {
    pinAppHeader();
    showAppHeader();
  };
  const closeLater = () => scheduleAppHeaderCollapse(650);
  header.addEventListener("mouseenter", open);
  header.addEventListener("mouseleave", closeLater);
  zone.addEventListener("mouseenter", open);
  zone.addEventListener("mouseleave", closeLater);
  header.addEventListener("focusin", open);
  header.addEventListener("focusout", closeLater);
  document.addEventListener("mousemove", (event) => {
    if (event.clientY <= 30 && !$("#appShell")?.classList.contains("hidden")) {
      open();
    }
  });
  state.lastHeaderScrollY = window.scrollY || 0;
  document.addEventListener("scroll", () => {
      const shell = $("#appShell");
      if (!shell || shell.classList.contains("hidden")) return;
      const currentY = window.scrollY || document.documentElement.scrollTop || 0;
      const action = headerVisibilityForScroll(state.lastHeaderScrollY, currentY);
      state.lastHeaderScrollY = Math.max(0, currentY);
      if (Date.now() < state.headerScrollPinnedUntil && action !== "hide") return;
      if (action === "show") {
        showAppHeader();
      } else if (action === "hide") {
        scheduleAppHeaderCollapse(0);
      }
    },
    { passive: true }
  );
}

function setRoute(route, updateHash = true) {
  const normalized = ["agenthub", "inforadar", "codex", "openclaw"].includes(route) ? route : "hub";
  const isHub = normalized === "hub";
  const isAgentHub = normalized === "agenthub";
  const isInfoRadar = normalized === "inforadar";
  const isCodex = normalized === "codex";
  const isOpenClaw = normalized === "openclaw";
  $("#hubView")?.classList.toggle("hidden", !isHub);
  $("#project-agenthub")?.classList.toggle("hidden", !isAgentHub);
  $("#project-inforadar")?.classList.toggle("hidden", !isInfoRadar);
  $("#project-codex")?.classList.toggle("hidden", !isCodex);
  $("#project-openclaw")?.classList.toggle("hidden", !isOpenClaw);
  $(".tabs")?.classList.toggle("hidden", !isInfoRadar);
  $("#backHubBtn")?.classList.toggle("hidden", isHub);
  $("#headerEyebrow").textContent = isAgentHub
    ? "Agent Company"
    : isInfoRadar
      ? "Active Project"
      : isCodex
        ? "Ubuntu Workstation"
        : isOpenClaw
          ? "WeChat Command Bridge"
          : "Personal Project Hub";
  $("#headerTitle").textContent = isAgentHub
    ? "AgentHub"
    : isInfoRadar
      ? "Folo 信息蜂巢"
      : isCodex
        ? "Codex 工作站"
        : isOpenClaw
          ? "微信命令中心"
          : "Mana Hub";
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (isCodex && state.authenticated) {
    loadCodexWorkspace().catch((err) => showToast(err.message));
  }
  if (isOpenClaw) {
    renderOpenClawCommandCenter();
  }
  if (updateHash) {
    history.replaceState(null, "", `#${normalized}`);
  }
}

function renderProjects() {
  const box = $("#projectGrid");
  const rows = state.agenthub?.projects?.length
    ? state.agenthub.projects.map((project) => ({
        id: project.project_id,
        name:
          project.project_id === "AgentHub"
            ? "Codex Agent总控"
            : project.project_id === "InfoRadar"
              ? "Folo 信息蜂巢"
              : project.name || project.project_id,
        status: project.status || "unknown",
        description:
          project.project_id === "AgentHub"
            ? "Mana AI 公司总控：Api Codex和Gpt Codex共享实时聊天直播。"
            : project.project_id === "InfoRadar"
              ? "通过 Folo 让所有优质订阅信息自己找上你"
            : project.notes || project.public_hostname || project.project_type || "",
        publicHostname: project.project_id === "CourseMindNAS" ? "/coursemind/" : project.public_hostname || "",
        accent:
          project.project_id === "AgentHub"
            ? "green"
            : project.project_id === "OpenClawBridge"
              ? "amber"
              : project.status === "online" || project.status === "active"
                ? "green"
                : project.status === "planned"
                  ? "slate"
                  : "blue",
        active: ["AgentHub", "InfoRadar", "ManaHubWeb", "CourseMindNAS", "OpenClawBridge"].includes(project.project_id) || ["online", "active", "mvp"].includes(project.status),
        actionText:
          project.project_id === "AgentHub"
            ? "进入总控"
            : project.project_id === "InfoRadar"
              ? "进入蜂巢"
              : project.project_id === "ManaHubWeb"
                ? "进入 Codex"
                : project.project_id === "OpenClawBridge"
                  ? "进入命令中心"
                  : project.project_id === "CourseMindNAS"
                    ? "进入学习库"
                    : project.status === "mvp"
                      ? "查看项目"
                      : "预留位",
      }))
    : state.projects;
  $("#projectCount").textContent = String(rows.length);
  $("#onlineCount").textContent = String(rows.filter((item) => item.active).length);
  box.innerHTML = rows
    .map(
      (project) => `
        <article class="project-card ${project.accent || "green"} ${project.active ? "active" : ""}">
          <div class="project-top">
            <div>
              <p class="eyebrow">${escapeHtml(project.id === "AgentHub" ? "AgentHub" : project.active ? "Current" : "Reserved")}</p>
              <h3>${escapeHtml(project.name)}</h3>
            </div>
            <span class="status-chip">${escapeHtml(project.status)}</span>
          </div>
          <p class="project-desc">${escapeHtml(project.description)}</p>
          <div class="project-actions">
            <button type="button" data-project="${escapeHtml(project.id)}" data-url="${escapeHtml(project.publicHostname || "")}" ${project.active ? "" : "disabled"}>
              ${escapeHtml(project.actionText || (project.active ? "进入项目" : "预留位"))}
            </button>
          </div>
        </article>
      `
    )
    .join("");

  box.querySelectorAll("button[data-project]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.project;
      if (target === "AgentHub") {
        setRoute("agenthub");
        showToast("已进入 AgentHub 总控");
      } else if (target === "InfoRadar" || target === "inforadar") {
        setRoute("inforadar");
        showToast("已进入 Folo 信息蜂巢");
      } else if (target === "ManaHubWeb") {
        setRoute("codex");
        showToast("已进入 Ubuntu Codex 工作站");
      } else if (target === "OpenClawBridge") {
        setRoute("openclaw");
        showToast("已进入微信命令中心");
      } else if (target === "CourseMindNAS") {
        const url = button.dataset.url || "/coursemind/";
        window.location.assign(url);
        showToast("正在打开 CourseMind 学习库");
      } else {
        showToast("这个项目位已经预留，后续可以接入");
      }
    });
  });
}

function statusText(value) {
  const map = {
    queued: "待领取",
    claimed: "已领取",
    in_progress: "进行中",
    blocked: "阻塞",
    needs_review: "待验收",
    approved: "已通过",
    merged: "已合并",
    done: "完成",
    failed: "失败",
    active: "活跃",
    idle: "空闲",
    planned: "规划",
    online: "在线",
    mvp: "MVP",
  };
  return map[value] || value || "未知";
}

function realtimeText(agent) {
  const state = agent.realtime_state || "unverified";
  const label = agent.realtime_label || "未接入实时检查";
  const age = Number(agent.heartbeat_age_seconds);
  if (state === "online" && Number.isFinite(age)) {
    return `${label} · ${Math.max(0, Math.round(age))} 秒前`;
  }
  if (state === "stale" && Number.isFinite(age)) {
    return `${label} · ${Math.round(age / 60)} 分钟前`;
  }
  return label;
}

function realtimeClass(agent) {
  const state = agent.realtime_state || "unverified";
  if (state === "online") return "online";
  if (state === "stale") return "stale";
  return "unverified";
}

function codexThreadClass(thread) {
  const status = thread?.status || "not_connected";
  if (status === "active") return "online";
  if (["stale", "archived"].includes(status)) return "stale";
  return "unverified";
}

function codexThreadText(thread) {
  if (!thread || !thread.thread_id) return "未接入本机 Codex 会话";
  const age = Number(thread.updated_age_seconds);
  if (thread.status === "active" && Number.isFinite(age)) return `Codex 会话活跃 · ${Math.max(0, Math.round(age))} 秒前`;
  if (thread.status === "stale" && Number.isFinite(age)) return `Codex 会话过期 · ${Math.round(age / 60)} 分钟前`;
  if (thread.status === "archived") return "Codex 会话已归档";
  return `Codex 会话：${thread.status || "未知"}`;
}

function renderAgentDetail(agent) {
  const panel = $("#agentDetailPanel");
  const box = $("#agentDetail");
  if (!panel || !box) return;
  if (!agent) {
    panel.classList.add("hidden");
    box.innerHTML = "";
    return;
  }

  const tasks = agent.tasks || [];
  const events = (agent.events || []).slice(-8).reverse();
  const outputs = agent.outputs || [];
  const codexThread = agent.codex_thread || {};
  const codexMessages = (codexThread.recent_messages || []).slice(-8).reverse();
  const codexMessageRows = codexMessages.length
    ? codexMessages
        .map(
          (message) => `
            <div class="codex-message ${escapeHtml(message.kind || "event")}">
              <div class="codex-message-top">
                <span>${escapeHtml(message.kind || "event")}</span>
                <time>${escapeHtml(message.at || "")}</time>
              </div>
              <div class="codex-message-text">${escapeHtml(message.text || "")}</div>
            </div>
          `
        )
        .join("")
    : `<div class="detail-row"><div class="item-meta">暂无可展示的最近消息摘要；monitor 默认不公开完整对话正文。</div></div>`;
  const codexThreadRows = codexThread.thread_id
    ? `
      <section class="codex-thread-card ${escapeHtml(codexThreadClass(codexThread))}">
        <div class="codex-thread-head">
          <div>
            <p class="eyebrow">Codex App Local Thread</p>
            <h4>${escapeHtml(codexThread.session_thread_name || codexThread.title || "未命名会话")}</h4>
          </div>
          <span class="realtime-pill ${escapeHtml(codexThreadClass(codexThread))}">${escapeHtml(codexThreadText(codexThread))}</span>
        </div>
        <div class="agent-detail-grid">
          <div class="detail-row">
            <div class="item-title">真实会话</div>
            <div class="item-meta">thread_id：${escapeHtml(codexThread.thread_id || "无")}</div>
            <div class="item-meta">标题：${escapeHtml(codexThread.title || "无")}</div>
            <div class="item-meta">更新时间：${escapeHtml(codexThread.updated_at || "无")}</div>
          </div>
          <div class="detail-row">
            <div class="item-title">本机上下文</div>
            <div class="item-meta">工作区：${escapeHtml(codexThread.cwd || "无")}</div>
            <div class="item-meta">tokens：${escapeHtml(codexThread.tokens_used || 0)} · 隐私模式：${escapeHtml(codexThread.privacy_mode || "summary_only")}</div>
            <div class="item-meta">monitor：${escapeHtml(codexThread.monitor_checked_at || "未同步")}</div>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">最近消息摘要</div>
          <div class="codex-message-list">${codexMessageRows}</div>
        </div>
      </section>
    `
    : `
      <section class="codex-thread-card unverified">
        <div class="codex-thread-head">
          <div>
            <p class="eyebrow">Codex App Local Thread</p>
            <h4>未找到匹配的本机会话</h4>
          </div>
          <span class="realtime-pill unverified">未接入</span>
        </div>
        <div class="item-meta">${escapeHtml(codexThread.message || "请先在 Win11 本机运行 codex_app_monitor.py 同步会话摘要。")}</div>
      </section>
    `;
  const taskRows = tasks.length
    ? tasks
        .map(
          (task) => `
            <div class="detail-row">
              <div class="item-title">${escapeHtml(task.task_id)} · ${escapeHtml(task.title || "未命名任务")}</div>
              <div class="item-meta">
                项目：${escapeHtml(task.project_id || "未知")} · 状态：${escapeHtml(statusText(task.status))} · 优先级：${escapeHtml(task.priority || "-")}
              </div>
              <div class="item-meta">工作区：${escapeHtml(task.workspace || "未登记")}</div>
            </div>
          `
        )
        .join("")
    : `<div class="detail-row"><div class="item-meta">暂无分配给该角色的任务</div></div>`;
  const eventRows = events.length
    ? events
        .map(
          (event) => `
            <div class="detail-row">
              <div class="item-title">${escapeHtml(event.event || "event")} · ${escapeHtml(event.task_id || "无任务")}</div>
              <div class="item-meta">${escapeHtml(event.ts || "")} · ${escapeHtml(event.message || "")}</div>
            </div>
          `
        )
        .join("")
    : `<div class="detail-row"><div class="item-meta">暂无该角色事件日志</div></div>`;
  const outputRows = outputs.length
    ? outputs
        .map(
          (output) => `
            <div class="detail-row">
              <div class="item-title">${escapeHtml(output.name)}</div>
              <div class="item-meta">${escapeHtml(output.modified_at || "")} · ${escapeHtml(output.relative_path || "")}</div>
            </div>
          `
        )
        .join("")
    : `<div class="detail-row"><div class="item-meta">暂无输出文件</div></div>`;

  panel.classList.remove("hidden");
  box.innerHTML = `
    <section class="agent-detail-head ${escapeHtml(realtimeClass(agent))}">
      <div>
        <p class="eyebrow">Selected Agent</p>
        <h3>${escapeHtml(agent.agent_id)}</h3>
      </div>
      <span class="realtime-pill ${escapeHtml(realtimeClass(agent))}">${escapeHtml(realtimeText(agent))}</span>
    </section>
    <div class="agent-detail-grid">
      <div class="detail-row">
        <div class="item-title">实时心跳</div>
        <div class="item-meta">最后心跳：${escapeHtml(agent.heartbeat_at || "无")}</div>
        <div class="item-meta">来源：${escapeHtml(agent.heartbeat_source || "未登记")} · 备注：${escapeHtml(agent.realtime_note || "无")}</div>
      </div>
      <div class="detail-row">
        <div class="item-title">登记任务</div>
        <div class="item-meta">登记状态：${escapeHtml(statusText(agent.declared_status || agent.status))}</div>
        <div class="item-meta">当前任务：${escapeHtml(agent.current_task_id || "无")} · 当前项目：${escapeHtml(agent.current_project_id || "无")}</div>
      </div>
    </div>
    ${codexThreadRows}
    <section class="detail-section">
      <div class="detail-section-title">负责任务</div>
      <div class="detail-list">${taskRows}</div>
    </section>
    <section class="detail-section">
      <div class="detail-section-title">最近事件</div>
      <div class="detail-list">${eventRows}</div>
    </section>
    <section class="detail-section">
      <div class="detail-section-title">输出文件</div>
      <div class="detail-list">${outputRows}</div>
    </section>
  `;
}

function selectAgent(agentId, scroll = true) {
  state.selectedAgentId = agentId || "";
  const agent = (state.agenthub?.agents || []).find((item) => item.agent_id === state.selectedAgentId);
  renderAgentHub(state.agenthub || { projects: [], tasks: [], agents: [] });
  if (scroll && agent) {
    $("#agentDetailPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderAgentHub(data) {
  state.agenthub = data;
  $("#agentHubRoot").textContent = data.root || "AgentHub";
  renderProjects();

  const projects = data.projects || [];
  const tasks = (data.tasks || []).slice(0, 10);
  const agents = data.agents || [];
  if (state.selectedAgentId && !agents.some((agent) => agent.agent_id === state.selectedAgentId)) {
    state.selectedAgentId = "";
  }
  $("#agentProjectCount").textContent = String(projects.length);
  $("#agentTaskCount").textContent = String(data.tasks?.length || 0);
  $("#agentRoleCount").textContent = String(agents.length);
  $("#agentHubProjectList").innerHTML = projects.length
    ? projects
        .map(
          (project) => `
            <div class="item">
              <div class="item-title">${escapeHtml(project.project_id)} · ${escapeHtml(project.name || project.project_id)}</div>
              <div class="item-meta">
                状态：${escapeHtml(statusText(project.status))} · 负责人：${escapeHtml(project.owner_agent || "未分配")} · 类型：${escapeHtml(project.project_type || "未知")}
              </div>
              <div class="item-meta">${escapeHtml(project.notes || "")}</div>
            </div>
          `
        )
        .join("")
    : `<div class="item"><div class="item-meta">暂无项目注册记录</div></div>`;

  $("#taskBoard").innerHTML = tasks.length
    ? tasks
        .map(
          (task) => `
            <div class="item">
              <div class="item-title">${escapeHtml(task.task_id)} · ${escapeHtml(task.title)}</div>
              <div class="item-meta">
                项目：${escapeHtml(task.project_id)} · 负责人：${escapeHtml(task.owner_agent)} · 状态：${escapeHtml(statusText(task.status))} · 优先级：${escapeHtml(task.priority)}
              </div>
            </div>
          `
        )
        .join("")
    : `<div class="item"><div class="item-meta">暂无任务</div></div>`;

  $("#agentStatus").innerHTML = agents.length
    ? agents
        .map(
          (agent) => `
            <div class="item agent-status-card ${escapeHtml(realtimeClass(agent))} ${agent.agent_id === state.selectedAgentId ? "selected" : ""}" data-agent-id="${escapeHtml(agent.agent_id)}" role="button" tabindex="0">
              <div class="item-title">
                ${escapeHtml(agent.agent_id)}
                <span class="realtime-pill ${escapeHtml(realtimeClass(agent))}">${escapeHtml(realtimeText(agent))}</span>
              </div>
              <div class="item-meta">
                登记状态：${escapeHtml(statusText(agent.declared_status || agent.status))} · 角色：${escapeHtml(agent.role)}
              </div>
              <div class="item-meta">
                当前任务：${escapeHtml(agent.current_task_id || "无")} · 下一步：${escapeHtml(agent.next_action || "等待")}
              </div>
              <div class="item-meta">
                Codex会话：${escapeHtml(agent.codex_thread_title || "未同步")} · ${escapeHtml(codexThreadText(agent.codex_thread || {}))}
              </div>
              <div class="item-meta">
                最后心跳：${escapeHtml(agent.heartbeat_at || "无")} · 来源：${escapeHtml(agent.heartbeat_source || "未登记")}
              </div>
              <div class="agent-card-action">点开查看 Codex App 真实会话摘要</div>
            </div>
          `
        )
        .join("")
    : `<div class="item"><div class="item-meta">暂无角色状态</div></div>`;
  renderAgentDetail(agents.find((agent) => agent.agent_id === state.selectedAgentId));
}

function renderFiles(target, files, limit = 20) {
  const box = $(target);
  const rows = (files || []).slice(0, limit);
  if (!rows.length) {
    box.innerHTML = `<div class="item"><div class="item-meta">暂无文件</div></div>`;
    return;
  }
  box.innerHTML = rows
    .map(
      (file) => `
        <div class="item">
          <div class="item-title">${escapeHtml(file.name)}</div>
          <div class="item-meta">${escapeHtml(file.category)} · ${escapeHtml(file.size_text)} · ${escapeHtml(file.modified_at)}</div>
          <div class="item-actions">
            <a href="${fileUrl(file.path)}" target="_blank" rel="noreferrer">打开</a>
            <a href="${fileUrl(file.path, true)}" target="_blank" rel="noreferrer">下载</a>
          </div>
        </div>
      `
    )
    .join("");
}

function renderRows(target, rows, titleKeys, metaKeys) {
  const box = $(target);
  if (!rows || !rows.length) {
    box.innerHTML = `<div class="item"><div class="item-meta">暂无记录</div></div>`;
    return;
  }
  box.innerHTML = rows
    .map((row) => {
      const title = titleKeys.map((key) => row[key]).find(Boolean) || "未命名";
      const meta = metaKeys
        .map((key) => (row[key] ? `${key}：${row[key]}` : ""))
        .filter(Boolean)
        .join(" · ");
      return `
        <div class="item">
          <div class="item-title">${escapeHtml(title)}</div>
          <div class="item-meta">${escapeHtml(meta)}</div>
        </div>
      `;
    })
    .join("");
}

function manualEntryToIntelItem(entry) {
  return {
    title: entry.name || entry.url || "手动信息源",
    source: entry.platform || "手动信息获取站",
    section: "手动加入",
    category: "手动信息",
    collection_type: "手动收集",
    article_url: entry.url || "",
    official_url: entry.url || "",
    published_at: entry.created_at || "",
    why: "由手动信息获取站加入本次信息寻缘。",
    action: "后续可接入平台订阅或自动化采集。",
    verify_status: entry.url ? "手动 URL 待核验" : "仅记录名称",
    score: entry.score || 0,
  };
}

function platformSearchUrl(platform, value) {
  const query = String(value || "").trim();
  if (!query) return "";
  if (/^https?:\/\//i.test(query)) return query;
  const siteMap = {
    公众号: "mp.weixin.qq.com",
    快手: "kuaishou.com",
    抖音: "douyin.com",
    B站: "bilibili.com",
    Twitch: "twitch.tv",
    YouTube: "youtube.com",
    TED: "ted.com",
  };
  const site = siteMap[platform] ? `site:${siteMap[platform]} ` : "";
  return `https://www.google.com/search?q=${encodeURIComponent(`${site}${query}`)}`;
}

function foloSourceKey(item, url = "") {
  const raw = [item?.folo_article_url, url, item?.title, item?.source].filter(Boolean).join("|");
  return encodeURIComponent(raw || "unknown").slice(0, 180);
}

function isFoloJumpReady(item) {
  return Boolean(item?.folo_article_url && (item?.has_folo_internal_id || String(item?.folo_position_status || "").includes("可打开")));
}

function itemAgeHours(item) {
  const raw = item?.published_at || item?.created_at || item?.collected_at || "";
  if (!raw) return null;
  const normalized = String(raw).trim().replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, (Date.now() - date.getTime()) / 36e5);
}

function hotspotSignal(item) {
  const baseScore = Math.max(0, Math.min(100, Number(item?.score || 0)));
  const text = [item?.title, item?.why, item?.action, item?.section, item?.category, item?.source].filter(Boolean).join(" ");
  const rules = [
    { pattern: /风口|趋势|爆发|拐点|红利|机会|窗口期|新规|政策/, weight: 22, label: "趋势/政策窗口" },
    { pattern: /监管|风险|安全|漏洞|诈骗|预警|合规|封禁/, weight: 18, label: "风险/安全信号" },
    { pattern: /融资|招聘|校招|奖学金|补贴|竞赛|项目申报|资格证/, weight: 16, label: "机会/资源信号" },
    { pattern: /AI|人工智能|agent|机器人|自动化|芯片|算力|大模型/i, weight: 14, label: "技术风向" },
    { pattern: /稀缺|档案|解密|数据库|题库|电子书|开源|论文|报告/, weight: 12, label: "稀缺资源" },
  ];
  const reasons = [];
  let score = Math.round(baseScore * 0.42);
  for (const rule of rules) {
    if (rule.pattern.test(text)) {
      score += rule.weight;
      reasons.push(rule.label);
    }
  }
  if (isFoloJumpReady(item)) {
    score += 10;
    reasons.push("Folo 可追踪");
  }
  const age = itemAgeHours(item);
  if (age !== null) {
    if (age <= 24) {
      score += 12;
      reasons.push("24小时新鲜");
    } else if (age <= 72) {
      score += 6;
      reasons.push("72小时内");
    } else if (age > 720) {
      score -= 10;
      reasons.push("时间衰减");
    }
  }
  const sourceKey = foloSourceKey(item, item?.folo_source_url || item?.folo_url || item?.folo_article_url || "");
  const clicks = foloClickCount(sourceKey);
  if (clicks >= 3) {
    score += 16;
    reasons.push("多次寻源");
  } else if (clicks > 0) {
    score += Math.min(10, clicks * 4);
    reasons.push("已被点击");
  }
  const finalScore = Math.max(0, Math.min(100, score));
  return {
    score: finalScore,
    reasons: [...new Set(reasons)].slice(0, 4),
    level: finalScore >= 82 ? "high" : finalScore >= 68 ? "medium" : "low",
  };
}

function isHotPotential(item) {
  return hotspotSignal(item).score >= 68;
}

function foloToneClass(count) {
  const tones = ["violet", "cyan", "indigo", "blue", "green", "yellow", "orange", "red"];
  return `tone-${tones[Math.min(Math.max(Number(count || 1) - 1, 0), tones.length - 1)]}`;
}

function foloClickCount(key) {
  return (state.foloSourceTimeline || []).find((item) => item.key === key)?.count || 0;
}

function beijingParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

function beijingDateFromParts(parts, hour, minute) {
  return new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), hour - 8, minute, 0));
}

function parseBackendUtcDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const normalized = raw.replace(" ", "T");
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const date = new Date(hasZone ? normalized : `${normalized}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatBeijingDateTime(value, withSeconds = false) {
  const date = value instanceof Date ? value : parseBackendUtcDate(value);
  if (!date) return "未记录";
  const parts = beijingParts(date);
  const time = withSeconds ? `${parts.hour}:${parts.minute}:${parts.second}` : `${parts.hour}:${parts.minute}`;
  return `${parts.year}-${parts.month}-${parts.day} ${time}`;
}

function formatBeijingDateTimeLoose(value, withSeconds = false) {
  if (!value) return "";
  const raw = String(value).trim();
  if (!raw) return "";
  if (!/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(raw)) return raw;
  return formatBeijingDateTime(raw, withSeconds);
}

function beijingBackendIntervalLabel(health = {}) {
  const previous = health.previous_finished_at || "";
  const current = health.current_finished_at || health.last_finished_at || "";
  if (previous || current) {
    return `${formatBeijingDateTimeLoose(previous, true) || "首次记录"} → ${formatBeijingDateTimeLoose(current, true) || "等待巡检完成"}`;
  }
  const label = String(health.inspection_interval_label || "").trim();
  if (!label || !label.includes("→")) return "";
  const parts = label.split("→").map((part) => part.trim());
  if (parts.length < 2) return "";
  return `${formatBeijingDateTimeLoose(parts[0], true) || parts[0] || "首次记录"} → ${formatBeijingDateTimeLoose(parts[1], true) || parts[1] || "等待巡检完成"}`;
}

function beijingInspectionWindow(now = new Date()) {
  const slots = [
    { hour: 8, minute: 30 },
    { hour: 11, minute: 30 },
    { hour: 17, minute: 30 },
    { hour: 21, minute: 30 },
  ];
  const today = beijingParts(now);
  const yesterday = beijingParts(new Date(beijingDateFromParts(today, 0, 0).getTime() - 60 * 1000));
  const tomorrow = beijingParts(new Date(beijingDateFromParts(today, 23, 59).getTime() + 60 * 1000));
  const todaySlots = slots.map((slot) => beijingDateFromParts(today, slot.hour, slot.minute));
  const previousDaySlots = slots.map((slot) => beijingDateFromParts(yesterday, slot.hour, slot.minute));
  const tomorrowSlots = slots.map((slot) => beijingDateFromParts(tomorrow, slot.hour, slot.minute));
  let currentIndex = -1;
  for (let index = 0; index < todaySlots.length; index += 1) {
    if (todaySlots[index].getTime() <= now.getTime()) currentIndex = index;
  }
  let current;
  let previous;
  let next;
  if (currentIndex === -1) {
    current = previousDaySlots[previousDaySlots.length - 1];
    previous = previousDaySlots[previousDaySlots.length - 2];
    next = todaySlots[0];
  } else {
    current = todaySlots[currentIndex];
    previous = currentIndex === 0 ? previousDaySlots[previousDaySlots.length - 1] : todaySlots[currentIndex - 1];
    next = todaySlots[currentIndex + 1] || tomorrowSlots[0];
  }
  return {
    previous,
    current,
    next,
    label: `${formatBeijingDateTime(previous)} → ${formatBeijingDateTime(current)}`,
    nextLabel: formatBeijingDateTime(next),
  };
}

function inspectionIntervalLabel(health = state.latestHealth || {}) {
  return beijingBackendIntervalLabel(health) || beijingInspectionWindow().label;
}

function hiveMetrics(items = state.currentHiveItems || []) {
  const rows = items || [];
  const jumpReadyCount = rows.filter(isFoloJumpReady).length;
  const hotCount = rows.filter(isHotPotential).length;
  return {
    totalNew: rows.length,
    jumpReadyCount,
    hotCount,
    foloNewIdCount: jumpReadyCount,
  };
}

function updateHiveKpis(items = state.currentHiveItems || []) {
  state.currentHiveMetrics = hiveMetrics(items);
  const intelCount = $("#intelCount");
  const fileCount = $("#fileCount");
  const inboxCount = $("#inboxCount");
  if (intelCount) intelCount.textContent = String(state.currentHiveMetrics.jumpReadyCount);
  if (fileCount) fileCount.textContent = String(state.currentHiveMetrics.totalNew);
  if (inboxCount) inboxCount.textContent = String(state.currentHiveMetrics.hotCount);
  const interval = $("#inspectionIntervalLabel");
  if (interval) interval.textContent = inspectionIntervalLabel();
}

function recordFoloSourceClick(dataset) {
  const key = dataset.foloKey || "";
  if (!key) return null;
  const rows = state.foloSourceTimeline || [];
  const current = rows.find((item) => item.key === key) || {
    key,
    title: dataset.foloTitle || "未命名 Folo 源",
    source: dataset.foloSource || "未知来源",
    url: dataset.foloUrl || "",
    count: 0,
    clicks: [],
  };
  current.title = dataset.foloTitle || current.title;
  current.source = dataset.foloSource || current.source;
  current.url = dataset.foloUrl || current.url;
  current.count = Number(current.count || 0) + 1;
  current.clicks = [...(current.clicks || []), { at: new Date().toISOString() }].slice(-30);
  state.foloSourceTimeline = [current, ...rows.filter((item) => item.key !== key)].slice(0, 80);
  saveLocalJson(FOLO_SOURCE_TIMELINE_KEY, state.foloSourceTimeline);
  return current;
}

async function loadFoloSourceTimeline() {
  try {
    const data = await api("/api/folo/source-timeline?limit=80");
    state.foloSourceTimeline = data.items || [];
    saveLocalJson(FOLO_SOURCE_TIMELINE_KEY, state.foloSourceTimeline);
    renderFoloTimeline();
    return data;
  } catch (err) {
    renderFoloTimeline();
    throw err;
  }
}

async function syncFoloSourceClick(dataset, linkEl = null) {
  const payload = {
    key: dataset.foloKey || "",
    title: dataset.foloTitle || "",
    source: dataset.foloSource || "",
    url: dataset.foloUrl || "",
  };
  if (!payload.key) return null;
  try {
    const data = await api("/api/folo/source-timeline", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.foloSourceTimeline = data.items || [];
    saveLocalJson(FOLO_SOURCE_TIMELINE_KEY, state.foloSourceTimeline);
    renderFoloTimeline();
    if (linkEl) linkEl.textContent = `Folo 源列表 · ${foloClickCount(payload.key)}次`;
    showToast("已同步 Folo 寻源时间线");
    return data;
  } catch (err) {
    showToast("服务端同步失败，已本地记录");
    return null;
  }
}

function renderManualHiveEntries() {
  const list = $("#manualHiveList");
  const status = $("#manualHiveStatus");
  if (!list) return;
  const rows = state.manualHiveEntries || [];
  const wechat = state.manualHiveWechatResults;
  const wechatRows = wechat?.items || [];
  if (status) {
    status.textContent = state.manualHiveWechatLoading
      ? "正在检索公众号..."
      : wechat
      ? `公众号检索「${wechat.query || ""}」命中 ${wechat.count || wechatRows.length || 0} 个；可订阅、拉取文章、查看文章列表，并回到个人雷达检索。`
      : state.manualHiveStats
      ? `服务端手动信息源 ${state.manualHiveStats.total || rows.length} 条；会直接并入本次信息寻缘卡片池。`
      : `本地手动信息源 ${rows.length} 条；登录后会优先同步到服务端。`;
  }
  const wechatHtml = wechatRows.length
    ? `
      <section class="manual-wechat-results" aria-label="公众号检索结果">
        ${wechatRows.map((item) => `
          <article class="item hive-entry manual-wechat-card ${item.subscribed ? "is-subscribed" : ""}">
            <div class="manual-wechat-head">
              ${item.round_head_img ? `<img src="${escapeHtml(item.round_head_img)}" alt="" loading="lazy" />` : `<div class="manual-wechat-avatar">微</div>`}
              <div>
                <div class="item-title">${escapeHtml(item.nickname || item.name || "未命名公众号")}</div>
                <div class="item-meta">${escapeHtml(item.alias ? `微信号 ${item.alias}` : "未提供微信号")} · ${escapeHtml(item.status || (item.subscribed ? "已订阅" : "可订阅"))}</div>
              </div>
            </div>
            <code>${escapeHtml(item.fakeid || "缺少 fakeid")}</code>
            <div class="manual-wechat-actions">
              <button class="secondary" type="button" data-wechat-subscribe="1" data-fakeid="${escapeHtml(item.fakeid || "")}" data-nickname="${escapeHtml(item.nickname || item.name || "")}">
                ${item.subscribed ? "重新拉取文章" : "订阅公众号"}
              </button>
              ${(item.rss_view_url || item.rss_url) ? `<a href="${escapeHtml(item.rss_view_url || item.rss_url)}" target="_blank" rel="noreferrer">查看文章</a>` : ""}
              <button class="ghost" type="button" data-wechat-folo-open="1" data-fakeid="${escapeHtml(item.fakeid || "")}" data-nickname="${escapeHtml(item.nickname || item.name || "")}">
                在 Folo 订阅并打开
              </button>
              <button class="ghost" type="button" data-wechat-search-radar="${escapeHtml(item.nickname || item.name || "")}">检索文章</button>
            </div>
          </article>
        `).join("")}
      </section>
    `
    : wechat && !state.manualHiveWechatLoading
    ? `<div class="item"><div class="item-meta">没有命中公众号；确认已登录微信采集器账号后再试。</div></div>`
    : "";
  const entriesHtml = rows.length
    ? rows.slice(0, 10).map((item) => `
      <article class="item hive-entry">
        <div class="item-title">${escapeHtml(item.name || "未命名信息源")}</div>
        <div class="item-meta">${escapeHtml(item.platform || "其它")} · 记录 ${escapeHtml(item.seen_count || 1)} 次 · ${escapeHtml(item.updated_at || item.created_at || "未记录时间")}</div>
        ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开线索</a>` : ""}
      </article>
    `).join("")
    : "";
  list.innerHTML = [wechatHtml, entriesHtml || (!wechatHtml ? `<div class="item"><div class="item-meta">还没有手动加入的信息源。</div></div>` : "")]
    .filter(Boolean)
    .join("");
}

async function loadManualHiveEntries() {
  try {
    const data = await api("/api/folo/manual-entries?limit=80");
    state.manualHiveStats = data;
    state.manualHiveEntries = data.items || [];
    saveLocalJson(FOLO_MANUAL_ENTRIES_KEY, state.manualHiveEntries);
    renderIntelCards(state.currentApiHiveItems);
    return data;
  } catch (err) {
    state.manualHiveStats = null;
    renderManualHiveEntries();
    throw err;
  }
}

async function syncManualHiveEntry(entry) {
  const data = await api("/api/folo/manual-entries", {
    method: "POST",
    body: JSON.stringify(entry),
  });
  state.manualHiveStats = data;
  state.manualHiveEntries = data.items || [];
  saveLocalJson(FOLO_MANUAL_ENTRIES_KEY, state.manualHiveEntries);
  renderIntelCards(state.currentApiHiveItems);
  return data;
}

async function clearManualHiveEntries() {
  const data = await api("/api/folo/manual-entries", { method: "DELETE" });
  state.manualHiveStats = data;
  state.manualHiveEntries = data.items || [];
  saveLocalJson(FOLO_MANUAL_ENTRIES_KEY, state.manualHiveEntries);
  renderIntelCards(state.currentApiHiveItems);
  return data;
}

async function searchManualHiveWechat() {
  const input = $("#manualHiveName");
  const button = $("#manualHiveSearchNameBtn");
  const query = (input?.value || "").trim();
  if (!query) {
    showToast("先输入公众号名称");
    return null;
  }
  state.manualHiveWechatLoading = true;
  renderManualHiveEntries();
  if (button) button.disabled = true;
  try {
    const data = await api("/api/manual-hive/wechat/search", {
      method: "POST",
      body: JSON.stringify({ query, limit: 10 }),
    });
    state.manualHiveWechatResults = data;
    showToast(`公众号检索命中 ${data.count || data.items?.length || 0} 个`);
    return data;
  } finally {
    state.manualHiveWechatLoading = false;
    if (button) button.disabled = false;
    renderManualHiveEntries();
  }
}

async function subscribeManualHiveWechat(fakeid, nickname, button = null) {
  const fid = String(fakeid || "").trim();
  const name = String(nickname || "").trim();
  if (!fid) {
    showToast("缺少公众号 fakeid，无法订阅");
    return null;
  }
  if (button) button.disabled = true;
  try {
    const data = await api("/api/manual-hive/wechat/subscribe", {
      method: "POST",
      body: JSON.stringify({ fakeid: fid, nickname: name, poll: true }),
    });
    if (state.manualHiveWechatResults?.items) {
      state.manualHiveWechatResults.items = state.manualHiveWechatResults.items.map((item) => (
        item.fakeid === fid
          ? { ...item, subscribed: true, status: "已订阅", rss_url: data.rss_url || item.rss_url }
          : item
      ));
    }
    await loadManualHiveEntries().catch(() => null);
    const articleCount = data.import_result?.article_count ?? 0;
    showToast(`已订阅并入库：${name || "公众号"} · ${articleCount} 篇`);
    return data;
  } finally {
    if (button) button.disabled = false;
    renderManualHiveEntries();
  }
}

async function openManualHiveWechatInFolo(fakeid, nickname, button = null) {
  const fid = String(fakeid || "").trim();
  const name = String(nickname || "").trim();
  if (!fid) {
    showToast("缺少公众号 fakeid，无法送往 Folo");
    return null;
  }
  let popup = null;
  try {
    popup = window.open("about:blank", "_blank", "noopener,noreferrer");
  } catch {
    popup = null;
  }
  const originalText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "正在送往 Folo...";
  }
  try {
    const data = await api("/api/manual-hive/wechat/folo-open", {
      method: "POST",
      body: JSON.stringify({ fakeid: fid, nickname: name, poll: true }),
    });
    if (state.manualHiveWechatResults?.items) {
      state.manualHiveWechatResults.items = state.manualHiveWechatResults.items.map((item) => (
        item.fakeid === fid
          ? {
              ...item,
              subscribed: true,
              status: "已订阅 · Folo待确认",
              rss_url: data.raw_rss_url || item.rss_url,
              rss_view_url: data.rss_view_url || item.rss_view_url,
              folo_feed_url: data.feed_url,
              folo_open_url: data.folo_open_url,
            }
          : item
      ));
    }
    if (data.feed_url) {
      await copyText(data.feed_url).catch(() => null);
    }
    if (data.folo_open_url) {
      if (popup) {
        popup.location.href = data.folo_open_url;
      } else {
        window.open(data.folo_open_url, "_blank", "noopener,noreferrer");
      }
    } else if (popup) {
      popup.close();
    }
    await loadManualHiveEntries().catch(() => null);
    const articleCount = data.import_result?.article_count ?? 0;
    showToast(`已订阅并打开 Folo：${name || "公众号"} · ${articleCount} 篇；RSS 地址已复制`);
    return data;
  } catch (err) {
    if (popup) popup.close();
    throw err;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText || "在 Folo 订阅并打开";
    }
    renderManualHiveEntries();
  }
}

function openManualHiveSearch(kind = "name") {
  const platform = $("#manualHivePlatform")?.value || "其它";
  const input = kind === "url" ? $("#manualHiveUrl") : $("#manualHiveName");
  const value = (input?.value || "").trim();
  if (!value) {
    showToast(kind === "url" ? "先输入 URL 或内容关键词" : "先输入账号/频道/作者名称");
    return;
  }
  if (platform === "公众号" && kind === "name") {
    searchManualHiveWechat().catch((err) => showToast(err.message));
    return;
  }
  window.open(platformSearchUrl(platform, value), "_blank", "noopener,noreferrer");
}

function renderManualFeedProbe() {
  const list = $("#manualFeedProbeList");
  const status = $("#manualFeedProbeStatus");
  if (!list) return;
  const data = state.manualFeedProbe;
  const rows = data?.items || [];
  if (status) {
    status.textContent = data
      ? `${data.title || "订阅源"}：解析到 ${data.count || rows.length} 条；内置适配器不运行外部代码。`
      : "RSS/Atom 内置适配器可解析公开订阅源，不运行外部代码。";
  }
  list.innerHTML = rows.length
    ? rows.slice(0, 8).map((item) => `
      <article class="item hive-entry">
        <div class="item-title">${escapeHtml(item.title || "未命名条目")}</div>
        <div class="item-meta">${escapeHtml(item.published_at || "未记录时间")}</div>
        ${item.link ? `<a href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer">打开条目</a>` : ""}
      </article>
    `).join("")
    : `<div class="item"><div class="item-meta">粘贴 RSS/Atom URL 后点击“探测RSS/Atom”。</div></div>`;
}

async function probeManualFeed() {
  const button = $("#manualFeedProbeBtn");
  const url = ($("#manualHiveUrl")?.value || "").trim();
  if (!url) {
    showToast("先在 URL 检索框粘贴 RSS/Atom 地址");
    return null;
  }
  if (button) button.disabled = true;
  try {
    const data = await api("/api/folo/feed-probe", {
      method: "POST",
      body: JSON.stringify({ url, limit: 12 }),
    });
    state.manualFeedProbe = data;
    renderManualFeedProbe();
    showToast(`订阅源解析到 ${data.count || 0} 条`);
    return data;
  } finally {
    if (button) button.disabled = false;
  }
}

function renderCollectorAdapters() {
  const list = $("#collectorAdapterList");
  const status = $("#collectorAdapterStatus");
  if (!list) return;
  const rows = state.collectorAdapterEntries || [];
  const presets = state.collectorAdapterStats?.presets || [];
  const whitelist = state.collectorAdapterStats?.whitelist || [];
  const runs = state.collectorAdapterStats?.runs || [];
  const whitelistByFingerprint = new Map(whitelist.map((item) => [item.fingerprint, item]));
  if (status) {
    status.textContent = `已登记候选 ${rows.length} 个；执行白名单 ${whitelist.length} 个；最近运行 ${runs.length} 次。候选只登记，只有白名单内置 runner 可执行。`;
  }
  list.innerHTML = rows.length
    ? rows.slice(0, 8).map((item) => {
      const allowed = whitelistByFingerprint.get(item.fingerprint);
      return `
      <article class="item hive-entry">
        <div class="item-title">${escapeHtml(item.platform || "其它")} · ${escapeHtml(item.name || "未命名采集器")}</div>
        <div class="item-meta">${escapeHtml(item.status || "候选")} · ${escapeHtml(item.source || "GitHub")} · 记录 ${escapeHtml(item.seen_count || 1)} 次${item.github_license ? ` · License ${escapeHtml(item.github_license)}` : ""}${item.github_stars !== undefined ? ` · Stars ${escapeHtml(item.github_stars)}` : ""}</div>
        ${item.repo_url ? `<a href="${escapeHtml(item.repo_url)}" target="_blank" rel="noreferrer">打开仓库</a>` : ""}
        ${item.repo_url && item.fingerprint ? `<button class="ghost" data-collector-adapter-review="${escapeHtml(item.fingerprint)}" type="button">审核仓库</button>` : ""}
        ${item.repo_url && item.fingerprint && String(item.status || "").startsWith("reviewed-") && !allowed ? `<button class="ghost" data-collector-adapter-allow="${escapeHtml(item.fingerprint)}" type="button">加入白名单</button>` : ""}
        ${allowed ? `<button class="ghost" data-collector-adapter-run="${escapeHtml(item.fingerprint)}" type="button">执行采集</button>` : ""}
        ${allowed ? `<div class="source-note">白名单 runner：${escapeHtml(allowed.runner || "未指定")}；最近运行：${escapeHtml(allowed.last_run_at || "尚未运行")}</div>` : ""}
        ${item.notes ? `<div class="source-note">${escapeHtml(item.notes)}</div>` : ""}
        ${item.review_note ? `<div class="source-note">${escapeHtml(item.review_note)}</div>` : ""}
      </article>
    `;
    }).join("")
    : `<div class="item"><div class="item-meta">选择平台后点击“发现当前平台采集器”。</div></div>`;
  if (runs.length) {
    list.insertAdjacentHTML("beforeend", `
      <article class="item hive-entry">
        <div class="item-title">最近白名单采集</div>
        ${runs.slice(0, 3).map((run) => `<div class="item-meta">${escapeHtml(run.finished_at || run.started_at || "未记录时间")} · ${escapeHtml(run.runner || "runner")} · ${escapeHtml(run.collected_count || 0)} 条 · ${escapeHtml(run.sandbox_dir || "")}</div>`).join("")}
      </article>
    `);
  }
}

async function loadCollectorAdapters() {
  try {
    const data = await api("/api/folo/collector-adapters?limit=80");
    state.collectorAdapterStats = data;
    state.collectorAdapterEntries = data.items || [];
    renderCollectorAdapters();
    return data;
  } catch (err) {
    state.collectorAdapterStats = null;
    renderCollectorAdapters();
    throw err;
  }
}

async function discoverCollectorAdapters() {
  const button = $("#collectorAdapterDiscoverBtn");
  const platform = $("#manualHivePlatform")?.value || "其它";
  if (button) button.disabled = true;
  try {
    const data = await api("/api/folo/collector-adapters/discover", {
      method: "POST",
      body: JSON.stringify({ platform, limit: 5 }),
    });
    state.collectorAdapterStats = data;
    state.collectorAdapterEntries = data.items || [];
    renderCollectorAdapters();
    showToast(`已发现 ${data.added?.length || 0} 个${platform}采集器候选`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function reviewCollectorAdapter(fingerprint) {
  const data = await api("/api/folo/collector-adapters/review", {
    method: "POST",
    body: JSON.stringify({ fingerprint }),
  });
  state.collectorAdapterStats = data;
  state.collectorAdapterEntries = data.items || [];
  renderCollectorAdapters();
  return data;
}

async function allowCollectorAdapter(fingerprint) {
  const data = await api("/api/folo/collector-adapters/allow", {
    method: "POST",
    body: JSON.stringify({ fingerprint, runner: "github-repo-metadata-snapshot" }),
  });
  state.collectorAdapterStats = data;
  state.collectorAdapterEntries = data.items || [];
  renderCollectorAdapters();
  return data;
}

async function runCollectorAdapter(fingerprint) {
  const data = await api("/api/folo/collector-adapters/run", {
    method: "POST",
    body: JSON.stringify({ fingerprint }),
  });
  state.collectorAdapterStats = data;
  state.collectorAdapterEntries = data.items || [];
  if (data.manual_entries?.items) state.manualHiveEntries = data.manual_entries.items;
  renderCollectorAdapters();
  return data;
}

function renderResourcePoolEntries() {
  const list = $("#resourceHiveList");
  const status = $("#resourceHiveStatus");
  if (!list) return;
  const rows = state.resourcePoolEntries || [];
  const stats = state.resourceHiveStats || {};
  if (status) {
    status.textContent = stats.total !== undefined
      ? `服务端池源 ${stats.total} 条；有链接 ${stats.linked_count || 0} 条；已关联 NAS ${stats.nas_archived_count || 0} 条。可写入 .url 链接；原文件下载需先批准。`
      : `本地候选资源 ${rows.length} 条；登录后会优先同步到服务端池源。`;
  }
  list.innerHTML = rows.length
    ? rows.slice(0, 12).map((item) => `
      <article class="item hive-entry resource-entry">
        <div class="item-title">${escapeHtml(item.name || "未命名资源")}</div>
        <div class="item-meta">${escapeHtml(item.type || "其它资源")} · ${escapeHtml(item.status || "candidate")} · 记录 ${escapeHtml(item.seen_count || 1)} 次 · ${escapeHtml(item.updated_at || item.created_at || "未记录时间")}</div>
        ${item.link ? `<a href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer">打开资源线索</a>` : ""}
        ${item.link && !item.nas_path && item.fingerprint ? `<button class="ghost" data-resource-download-approve="${escapeHtml(item.fingerprint)}" type="button">批准下载</button>` : ""}
        ${item.nas_path ? `<code>${escapeHtml(item.nas_path)}</code>` : ""}
      </article>
    `).join("")
    : `<div class="item"><div class="item-meta">先记录候选资源名；后续再接全网搜索和 NAS 自动归档。</div></div>`;
}

async function loadResourceHive() {
  try {
    const data = await api("/api/resource-hive?limit=120");
    state.resourceHiveStats = data;
    state.resourcePoolEntries = data.items || [];
    saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
    renderResourcePoolEntries();
    return data;
  } catch (err) {
    state.resourceHiveStats = null;
    renderResourcePoolEntries();
    throw err;
  }
}

function renderResourceHiveCandidates() {
  const box = $("#resourceHiveCandidates");
  if (!box) return;
  const rows = state.resourceHiveCandidates || [];
  box.innerHTML = rows.length
    ? rows.map((item, index) => `
      <article class="item hive-entry resource-candidate">
        <div class="item-title">${escapeHtml(item.name || "未命名候选")}</div>
        <div class="item-meta">${escapeHtml(item.type || "其它资源")} · ${escapeHtml(item.source || "公开搜索")} · ${escapeHtml(item.status || "discovered")}</div>
        ${item.link ? `<a href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer">打开候选来源</a>` : ""}
        <button class="ghost" data-resource-candidate-add="${escapeHtml(index)}" type="button">加入服务端池源</button>
      </article>
    `).join("")
    : `<div class="item"><div class="item-meta">输入关键词后可搜索公开网页候选资源。</div></div>`;
}

async function discoverResourceHive(autoAdd = false) {
  const queryInput = $("#resourceHiveQuery");
  const query = (queryInput?.value || "").trim();
  const type = $("#resourceHiveType")?.value || "其它资源";
  if (!query) {
    showToast("请输入资源搜索关键词");
    return;
  }
  const button = autoAdd ? $("#resourceHiveAutoAddBtn") : $("#resourceHiveDiscoverBtn");
  if (button) button.disabled = true;
  try {
    const data = await api("/api/resource-hive/discover", {
      method: "POST",
      body: JSON.stringify({ query, type, limit: 8, auto_add: autoAdd }),
    });
    state.resourceHiveCandidates = data.items || [];
    renderResourceHiveCandidates();
    if (autoAdd && data.resource_hive) {
      state.resourceHiveStats = data.resource_hive;
      state.resourcePoolEntries = data.resource_hive.items || [];
      saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
      renderResourcePoolEntries();
    }
    showToast(autoAdd ? `已发现并入池 ${data.added?.length || 0} 条` : `发现候选 ${data.count || 0} 条`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function discoverResourceHiveBatch(autoAdd = false) {
  const button = autoAdd ? $("#resourceHiveBatchAutoAddBtn") : $("#resourceHiveBatchBtn");
  if (button) button.disabled = true;
  try {
    const data = await api("/api/resource-hive/discover-batch", {
      method: "POST",
      body: JSON.stringify({ limit_per_query: 2, auto_add: autoAdd }),
    });
    state.resourceHiveCandidates = data.items || [];
    renderResourceHiveCandidates();
    if (autoAdd && data.resource_hive) {
      state.resourceHiveStats = data.resource_hive;
      state.resourcePoolEntries = data.resource_hive.items || [];
      saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
      renderResourcePoolEntries();
    }
    const errorText = data.errors?.length ? `，失败 ${data.errors.length} 组` : "";
    showToast(autoAdd ? `预设巡检入池 ${data.added?.length || 0} 条${errorText}` : `预设巡检发现 ${data.count || 0} 条${errorText}`);
  } finally {
    if (button) button.disabled = false;
  }
}

function renderResourceArchivePlan() {
  const list = $("#resourceArchivePlanList");
  const status = $("#resourceArchivePlanStatus");
  if (!list) return;
  const data = state.resourceArchivePlan;
  const rows = data?.items || [];
  if (status) {
    status.textContent = data
      ? `待归档 ${data.total_pending || rows.length} 条；根目录：${data.archive_root || "未配置"}。只生成计划，不自动下载。`
      : "归档计划只生成建议路径，不自动下载版权或来源未确认的文件。";
  }
  list.innerHTML = rows.length
    ? rows.slice(0, 8).map((item) => `
      <article class="item hive-entry resource-entry">
        <div class="item-title">${escapeHtml(item.type || "其它资源")} · ${escapeHtml(item.name || "未命名资源")}</div>
        <div class="item-meta">${escapeHtml(item.reason || "等待确认")}</div>
        ${item.link ? `<a href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer">打开来源</a>` : ""}
        <code>${escapeHtml(item.suggested_nas_path || "")}</code>
      </article>
    `).join("")
    : `<div class="item"><div class="item-meta">暂无待归档资源，或资源池仍为空。</div></div>`;
}

async function loadResourceArchivePlan() {
  const data = await api("/api/resource-hive/archive-plan?limit=120");
  state.resourceArchivePlan = data;
  renderResourceArchivePlan();
  return data;
}

async function writeResourceArchiveLinks() {
  const data = await api("/api/resource-hive/archive-links?limit=120", { method: "POST" });
  state.resourceHiveStats = data.resource_hive || state.resourceHiveStats;
  state.resourcePoolEntries = data.resource_hive?.items || state.resourcePoolEntries;
  state.resourceArchivePlan = await api("/api/resource-hive/archive-plan?limit=120");
  saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries || []);
  renderResourcePoolEntries();
  renderResourceArchivePlan();
  return data;
}

async function approveResourceDownload(fingerprint) {
  const data = await api("/api/resource-hive/download-approval", {
    method: "POST",
    body: JSON.stringify({ fingerprint }),
  });
  state.resourceHiveStats = data;
  state.resourcePoolEntries = data.items || [];
  saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries || []);
  renderResourcePoolEntries();
  return data;
}

async function downloadApprovedResources() {
  const data = await api("/api/resource-hive/download-approved?limit=20", { method: "POST" });
  state.resourceHiveStats = data.resource_hive || state.resourceHiveStats;
  state.resourcePoolEntries = data.resource_hive?.items || state.resourcePoolEntries;
  state.resourceArchivePlan = await api("/api/resource-hive/archive-plan?limit=120");
  saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries || []);
  renderResourcePoolEntries();
  renderResourceArchivePlan();
  return data;
}

function formatTimelineClick(value) {
  if (!value) return "未记录";
  const date = parseBackendUtcDate(value);
  if (!date) return value;
  const parts = beijingParts(date);
  return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

function renderFoloTimeline() {
  const timeline = $("#foloSourceTimeline");
  const starList = $("#starCardList");
  if (!timeline || !starList) return;
  const rows = state.foloSourceTimeline || [];
  timeline.innerHTML = rows.length
    ? rows.slice(0, 12).map((item) => {
        const last = item.clicks?.[item.clicks.length - 1]?.at || "";
        const clickChain = (item.clicks || []).slice(-6).map((click) => formatTimelineClick(click.at));
        return `
          <article class="timeline-node ${item.count >= 3 ? "starred" : ""} ${foloToneClass(item.count)}">
            <div class="timeline-curve"></div>
            <div>
              <strong>${escapeHtml(item.title)}</strong>
              <span>${escapeHtml(item.source)} · 点击 ${escapeHtml(item.count)} 次 · ${escapeHtml(last || "未记录时间")}</span>
            </div>
            ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开 Folo 源</a>` : ""}
            ${clickChain.length ? `
              <div class="timeline-click-chain">
                ${clickChain.map((label, index) => `
                  ${index ? "<i aria-hidden=\"true\"></i>" : ""}
                  <span>${escapeHtml(label)}</span>
                `).join("")}
              </div>
            ` : ""}
          </article>
        `;
      }).join("")
    : `<div class="item"><div class="item-meta">还没有点击过 Folo 源列表。点击卡片里的“Folo 源列表”后会自动形成时间线。</div></div>`;

  const stars = rows.filter((item) => item.count >= 3);
  starList.innerHTML = stars.length
    ? `
      <div class="star-list-title">星标级别</div>
      ${stars.slice(0, 8).map((item) => `
        <article class="star-card ${foloToneClass(item.count)}">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.source)} · ${escapeHtml(item.count)} 次寻源</span>
        </article>
      `).join("")}
    `
    : `<div class="item"><div class="item-meta">同一 Folo 源列表点击 3 次后会自动进入星标级别。</div></div>`;
}

function renderIntelCards(items = state.currentApiHiveItems || []) {
  const box = $("#intelCards");
  state.currentApiHiveItems = Array.isArray(items) ? items : [];
  const combined = [...(state.manualHiveEntries || []).map(manualEntryToIntelItem), ...state.currentApiHiveItems];
  state.currentHiveItems = combined;
  updateHiveKpis(combined);
  renderManualHiveEntries();
  renderResourcePoolEntries();
  const rows = combined.slice(0, 24);
  if (!rows.length) {
    box.innerHTML = `<div class="item"><div class="item-meta">暂无区间搜集卡片</div></div>`;
    renderFoloTimeline();
    return;
  }
  box.innerHTML = rows
    .map((item, idx) => {
      const id = locatorId("intel", idx);
      storeLocatorItem(id, item);
      const articleUrl = item.article_url || "";
      const officialUrl = item.official_url || articleUrl;
      const legacyFoloUrl = item.folo_url || "";
      const foloUrl = item.folo_article_url || "";
      const foloSourceBase = item.folo_source_url || (item.folo_matched ? legacyFoloUrl : "");
      const foloSourceUrl = foloLocatorUrl(foloSourceBase, item, "source");
      const foloKey = foloSourceKey(item, foloSourceUrl);
      const sourceClickCount = foloClickCount(foloKey);
      const starClass = sourceClickCount >= 3 ? ` star-card ${foloToneClass(sourceClickCount)}` : "";
      const foloText = item.folo_article_url ? "Folo 看原条" : "Folo 原条待补";
      const verifyText = item.verify_status ? `核验：${item.verify_status}` : "原文核验";
      const sourceType = item.collection_type || "来源待确认";
      const foloStatus = item.folo_position_status || (item.has_folo_internal_id ? "可打开 Folo 原条" : "缺少 Folo 内部条目 ID");
      const hot = hotspotSignal(item);
      const publishedAt = formatBeijingDateTimeLoose(item.published_at || "", true) || "待补充";
      return `
        <article class="intel-card${starClass}">
          <div class="intel-head">
            <div class="intel-index">${escapeHtml(item.index || idx + 1)}</div>
            <div class="intel-title">${escapeHtml(item.title || "未命名情报")}</div>
          </div>
          <div class="intel-time">
            <span>发布时间</span>
            <strong>${escapeHtml(publishedAt)}</strong>
          </div>
          <div class="badges">
            <span class="badge">${escapeHtml(item.section || item.category || "未分类")}</span>
            <span class="badge">${escapeHtml(item.source || "未知来源")}</span>
            <span class="badge ${item.collection_type === "手动收集" ? "manual" : ""}">${escapeHtml(sourceType)}</span>
            <span class="badge ${item.has_folo_internal_id ? "" : "warn"}">${escapeHtml(foloStatus)}</span>
            <span class="badge score">评分 ${escapeHtml(item.score || "-")}</span>
            <span class="badge hotspot ${escapeHtml(hot.level)}">热点 ${escapeHtml(hot.score)}</span>
          </div>
          <div class="intel-body">
            <div>${escapeHtml(item.why || "暂无关联说明")}</div>
            <div>${escapeHtml(item.action || "暂无建议行动")}</div>
            <div class="hotspot-line">热点因子：${escapeHtml(hot.reasons.length ? hot.reasons.join("、") : "未命中强信号")}</div>
            <div class="verify-line">${escapeHtml(verifyText)} · Folo 位置：${escapeHtml(item.folo_folder || "待补充")}</div>
          </div>
          <div class="intel-actions">
            <button class="secondary locator-trigger" data-locator="${escapeHtml(id)}" type="button">定位证据</button>
            <a class="${officialUrl ? "" : "disabled"}" href="${escapeHtml(officialUrl || "#")}" target="_blank" rel="noreferrer">原文核验</a>
            <a class="${foloUrl ? "secondary" : "disabled"}" href="${escapeHtml(foloUrl || "#")}" target="_blank" rel="noreferrer">${foloText}</a>
            <a class="${foloSourceUrl ? "secondary folo-source-jump" : "disabled"}" href="${escapeHtml(foloSourceUrl || "#")}" target="_blank" rel="noreferrer" data-folo-source-click="${foloSourceUrl ? "1" : ""}" data-folo-key="${escapeHtml(foloKey)}" data-folo-title="${escapeHtml(item.title || "未命名情报")}" data-folo-source="${escapeHtml(item.source || "未知来源")}" data-folo-url="${escapeHtml(foloSourceUrl || "")}">Folo 源列表${sourceClickCount ? ` · ${escapeHtml(sourceClickCount)}次` : ""}</a>
          </div>
        </article>
      `;
    })
    .join("");
  renderFoloTimeline();
}

function formatRatio(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Math.round(number * 100)}%`;
}

function formatAgeHours(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "未知";
  if (number < 1) return `${Math.max(0, Math.round(number * 60))} 分钟前`;
  if (number < 48) return `${number.toFixed(1)} 小时前`;
  return `${(number / 24).toFixed(1)} 天前`;
}

function textByteLength(value) {
  try {
    return new TextEncoder().encode(String(value || "")).length;
  } catch {
    return String(value || "").length;
  }
}

function formatBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "未记录";
  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function compactInlineText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function metricValue(text, patterns) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match[1];
  }
  return "";
}

function parseNumberedItems(text, limit = 3) {
  const normalized = compactInlineText(text);
  if (!normalized) return [];
  const matches = [...normalized.matchAll(/(?:^|\s)(\d{1,2})[.、]\s*/g)];
  if (!matches.length) return [normalized].filter(Boolean).slice(0, limit);
  return matches
    .slice(0, limit)
    .map((match, index) => {
      const start = match.index + match[0].length;
      const end = matches[index + 1]?.index ?? normalized.length;
      return normalized.slice(start, end).trim();
    })
    .filter(Boolean);
}

function parseBriefSections(text) {
  const sections = [];
  const headingPattern = /([一二三四五六七八九十]+)、([^一二三四五六七八九十]{2,24}?)(?=\s+\d+[.、]|\s|$)/g;
  const matches = [...text.matchAll(headingPattern)];
  for (const match of matches.slice(0, 4)) {
    const start = match.index + match[0].length;
    const next = matches.find((item) => item.index > match.index);
    const end = next?.index ?? text.length;
    const title = compactInlineText(match[2]).replace(/[：:]+$/, "");
    const items = parseNumberedItems(text.slice(start, end), 3);
    if (title && items.length) {
      sections.push({ title, items });
    }
  }
  return sections;
}

function renderStructuredSummary(body) {
  const text = compactInlineText(body);
  const isDailyBrief = text.includes("【InfoRadar 今日情报】") || /输入\s*\d+\s*条/.test(text);
  if (!isDailyBrief) {
    return `<div>${escapeHtml(body || "暂无摘要")}</div>`;
  }
  const metrics = [
    { label: "输入", value: metricValue(text, [/输入\s*(\d+)\s*条/]) },
    { label: "输出", value: metricValue(text, [/输出\s*(\d+)\s*条/]) },
    { label: "自动源", value: metricValue(text, [/自动源[：:]\s*(\d+)\s*条/]) },
    { label: "Folo回流", value: metricValue(text, [/Folo回流[：:]\s*(\d+)\s*条/]) },
    { label: "重复", value: metricValue(text, [/合并重复\s*(\d+)\s*条/]) },
    { label: "URL异常", value: metricValue(text, [/URL异常\s*(\d+)\s*条/]) },
  ].filter((item) => item.value !== "");
  const sections = parseBriefSections(text);
  const lead = compactInlineText(text.split(/[一二三四五六七八九十]、/)[0] || "").replace(/^【InfoRadar 今日情报】\s*/, "");
  return `
    <div class="brief-summary">
      ${lead ? `<div class="brief-lead">${escapeHtml(lead)}</div>` : ""}
      ${metrics.length ? `
        <div class="brief-metrics">
          ${metrics.map((item) => `
            <span class="brief-metric">
              <em>${escapeHtml(item.value)}</em>
              <span>${escapeHtml(item.label)}</span>
            </span>
          `).join("")}
        </div>
      ` : ""}
      ${sections.length ? `
        <div class="brief-sections">
          ${sections.map((section) => `
            <div class="brief-section">
              <div class="brief-section-title">${escapeHtml(section.title)}</div>
              <ul>
                ${section.items.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}
              </ul>
            </div>
          `).join("")}
        </div>
      ` : `<div class="brief-fallback">${escapeHtml(text)}</div>`}
    </div>
  `;
}

function renderRadarHealth() {
  const box = $("#radarHealth");
  if (!box) return;
  const health = state.latestHealth || {};
  const stats = state.itemStats || {};
  const metrics = state.currentHiveMetrics || hiveMetrics(state.currentHiveItems);
  const stale = Boolean(health.is_stale);
  const foloTotal = Number(metrics.totalNew || 0);
  const foloReady = metrics.jumpReadyCount;
  const foloRatio = foloTotal ? foloReady / foloTotal : 0;
  const foloBaseIdCount = Math.max(0, Number(stats.folo_internal_id_count || 0) - Number(metrics.foloNewIdCount || 0));
  const inventoryTotal = Number(health.search_index_record_count || stats.item_count || metrics.totalNew || 0);
  const inventoryBase = Math.max(0, inventoryTotal - Number(metrics.totalNew || 0));
  const currentHiveBytes = state.currentHiveItems?.length ? textByteLength(JSON.stringify(state.currentHiveItems)) : 0;
  const inventorySizeText = health.search_index_size_text || formatBytes(health.search_index_size_bytes || health.search_index_bytes || currentHiveBytes);
  const schedule = beijingInspectionWindow();
  const lastActualFinished = health.daily_automation_finished_at || health.last_finished_at || health.search_index_built_at || "";
  const lastActualAge = health.daily_automation_age_hours ?? health.age_hours;
  const lines = [
    `今日全网检索（北京时间）：08:30 / 11:30 / 17:30 / 21:30 信息抓取；当前窗口：${schedule.label}；下次抓取：${schedule.nextLabel}`,
    `最近实际完成：${formatBeijingDateTime(lastActualFinished, true)}（${formatAgeHours(lastActualAge)}）；服务器原始时区：UTC，页面已换算为北京时间`,
    `Folo 直查源成功：${foloReady}/${foloTotal} 条，成功比例 ${formatRatio(foloRatio)}；仅统计可跳转 Folo 且能高亮定位的条目`,
    `当前卡片：此次新增 ${metrics.totalNew} 条；Folo 新增 ${metrics.foloNewIdCount} 条；Folo源条ID ${foloBaseIdCount}+${metrics.foloNewIdCount} 条；库存总条目 ${inventoryBase}+${metrics.totalNew} 条`,
    `现库存总条目：${inventoryTotal} 条；完成时间：${formatBeijingDateTime(health.search_index_built_at || health.last_finished_at, true)}；总体积容量：${inventorySizeText}`,
    `缓存兜底：${health.cache_fallback_used ? `使用，补入 ${health.cache_fallback_added_count || 0} 条` : "未使用"}；用户级 crontab 每天自动更新四遍 InfoRadar`,
  ];
  if ((health.daily_automation_failed_count || 0) > 0) {
    lines.push(`失败步骤：${(health.daily_automation_failed_commands || []).join("、") || "未记录"}`);
  }
  if ((health.fetch_failed_examples || []).length) {
    lines.push(`失败源示例：${health.fetch_failed_examples.map((item) => `${item.name || "未命名源"}：${item.error || "未记录原因"}`).join("；")}`);
  }
  box.className = `radar-health ${stale ? "stale" : "fresh"}`;
  box.innerHTML = `
    <div class="radar-health-head">${stale ? "数据已过期" : "运行状态"}</div>
    ${lines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}
    <div class="radar-health-note">${escapeHtml("当前只展示可验证的本地运行记录；全网资源自动搜索与 NAS 入库仍是后续自动化。")}</div>
  `;
}

function renderSearchResults(data, append = false) {
  const box = $("#radarSearchResults");
  const meta = $("#radarSearchMeta");
  if (!box || !meta) return;
  const rows = data.results || [];
  const related = (data.related_terms || []).slice(0, 8);
  const relatedText = related.length ? ` · 扩展 ${related.join("、")}` : "";
  const offset = Number(data.offset || 0);
  const limit = Number(data.limit || rows.length || 30);
  const shown = Math.min(Number(data.total || 0), offset + rows.length);
  state.radarSearch = {
    query: data.query || "",
    scope: data.scope || "all",
    offset,
    limit,
    total: Number(data.total || 0),
  };
  const totalText = data.total_is_estimated ? `至少 ${data.total || shown} 条` : `${data.total || 0} 条`;
  meta.textContent = data.query
    ? `关键词：${data.query} · 范围：${data.scope} · 命中 ${totalText} · 已显示 ${shown} 条${relatedText}`
    : "输入关键词后检索本地情报库";
  if (!rows.length) {
    if (!append) {
      box.innerHTML = data.query ? `<div class="item"><div class="item-meta">没有命中本地记录</div></div>` : "";
    }
    return;
  }
  if (append) {
    const oldMore = box.querySelector(".search-more-row");
    if (oldMore) oldMore.remove();
  }
  const html = rows
    .map((item, idx) => {
      const globalIndex = offset + idx;
      const id = locatorId("search", globalIndex);
      storeLocatorItem(id, item);
      const href = item.url || "";
      const foloHref = item.folo_url || "";
      const openLabel = item.kind === "情报" ? "原文核验" : item.kind === "文件" || item.kind === "源池文件" ? "查看文件" : "打开";
      const actions = [
        `<button class="secondary locator-trigger" data-locator="${escapeHtml(id)}" type="button">定位证据</button>`,
        href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${openLabel}</a>` : "",
        foloHref
          ? `<a class="${item.folo_matched ? "folo" : "secondary"}" href="${escapeHtml(foloHref)}" target="_blank" rel="noreferrer">${escapeHtml(item.folo_label || "打开 Folo")}</a>`
          : "",
      ].filter(Boolean).join("");
      const payload = item.payload || {};
      const isIntelLike = String(item.kind || "").includes("情报");
      const timeLabel = isIntelLike ? "发布时间" : item.kind === "文件" || item.kind === "源池文件" ? "文件时间" : "记录时间";
      const rawTimeValue = isIntelLike
        ? (payload.published_at || payload["发布时间"] || "")
        : (payload.published_at || payload["发布时间"] || payload.modified_at || payload.collected_at || payload.detected_at || payload["创建时间"] || "");
      const timeValue = formatBeijingDateTimeLoose(rawTimeValue, true) || rawTimeValue;
      const chips = [item.kind, item.meta, `相关度 ${item.score || "-"}`].filter(Boolean);
      return `
        <article class="search-result-card intel-card">
          <div class="intel-head">
            <div class="intel-index">${escapeHtml(globalIndex + 1)}</div>
            <div class="intel-title">${escapeHtml(item.title)}</div>
          </div>
          <div class="intel-time">
            <span>${escapeHtml(timeLabel)}</span>
            <strong>${escapeHtml(timeValue || "待补充")}</strong>
          </div>
          <div class="badges">
            ${chips.map((chip, chipIndex) => `<span class="badge ${chipIndex === 2 ? "score" : ""}">${escapeHtml(chip)}</span>`).join("")}
          </div>
          <div class="intel-body">
            ${renderStructuredSummary(item.body || "暂无摘要")}
          </div>
          <div class="intel-actions search-actions">${actions}</div>
        </article>
      `;
    })
    .join("");
  const more = data.has_more
    ? `<div class="search-more-row"><button id="radarSearchMoreBtn" class="secondary" type="button">加载更多</button></div>`
    : "";
  if (append) {
    box.insertAdjacentHTML("beforeend", html + more);
  } else {
    box.innerHTML = html + more;
  }
  const moreBtn = $("#radarSearchMoreBtn");
  if (moreBtn) {
    moreBtn.addEventListener("click", () => runRadarSearch(state.radarSearch.query, state.radarSearch.offset + state.radarSearch.limit, true));
  }
}

async function runRadarSearch(query = "", offset = 0, append = false) {
  const input = $("#radarSearchInput");
  const scope = $("#radarSearchScope");
  const mode = $("#radarSearchMode");
  const value = String(query || input?.value || "").trim();
  if (!value) {
    showToast("请输入检索关键词");
    return;
  }
  if (input) input.value = value;
  const meta = $("#radarSearchMeta");
  if (meta) meta.textContent = "检索中...";
  const selectedScope = scope?.value || "all";
  const selectedMode = mode?.value || "smart";
  const data = await api(`/api/search?q=${encodeURIComponent(value)}&scope=${encodeURIComponent(selectedScope)}&mode=${encodeURIComponent(selectedMode)}&limit=30&offset=${Number(offset || 0)}`);
  renderSearchResults(data, append);
}

async function loadLatest() {
  const data = await api("/api/latest");
  state.latest = data;
  state.latestHealth = data.health || {};
  renderFiles("#homeFiles", data.files || [], 8);
  renderRadarHealth();
  return data;
}

async function loadItems(topic = "今日情报") {
  const data = await api(`/api/items?topic=${encodeURIComponent(topic)}&limit=40`);
  state.itemStats = data.stats || {};
  renderIntelCards(data.items || []);
  renderRadarHealth();
  return data;
}

async function loadFiles() {
  const data = await api("/api/files");
  renderFiles("#allFiles", data.files || [], 120);
}

async function loadManualInbox() {
  const data = await api("/api/manual-inbox");
  const rows = data.recent_items || [];
  const top = data.summary ? [{ raw_text: data.summary, platform: "摘要" }, ...rows] : rows;
  renderRows("#manualInbox", top, ["raw_text", "标题", "source_trace_id"], ["platform", "status", "collected_at"]);
}

async function loadWatch() {
  const data = await api("/api/watch");
  const rows = [...((data.updates || []).slice(-8).reverse()), ...((data.requests || []).slice(-8).reverse())];
  renderRows("#watchStatus", rows, ["title", "关键词", "watch_keyword"], ["source_name", "状态", "detected_at", "创建时间"]);
}

async function loadSources() {
  const data = await api("/api/source-pool");
  const webhook = await api("/api/folo/webhook-config").catch((err) => ({ ok: false, error: err.message }));
  renderSourceConsole(data, webhook);
}

function sourceMetric(label, value, hint = "") {
  return `
    <div class="source-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${hint ? `<small>${escapeHtml(hint)}</small>` : ""}
    </div>
  `;
}

function sourceCard(row, mode = "candidate") {
  const title = row["源名称"] || row["Folo订阅源名称"] || row["List名称"] || "未命名源";
  const folder = row["Folo文件夹路径"] || row["推荐Folo文件夹"] || row["broad_category"] || row["source_layer"] || "待定位";
  const rss = row["可抓取RSS链接"] || row["RSS链接"] || row["RSS候选"] || "";
  const site = row["官网链接"] || row["候选URL"] || "";
  const priority = row["订阅优先级"] || row["优先级"] || row["长期价值评分"] || "";
  const note = row["适合你的原因"] || row["推荐原因"] || row["备注"] || row["建议动作"] || "";
  const status = mode === "folo" ? "已在 Folo" : row["是否可被Folo添加"] === "是" ? "可导入" : row["源状态"] || "候选";
  return `
    <article class="source-card ${mode}">
      <div class="source-card-head">
        <div>
          <div class="source-title">${escapeHtml(title)}</div>
          <div class="source-meta">${escapeHtml(folder)} · ${escapeHtml(status)}${priority ? ` · ${escapeHtml(priority)}` : ""}</div>
        </div>
      </div>
      ${note ? `<div class="source-note">${escapeHtml(note)}</div>` : ""}
      <div class="source-actions">
        ${rss ? `<a class="secondary" href="${escapeHtml(rss)}" target="_blank" rel="noreferrer">RSS</a>` : ""}
        ${site ? `<a class="secondary" href="${escapeHtml(site)}" target="_blank" rel="noreferrer">官网</a>` : ""}
      </div>
    </article>
  `;
}

function foloArticleLinkCard(row) {
  const title = row.title || row.original_url || row.folo_article_url || "Folo 原条";
  return `
    <article class="source-card link">
      <div class="source-title">${escapeHtml(title)}</div>
      <div class="source-meta">${escapeHtml(row.source || "来源待补")} · ${escapeHtml(row.created_at || "")}</div>
      <div class="source-actions">
        <a class="folo" href="${escapeHtml(row.folo_article_url || "#")}" target="_blank" rel="noreferrer">打开原条</a>
        ${row.original_url ? `<a class="secondary" href="${escapeHtml(row.original_url)}" target="_blank" rel="noreferrer">原文</a>` : ""}
      </div>
    </article>
  `;
}

function foloWebhookPanel(webhook) {
  const configured = Boolean(webhook?.configured);
  const url = webhook?.webhook_url || "";
  const testFeedUrl = webhook?.test_feed_url || "";
  const status = configured ? "已配置" : "未配置";
  const count = webhook?.article_link_count || 0;
  const exampleBody = `{
  "entry": "[entry]",
  "feed": "[feed]",
  "view": "[view]"
}`;
  return `
    <div class="source-webhook ${configured ? "ready" : "pending"}">
      <div>
        <div class="source-title">Folo Actions Webhook：${escapeHtml(status)}</div>
        <div class="source-meta">原条映射 ${escapeHtml(count)} 条 · 入口必须配置在 Folo Actions / Webhooks，不是普通自定义集成。</div>
      </div>
      <div class="source-webhook-url">${escapeHtml(url || webhook?.target || "等待配置")}</div>
      <div class="source-note">Method 选 POST，请求体需要包含 entry 和 feed；InfoRadar 会读取 entry.id 与 entry.feedId 生成真实 Folo 原条链接。若只能填写 [title]、[url]，只能作为信号回传，不能生成原条深链。</div>
      <pre class="source-webhook-body">${escapeHtml(exampleBody)}</pre>
      ${testFeedUrl ? `<div class="source-note">验证 Feed：把下面地址添加到 Folo 订阅源，然后点“生成新测试条目”，等待 Folo Actions 回传。</div><div class="source-webhook-url">${escapeHtml(testFeedUrl)}</div>` : ""}
      <div class="source-actions">
        <button class="secondary copy-webhook-url" type="button" ${url ? "" : "disabled"}>复制 Webhook URL</button>
        <button class="secondary copy-test-feed-url" type="button" ${testFeedUrl ? "" : "disabled"}>复制测试 Feed</button>
        <button class="secondary bump-test-feed" type="button" ${testFeedUrl ? "" : "disabled"}>生成新测试条目</button>
        <a class="secondary" href="https://github.com/RSSNext/Folo/wiki/Actions" target="_blank" rel="noreferrer">Folo Actions</a>
      </div>
    </div>
  `;
}

function renderSourceConsole(data, webhook = {}) {
  const box = $("#sourcePool");
  if (!box) return;
  const latestOpml = data.latest_opml || {};
  const links = (data.folo_article_links || []).slice(0, 8);
  const importReady = (data.import_ready_sources || []).slice(0, 10);
  const broad = (data.broad_candidates || []).slice(0, 10);
  const foloSources = (data.folo_sources || []).slice(0, 10);
  box.innerHTML = `
    ${foloWebhookPanel(webhook)}
    <div class="source-metric-grid">
      ${sourceMetric("Folo 已有源", data.folo_source_count || 0, "来自当前订阅导出")}
      ${sourceMetric("可导入源", data.import_ready_count || 0, "已有 RSS，可生成 OPML")}
      ${sourceMetric("广域候选", data.broad_candidate_count || 0, "公众号/视频/政务/学校等预备")}
      ${sourceMetric("Folo 原条映射", data.folo_article_link_count || 0, "真实 feedId/entryId")}
    </div>
    <div class="source-section">
      <div class="source-section-head">
        <strong>Folo 回传原条</strong>
        <span>只有这里有记录，卡片才会亮真实 Folo 原条链接</span>
      </div>
      <div class="source-card-grid">${links.length ? links.map(foloArticleLinkCard).join("") : `<div class="item"><div class="item-meta">暂无 Folo 原条回传；需要在 Folo 配置 webhook 后自动积累。</div></div>`}</div>
    </div>
    <div class="source-section">
      <div class="source-section-head">
        <strong>可导入 Folo</strong>
        <span>${latestOpml.name ? `最新 OPML：${latestOpml.name}` : "尚未生成 OPML"}</span>
      </div>
      <div class="source-card-grid">${importReady.length ? importReady.map((row) => sourceCard(row, "candidate")).join("") : `<div class="item"><div class="item-meta">暂无已探测 RSS 的候选源。</div></div>`}</div>
    </div>
    <div class="source-section">
      <div class="source-section-head">
        <strong>广域候选</strong>
        <span>先进入候选和监控，探测到稳定 RSS 后再导入 Folo</span>
      </div>
      <div class="source-card-grid">${broad.length ? broad.map((row) => sourceCard(row, "broad")).join("") : `<div class="item"><div class="item-meta">暂无广域候选。</div></div>`}</div>
    </div>
    <div class="source-section">
      <div class="source-section-head">
        <strong>当前 Folo 源样本</strong>
        <span>完整清单在文件区，可打开 Excel/CSV 核验</span>
      </div>
      <div class="source-card-grid">${foloSources.length ? foloSources.map((row) => sourceCard(row, "folo")).join("") : `<div class="item"><div class="item-meta">暂无 Folo 源池导出，请先同步 Folo 源池。</div></div>`}</div>
    </div>
    <div class="source-section">
      <div class="source-section-head">
        <strong>源池文件</strong>
        <span>OPML、源池、验收报告和 RSS 健康检查</span>
      </div>
      <div class="file-list">${sourceFilesHtml(data.files || [], 30)}</div>
    </div>
  `;
  box.querySelector(".copy-webhook-url")?.addEventListener("click", async () => {
    const url = webhook?.webhook_url || "";
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      showToast("Webhook URL 已复制");
    } catch (_) {
      showToast("复制失败，请手动选中 URL");
    }
  });
  box.querySelector(".copy-test-feed-url")?.addEventListener("click", async () => {
    const url = webhook?.test_feed_url || "";
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      showToast("测试 Feed 已复制");
    } catch (_) {
      showToast("复制失败，请手动选中 URL");
    }
  });
  box.querySelector(".bump-test-feed")?.addEventListener("click", async () => {
    try {
      await api("/api/folo/test-feed/bump", { method: "POST" });
      showToast("已生成新测试条目，等待 Folo 抓取并触发 Actions");
      await loadSources();
    } catch (err) {
      showToast(`生成测试条目失败：${err.message}`);
    }
  });
}

function sourceFilesHtml(files, limit = 30) {
  const rows = (files || []).slice(0, limit);
  if (!rows.length) return `<div class="item"><div class="item-meta">暂无文件</div></div>`;
  return rows
    .map(
      (file) => `
        <div class="item">
          <div class="item-title">${escapeHtml(file.name)}</div>
          <div class="item-meta">${escapeHtml(file.category)} · ${escapeHtml(file.size_text)} · ${escapeHtml(file.modified_at)}</div>
          <div class="item-actions">
            <a href="${fileUrl(file.path)}" target="_blank" rel="noreferrer">打开</a>
            <a href="${fileUrl(file.path, true)}" target="_blank" rel="noreferrer">下载</a>
          </div>
        </div>
      `
    )
    .join("");
}

async function loadAgentHub() {
  const data = await api("/api/agenthub");
  if (data.ok) {
    renderAgentHub(data);
  } else {
    $("#taskBoard").innerHTML = `<div class="item"><div class="item-meta">${escapeHtml(data.error || "AgentHub 未连接")}</div></div>`;
    $("#agentStatus").innerHTML = `<div class="item"><div class="item-meta">等待 AgentHub 初始化</div></div>`;
  }
}

function serviceChip(label, ok, detail = "") {
  const cls = ok ? "ok" : detail ? "warn" : "off";
  return `
    <div class="service-chip ${cls}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(ok ? "在线" : detail ? "注意" : "未检测")}</strong>
      ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
    </div>
  `;
}

function renderCodexWorkstation(data) {
  state.codex = data;
  const statusPill = $("#codexStatusPill");
  if (statusPill) {
    statusPill.textContent = "codex exec ready";
    statusPill.className = `status-pill ${data.status === "online" ? "ok" : data.status === "partial" ? "warn" : "off"}`;
  }
  renderCodexConversations(data);
  renderCodexLogs(data.logs || []);
}

function renderCodexConversations(data) {
  const rail = $(".codex-conversation-rail");
  if (!rail) return;
  const sessions = data.session_cards?.length
    ? data.session_cards
    : [
        { id: "codex", name: "主 Codex", role: "默认交互会话", status: "reserved", tmux_session: "codex" },
        { id: "codex-research", name: "研究会话", role: "资料检索和方案沉淀", status: "reserved", tmux_session: "codex-research" },
        { id: "codex-build", name: "构建会话", role: "构建、发布、服务维护", status: "reserved", tmux_session: "codex-build" },
        { id: "codex-qa", name: "日志/测试", role: "验收、日志、回归检查", status: "reserved", tmux_session: "codex-qa" },
      ];

  if (!sessions.some((item) => item.id === state.codexSession)) {
    state.codexSession = sessions[0]?.id || "codex";
  }

  rail.innerHTML = `
    <div class="rail-title">对话</div>
    ${sessions
      .map((item) => {
        const id = item.id || item.tmux_session || "codex";
        const online = item.status === "online";
        const active = id === state.codexSession;
        const displayName = codexSessionDisplayName(id, item.name || id);
        const role = item.role || item.tmux_session || id;
        return `
          <article class="conversation-item ${active ? "active" : ""} ${online ? "online" : "reserved"}" data-codex-session="${escapeHtml(id)}" role="button" tabindex="0">
            <div class="conversation-title-row">
              <strong>${escapeHtml(displayName)}</strong>
              <button class="conversation-rename" data-codex-rename-session="${escapeHtml(id)}" type="button" title="重命名这个会话">重命名</button>
            </div>
            <span>${escapeHtml(role)}</span>
            <small>${escapeHtml(online ? "在线" : "点击启动")}</small>
          </article>
        `;
      })
      .join("")}
  `;
}

function renderCodexTerminal(payload) {
  const output = $("#codexTerminalOutput");
  const status = $("#codexTerminalStatus");
  if (!output || !status) return;
  const session = payload?.session || state.codexSession || "codex";
  state.codexSession = session;
  $$(".conversation-item[data-codex-session]").forEach((item) => {
    item.classList.toggle("active", item.dataset.codexSession === session);
  });
  output.textContent = payload?.ok
    ? payload.output || "浏览器 Codex 会话暂无消息。输入内容后按 Enter 发送。"
    : payload?.error || `Codex exec:${session} 暂时不可用`;
  output.scrollTop = output.scrollHeight;
  const command = payload?.pane_command ? ` / ${payload.pane_command}` : "";
  const source = payload?.source === "codex-exec-web" ? "浏览器直连 Codex exec" : `Codex exec:${session}`;
  const jobStatus = payload?.job_status ? ` · ${payload.job_status}` : "";
  status.textContent = payload?.ok ? `${source}${command}${jobStatus}` : `Codex exec:${session} 暂时不可用`;
}

function renderCodexTerminalError(error) {
  const output = $("#codexTerminalOutput");
  const status = $("#codexTerminalStatus");
  if (output) output.textContent = error?.message || "读取 Codex 聊天失败";
  if (status) status.textContent = `Codex exec:${state.codexSession} 读取失败`;
}

function openClawPolicyLabel(policy) {
  const map = { now: "立即", queue: "排队", hold: "主管待定" };
  return map[policy] || "立即";
}

function openClawSessionLabel(session) {
  return codexSessionDisplayName(session || "codex", session || "codex");
}

function openClawNowLabel() {
  return new Date().toLocaleString("zh-CN", { hour12: false });
}

function normalizeOpenClawTarget(value) {
  return String(value || "")
    .trim()
    .replace(/^\/+/, "")
    .replace(/\s+/g, "-")
    .toLowerCase();
}

function openClawTargetValid(target) {
  return /^[a-z][a-z0-9_-]{1,31}$/.test(target || "");
}

function openClawTargetRows() {
  const custom = state.openclawTargets || [];
  const rows = OPENCLAW_BASE_TARGETS.map((target) => ({
    target,
    label: target,
    purpose: target === "codexapp" ? "默认微信入口" : `固定 ${target} 会话`,
    builtIn: true,
  }));
  custom.forEach((item) => {
    const target = normalizeOpenClawTarget(item.target || item.name);
    if (!target || rows.some((row) => row.target === target)) return;
    rows.push({ ...item, target, label: item.label || target, builtIn: false });
  });
  return rows;
}

function upsertOpenClawTarget(target, purpose = "", label = "") {
  const normalized = normalizeOpenClawTarget(target);
  if (!openClawTargetValid(normalized)) {
    throw new Error("新指令通道只支持 2-32 位英文、数字、下划线或短横线，且必须以英文字母开头");
  }
  if (OPENCLAW_BASE_TARGETS.includes(normalized)) return { target: normalized, builtIn: true };
  const rows = (state.openclawTargets || []).filter((item) => normalizeOpenClawTarget(item.target || item.name) !== normalized);
  const item = {
    target: normalized,
    label: label || normalized,
    purpose: String(purpose || "").trim(),
    created_at: new Date().toISOString(),
    last_check: null,
  };
  state.openclawTargets = [item, ...rows].slice(0, 32);
  saveOpenClawTargets(state.openclawTargets);
  return item;
}

function renderOpenClawTargets(selected = $("#openclawTarget")?.value || "codexapp1") {
  const select = $("#openclawTarget");
  if (!select) return;
  const rows = openClawTargetRows();
  select.innerHTML = rows
    .map((item) => `<option value="${escapeHtml(item.target)}">${escapeHtml(item.label || item.target)}${item.purpose ? ` · ${escapeHtml(item.purpose)}` : ""}</option>`)
    .join("");
  select.value = rows.some((item) => item.target === selected) ? selected : "codexapp1";
  const count = $("#openclawTargetCount");
  if (count) count.textContent = String(rows.length);
}

function openClawDraftFromForm() {
  const customTarget = normalizeOpenClawTarget($("#openclawCustomTarget")?.value || "");
  const selectedTarget = normalizeOpenClawTarget($("#openclawTarget")?.value || "codexapp1");
  return {
    id: `cmd-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 7)}`,
    name: ($("#openclawCommandName")?.value || "未命名指令").trim() || "未命名指令",
    target: customTarget || selectedTarget || "codexapp1",
    policy: $("#openclawPolicy")?.value || "hold",
    session: $("#openclawSession")?.value || "codex",
    prompt: ($("#openclawPrompt")?.value || "").trim(),
    purpose: ($("#openclawPurpose")?.value || "").trim(),
  };
}

function openClawSlashCommand(item) {
  const target = String(item?.target || "codexapp1").replace(/^\/+/, "");
  const policy = item?.policy || "hold";
  const prompt = String(item?.prompt || "").replace(/\s+/g, " ").trim();
  return `/${target} ${policy}${prompt ? ` ${prompt}` : ""}`.trim();
}

function openClawCodexInstruction(item) {
  const slash = openClawSlashCommand(item);
  return [
    "来自 Mana Hub 微信命令中心的任务。",
    `快捷指令：${item.name || "未命名指令"}`,
    `指令通道：/${item.target || "codexapp1"}`,
    `功能说明：${item.purpose || "未填写"}`,
    `微信命令：${slash}`,
    `调度策略：${openClawPolicyLabel(item.policy)}；目标：/${item.target || "codexapp1"}`,
    "",
    "请在当前 Codex 已授权可访问范围内完成对应任务。",
    "如果任务需要投递到微信/OpenClaw，只生成可执行命令和验收步骤；不要输出 token、Cookie、API Key 或私密凭证。",
  ].join("\n");
}

function renderOpenClawPreview() {
  const preview = $("#openclawCommandPreview");
  if (!preview) return;
  const draft = openClawDraftFromForm();
  preview.textContent = draft.prompt ? openClawSlashCommand(draft) : `/${draft.target} ${draft.policy} <任务内容>`;
}

function renderOpenClawSelfCheckLog(lines = null) {
  const box = $("#openclawSelfCheckLog");
  if (!box) return;
  const current = lines || state.openclawSelfCheckLogs || [];
  box.textContent = current.length ? current.join("\n") : "等待自检。保存新通道或执行任务前会先做红绿联通性测试。";
}

function setOpenClawSelfCheckLog(lines) {
  state.openclawSelfCheckLogs = lines.slice(-80);
  saveOpenClawSelfCheckLogs(state.openclawSelfCheckLogs);
  renderOpenClawSelfCheckLog(state.openclawSelfCheckLogs);
}

function appendOpenClawSelfCheckLog(line) {
  setOpenClawSelfCheckLog([...(state.openclawSelfCheckLogs || []), line]);
}

async function openClawSelfCheck(item, options = {}) {
  const draft = item || openClawDraftFromForm();
  const target = normalizeOpenClawTarget(draft.target || "");
  const session = draft.session || "codex";
  const lines = [`== OpenClaw 自检 ${openClawNowLabel()} ==`];
  let ok = true;
  const add = (pass, name, detail) => {
    ok = ok && pass;
    lines.push(`${pass ? "[GREEN]" : "[RED]"} ${name} :: ${detail}`);
    renderOpenClawSelfCheckLog(lines);
  };

  add(openClawTargetValid(target), "指令通道名称", target || "空");
  add(Boolean(draft.purpose || OPENCLAW_BASE_TARGETS.includes(target)), "功能说明", draft.purpose || "固定通道可不填");
  add(!options.requirePrompt || Boolean(draft.prompt), "指令内容", draft.prompt ? `${draft.prompt.length} 字` : "空");
  add(Boolean(session), "网页执行会话", openClawSessionLabel(session));

  if (ok) {
    try {
      const health = await api("/api/health");
      add(Boolean(health?.ok), "Mana Hub API", health?.service || JSON.stringify(health));
    } catch (err) {
      add(false, "Mana Hub API", err.message);
    }
  }

  if (ok) {
    try {
      const params = new URLSearchParams({ session, lines: "40" });
      const data = await api(`/api/codex-terminal?${params.toString()}`);
      add(Boolean(data?.ok), "Codex 会话读取", `${data?.session || session} · ${data?.entry_count ?? 0} 条缓存`);
    } catch (err) {
      add(false, "Codex 会话读取", err.message);
    }
  }

  if (ok) {
    try {
      upsertOpenClawTarget(target, draft.purpose, target);
      renderOpenClawTargets(target);
      add(true, "微信会话下拉框", `已登记 /${target}`);
    } catch (err) {
      add(false, "微信会话下拉框", err.message);
    }
  }

  lines.push(`${ok ? "[RESULT] PASS" : "[RESULT] FAIL"} ${openClawNowLabel()}`);
  setOpenClawSelfCheckLog(lines);
  return { ok, lines, target, session };
}

function openClawCommandById(id) {
  return state.openclawCommands.find((item) => item.id === id);
}

function renderOpenClawCommandCenter() {
  const list = $("#openclawCommandList");
  if (!list) return;
  const rows = state.openclawCommands || [];
  renderOpenClawTargets();
  $("#openclawSavedCount").textContent = String(rows.length);
  $("#openclawPolicyCount").textContent = "3";
  list.innerHTML = rows.length
    ? rows
        .map((item) => {
          const slash = openClawSlashCommand(item);
          return `
            <article class="openclaw-command-item">
              <div>
                <div class="item-title">${escapeHtml(item.name || "未命名指令")}</div>
                <div class="item-meta">
                  /${escapeHtml(item.target || "codexapp1")} · ${escapeHtml(openClawPolicyLabel(item.policy))} · ${escapeHtml(openClawSessionLabel(item.session))}${item.purpose ? ` · ${escapeHtml(item.purpose)}` : ""}
                </div>
                <code>${escapeHtml(slash)}</code>
              </div>
              <div class="openclaw-command-actions">
                <button class="ghost small" data-openclaw-copy="${escapeHtml(item.id)}" type="button">复制</button>
                <button class="small" data-openclaw-run="${escapeHtml(item.id)}" type="button">执行</button>
                <button class="ghost small" data-openclaw-edit="${escapeHtml(item.id)}" type="button">编辑</button>
                <button class="ghost small" data-openclaw-delete="${escapeHtml(item.id)}" type="button">删除</button>
              </div>
            </article>
          `;
        })
        .join("")
    : `<div class="item">暂无快捷指令</div>`;
  renderOpenClawSelfCheckLog();
  renderOpenClawPreview();
}

function fillOpenClawForm(item) {
  if (!item) return;
  $("#openclawCommandName").value = item.name || "";
  renderOpenClawTargets(item.target || "codexapp1");
  $("#openclawTarget").value = item.target || "codexapp1";
  $("#openclawPolicy").value = item.policy || "hold";
  $("#openclawSession").value = item.session || "codex";
  $("#openclawPrompt").value = item.prompt || "";
  $("#openclawCustomTarget").value = OPENCLAW_BASE_TARGETS.includes(item.target || "") ? "" : item.target || "";
  $("#openclawPurpose").value = item.purpose || "";
  renderOpenClawPreview();
}

async function saveOpenClawCommandFromForm() {
  const draft = openClawDraftFromForm();
  if (!draft.prompt) {
    showToast("指令内容不能为空");
    return;
  }
  const check = await openClawSelfCheck(draft, { requirePrompt: true });
  if (!check.ok) {
    showToast("自检未通过，已停止保存");
    return;
  }
  state.openclawCommands = [draft, ...state.openclawCommands.filter((item) => item.name !== draft.name)].slice(0, 24);
  saveOpenClawCommands(state.openclawCommands);
  renderOpenClawCommandCenter();
  showToast(`快捷指令已保存，/${check.target} 已加入微信会话`);
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

function renderOpenClawResult(text) {
  const box = $("#openclawCommandResult");
  if (box) box.textContent = text || "等待执行";
}

async function runOpenClawCommand(item) {
  if (!item?.prompt) {
    showToast("指令内容不能为空");
    return;
  }
  const check = await openClawSelfCheck(item, { requirePrompt: true });
  if (!check.ok) {
    renderOpenClawResult((check.lines || []).join("\n"));
    showToast("自检未通过，已停止执行");
    return;
  }
  const session = item.session || "codex";
  renderOpenClawResult(`${(check.lines || []).join("\n")}\n\n正在发送到 ${openClawSessionLabel(session)}...\n\n${openClawCodexInstruction(item)}`);
  const data = await api("/api/codex-terminal/send", {
    method: "POST",
    body: JSON.stringify({ session, message: openClawCodexInstruction(item) }),
  });
  renderOpenClawResult(data.output || `任务已提交：${data.job_id || ""}\n状态：${data.job_status || "queued"}`);
  if (data?.job_id && !codexTerminalJobDone(data?.job_status)) {
    await followOpenClawCommandJob(data.job_id, session);
  }
}

async function followOpenClawCommandJob(jobId, session) {
  const deadline = Date.now() + CODEX_TERMINAL_FOLLOW_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 800));
    const data = await api(`/api/codex-terminal/job/${encodeURIComponent(jobId)}?${new URLSearchParams({ session })}`);
    renderOpenClawResult(data.output || `任务状态：${data.job_status || "running"}`);
    if (codexTerminalJobDone(data?.job_status)) return;
  }
  showToast("执行跟随已超时，可到 Codex 工作站查看结果");
}

function renderCodexLogs(logs) {
  state.codexLogs = logs;
  const tabs = $("#codexLogTabs");
  const output = $("#codexLogOutput");
  if (!logs.length) {
    tabs.innerHTML = "";
    output.textContent = "暂无日志";
    return;
  }
  tabs.innerHTML = logs
    .map((item, index) => `<button class="${index === 0 ? "active" : ""}" data-codex-log="${index}" type="button">${escapeHtml(item.name || `log-${index + 1}`)}</button>`)
    .join("");
  const first = logs[0];
  output.textContent = first.exists ? (first.lines || []).join("\n") || "日志为空" : first.error || "日志文件不存在";
}

async function loadCodexWorkstation() {
  const data = await api("/api/codex-workstation");
  renderCodexWorkstation(data);
}

async function loadCodexTerminal(session = state.codexSession, start = false) {
  if (state.codexTerminalLoading || state.codexTerminalSending) return null;
  state.codexTerminalLoading = true;
  state.codexSession = session || "codex";
  const status = $("#codexTerminalStatus");
  if (status) status.textContent = `正在读取 Codex exec 会话:${state.codexSession}...`;
  try {
    const params = new URLSearchParams({ session: state.codexSession, lines: "220" });
    if (start) params.set("start", "true");
    const data = await api(`/api/codex-terminal?${params.toString()}`);
    renderCodexTerminal(data);
    return data;
  } finally {
    state.codexTerminalLoading = false;
  }
}

function codexTerminalJobDone(status) {
  return ["done", "error", "timeout"].includes(String(status || ""));
}

function stopCodexTerminalFollow() {
  state.codexTerminalFollowActive = false;
  state.codexTerminalFollowToken = "";
  state.codexTerminalFollowSignature = "";
  state.codexTerminalFollowStableTicks = 0;
  state.codexTerminalFollowDeadline = 0;
}

async function loadCodexTerminalJob(jobId, session = state.codexSession) {
  const params = new URLSearchParams({ session: session || "codex" });
  const data = await api(`/api/codex-terminal/job/${encodeURIComponent(jobId)}?${params.toString()}`);
  renderCodexTerminal(data);
  return data;
}

function startCodexTerminalFollow(jobId, session = state.codexSession) {
  if (!jobId) return;
  const token = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.codexTerminalFollowActive = true;
  state.codexTerminalFollowToken = token;
  state.codexTerminalFollowSignature = "";
  state.codexTerminalFollowStableTicks = 0;
  state.codexTerminalFollowDeadline = Date.now() + CODEX_TERMINAL_FOLLOW_TIMEOUT_MS;

  const tick = async () => {
    if (!state.codexTerminalFollowActive || state.codexTerminalFollowToken !== token) return;
    if (Date.now() > state.codexTerminalFollowDeadline) {
      const status = $("#codexTerminalStatus");
      if (status) status.textContent = "Codex 回复跟随已超时停止，可点刷新会话查看最新状态";
      stopCodexTerminalFollow();
      return;
    }
    try {
      const data = await loadCodexTerminalJob(jobId, session);
      const signature = `${data?.job_status || ""}:${data?.output || ""}`;
      if (signature === state.codexTerminalFollowSignature) {
        state.codexTerminalFollowStableTicks += 1;
      } else {
        state.codexTerminalFollowSignature = signature;
        state.codexTerminalFollowStableTicks = 0;
      }
      if (codexTerminalJobDone(data?.job_status)) {
        stopCodexTerminalFollow();
        return;
      }
      window.setTimeout(tick, CODEX_TERMINAL_FOLLOW_INTERVAL_MS);
    } catch (err) {
      showToast(err.message);
      stopCodexTerminalFollow();
    }
  };

  window.setTimeout(tick, CODEX_TERMINAL_FOLLOW_INTERVAL_MS);
}

async function sendCodexTerminal(message) {
  const text = String(message || "").trim();
  if (!text) {
    showToast("消息不能为空");
    return;
  }
  stopCodexTerminalFollow();
  const input = $("#codexTerminalInput");
  const button = $("#sendCodexTerminalBtn");
  const status = $("#codexTerminalStatus");
  state.codexTerminalSending = true;
  if (button) button.disabled = true;
  if (status) status.textContent = `正在创建 Codex 任务:${state.codexSession}...`;
  try {
    const data = await api("/api/codex-terminal/send", {
      method: "POST",
      body: JSON.stringify({ session: state.codexSession, message: text }),
    });
    if (input) input.value = "";
    renderCodexTerminal(data);
    if (data?.job_id && !codexTerminalJobDone(data?.job_status)) {
      startCodexTerminalFollow(data.job_id, data.session || state.codexSession);
    }
  } finally {
    state.codexTerminalSending = false;
    if (button) button.disabled = false;
  }
}

async function loadCodexWorkspace() {
  const [workstation, terminal] = await Promise.allSettled([
    api("/api/codex-workstation"),
    loadCodexTerminal(state.codexSession, false),
  ]);
  if (workstation.status === "fulfilled") {
    renderCodexWorkstation(workstation.value);
  } else {
    showToast(workstation.reason?.message || "Codex 工作站状态读取失败");
  }
  if (terminal.status === "rejected") {
    renderCodexTerminalError(terminal.reason);
  }
}

async function refreshWorkspace() {
  await Promise.allSettled([loadAgentHub(), loadLatest(), loadItems(), loadFiles(), loadManualInbox(), loadManualHiveEntries(), loadCollectorAdapters(), loadWatch(), loadSources(), loadResourceHive(), loadFoloSourceTimeline(), loadCodexWorkstation()]);
}

async function checkSession() {
  const data = await api("/api/session");
  state.authenticated = Boolean(data.authenticated);
  state.protected = Boolean(data.protected);
  state.totpRequired = Boolean(data.totp_required);
  state.tabBound = Boolean(data.tab_bound);
  $("#lockStatus").textContent = data.protected ? (data.authenticated ? "已解锁，7 天内保持登录" : "需要口令和动态码") : "服务端未配置口令，已拒绝开放";
  return data;
}

async function unlock(token, totp = "") {
  const data = await api("/api/session", {
    method: "POST",
    body: JSON.stringify({ token, totp }),
  });
  state.authenticated = Boolean(data.authenticated);
  if (data.tab_nonce) setTabNonce(data.tab_nonce);
  $("#unlockError").textContent = "";
  setAppVisible(true);
  $("#healthLine").textContent = "本机服务正常";
  await refreshWorkspace();
}

async function lock() {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  setTabNonce("");
  clearLegacyAuthState();
  state.authenticated = false;
  setAppVisible(false);
  $("#unlockPassword").value = "";
  $("#unlockTotp").value = "";
  $("#lockStatus").textContent = "已锁定";
}

async function runCommand(command) {
  const trimmed = String(command || "").trim();
  if (!trimmed) {
    showToast("命令不能为空");
    return;
  }
  $("#commandResult").textContent = "执行中...";
  const data = await api("/api/command", {
    method: "POST",
    body: JSON.stringify({ command: trimmed }),
  });
  $("#commandResult").textContent = data.summary || data.stdout || data.error || "已执行";
  if (!data.ok) showToast(data.error || "执行失败");
  await refreshWorkspace();
}

function bindNavigation() {
  $$(".tabs button").forEach((button) => {
    button.addEventListener("click", async () => {
      const view = button.dataset.view;
      $$(".tabs button").forEach((item) => item.classList.toggle("active", item === button));
      $$(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
      if (view === "files") await loadFiles().catch((err) => showToast(err.message));
      if (view === "inbox") await loadManualInbox().catch((err) => showToast(err.message));
      if (view === "watch") await loadWatch().catch((err) => showToast(err.message));
      if (view === "sources") await loadSources().catch((err) => showToast(err.message));
    });
  });
}

function bindProjectShell() {
  $("#backHubBtn")?.addEventListener("click", () => {
    setRoute("hub");
    showToast("已返回 Mana Hub");
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-route]");
    if (!button) return;
    setRoute(button.dataset.route || "hub");
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-scroll]");
    if (!button) return;
    const target = $(button.dataset.scroll || "");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  document.addEventListener("click", (event) => {
    const locator = event.target.closest("[data-locator]");
    if (locator) {
      openLocator(locator.dataset.locator || "");
      return;
    }
  });
  $("#locatorCloseBtn")?.addEventListener("click", () => {
    $("#locatorPanel")?.classList.add("hidden");
  });
  document.addEventListener("click", (event) => {
    const card = event.target.closest(".agent-status-card[data-agent-id]");
    if (!card) return;
    selectAgent(card.dataset.agentId || "", true);
  });
  document.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const card = event.target.closest(".agent-status-card[data-agent-id]");
    if (!card) return;
    event.preventDefault();
    selectAgent(card.dataset.agentId || "", true);
  });
  window.addEventListener("hashchange", () => {
    const route =
      location.hash === "#agenthub"
        ? "agenthub"
        : location.hash === "#inforadar"
          ? "inforadar"
          : location.hash === "#codex"
            ? "codex"
            : location.hash === "#openclaw"
              ? "openclaw"
              : "hub";
    setRoute(route, false);
  });
}

function startAgentHubLiveRefresh() {
  if (state.agentRefreshTimer) {
    window.clearInterval(state.agentRefreshTimer);
  }
  state.agentRefreshTimer = window.setInterval(() => {
    const appHidden = $("#appShell")?.classList.contains("hidden");
    if (!state.authenticated || appHidden || location.hash !== "#agenthub") return;
    loadAgentHub().catch((err) => showToast(err.message));
  }, 15000);
}

function startCodexTerminalRefresh() {
  if (state.codexTerminalTimer) {
    window.clearInterval(state.codexTerminalTimer);
  }
  state.codexTerminalTimer = null;
}

function bindCodexTerminal() {
  $("#refreshCodexTerminalBtn")?.addEventListener("click", () => {
    loadCodexTerminal(state.codexSession, true).catch((err) => showToast(err.message));
  });
  $("#sendCodexTerminalBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    sendCodexTerminal($("#codexTerminalInput")?.value || "").catch((err) => showToast(err.message));
  });
  $("#codexTerminalForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendCodexTerminal($("#codexTerminalInput")?.value || "").catch((err) => showToast(err.message));
  });
  $("#codexTerminalInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCodexTerminal(event.currentTarget.value).catch((err) => showToast(err.message));
    }
  });
  document.addEventListener("click", (event) => {
    const renameButton = event.target.closest("button[data-codex-rename-session]");
    if (renameButton) {
      const session = renameButton.dataset.codexRenameSession || "codex";
      const current = codexSessionDisplayName(session, session);
      const next = window.prompt("给这个 Codex 会话改个名字：", current);
      if (next === null) return;
      const trimmed = next.trim();
      if (!trimmed) {
        delete state.codexSessionNames[session];
      } else {
        state.codexSessionNames[session] = trimmed.slice(0, 32);
      }
      saveCodexSessionNames(state.codexSessionNames);
      renderCodexConversations(state.codex || {});
      showToast(trimmed ? "会话已重命名" : "已恢复默认名称");
      return;
    }

    const item = event.target.closest(".conversation-item[data-codex-session]");
    if (!item) return;
    state.codexSession = item.dataset.codexSession || "codex";
    $$(".conversation-item[data-codex-session]").forEach((entry) => entry.classList.toggle("active", entry === item));
    loadCodexTerminal(state.codexSession, true).catch((err) => showToast(err.message));
  });
  document.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const item = event.target.closest(".conversation-item[data-codex-session]");
    if (!item) return;
    event.preventDefault();
    state.codexSession = item.dataset.codexSession || "codex";
    $$(".conversation-item[data-codex-session]").forEach((entry) => entry.classList.toggle("active", entry === item));
    loadCodexTerminal(state.codexSession, true).catch((err) => showToast(err.message));
  });
}

function bindOpenClawCommandCenter() {
  $("#openclawCommandForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    saveOpenClawCommandFromForm().catch((err) => {
      renderOpenClawResult(err.message);
      showToast(err.message);
    });
  });
  ["openclawCommandName", "openclawTarget", "openclawCustomTarget", "openclawPurpose", "openclawPolicy", "openclawSession", "openclawPrompt"].forEach((id) => {
    const input = $(`#${id}`);
    input?.addEventListener("input", renderOpenClawPreview);
    input?.addEventListener("change", renderOpenClawPreview);
  });
  $("#openclawCopyCurrentBtn")?.addEventListener("click", () => {
    copyText(openClawSlashCommand(openClawDraftFromForm()))
      .then(() => showToast("微信命令已复制"))
      .catch((err) => showToast(err.message));
  });
  $("#openclawSelfCheckBtn")?.addEventListener("click", () => {
    openClawSelfCheck(openClawDraftFromForm(), { requirePrompt: true })
      .then((result) => showToast(result.ok ? "OpenClaw 自检通过" : "OpenClaw 自检未通过"))
      .catch((err) => {
        appendOpenClawSelfCheckLog(`[RED] 自检异常 :: ${err.message}`);
        showToast(err.message);
      });
  });
  $("#openclawRunCurrentBtn")?.addEventListener("click", () => {
    runOpenClawCommand(openClawDraftFromForm()).catch((err) => {
      renderOpenClawResult(err.message);
      showToast(err.message);
    });
  });
  document.addEventListener("click", (event) => {
    const presetButton = event.target.closest("button[data-openclaw-preset]");
    if (presetButton) {
      fillOpenClawForm(OPENCLAW_COMMAND_PRESETS[Number(presetButton.dataset.openclawPreset || 0)]);
      return;
    }

    const copyButton = event.target.closest("button[data-openclaw-copy]");
    if (copyButton) {
      const item = openClawCommandById(copyButton.dataset.openclawCopy || "");
      copyText(openClawSlashCommand(item))
        .then(() => showToast("微信命令已复制"))
        .catch((err) => showToast(err.message));
      return;
    }

    const runButton = event.target.closest("button[data-openclaw-run]");
    if (runButton) {
      runOpenClawCommand(openClawCommandById(runButton.dataset.openclawRun || "")).catch((err) => {
        renderOpenClawResult(err.message);
        showToast(err.message);
      });
      return;
    }

    const editButton = event.target.closest("button[data-openclaw-edit]");
    if (editButton) {
      fillOpenClawForm(openClawCommandById(editButton.dataset.openclawEdit || ""));
      return;
    }

    const deleteButton = event.target.closest("button[data-openclaw-delete]");
    if (deleteButton) {
      const id = deleteButton.dataset.openclawDelete || "";
      state.openclawCommands = state.openclawCommands.filter((item) => item.id !== id);
      saveOpenClawCommands(state.openclawCommands);
      renderOpenClawCommandCenter();
      showToast("快捷指令已删除");
    }
  });
}

function bindCommands() {
  document.addEventListener("click", async (event) => {
    const logButton = event.target.closest("button[data-codex-log]");
    if (logButton) {
      const index = Number(logButton.dataset.codexLog || 0);
      $$("#codexLogTabs button").forEach((button) => button.classList.toggle("active", button === logButton));
      const log = state.codexLogs[index];
      $("#codexLogOutput").textContent = log?.exists ? (log.lines || []).join("\n") || "日志为空" : log?.error || "日志文件不存在";
      return;
    }

    const button = event.target.closest("button[data-command]");
    if (!button) return;
    button.disabled = true;
    try {
      await runCommand(button.dataset.command);
    } catch (err) {
      if (err.status === 401) {
        showToast("需要先解锁");
        $("#unlockError").textContent = "需要先输入口令";
        setAppVisible(false);
      } else {
        showToast(err.message);
      }
      $("#commandResult").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });

  $("#runCommandBtn").addEventListener("click", () => runCommand($("#commandInput").value).catch((err) => showToast(err.message)));
  $("#collectBtn").addEventListener("click", () => {
    const platform = $("#collectPlatform").value;
    const text = $("#collectText").value.trim();
    return runCommand(`收集 ${platform} ${text}`).catch((err) => showToast(err.message));
  });
  $("#watchAddBtn").addEventListener("click", () => {
    const keyword = $("#watchInput").value.trim();
    return runCommand(`/watch ${keyword}`).catch((err) => showToast(err.message));
  });
  $("#refreshCodexBtn")?.addEventListener("click", () => loadCodexWorkstation().catch((err) => showToast(err.message)));
  $("#lockBtn").addEventListener("click", () => lock().catch((err) => showToast(err.message)));
}

function bindRadarSearch() {
  const input = $("#radarSearchInput");
  const button = $("#radarSearchBtn");
  if (!input || !button) return;
  button.addEventListener("click", () => runRadarSearch().catch((err) => showToast(err.message)));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runRadarSearch().catch((err) => showToast(err.message));
    }
  });
  input.addEventListener("search", () => {
    if (input.value.trim()) {
      runRadarSearch().catch((err) => showToast(err.message));
    }
  });
  $$("button[data-search]").forEach((item) => {
    item.addEventListener("click", () => runRadarSearch(item.dataset.search).catch((err) => showToast(err.message)));
  });
}

function bindFoloHiveTools() {
  document.addEventListener("click", (event) => {
    const foloLink = event.target.closest("[data-folo-source-click]");
    if (!foloLink) return;
    const current = recordFoloSourceClick(foloLink.dataset);
    renderFoloTimeline();
    if (current) foloLink.textContent = `Folo 源列表 · ${current.count}次`;
    showToast("已记录 Folo 寻源时间线，正在同步");
    syncFoloSourceClick(foloLink.dataset, foloLink);
  });

  $("#manualHiveSearchNameBtn")?.addEventListener("click", () => {
    openManualHiveSearch("name");
  });

  $("#manualHiveSearchUrlBtn")?.addEventListener("click", () => {
    openManualHiveSearch("url");
  });

  $("#manualHiveName")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      openManualHiveSearch("name");
    }
  });

  $("#manualHiveUrl")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      openManualHiveSearch("url");
    }
  });

  $("#manualHiveList")?.addEventListener("click", (event) => {
    const foloOpenBtn = event.target.closest("[data-wechat-folo-open]");
    if (foloOpenBtn) {
      openManualHiveWechatInFolo(foloOpenBtn.dataset.fakeid, foloOpenBtn.dataset.nickname, foloOpenBtn).catch((err) => showToast(err.message));
      return;
    }
    const subscribeBtn = event.target.closest("[data-wechat-subscribe]");
    if (subscribeBtn) {
      subscribeManualHiveWechat(subscribeBtn.dataset.fakeid, subscribeBtn.dataset.nickname, subscribeBtn).catch((err) => showToast(err.message));
      return;
    }
    const radarBtn = event.target.closest("[data-wechat-search-radar]");
    if (radarBtn) {
      const query = radarBtn.dataset.wechatSearchRadar || "";
      if ($("#radarSearchInput")) $("#radarSearchInput").value = query;
      runRadarSearch(query)
        .then(() => $("#radarSearchResults")?.scrollIntoView({ behavior: "smooth", block: "start" }))
        .catch((err) => showToast(err.message));
    }
  });

  $("#manualFeedProbeBtn")?.addEventListener("click", () => {
    probeManualFeed().catch((err) => showToast(err.message));
  });

  $("#collectorAdapterDiscoverBtn")?.addEventListener("click", () => {
    discoverCollectorAdapters().catch((err) => showToast(err.message));
  });

  $("#collectorAdapterRefreshBtn")?.addEventListener("click", () => {
    loadCollectorAdapters().then(() => showToast("采集器候选已刷新")).catch((err) => showToast(err.message));
  });

  $("#manualHiveAddBtn")?.addEventListener("click", async () => {
    const button = $("#manualHiveAddBtn");
    const platform = $("#manualHivePlatform")?.value || "其它";
    const name = ($("#manualHiveName")?.value || "").trim();
    const urlInput = ($("#manualHiveUrl")?.value || "").trim();
    if (!name && !urlInput) {
      showToast("先输入名称或 URL 线索");
      return;
    }
    const entry = {
      id: `manual-${Date.now()}`,
      platform,
      name: name || urlInput,
      url: platformSearchUrl(platform, urlInput || name),
      created_at: new Date().toLocaleString("zh-CN", { hour12: false }),
      score: 65,
    };
    state.manualHiveEntries = [entry, ...(state.manualHiveEntries || [])].slice(0, 80);
    saveLocalJson(FOLO_MANUAL_ENTRIES_KEY, state.manualHiveEntries);
    if ($("#manualHiveName")) $("#manualHiveName").value = "";
    if ($("#manualHiveUrl")) $("#manualHiveUrl").value = "";
    renderIntelCards();
    if (button) button.disabled = true;
    showToast("已加入本次信息寻缘，正在同步");
    try {
      await syncManualHiveEntry(entry);
      showToast("已同步到服务端手动信息池");
    } catch (err) {
      state.manualHiveStats = null;
      renderManualHiveEntries();
      showToast("服务端同步失败，已本地记录");
    } finally {
      if (button) button.disabled = false;
    }
  });

  $("#manualHiveClearBtn")?.addEventListener("click", async () => {
    const button = $("#manualHiveClearBtn");
    state.manualHiveEntries = [];
    state.manualHiveStats = null;
    saveLocalJson(FOLO_MANUAL_ENTRIES_KEY, state.manualHiveEntries);
    renderIntelCards();
    if (button) button.disabled = true;
    try {
      await clearManualHiveEntries();
      showToast("已清空服务端手动项");
    } catch (err) {
      showToast("服务端清空失败，本地已清空");
    } finally {
      if (button) button.disabled = false;
    }
  });

  $("#resourceHiveAddBtn")?.addEventListener("click", async () => {
    const type = $("#resourceHiveType")?.value || "其它资源";
    const name = ($("#resourceHiveName")?.value || "").trim();
    const link = ($("#resourceHiveLink")?.value || "").trim();
    if (!name && !link) {
      showToast("先输入资源名称或链接");
      return;
    }
    const button = $("#resourceHiveAddBtn");
    if (button) button.disabled = true;
    const payload = {
      type,
      name: name || link,
      link: platformSearchUrl("其它", link || name),
      source: "web-resource-hive",
      status: "candidate",
    };
    try {
      const data = await api("/api/resource-hive", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.resourceHiveStats = data;
      state.resourcePoolEntries = data.items || [];
      saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
      showToast("已写入服务端池源");
    } catch (err) {
      const entry = {
        id: `resource-local-${Date.now()}`,
        ...payload,
        created_at: new Date().toLocaleString("zh-CN", { hour12: false }),
        seen_count: 1,
      };
      state.resourcePoolEntries = [entry, ...(state.resourcePoolEntries || [])].slice(0, 120);
      state.resourceHiveStats = null;
      saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
      showToast(`服务端写入失败，已暂存本地：${err.message}`);
    } finally {
      if ($("#resourceHiveName")) $("#resourceHiveName").value = "";
      if ($("#resourceHiveLink")) $("#resourceHiveLink").value = "";
      if (button) button.disabled = false;
      renderResourcePoolEntries();
    }
  });

  $("#resourceHiveRefreshBtn")?.addEventListener("click", () => {
    loadResourceHive().then(() => showToast("资源池已刷新")).catch((err) => showToast(err.message));
  });

  $("#resourceArchivePlanBtn")?.addEventListener("click", () => {
    loadResourceArchivePlan().then((data) => showToast(`待归档 ${data.total_pending || 0} 条`)).catch((err) => showToast(err.message));
  });

  $("#resourceArchiveLinksBtn")?.addEventListener("click", async () => {
    const button = $("#resourceArchiveLinksBtn");
    if (button) button.disabled = true;
    try {
      const data = await writeResourceArchiveLinks();
      showToast(`已写入 NAS 链接 ${data.written_count || 0} 个`);
    } catch (err) {
      showToast(err.message);
    } finally {
      if (button) button.disabled = false;
    }
  });

  $("#resourceDownloadApprovedBtn")?.addEventListener("click", async () => {
    const button = $("#resourceDownloadApprovedBtn");
    if (button) button.disabled = true;
    try {
      const data = await downloadApprovedResources();
      showToast(`已下载 ${data.downloaded_count || 0} 个批准资源`);
    } catch (err) {
      showToast(err.message);
    } finally {
      if (button) button.disabled = false;
    }
  });

  $("#resourceHiveDiscoverBtn")?.addEventListener("click", () => {
    discoverResourceHive(false).catch((err) => showToast(err.message));
  });

  $("#resourceHiveAutoAddBtn")?.addEventListener("click", () => {
    discoverResourceHive(true).catch((err) => showToast(err.message));
  });

  $("#resourceHiveBatchBtn")?.addEventListener("click", () => {
    discoverResourceHiveBatch(false).catch((err) => showToast(err.message));
  });

  $("#resourceHiveBatchAutoAddBtn")?.addEventListener("click", () => {
    discoverResourceHiveBatch(true).catch((err) => showToast(err.message));
  });

  $("#resourceHiveQuery")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    discoverResourceHive(false).catch((err) => showToast(err.message));
  });

  document.addEventListener("click", async (event) => {
    const runButton = event.target.closest("[data-collector-adapter-run]");
    if (runButton) {
      runButton.disabled = true;
      try {
        const data = await runCollectorAdapter(runButton.dataset.collectorAdapterRun);
        showToast(`采集完成：${data.run?.collected_count || 0} 条`);
      } catch (err) {
        showToast(err.message);
      } finally {
        runButton.disabled = false;
      }
      return;
    }

    const allowButton = event.target.closest("[data-collector-adapter-allow]");
    if (allowButton) {
      allowButton.disabled = true;
      try {
        await allowCollectorAdapter(allowButton.dataset.collectorAdapterAllow);
        showToast("已加入执行白名单");
      } catch (err) {
        showToast(err.message);
      } finally {
        allowButton.disabled = false;
      }
      return;
    }

    const reviewButton = event.target.closest("[data-collector-adapter-review]");
    if (reviewButton) {
      reviewButton.disabled = true;
      try {
        await reviewCollectorAdapter(reviewButton.dataset.collectorAdapterReview);
        showToast("仓库审核完成");
      } catch (err) {
        showToast(err.message);
      } finally {
        reviewButton.disabled = false;
      }
      return;
    }

    const approveButton = event.target.closest("[data-resource-download-approve]");
    if (approveButton) {
      approveButton.disabled = true;
      try {
        await approveResourceDownload(approveButton.dataset.resourceDownloadApprove);
        showToast("已批准该资源下载");
      } catch (err) {
        showToast(err.message);
      } finally {
        approveButton.disabled = false;
      }
      return;
    }

    const button = event.target.closest("[data-resource-candidate-add]");
    if (!button) return;
    const item = state.resourceHiveCandidates[Number(button.dataset.resourceCandidateAdd || -1)];
    if (!item) return;
    button.disabled = true;
    try {
      const data = await api("/api/resource-hive", {
        method: "POST",
        body: JSON.stringify(item),
      });
      state.resourceHiveStats = data;
      state.resourcePoolEntries = data.items || [];
      saveLocalJson(FOLO_RESOURCE_POOL_KEY, state.resourcePoolEntries);
      renderResourcePoolEntries();
      showToast("候选已加入服务端池源");
    } catch (err) {
      showToast(err.message);
    } finally {
      button.disabled = false;
    }
  });

  renderManualHiveEntries();
  renderManualFeedProbe();
  renderResourcePoolEntries();
  renderResourceHiveCandidates();
  renderResourceArchivePlan();
  renderCollectorAdapters();
  renderFoloTimeline();
}

function bindUnlockForm() {
  $("#unlockForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = $("#unlockPassword").value.trim();
    const totp = ($("#unlockTotp")?.value || "").replace(/\D/g, "");
    if (!state.protected) {
      $("#unlockError").textContent = "服务端未配置访问口令，已拒绝开放访问";
      return;
    }
    if (!password) {
      $("#unlockError").textContent = "请输入口令";
      return;
    }
    if (state.totpRequired && totp.length !== 6) {
      $("#unlockError").textContent = "请输入 Authenticator 6 位动态码";
      return;
    }
    $("#unlockBtn").disabled = true;
    $("#unlockError").textContent = "";
    try {
      await unlock(password, totp);
      showToast("已解锁");
    } catch (err) {
      $("#unlockError").textContent = err.status === 401 ? "口令或动态码不正确" : err.message;
      showToast("解锁失败");
    } finally {
      $("#unlockBtn").disabled = false;
    }
  });
}

async function bootstrap() {
  clearLegacyAuthState();
  renderProjects();
  const initialRoute =
    location.hash === "#agenthub"
      ? "agenthub"
      : location.hash === "#inforadar"
        ? "inforadar"
        : location.hash === "#codex"
          ? "codex"
          : location.hash === "#openclaw"
            ? "openclaw"
            : "hub";
  setRoute(initialRoute, false);
  bindNavigation();
  bindProjectShell();
  bindCommands();
  bindCodexTerminal();
  bindOpenClawCommandCenter();
  bindRadarSearch();
  bindFoloHiveTools();
  bindUnlockForm();
  bindHeaderDrawer();
  startAgentHubLiveRefresh();
  startCodexTerminalRefresh();

  try {
    const health = await api("/api/health");
    $("#healthLine").textContent = health.ok ? "本机服务正常" : "服务异常";
  } catch (err) {
    $("#healthLine").textContent = "服务未连接";
  }

  try {
    const session = await checkSession();
    if (session.authenticated) {
      setAppVisible(true);
      await refreshWorkspace();
    } else {
      setTabNonce("");
      setAppVisible(false);
    }
  } catch (err) {
    setAppVisible(false);
    $("#lockStatus").textContent = "等待解锁";
    showToast(err.message);
  }
}

bootstrap();
