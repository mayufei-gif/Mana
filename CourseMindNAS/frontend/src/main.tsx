import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const MEDIA_BASE =
  import.meta.env.VITE_MEDIA_BASE ??
  (window.location.hostname && window.location.port === "8788"
    ? `${window.location.protocol}//${window.location.hostname}:8766`
    : API_BASE);
const HUB_URL = import.meta.env.VITE_HUB_URL ?? "https://inforadar.mana-mana.top/";
const ACTIVE_STATUSES = new Set([
  "queued",
  "extracting_audio",
  "splitting_audio",
  "transcribing",
  "optimizing_subtitle",
  "generating_chapters",
  "generating_highlights",
  "generating_note",
  "indexing"
]);
const STAR_COLORS = [
  { value: "gold", label: "重点", color: "#c4933a" },
  { value: "red", label: "易错", color: "#d9542b" },
  { value: "green", label: "方法", color: "#2f6f5f" },
  { value: "blue", label: "疑问", color: "#2d6cdf" },
  { value: "purple", label: "例题", color: "#8a5bd1" }
];
const MINE_TAB_KEY = "mine";
const SYSTEM_TAB_KEY = "system";
const DEFAULT_LOOP_COUNT = 2;

type Video = {
  id: number;
  title: string;
  file_path: string;
  folder: string | null;
  duration: number | null;
  file_size: number;
  extension: string | null;
  status: string;
  subtitle_status: string;
  analysis_status: string;
  note_status: string;
  error_stage: string | null;
  error_message: string | null;
  updated_at: string;
  last_play_position: number;
  last_opened_at: string | null;
  missing: number;
  chapter_count: number;
  highlight_count: number;
  has_note: number;
  has_mock_transcript: number;
  job_id: number | null;
  job_status: string | null;
  job_progress: number | null;
  job_current_step: string | null;
  job_priority: number | null;
};

type Segment = { id?: number; start_time: number; end_time: number; text: string; cleaned_text: string; segment_index?: number };
type Chapter = { id: number; title: string; start_time: number; end_time: number; summary: string; importance: number };
type HighlightSource = {
  source_role: string;
  segment_id: number | null;
  start_time: number;
  end_time: number;
  text: string;
  cleaned_text: string;
  segment_index?: number | null;
  star_id?: number | null;
  star_color?: string | null;
  tag_label?: string | null;
  star_tags?: StarTag[];
};
type StarTag = { star_id?: number | null; star_color?: string | null; tag_label?: string | null };
type Highlight = {
  id: number;
  video_id?: number;
  type: string;
  title: string;
  content: string;
  start_time: number;
  end_time: number;
  importance: number;
  source_method?: string | null;
  status?: string | null;
  source_segment_count?: number | null;
  review_status?: string | null;
  sources?: HighlightSource[];
};
type StarredSegment = Segment & {
  star_id: number;
  segment_id: number;
  note: string | null;
  star_color?: string | null;
  tag_label?: string | null;
  created_at: string;
  updated_at: string;
};
type SearchHit = { video_id: number; video_title: string; start_time: number; hit_type: string; content: string };
type SettingsData = Record<string, unknown>;
type StarDraft = { segmentId: number | null; color: string; label: string; customColor: string };
type PlaybackRange = { id: string; start_time: number; end_time: number; title: string };
type LoopPlaybackState = {
  ranges: PlaybackRange[];
  activeIndex: number;
  repeatCount: number;
  remainingRepeats: number;
};
type StarCluster = {
  id: string;
  categoryKey: string;
  label: string;
  color: string;
  colorValue: string;
  title: string;
  defaultTitle: string;
  start_time: number;
  end_time: number;
  sources: HighlightSource[];
  sideNotes: HighlightSource[];
  anchorCount: number;
  groupKind: "pair" | "single";
};
type StarClusterCategory = {
  key: string;
  label: string;
  color: string;
  colorValue: string;
  clusters: StarCluster[];
};
type ManualRangeDraft = {
  startSegmentId: string;
  endSegmentId: string;
  title: string;
  highlightType: string;
  summary: string;
};
type TimelineItem = {
  time: number;
  endTime?: number;
  title: string;
  body: string;
  badge: string;
  tone?: "auto" | "starred";
  sourceCount?: number;
  sources?: HighlightSource[];
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function formatTime(seconds?: number | null) {
  const value = Math.max(0, Math.floor(seconds ?? 0));
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return h > 0
    ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatTimeRange(start?: number | null, end?: number | null) {
  if (end == null || end <= (start ?? 0)) return formatTime(start);
  return `${formatTime(start)} - ${formatTime(end)}`;
}

function formatSize(bytes?: number | null) {
  const mb = (bytes ?? 0) / 1024 / 1024;
  return `${Math.max(0, Math.round(mb))} MB`;
}

function compactText(text: string, maxLength = 42) {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
}

function readNumberSetting(key: string, fallback: number, min: number, max: number) {
  const raw = window.localStorage.getItem(key);
  const value = Number(raw);
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function isTextEditingTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;
  if (target.closest("textarea, select, [contenteditable='true'], [contenteditable='plaintext-only'], [role='textbox']")) {
    return true;
  }
  const input = target.closest("input");
  if (!(input instanceof HTMLInputElement)) return false;
  return ["", "text", "search", "url", "email", "password", "number", "tel"].includes(input.type);
}

function statusLabel(status: string) {
  const mapping: Record<string, string> = {
    pending: "未处理",
    queued: "已入队",
    extracting_audio: "提取音频中",
    splitting_audio: "切片中",
    transcribing: "生成字幕中",
    optimizing_subtitle: "优化智能字幕中",
    generating_chapters: "生成章节中",
    generating_highlights: "提取重点中",
    generating_note: "生成笔记中",
    indexing: "建立索引中",
    ready: "已完成",
    failed: "处理失败",
    missing: "源文件缺失",
    mock_placeholder: "待真实转录",
    none: "未生成",
    processing: "处理中"
  };
  return mapping[status] ?? status;
}

function canOpen(video: Video) {
  return video.missing !== 1 && video.status !== "missing";
}

function isInternalAsrSample(video: Video) {
  return video.file_path.includes("/real_asr_samples/");
}

function isCompletedRealAsrSample(video: Video) {
  return isInternalAsrSample(video) && video.status === "ready" && video.subtitle_status === "ready";
}

function shouldShowInLibrary(video: Video) {
  return !isInternalAsrSample(video) || isCompletedRealAsrSample(video);
}

function isMockPlaceholderSegment(segment: Segment) {
  const text = `${segment.cleaned_text || ""} ${segment.text || ""}`;
  return (
    text.includes("待转录片段：chunk_") ||
    text.includes("当前使用 mock provider") ||
    text.trim() === "mp3。"
  );
}

function segmentText(segment: Pick<Segment, "text" | "cleaned_text">) {
  return segment.cleaned_text || segment.text || "";
}

function sourceRoleLabel(role?: string | null) {
  const mapping: Record<string, string> = {
    anchor: "星标句",
    context_before: "前文",
    context_after: "后文",
    start_segment: "起点",
    middle_segment: "区间",
    end_segment: "终点"
  };
  return mapping[role ?? ""] ?? "来源";
}

function segmentMatchesStar(segment: Segment, star: StarredSegment) {
  if (segment.id && segment.id === star.segment_id) return true;
  return Math.abs(segment.start_time - star.start_time) < 0.5 && Math.abs(segment.end_time - star.end_time) < 0.5;
}

function findStarredSegmentIndex(segments: Segment[], star: StarredSegment) {
  return segments.findIndex((segment) => segmentMatchesStar(segment, star));
}

function buildStarredTimelineItems(starredSegments: StarredSegment[], allSegments: Segment[]): TimelineItem[] {
  const sorted = [...starredSegments].sort((a, b) => a.start_time - b.start_time);
  const groups: StarredSegment[][] = [];
  for (const segment of sorted) {
    const previousGroup = groups[groups.length - 1];
    const previousSegment = previousGroup?.[previousGroup.length - 1];
    if (previousGroup && previousSegment && segment.start_time - previousSegment.end_time <= 20) {
      previousGroup.push(segment);
    } else {
      groups.push([segment]);
    }
  }

  return groups.map((group) => {
    const starredText = group.map(segmentText).filter(Boolean).join(" ");
    const matchedIndexes = group
      .map((segment) => findStarredSegmentIndex(allSegments, segment))
      .filter((index) => index >= 0);
    const contextSegments = matchedIndexes.length > 0
      ? allSegments.slice(Math.max(0, Math.min(...matchedIndexes) - 1), Math.min(allSegments.length, Math.max(...matchedIndexes) + 3))
      : group;
    const contextText = contextSegments
      .map((segment) => `${formatTimeRange(segment.start_time, segment.end_time)} ${segmentText(segment)}`)
      .filter(Boolean)
      .join("\n");
    const start = contextSegments[0]?.start_time ?? group[0].start_time;
    const end = contextSegments[contextSegments.length - 1]?.end_time ?? group[group.length - 1].end_time;
    const body = [
      `重点句：${starredText}`,
      "为什么重要：这是你手动标出的复习点，系统已自动带入前后字幕，方便回看这一段的完整语境。",
      `来源字幕：\n${contextText}`
    ].join("\n\n");
    return {
      time: start,
      endTime: end,
      title: group.length > 1 ? `我的星标片段：${compactText(starredText, 28)}` : `我的星标片段：${compactText(starredText, 28)}`,
      body,
      badge: group.length > 1 ? `星标 ${group.length} 条` : "我的星标",
      sourceCount: contextSegments.length,
      sources: contextSegments.map((segment) => ({
        source_role: group.some((star) => segmentMatchesStar(segment, star))
          ? "anchor"
          : segment.start_time < group[0].start_time ? "context_before" : "context_after",
        segment_id: segment.id ?? null,
        start_time: segment.start_time,
        end_time: segment.end_time,
        text: segment.text,
        cleaned_text: segment.cleaned_text,
        segment_index: segment.segment_index ?? null
      })),
      tone: "starred"
    };
  });
}

function hasMockTranscript(video: Video) {
  return video.has_mock_transcript === 1;
}

function segmentIndexLabel(segment?: { segment_index?: number | null } | null) {
  if (segment?.segment_index == null) return "";
  return `第 ${segment.segment_index + 1} 条`;
}

function segmentOptionLabel(segment: Segment) {
  const indexLabel = segmentIndexLabel(segment);
  return `${indexLabel ? `${indexLabel} · ` : ""}${formatTimeRange(segment.start_time, segment.end_time)} · ${compactText(segmentText(segment), 36)}`;
}

function cleanParagraphFromSources(sources: HighlightSource[]) {
  const seen = new Set<string>();
  const texts: string[] = [];
  for (const source of sources) {
    const text = segmentText(source).replace(/\s+/g, " ").trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    texts.push(text);
  }
  return texts.join(" ").trim();
}

function starColorMeta(value?: string | null) {
  const normalized = (value ?? "").trim();
  const builtIn = STAR_COLORS.find((item) => item.value === normalized);
  if (builtIn) return builtIn;
  if (/^#[0-9a-f]{6}$/i.test(normalized)) {
    return { value: normalized, label: "自定义", color: normalized };
  }
  return STAR_COLORS[0];
}

function starTagLabel(value?: string | null, fallbackColor?: string | null) {
  const custom = (value ?? "").trim();
  if (custom) return custom;
  return starColorMeta(fallbackColor).label;
}

function starTagItems(sources: HighlightSource[]) {
  const seen = new Set<string>();
  const tags: Array<{ color: string; label: string }> = [];
  for (const source of sources) {
    const sourceTags = source.star_tags?.length
      ? source.star_tags
      : source.star_id || source.tag_label ? [{ star_id: source.star_id, star_color: source.star_color, tag_label: source.tag_label }] : [];
    for (const tag of sourceTags) {
      const meta = starColorMeta(tag.star_color);
      const label = starTagLabel(tag.tag_label, tag.star_color);
      const key = `${meta.value}:${label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      tags.push({ color: meta.color, label });
    }
  }
  return tags;
}

function starCategoryKey(colorValue: string, label: string) {
  return colorValue === "gold" && label === "重点" ? MINE_TAB_KEY : `star:${colorValue}:${label}`;
}

function highlightSearchText(highlight: Highlight) {
  return [
    highlight.title,
    highlight.type,
    highlight.content,
    ...(highlight.sources ?? []).map((source) => `${formatTimeRange(source.start_time, source.end_time)} ${segmentText(source)}`)
  ].join(" ").toLowerCase();
}

function clusterSearchText(cluster: StarCluster) {
  return [
    cluster.title,
    cluster.label,
    formatTimeRange(cluster.start_time, cluster.end_time),
    ...cluster.sources.map((source) => `${formatTimeRange(source.start_time, source.end_time)} ${segmentText(source)}`),
    ...cluster.sideNotes.map((source) => `${formatTimeRange(source.start_time, source.end_time)} ${segmentText(source)} ${starTagLabel(source.tag_label, source.star_color)}`)
  ].join(" ").toLowerCase();
}

function highlightToPlaybackRange(highlight: Highlight): PlaybackRange {
  return {
    id: `highlight:${highlight.id}`,
    start_time: highlight.start_time,
    end_time: highlight.end_time,
    title: highlight.title
  };
}

function clusterToPlaybackRange(cluster: StarCluster): PlaybackRange {
  return {
    id: `cluster:${cluster.id}`,
    start_time: cluster.start_time,
    end_time: cluster.end_time,
    title: cluster.title
  };
}

function buildStarClusterCategories(
  starredSegments: StarredSegment[],
  allSegments: Segment[],
  customTitles: Record<string, string>
): StarClusterCategory[] {
  const categoryMap = new Map<string, { label: string; color: string; colorValue: string; stars: StarredSegment[] }>();
  for (const star of starredSegments) {
    const meta = starColorMeta(star.star_color);
    const label = starTagLabel(star.tag_label, star.star_color);
    const key = starCategoryKey(meta.value, label);
    const bucket = categoryMap.get(key) ?? { label: key === MINE_TAB_KEY ? "我的重点" : label, color: meta.color, colorValue: meta.value, stars: [] };
    bucket.stars.push(star);
    categoryMap.set(key, bucket);
  }

  const colorOrder = new Map(STAR_COLORS.map((item, index) => [item.value, index]));
  return [...categoryMap.entries()]
    .sort((left, right) => {
      if (left[0] === MINE_TAB_KEY) return -1;
      if (right[0] === MINE_TAB_KEY) return 1;
      const leftRank = colorOrder.get(left[1].colorValue) ?? 99;
      const rightRank = colorOrder.get(right[1].colorValue) ?? 99;
      if (leftRank !== rightRank) return leftRank - rightRank;
      return left[1].label.localeCompare(right[1].label, "zh-Hans-CN");
    })
    .map(([key, category]) => {
      const sorted = [...category.stars].sort((a, b) => a.start_time - b.start_time);
      const pairedGroups: StarredSegment[][] = [];
      const singleGroups: StarredSegment[][] = [];
      for (let index = 0; index < sorted.length; index += 2) {
        const first = sorted[index];
        const second = sorted[index + 1];
        if (first && second) {
          pairedGroups.push([first, second]);
        } else if (first) {
          singleGroups.push([first]);
        }
      }

      const makeSource = (segment: Segment, anchor?: StarredSegment | null): HighlightSource => ({
        source_role: anchor ? "anchor" : "middle_segment",
        segment_id: segment.id ?? null,
        start_time: segment.start_time,
        end_time: segment.end_time,
        text: segment.text,
        cleaned_text: segment.cleaned_text,
        segment_index: segment.segment_index ?? null,
        star_id: anchor?.star_id ?? null,
        star_color: anchor?.star_color ?? category.colorValue,
        tag_label: anchor?.tag_label ?? category.label,
        star_tags: anchor ? [{ star_id: anchor.star_id, star_color: anchor.star_color, tag_label: anchor.tag_label }] : []
      });

      const makeCluster = (group: StarredSegment[], index: number, groupKind: "pair" | "single"): StarCluster => {
        const matchedIndexes = group
          .map((star) => findStarredSegmentIndex(allSegments, star))
          .filter((item) => item >= 0);
        const left = matchedIndexes.length ? Math.min(...matchedIndexes) : -1;
        const right = matchedIndexes.length ? Math.max(...matchedIndexes) : -1;
        const sourceSegments = left >= 0 && right >= 0 ? allSegments.slice(left, right + 1) : group;
        const first = sourceSegments[0] ?? group[0];
        const last = sourceSegments[sourceSegments.length - 1] ?? group[group.length - 1];
        const anchorStars = new Map<number, StarredSegment>();
        for (const star of group) {
          if (star.segment_id != null) anchorStars.set(star.segment_id, star);
        }
        const id = [
          key,
          first.id ?? Math.round(first.start_time * 1000),
          last.id ?? Math.round(last.end_time * 1000)
        ].join(":");
        const defaultTitle = `第 ${index + 1} 条`;
        const title = customTitles[id]?.trim() || defaultTitle;
        const sources: HighlightSource[] = sourceSegments.map((segment) => {
          const anchor = segment.id != null ? anchorStars.get(segment.id) : group.find((star) => segmentMatchesStar(segment, star));
          return makeSource(segment, anchor);
        });
        return {
          id,
          categoryKey: key,
          label: category.label,
          color: category.color,
          colorValue: category.colorValue,
          title,
          defaultTitle,
          start_time: first.start_time,
          end_time: last.end_time,
          sources,
          sideNotes: [],
          anchorCount: group.length,
          groupKind
        };
      };

      let visibleIndex = 0;
      const clusters = pairedGroups.map((group) => makeCluster(group, visibleIndex++, "pair"));
      const singles = singleGroups.map((group) => makeCluster(group, visibleIndex++, "single"));

      for (const cluster of clusters) {
        const endpointStarIds = new Set(cluster.sources.map((source) => source.star_id).filter((starId) => starId != null));
        const sideMap = new Map<string, HighlightSource>();
        for (const star of starredSegments) {
          if (endpointStarIds.has(star.star_id)) continue;
          if (star.start_time < cluster.start_time || star.end_time > cluster.end_time) continue;
          const matchedIndex = findStarredSegmentIndex(allSegments, star);
          const segment = matchedIndex >= 0 ? allSegments[matchedIndex] : star;
          const sideSource = makeSource(segment, star);
          sideSource.source_role = "side_note";
          const sideKey = `${sideSource.segment_id ?? sideSource.start_time}:${sideSource.star_color}:${starTagLabel(sideSource.tag_label, sideSource.star_color)}`;
          sideMap.set(sideKey, sideSource);
        }
        cluster.sideNotes = [...sideMap.values()].sort((a, b) => a.start_time - b.start_time);
      }

      const orphanSingles = singles.filter((single) => {
        const host = clusters.find((cluster) => single.start_time >= cluster.start_time && single.end_time <= cluster.end_time);
        if (!host) return true;
        const sideKey = `${single.sources[0]?.segment_id ?? single.start_time}:${single.colorValue}:${single.label}`;
        const exists = host.sideNotes.some((source) => `${source.segment_id ?? source.start_time}:${source.star_color}:${starTagLabel(source.tag_label, source.star_color)}` === sideKey);
        if (!exists && single.sources[0]) {
          host.sideNotes.push({ ...single.sources[0], source_role: "side_note" });
          host.sideNotes.sort((a, b) => a.start_time - b.start_time);
        }
        return false;
      });
      const allClusters = [...clusters, ...orphanSingles].sort((a, b) => a.start_time - b.start_time);
      allClusters.forEach((cluster, index) => {
        if (!customTitles[cluster.id]?.trim()) {
          cluster.defaultTitle = `第 ${index + 1} 条`;
          cluster.title = cluster.defaultTitle;
        }
      });

      return {
        key,
        label: category.label,
        color: category.color,
        colorValue: category.colorValue,
        clusters: allClusters
      };
    });
}

function videoFolderKey(video: Video) {
  if (isCompletedRealAsrSample(video)) return "__real_asr_samples__";
  const folder = (video.folder ?? "").trim();
  return folder && folder !== "." ? folder : "__root__";
}

function folderLabelFromKey(key: string) {
  if (key === "__real_asr_samples__") return "真实 ASR 样片";
  if (key === "__root__") return "根目录";
  return key;
}

function compareFolderKey(left: string, right: string) {
  const rank = (key: string) => {
    if (key === "__real_asr_samples__") return 0;
    if (key === "__root__") return 1;
    return 2;
  };
  const leftRank = rank(left);
  const rightRank = rank(right);
  if (leftRank !== rightRank) return leftRank - rightRank;
  return folderLabelFromKey(left).localeCompare(folderLabelFromKey(right), "zh-Hans-CN");
}

function App() {
  const [page, setPage] = useState<"library" | "player" | "search" | "settings">("library");
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("coursemind_sidebar_collapsed") === "1";
    } catch {
      return false;
    }
  });

  function openPlayer(videoId: number, start = 0) {
    setSelectedVideoId(videoId);
    setPage("player");
    window.history.replaceState(null, "", `#video=${videoId}&t=${Math.floor(start)}`);
  }

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const videoId = Number(hash.get("video"));
    if (videoId) {
      setSelectedVideoId(videoId);
      setPage("player");
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("coursemind_sidebar_collapsed", sidebarCollapsed ? "1" : "0");
    } catch {
      // localStorage 不可用时仍保持本次页面状态。
    }
  }, [sidebarCollapsed]);

  return (
    <div className={`shell ${sidebarCollapsed ? "shellCollapsed" : ""}`}>
      <aside className="sidebar">
        <button
          type="button"
          className="sidebarToggle"
          onClick={() => setSidebarCollapsed((value) => !value)}
          aria-label={sidebarCollapsed ? "展开左侧栏" : "折叠左侧栏"}
          title={sidebarCollapsed ? "展开左侧栏" : "折叠左侧栏"}
        >
          {sidebarCollapsed ? "☰" : "‹"}
        </button>
        <div className="brand">
          <span className="brandMark">CM</span>
          <div className="brandText">
            <strong>CourseMind</strong>
            <small>NAS 学习大脑</small>
          </div>
        </div>
        <a className="hubLink" href={HUB_URL}>
          <span className="hubIcon">←</span>
          <span className="hubLabel">返回 Mana Hub</span>
        </a>
        <button className={page === "library" ? "active" : ""} onClick={() => setPage("library")} title="课程库">
          <span className="navIcon">库</span>
          <span className="navLabel">课程库</span>
        </button>
        <button className={page === "search" ? "active" : ""} onClick={() => setPage("search")} title="全文搜索">
          <span className="navIcon">搜</span>
          <span className="navLabel">全文搜索</span>
        </button>
        <button className={page === "settings" ? "active" : ""} onClick={() => setPage("settings")} title="设置">
          <span className="navIcon">设</span>
          <span className="navLabel">设置</span>
        </button>
      </aside>
      <main>
        {page === "library" && <LibraryPage onOpen={openPlayer} />}
        {page === "player" && selectedVideoId && <PlayerPage videoId={selectedVideoId} />}
        {page === "search" && <SearchPage onOpen={openPlayer} />}
        {page === "settings" && <SettingsPage />}
      </main>
    </div>
  );
}

function LibraryPage({ onOpen }: { onOpen: (videoId: number) => void }) {
  const [videos, setVideos] = useState<Video[]>([]);
  const [message, setMessage] = useState("");
  const [filter, setFilter] = useState("all");
  const [folderFilter, setFolderFilter] = useState("all");

  async function load() {
    const res = await api<{ ok: boolean; data: Video[] }>("/api/videos");
    setVideos(res.data);
  }

  async function scan() {
    setMessage("正在扫描 NAS 视频目录...");
    const res = await api<{ ok: boolean; data: { found: number; inserted: number; updated: number; skipped: number; missing: number } }>(
      "/api/videos/scan",
      { method: "POST", body: JSON.stringify({}) }
    );
    setMessage(`扫描完成：发现 ${res.data.found}，新增 ${res.data.inserted}，更新 ${res.data.updated}，缺失 ${res.data.missing}。`);
    await load();
  }

  async function enqueue(videoId: number, mode: "priority-process" | "reprocess" | "process") {
    const endpoint = mode === "priority-process" ? "priority-process" : mode === "reprocess" ? "reprocess" : "process";
    await api(`/api/videos/${videoId}/${endpoint}`, { method: "POST" });
    setMessage(mode === "priority-process" ? `视频 ${videoId} 已优先入队。` : `视频 ${videoId} 已加入处理队列。`);
    await load();
  }

  useEffect(() => {
    load().catch((err) => setMessage(String(err)));
  }, []);

  useEffect(() => {
    if (!videos.some((video) => ACTIVE_STATUSES.has(video.status) || video.status === "queued")) {
      return;
    }
    const timer = window.setInterval(() => {
      load().catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [videos]);

  const visibleVideos = useMemo(() => videos.filter(shouldShowInLibrary), [videos]);

  const folderOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const video of visibleVideos) {
      const key = videoFolderKey(video);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([key, count]) => ({ key, label: folderLabelFromKey(key), count }))
      .sort((a, b) => compareFolderKey(a.key, b.key));
  }, [visibleVideos]);

  useEffect(() => {
    if (folderFilter !== "all" && !folderOptions.some((option) => option.key === folderFilter)) {
      setFolderFilter("all");
    }
  }, [folderFilter, folderOptions]);

  const statusFilteredVideos = useMemo(() => {
    if (filter === "all") return visibleVideos;
    if (filter === "processing") return visibleVideos.filter((video) => ACTIVE_STATUSES.has(video.status) || video.status === "queued");
    return visibleVideos.filter((video) => video.status === filter);
  }, [filter, visibleVideos]);

  const filteredVideos = useMemo(() => {
    if (folderFilter === "all") return statusFilteredVideos;
    return statusFilteredVideos.filter((video) => videoFolderKey(video) === folderFilter);
  }, [folderFilter, statusFilteredVideos]);

  const groupedVideos = useMemo(() => {
    const groups = new Map<string, Video[]>();
    for (const video of filteredVideos) {
      const key = videoFolderKey(video);
      const list = groups.get(key) ?? [];
      list.push(video);
      groups.set(key, list);
    }
    return [...groups.entries()]
      .map(([key, groupVideos]) => ({
        key,
        label: folderLabelFromKey(key),
        videos: groupVideos
      }))
      .sort((a, b) => compareFolderKey(a.key, b.key));
  }, [filteredVideos]);

  return (
    <section className="panel hero">
      <div className="heroHeader">
        <div>
          <p className="eyebrow">NAS 视频自动字幕与重点定位</p>
          <h1>放进目录，点开就能学</h1>
          <p>自动扫描 NAS 视频，后台先生成智能字幕、章节、重点和笔记；完成后进入同步学习播放器。</p>
        </div>
        <div className="heroActions">
          <button className="primary" onClick={scan}>立即扫描</button>
        </div>
      </div>
      <div className="libraryTools">
        <div className="toolBlock">
          <div className="toolTitle">
            <strong>处理状态</strong>
            <span>{statusFilteredVideos.length} / {visibleVideos.length}</span>
          </div>
          <div className="filterRow">
            {[
              ["all", "全部视频"],
              ["pending", "未处理"],
              ["processing", "处理中"],
              ["ready", "已完成"],
              ["failed", "失败"],
              ["missing", "缺失"]
            ].map(([value, label]) => (
              <button key={value} className={filter === value ? "chip activeChip" : "chip"} onClick={() => setFilter(value)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="toolBlock">
          <div className="toolTitle">
            <strong>课程目录</strong>
            <span>递归扫描后自动归类</span>
          </div>
          <div className="folderFilterRow">
            <button className={folderFilter === "all" ? "folderChip folderChipActive" : "folderChip"} onClick={() => setFolderFilter("all")}>
              <span>全部目录</span>
              <small>{visibleVideos.length}</small>
            </button>
            {folderOptions.map((option) => (
              <button
                key={option.key}
                className={folderFilter === option.key ? "folderChip folderChipActive" : "folderChip"}
                onClick={() => setFolderFilter(option.key)}
              >
                <span>{option.label}</span>
                <small>{option.count}</small>
              </button>
            ))}
          </div>
        </div>
      </div>
      {message && <div className="notice">{message}</div>}
      {filteredVideos.length === 0 ? (
        <div className="emptyLibrary">
          <strong>当前筛选下没有视频。</strong>
          <span>可以切回“全部目录”，或把课程视频放进 NAS 视频目录后点击“立即扫描”。</span>
        </div>
      ) : (
        <div className="folderGroups">
          {groupedVideos.map((group) => (
            <section className="folderGroup" key={group.key}>
              <div className="folderGroupHeader">
                <div>
                  <span className="folderBadge">课程目录</span>
                  <h2>{group.label}</h2>
                </div>
                <span>{group.videos.length} 个视频</span>
              </div>
              <div className="videoGrid">
                {group.videos.map((video) => (
                  <article className="videoCard" key={video.id}>
                    <div className="cardTop">
                      <div className={`status ${video.status}`}>{statusLabel(video.status)}</div>
                      {video.job_progress != null && ACTIVE_STATUSES.has(video.status) && (
                        <span className="progressPill">{video.job_progress}%</span>
                      )}
                    </div>
                    <h3>{video.title}{isCompletedRealAsrSample(video) ? " · 真实 ASR 样片" : ""}</h3>
                    <div className="folderPath">{folderLabelFromKey(videoFolderKey(video))}</div>
                    <p>{video.file_path}</p>
                    <div className="meta">
                      <span>{formatTime(video.duration)}</span>
                      <span>{formatSize(video.file_size)}</span>
                      <span>{video.extension || "视频"}</span>
                    </div>
                    <div className="dataList">
                      <span>字幕：{hasMockTranscript(video) ? statusLabel("mock_placeholder") : statusLabel(video.subtitle_status || "none")}</span>
                      <span>章节：{hasMockTranscript(video) ? "待真实转录" : video.chapter_count}</span>
                      <span>重点：{hasMockTranscript(video) ? "待真实转录" : video.highlight_count}</span>
                      <span>笔记：{hasMockTranscript(video) ? "待真实转录" : video.has_note ? "已生成" : "未生成"}</span>
                      <span>上次播放：{formatTime(video.last_play_position)}</span>
                    </div>
                    {video.job_current_step && ACTIVE_STATUSES.has(video.status) && (
                      <div className="miniProgress">
                        <div className="miniProgressBar" style={{ width: `${video.job_progress ?? 0}%` }} />
                        <small>{statusLabel(video.job_current_step)}</small>
                      </div>
                    )}
                    {video.error_message && <pre className="error">{video.error_stage ? `[${statusLabel(video.error_stage)}]\n` : ""}{video.error_message}</pre>}
                    <div className="actions">
                      <button disabled={!canOpen(video)} onClick={() => onOpen(video.id)}>
                        {video.status === "ready" ? "打开学习" : "查看处理"}
                      </button>
                      <button onClick={() => enqueue(video.id, "priority-process")}>优先处理</button>
                      <button onClick={() => enqueue(video.id, "reprocess")}>重新处理</button>
                      {video.status === "ready" && video.subtitle_status === "ready" && !hasMockTranscript(video) && <a href={`${API_BASE}/api/videos/${video.id}/smart-subtitle/vtt`} target="_blank">导出字幕</a>}
                      {video.has_note && !hasMockTranscript(video) ? <a href={`${API_BASE}/api/videos/${video.id}/export/markdown`} target="_blank">导出笔记</a> : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function PlayerPage({ videoId }: { videoId: number }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playerTopRef = useRef<HTMLDivElement | null>(null);
  const subtitleScrollRef = useRef<HTMLDivElement | null>(null);
  const subtitleLineRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [video, setVideo] = useState<Video | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [starredSegments, setStarredSegments] = useState<StarredSegment[]>([]);
  const [note, setNote] = useState("");
  const [current, setCurrent] = useState(0);
  const [videoError, setVideoError] = useState("");
  const [playbackVersion, setPlaybackVersion] = useState(() => Date.now());
  const [subtitleFontSize, setSubtitleFontSize] = useState(() => readNumberSetting("coursemind.subtitle.size", 16, 14, 28));
  const [subtitleOpacity, setSubtitleOpacity] = useState(() => readNumberSetting("coursemind.subtitle.opacity", 54, 25, 90));
  const [subtitleBottom, setSubtitleBottom] = useState(() => readNumberSetting("coursemind.subtitle.bottom", 8, 2, 80));
  const [highlightTab, setHighlightTab] = useState<string>(MINE_TAB_KEY);
  const [highlightMessage, setHighlightMessage] = useState("");
  const [expandedHighlightIds, setExpandedHighlightIds] = useState<Set<number>>(() => new Set());
  const [expandedStarClusterIds, setExpandedStarClusterIds] = useState<Set<string>>(() => new Set());
  const [starClusterTitles, setStarClusterTitles] = useState<Record<string, string>>({});
  const [highlightSearch, setHighlightSearch] = useState("");
  const [loopCount, setLoopCount] = useState(() => readNumberSetting("coursemind.highlight.loopCount", DEFAULT_LOOP_COUNT, 1, 9));
  const [loopPlayback, setLoopPlayback] = useState<LoopPlaybackState | null>(null);
  const [starDraft, setStarDraft] = useState<StarDraft>({ segmentId: null, color: "gold", label: "", customColor: "#c4933a" });
  const [rangeDraft, setRangeDraft] = useState<ManualRangeDraft>({
    startSegmentId: "",
    endSegmentId: "",
    title: "",
    highlightType: "知识点",
    summary: ""
  });
  const restoredRef = useRef(false);

  async function loadStatus() {
    const res = await api<{ data: { video: Video; job: { progress: number; current_step: string; status: string } | null } }>(`/api/videos/${videoId}/status`);
    setVideo({
      ...res.data.video,
      job_progress: res.data.job?.progress ?? null,
      job_current_step: res.data.job?.current_step ?? null,
      job_status: res.data.job?.status ?? null
    });
    return res;
  }

  async function loadArtifacts() {
    const [videoRes, transcriptRes, chapterRes, highlightRes, starredRes, noteRes] = await Promise.all([
      api<{ data: Video }>(`/api/videos/${videoId}`),
      api<{ data: Segment[] }>(`/api/videos/${videoId}/transcript`),
      api<{ data: Chapter[] }>(`/api/videos/${videoId}/chapters`),
      api<{ data: Highlight[] }>(`/api/videos/${videoId}/highlights`),
      api<{ data: StarredSegment[] }>(`/api/videos/${videoId}/starred-segments`),
      api<{ data: { markdown_content: string } | null }>(`/api/videos/${videoId}/note`)
    ]);
    setVideo(videoRes.data);
    setSegments(transcriptRes.data);
    setChapters(chapterRes.data);
    setHighlights(highlightRes.data);
    setStarredSegments(starredRes.data);
    setNote(noteRes.data?.markdown_content ?? "");
  }

  async function savePosition(value: number) {
    if (!Number.isFinite(value)) return;
    try {
      await api(`/api/videos/${videoId}/playback-position`, {
        method: "POST",
        body: JSON.stringify({ current_time: value })
      });
    } catch {
      // 静默保存，避免打断播放。
    }
  }

  async function priorityProcess() {
    await api(`/api/videos/${videoId}/priority-process`, { method: "POST" });
    await loadStatus();
  }

  async function reprocess() {
    await api(`/api/videos/${videoId}/reprocess`, { method: "POST" });
    await loadStatus();
  }

  function scrollToPlayer() {
    const reveal = () => {
      playerTopRef.current?.scrollIntoView({ block: "start", behavior: "auto" });
    };
    window.requestAnimationFrame(reveal);
    window.setTimeout(reveal, 80);
  }

  function jump(time: number, options: { revealPlayer?: boolean } = {}) {
    if (!videoRef.current || video?.status !== "ready") return;
    videoRef.current.currentTime = time;
    window.history.replaceState(null, "", `#video=${videoId}&t=${Math.floor(time)}`);
    videoRef.current.play().catch(() => undefined);
    if (options.revealPlayer) {
      scrollToPlayer();
    }
  }

  function playRanges(ranges: PlaybackRange[], startIndex = 0, options: { revealPlayer?: boolean } = {}) {
    const playableRanges = ranges
      .filter((range) => Number.isFinite(range.start_time) && Number.isFinite(range.end_time) && range.end_time > range.start_time)
      .sort((a, b) => a.start_time - b.start_time);
    if (playableRanges.length === 0) return;
    const boundedIndex = Math.min(playableRanges.length - 1, Math.max(0, startIndex));
    setLoopPlayback({
      ranges: playableRanges,
      activeIndex: boundedIndex,
      repeatCount: loopCount,
      remainingRepeats: loopCount
    });
    jump(playableRanges[boundedIndex].start_time, options);
  }

  function stopLoopPlayback() {
    setLoopPlayback(null);
  }

  function reloadVideoSource() {
    setVideoError("");
    restoredRef.current = false;
    setPlaybackVersion(Date.now());
  }

  async function toggleStarSegment(segment: Segment) {
    if (!segment.id) return;
    const segmentId = segment.id;
    setStarDraft((draft) => draft.segmentId === segmentId
      ? { segmentId: null, color: "gold", label: "", customColor: "#c4933a" }
      : { segmentId, color: "gold", label: "", customColor: "#c4933a" }
    );
  }

  async function refreshStarredSegments() {
    const res = await api<{ data: StarredSegment[] }>(`/api/videos/${videoId}/starred-segments`);
    setStarredSegments(res.data);
  }

  async function addStarTag(segment: Segment, color: string, label: string) {
    if (!segment.id) return;
    const colorMeta = starColorMeta(color);
    const normalizedLabel = label.trim() || colorMeta.label;
    const optimistic: StarredSegment = {
      ...segment,
      id: segment.id,
      star_id: -Math.round(Date.now() + segment.id),
      segment_id: segment.id,
      note: null,
      star_color: colorMeta.value,
      tag_label: normalizedLabel,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    setStarredSegments((items) => {
      const exists = items.some((item) => item.segment_id === segment.id && item.star_color === colorMeta.value && starTagLabel(item.tag_label, item.star_color) === normalizedLabel);
      return exists ? items : [...items, optimistic].sort((a, b) => a.start_time - b.start_time);
    });
    await api(`/api/videos/${videoId}/segments/${segment.id}/star`, {
      method: "POST",
      body: JSON.stringify({ note: null, star_color: colorMeta.value, tag_label: normalizedLabel })
    });
    await refreshStarredSegments();
  }

  async function removeStarTag(segment: Segment, color: string, label: string) {
    if (!segment.id) return;
    const encodedColor = encodeURIComponent(color);
    const encodedLabel = encodeURIComponent(label);
    setStarredSegments((items) => items.filter((item) => !(
      item.segment_id === segment.id &&
      item.star_color === color &&
      starTagLabel(item.tag_label, item.star_color) === label
    )));
    await api(`/api/videos/${videoId}/segments/${segment.id}/star?star_color=${encodedColor}&tag_label=${encodedLabel}`, { method: "DELETE" });
    await refreshStarredSegments();
  }

  async function toggleStarTag(segment: Segment, color: string, label: string, active: boolean) {
    if (active) {
      await removeStarTag(segment, color, label);
      return;
    }
    await addStarTag(segment, color, label);
  }

  async function saveStarSegment(segment: Segment) {
    if (!segment.id || starDraft.segmentId !== segment.id) return;
    const selectedColor = starDraft.color === "custom" ? starDraft.customColor : starDraft.color;
    const colorMeta = starColorMeta(selectedColor);
    const label = starDraft.label.trim() || colorMeta.label;
    await addStarTag(segment, colorMeta.value, label);
    setStarDraft({ segmentId: null, color: "gold", label: "", customColor: "#c4933a" });
  }

  async function createManualHighlight() {
    const startSegmentId = Number(rangeDraft.startSegmentId);
    const endSegmentId = Number(rangeDraft.endSegmentId);
    if (!startSegmentId || !endSegmentId) {
      setHighlightMessage("请先选择重点区间的起点和终点。");
      return;
    }
    try {
      const res = await api<{ data: Highlight }>(`/api/videos/${videoId}/highlights/manual-range`, {
        method: "POST",
        body: JSON.stringify({
          start_segment_id: startSegmentId,
          end_segment_id: endSegmentId,
          title: rangeDraft.title || undefined,
          highlight_type: rangeDraft.highlightType || "自定义",
          summary: rangeDraft.summary || undefined
        })
      });
      setHighlights((items) => [...items.filter((item) => item.id !== res.data.id), res.data].sort((a, b) => a.start_time - b.start_time));
      setRangeDraft({ startSegmentId: "", endSegmentId: "", title: "", highlightType: "知识点", summary: "" });
      setHighlightTab("mine");
      setHighlightMessage("已保存到我的重点。");
    } catch (error) {
      setHighlightMessage(`创建重点失败：${String(error)}`);
    }
  }

  async function editHighlight(highlight: Highlight) {
    const title = window.prompt("修改重点标题", highlight.title);
    if (title == null) return;
    const highlightType = window.prompt("修改重点类型", highlight.type || "自定义");
    if (highlightType == null) return;
    const summary = window.prompt("修改简短说明", highlight.content || "");
    if (summary == null) return;
    try {
      const res = await api<{ data: Highlight }>(`/api/videos/${videoId}/highlights/${highlight.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title,
          highlight_type: highlightType,
          summary
        })
      });
      setHighlights((items) => items.map((item) => item.id === highlight.id ? res.data : item));
      setHighlightMessage("重点已更新。");
    } catch (error) {
      setHighlightMessage(`更新失败：${String(error)}`);
    }
  }

  async function deleteHighlight(highlight: Highlight) {
    if (!window.confirm(`确认删除这个重点区间？\n${formatTimeRange(highlight.start_time, highlight.end_time)} ${highlight.title}`)) return;
    try {
      await api(`/api/videos/${videoId}/highlights/${highlight.id}`, { method: "DELETE" });
      setHighlights((items) => items.filter((item) => item.id !== highlight.id));
      setHighlightMessage("重点已删除。");
    } catch (error) {
      setHighlightMessage(`删除失败：${String(error)}`);
    }
  }

  async function exportHighlightMarkdown(action: "copy" | "download") {
    try {
      const res = await api<{ data: { filename: string; content: string; count: number } }>(
        `/api/videos/${videoId}/highlights/export-markdown?scope=my_highlights&mode=clean`
      );
      if (!res.data.content) {
        setHighlightMessage("当前还没有可导出的“我的重点”。");
        return;
      }
      if (action === "copy") {
        await navigator.clipboard.writeText(res.data.content);
        setHighlightMessage(`已复制 ${res.data.count} 个重点区间的 Markdown。`);
        return;
      }
      const blob = new Blob([res.data.content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = res.data.filename;
      link.click();
      URL.revokeObjectURL(url);
      setHighlightMessage(`已导出 ${res.data.count} 个重点区间。`);
    } catch (error) {
      setHighlightMessage(`导出失败：${String(error)}`);
    }
  }

  function toggleHighlightExpanded(highlightId: number) {
    setExpandedHighlightIds((currentIds) => {
      const next = new Set(currentIds);
      if (next.has(highlightId)) {
        next.delete(highlightId);
      } else {
        next.add(highlightId);
      }
      return next;
    });
  }

  function toggleStarClusterExpanded(clusterId: string) {
    setExpandedStarClusterIds((currentIds) => {
      const next = new Set(currentIds);
      if (next.has(clusterId)) {
        next.delete(clusterId);
      } else {
        next.add(clusterId);
      }
      return next;
    });
  }

  function updateStarClusterTitle(clusterId: string, title: string) {
    setStarClusterTitles((currentTitles) => {
      const next = { ...currentTitles, [clusterId]: title };
      try {
        window.localStorage.setItem(`coursemind.starClusterTitles.${videoId}`, JSON.stringify(next));
      } catch {
        // 本地标题只是学习视图偏好，保存失败时不影响使用。
      }
      return next;
    });
  }

  useEffect(() => {
    setVideoError("");
    setPlaybackVersion(Date.now());
    restoredRef.current = false;
    setLoopPlayback(null);
    setHighlightSearch("");
    setExpandedStarClusterIds(new Set());
    try {
      const savedTitles = window.localStorage.getItem(`coursemind.starClusterTitles.${videoId}`);
      setStarClusterTitles(savedTitles ? JSON.parse(savedTitles) as Record<string, string> : {});
    } catch {
      setStarClusterTitles({});
    }
    loadArtifacts().catch(() => {
      loadStatus().catch(console.error);
    });
  }, [videoId]);

  useEffect(() => {
    if (!video) return;
    if (video.status === "ready" || ACTIVE_STATUSES.has(video.status) || video.status === "queued" || video.status === "pending") {
      const timer = window.setInterval(() => {
        loadStatus()
          .then((statusRes) => {
            if (statusRes?.data?.video?.status === "ready" || ACTIVE_STATUSES.has(statusRes?.data?.video?.status ?? "") || statusRes?.data?.video?.status === "queued") {
              return loadArtifacts();
            }
            return undefined;
          })
          .catch(() => undefined);
      }, 4000);
      return () => window.clearInterval(timer);
    }
  }, [video, videoId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (videoRef.current) {
        savePosition(videoRef.current.currentTime);
      }
    }, 8000);
    return () => {
      window.clearInterval(timer);
      if (videoRef.current) {
        void savePosition(videoRef.current.currentTime);
      }
    };
  }, [videoId]);

  useEffect(() => {
    window.localStorage.setItem("coursemind.subtitle.size", String(subtitleFontSize));
    window.localStorage.setItem("coursemind.subtitle.opacity", String(subtitleOpacity));
    window.localStorage.setItem("coursemind.subtitle.bottom", String(subtitleBottom));
  }, [subtitleBottom, subtitleFontSize, subtitleOpacity]);

  useEffect(() => {
    window.localStorage.setItem("coursemind.highlight.loopCount", String(loopCount));
  }, [loopCount]);

  useEffect(() => {
    if (!loopPlayback || !videoRef.current) return;
    const activeRange = loopPlayback.ranges[loopPlayback.activeIndex];
    if (!activeRange || current < activeRange.end_time - 0.15) return;
    if (loopPlayback.remainingRepeats > 1) {
      setLoopPlayback((state) => state
        ? { ...state, remainingRepeats: state.remainingRepeats - 1 }
        : state
      );
      jump(activeRange.start_time);
      return;
    }
    const nextIndex = loopPlayback.activeIndex + 1;
    const nextRange = loopPlayback.ranges[nextIndex];
    if (nextRange) {
      setLoopPlayback((state) => state
        ? { ...state, activeIndex: nextIndex, remainingRepeats: state.repeatCount }
        : state
      );
      jump(nextRange.start_time);
      return;
    }
    setLoopPlayback(null);
  }, [current, loopPlayback]);

  const displaySegments = useMemo(() => segments.filter((segment) => !isMockPlaceholderSegment(segment)), [segments]);
  const hasMockPlaceholderTranscript = segments.length > 0 && displaySegments.length === 0 && segments.some(isMockPlaceholderSegment);

  const activeSegmentIndex = useMemo(() => {
    if (displaySegments.length === 0) return -1;
    const exactIndex = displaySegments.findIndex((item) => current >= item.start_time && current <= item.end_time);
    if (exactIndex >= 0) return exactIndex;
    let previousIndex = -1;
    for (let index = displaySegments.length - 1; index >= 0; index -= 1) {
      if (displaySegments[index].start_time <= current) {
        previousIndex = index;
        break;
      }
    }
    return previousIndex >= 0 ? previousIndex : 0;
  }, [current, displaySegments]);
  const activeSegment = activeSegmentIndex >= 0 ? displaySegments[activeSegmentIndex] : null;
  const progressPercent = video?.duration ? Math.min(100, (current / video.duration) * 100) : 0;
  const timelineMarkers = [
    ...chapters.map((item) => item.start_time),
    ...highlights.map((item) => item.start_time),
    ...starredSegments.map((item) => item.start_time)
  ].sort((a, b) => a - b);
  const isPlayable = Boolean(video && video.missing !== 1 && video.status !== "missing");
  const pendingCopy = {
    subtitle: hasMockPlaceholderTranscript
      ? "当前只有 mock 占位字幕，尚未进行真实转录。"
      : video?.status === "ready" ? "暂无字幕。" : "字幕生成中，处理完成后会自动刷新。",
    chapter: hasMockPlaceholderTranscript
      ? "当前章节来自 mock 占位字幕，已隐藏；真实转录完成后再生成章节。"
      : video?.status === "ready" ? "暂无章节。" : "章节生成中，处理完成后会自动刷新。",
    highlight: hasMockPlaceholderTranscript
      ? "当前重点来自 mock 占位字幕，已隐藏；真实转录完成后再提取重点。"
      : video?.status === "ready" ? "暂无重点。也可以先在同步字幕里点击星标手动标重点。" : "重点提取中，处理完成后会自动刷新。",
    note: hasMockPlaceholderTranscript
      ? "当前笔记来自 mock 占位字幕，已隐藏；真实转录完成后再生成学习笔记。"
      : video?.status === "ready" ? "暂无笔记。" : "笔记生成中，处理完成后会自动刷新。"
  };
  const activeSubtitleText = hasMockPlaceholderTranscript ? "" : activeSegment?.cleaned_text || activeSegment?.text || "";
  const subtitleStateLabel = hasMockPlaceholderTranscript ? statusLabel("mock_placeholder") : statusLabel(video?.subtitle_status ?? "none");
  const visibleChapters = hasMockPlaceholderTranscript ? [] : chapters;
  const visibleHighlights = hasMockPlaceholderTranscript ? [] : highlights;
  const visibleStarredSegments = hasMockPlaceholderTranscript ? [] : starredSegments;
  const starredBySegmentId = useMemo(() => {
    const map = new Map<number, StarredSegment[]>();
    for (const item of visibleStarredSegments) {
      const existing = map.get(item.segment_id) ?? [];
      existing.push(item);
      map.set(item.segment_id, existing);
    }
    return map;
  }, [visibleStarredSegments]);
  const myHighlights = useMemo(
    () => visibleHighlights
      .filter((item) => item.source_method === "manual_range" && (item.status ?? "confirmed") === "confirmed")
      .sort((a, b) => a.start_time - b.start_time),
    [visibleHighlights]
  );
  const systemHighlights = useMemo(
    () => visibleHighlights
      .filter((item) => item.source_method !== "manual_range" && item.source_method !== "user_anchor" && item.type !== "user_anchor")
      .sort((a, b) => a.start_time - b.start_time),
    [visibleHighlights]
  );
  const starClusterCategories = useMemo(
    () => buildStarClusterCategories(visibleStarredSegments, displaySegments, starClusterTitles),
    [displaySegments, starClusterTitles, visibleStarredSegments]
  );
  const activeLoopRangeId = loopPlayback?.ranges[loopPlayback.activeIndex]?.id ?? "";
  const rangePreviewSegments = useMemo(() => {
    const startId = Number(rangeDraft.startSegmentId);
    const endId = Number(rangeDraft.endSegmentId);
    if (!startId || !endId) return [];
    const startIndex = displaySegments.findIndex((segment) => segment.id === startId);
    const endIndex = displaySegments.findIndex((segment) => segment.id === endId);
    if (startIndex < 0 || endIndex < 0) return [];
    const left = Math.min(startIndex, endIndex);
    const right = Math.max(startIndex, endIndex);
    return displaySegments.slice(left, right + 1);
  }, [displaySegments, rangeDraft.endSegmentId, rangeDraft.startSegmentId]);
  const visibleNote = hasMockPlaceholderTranscript ? "" : note;
  const streamUrl = `${MEDIA_BASE}/api/videos/${videoId}/stream?v=${playbackVersion}`;
  const posterUrl = `${MEDIA_BASE}/api/videos/${videoId}/poster?v=${playbackVersion}`;
  const subtitleOverlayStyle = {
    "--subtitle-size": `${subtitleFontSize}px`,
    "--subtitle-alpha": `${subtitleOpacity / 100}`,
    "--subtitle-bottom": `${subtitleBottom}px`
  } as React.CSSProperties;

  useEffect(() => {
    function handleGlobalSpace(event: KeyboardEvent) {
      if (event.defaultPrevented || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
      if (event.code !== "Space" && event.key !== " " && event.key !== "Spacebar") return;
      if (isTextEditingTarget(event.target)) return;

      const player = videoRef.current;
      if (!player || !isPlayable || video?.status !== "ready") return;

      event.preventDefault();
      event.stopPropagation();
      if (player.paused || player.ended) {
        player.play().catch(() => undefined);
      } else {
        player.pause();
      }
    }

    window.addEventListener("keydown", handleGlobalSpace, true);
    return () => window.removeEventListener("keydown", handleGlobalSpace, true);
  }, [isPlayable, video?.status]);

  useEffect(() => {
    if (activeSegmentIndex < 0) return;
    const container = subtitleScrollRef.current;
    const activeLine = subtitleLineRefs.current[activeSegmentIndex];
    if (!container || !activeLine) return;
    const containerRect = container.getBoundingClientRect();
    const activeRect = activeLine.getBoundingClientRect();
    const targetTop = container.scrollTop
      + (activeRect.top - containerRect.top)
      - container.clientHeight * 0.38
      + activeRect.height / 2;

    container.scrollTo({
      top: Math.max(0, targetTop),
      behavior: "smooth"
    });
  }, [activeSegmentIndex]);

  return (
    <section className="playerPage">
      <div className="playerHeader">
        <div>
          <p className="eyebrow">点开即看</p>
          <h2>{video?.title ?? "视频播放器"}</h2>
          <div className="headerMeta">
            <span className={`status ${video?.status ?? "pending"}`}>{statusLabel(video?.status ?? "pending")}</span>
            <span>{video?.job_progress != null ? `处理进度 ${video.job_progress}%` : `时长 ${formatTime(video?.duration)}`}</span>
            <span>字幕：{subtitleStateLabel}</span>
            {video?.folder && <span>{video.folder}</span>}
          </div>
        </div>
        <div className="headerActions">
          {(video?.status === "pending" || video?.status === "queued") && <button className="primary" onClick={priorityProcess}>优先处理这个视频</button>}
          {video?.status === "failed" && <button className="primary" onClick={reprocess}>重新处理</button>}
          {isPlayable && video?.subtitle_status === "ready" && !hasMockPlaceholderTranscript && (
            <a className="ghostButton" href={`${API_BASE}/api/videos/${videoId}/smart-subtitle/vtt`} target="_blank">导出智能字幕</a>
          )}
        </div>
      </div>

      {video?.error_message && <div className="notice errorNotice">{video.error_stage ? `[${statusLabel(video.error_stage)}] ` : ""}{video.error_message}</div>}
      {video?.status === "missing" && <div className="notice errorNotice">原视频文件已不存在或路径失效，请检查 NAS 挂载路径。</div>}

      <div className="playerTop" ref={playerTopRef}>
        <div className="videoPane">
          {isPlayable ? (
            <>
              <div className="videoFrame">
                <video
                  key={`${videoId}-${playbackVersion}`}
                  ref={videoRef}
                  controls
                  preload="metadata"
                  poster={posterUrl}
                  onCanPlay={() => setVideoError("")}
                  onLoadedMetadata={(event) => {
                    if (restoredRef.current) return;
                    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
                    const fromHash = Number(hash.get("t") ?? 0);
                    const fromSaved = video?.last_play_position ?? 0;
                    const target = fromHash || fromSaved;
                    if (target > 0) {
                      event.currentTarget.currentTime = target;
                    }
                    restoredRef.current = true;
                  }}
                  onError={(event) => {
                    const error = event.currentTarget.error;
                    const detail = error ? `code=${error.code}` : "unknown";
                    setVideoError(`浏览器无法播放当前视频源（${detail}）。兼容播放代理已生成时，可重新加载视频源或打开直连源测试。`);
                  }}
                  onPause={(event) => void savePosition(event.currentTarget.currentTime)}
                  onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
                >
                  <source src={streamUrl} type="video/mp4" />
                  {video?.subtitle_status === "ready" && !hasMockPlaceholderTranscript && (
                    <track label="智能字幕" kind="subtitles" srcLang="zh" src={`${API_BASE}/api/videos/${videoId}/smart-subtitle/vtt`} default />
                  )}
                </video>
                {videoError && (
                  <div className="videoErrorOverlay">
                    <span>{videoError}</span>
                    <div className="videoErrorActions">
                      <button type="button" onClick={reloadVideoSource}>重新加载视频</button>
                      <a href={streamUrl} target="_blank" rel="noreferrer">打开直连播放源</a>
                    </div>
                  </div>
                )}
                {activeSubtitleText && (
                  <div className="activeSubtitleOverlay" style={subtitleOverlayStyle}>
                    {activeSubtitleText}
                  </div>
                )}
              </div>
              <div className="progressRail" onClick={(event) => {
                if (!videoRef.current || !video?.duration) return;
                const rect = (event.currentTarget as HTMLDivElement).getBoundingClientRect();
                const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
                jump(video.duration * ratio);
              }}>
                <div className="progressFill" style={{ width: `${progressPercent}%` }} />
                {timelineMarkers.map((time, index) => (
                  <span
                    key={`${time}-${index}`}
                    className="progressMarker"
                    style={{ left: `${video?.duration ? (time / video.duration) * 100 : 0}%` }}
                  />
                ))}
              </div>
              {displaySegments.length > 0 && (
                <div className="subtitleControls" aria-label="字幕显示设置">
                  <label className="subtitleControl">
                    <span>字号 <strong>{subtitleFontSize}px</strong></span>
                    <input
                      type="range"
                      min="14"
                      max="28"
                      value={subtitleFontSize}
                      onChange={(event) => setSubtitleFontSize(Number(event.currentTarget.value))}
                    />
                  </label>
                  <label className="subtitleControl">
                    <span>透明度 <strong>{subtitleOpacity}%</strong></span>
                    <input
                      type="range"
                      min="35"
                      max="90"
                      value={subtitleOpacity}
                      onChange={(event) => setSubtitleOpacity(Number(event.currentTarget.value))}
                    />
                  </label>
                  <label className="subtitleControl">
                    <span>离底部 <strong>{subtitleBottom}px</strong></span>
                    <input
                      type="range"
                      min="8"
                      max="80"
                      value={subtitleBottom}
                      onChange={(event) => setSubtitleBottom(Number(event.currentTarget.value))}
                    />
                  </label>
                </div>
              )}
            </>
          ) : (
            <div className="processingGate">
              <strong>{statusLabel(video?.status ?? "pending")}</strong>
              <p>视频会先完成字幕化、章节、重点和笔记生成，然后开放同步学习播放。</p>
              <div className="miniProgress gateProgress">
                <div className="miniProgressBar" style={{ width: `${video?.job_progress ?? 0}%` }} />
                <small>{video?.job_current_step ? statusLabel(video.job_current_step) : "等待处理"}</small>
              </div>
              {(video?.status === "pending" || video?.status === "queued") && <button className="primary" onClick={priorityProcess}>优先处理这个视频</button>}
              {video?.status === "failed" && <button className="primary" onClick={reprocess}>重新处理</button>}
            </div>
          )}
        </div>

        <div className="sidePanel">
          <div className="sidePanelHeader">
            <h3>同步字幕</h3>
            <span>自动跟随 · 点击跳转</span>
          </div>
          <div className="scrollList" ref={subtitleScrollRef}>
            {displaySegments.length === 0 && <p className="muted">{pendingCopy.subtitle}</p>}
            {hasMockPlaceholderTranscript && (
              <div className="transcriptWarning">
                <strong>这不是课程字幕。</strong>
                <span>这些记录来自 mock 测试流程，已经被隐藏。等切到真实 ASR 并重新处理后，这里才会显示可跳转字幕。</span>
              </div>
            )}
            {displaySegments.map((segment, index) => {
              const starInfos = segment.id ? starredBySegmentId.get(segment.id) ?? [] : [];
              const isStarred = starInfos.length > 0;
              const starLabels = starInfos.map((star) => starTagLabel(star.tag_label, star.star_color));
              const customStar = starInfos.find((star) => {
                const label = starTagLabel(star.tag_label, star.star_color);
                return !STAR_COLORS.some((item) => item.value === star.star_color && item.label === label);
              });
              const isBuiltInActive = (item: typeof STAR_COLORS[number]) => starInfos.some((star) => (
                star.star_color === item.value && starTagLabel(star.tag_label, star.star_color) === item.label
              ));
              return (
              <div
                key={segment.id ?? index}
                ref={(node) => {
                  subtitleLineRefs.current[index] = node;
                }}
                className={[
                  "line",
                  index === activeSegmentIndex ? "activeLine" : "",
                  isStarred ? "starredLine" : ""
                ].filter(Boolean).join(" ")}
              >
                <button className="lineJump" type="button" onClick={() => jump(segment.start_time)}>
                  <span>{formatTimeRange(segment.start_time, segment.end_time)}</span>
                  <strong>{segmentText(segment)}</strong>
                </button>
                <button
                  className={isStarred ? "starButton multiStarButton starButtonActive" : "starButton multiStarButton"}
                  type="button"
                  onClick={() => void toggleStarSegment(segment)}
                  disabled={!segment.id}
                  title={isStarred ? `已选：${starLabels.join("、")}。点击打开标签面板。` : "打开星标标签面板"}
                  aria-label={isStarred ? `已选：${starLabels.join("、")}。点击打开标签面板。` : "打开星标标签面板"}
                >
                  <span className="multiStarShape">
                    {STAR_COLORS.map((item, starIndex) => {
                      const active = isBuiltInActive(item);
                      return (
                        <i
                          key={item.value}
                          className={active ? `starPoint point${starIndex + 1} active` : `starPoint point${starIndex + 1}`}
                          style={{ "--star-color": item.color } as React.CSSProperties}
                        />
                      );
                    })}
                    <i
                      className={customStar ? "starCenter active" : "starCenter"}
                      style={{ "--star-color": customStar ? starColorMeta(customStar.star_color).color : "#ffffff" } as React.CSSProperties}
                    />
                  </span>
                </button>
                {segment.id && starDraft.segmentId === segment.id && (
                  <div className="starPicker">
                    <div className="starPickerTitle">
                      <strong>选择星标标签</strong>
                      <span>{formatTimeRange(segment.start_time, segment.end_time)}</span>
                    </div>
                    <div className="starColorRow">
                      {STAR_COLORS.map((item) => {
                        const active = isBuiltInActive(item);
                        return (
                          <button
                            key={item.value}
                            type="button"
                            className={active ? "starColorOption activeStarColor" : "starColorOption"}
                            onClick={() => void toggleStarTag(segment, item.value, item.label, active)}
                            style={{ "--star-color": item.color } as React.CSSProperties}
                          >
                            <span />
                            {active ? `取消${item.label}` : item.label}
                          </button>
                        );
                      })}
                    </div>
                    <label className="starTagInput">
                      <span>自定义标签</span>
                      <input
                        value={starDraft.label}
                        placeholder="例如：公式、要背、做题模板"
                        onChange={(event) => setStarDraft((draft) => ({ ...draft, label: event.currentTarget.value }))}
                      />
                    </label>
                    <label className="starTagInput starColorInput">
                      <span>自定义颜色</span>
                      <input
                        type="color"
                        value={starDraft.customColor}
                        onChange={(event) => setStarDraft((draft) => ({ ...draft, customColor: event.currentTarget.value, color: "custom" }))}
                      />
                    </label>
                    <div className="starPickerActions">
                      <button type="button" onClick={() => void saveStarSegment(segment)}>添加自定义标签</button>
                      <button type="button" onClick={() => setStarDraft({ segmentId: null, color: "gold", label: "", customColor: "#c4933a" })}>关闭</button>
                    </div>
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="learningGrid">
        <Timeline
          title="章节目录"
          emptyText={pendingCopy.chapter}
          items={visibleChapters.map((item) => ({
            time: item.start_time,
            endTime: item.end_time,
            title: item.title,
            body: item.summary,
            badge: `重要度 ${item.importance}`
          }))}
          onJump={jump}
        />
        <HighlightWorkspace
          segments={displaySegments}
          myHighlights={myHighlights}
          systemHighlights={systemHighlights}
          starCategories={starClusterCategories}
          rangeDraft={rangeDraft}
          rangePreviewSegments={rangePreviewSegments}
          activeTab={highlightTab}
          searchTerm={highlightSearch}
          loopCount={loopCount}
          loopPlayback={loopPlayback}
          activeLoopRangeId={activeLoopRangeId}
          message={highlightMessage}
          expandedHighlightIds={expandedHighlightIds}
          expandedStarClusterIds={expandedStarClusterIds}
          emptyText={pendingCopy.highlight}
          onTabChange={setHighlightTab}
          onSearchChange={setHighlightSearch}
          onLoopCountChange={setLoopCount}
          onDraftChange={setRangeDraft}
          onCreate={createManualHighlight}
          onJump={(time) => jump(time, { revealPlayer: true })}
          onPlayRanges={(ranges, startIndex) => playRanges(ranges, startIndex, { revealPlayer: true })}
          onStopLoop={stopLoopPlayback}
          onToggleExpanded={toggleHighlightExpanded}
          onToggleStarClusterExpanded={toggleStarClusterExpanded}
          onUpdateStarClusterTitle={updateStarClusterTitle}
          onEdit={editHighlight}
          onDelete={deleteHighlight}
          onExportMarkdown={exportHighlightMarkdown}
        />
        <article className="notePanel">
          <div className="notePanelHeader">
            <h3>AI 学习笔记</h3>
            {!hasMockPlaceholderTranscript && (
              <a className="ghostButton noteExportButton" href={`${API_BASE}/api/videos/${videoId}/export/markdown`} target="_blank" rel="noreferrer">
                导出 Markdown
              </a>
            )}
          </div>
          <pre>{visibleNote || pendingCopy.note}</pre>
        </article>
      </div>
    </section>
  );
}

function HighlightWorkspace({
  segments,
  myHighlights,
  systemHighlights,
  starCategories,
  rangeDraft,
  rangePreviewSegments,
  activeTab,
  searchTerm,
  loopCount,
  loopPlayback,
  activeLoopRangeId,
  message,
  expandedHighlightIds,
  expandedStarClusterIds,
  emptyText,
  onTabChange,
  onSearchChange,
  onLoopCountChange,
  onDraftChange,
  onCreate,
  onJump,
  onPlayRanges,
  onStopLoop,
  onToggleExpanded,
  onToggleStarClusterExpanded,
  onUpdateStarClusterTitle,
  onEdit,
  onDelete,
  onExportMarkdown
}: {
  segments: Segment[];
  myHighlights: Highlight[];
  systemHighlights: Highlight[];
  starCategories: StarClusterCategory[];
  rangeDraft: ManualRangeDraft;
  rangePreviewSegments: Segment[];
  activeTab: string;
  searchTerm: string;
  loopCount: number;
  loopPlayback: LoopPlaybackState | null;
  activeLoopRangeId: string;
  message: string;
  expandedHighlightIds: Set<number>;
  expandedStarClusterIds: Set<string>;
  emptyText: string;
  onTabChange: (tab: string) => void;
  onSearchChange: (value: string) => void;
  onLoopCountChange: (value: number) => void;
  onDraftChange: React.Dispatch<React.SetStateAction<ManualRangeDraft>>;
  onCreate: () => void;
  onJump: (time: number) => void;
  onPlayRanges: (ranges: PlaybackRange[], startIndex?: number) => void;
  onStopLoop: () => void;
  onToggleExpanded: (highlightId: number) => void;
  onToggleStarClusterExpanded: (clusterId: string) => void;
  onUpdateStarClusterTitle: (clusterId: string, title: string) => void;
  onEdit: (highlight: Highlight) => void;
  onDelete: (highlight: Highlight) => void;
  onExportMarkdown: (action: "copy" | "download") => void;
}) {
  const previewStart = rangePreviewSegments[0];
  const previewEnd = rangePreviewSegments[rangePreviewSegments.length - 1];
  const mineCategory = starCategories.find((category) => category.key === MINE_TAB_KEY);
  const categories = [
    mineCategory ?? { key: MINE_TAB_KEY, label: "我的重点", color: starColorMeta("gold").color, colorValue: "gold", clusters: [] },
    ...starCategories.filter((category) => category.key !== MINE_TAB_KEY)
  ];
  const activeCategory = categories.find((category) => category.key === activeTab);
  const query = searchTerm.trim().toLowerCase();
  const makeHighlightRow = (highlight: Highlight) => ({
    kind: "highlight" as const,
    id: `highlight:${highlight.id}`,
    start_time: highlight.start_time,
    range: highlightToPlaybackRange(highlight),
    highlight
  });
  const makeClusterRow = (cluster: StarCluster) => ({
    kind: "cluster" as const,
    id: `cluster:${cluster.id}`,
    start_time: cluster.start_time,
    range: clusterToPlaybackRange(cluster),
    cluster
  });
  const categoryRows = activeCategory
    ? [
        ...(activeTab === MINE_TAB_KEY ? myHighlights.filter((item) => !query || highlightSearchText(item).includes(query)).map(makeHighlightRow) : []),
        ...activeCategory.clusters.filter((item) => !query || clusterSearchText(item).includes(query)).map(makeClusterRow)
      ].sort((a, b) => a.start_time - b.start_time)
    : [];
  const systemRows = systemHighlights
    .filter((item) => !query || highlightSearchText(item).includes(query))
    .map(makeHighlightRow)
    .sort((a, b) => a.start_time - b.start_time);
  const activeRows = activeTab === SYSTEM_TAB_KEY ? systemRows : categoryRows;
  const activeLabel = activeTab === SYSTEM_TAB_KEY ? "系统候选" : activeCategory?.label ?? "我的重点";

  function playRow(index: number) {
    onPlayRanges(activeRows.map((row) => row.range), index);
  }

  return (
    <article className="timeline highlightWorkspace">
      <div className="highlightHeader">
        <div>
          <h3>重点时间轴</h3>
          <p>同色同标签星标会自动整理成区间卡片；每个分类都按视频时间顺序播放和复习。</p>
        </div>
        <div className="highlightExportActions">
          <button type="button" onClick={() => onExportMarkdown("copy")}>复制 Markdown</button>
          <button type="button" onClick={() => onExportMarkdown("download")}>导出 Markdown</button>
        </div>
      </div>

      <div className="manualRangeBox">
        <div className="manualRangeTitle">
          <strong>创建重点区间</strong>
          <span>不改同步字幕区，在这里选择起点和终点字幕。</span>
        </div>
        <div className="manualRangeGrid">
          <label>
            <span>起点字幕</span>
            <select
              value={rangeDraft.startSegmentId}
              onChange={(event) => onDraftChange((draft) => ({ ...draft, startSegmentId: event.currentTarget.value }))}
            >
              <option value="">选择起点</option>
              {segments.map((segment) => (
                <option key={segment.id ?? `${segment.start_time}-start`} value={segment.id ?? ""}>
                  {segmentOptionLabel(segment)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>终点字幕</span>
            <select
              value={rangeDraft.endSegmentId}
              onChange={(event) => onDraftChange((draft) => ({ ...draft, endSegmentId: event.currentTarget.value }))}
            >
              <option value="">选择终点</option>
              {segments.map((segment) => (
                <option key={segment.id ?? `${segment.start_time}-end`} value={segment.id ?? ""}>
                  {segmentOptionLabel(segment)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>重点类型</span>
            <select
              value={rangeDraft.highlightType}
              onChange={(event) => onDraftChange((draft) => ({ ...draft, highlightType: event.currentTarget.value }))}
            >
              {["知识点", "例题", "易错点", "老师强调", "课程安排", "学习方法", "自定义"].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="manualRangeField">
          <span>重点标题</span>
          <input
            value={rangeDraft.title}
            placeholder="可留空，系统会按区间字幕生成"
            onChange={(event) => onDraftChange((draft) => ({ ...draft, title: event.currentTarget.value }))}
          />
        </label>
        <label className="manualRangeField">
          <span>简短说明</span>
          <textarea
            value={rangeDraft.summary}
            placeholder="可留空，系统会按区间字幕生成"
            onChange={(event) => onDraftChange((draft) => ({ ...draft, summary: event.currentTarget.value }))}
          />
        </label>
        {rangePreviewSegments.length > 0 && previewStart && previewEnd && (
          <div className="rangePreview">
            <span>{formatTimeRange(previewStart.start_time, previewEnd.end_time)}</span>
            <strong>{segmentIndexLabel(previewStart)} - {segmentIndexLabel(previewEnd)}</strong>
            <p>{compactText(rangePreviewSegments.map(segmentText).join(" "), 160)}</p>
          </div>
        )}
        <button className="primary" type="button" onClick={onCreate} disabled={segments.length === 0}>
          保存到我的重点
        </button>
        {message && <div className="notice highlightNotice">{message}</div>}
      </div>

      <div className="highlightTabs">
        {categories.map((category) => {
          const count = category.clusters.length + (category.key === MINE_TAB_KEY ? myHighlights.length : 0);
          return (
            <button
              key={category.key}
              className={activeTab === category.key ? "activeHighlightTab" : ""}
              onClick={() => onTabChange(category.key)}
              style={{ "--tab-color": category.color } as React.CSSProperties}
            >
              {category.label} <span>{count}</span>
            </button>
          );
        })}
        <button className={activeTab === SYSTEM_TAB_KEY ? "activeHighlightTab" : ""} onClick={() => onTabChange(SYSTEM_TAB_KEY)}>
          系统候选 <span>{systemHighlights.length}</span>
        </button>
      </div>

      <form
        className="highlightSearchRow"
        onSubmit={(event) => {
          event.preventDefault();
          if (activeRows.length > 0) playRow(0);
        }}
      >
        <input
          value={searchTerm}
          placeholder={`搜索${activeLabel}，回车播放第一条匹配`}
          onChange={(event) => onSearchChange(event.currentTarget.value)}
        />
        <button type="submit" disabled={activeRows.length === 0}>搜索播放</button>
        {searchTerm && <button type="button" onClick={() => onSearchChange("")}>清空</button>}
        <label>
          <span>区间循环</span>
          <input
            type="number"
            min="1"
            max="9"
            value={loopCount}
            onChange={(event) => onLoopCountChange(Math.min(9, Math.max(1, Number(event.currentTarget.value) || DEFAULT_LOOP_COUNT)))}
          />
          <span>遍</span>
        </label>
      </form>

      {loopPlayback && (
        <div className="loopStatus">
          <span>
            正在循环：{loopPlayback.ranges[loopPlayback.activeIndex]?.title}
            {" · "}
            剩余本区间 {loopPlayback.remainingRepeats}/{loopPlayback.repeatCount} 遍
          </span>
          <button type="button" onClick={onStopLoop}>停止循环</button>
        </div>
      )}

      <div className="highlightList">
        {activeRows.length === 0 && (
          <p className="muted">
            {searchTerm
              ? `没有在“${activeLabel}”里找到匹配内容。`
              : activeTab === SYSTEM_TAB_KEY ? "暂无系统候选。当前优先使用星标分类和我的重点。" : emptyText}
          </p>
        )}
        {activeRows.map((row, index) => row.kind === "highlight" ? (
          <HighlightCard
            key={row.id}
            order={index + 1}
            highlight={row.highlight}
            expanded={expandedHighlightIds.has(row.highlight.id)}
            activeLoop={activeLoopRangeId === row.range.id}
            mode={activeTab === SYSTEM_TAB_KEY ? "system" : "mine"}
            onJump={onJump}
            onPlayRange={() => playRow(index)}
            onToggleExpanded={onToggleExpanded}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        ) : (
          <StarClusterCard
            key={row.id}
            order={index + 1}
            cluster={row.cluster}
            expanded={expandedStarClusterIds.has(row.cluster.id)}
            activeLoop={activeLoopRangeId === row.range.id}
            onJump={onJump}
            onPlayRange={() => playRow(index)}
            onToggleExpanded={onToggleStarClusterExpanded}
            onUpdateTitle={onUpdateStarClusterTitle}
          />
        ))}
      </div>
    </article>
  );
}

function HighlightCard({
  order,
  highlight,
  expanded,
  activeLoop,
  mode,
  onJump,
  onPlayRange,
  onToggleExpanded,
  onEdit,
  onDelete
}: {
  order: number;
  highlight: Highlight;
  expanded: boolean;
  activeLoop: boolean;
  mode: "mine" | "system";
  onJump: (time: number) => void;
  onPlayRange: () => void;
  onToggleExpanded: (highlightId: number) => void;
  onEdit: (highlight: Highlight) => void;
  onDelete: (highlight: Highlight) => void;
}) {
  const sources = highlight.sources ?? [];
  const firstSource = sources[0];
  const lastSource = sources[sources.length - 1];
  const tags = starTagItems(sources);
  const subtitleRange = firstSource && lastSource
    ? `${segmentIndexLabel(firstSource)} - ${segmentIndexLabel(lastSource)}`
    : `字幕区间 ${highlight.source_segment_count ?? 0} 条`;
  const cleanContent = expanded && sources.length ? cleanParagraphFromSources(sources) : "";
  const jumpToSource = (event: React.MouseEvent<HTMLButtonElement>, time: number) => {
    event.currentTarget.blur();
    onJump(time);
  };

  return (
    <article className={mode === "mine" ? "rangeHighlightCard" : "rangeHighlightCard systemRangeCard"}>
      <div className="rangeOrderBadge">{order}</div>
      <div className="rangeCardBody">
      <div className="rangeCardTop">
        <span>{formatTimeRange(highlight.start_time, highlight.end_time)}</span>
        <em>{mode === "mine" ? "用户手动划定区间" : `系统候选 · ${highlight.type}`}</em>
      </div>
      <h4>{highlight.title}</h4>
      {tags.length > 0 && (
        <div className="highlightTagRow">
          {tags.map((tag) => (
            <span key={`${tag.color}-${tag.label}`} style={{ "--tag-color": tag.color } as React.CSSProperties}>
              {tag.label}
            </span>
          ))}
        </div>
      )}
      <p>{highlight.content}</p>
      <div className="rangeMeta">
        <span>字幕：{subtitleRange}</span>
        <span>类型：{highlight.type || "自定义"}</span>
      </div>
      <div className="rangeActions">
        <button type="button" onClick={() => onJump(highlight.start_time)}>跳转播放</button>
        <button type="button" className={activeLoop ? "activeLoopButton" : ""} onClick={onPlayRange}>{activeLoop ? "循环中" : "循环播放"}</button>
        <button type="button" className="collapseButton" onClick={() => onToggleExpanded(highlight.id)}>
          {expanded ? "▴ 收起" : "▾ 展开"}
        </button>
        {mode === "mine" && <button type="button" onClick={() => onEdit(highlight)}>编辑</button>}
        {mode === "mine" && <button type="button" onClick={() => onDelete(highlight)}>删除</button>}
      </div>
      {expanded && (
        <div className="rangeSources">
          {sources.length === 0 ? (
            <p>{highlight.content}</p>
          ) : (
            <>
              <strong>该重点区间内的原始字幕</strong>
              <p>{cleanContent}</p>
              {sources.map((source) => (
                <button key={`${source.segment_id}-${source.start_time}`} type="button" onClick={(event) => jumpToSource(event, source.start_time)}>
                  <span>{formatTimeRange(source.start_time, source.end_time)} · {sourceRoleLabel(source.source_role)}</span>
                  <p>{segmentText(source)}</p>
                </button>
              ))}
            </>
          )}
        </div>
      )}
      </div>
    </article>
  );
}

function StarClusterCard({
  order,
  cluster,
  expanded,
  activeLoop,
  onJump,
  onPlayRange,
  onToggleExpanded,
  onUpdateTitle
}: {
  order: number;
  cluster: StarCluster;
  expanded: boolean;
  activeLoop: boolean;
  onJump: (time: number) => void;
  onPlayRange: () => void;
  onToggleExpanded: (clusterId: string) => void;
  onUpdateTitle: (clusterId: string, title: string) => void;
}) {
  const firstSource = cluster.sources[0];
  const visibleSources = expanded ? cluster.sources : cluster.sources.slice(0, 1);
  const preview = firstSource ? segmentText(firstSource) : "";
  const hasSideNotes = cluster.sideNotes.length > 0;
  const jumpToSource = (event: React.MouseEvent<HTMLButtonElement>, time: number) => {
    event.currentTarget.blur();
    onJump(time);
  };

  return (
    <article className="rangeHighlightCard starClusterCard" style={{ "--cluster-color": cluster.color } as React.CSSProperties}>
      <div className="rangeOrderRail">
        <div className="rangeOrderBadge">{order}</div>
        {hasSideNotes && (
          <div className="sideNoteBranch">
            <div className="branchLine" />
            <div className="sideNotePopover">
              <strong>旁支单标</strong>
              {cluster.sideNotes.map((source, index) => (
                <button key={`${source.segment_id ?? index}-${source.start_time}-${source.star_color}`} type="button" onClick={(event) => jumpToSource(event, source.start_time)}>
                  <span>{formatTimeRange(source.start_time, source.end_time)}</span>
                  <em style={{ "--tag-color": starColorMeta(source.star_color).color } as React.CSSProperties}>
                    {starTagLabel(source.tag_label, source.star_color)}
                  </em>
                  <p>{segmentText(source)}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="rangeCardBody">
        <div className="rangeCardTop">
          <span>{formatTimeRange(cluster.start_time, cluster.end_time)}</span>
          <em>
            {cluster.label} · {cluster.groupKind === "pair" ? `端点 ${cluster.anchorCount} 条` : "单句"}
            {hasSideNotes ? ` · 旁支 ${cluster.sideNotes.length} 条` : ""} · 字幕 {cluster.sources.length} 条
          </em>
        </div>
        <div className="clusterTitleRow">
          <input
            value={cluster.title === cluster.defaultTitle ? "" : cluster.title}
            placeholder={cluster.defaultTitle}
            onChange={(event) => onUpdateTitle(cluster.id, event.currentTarget.value)}
            aria-label="修改这个重点区间标题"
          />
          <button type="button" className="collapseIconButton" onClick={() => onToggleExpanded(cluster.id)} aria-label={expanded ? "收起字幕" : "展开字幕"}>
            {expanded ? "▴" : "▾"}
          </button>
        </div>
        <div className="highlightTagRow">
          <span style={{ "--tag-color": cluster.color } as React.CSSProperties}>{cluster.label}</span>
        </div>
        <p>{expanded ? cleanParagraphFromSources(cluster.sources) : preview}</p>
        <div className="rangeActions">
          <button type="button" onClick={() => onJump(cluster.start_time)}>跳转播放</button>
          <button type="button" className={activeLoop ? "activeLoopButton" : ""} onClick={onPlayRange}>{activeLoop ? "循环中" : "循环播放"}</button>
          <button type="button" className="collapseButton" onClick={() => onToggleExpanded(cluster.id)}>
            {expanded ? "▴ 收起字幕" : "▾ 展开字幕"}
          </button>
        </div>
        <div className={expanded ? "rangeSources clusterSources expanded" : "rangeSources clusterSources"}>
          <strong>{expanded ? "该区间内的全部字幕" : "折叠预览：第一条字幕"}</strong>
          {visibleSources.map((source, sourceIndex) => (
            <button
              key={`${source.segment_id ?? sourceIndex}-${source.start_time}`}
              className={source.source_role === "anchor" ? "clusterSourceLine anchor" : "clusterSourceLine"}
              type="button"
              onClick={(event) => jumpToSource(event, source.start_time)}
            >
              <span>[{formatTimeRange(source.start_time, source.end_time)}]</span>
              <p>{segmentText(source)}</p>
            </button>
          ))}
        </div>
        {expanded && hasSideNotes && (
          <div className="rangeSources sideNoteInline">
            <strong>该区间旁支单标</strong>
            {cluster.sideNotes.map((source, sourceIndex) => (
              <button key={`${source.segment_id ?? sourceIndex}-${source.start_time}-${source.star_color}`} type="button" onClick={(event) => jumpToSource(event, source.start_time)}>
                <span>[{formatTimeRange(source.start_time, source.end_time)}] · {starTagLabel(source.tag_label, source.star_color)}</span>
                <p>{segmentText(source)}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function Timeline({
  title,
  items,
  onJump,
  emptyText
}: {
  title: string;
  items: TimelineItem[];
  onJump: (time: number) => void;
  emptyText: string;
}) {
  return (
    <article className="timeline">
      <h3>{title}</h3>
      {items.length === 0 && <p className="muted">{emptyText}</p>}
      {items.map((item, index) => (
        <article key={index} className={item.tone === "starred" ? "timelineCard timelineStarred" : "timelineCard"}>
          <button className="timelineJump" type="button" onClick={() => onJump(item.time)}>
            <span>{formatTimeRange(item.time, item.endTime)}</span>
            <strong>{item.title}</strong>
            <em>{item.badge}</em>
            {item.sourceCount ? <small className="timelineSource">来源字幕 {item.sourceCount} 条</small> : null}
            <p>{item.body}</p>
          </button>
          {item.sources?.length ? (
            <div className="timelineSources">
              <strong>来源字幕 / 上下文</strong>
              {item.sources.map((source, sourceIndex) => (
                <button
                  key={`${source.segment_id ?? sourceIndex}-${source.start_time}`}
                  className={source.source_role === "anchor" ? "timelineSourceLine anchor" : "timelineSourceLine"}
                  type="button"
                  onClick={() => onJump(source.start_time)}
                >
                  <span>{formatTimeRange(source.start_time, source.end_time)} · {sourceRoleLabel(source.source_role)}</span>
                  <p>{segmentText(source)}</p>
                </button>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </article>
  );
}

function SearchPage({ onOpen }: { onOpen: (videoId: number, start?: number) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [message, setMessage] = useState("");

  async function runSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!q.trim()) return;
    try {
      const res = await api<{ data: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q.trim())}`);
      setHits(res.data);
      setMessage(res.data.length ? "" : "没有找到匹配结果。");
    } catch (error) {
      setMessage(String(error));
    }
  }

  return (
    <section className="panel">
      <h1>全文搜索</h1>
      <form className="searchBox" onSubmit={runSearch}>
        <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="搜索标题、文件夹、字幕、重点、笔记..." />
        <button className="primary">搜索</button>
      </form>
      {message && <div className="notice">{message}</div>}
      <div className="searchResults">
        {hits.map((hit, index) => (
          <button key={index} onClick={() => onOpen(hit.video_id, hit.start_time)}>
            <span>{hit.hit_type} · {formatTime(hit.start_time)}</span>
            <strong>{hit.video_title}</strong>
            <p>{hit.content}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData>({});
  const [message, setMessage] = useState("");

  useEffect(() => {
    api<{ data: SettingsData }>("/api/settings").then((res) => setSettings(res.data));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const videoDirsText = String(settings.video_dirs_text ?? "");
    const videoDirs = videoDirsText
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);
    const payload = {
      video_dir: videoDirs[0] ?? String(settings.video_dir ?? ""),
      video_dirs: videoDirs,
      auto_scan: Boolean(settings.auto_scan),
      scan_interval_seconds: Number(settings.scan_interval_seconds ?? 300),
      scan_recursive: Boolean(settings.scan_recursive),
      auto_process_new_videos: Boolean(settings.auto_process_new_videos),
      auto_process_max_per_round: Number(settings.auto_process_max_per_round ?? 1)
    };
    const res = await api<{ data: SettingsData }>("/api/settings", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    setSettings((old) => ({ ...old, ...res.data }));
    setMessage("设置已保存。自动扫描线程会按新的配置继续运行。");
  }

  const videoDirsValue = String(
    settings.video_dirs_text ??
      (Array.isArray(settings.video_dirs)
        ? settings.video_dirs.join("\n")
        : settings.video_dir ?? "")
  );

  return (
    <section className="panel">
      <h1>设置</h1>
      <p className="muted">建议默认只开自动扫描，不开自动处理。开启自动处理新视频后，系统会自动调用语音识别和 AI 分析接口，可能产生 API 费用。</p>
      <form className="settingsForm" onSubmit={save}>
        <label>
          NAS 视频目录（每行一个）
          <textarea
            value={videoDirsValue}
            onChange={(event) => setSettings((old) => ({ ...old, video_dirs_text: event.target.value }))}
            placeholder={"例如：\n/videos\n/videos_upload"}
          />
        </label>
        <label className="switchRow">
          <input
            type="checkbox"
            checked={Boolean(settings.auto_scan)}
            onChange={(event) => setSettings((old) => ({ ...old, auto_scan: event.target.checked }))}
          />
          启用自动扫描
        </label>
        <label>
          扫描间隔（秒）
          <input
            type="number"
            value={String(settings.scan_interval_seconds ?? 300)}
            onChange={(event) => setSettings((old) => ({ ...old, scan_interval_seconds: Number(event.target.value) }))}
          />
        </label>
        <label className="switchRow">
          <input
            type="checkbox"
            checked={Boolean(settings.scan_recursive)}
            onChange={(event) => setSettings((old) => ({ ...old, scan_recursive: event.target.checked }))}
          />
          扫描子目录
        </label>
        <label className="switchRow warningRow">
          <input
            type="checkbox"
            checked={Boolean(settings.auto_process_new_videos)}
            onChange={(event) => setSettings((old) => ({ ...old, auto_process_new_videos: event.target.checked }))}
          />
          自动处理新视频
        </label>
        <label>
          每轮自动处理数量
          <input
            type="number"
            value={String(settings.auto_process_max_per_round ?? 1)}
            onChange={(event) => setSettings((old) => ({ ...old, auto_process_max_per_round: Number(event.target.value) }))}
          />
        </label>
        <button className="primary">保存设置</button>
      </form>
      {message && <div className="notice">{message}</div>}
      <pre className="settingsDump">{JSON.stringify(settings, null, 2)}</pre>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
