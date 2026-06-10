CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    file_hash TEXT,
    duration REAL,
    file_size INTEGER,
    status TEXT DEFAULT 'pending',
    folder TEXT,
    extension TEXT,
    modified_time REAL,
    quick_hash TEXT,
    subtitle_status TEXT DEFAULT 'none',
    analysis_status TEXT DEFAULT 'none',
    note_status TEXT DEFAULT 'none',
    last_play_position REAL DEFAULT 0,
    last_opened_at DATETIME,
    missing INTEGER DEFAULT 0,
    error_stage TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    cleaned_text TEXT,
    segment_index INTEGER,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    summary TEXT,
    importance INTEGER DEFAULT 3,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS highlights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    type TEXT,
    title TEXT,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 3,
    source_method TEXT DEFAULT 'auto',
    status TEXT DEFAULT 'candidate',
    importance_reason TEXT,
    source_segment_count INTEGER DEFAULT 0,
    review_status TEXT DEFAULT '未复习',
    review_count INTEGER DEFAULT 0,
    last_reviewed_at DATETIME,
    user_edited_fields TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS highlight_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    highlight_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    source_role TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(highlight_id) REFERENCES highlights(id) ON DELETE CASCADE,
    FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
    UNIQUE(highlight_id, segment_id)
);

CREATE TABLE IF NOT EXISTS starred_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    segment_id INTEGER NOT NULL,
    note TEXT,
    star_color TEXT DEFAULT 'gold',
    tag_label TEXT,
    tag_key TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
    UNIQUE(video_id, segment_id, star_color, tag_key)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE,
    markdown_content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 0,
    current_step TEXT,
    total_steps INTEGER DEFAULT 0,
    started_at DATETIME,
    finished_at DATETIME,
    error_stage TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS playback_positions (
    video_id INTEGER PRIMARY KEY,
    current_time REAL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_dir TEXT NOT NULL,
    found_count INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    missing_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_transcript_video_time ON transcript_segments(video_id, start_time);
CREATE INDEX IF NOT EXISTS idx_chapters_video_time ON chapters(video_id, start_time);
CREATE INDEX IF NOT EXISTS idx_highlights_video_time ON highlights(video_id, start_time);
CREATE INDEX IF NOT EXISTS idx_highlight_sources_highlight ON highlight_sources(highlight_id);
CREATE INDEX IF NOT EXISTS idx_highlight_sources_segment ON highlight_sources(segment_id);
CREATE INDEX IF NOT EXISTS idx_starred_segments_video_time ON starred_segments(video_id, created_at);
