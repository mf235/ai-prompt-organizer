# -*- coding: utf-8 -*-
"""
AI Prompt Organizer v36

AI生成用プロンプトを、タイトル・タグ・説明・画像付きで管理するローカルGUIツール。
PySide6 + SQLite で動作します。

必要環境:
    pip install PySide6 opencv-python

保存場所:
    スクリプトと同じフォルダに prompt_organizer.db と assets/ を作成します。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    from PySide6.QtCore import QLockFile, QMimeData, QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
    from PySide6.QtGui import QAction, QActionGroup, QColor, QDrag, QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QPixmapCache
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLayout,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QSpinBox,
        QStatusBar,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover - 実行環境向けメッセージ
    print("PySide6 が見つかりません。以下を実行してください:")
    print("pip install PySide6")
    print(f"詳細: {exc}")
    sys.exit(1)


APP_NAME = "AI Prompt Organizer"
APP_VERSION = "v1.12.1"
APP_AUTHOR = "MF235"
APP_CONTACT_X = "https://x.com/MF235XBR"
APP_REPOSITORY = "https://github.com/mf235/ai-prompt-organizer"
APP_USER_MODEL_ID = "chappy.ai-prompt-organizer"
WINDOW_ICON_RELATIVE = ("resources", "icons", "window.png")
EXE_ICON_RELATIVE = ("resources", "icons", "app.ico")
DB_FILENAME = "prompt_organizer.db"
INTERNAL_MATERIAL_DRAG_MIME = "application/x-ai-prompt-organizer-material-drag"
BACKUP_DIR_NAME = "_backup"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_MEDIA_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".css", ".js", ".py"}
DOCUMENT_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
CODE_EXTS = {".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".h", ".cs", ".java", ".rs", ".go"}


DEFAULT_CATEGORY_COLORS = {
    "メディア": "#4f8cff",
    "用途": "#b26cff",
    "状態": "#ff9f43",
    "プロジェクト": "#35b779",
    "AI": "#00a6b8",
    "custom": "#777777",
}


DEFAULT_TAG_CATEGORIES = {
    "メディア": ["画像", "動画", "音楽", "テキスト", "ポーズ", "ロゴ", "UI"],
    "用途": ["キャラ", "衣装", "表情", "背景", "構図", "カメラ", "ライティング", "画風", "ネガティブ", "動画モーション", "セリフ"],
    "状態": ["お気に入り", "成功", "微妙", "要修正", "指が壊れる", "構図は良い", "色味は良い", "再利用可", "没"],
    "AI": ["ChatGPT", "Gemini", "Grok", "Midjourney", "Stable Diffusion", "Flux", "Suno", "Kling", "Runway", "Google Flow"],
    "プロジェクト": ["Layer Breaker", "ちゃっぴー", "Dark Chappy", "Stage背景", "BOSS", "年齢確認"],
}


DEFAULT_TAG_PRESETS = {
    "画像生成基本": ["画像", "画風"],
    "動画生成基本": ["動画", "動画モーション", "カメラ"],
    "ポーズ研究": ["画像", "ポーズ", "構図"],
    "キャラ設定": ["画像", "キャラ", "表情"],
    "背景素材": ["画像", "背景", "ライティング"],
    "Layer Breaker背景": ["画像", "Layer Breaker", "背景"],
    "ちゃっぴー": ["ちゃっぴー", "キャラ"],
}

META_OPTION_FIELDS = ("engine", "model", "project")
META_OPTION_LABELS = {
    "engine": "生成AI",
    "model": "モデル",
    "project": "プロジェクト",
}
META_OPTION_FIELDS_BY_LABEL = {value: key for key, value in META_OPTION_LABELS.items()}


@dataclass
class PromptRow:
    id: int
    title: str
    prompt: str
    negative_prompt: str
    description: str
    engine: str
    model: str
    project: str
    rating: int
    favorite: int
    tags: list[str]
    cover_thumb: str
    updated_at: str


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                negative_prompt TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                project TEXT NOT NULL DEFAULT '',
                rating INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0,
                parent_prompt_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(parent_prompt_id) REFERENCES prompts(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_categories (
                name TEXT PRIMARY KEY,
                color TEXT NOT NULL DEFAULT '#777777'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'custom',
                color TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.ensure_column("tags", "visible", "INTEGER NOT NULL DEFAULT 1")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_tags (
                prompt_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY(prompt_id, tag_id),
                FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                caption TEXT NOT NULL DEFAULT '',
                is_cover INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
            )
            """
        )
        self.ensure_column("images", "media_type", "TEXT NOT NULL DEFAULT 'image'")
        self.ensure_column("images", "original_name", "TEXT NOT NULL DEFAULT ''")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_options (
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(field, value)
            )
            """
        )
        self.conn.commit()
        self.seed_defaults_if_needed()
        self.seed_meta_options_from_prompts_if_needed()

    def seed_defaults_if_needed(self) -> None:
        """Seed default tags only for a brand-new database.

        Older versions called seed_defaults() on every startup. That meant
        a user-deleted default tag was silently recreated after restart.
        If this database already has any tags or presets, treat it as an
        existing user database and only mark the seed as completed.
        """
        seeded = self.get_setting("defaults_seeded_v1", "")
        if seeded == "1":
            return

        tag_count = int(self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
        preset_count = int(self.conn.execute("SELECT COUNT(*) FROM tag_presets").fetchone()[0])
        if tag_count > 0 or preset_count > 0:
            self.set_setting("defaults_seeded_v1", "1")
            return

        self.seed_defaults()
        self.set_setting("defaults_seeded_v1", "1")

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {str(row["name"]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def seed_defaults(self) -> None:
        for category, color in DEFAULT_CATEGORY_COLORS.items():
            self.ensure_category(category, color)
        for category, names in DEFAULT_TAG_CATEGORIES.items():
            for name in names:
                self.ensure_tag(name, category)
        for name, tags in DEFAULT_TAG_PRESETS.items():
            if not self.get_tag_preset_by_name(name):
                self.save_tag_preset(None, name, tags)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def backup_to(self, dest_path: Path) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.commit()
        backup_conn = sqlite3.connect(str(dest_path))
        try:
            self.conn.backup(backup_conn)
        finally:
            backup_conn.close()

    def now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def ensure_category(self, name: str, color: str = "") -> None:
        name = normalize_category(name)
        if not name:
            name = "custom"
        color = normalize_hex_color(color) or DEFAULT_CATEGORY_COLORS.get(name, "#777777")
        self.conn.execute(
            "INSERT OR IGNORE INTO tag_categories(name, color) VALUES(?, ?)",
            (name, color),
        )

    def set_category_color(self, name: str, color: str) -> None:
        name = normalize_category(name) or "custom"
        color = normalize_hex_color(color) or DEFAULT_CATEGORY_COLORS.get(name, "#777777")
        self.conn.execute(
            "INSERT INTO tag_categories(name, color) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET color = excluded.color",
            (name, color),
        )
        self.conn.commit()

    def get_category_color(self, name: str) -> str:
        name = normalize_category(name) or "custom"
        row = self.conn.execute("SELECT color FROM tag_categories WHERE name = ?", (name,)).fetchone()
        if row:
            return str(row["color"])
        return DEFAULT_CATEGORY_COLORS.get(name, "#777777")

    def list_categories(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT name, color FROM tag_categories ORDER BY name COLLATE NOCASE").fetchall()

    def find_tag_by_name_nocase(self, name: str) -> sqlite3.Row | None:
        name = normalize_tag(name)
        if not name:
            return None
        return self.conn.execute(
            "SELECT id, name FROM tags WHERE name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
            (name,),
        ).fetchone()

    def canonical_tag_name(self, name: str) -> str:
        name = normalize_tag(name)
        if not name:
            return ""
        row = self.find_tag_by_name_nocase(name)
        if row:
            return str(row["name"])
        return name

    def ensure_tag(self, name: str, category: str = "custom", color: str = "") -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("empty tag")
        category = normalize_category(category) or "custom"
        self.ensure_category(category, DEFAULT_CATEGORY_COLORS.get(category, "#777777"))
        color = normalize_hex_color(color)
        cur = self.conn.cursor()
        row = self.find_tag_by_name_nocase(name)
        if row:
            return int(row["id"])
        cur.execute("INSERT INTO tags(name, category, color) VALUES(?, ?, ?)", (name, category, color))
        return int(cur.lastrowid)

    def update_tag(self, tag_id: Optional[int], name: str, category: str, color: str = "", visible: bool = True) -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("タグ名が空です。")
        category = normalize_category(category) or "custom"
        color = normalize_hex_color(color)
        visible_value = 1 if visible else 0
        self.ensure_category(category)
        cur = self.conn.cursor()
        if tag_id is None:
            row = self.find_tag_by_name_nocase(name)
            if row:
                tag_id = int(row["id"])
                cur.execute("UPDATE tags SET category = ?, color = ?, visible = ? WHERE id = ?", (category, color, visible_value, tag_id))
            else:
                cur.execute("INSERT INTO tags(name, category, color, visible) VALUES(?, ?, ?, ?)", (name, category, color, visible_value))
                tag_id = int(cur.lastrowid)
        else:
            cur.execute("UPDATE tags SET name = ?, category = ?, color = ?, visible = ? WHERE id = ?", (name, category, color, visible_value, tag_id))
        self.conn.commit()
        return int(tag_id)

    def delete_tag(self, tag_id: int) -> None:
        row = self.conn.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)).fetchone()
        tag_name = normalize_tag(str(row["name"])) if row else ""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

        # Also remove the deleted tag name from presets. Otherwise applying
        # an old preset later would recreate the tag via ensure_tag().
        if tag_name:
            preset_rows = cur.execute("SELECT id, tags_json FROM tag_presets").fetchall()
            for preset in preset_rows:
                try:
                    tags = json.loads(str(preset["tags_json"] or "[]"))
                except Exception:
                    tags = []
                cleaned = [t for t in tags if normalize_tag(str(t)) != tag_name]
                if cleaned != tags:
                    cur.execute(
                        "UPDATE tag_presets SET tags_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(cleaned, ensure_ascii=False), self.now(), int(preset["id"])),
                    )
        self.conn.commit()

    def get_tag(self, tag_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()

    def get_effective_tag_color(self, tag_name: str) -> str:
        row = self.conn.execute(
            """
            SELECT t.color AS color, c.color AS category_color
            FROM tags t
            LEFT JOIN tag_categories c ON c.name = t.category
            WHERE t.name = ?
            """,
            (tag_name,),
        ).fetchone()
        if not row:
            return DEFAULT_CATEGORY_COLORS.get("custom", "#777777")
        return normalize_hex_color(str(row["color"] or "")) or normalize_hex_color(str(row["category_color"] or "")) or "#777777"

    def set_prompt_tags(self, prompt_id: int, tag_names: Iterable[str]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        seen: set[str] = set()
        for tag_name in tag_names:
            tag_name = self.canonical_tag_name(str(tag_name))
            key = tag_name.casefold()
            if not tag_name or key in seen:
                continue
            seen.add(key)
            tag_id = self.ensure_tag(tag_name)
            cur.execute("INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) VALUES(?, ?)", (prompt_id, tag_id))
        self.conn.commit()

    def create_prompt(
        self,
        title: str = "新規プロンプト",
        prompt: str = "",
        negative_prompt: str = "",
        description: str = "",
        engine: str = "",
        model: str = "",
        project: str = "",
        rating: int = 0,
        favorite: int = 0,
        parent_prompt_id: Optional[int] = None,
    ) -> int:
        now = self.now()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO prompts(title, prompt, negative_prompt, description, engine, model, project, rating, favorite, parent_prompt_id, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, prompt, negative_prompt, description, engine, model, project, rating, favorite, parent_prompt_id, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_prompt(self, prompt_id: int, data: dict) -> None:
        fields = [
            "title",
            "prompt",
            "negative_prompt",
            "description",
            "engine",
            "model",
            "project",
            "rating",
            "favorite",
        ]
        values = [data.get(field, "") for field in fields]
        values.append(self.now())
        values.append(prompt_id)
        sql = """
            UPDATE prompts
            SET title = ?, prompt = ?, negative_prompt = ?, description = ?, engine = ?, model = ?, project = ?,
                rating = ?, favorite = ?, updated_at = ?
            WHERE id = ?
        """
        self.conn.execute(sql, values)
        self.conn.commit()

    def delete_prompt(self, prompt_id: int) -> None:
        self.conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        self.conn.commit()

    def get_prompt(self, prompt_id: int) -> sqlite3.Row | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        return cur.fetchone()

    def list_prompt_tags(self, prompt_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN prompt_tags pt ON pt.tag_id = t.id
            WHERE pt.prompt_id = ?
            ORDER BY t.category, t.name
            """,
            (prompt_id,),
        ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_tags_with_counts(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT t.id, t.name, t.category, t.color, t.visible, COALESCE(c.color, '#777777') AS category_color,
                   COUNT(pt.prompt_id) AS count
            FROM tags t
            LEFT JOIN prompt_tags pt ON pt.tag_id = t.id
            LEFT JOIN tag_categories c ON c.name = t.category
            GROUP BY t.id
            ORDER BY CASE t.category
                WHEN 'メディア' THEN 0
                WHEN '用途' THEN 1
                WHEN '状態' THEN 2
                WHEN 'プロジェクト' THEN 3
                WHEN 'AI' THEN 4
                ELSE 5
            END, t.name COLLATE NOCASE
            """
        ).fetchall()

    def list_prompts(self) -> list[PromptRow]:
        rows = self.conn.execute(
            """
            SELECT p.*,
                   COALESCE((
                       SELECT i.thumbnail_path FROM images i
                       WHERE i.prompt_id = p.id
                       ORDER BY i.is_cover DESC, i.sort_order ASC, i.id ASC
                       LIMIT 1
                   ), '') AS cover_thumb
            FROM prompts p
            ORDER BY p.updated_at DESC, p.id DESC
            """
        ).fetchall()
        result: list[PromptRow] = []
        for row in rows:
            tags = self.list_prompt_tags(int(row["id"]))
            result.append(
                PromptRow(
                    id=int(row["id"]),
                    title=str(row["title"]),
                    prompt=str(row["prompt"]),
                    negative_prompt=str(row["negative_prompt"]),
                    description=str(row["description"]),
                    engine=str(row["engine"]),
                    model=str(row["model"]),
                    project=str(row["project"]),
                    rating=int(row["rating"]),
                    favorite=int(row["favorite"]),
                    tags=tags,
                    cover_thumb=str(row["cover_thumb"] or ""),
                    updated_at=str(row["updated_at"]),
                )
            )
        return result

    def add_image(
        self,
        prompt_id: int,
        file_path: str,
        thumbnail_path: str = "",
        caption: str = "",
        is_cover: int = 0,
        media_type: str = "image",
        original_name: str = "",
    ) -> int:
        cur = self.conn.cursor()
        max_sort = cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["max_sort"]
        count = cur.execute("SELECT COUNT(*) AS c FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["c"]
        if count == 0:
            is_cover = 1
        cur.execute(
            """
            INSERT INTO images(prompt_id, file_path, thumbnail_path, sort_order, caption, is_cover, created_at, media_type, original_name)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt_id, file_path, thumbnail_path, int(max_sort) + 1, caption, is_cover, self.now(), media_type, original_name),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_image_thumbnail(self, image_id: int, thumbnail_path: str) -> None:
        self.conn.execute("UPDATE images SET thumbnail_path = ? WHERE id = ?", (thumbnail_path, image_id))
        self.conn.commit()

    def update_image_file_path(self, image_id: int, file_path: str) -> None:
        self.conn.execute("UPDATE images SET file_path = ? WHERE id = ?", (file_path, image_id))
        self.conn.commit()

    def list_images(self, prompt_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM images WHERE prompt_id = ? ORDER BY is_cover DESC, sort_order ASC, id ASC",
            (prompt_id,),
        ).fetchall()

    def get_image(self, image_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()

    def delete_image(self, image_id: int) -> None:
        row = self.get_image(image_id)
        if not row:
            return
        prompt_id = int(row["prompt_id"])
        self.conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        has_cover = self.conn.execute(
            "SELECT COUNT(*) AS c FROM images WHERE prompt_id = ? AND is_cover = 1", (prompt_id,)
        ).fetchone()["c"]
        if int(has_cover) == 0:
            first = self.conn.execute(
                "SELECT id FROM images WHERE prompt_id = ? ORDER BY sort_order ASC, id ASC LIMIT 1", (prompt_id,)
            ).fetchone()
            if first:
                self.conn.execute("UPDATE images SET is_cover = 1 WHERE id = ?", (int(first["id"]),))
        self.conn.commit()

    def set_cover_image(self, prompt_id: int, image_id: int) -> None:
        self.conn.execute("UPDATE images SET is_cover = 0 WHERE prompt_id = ?", (prompt_id,))
        self.conn.execute("UPDATE images SET is_cover = 1 WHERE id = ? AND prompt_id = ?", (image_id, prompt_id))
        self.conn.commit()

    def duplicate_prompt(self, prompt_id: int) -> Optional[int]:
        row = self.get_prompt(prompt_id)
        if not row:
            return None
        new_id = self.create_prompt(
            title=f"{row['title']} のコピー",
            prompt=str(row["prompt"]),
            negative_prompt=str(row["negative_prompt"]),
            description=str(row["description"]),
            engine=str(row["engine"]),
            model=str(row["model"]),
            project=str(row["project"]),
            rating=int(row["rating"]),
            favorite=int(row["favorite"]),
            parent_prompt_id=prompt_id,
        )
        self.set_prompt_tags(new_id, self.list_prompt_tags(prompt_id))
        return new_id

    def get_tag_preset_by_name(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tag_presets WHERE name = ?", (name,)).fetchone()

    def list_tag_presets(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM tag_presets ORDER BY name COLLATE NOCASE").fetchall()

    def save_tag_preset(self, preset_id: Optional[int], name: str, tags: Iterable[str]) -> int:
        name = name.strip()
        if not name:
            raise ValueError("プリセット名が空です。")
        tag_list: list[str] = []
        seen_tags: set[str] = set()
        for tag in tags:
            tag_name = self.canonical_tag_name(str(tag))
            key = tag_name.casefold()
            if tag_name and key not in seen_tags:
                tag_list.append(tag_name)
                seen_tags.add(key)
        for tag in tag_list:
            self.ensure_tag(tag)
        tags_json = json.dumps(tag_list, ensure_ascii=False)
        now = self.now()
        cur = self.conn.cursor()
        if preset_id is None:
            row = cur.execute("SELECT id FROM tag_presets WHERE name = ?", (name,)).fetchone()
            if row:
                preset_id = int(row["id"])
                cur.execute("UPDATE tag_presets SET tags_json = ?, updated_at = ? WHERE id = ?", (tags_json, now, preset_id))
            else:
                cur.execute(
                    "INSERT INTO tag_presets(name, tags_json, created_at, updated_at) VALUES(?, ?, ?, ?)",
                    (name, tags_json, now, now),
                )
                preset_id = int(cur.lastrowid)
        else:
            cur.execute("UPDATE tag_presets SET name = ?, tags_json = ?, updated_at = ? WHERE id = ?", (name, tags_json, now, preset_id))
        self.conn.commit()
        return int(preset_id)

    def delete_tag_preset(self, preset_id: int) -> None:
        self.conn.execute("DELETE FROM tag_presets WHERE id = ?", (preset_id,))
        self.conn.commit()

    def seed_meta_options_from_prompts_if_needed(self) -> None:
        if self.get_setting("meta_options_seeded_from_prompts_v1", "") == "1":
            return
        for field in META_OPTION_FIELDS:
            rows = self.conn.execute(
                f"SELECT DISTINCT {field} AS value FROM prompts WHERE TRIM({field}) != ''"
            ).fetchall()
            for row in rows:
                self.ensure_meta_option(field, str(row["value"]), commit=False)
        self.set_setting("meta_options_seeded_from_prompts_v1", "1")
        self.conn.commit()

    def ensure_meta_option(self, field: str, value: str, commit: bool = True) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            return
        now = self.now()
        self.conn.execute(
            """
            INSERT INTO meta_options(field, value, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(field, value) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (field, value, now, now),
        )
        if commit:
            self.conn.commit()

    def ensure_meta_options_from_prompt_data(self, data: dict) -> None:
        for field in META_OPTION_FIELDS:
            self.ensure_meta_option(field, str(data.get(field, "") or ""), commit=False)
        self.conn.commit()

    def list_meta_options(self, field: str | None = None) -> list[sqlite3.Row]:
        if field:
            field = normalize_meta_field(field)
            return self.conn.execute(
                "SELECT field, value FROM meta_options WHERE field = ? ORDER BY value COLLATE NOCASE",
                (field,),
            ).fetchall()
        return self.conn.execute(
            "SELECT field, value FROM meta_options ORDER BY field, value COLLATE NOCASE"
        ).fetchall()

    def save_meta_option(self, old_field: str | None, old_value: str | None, field: str, value: str) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            raise ValueError("入力候補の種類または値が空です。")
        old_field = normalize_meta_field(old_field or "")
        old_value = normalize_meta_value(old_value or "")
        now = self.now()
        cur = self.conn.cursor()
        if old_field and old_value and (old_field != field or old_value != value):
            cur.execute("DELETE FROM meta_options WHERE field = ? AND value = ?", (old_field, old_value))
            if old_field in META_OPTION_FIELDS:
                cur.execute(f"UPDATE prompts SET {old_field} = ? WHERE {old_field} = ?", (value, old_value))
        cur.execute(
            """
            INSERT INTO meta_options(field, value, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(field, value) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (field, value, now, now),
        )
        self.conn.commit()

    def delete_meta_option(self, field: str, value: str) -> None:
        field = normalize_meta_field(field)
        value = normalize_meta_value(value)
        if not field or not value:
            return
        self.conn.execute("DELETE FROM meta_options WHERE field = ? AND value = ?", (field, value))
        self.conn.commit()


class FlowLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        self.item_list = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):  # noqa: N802 - Qt naming
        self.item_list.append(item)

    def count(self) -> int:
        return len(self.item_list)

    def itemAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - Qt naming
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt naming
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt naming
        size = QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def doLayout(self, rect: QRect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        space_x = self._spacing
        space_y = self._spacing

        for item in self.item_list:
            widget_size = item.sizeHint()
            next_x = x + widget_size.width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + space_y
                next_x = x + widget_size.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), widget_size))
            x = next_x
            line_height = max(line_height, widget_size.height())
        return y + line_height - rect.y() + bottom


class TagChipEditor(QWidget):
    tagsChanged = Signal()

    def __init__(
        self,
        color_provider: Callable[[str], str],
        parent: Optional[QWidget] = None,
        standalone_layout: bool = True,
        tag_resolver: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(parent)
        self.color_provider = color_provider
        self.tag_resolver = tag_resolver
        self.tags: list[str] = []

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("タグを入力して... / Enter・カンマ区切り可")
        self.add_button = QPushButton("追加")
        self.chip_container = QWidget()
        self.flow = FlowLayout(self.chip_container, margin=0, spacing=6)
        self.chip_container.setLayout(self.flow)
        self.chip_container.setMinimumHeight(30)

        if standalone_layout:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(5)
            add_row = QHBoxLayout()
            add_row.setContentsMargins(0, 0, 0, 0)
            add_row.addWidget(self.input_edit, 1)
            add_row.addWidget(self.add_button)
            root.addLayout(add_row)
            root.addWidget(self.chip_container)

        self.input_edit.returnPressed.connect(self.add_from_input)
        self.add_button.clicked.connect(self.add_from_input)

    def resolve_tag_name(self, tag: str) -> str:
        tag = normalize_tag(tag)
        if not tag:
            return ""
        if self.tag_resolver is None:
            return tag
        resolved = normalize_tag(self.tag_resolver(tag))
        return resolved or tag

    def set_tags(self, tags: Iterable[str]) -> None:
        self.tags = []
        seen: set[str] = set()
        for tag in tags:
            tag = self.resolve_tag_name(str(tag))
            key = tag.casefold()
            if tag and key not in seen:
                self.tags.append(tag)
                seen.add(key)
        self.refresh_chips()

    def get_tags(self) -> list[str]:
        return list(self.tags)

    def add_tags(self, tags: Iterable[str]) -> None:
        changed = False
        seen = {tag.casefold() for tag in self.tags}
        for tag in tags:
            tag = self.resolve_tag_name(str(tag))
            key = tag.casefold()
            if tag and key not in seen:
                self.tags.append(tag)
                seen.add(key)
                changed = True
        if changed:
            self.refresh_chips()
            self.tagsChanged.emit()

    def add_from_input(self) -> None:
        tags = parse_tags(self.input_edit.text())
        if not tags:
            return
        self.input_edit.clear()
        self.add_tags(tags)

    def remove_tag(self, tag: str) -> None:
        if tag not in self.tags:
            return
        self.tags.remove(tag)
        self.refresh_chips()
        self.tagsChanged.emit()

    def refresh_chips(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()
        for tag in self.tags:
            btn = QToolButton()
            btn.setText(f"{tag}  ×")
            btn.setAutoRaise(False)
            btn.setStyleSheet(chip_style(self.color_provider(tag), checked=True))
            btn.clicked.connect(lambda _checked=False, t=tag: self.remove_tag(t))
            self.flow.addWidget(btn)
        self.chip_container.updateGeometry()


class PromptListItemWidget(QWidget):
    def __init__(self, row: PromptRow, icon_size: QSize, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAutoFillBackground(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(icon_size)
        icon_label.setAlignment(Qt.AlignCenter)
        pix = pixmap_from_path(row.cover_thumb, icon_size)
        if pix is not None:
            icon_label.setPixmap(pix)
        layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = row.title or "(無題)"
        fav = "★ " if row.favorite else ""
        self.title_label = QLabel(f"{fav}{title}")
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setTextInteractionFlags(Qt.NoTextInteraction)
        text_layout.addWidget(self.title_label)

        rating = "★" * row.rating if row.rating else ""
        sub = "  ".join(part for part in [row.project, row.engine, rating] if part)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setTextInteractionFlags(Qt.NoTextInteraction)
            text_layout.addWidget(sub_label)

        tags_label = " / ".join(row.tags[:5])
        if tags_label:
            tag_label = QLabel(tags_label)
            tag_label.setTextInteractionFlags(Qt.NoTextInteraction)
            text_layout.addWidget(tag_label)

        text_layout.addStretch(1)
        layout.addLayout(text_layout, 1)


class ImageListWidget(QListWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_item: Optional[QListWidgetItem] = None
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(140, 105))
        self.setGridSize(QSize(170, 150))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(8)
        self.setWordWrap(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setMinimumHeight(170)

    def event_local_pos(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            local_pos = self.event_local_pos(event)
            self._drag_start_pos = local_pos
            self._drag_start_item = self.itemAt(local_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt naming
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_start_pos is None or self._drag_start_item is None:
            super().mouseMoveEvent(event)
            return
        drag_distance = QApplication.startDragDistance() if hasattr(QApplication, "startDragDistance") else QApplication.styleHints().startDragDistance()
        if (self.event_local_pos(event) - self._drag_start_pos).manhattanLength() < drag_distance:
            super().mouseMoveEvent(event)
            return
        self.setCurrentItem(self._drag_start_item)
        self.startDrag(Qt.CopyAction)
        self._drag_start_pos = None
        self._drag_start_item = None

    def startDrag(self, supported_actions):  # noqa: N802 - Qt naming
        path = self.main_window.selected_material_path()
        if not path or not path.exists():
            return
        mime = QMimeData()
        file_url = QUrl.fromLocalFile(str(path.resolve()))
        mime.setUrls([file_url])
        mime.setText(str(path.resolve()))
        mime.setData(INTERNAL_MATERIAL_DRAG_MIME, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        thumb = self.main_window.selected_material_drag_pixmap()
        if thumb is not None and not thumb.isNull():
            drag.setPixmap(thumb)
            drag.setHotSpot(QPoint(min(thumb.width() // 2, 32), min(thumb.height() // 2, 32)))
        drag.exec(Qt.CopyAction)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        paths = media_paths_from_mime(event.mimeData())
        if paths:
            self.main_window.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)



class ImageViewerWindow(QWidget):
    MODE_FRAMELESS = "frameless"
    MODE_SCROLL = "scroll"
    MODE_LABELS = {
        MODE_FRAMELESS: "フレームレス表示",
        MODE_SCROLL: "原寸スクロール表示",
    }
    RESIZE_MARGIN = 8

    def __init__(self, main_window: "MainWindow", image_path: Path, mode: str = MODE_FRAMELESS):
        super().__init__()
        self.main_window = main_window
        self.image_path = image_path
        self.pixmap = QPixmap(str(image_path))
        self.mode = mode if mode in self.MODE_LABELS else self.MODE_FRAMELESS
        self.zoom_percent = 100
        self.offset = QPoint(0, 0)
        self._dragging_window = False
        self._dragging_image = False
        self._resizing = False
        self._resize_edges = ""
        self._press_global = QPoint(0, 0)
        self._press_pos = QPoint(0, 0)
        self._press_window_pos = QPoint(0, 0)
        self._press_geom = QRect()
        self._press_offset = QPoint(0, 0)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(80, 60)
        self.setWindowTitle(image_path.name)
        self.apply_mode(first=True)
        self.resize_to_zoom()
        self.move(self.main_window.next_viewer_position(self.size()))

    def apply_mode(self, first: bool = False) -> None:
        current_geometry = QRect(self.geometry())
        was_visible = self.isVisible()
        if not first and was_visible:
            self.hide()

        if self.mode == self.MODE_FRAMELESS:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        else:
            # Let the platform apply the normal decorated window frame.
            # Replacing a frameless top-level window with a newly shown decorated one is
            # more reliable than trying to keep every title/close/minimize hint manually.
            self.setWindowFlags(Qt.Window)
        self.setWindowTitle(self.image_path.name)

        if not first:
            if current_geometry.isValid():
                self.setGeometry(current_geometry)
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def switch_mode(self, mode: str) -> None:
        if mode not in self.MODE_LABELS or mode == self.mode:
            return
        if self.mode == self.MODE_FRAMELESS and mode == self.MODE_SCROLL:
            self.main_window.replace_image_viewer_mode(self, mode)
            return
        self.mode = mode
        self.apply_mode()
        if self.mode == self.MODE_FRAMELESS:
            self.resize_to_zoom()
        else:
            self.center_image_if_needed()
        screen = QGuiApplication.primaryScreen()
        center = screen.geometry().center() if screen is not None else QPoint(0, 0)
        self.update_cursor(self.mapFromGlobal(center))
        self.update()

    def image_size_at_zoom(self) -> QSize:
        if self.pixmap.isNull():
            return QSize(320, 240)
        return QSize(
            max(1, int(round(self.pixmap.width() * self.zoom_percent / 100.0))),
            max(1, int(round(self.pixmap.height() * self.zoom_percent / 100.0))),
        )

    def available_size(self) -> QSize:
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(1280, 720)
        rect = screen.availableGeometry()
        return QSize(max(120, rect.width()), max(90, rect.height()))

    def resize_to_zoom(self, clamp_to_screen: bool = True) -> None:
        desired = self.image_size_at_zoom()
        if clamp_to_screen:
            avail = self.available_size()
            if desired.width() > avail.width() or desired.height() > avail.height():
                desired.scale(avail, Qt.KeepAspectRatio)
        if self.mode == self.MODE_FRAMELESS:
            self.resize(desired)
        self.center_image_if_needed()

    def center_image_if_needed(self) -> None:
        img_size = self.image_size_at_zoom()
        x = self.offset.x()
        y = self.offset.y()
        if img_size.width() <= self.width():
            x = (self.width() - img_size.width()) // 2
        else:
            x = min(0, max(self.width() - img_size.width(), x))
        if img_size.height() <= self.height():
            y = (self.height() - img_size.height()) // 2
        else:
            y = min(0, max(self.height() - img_size.height(), y))
        self.offset = QPoint(x, y)

    def edge_at(self, pos: QPoint) -> str:
        if self.mode != self.MODE_FRAMELESS:
            return ""
        m = self.RESIZE_MARGIN
        edges = ""
        if pos.x() <= m:
            edges += "L"
        elif pos.x() >= self.width() - m:
            edges += "R"
        if pos.y() <= m:
            edges += "T"
        elif pos.y() >= self.height() - m:
            edges += "B"
        return edges

    def update_cursor(self, pos: QPoint) -> None:
        edges = self.edge_at(pos)
        if edges in ("L", "R"):
            self.setCursor(Qt.SizeHorCursor)
        elif edges in ("T", "B"):
            self.setCursor(Qt.SizeVerCursor)
        elif edges in ("LT", "RB"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in ("RT", "LB"):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def contextMenuEvent(self, event):  # noqa: N802 - Qt naming
        menu = QMenu(self)
        frameless_action = QAction(self.MODE_LABELS[self.MODE_FRAMELESS], self)
        frameless_action.setCheckable(True)
        frameless_action.setChecked(self.mode == self.MODE_FRAMELESS)
        scroll_action = QAction(self.MODE_LABELS[self.MODE_SCROLL], self)
        scroll_action.setCheckable(True)
        scroll_action.setChecked(self.mode == self.MODE_SCROLL)
        close_all_action = QAction("全て閉じる", self)
        close_action = QAction("閉じる", self)
        frameless_action.triggered.connect(lambda: self.switch_mode(self.MODE_FRAMELESS))
        scroll_action.triggered.connect(lambda: self.switch_mode(self.MODE_SCROLL))
        close_all_action.triggered.connect(self.main_window.close_all_image_viewers)
        close_action.triggered.connect(self.close)
        menu.addAction(frameless_action)
        menu.addAction(scroll_action)
        menu.addSeparator()
        menu.addAction(close_all_action)
        menu.addAction(close_action)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):  # noqa: N802 - Qt naming
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Qt naming
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            self.zoom_percent = max(10, min(500, self.zoom_percent + (10 if delta > 0 else -10)))
            if self.mode == self.MODE_FRAMELESS:
                self.resize_to_zoom(clamp_to_screen=False)
            else:
                self.center_image_if_needed()
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = event.position().toPoint()
            self._press_window_pos = self.pos()
            self._press_geom = self.geometry()
            self._press_offset = QPoint(self.offset)
            if self.mode == self.MODE_FRAMELESS:
                edges = self.edge_at(self._press_pos)
                if edges:
                    self._resizing = True
                    self._resize_edges = edges
                else:
                    self._dragging_window = True
            else:
                self._dragging_image = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt naming
        pos = event.position().toPoint()
        global_pos = event.globalPosition().toPoint()
        if self._dragging_window:
            self.move(self._press_window_pos + (global_pos - self._press_global))
            event.accept()
            return
        if self._dragging_image:
            self.offset = self._press_offset + (pos - self._press_pos)
            self.center_image_if_needed()
            self.update()
            event.accept()
            return
        if self._resizing:
            self.resize_frameless(global_pos)
            event.accept()
            return
        self.update_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt naming
        self._dragging_window = False
        self._dragging_image = False
        self._resizing = False
        self._resize_edges = ""
        super().mouseReleaseEvent(event)

    def resize_frameless(self, global_pos: QPoint) -> None:
        if self.pixmap.isNull():
            return
        geom = QRect(self._press_geom)
        dx = global_pos.x() - self._press_global.x()
        dy = global_pos.y() - self._press_global.y()
        ratio = self.pixmap.width() / max(1, self.pixmap.height())
        if "L" in self._resize_edges:
            new_w = geom.width() - dx
        elif "R" in self._resize_edges:
            new_w = geom.width() + dx
        else:
            if "T" in self._resize_edges:
                new_w = int(round((geom.height() - dy) * ratio))
            else:
                new_w = int(round((geom.height() + dy) * ratio))
        new_w = max(80, new_w)
        new_h = max(60, int(round(new_w / ratio)))
        avail = self.available_size()
        if new_w > avail.width() or new_h > avail.height():
            size = QSize(new_w, new_h)
            size.scale(avail, Qt.KeepAspectRatio)
            new_w, new_h = size.width(), size.height()
        new_x = geom.x()
        new_y = geom.y()
        if "L" in self._resize_edges:
            new_x = geom.right() - new_w + 1
        if "T" in self._resize_edges:
            new_y = geom.bottom() - new_h + 1
        self.setGeometry(new_x, new_y, new_w, new_h)
        self.update()

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        if self.mode == self.MODE_FRAMELESS and not self.pixmap.isNull():
            ratio = self.pixmap.width() / max(1, self.pixmap.height())
            expected_h = max(1, int(round(self.width() / ratio)))
            if abs(expected_h - self.height()) > 1 and not self._resizing:
                self.resize(self.width(), expected_h)
        self.center_image_if_needed()
        super().resizeEvent(event)

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 20))
        if self.pixmap.isNull():
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(self.rect(), Qt.AlignCenter, "画像を表示できません")
            return
        if self.mode == self.MODE_FRAMELESS:
            painter.drawPixmap(self.rect(), self.pixmap)
        else:
            img_size = self.image_size_at_zoom()
            target = QRect(self.offset, img_size)
            painter.drawPixmap(target, self.pixmap)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        self.main_window.save_image_viewer_position(self.pos())
        self.main_window.unregister_image_viewer(self)
        super().closeEvent(event)


class CollapsibleGroupBox(QGroupBox):
    collapsedChanged = Signal(str, bool)

    def __init__(self, title: str, state_key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plain_title = title
        self.state_key = state_key
        self._collapsed = False
        self._saved_maximum_height = self.maximumHeight()
        self.setTitle(f"▼ {self.plain_title}")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, emit_signal: bool = True) -> None:
        collapsed = bool(collapsed)
        if self._collapsed == collapsed:
            self._apply_collapsed_visual()
            return
        self._collapsed = collapsed
        self._apply_collapsed_visual()
        if emit_signal:
            self.collapsedChanged.emit(self.state_key, self._collapsed)

    def _collapsed_height(self) -> int:
        return max(30, self.fontMetrics().height() + 12)

    def _apply_collapsed_visual(self) -> None:
        self.setTitle(("▶ " if self._collapsed else "▼ ") + self.plain_title)
        layout = self.layout()
        if layout is not None:
            self._set_layout_visible(layout, not self._collapsed)
        if self._collapsed:
            self.setMaximumHeight(self._collapsed_height())
        else:
            self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _set_layout_visible(self, layout: QLayout, visible: bool) -> None:
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)
            child_layout = item.layout()
            if child_layout is not None:
                self._set_layout_visible(child_layout, visible)

    def mousePressEvent(self, event):  # noqa: N802 - Qt naming
        pos = event.position() if hasattr(event, "position") else event.pos()
        x = pos.x()
        y = pos.y()
        title_click_width = self.fontMetrics().horizontalAdvance(self.title()) + 28
        if y <= self._collapsed_height() and x <= title_click_width:
            self.set_collapsed(not self._collapsed)
            event.accept()
            return
        super().mousePressEvent(event)

class TagManagerDialog(QDialog):
    def __init__(self, db: Database, color_provider: Callable[[str], str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.color_provider = color_provider
        self.current_tag_id: Optional[int] = None
        self.current_preset_id: Optional[int] = None
        self.current_meta_field: str = ""
        self.current_meta_value: str = ""
        self.setWindowTitle("タグ管理")
        self.resize(900, 620)
        self.build_ui()
        self.refresh_categories()
        self.refresh_tag_list()
        self.refresh_preset_list()
        self.refresh_meta_option_list()

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        tag_tab = QWidget()
        tag_root = QHBoxLayout(tag_tab)
        self.tag_list = QListWidget()
        self.tag_list.setMinimumWidth(290)
        tag_root.addWidget(self.tag_list, 1)

        tag_form_box = QGroupBox("タグ編集")
        tag_form = QGridLayout(tag_form_box)
        self.tag_name_edit = QLineEdit()
        self.tag_category_combo = QComboBox()
        self.tag_category_combo.setEditable(True)
        self.tag_color_edit = QLineEdit()
        self.tag_color_edit.setPlaceholderText("空ならカテゴリ色")
        self.tag_color_button = QPushButton("タグ色")
        self.tag_visible_check = QCheckBox("表示する")
        self.tag_visible_check.setChecked(True)
        self.category_color_edit = QLineEdit()
        self.category_color_button = QPushButton("カテゴリ色")
        self.new_tag_button = QPushButton("新規")
        self.save_tag_button = QPushButton("保存")
        self.delete_tag_button = QPushButton("削除")

        tag_form.addWidget(QLabel("タグ名"), 0, 0)
        tag_form.addWidget(self.tag_name_edit, 0, 1, 1, 3)
        tag_form.addWidget(QLabel("カテゴリ"), 1, 0)
        tag_form.addWidget(self.tag_category_combo, 1, 1, 1, 3)
        tag_form.addWidget(QLabel("タグ色"), 2, 0)
        tag_form.addWidget(self.tag_color_edit, 2, 1)
        tag_form.addWidget(self.tag_color_button, 2, 2)
        tag_form.addWidget(QLabel("カテゴリ色"), 3, 0)
        tag_form.addWidget(self.category_color_edit, 3, 1)
        tag_form.addWidget(self.category_color_button, 3, 2)
        tag_form.addWidget(self.tag_visible_check, 4, 1, 1, 3)
        tag_btn_row = QHBoxLayout()
        tag_btn_row.addWidget(self.new_tag_button)
        tag_btn_row.addWidget(self.save_tag_button)
        tag_btn_row.addWidget(self.delete_tag_button)
        tag_btn_row.addStretch(1)
        tag_form.addLayout(tag_btn_row, 5, 0, 1, 4)
        tag_form.setRowStretch(6, 1)
        tag_root.addWidget(tag_form_box, 2)
        tabs.addTab(tag_tab, "タグ")

        preset_tab = QWidget()
        preset_root = QHBoxLayout(preset_tab)
        self.preset_list = QListWidget()
        self.preset_list.setMinimumWidth(290)
        preset_root.addWidget(self.preset_list, 1)

        preset_form_box = QGroupBox("タグプリセット編集")
        preset_form = QVBoxLayout(preset_form_box)
        preset_form.addWidget(QLabel("プリセット名"))
        self.preset_name_edit = QLineEdit()
        preset_form.addWidget(self.preset_name_edit)
        preset_form.addWidget(QLabel("含めるタグ"))
        self.preset_tags_editor = TagChipEditor(color_provider=self.color_provider, tag_resolver=self.db.canonical_tag_name)
        preset_form.addWidget(self.preset_tags_editor)
        preset_btn_row = QHBoxLayout()
        self.new_preset_button = QPushButton("新規")
        self.save_preset_button = QPushButton("保存")
        self.delete_preset_button = QPushButton("削除")
        preset_btn_row.addWidget(self.new_preset_button)
        preset_btn_row.addWidget(self.save_preset_button)
        preset_btn_row.addWidget(self.delete_preset_button)
        preset_btn_row.addStretch(1)
        preset_form.addLayout(preset_btn_row)
        preset_form.addStretch(1)
        preset_root.addWidget(preset_form_box, 2)
        tabs.addTab(preset_tab, "タグプリセット")

        meta_tab = QWidget()
        meta_root = QHBoxLayout(meta_tab)
        self.meta_option_list = QListWidget()
        self.meta_option_list.setMinimumWidth(290)
        meta_root.addWidget(self.meta_option_list, 1)

        meta_form_box = QGroupBox("入力候補編集")
        meta_form = QGridLayout(meta_form_box)
        self.meta_field_combo = QComboBox()
        self.meta_field_combo.addItems([META_OPTION_LABELS[field] for field in META_OPTION_FIELDS])
        self.meta_value_edit = QLineEdit()
        self.new_meta_option_button = QPushButton("新規")
        self.save_meta_option_button = QPushButton("保存")
        self.delete_meta_option_button = QPushButton("削除")
        meta_form.addWidget(QLabel("種類"), 0, 0)
        meta_form.addWidget(self.meta_field_combo, 0, 1, 1, 3)
        meta_form.addWidget(QLabel("値"), 1, 0)
        meta_form.addWidget(self.meta_value_edit, 1, 1, 1, 3)
        meta_btn_row = QHBoxLayout()
        meta_btn_row.addWidget(self.new_meta_option_button)
        meta_btn_row.addWidget(self.save_meta_option_button)
        meta_btn_row.addWidget(self.delete_meta_option_button)
        meta_btn_row.addStretch(1)
        meta_form.addLayout(meta_btn_row, 2, 0, 1, 4)
        meta_form.setRowStretch(3, 1)
        meta_root.addWidget(meta_form_box, 2)
        tabs.addTab(meta_tab, "入力候補")

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button, alignment=Qt.AlignRight)

        self.tag_list.currentItemChanged.connect(self.on_tag_selected)
        self.tag_category_combo.currentTextChanged.connect(self.on_category_text_changed)
        self.tag_color_button.clicked.connect(lambda: self.pick_color(self.tag_color_edit))
        self.category_color_button.clicked.connect(lambda: self.pick_color(self.category_color_edit))
        self.new_tag_button.clicked.connect(self.new_tag)
        self.save_tag_button.clicked.connect(self.save_tag)
        self.delete_tag_button.clicked.connect(self.delete_tag)

        self.preset_list.currentItemChanged.connect(self.on_preset_selected)
        self.new_preset_button.clicked.connect(self.new_preset)
        self.save_preset_button.clicked.connect(self.save_preset)
        self.delete_preset_button.clicked.connect(self.delete_preset)

        self.meta_option_list.currentItemChanged.connect(self.on_meta_option_selected)
        self.new_meta_option_button.clicked.connect(self.new_meta_option)
        self.save_meta_option_button.clicked.connect(self.save_meta_option)
        self.delete_meta_option_button.clicked.connect(self.delete_meta_option)

    def refresh_categories(self) -> None:
        current = self.tag_category_combo.currentText().strip()
        self.tag_category_combo.blockSignals(True)
        self.tag_category_combo.clear()
        for row in self.db.list_categories():
            self.tag_category_combo.addItem(str(row["name"]))
        if current:
            index = self.tag_category_combo.findText(current)
            if index >= 0:
                self.tag_category_combo.setCurrentIndex(index)
            else:
                self.tag_category_combo.setEditText(current)
        self.tag_category_combo.blockSignals(False)

    def refresh_tag_list(self) -> None:
        selected_id = self.current_tag_id
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for row in self.db.list_tags_with_counts():
            name = str(row["name"])
            category = str(row["category"])
            count = int(row["count"])
            visible = int(row["visible"] if "visible" in row.keys() else 1)
            hidden = "" if visible else "   [非表示]"
            label = f"{name}   [{category}]   ({count}){hidden}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, int(row["id"]))
            item.setIcon(colored_square_icon(effective_color_from_row(row), QSize(16, 16)))
            self.tag_list.addItem(item)
            if selected_id == int(row["id"]):
                self.tag_list.setCurrentItem(item)
        self.tag_list.blockSignals(False)

    def refresh_preset_list(self) -> None:
        selected_id = self.current_preset_id
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        for row in self.db.list_tag_presets():
            tags = tags_from_json(str(row["tags_json"]))
            item = QListWidgetItem(f"{row['name']}   ({len(tags)})")
            item.setData(Qt.UserRole, int(row["id"]))
            self.preset_list.addItem(item)
            if selected_id == int(row["id"]):
                self.preset_list.setCurrentItem(item)
        self.preset_list.blockSignals(False)

    def on_tag_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        tag_id = int(current.data(Qt.UserRole))
        row = self.db.get_tag(tag_id)
        if not row:
            return
        self.current_tag_id = tag_id
        category = str(row["category"] or "custom")
        self.tag_name_edit.setText(str(row["name"]))
        index = self.tag_category_combo.findText(category)
        if index >= 0:
            self.tag_category_combo.setCurrentIndex(index)
        else:
            self.tag_category_combo.setEditText(category)
        self.tag_color_edit.setText(str(row["color"] or ""))
        self.tag_visible_check.setChecked(int(row["visible"] if "visible" in row.keys() else 1) != 0)
        self.category_color_edit.setText(self.db.get_category_color(category))

    def on_category_text_changed(self, text: str) -> None:
        category = normalize_category(text) or "custom"
        self.category_color_edit.setText(self.db.get_category_color(category))

    def new_tag(self) -> None:
        self.current_tag_id = None
        self.tag_list.clearSelection()
        self.tag_name_edit.clear()
        self.tag_category_combo.setEditText("custom")
        self.tag_color_edit.clear()
        self.tag_visible_check.setChecked(True)
        self.category_color_edit.setText(self.db.get_category_color("custom"))
        self.tag_name_edit.setFocus()

    def save_tag(self) -> None:
        try:
            category = normalize_category(self.tag_category_combo.currentText()) or "custom"
            self.db.set_category_color(category, self.category_color_edit.text())
            self.current_tag_id = self.db.update_tag(
                self.current_tag_id,
                self.tag_name_edit.text(),
                category,
                self.tag_color_edit.text(),
                self.tag_visible_check.isChecked(),
            )
            self.refresh_categories()
            self.refresh_tag_list()
            self.refresh_preset_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"タグ名が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_tag(self) -> None:
        if self.current_tag_id is None:
            return
        result = QMessageBox.question(
            self,
            "タグ削除確認",
            "このタグを削除しますか？\nプロンプトとの紐づけと、タグプリセット内の同名タグも削除されます。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_tag(self.current_tag_id)
        self.current_tag_id = None
        self.new_tag()
        self.refresh_tag_list()
        self.refresh_preset_list()

    def on_preset_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        preset_id = int(current.data(Qt.UserRole))
        row = self.db.conn.execute("SELECT * FROM tag_presets WHERE id = ?", (preset_id,)).fetchone()
        if not row:
            return
        self.current_preset_id = preset_id
        self.preset_name_edit.setText(str(row["name"]))
        self.preset_tags_editor.set_tags(tags_from_json(str(row["tags_json"])))

    def new_preset(self) -> None:
        self.current_preset_id = None
        self.preset_list.clearSelection()
        self.preset_name_edit.clear()
        self.preset_tags_editor.set_tags([])
        self.preset_name_edit.setFocus()

    def save_preset(self) -> None:
        try:
            self.current_preset_id = self.db.save_tag_preset(
                self.current_preset_id,
                self.preset_name_edit.text(),
                self.preset_tags_editor.get_tags(),
            )
            self.refresh_categories()
            self.refresh_tag_list()
            self.refresh_preset_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"プリセット名が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_preset(self) -> None:
        if self.current_preset_id is None:
            return
        result = QMessageBox.question(
            self,
            "プリセット削除確認",
            "このタグプリセットを削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_tag_preset(self.current_preset_id)
        self.current_preset_id = None
        self.new_preset()
        self.refresh_preset_list()

    def refresh_meta_option_list(self) -> None:
        selected = (self.current_meta_field, self.current_meta_value)
        self.meta_option_list.blockSignals(True)
        self.meta_option_list.clear()
        for row in self.db.list_meta_options():
            field = str(row["field"])
            value = str(row["value"])
            item = QListWidgetItem(f"{meta_field_label(field)}: {value}")
            item.setData(Qt.UserRole, (field, value))
            self.meta_option_list.addItem(item)
            if selected == (field, value):
                self.meta_option_list.setCurrentItem(item)
        self.meta_option_list.blockSignals(False)

    def on_meta_option_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        field, value = current.data(Qt.UserRole)
        self.current_meta_field = normalize_meta_field(field)
        self.current_meta_value = normalize_meta_value(value)
        label = meta_field_label(self.current_meta_field)
        index = self.meta_field_combo.findText(label)
        if index >= 0:
            self.meta_field_combo.setCurrentIndex(index)
        self.meta_value_edit.setText(self.current_meta_value)

    def new_meta_option(self) -> None:
        self.current_meta_field = ""
        self.current_meta_value = ""
        self.meta_option_list.clearSelection()
        if self.meta_field_combo.count() > 0:
            self.meta_field_combo.setCurrentIndex(0)
        self.meta_value_edit.clear()
        self.meta_value_edit.setFocus()

    def save_meta_option(self) -> None:
        try:
            field = normalize_meta_field(self.meta_field_combo.currentText())
            value = self.meta_value_edit.text()
            self.db.save_meta_option(self.current_meta_field, self.current_meta_value, field, value)
            self.current_meta_field = field
            self.current_meta_value = normalize_meta_value(value)
            self.refresh_meta_option_list()
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存エラー", f"入力候補が重複している可能性があります。\n\n{exc}")
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", str(exc))

    def delete_meta_option(self) -> None:
        if not self.current_meta_field or not self.current_meta_value:
            return
        result = QMessageBox.question(
            self,
            "入力候補削除確認",
            "この入力候補を削除しますか？\n既存プロンプトの入力済みテキストは変更しません。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.db.delete_meta_option(self.current_meta_field, self.current_meta_value)
        self.current_meta_field = ""
        self.current_meta_value = ""
        self.new_meta_option()
        self.refresh_meta_option_list()

    def pick_color(self, line_edit: QLineEdit) -> None:
        current = normalize_hex_color(line_edit.text()) or "#777777"
        color = QColorDialog.getColor(QColor(current), self, "色を選択")
        if color.isValid():
            line_edit.setText(color.name())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.base_dir = get_base_dir()
        self.db_path = self.base_dir / DB_FILENAME
        self.assets_dir = self.base_dir / "assets"
        self.legacy_images_dir = self.assets_dir / "images"
        self.legacy_files_dir = self.assets_dir / "files"
        self.legacy_thumbs_dir = self.assets_dir / "thumbnails"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.base_dir / BACKUP_DIR_NAME

        self.db = Database(self.db_path)
        self.run_daily_backup_if_needed()
        self.migrate_legacy_asset_layout()
        self.current_prompt_id: Optional[int] = None
        self.loading = False
        self.tag_list_loading = False
        self.dirty = False
        self.tag_filter_buttons: list[QToolButton] = []
        self.tag_color_map: dict[str, str] = {}
        self.tag_presets: dict[str, list[str]] = {}
        self.collapsible_sections: list[CollapsibleGroupBox] = []
        self.warned_invalid_image_folder_files: set[str] = set()
        self.current_font_size = max(9, min(25, safe_int(self.db.get_setting("font_size", "10"), 10)))
        self.font_size_actions: dict[int, QAction] = {}
        self.image_viewers: list[ImageViewerWindow] = []
        self._viewer_open_offset = 0
        self.material_load_chunk_size = 60
        self._material_load_timer = QTimer(self)
        self._material_load_timer.setInterval(0)
        self._material_load_timer.timeout.connect(self.process_material_load_chunk)
        self._material_load_rows: list[sqlite3.Row] = []
        self._material_load_index = 0
        self._material_load_prompt_id: Optional[int] = None

        self.setWindowTitle(APP_NAME)
        self.apply_window_icon()
        self.resize(1320, 900)
        self.setAcceptDrops(True)
        self.build_ui()
        self.build_menu()
        self.connect_signals()
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        self.apply_font_size(self.current_font_size, save=False)
        self.restore_ui_state()
        self.refresh_prompt_list()
        self.statusBar().showMessage(f"DB: {self.db_path}")

    def apply_window_icon(self) -> None:
        icon = load_window_icon()
        if icon.isNull():
            return
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
        self.setWindowIcon(icon)

    def backup_database(self, manual: bool = False) -> Optional[Path]:
        if not self.db_path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = unique_path(self.backup_dir / f"{timestamp}.db")
        self.db.backup_to(dest)
        return dest

    def run_daily_backup_if_needed(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if self.db.get_setting("last_auto_backup_date", "") == today:
            return
        try:
            self.backup_database(manual=False)
            self.db.set_setting("last_auto_backup_date", today)
        except Exception:
            pass

    def run_manual_backup(self) -> None:
        try:
            if self.dirty:
                self.save_current_prompt()
            backup_path = self.backup_database(manual=True)
            if backup_path:
                QMessageBox.information(self, "バックアップ完了", f"DBをバックアップしました。\n{backup_path}")
            else:
                QMessageBox.warning(self, "バックアップ失敗", "バックアップ対象のDBが見つかりませんでした。")
        except Exception as exc:
            QMessageBox.warning(self, "バックアップ失敗", f"DBをバックアップできませんでした。\n\n{exc}")

    def prompt_asset_dir(self, prompt_id: int) -> Path:
        return self.assets_dir / f"prompt_{prompt_id:06d}"

    def prompt_images_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "images"

    def prompt_files_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "files"

    def prompt_thumbs_dir(self, prompt_id: int) -> Path:
        return self.prompt_asset_dir(prompt_id) / "thumbnails"

    def ensure_prompt_asset_dirs(self, prompt_id: int) -> tuple[Path, Path, Path]:
        image_dir = self.prompt_images_dir(prompt_id)
        file_dir = self.prompt_files_dir(prompt_id)
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        image_dir.mkdir(parents=True, exist_ok=True)
        file_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        return image_dir, file_dir, thumb_dir

    def migrate_legacy_asset_layout(self) -> None:
        legacy_roots = [self.legacy_images_dir, self.legacy_files_dir, self.legacy_thumbs_dir]
        if not any(path.exists() for path in legacy_roots):
            return

        rows = self.db.conn.execute("SELECT * FROM images ORDER BY id ASC").fetchall()
        for row in rows:
            image_id = int(row["id"])
            prompt_id = int(row["prompt_id"])
            media_type = str(row["media_type"] if "media_type" in row.keys() else "image")
            image_dir, file_dir, thumb_dir = self.ensure_prompt_asset_dirs(prompt_id)

            file_path = Path(str(row["file_path"] or ""))
            if file_path.exists():
                target_dir = image_dir if media_type == "image" else file_dir
                if not is_relative_to_path(file_path, target_dir):
                    try:
                        dest = unique_path(target_dir / file_path.name)
                        shutil.move(str(file_path), str(dest))
                        self.db.update_image_file_path(image_id, str(dest))
                    except Exception:
                        pass

            thumb_path = Path(str(row["thumbnail_path"] or ""))
            if thumb_path.exists() and not is_relative_to_path(thumb_path, thumb_dir):
                try:
                    dest = unique_path(thumb_dir / thumb_path.name)
                    shutil.move(str(thumb_path), str(dest))
                    self.db.update_image_thumbnail(image_id, str(dest))
                except Exception:
                    pass

        self.migrate_remaining_legacy_prompt_folders(self.legacy_images_dir, "images")
        self.migrate_remaining_legacy_prompt_folders(self.legacy_files_dir, "files")
        for root in legacy_roots:
            remove_empty_dirs(root)

    def migrate_remaining_legacy_prompt_folders(self, legacy_root: Path, subfolder: str) -> None:
        if not legacy_root.exists():
            return
        for prompt_dir in legacy_root.glob("prompt_*"):
            if not prompt_dir.is_dir():
                continue
            match = re.fullmatch(r"prompt_(\d+)", prompt_dir.name)
            if not match:
                continue
            prompt_id = int(match.group(1))
            target_dir = self.prompt_asset_dir(prompt_id) / subfolder
            target_dir.mkdir(parents=True, exist_ok=True)
            for child in list(prompt_dir.iterdir()):
                try:
                    shutil.move(str(child), str(unique_path(target_dir / child.name)))
                except Exception:
                    pass

    def create_editable_combo(self, placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        return combo

    def reload_meta_combos(self) -> None:
        for field, combo in [("engine", self.engine_edit), ("model", self.model_edit), ("project", self.project_edit)]:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            for row in self.db.list_meta_options(field):
                combo.addItem(str(row["value"]))
            combo.setCurrentText(current)
            combo.blockSignals(False)

    def build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        self.main_splitter = splitter
        root_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("検索: タイトル / プロンプト / 説明 / タグ")
        self.search_edit.setClearButtonEnabled(True)
        left_layout.addWidget(self.search_edit)

        tag_box = QGroupBox("タグ絞り込み")
        tag_layout = QVBoxLayout(tag_box)
        tag_layout.setContentsMargins(8, 8, 8, 8)
        self.tag_filter_content = QWidget()
        self.tag_filter_layout = FlowLayout(self.tag_filter_content, margin=0, spacing=6)
        self.tag_filter_content.setLayout(self.tag_filter_layout)
        self.tag_filter_scroll = QScrollArea()
        self.tag_filter_scroll.setWidgetResizable(True)
        self.tag_filter_scroll.setWidget(self.tag_filter_content)
        self.tag_filter_scroll.setMinimumHeight(120)
        tag_layout.addWidget(self.tag_filter_scroll)
        tag_btn_row = QHBoxLayout()
        self.clear_tags_button = QPushButton("解除")
        self.only_favorite_checkbox = QCheckBox("お気に入りのみ")
        tag_btn_row.addWidget(self.clear_tags_button)
        tag_btn_row.addWidget(self.only_favorite_checkbox)
        tag_layout.addLayout(tag_btn_row)
        self.prompt_list = QListWidget()
        self.prompt_list.setIconSize(QSize(96, 72))
        self.prompt_list.setUniformItemSizes(False)
        self.prompt_list.setSpacing(4)
        self.prompt_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.prompt_list.setContextMenuPolicy(Qt.CustomContextMenu)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.addWidget(tag_box)
        self.left_splitter.addWidget(self.prompt_list)
        self.left_splitter.setSizes([260, 540])
        left_layout.addWidget(self.left_splitter, 1)

        splitter.addWidget(left)

        right = QWidget()
        self.right_widget = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form_root = QVBoxLayout(content)
        form_root.setContentsMargins(0, 0, 8, 0)

        meta_group = QGroupBox("基本情報")
        meta_layout = QGridLayout(meta_group)
        self.title_edit = QLineEdit()
        self.favorite_check = QCheckBox("お気に入り")
        self.rating_combo = QComboBox()
        self.rating_combo.addItems(["評価なし", "★", "★★", "★★★", "★★★★", "★★★★★"])
        self.engine_edit = self.create_editable_combo("例: ChatGPT / Gemini / Grok / Midjourney")
        self.model_edit = self.create_editable_combo("例: GPT-Image / Imagen / Flux など")
        self.project_edit = self.create_editable_combo("例: Layer Breaker / ちゃっぴー")
        self.tags_editor = TagChipEditor(color_provider=self.tag_color_for_name, standalone_layout=False, tag_resolver=self.db.canonical_tag_name)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("タグプリセットを追加...")
        self.add_preset_button = QPushButton("追加")

        meta_layout.addWidget(QLabel("タイトル"), 0, 0)
        meta_layout.addWidget(self.title_edit, 0, 1, 1, 4)
        meta_layout.addWidget(self.favorite_check, 0, 5)
        rating_label = QLabel("評価")
        rating_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_layout.addWidget(rating_label, 0, 6)
        meta_layout.addWidget(self.rating_combo, 0, 7)
        meta_layout.addWidget(QLabel("使用AI"), 1, 0)
        meta_layout.addWidget(self.engine_edit, 1, 1)
        meta_layout.addWidget(QLabel("モデル"), 1, 2)
        meta_layout.addWidget(self.model_edit, 1, 3)
        meta_layout.addWidget(QLabel("プロジェクト"), 1, 4)
        meta_layout.addWidget(self.project_edit, 1, 5, 1, 3)
        tag_label = QLabel("タグ")
        tag_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        tag_control = QWidget()
        tag_control_layout = QVBoxLayout(tag_control)
        tag_control_layout.setContentsMargins(0, 0, 0, 0)
        tag_control_layout.setSpacing(5)
        tag_top_row = QHBoxLayout()
        tag_top_row.setContentsMargins(0, 0, 0, 0)
        tag_top_row.addWidget(self.tags_editor.input_edit, 1)
        tag_top_row.addWidget(self.tags_editor.add_button)
        tag_top_row.addWidget(self.preset_combo)
        tag_top_row.addWidget(self.add_preset_button)
        tag_control_layout.addLayout(tag_top_row)
        tag_control_layout.addWidget(self.tags_editor.chip_container)
        meta_layout.addWidget(tag_label, 2, 0)
        meta_layout.addWidget(tag_control, 2, 1, 1, 7)
        form_root.addWidget(meta_group)

        prompt_group = CollapsibleGroupBox("プロンプト", "section_prompt_collapsed")
        self.collapsible_sections.append(prompt_group)
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.setPlaceholderText("ここにメインプロンプトを入力")
        self.prompt_edit.setMinimumHeight(190)
        prompt_layout.addWidget(self.prompt_edit)
        form_root.addWidget(prompt_group)

        negative_group = CollapsibleGroupBox("ネガティブ / 補助プロンプト", "section_negative_collapsed")
        self.collapsible_sections.append(negative_group)
        negative_layout = QVBoxLayout(negative_group)
        self.negative_edit = QTextEdit()
        self.negative_edit.setAcceptRichText(False)
        self.negative_edit.setPlaceholderText("ネガティブプロンプトや補助プロンプト。不要なら空でOK")
        self.negative_edit.setMinimumHeight(90)
        negative_layout.addWidget(self.negative_edit)
        form_root.addWidget(negative_group)

        desc_group = CollapsibleGroupBox("説明 / メモ", "section_description_collapsed")
        self.collapsible_sections.append(desc_group)
        desc_layout = QVBoxLayout(desc_group)
        self.description_edit = QTextEdit()
        self.description_edit.setAcceptRichText(False)
        self.description_edit.setPlaceholderText("使いどころ、成功/失敗メモ、修正方針など")
        self.description_edit.setMinimumHeight(110)
        desc_layout.addWidget(self.description_edit)
        form_root.addWidget(desc_group)

        image_group = CollapsibleGroupBox("素材", "section_images_collapsed")
        self.collapsible_sections.append(image_group)
        image_layout = QVBoxLayout(image_group)
        img_btn_row = QHBoxLayout()
        self.add_images_button = QPushButton("素材を追加")
        self.rename_image_button = QPushButton("ファイル名変更")
        self.remove_image_button = QPushButton("選択素材を削除")
        self.cover_image_button = QPushButton("カバーにする")
        self.open_image_button = QPushButton("開く")
        self.open_prompt_assets_button = QPushButton("素材フォルダを開く")
        self.reload_materials_button = QPushButton("再読み込み")
        self.rebuild_thumbnails_button = QPushButton("サムネ再作成")
        img_btn_row.addWidget(self.add_images_button)
        img_btn_row.addWidget(self.open_prompt_assets_button)
        img_btn_row.addWidget(self.reload_materials_button)
        img_btn_row.addWidget(self.rebuild_thumbnails_button)
        img_btn_row.addStretch(1)
        image_layout.addLayout(img_btn_row)
        self.image_list = ImageListWidget(self)
        image_layout.addWidget(self.image_list)
        self.drop_hint_label = QLabel("画像/動画/ファイルをここへドラッグ＆ドロップで追加できます。")
        self.drop_hint_label.setStyleSheet("color: #777;")
        image_layout.addWidget(self.drop_hint_label)
        form_root.addWidget(image_group)

        scroll.setWidget(content)
        right_layout.addWidget(scroll, 1)

        splitter.addWidget(right)
        splitter.setSizes([410, 910])

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        open_assets_action = QAction("素材フォルダを開く", self)
        backup_action = QAction("バックアップ実行", self)
        open_backup_action = QAction("バックアップフォルダを開く", self)
        quit_action = QAction("終了", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        open_assets_action.triggered.connect(self.open_assets_folder)
        backup_action.triggered.connect(self.run_manual_backup)
        open_backup_action.triggered.connect(self.open_backup_folder)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_assets_action)
        file_menu.addAction(open_backup_action)
        file_menu.addSeparator()
        file_menu.addAction(backup_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("編集")
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_current_prompt)
        new_action = QAction("新規", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_prompt)
        duplicate_action = QAction("複製", self)
        duplicate_action.triggered.connect(self.duplicate_prompt)
        delete_action = QAction("削除", self)
        delete_action.triggered.connect(self.delete_current_prompt)
        search_action = QAction("検索", self)
        search_action.setShortcut(QKeySequence.Find)
        search_action.setShortcutContext(Qt.ApplicationShortcut)
        search_action.triggered.connect(self.focus_search_box)
        reload_action = QAction("再読み込み", self)
        reload_action.setShortcut(QKeySequence("F5"))
        reload_action.setShortcutContext(Qt.ApplicationShortcut)
        reload_action.triggered.connect(self.reload_current_materials)
        self.addAction(reload_action)
        copy_prompt_action = QAction("プロンプトをコピー", self)
        copy_prompt_action.setShortcut(QKeySequence("Alt+C"))
        copy_prompt_action.setShortcutContext(Qt.ApplicationShortcut)
        copy_prompt_action.triggered.connect(self.copy_prompt)
        copy_full_action = QAction("タイトル+プロンプトをコピー", self)
        copy_full_action.triggered.connect(self.copy_full_prompt)
        tag_manage_action = QAction("タグ管理", self)
        tag_manage_action.triggered.connect(self.open_tag_manager)
        edit_menu.addAction(save_action)
        edit_menu.addSeparator()
        edit_menu.addAction(new_action)
        edit_menu.addAction(duplicate_action)
        edit_menu.addAction(delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(search_action)
        edit_menu.addSeparator()
        edit_menu.addAction(copy_prompt_action)
        edit_menu.addAction(copy_full_action)
        edit_menu.addSeparator()
        edit_menu.addAction(tag_manage_action)

        view_menu = self.menuBar().addMenu("表示")
        font_menu = view_menu.addMenu("文字サイズ")
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        self.font_size_actions = {}
        for size in range(9, 26):
            action = QAction(f"{size}pt", self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, s=size: self.apply_font_size(s, save=True))
            font_group.addAction(action)
            font_menu.addAction(action)
            self.font_size_actions[size] = action

        help_menu = self.menuBar().addMenu("ヘルプ")
        about_action = QAction("バージョン情報", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self.refresh_prompt_list)
        self.prompt_list.currentItemChanged.connect(self.on_prompt_selected)
        self.prompt_list.itemDoubleClicked.connect(lambda _item: self.copy_prompt())
        self.prompt_list.customContextMenuRequested.connect(self.show_prompt_list_context_menu)
        self.clear_tags_button.clicked.connect(self.clear_tag_filters)
        self.only_favorite_checkbox.stateChanged.connect(self.refresh_prompt_list)
        for section in self.collapsible_sections:
            section.collapsedChanged.connect(self.on_section_collapsed_changed)

        self.add_preset_button.clicked.connect(self.add_selected_preset)

        self.add_images_button.clicked.connect(self.choose_images)
        self.rename_image_button.clicked.connect(self.rename_selected_image)
        self.remove_image_button.clicked.connect(self.remove_selected_image)
        self.cover_image_button.clicked.connect(self.set_selected_image_as_cover)
        self.open_image_button.clicked.connect(self.open_selected_image)
        self.open_prompt_assets_button.clicked.connect(self.open_current_prompt_asset_folder)
        self.reload_materials_button.clicked.connect(self.reload_current_materials)
        self.rebuild_thumbnails_button.clicked.connect(self.rebuild_current_material_thumbnails)
        self.image_list.customContextMenuRequested.connect(self.show_material_context_menu)
        self.image_list.itemDoubleClicked.connect(lambda _item: self.open_selected_image())
        self.image_list.currentItemChanged.connect(self.on_material_selected)

        self.title_edit.textChanged.connect(self.mark_dirty)
        for combo in [
            self.engine_edit,
            self.model_edit,
            self.project_edit,
        ]:
            combo.currentTextChanged.connect(self.mark_dirty)
        self.tags_editor.tagsChanged.connect(self.mark_dirty)
        self.favorite_check.stateChanged.connect(self.mark_dirty)
        self.rating_combo.currentIndexChanged.connect(self.mark_dirty)
        self.prompt_edit.textChanged.connect(self.mark_dirty)
        self.negative_edit.textChanged.connect(self.mark_dirty)
        self.description_edit.textChanged.connect(self.mark_dirty)

    def apply_font_size(self, size: int, save: bool = True) -> None:
        size = max(9, min(25, int(size)))
        self.current_font_size = size
        action = self.font_size_actions.get(size)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        app = QApplication.instance()
        if app is not None:
            font = app.font()
            font.setPointSize(size)
            app.setFont(font)
        self.setStyleSheet(
            f"""
            * {{ font-size: {size}pt; }}
            QGroupBox {{ font-weight: bold; }}
            QTextEdit, QLineEdit, QListWidget {{ font-weight: normal; }}
            QListWidget::item {{ padding: 4px; }}
            QPushButton {{ padding: 5px 10px; }}
            QToolButton {{ padding: 3px 8px; }}
            """
        )
        if save:
            self.db.set_setting("font_size", str(size))
            self.statusBar().showMessage(f"文字サイズ: {size}pt")

    def on_font_size_changed(self, value: int) -> None:
        self.apply_font_size(value, save=True)

    def restore_ui_state(self) -> None:
        geometry_json = self.db.get_setting("window_geometry", "")
        if geometry_json:
            try:
                data = json.loads(geometry_json)
                x = safe_int(data.get("x", ""), self.x())
                y = safe_int(data.get("y", ""), self.y())
                w = max(800, safe_int(data.get("w", ""), self.width()))
                h = max(600, safe_int(data.get("h", ""), self.height()))
                self.setGeometry(x, y, w, h)
                if bool(data.get("maximized", False)):
                    self.setWindowState(self.windowState() | Qt.WindowMaximized)
            except Exception:
                pass
        self.restore_splitter_sizes()
        for section in self.collapsible_sections:
            collapsed = self.db.get_setting(section.state_key, "0") == "1"
            section.set_collapsed(collapsed, emit_signal=False)

    def restore_splitter_sizes(self) -> None:
        for key, splitter in [("main_splitter_sizes", self.main_splitter), ("left_splitter_sizes", self.left_splitter)]:
            raw = self.db.get_setting(key, "")
            if not raw:
                continue
            try:
                sizes = json.loads(raw)
                if isinstance(sizes, list) and all(isinstance(v, int) for v in sizes):
                    splitter.setSizes(sizes)
            except Exception:
                pass

    def save_splitter_sizes(self) -> None:
        self.db.set_setting("main_splitter_sizes", json.dumps(self.main_splitter.sizes()))
        self.db.set_setting("left_splitter_sizes", json.dumps(self.left_splitter.sizes()))

    def save_ui_state(self) -> None:
        geom = self.normalGeometry() if self.isMaximized() else self.geometry()
        data = {
            "x": geom.x(),
            "y": geom.y(),
            "w": geom.width(),
            "h": geom.height(),
            "maximized": self.isMaximized(),
        }
        self.db.set_setting("window_geometry", json.dumps(data, ensure_ascii=False))
        self.save_splitter_sizes()
        for section in self.collapsible_sections:
            self.db.set_setting(section.state_key, "1" if section.is_collapsed() else "0")

    def on_section_collapsed_changed(self, state_key: str, collapsed: bool) -> None:
        self.db.set_setting(state_key, "1" if collapsed else "0")

    def tag_color_for_name(self, tag_name: str) -> str:
        return self.tag_color_map.get(tag_name, self.db.get_effective_tag_color(tag_name))

    def reload_preset_combo(self) -> None:
        current = self.preset_combo.currentText() if hasattr(self, "preset_combo") else ""
        self.tag_presets = {}
        for row in self.db.list_tag_presets():
            self.tag_presets[str(row["name"])] = tags_from_json(str(row["tags_json"]))
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("タグプリセットを追加...")
        for name in self.tag_presets:
            self.preset_combo.addItem(name)
        if current:
            index = self.preset_combo.findText(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def mark_dirty(self) -> None:
        if not self.loading:
            self.dirty = True

    def selected_filter_tags(self) -> list[str]:
        tags: list[str] = []
        for button in self.tag_filter_buttons:
            if button.isChecked():
                tag_name = str(button.property("tag_name") or "")
                if tag_name:
                    tags.append(tag_name)
        return tags

    def refresh_tags(self) -> None:
        checked = set(self.selected_filter_tags())
        self.tag_list_loading = True
        self.tag_color_map = {}
        while self.tag_filter_layout.count():
            item = self.tag_filter_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()
        self.tag_filter_buttons = []

        for row in self.db.list_tags_with_counts():
            name = str(row["name"])
            count = int(row["count"])
            color = effective_color_from_row(row)
            self.tag_color_map[name] = color
            if int(row["visible"] if "visible" in row.keys() else 1) == 0:
                continue
            btn = QToolButton()
            btn.setText(f"{name} ({count})")
            btn.setCheckable(True)
            btn.setChecked(name in checked)
            btn.setProperty("tag_name", name)
            btn.setToolTip(f"カテゴリ: {row['category']}")
            btn.setStyleSheet(chip_style(color, checked=btn.isChecked()))
            btn.toggled.connect(lambda is_checked, b=btn: self.on_tag_filter_toggled(b, is_checked))
            self.tag_filter_layout.addWidget(btn)
            self.tag_filter_buttons.append(btn)
        self.tag_filter_content.updateGeometry()
        self.tags_editor.refresh_chips()
        self.tag_list_loading = False

    def on_tag_filter_toggled(self, button: QToolButton, checked: bool) -> None:
        tag_name = str(button.property("tag_name") or "")
        button.setStyleSheet(chip_style(self.tag_color_for_name(tag_name), checked=checked))
        if not self.tag_list_loading:
            self.refresh_prompt_list()

    def refresh_prompt_list(self) -> None:
        if self.loading:
            return
        current_id = self.current_prompt_id
        query = self.search_edit.text().strip().lower()
        selected_tags = set(self.selected_filter_tags())
        only_fav = self.only_favorite_checkbox.isChecked()
        rows = self.db.list_prompts()

        self.prompt_list.blockSignals(True)
        self.prompt_list.clear()
        matched_count = 0
        for row in rows:
            if only_fav and not row.favorite:
                continue
            if selected_tags and not selected_tags.issubset(set(row.tags)):
                continue
            haystack = "\n".join(
                [
                    row.title,
                    row.prompt,
                    row.negative_prompt,
                    row.description,
                    row.engine,
                    row.model,
                    row.project,
                    " ".join(row.tags),
                ]
            ).lower()
            if query and query not in haystack:
                continue

            item = QListWidgetItem()
            # The visible row is drawn by PromptListItemWidget.
            # Keep the QListWidgetItem display text empty so Qt's default item text
            # does not bleed into the reserved thumbnail area behind the custom widget.
            item.setText("")
            item.setData(Qt.UserRole, row.id)
            item.setData(Qt.UserRole + 1, row.title or "(無題)")
            item.setToolTip(f"更新: {row.updated_at}\nタグ: {', '.join(row.tags)}")
            widget = PromptListItemWidget(row, QSize(72, 72))
            item.setSizeHint(widget.sizeHint())
            self.prompt_list.addItem(item)
            self.prompt_list.setItemWidget(item, widget)
            if current_id == row.id:
                self.prompt_list.setCurrentItem(item)
            matched_count += 1
        self.prompt_list.blockSignals(False)
        self.statusBar().showMessage(f"{matched_count} 件表示 / DB: {self.db_path}")

    def clear_tag_filters(self) -> None:
        self.tag_list_loading = True
        for button in self.tag_filter_buttons:
            button.setChecked(False)
            tag_name = str(button.property("tag_name") or "")
            button.setStyleSheet(chip_style(self.tag_color_for_name(tag_name), checked=False))
        self.tag_list_loading = False

        self.only_favorite_checkbox.blockSignals(True)
        self.only_favorite_checkbox.setChecked(False)
        self.only_favorite_checkbox.blockSignals(False)

        if self.search_edit.text():
            self.search_edit.clear()
        else:
            self.refresh_prompt_list()

    def focus_search_box(self) -> None:
        self.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.search_edit.selectAll()

    def maybe_save_dirty(self) -> bool:
        if not self.dirty or self.current_prompt_id is None:
            return True
        result = QMessageBox.question(
            self,
            "未保存の変更",
            "現在のプロンプトに未保存の変更があります。保存しますか？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            self.save_current_prompt()
        return True

    def on_prompt_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        if not self.maybe_save_dirty():
            return
        prompt_id = int(current.data(Qt.UserRole))
        self.load_prompt(prompt_id)

    def clear_detail(self) -> None:
        self.cancel_material_list_loading()
        self.loading = True
        self.current_prompt_id = None
        self.title_edit.clear()
        self.engine_edit.setCurrentText("")
        self.model_edit.setCurrentText("")
        self.project_edit.setCurrentText("")
        self.tags_editor.set_tags([])
        self.favorite_check.setChecked(False)
        self.rating_combo.setCurrentIndex(0)
        self.prompt_edit.clear()
        self.negative_edit.clear()
        self.description_edit.clear()
        self.image_list.clear()
        self.loading = False
        self.dirty = False

    def load_prompt(self, prompt_id: int) -> None:
        row = self.db.get_prompt(prompt_id)
        if not row:
            return
        self.loading = True
        self.current_prompt_id = prompt_id
        self.title_edit.setText(str(row["title"]))
        self.engine_edit.setCurrentText(str(row["engine"]))
        self.model_edit.setCurrentText(str(row["model"]))
        self.project_edit.setCurrentText(str(row["project"]))
        self.tags_editor.set_tags(self.db.list_prompt_tags(prompt_id))
        self.favorite_check.setChecked(bool(row["favorite"]))
        rating = max(0, min(5, int(row["rating"])))
        self.rating_combo.setCurrentIndex(rating)
        self.prompt_edit.setPlainText(str(row["prompt"]))
        self.negative_edit.setPlainText(str(row["negative_prompt"]))
        self.description_edit.setPlainText(str(row["description"]))
        assets_changed = self.sync_current_prompt_assets()
        self.refresh_images(sync_assets=False)
        if assets_changed:
            self.refresh_prompt_list()
            self.select_prompt_in_list(prompt_id)
        self.loading = False
        self.dirty = False
        self.statusBar().showMessage(f"読み込み: {row['title']}")

    def gather_current_data(self) -> dict:
        return {
            "title": self.title_edit.text().strip() or "(無題)",
            "prompt": self.prompt_edit.toPlainText(),
            "negative_prompt": self.negative_edit.toPlainText(),
            "description": self.description_edit.toPlainText(),
            "engine": self.engine_edit.currentText().strip(),
            "model": self.model_edit.currentText().strip(),
            "project": self.project_edit.currentText().strip(),
            "rating": self.rating_combo.currentIndex(),
            "favorite": 1 if self.favorite_check.isChecked() else 0,
        }

    def save_current_prompt(self) -> None:
        data = self.gather_current_data()
        if self.current_prompt_id is None:
            self.current_prompt_id = self.db.create_prompt(**data)
        else:
            self.db.update_prompt(self.current_prompt_id, data)
        self.db.set_prompt_tags(self.current_prompt_id, self.tags_editor.get_tags())
        self.db.ensure_meta_options_from_prompt_data(data)
        self.dirty = False
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        self.refresh_prompt_list()
        self.select_prompt_in_list(self.current_prompt_id)
        self.statusBar().showMessage("保存しました")

    def select_prompt_in_list(self, prompt_id: int) -> None:
        for i in range(self.prompt_list.count()):
            item = self.prompt_list.item(i)
            if int(item.data(Qt.UserRole)) == prompt_id:
                self.prompt_list.setCurrentItem(item)
                return

    def new_prompt(self) -> None:
        if not self.maybe_save_dirty():
            return
        new_id = self.db.create_prompt("新規プロンプト")
        self.db.set_prompt_tags(new_id, [])
        self.current_prompt_id = new_id
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.title_edit.selectAll()
        self.title_edit.setFocus()

    def duplicate_prompt(self) -> None:
        if self.current_prompt_id is None:
            return
        if not self.maybe_save_dirty():
            return
        new_id = self.db.duplicate_prompt(self.current_prompt_id)
        if new_id is None:
            return
        self.current_prompt_id = new_id
        self.refresh_tags()
        self.refresh_prompt_list()
        self.select_prompt_in_list(new_id)
        self.load_prompt(new_id)
        self.statusBar().showMessage("複製しました。素材はコピーせず、プロンプト情報だけ複製しています。")

    def show_prompt_list_context_menu(self, pos: QPoint) -> None:
        item = self.prompt_list.itemAt(pos)
        if item is None:
            return
        target_id = int(item.data(Qt.UserRole))
        self.prompt_list.setCurrentItem(item)
        if self.current_prompt_id != target_id:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("プロンプトをコピー")
        copy_full_action = menu.addAction("タイトル+プロンプトをコピー")
        menu.addSeparator()
        duplicate_action = menu.addAction("複製")
        delete_action = menu.addAction("削除")
        selected = menu.exec(self.prompt_list.viewport().mapToGlobal(pos))
        if selected == copy_action:
            self.copy_prompt()
        elif selected == copy_full_action:
            self.copy_full_prompt()
        elif selected == duplicate_action:
            self.duplicate_prompt()
        elif selected == delete_action:
            self.delete_current_prompt()

    def delete_current_prompt(self) -> None:
        if self.current_prompt_id is None:
            return
        title = self.title_edit.text().strip() or "(無題)"
        result = QMessageBox.question(
            self,
            "削除確認",
            f"「{title}」を削除しますか？\nDB上の登録を削除し、assets内の素材ファイルはWindowsのゴミ箱へ移動します。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        deleted_id = self.current_prompt_id
        image_rows = self.db.list_images(deleted_id)
        prompt_asset_dir = self.prompt_asset_dir(deleted_id)
        recycle_targets: list[Path] = []
        if prompt_asset_dir.exists():
            recycle_targets.append(prompt_asset_dir)
        for row in image_rows:
            file_path = Path(str(row["file_path"]))
            thumb_path = Path(str(row["thumbnail_path"] or ""))
            if file_path.exists() and not (prompt_asset_dir.exists() and is_relative_to_path(file_path, prompt_asset_dir)):
                recycle_targets.append(file_path)
            if thumb_path.exists() and not (prompt_asset_dir.exists() and is_relative_to_path(thumb_path, prompt_asset_dir)):
                recycle_targets.append(thumb_path)

        self.db.delete_prompt(deleted_id)
        moved, errors = move_paths_to_recycle_bin(recycle_targets)
        self.clear_detail()
        self.refresh_tags()
        self.refresh_prompt_list()
        if errors:
            QMessageBox.warning(self, "削除警告", "登録は削除しましたが、一部ファイルをゴミ箱へ移動できませんでした。\n\n" + "\n".join(errors[:5]))
            self.statusBar().showMessage(f"削除しました。一部ファイル移動失敗: {len(errors)} 件")
        else:
            self.statusBar().showMessage(f"削除しました。素材ファイルをゴミ箱へ移動: {moved} 件")

    def copy_prompt(self) -> None:
        text = strip_prompt_comment_lines(self.prompt_edit.toPlainText())
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("プロンプトをコピーしました")

    def copy_full_prompt(self) -> None:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f"# {title}")
        prompt = strip_prompt_comment_lines(self.prompt_edit.toPlainText()).strip()
        if prompt:
            parts.append(prompt)
        negative = strip_prompt_comment_lines(self.negative_edit.toPlainText()).strip()
        if negative:
            parts.append("\n[Negative / Sub Prompt]\n" + negative)
        QGuiApplication.clipboard().setText("\n\n".join(parts))
        self.statusBar().showMessage("タイトル+プロンプトをコピーしました")

    def add_selected_preset(self) -> None:
        name = self.preset_combo.currentText()
        if name not in self.tag_presets:
            return
        self.tags_editor.add_tags(self.tag_presets[name])
        self.mark_dirty()

    def open_tag_manager(self) -> None:
        dialog = TagManagerDialog(self.db, self.tag_color_for_name, self)
        dialog.exec()
        self.refresh_tags()
        self.reload_preset_combo()
        self.reload_meta_combos()
        if self.current_prompt_id is not None and not self.dirty:
            self.loading = True
            self.tags_editor.set_tags(self.db.list_prompt_tags(self.current_prompt_id))
            self.loading = False
        self.refresh_prompt_list()

    def ensure_current_prompt_saved_for_images(self) -> bool:
        if self.current_prompt_id is None:
            self.save_current_prompt()
        elif self.dirty:
            self.save_current_prompt()
        return self.current_prompt_id is not None

    def choose_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "素材を選択",
            str(Path.home()),
            "All Files (*.*);;Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if files:
            self.add_images_from_paths([Path(f) for f in files])

    def add_images_from_paths(self, paths: Iterable[Path]) -> None:
        paths = [Path(p) for p in paths if Path(p).exists() and Path(p).is_file()]
        if not paths:
            return
        if not self.ensure_current_prompt_saved_for_images():
            return
        assert self.current_prompt_id is not None
        added = 0
        prompt_image_dir, prompt_file_dir, _prompt_thumb_dir = self.ensure_prompt_asset_dirs(self.current_prompt_id)
        video_count = sum(1 for p in paths if p.suffix.lower() in SUPPORTED_VIDEO_EXTS)
        video_mode_for_all: Optional[str] = None

        for src in paths:
            try:
                ext = src.suffix.lower()
                if ext in SUPPORTED_IMAGE_EXTS:
                    dest = unique_path(prompt_image_dir / safe_filename(src.name))
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                    image_id = self.db.add_image(self.current_prompt_id, str(dest), "", media_type="image", original_name=src.name)
                    thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "image")
                    if thumb_path:
                        self.db.update_image_thumbnail(image_id, str(thumb_path))
                    added += 1

                elif ext in SUPPORTED_VIDEO_EXTS:
                    if video_mode_for_all is not None:
                        mode = video_mode_for_all
                    else:
                        mode, apply_all = self.ask_video_import_mode(src, allow_apply_all=video_count > 1)
                        if apply_all and mode is not None:
                            video_mode_for_all = mode
                    if mode is None:
                        continue
                    if mode == "copy":
                        dest = unique_path(prompt_file_dir / safe_filename(src.name))
                        if src.resolve() != dest.resolve():
                            shutil.copy2(src, dest)
                        image_id = self.db.add_image(self.current_prompt_id, str(dest), "", media_type="video", original_name=src.name)
                        thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "video")
                        if not thumb_path:
                            thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, media_type_for_path(dest))
                        if thumb_path:
                            self.db.update_image_thumbnail(image_id, str(thumb_path))
                    else:
                        dest = self.generate_video_snapshot(src, prompt_image_dir)
                        image_id = self.db.add_image(self.current_prompt_id, str(dest), "", media_type="image", original_name=src.name)
                        thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, "image")
                        if thumb_path:
                            self.db.update_image_thumbnail(image_id, str(thumb_path))
                    added += 1

                else:
                    dest = unique_path(prompt_file_dir / safe_filename(src.name))
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                    image_id = self.db.add_image(self.current_prompt_id, str(dest), "", media_type=media_type_for_path(src), original_name=src.name)
                    thumb_path = self.create_material_thumbnail(dest, image_id, self.current_prompt_id, media_type_for_path(dest))
                    if thumb_path:
                        self.db.update_image_thumbnail(image_id, str(thumb_path))
                    added += 1
            except Exception as exc:
                QMessageBox.warning(self, "素材追加エラー", f"素材を追加できませんでした。\n{src}\n\n{exc}")
        if added:
            self.refresh_images()
            self.refresh_prompt_list()
            self.statusBar().showMessage(f"素材を {added} 件追加しました")

    def ask_video_import_mode(self, src: Path, allow_apply_all: bool = False) -> tuple[Optional[str], bool]:
        box = QMessageBox(self)
        box.setWindowTitle("動画追加")
        box.setText(f"動画をどう追加しますか？\n{src.name}")
        thumb_button = box.addButton("サムネ画像のみ作成", QMessageBox.AcceptRole)
        copy_button = box.addButton("動画をコピーして登録", QMessageBox.ActionRole)
        cancel_button = box.addButton("キャンセル", QMessageBox.RejectRole)
        apply_checkbox: Optional[QCheckBox] = None
        if allow_apply_all:
            apply_checkbox = QCheckBox("今後すべてに適用")
            box.setCheckBox(apply_checkbox)
        box.setDefaultButton(thumb_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        apply_all = bool(apply_checkbox and apply_checkbox.isChecked())
        clicked = box.clickedButton()
        if clicked == thumb_button:
            return "thumb", apply_all
        if clicked == copy_button:
            return "copy", apply_all
        return None, False

    def create_material_thumbnail(self, src: Path, image_id: int, prompt_id: int, media_type: str = "") -> Optional[Path]:
        media_type = (media_type or media_type_for_path(src)).strip().lower()
        if media_type == "video" or src.suffix.lower() in SUPPORTED_VIDEO_EXTS:
            thumb_path = self.create_video_thumbnail(src, image_id, prompt_id)
            if thumb_path:
                return thumb_path
            return self.create_extension_thumbnail(src, image_id, prompt_id)
        if media_type == "image" or src.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            return self.create_thumbnail(src, image_id, prompt_id)
        return self.create_extension_thumbnail(src, image_id, prompt_id)

    def create_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        pix = QPixmap(str(src))
        if pix.isNull():
            return None
        thumb = pix.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.jpg"
        canvas = QPixmap(320, 240)
        canvas.fill(QColor("#ffffff"))
        painter = QPainter(canvas)
        try:
            x = max(0, (canvas.width() - thumb.width()) // 2)
            y = max(0, (canvas.height() - thumb.height()) // 2)
            painter.drawPixmap(x, y, thumb)
        finally:
            painter.end()
        if canvas.save(str(thumb_path), "JPEG", 90):
            return thumb_path
        return None

    def generate_video_snapshot(self, src: Path, prompt_asset_dir: Path) -> Path:
        dest = unique_path(prompt_asset_dir / f"{normalize_file_stem(src.name)}.jpg")
        self.write_video_frame_jpeg(src, dest, target_height=1080)
        return dest

    def create_video_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.jpg"
        try:
            self.write_video_thumbnail_jpeg(src, thumb_path)
            return thumb_path
        except Exception:
            return None

    def capture_video_frame(self, src: Path):
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError("動画を開けませんでした。")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            candidate_indexes: list[int] = []
            if frame_count > 0:
                candidate_indexes.extend([max(0, int(frame_count * 0.15)), max(0, frame_count // 2), 0])
            else:
                candidate_indexes.extend([0])

            frame = None
            seen: set[int] = set()
            for index in candidate_indexes:
                if index in seen:
                    continue
                seen.add(index)
                if frame_count > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, current = cap.read()
                if ok and current is not None:
                    frame = current
                    break

            if frame is None:
                raise RuntimeError("動画からフレームを取得できませんでした。")
            return frame
        finally:
            cap.release()

    def write_video_thumbnail_jpeg(self, src: Path, dest: Path) -> None:
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        frame = self.capture_video_frame(src)
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            raise RuntimeError("取得したフレームのサイズが不正です。")

        canvas_w, canvas_h = 320, 240
        scale = min(canvas_w / float(width), canvas_h / float(height))
        target_w = max(1, int(round(width * scale)))
        target_h = max(1, int(round(height * scale)))
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
        left = max(0, (canvas_w - target_w) // 2)
        right = max(0, canvas_w - target_w - left)
        top = max(0, (canvas_h - target_h) // 2)
        bottom = max(0, canvas_h - target_h - top)
        canvas = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        ok = cv2.imwrite(str(dest), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise RuntimeError("JPEGを書き出せませんでした。")

    def write_video_frame_jpeg(self, src: Path, dest: Path, target_height: int = 1080) -> None:
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("動画サムネ生成には opencv-python が必要です。") from exc

        frame = self.capture_video_frame(src)
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            raise RuntimeError("取得したフレームのサイズが不正です。")

        target_width = max(1, int(round(width * (target_height / float(height)))))
        if height != target_height:
            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA if target_height < height else cv2.INTER_CUBIC)

        ok = cv2.imwrite(str(dest), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise RuntimeError("JPEGを書き出せませんでした。")

    def create_extension_thumbnail(self, src: Path, image_id: int, prompt_id: int) -> Optional[Path]:
        thumb_dir = self.prompt_thumbs_dir(prompt_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"thumb_{image_id:08d}.png"
        ext = extension_label(src)
        pix = QPixmap(320, 240)
        bg = QColor(color_for_media_type(media_type_for_path(src)))
        pix.fill(bg)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QColor("#ffffff"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(44 if len(ext) <= 4 else 34)
            painter.setFont(font)
            painter.drawText(QRect(0, 55, 320, 95), Qt.AlignCenter, ext)
            small_font = QFont()
            small_font.setPointSize(16)
            painter.setFont(small_font)
            painter.drawText(QRect(0, 150, 320, 45), Qt.AlignCenter, "FILE")
        finally:
            painter.end()
        if pix.save(str(thumb_path), "PNG"):
            return thumb_path
        return None

    def sync_current_prompt_assets(self) -> bool:
        if self.current_prompt_id is None:
            return False
        prompt_id = self.current_prompt_id
        image_dir, file_dir, _thumb_dir = self.ensure_prompt_asset_dirs(prompt_id)
        changed = False
        recycle_targets: list[Path] = []
        registered: set[str] = set()

        for row in self.db.list_images(prompt_id):
            image_id = int(row["id"])
            file_path = Path(str(row["file_path"] or ""))
            if not file_path.exists():
                thumb_path = Path(str(row["thumbnail_path"] or ""))
                if thumb_path.exists():
                    recycle_targets.append(thumb_path)
                self.db.delete_image(image_id)
                changed = True
                continue
            registered.add(material_path_key(file_path))
            thumb_path = Path(str(row["thumbnail_path"] or ""))
            if not thumb_path.exists():
                media_type = str(row["media_type"] if "media_type" in row.keys() else media_type_for_path(file_path))
                try:
                    new_thumb = self.create_material_thumbnail(file_path, image_id, prompt_id, media_type)
                    if new_thumb:
                        self.db.update_image_thumbnail(image_id, str(new_thumb))
                        changed = True
                except Exception:
                    pass

        if recycle_targets:
            move_paths_to_recycle_bin(recycle_targets)

        invalid_image_files: list[str] = []
        for child in sorted(image_dir.iterdir(), key=lambda p: p.name.lower()) if image_dir.exists() else []:
            if not child.is_file():
                continue
            if material_path_key(child) in registered:
                continue
            if child.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                key = material_path_key(child)
                if key not in self.warned_invalid_image_folder_files:
                    self.warned_invalid_image_folder_files.add(key)
                    invalid_image_files.append(child.name)
                continue
            try:
                image_id = self.db.add_image(prompt_id, str(child), "", media_type="image", original_name=child.name)
                thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, "image")
                if thumb_path:
                    self.db.update_image_thumbnail(image_id, str(thumb_path))
                registered.add(material_path_key(child))
                changed = True
            except Exception:
                pass

        for child in sorted(file_dir.iterdir(), key=lambda p: p.name.lower()) if file_dir.exists() else []:
            if not child.is_file():
                continue
            if material_path_key(child) in registered:
                continue
            try:
                if child.suffix.lower() in SUPPORTED_VIDEO_EXTS:
                    image_id = self.db.add_image(prompt_id, str(child), "", media_type="video", original_name=child.name)
                    thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, "video")
                    if not thumb_path:
                        thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, media_type_for_path(child))
                else:
                    image_id = self.db.add_image(prompt_id, str(child), "", media_type=media_type_for_path(child), original_name=child.name)
                    thumb_path = self.create_material_thumbnail(child, image_id, prompt_id, media_type_for_path(child))
                if thumb_path:
                    self.db.update_image_thumbnail(image_id, str(thumb_path))
                registered.add(material_path_key(child))
                changed = True
            except Exception:
                pass

        if invalid_image_files:
            preview = "\n".join(f"- {name}" for name in invalid_image_files[:20])
            if len(invalid_image_files) > 20:
                preview += f"\n...他 {len(invalid_image_files) - 20} 件"
            QMessageBox.warning(
                self,
                "素材同期警告",
                "imagesフォルダに画像以外のファイルがあります。\n"
                "このフォルダでは画像ファイルだけを登録します。\n\n" + preview,
            )

        return changed

    def cancel_material_list_loading(self) -> None:
        if self._material_load_timer.isActive():
            self._material_load_timer.stop()
        self._material_load_rows = []
        self._material_load_index = 0
        self._material_load_prompt_id = None

    def refresh_images(self, sync_assets: bool = True) -> None:
        self.cancel_material_list_loading()
        self.image_list.clear()
        if self.current_prompt_id is None:
            return
        if sync_assets:
            assets_changed = self.sync_current_prompt_assets()
            if assets_changed:
                self.refresh_prompt_list()
                self.select_prompt_in_list(self.current_prompt_id)
        rows = self.db.list_images(self.current_prompt_id)
        self.start_material_list_loading(rows, self.current_prompt_id)

    def start_material_list_loading(self, rows: list[sqlite3.Row], prompt_id: int) -> None:
        self._material_load_rows = list(rows)
        self._material_load_index = 0
        self._material_load_prompt_id = prompt_id
        total = len(self._material_load_rows)
        if total == 0:
            self.statusBar().showMessage("素材: 0 件")
            return
        self.statusBar().showMessage(f"素材一覧を読み込み中... 0/{total}")
        self._material_load_timer.start()

    def process_material_load_chunk(self) -> None:
        prompt_id = self._material_load_prompt_id
        if prompt_id is None or prompt_id != self.current_prompt_id:
            self.cancel_material_list_loading()
            return

        total = len(self._material_load_rows)
        if self._material_load_index >= total:
            self._material_load_timer.stop()
            self.statusBar().showMessage(f"素材: {total} 件")
            return

        end_index = min(total, self._material_load_index + self.material_load_chunk_size)
        self.image_list.setUpdatesEnabled(False)
        try:
            for row in self._material_load_rows[self._material_load_index:end_index]:
                self.add_material_list_item(row)
        finally:
            self.image_list.setUpdatesEnabled(True)
        self._material_load_index = end_index

        if self._material_load_index >= total:
            self._material_load_timer.stop()
            self.statusBar().showMessage(f"素材: {total} 件")
        else:
            self.statusBar().showMessage(f"素材一覧を読み込み中... {self._material_load_index}/{total}")

    def add_material_list_item(self, row: sqlite3.Row) -> None:
        image_id = int(row["id"])
        file_path = str(row["file_path"])
        thumb_path = str(row["thumbnail_path"] or file_path)
        cover = bool(row["is_cover"])
        media_type = str(row["media_type"] if "media_type" in row.keys() else "image")
        file_name = Path(file_path).name
        stem = Path(file_path).stem
        prefix = media_label(media_type)
        label_text = f"{prefix} {stem}" if prefix else stem
        label = f"★ {label_text}" if cover else label_text
        display_label = elide_material_label(label)
        item = QListWidgetItem(display_label)
        item.setData(Qt.UserRole, image_id)
        item.setData(Qt.UserRole + 1, file_name)
        item.setToolTip(file_name)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        item.setSizeHint(QSize(170, 150))
        icon = icon_from_path(thumb_path, QSize(140, 105))
        if icon.isNull():
            icon = icon_from_path(file_path, QSize(140, 105))
        if not icon.isNull():
            item.setIcon(icon)
        self.image_list.addItem(item)

    def selected_image_id(self) -> Optional[int]:
        item = self.image_list.currentItem()
        if not item:
            return None
        return int(item.data(Qt.UserRole))

    def selected_material_path(self) -> Optional[Path]:
        image_id = self.selected_image_id()
        if image_id is None:
            return None
        row = self.db.get_image(image_id)
        if not row:
            return None
        path = Path(str(row["file_path"] or ""))
        return path if path.exists() else None

    def selected_material_drag_pixmap(self) -> Optional[QPixmap]:
        image_id = self.selected_image_id()
        if image_id is None:
            return None
        row = self.db.get_image(image_id)
        if not row:
            return None
        thumb_path = str(row["thumbnail_path"] or row["file_path"] or "")
        pix = pixmap_from_path(thumb_path, QSize(96, 72))
        return pix

    def on_material_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self.drop_hint_label.setText("画像/動画/ファイルをここへドラッグ＆ドロップで追加できます。")
            return
        file_name = str(current.data(Qt.UserRole + 1) or current.text())
        self.drop_hint_label.setText(file_name)

    def reload_current_materials(self) -> None:
        if self.current_prompt_id is None:
            return
        self.refresh_images(sync_assets=True)
        self.refresh_prompt_list()
        self.select_prompt_in_list(self.current_prompt_id)
        self.statusBar().showMessage("素材リストを再読み込みしました")

    def rebuild_current_material_thumbnails(self) -> None:
        if self.current_prompt_id is None:
            return
        prompt_id = self.current_prompt_id
        self.sync_current_prompt_assets()
        rows = self.db.list_images(prompt_id)
        rebuilt = 0
        errors: list[str] = []
        old_thumbs_to_recycle: list[Path] = []
        for row in rows:
            image_id = int(row["id"])
            file_path = Path(str(row["file_path"] or ""))
            if not file_path.exists():
                continue
            old_thumb = Path(str(row["thumbnail_path"] or ""))
            media_type = str(row["media_type"] if "media_type" in row.keys() else media_type_for_path(file_path))
            try:
                new_thumb = self.create_material_thumbnail(file_path, image_id, prompt_id, media_type)
                if not new_thumb:
                    raise RuntimeError("サムネを作成できませんでした。")
                self.db.update_image_thumbnail(image_id, str(new_thumb))
                if old_thumb.exists() and old_thumb.resolve() != new_thumb.resolve():
                    old_thumbs_to_recycle.append(old_thumb)
                rebuilt += 1
            except Exception as exc:
                errors.append(f"{file_path.name}: {exc}")

        if old_thumbs_to_recycle:
            move_paths_to_recycle_bin(old_thumbs_to_recycle)
        QPixmapCache.clear()
        self.refresh_images(sync_assets=False)
        self.refresh_prompt_list()
        self.select_prompt_in_list(prompt_id)
        if errors:
            QMessageBox.warning(
                self,
                "サムネ再作成警告",
                f"サムネを {rebuilt} 件再作成しました。\n一部の素材で失敗しました。\n\n" + "\n".join(errors[:10]),
            )
        self.statusBar().showMessage(f"サムネを {rebuilt} 件再作成しました")

    def rename_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        old_path = Path(str(row["file_path"]))
        if not old_path.exists():
            QMessageBox.warning(self, "ファイル名変更エラー", "素材ファイルが見つかりません。")
            return
        current_stem = old_path.stem
        new_name, ok = QInputDialog.getText(
            self,
            "ファイル名変更",
            f"新しいファイル名を入力してください。\n拡張子 {old_path.suffix} は維持されます。",
            text=current_stem,
        )
        if not ok:
            return
        new_stem = normalize_file_stem(new_name)
        if not new_stem:
            return
        if new_stem == current_stem:
            return
        new_path = unique_path(old_path.with_name(f"{new_stem}{old_path.suffix}"))
        try:
            old_path.rename(new_path)
            self.db.update_image_file_path(image_id, str(new_path))
            self.refresh_images()
            self.refresh_prompt_list()
            self.statusBar().showMessage(f"素材ファイル名を変更しました: {new_path.name}")
        except Exception as exc:
            QMessageBox.warning(self, "ファイル名変更エラー", str(exc))

    def remove_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        result = QMessageBox.question(
            self,
            "素材削除確認",
            "選択素材の登録を削除しますか？\n素材ファイルはWindowsのゴミ箱へ移動します。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        recycle_targets = [Path(str(row["file_path"]))]
        thumb_path = Path(str(row["thumbnail_path"] or ""))
        if thumb_path.exists():
            recycle_targets.append(thumb_path)

        prompt_id = int(row["prompt_id"])
        prompt_asset_dir = self.prompt_asset_dir(prompt_id)
        self.db.delete_image(image_id)
        if not self.db.list_images(prompt_id):
            if prompt_asset_dir.exists():
                recycle_targets = [prompt_asset_dir]
        moved, errors = move_paths_to_recycle_bin(recycle_targets)
        remove_empty_dirs(prompt_asset_dir)
        self.refresh_images()
        self.refresh_prompt_list()
        if errors:
            QMessageBox.warning(self, "素材削除警告", "登録は削除しましたが、一部ファイルをゴミ箱へ移動できませんでした。\n\n" + "\n".join(errors[:5]))
            self.statusBar().showMessage(f"素材登録を削除しました。一部ファイル移動失敗: {len(errors)} 件")
        else:
            self.statusBar().showMessage(f"素材を削除しました。ゴミ箱へ移動: {moved} 件")

    def set_selected_image_as_cover(self) -> None:
        if self.current_prompt_id is None:
            return
        image_id = self.selected_image_id()
        if image_id is None:
            return
        self.db.set_cover_image(self.current_prompt_id, image_id)
        self.refresh_images()
        self.refresh_prompt_list()
        self.statusBar().showMessage("カバーを変更しました")

    def copy_selected_material_to_clipboard(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = Path(str(row["file_path"]))
        if not path.exists():
            QMessageBox.warning(self, "コピーエラー", "素材ファイルが見つかりません。")
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
        QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(f"素材をクリップボードにコピーしました: {path.name}")

    def show_selected_material_properties(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = Path(str(row["file_path"]))
        if not path.exists():
            QMessageBox.warning(self, "プロパティ表示エラー", "素材ファイルが見つかりません。")
            return
        if not show_file_properties(path):
            QMessageBox.warning(self, "プロパティ表示エラー", "プロパティを表示できませんでした。")

    def show_material_context_menu(self, pos: QPoint) -> None:
        item = self.image_list.itemAt(pos)
        if item is None:
            return
        self.image_list.setCurrentItem(item)
        menu = QMenu(self)
        open_action = menu.addAction("開く")
        copy_action = menu.addAction("コピー")
        rename_action = menu.addAction("ファイル名の変更")
        cover_action = menu.addAction("カバーにする")
        menu.addSeparator()
        delete_action = menu.addAction("削除")
        menu.addSeparator()
        property_action = menu.addAction("プロパティ")
        selected = menu.exec(self.image_list.viewport().mapToGlobal(pos))
        if selected == open_action:
            self.open_selected_image()
        elif selected == copy_action:
            self.copy_selected_material_to_clipboard()
        elif selected == rename_action:
            self.rename_selected_image()
        elif selected == cover_action:
            self.set_selected_image_as_cover()
        elif selected == delete_action:
            self.remove_selected_image()
        elif selected == property_action:
            self.show_selected_material_properties()

    def open_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        path = Path(str(row["file_path"]))
        if path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            self.open_image_viewer(path)
        else:
            open_path(path)

    def open_image_viewer(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "画像表示エラー", "画像ファイルが見つかりません。")
            return
        viewer = ImageViewerWindow(self, path, ImageViewerWindow.MODE_FRAMELESS)
        self.image_viewers.append(viewer)
        viewer.show()
        viewer.activateWindow()

    def replace_image_viewer_mode(self, old_viewer: ImageViewerWindow, mode: str) -> None:
        geometry = QRect(old_viewer.geometry())
        zoom_percent = old_viewer.zoom_percent
        offset = QPoint(old_viewer.offset)
        image_path = old_viewer.image_path
        if old_viewer in self.image_viewers:
            self.image_viewers.remove(old_viewer)
        old_viewer.close()

        viewer = ImageViewerWindow(self, image_path, mode)
        viewer.zoom_percent = zoom_percent
        viewer.offset = offset
        if geometry.isValid():
            if mode == ImageViewerWindow.MODE_SCROLL:
                geometry = self.keep_rect_on_screen(geometry)
            viewer.setGeometry(geometry)
        if mode == ImageViewerWindow.MODE_FRAMELESS:
            viewer.resize_to_zoom()
        else:
            viewer.center_image_if_needed()
        self.image_viewers.append(viewer)
        viewer.showNormal()
        viewer.raise_()
        viewer.activateWindow()
        QTimer.singleShot(0, viewer.showNormal)

    def unregister_image_viewer(self, viewer: ImageViewerWindow) -> None:
        if viewer in self.image_viewers:
            self.image_viewers.remove(viewer)

    def close_all_image_viewers(self) -> None:
        for viewer in list(self.image_viewers):
            viewer.close()

    def save_image_viewer_position(self, pos: QPoint) -> None:
        self.db.set_setting("image_viewer_x", str(pos.x()))
        self.db.set_setting("image_viewer_y", str(pos.y()))

    def keep_rect_on_screen(self, rect: QRect) -> QRect:
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)
        width = min(max(80, rect.width()), available.width())
        height = min(max(60, rect.height()), available.height())
        x = min(max(available.x(), rect.x()), available.right() - width + 1)
        y = min(max(available.y(), rect.y()), available.bottom() - height + 1)
        return QRect(x, y, width, height)

    def next_viewer_position(self, size: QSize) -> QPoint:
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)
        default_x = available.x() + max(0, (available.width() - size.width()) // 2)
        default_y = available.y() + max(0, (available.height() - size.height()) // 2)
        x = safe_int(self.db.get_setting("image_viewer_x", ""), default_x)
        y = safe_int(self.db.get_setting("image_viewer_y", ""), default_y)
        # Restore the saved position exactly for the first viewer.
        # Only additional simultaneous viewers are offset, so repeated open/close
        # does not drift farther from the saved position.
        offset = len(self.image_viewers) * 30
        rect = self.keep_rect_on_screen(QRect(x + offset, y + offset, size.width(), size.height()))
        return rect.topLeft()

    def open_backup_folder(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.backup_dir)

    def open_assets_folder(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.assets_dir)

    def open_current_prompt_asset_folder(self) -> None:
        if self.current_prompt_id is None:
            self.open_assets_folder()
            return
        prompt_dir = self.prompt_asset_dir(self.current_prompt_id)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        open_path(prompt_dir)

    def show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("バージョン情報")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        top = QHBoxLayout()

        icon_label = QLabel()
        icon = load_window_icon()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(64, 64))
        icon_label.setFixedSize(72, 72)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        top.addWidget(icon_label)

        info = QLabel(
            f"<b>{APP_NAME} {APP_VERSION}</b><br><br>"
            f"{APP_AUTHOR}<br>"
            f"<a href='{APP_CONTACT_X}'>{APP_CONTACT_X}</a><br>"
            f"<a href='{APP_REPOSITORY}'>{APP_REPOSITORY}</a><br><br>"
            "MIT License"
        )
        info.setOpenExternalLinks(True)
        info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        top.addWidget(info, 1)
        layout.addLayout(top)

        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(dialog.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(ok_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        dialog.exec()

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if has_media_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        paths = media_paths_from_mime(event.mimeData())
        if paths:
            self.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if not self.maybe_save_dirty():
            event.ignore()
            return
        self.cancel_material_list_loading()
        self.close_all_image_viewers()
        self.save_ui_state()
        self.db.close()
        event.accept()


def normalize_tag(tag: str) -> str:
    tag = tag.strip().strip("#＃")
    tag = re.sub(r"\s+", " ", tag)
    return tag


def normalize_category(category: str) -> str:
    category = category.strip()
    category = re.sub(r"\s+", " ", category)
    return category


def normalize_meta_field(field: str) -> str:
    field = str(field or "").strip()
    if field in META_OPTION_LABELS:
        return field
    return META_OPTION_FIELDS_BY_LABEL.get(field, "")


def normalize_meta_value(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def meta_field_label(field: str) -> str:
    return META_OPTION_LABELS.get(normalize_meta_field(field), str(field or ""))


def parse_tags(text: str) -> list[str]:
    parts = re.split(r"[,，、\n]+", text)
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = normalize_tag(part)
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def strip_prompt_comment_lines(text: str) -> str:
    lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("＃"):
            continue
        lines.append(line)
    return "\n".join(lines)


def tags_from_json(text: str) -> list[str]:
    try:
        data = json.loads(text or "[]")
    except Exception:
        data = []
    if not isinstance(data, list):
        return []
    return [normalize_tag(str(item)) for item in data if normalize_tag(str(item))]


def normalize_hex_color(color: str) -> str:
    color = (color or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color.lower()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", color):
        return "#" + "".join(ch * 2 for ch in color[1:]).lower()
    return ""


def text_color_for_bg(color: str) -> str:
    color = normalize_hex_color(color) or "#777777"
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#111111" if luminance > 150 else "#ffffff"


def chip_style(color: str, checked: bool = False) -> str:
    color = normalize_hex_color(color) or "#777777"
    text_color = text_color_for_bg(color)
    # 選択中タグの枠線。白枠だと白背景に溶けるため、濃いスレート色で強調する。
    border = "#1f2937" if checked else color
    width = 3 if checked else 1
    return f"""
        QToolButton {{
            background-color: {color};
            color: {text_color};
            border: {width}px solid {border};
            border-radius: 10px;
            padding: 3px 8px;
            font-weight: bold;
        }}
    """


def effective_color_from_row(row: sqlite3.Row) -> str:
    return normalize_hex_color(str(row["color"] or "")) or normalize_hex_color(str(row["category_color"] or "")) or "#777777"


def colored_square_icon(color: str, size: QSize) -> QIcon:
    pix = QPixmap(size)
    pix.fill(QColor(normalize_hex_color(color) or "#777777"))
    return QIcon(pix)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_path(*parts: str) -> Path:
    """Return a resource path for both normal .py runs and PyInstaller onefile builds."""
    candidates: list[Path] = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS).joinpath(*parts))  # type: ignore[attr-defined]
    candidates.append(get_base_dir().joinpath(*parts))
    candidates.append(Path(__file__).resolve().parent.joinpath(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path(*parts)


def load_window_icon() -> QIcon:
    window_icon_path = get_resource_path(*WINDOW_ICON_RELATIVE)
    if window_icon_path.exists():
        icon = QIcon(str(window_icon_path))
        if not icon.isNull():
            return icon

    exe_icon_path = get_resource_path(*EXE_ICON_RELATIVE)
    if exe_icon_path.exists():
        icon = QIcon(str(exe_icon_path))
        if not icon.isNull():
            return icon

    return QIcon()


def set_windows_app_user_model_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass



def material_path_key(path: Path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except Exception:
        return os.path.normcase(str(Path(path)))


def is_relative_to_path(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def move_path_to_recycle_bin(path: Path) -> bool:
    """Move a file/folder to the Windows Recycle Bin. Returns True when something was moved."""
    path = Path(path)
    if not path.exists():
        return False

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            FO_DELETE = 3
            FOF_SILENT = 0x0004
            FOF_NOCONFIRMATION = 0x0010
            FOF_ALLOWUNDO = 0x0040
            FOF_NOERRORUI = 0x0400

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.USHORT),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            # SHFileOperation requires a double-null-terminated path list.
            from_path = str(path.resolve()) + "\0\0"
            op = SHFILEOPSTRUCTW()
            op.hwnd = None
            op.wFunc = FO_DELETE
            op.pFrom = from_path
            op.pTo = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            op.fAnyOperationsAborted = False
            op.hNameMappings = None
            op.lpszProgressTitle = None

            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if result != 0 or op.fAnyOperationsAborted:
                raise OSError(f"SHFileOperationW failed: result={result}, aborted={bool(op.fAnyOperationsAborted)}")
            return True
        except Exception:
            raise

    # This tool is primarily for Windows EXE distribution. Non-Windows fallback keeps behavior simple.
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def move_paths_to_recycle_bin(paths: Iterable[Path]) -> tuple[int, list[str]]:
    moved = 0
    errors: list[str] = []
    seen: set[str] = set()
    normalized: list[Path] = []
    for raw_path in paths:
        try:
            path = Path(raw_path)
            key = str(path.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            normalized.append(path)

    # Move deeper files before parent folders unless the caller intentionally only provides a folder.
    normalized.sort(key=lambda p: len(p.parts), reverse=True)
    for path in normalized:
        if not path.exists():
            continue
        try:
            if move_path_to_recycle_bin(path):
                moved += 1
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return moved, errors


def remove_empty_dirs(root: Path) -> None:
    if not root.exists() or root.is_file():
        return
    for child in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            child.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass

def safe_filename(name: str) -> str:
    name = name.strip().replace("\x00", "")
    name = re.sub(r"[<>:\"/\\|?*]+", "_", name)
    return name or "image.png"


def normalize_file_stem(name: str) -> str:
    name = name.strip().replace("\x00", "")
    name = Path(name).stem if Path(name).suffix else name
    name = safe_filename(name)
    name = Path(name).stem if Path(name).suffix else name
    return name.strip(" .")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 2
    while True:
        candidate = parent / f"{stem}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def extension_label(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return (ext or "FILE").upper()[:8]


def media_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTS:
        return "image"
    if ext in SUPPORTED_VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in DOCUMENT_EXTS:
        return "document"
    if ext in CODE_EXTS:
        return "code"
    if ext in TEXT_EXTS:
        return "text"
    return "file"


def media_label(media_type: str) -> str:
    return {
        "video": "[VIDEO]",
        "audio": "[AUDIO]",
        "archive": "[ZIP]",
        "document": "[DOC]",
        "code": "[CODE]",
        "text": "[TEXT]",
        "file": "[FILE]",
    }.get(media_type, "")


def color_for_media_type(media_type: str) -> str:
    return {
        "video": "#334155",
        "audio": "#7c3aed",
        "archive": "#b45309",
        "document": "#2563eb",
        "code": "#047857",
        "text": "#4b5563",
        "file": "#374151",
    }.get(media_type, "#374151")


def icon_from_path(path: str, size: QSize) -> QIcon:
    pix = pixmap_from_path(path, size)
    if pix is None:
        return QIcon()
    return QIcon(pix)


def pixmap_from_path(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    pix = QPixmap(str(p))
    if pix.isNull():
        return None
    return pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def has_media_urls(mime_data) -> bool:
    return bool(media_paths_from_mime(mime_data))


def media_paths_from_mime(mime_data) -> list[Path]:
    paths: list[Path] = []
    if mime_data.hasFormat(INTERNAL_MATERIAL_DRAG_MIME):
        return paths
    if not mime_data.hasUrls():
        return paths
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_file():
            paths.append(path)
    return paths


def elide_material_label(text: str, max_chars: int = 22) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    keep = max(1, max_chars - 1)
    return text[:keep] + "…"


def show_file_properties(path: Path) -> bool:
    path = path.resolve()
    if not path.exists():
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            SEE_MASK_INVOKEIDLIST = 0x0000000C
            SW_SHOW = 5

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", wintypes.LPVOID),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("hIcon", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE),
                ]

            info = SHELLEXECUTEINFOW()
            info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
            info.fMask = SEE_MASK_INVOKEIDLIST
            info.hwnd = None
            info.lpVerb = "properties"
            info.lpFile = str(path)
            info.lpParameters = None
            info.lpDirectory = str(path.parent)
            info.nShow = SW_SHOW

            return bool(ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)))
        except Exception:
            return False
    open_path(path.parent)
    return True


def open_path(path: Path) -> None:
    path = path.resolve()
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def main() -> int:
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app_icon = load_window_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    lock = QLockFile(str(get_base_dir() / ".ai-prompt-organizer.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "AI Prompt Organizer は既に起動しています。")
        return 0

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.apply_window_icon)
    QTimer.singleShot(1000, window.apply_window_icon)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
