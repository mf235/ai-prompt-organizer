# -*- coding: utf-8 -*-
"""
AI Prompt Organizer v10

AI生成用プロンプトを、タイトル・タグ・説明・画像付きで管理するローカルGUIツール。
PySide6 + SQLite で動作します。

必要環境:
    pip install PySide6

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
    from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
    from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QKeySequence, QPixmap
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
APP_USER_MODEL_ID = "chappy.ai-prompt-organizer"
WINDOW_ICON_RELATIVE = ("resources", "icons", "window.png")
EXE_ICON_RELATIVE = ("resources", "icons", "app.ico")
DB_FILENAME = "prompt_organizer.db"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


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
        self.conn.commit()
        self.seed_defaults_if_needed()

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

    def ensure_tag(self, name: str, category: str = "custom", color: str = "") -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("empty tag")
        category = normalize_category(category) or "custom"
        self.ensure_category(category, DEFAULT_CATEGORY_COLORS.get(category, "#777777"))
        color = normalize_hex_color(color)
        cur = self.conn.cursor()
        row = cur.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row["id"])
        cur.execute("INSERT INTO tags(name, category, color) VALUES(?, ?, ?)", (name, category, color))
        return int(cur.lastrowid)

    def update_tag(self, tag_id: Optional[int], name: str, category: str, color: str = "") -> int:
        name = normalize_tag(name)
        if not name:
            raise ValueError("タグ名が空です。")
        category = normalize_category(category) or "custom"
        color = normalize_hex_color(color)
        self.ensure_category(category)
        cur = self.conn.cursor()
        if tag_id is None:
            row = cur.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            if row:
                tag_id = int(row["id"])
                cur.execute("UPDATE tags SET category = ?, color = ? WHERE id = ?", (category, color, tag_id))
            else:
                cur.execute("INSERT INTO tags(name, category, color) VALUES(?, ?, ?)", (name, category, color))
                tag_id = int(cur.lastrowid)
        else:
            cur.execute("UPDATE tags SET name = ?, category = ?, color = ? WHERE id = ?", (name, category, color, tag_id))
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
            tag_name = normalize_tag(tag_name)
            if not tag_name or tag_name in seen:
                continue
            seen.add(tag_name)
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
            SELECT t.id, t.name, t.category, t.color, COALESCE(c.color, '#777777') AS category_color,
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

    def add_image(self, prompt_id: int, file_path: str, thumbnail_path: str = "", caption: str = "", is_cover: int = 0) -> int:
        cur = self.conn.cursor()
        max_sort = cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["max_sort"]
        count = cur.execute("SELECT COUNT(*) AS c FROM images WHERE prompt_id = ?", (prompt_id,)).fetchone()["c"]
        if count == 0:
            is_cover = 1
        cur.execute(
            """
            INSERT INTO images(prompt_id, file_path, thumbnail_path, sort_order, caption, is_cover, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (prompt_id, file_path, thumbnail_path, int(max_sort) + 1, caption, is_cover, self.now()),
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
        tag_list = list(dict.fromkeys(normalize_tag(t) for t in tags if normalize_tag(t)))
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

    def __init__(self, color_provider: Callable[[str], str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.color_provider = color_provider
        self.tags: list[str] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("タグを入力して... / Enter・カンマ区切り可")
        self.add_button = QPushButton("追加")
        add_row.addWidget(self.input_edit, 1)
        add_row.addWidget(self.add_button)
        root.addLayout(add_row)

        self.chip_container = QWidget()
        self.flow = FlowLayout(self.chip_container, margin=0, spacing=6)
        self.chip_container.setLayout(self.flow)
        self.chip_container.setMinimumHeight(30)
        root.addWidget(self.chip_container)
        self.input_edit.returnPressed.connect(self.add_from_input)
        self.add_button.clicked.connect(self.add_from_input)

    def set_tags(self, tags: Iterable[str]) -> None:
        self.tags = []
        for tag in tags:
            tag = normalize_tag(tag)
            if tag and tag not in self.tags:
                self.tags.append(tag)
        self.refresh_chips()

    def get_tags(self) -> list[str]:
        return list(self.tags)

    def add_tags(self, tags: Iterable[str]) -> None:
        changed = False
        for tag in tags:
            tag = normalize_tag(tag)
            if tag and tag not in self.tags:
                self.tags.append(tag)
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
            btn.setToolTip("クリックでタグを外す")
            btn.setAutoRaise(False)
            btn.setStyleSheet(chip_style(self.color_provider(tag), checked=True))
            btn.clicked.connect(lambda _checked=False, t=tag: self.remove_tag(t))
            self.flow.addWidget(btn)
        self.chip_container.updateGeometry()


class ImageListWidget(QListWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(140, 105))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(8)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumHeight(170)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if has_image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if has_image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        paths = image_paths_from_mime(event.mimeData())
        if paths:
            self.main_window.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)



class CollapsibleGroupBox(QGroupBox):
    collapsedChanged = Signal(str, bool)

    def __init__(self, title: str, state_key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.plain_title = title
        self.state_key = state_key
        self._collapsed = False
        self._saved_maximum_height = self.maximumHeight()
        self.setTitle(f"▼ {self.plain_title}")
        self.setToolTip("グループ名をクリックすると折りたたみます。")

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
        self.setWindowTitle("タグ管理")
        self.resize(900, 620)
        self.build_ui()
        self.refresh_categories()
        self.refresh_tag_list()
        self.refresh_preset_list()

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
        tag_btn_row = QHBoxLayout()
        tag_btn_row.addWidget(self.new_tag_button)
        tag_btn_row.addWidget(self.save_tag_button)
        tag_btn_row.addWidget(self.delete_tag_button)
        tag_btn_row.addStretch(1)
        tag_form.addLayout(tag_btn_row, 4, 0, 1, 4)
        tag_form.setRowStretch(5, 1)
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
        self.preset_tags_editor = TagChipEditor(color_provider=self.color_provider)
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
            label = f"{name}   [{category}]   ({count})"
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
        self.images_dir = self.assets_dir / "images"
        self.thumbs_dir = self.assets_dir / "thumbnails"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(self.db_path)
        self.current_prompt_id: Optional[int] = None
        self.loading = False
        self.tag_list_loading = False
        self.dirty = False
        self.tag_filter_buttons: list[QToolButton] = []
        self.tag_color_map: dict[str, str] = {}
        self.tag_presets: dict[str, list[str]] = {}
        self.collapsible_sections: list[CollapsibleGroupBox] = []

        self.setWindowTitle(APP_NAME)
        window_icon = load_window_icon()
        if not window_icon.isNull():
            self.setWindowIcon(window_icon)
        self.resize(1320, 900)
        self.setAcceptDrops(True)
        self.build_ui()
        self.build_menu()
        self.connect_signals()
        self.refresh_tags()
        self.reload_preset_combo()
        self.apply_font_size(self.font_size_spin.value(), save=False)
        self.restore_ui_state()
        self.refresh_prompt_list()
        self.statusBar().showMessage(f"DB: {self.db_path}")

    def build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("検索: タイトル / プロンプト / 説明 / タグ")
        left_layout.addWidget(self.search_edit)

        quick_row = QHBoxLayout()
        self.new_button = QPushButton("新規")
        self.duplicate_button = QPushButton("複製")
        self.delete_button = QPushButton("削除")
        quick_row.addWidget(self.new_button)
        quick_row.addWidget(self.duplicate_button)
        quick_row.addWidget(self.delete_button)
        left_layout.addLayout(quick_row)

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
        self.tag_filter_scroll.setMaximumHeight(230)
        tag_layout.addWidget(self.tag_filter_scroll)
        tag_btn_row = QHBoxLayout()
        self.clear_tags_button = QPushButton("タグ解除")
        self.only_favorite_checkbox = QCheckBox("お気に入りのみ")
        tag_btn_row.addWidget(self.clear_tags_button)
        tag_btn_row.addWidget(self.only_favorite_checkbox)
        tag_layout.addLayout(tag_btn_row)
        left_layout.addWidget(tag_box)

        self.prompt_list = QListWidget()
        self.prompt_list.setIconSize(QSize(96, 72))
        self.prompt_list.setUniformItemSizes(False)
        self.prompt_list.setSpacing(4)
        self.prompt_list.setSelectionMode(QAbstractItemView.SingleSelection)
        left_layout.addWidget(self.prompt_list, 1)

        splitter.addWidget(left)

        right = QWidget()
        self.right_widget = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        top_row = QHBoxLayout()
        self.save_button = QPushButton("保存")
        self.copy_prompt_button = QPushButton("プロンプトをコピー")
        self.copy_full_button = QPushButton("タイトル+プロンプトをコピー")
        self.open_assets_button = QPushButton("画像フォルダ")
        self.manage_tags_button = QPushButton("タグ管理")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 28)
        self.font_size_spin.setValue(safe_int(self.db.get_setting("font_size", "10"), 10))
        self.font_size_spin.setSuffix(" pt")
        top_row.addWidget(self.save_button)
        top_row.addWidget(self.copy_prompt_button)
        top_row.addWidget(self.copy_full_button)
        top_row.addWidget(self.manage_tags_button)
        top_row.addStretch(1)
        top_row.addWidget(QLabel("文字サイズ"))
        top_row.addWidget(self.font_size_spin)
        top_row.addWidget(self.open_assets_button)
        right_layout.addLayout(top_row)

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
        self.engine_edit = QLineEdit()
        self.engine_edit.setPlaceholderText("例: ChatGPT / Gemini / Grok / Midjourney")
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("例: GPT-Image / Imagen / Flux など")
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("例: Layer Breaker / ちゃっぴー")
        self.tags_editor = TagChipEditor(color_provider=self.tag_color_for_name)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("タグプリセットを追加...")
        self.add_preset_button = QPushButton("追加")

        meta_layout.addWidget(QLabel("タイトル"), 0, 0)
        meta_layout.addWidget(self.title_edit, 0, 1, 1, 4)
        meta_layout.addWidget(self.favorite_check, 0, 5)
        meta_layout.addWidget(QLabel("評価"), 0, 6)
        meta_layout.addWidget(self.rating_combo, 0, 7)
        meta_layout.addWidget(QLabel("使用AI"), 1, 0)
        meta_layout.addWidget(self.engine_edit, 1, 1)
        meta_layout.addWidget(QLabel("モデル"), 1, 2)
        meta_layout.addWidget(self.model_edit, 1, 3)
        meta_layout.addWidget(QLabel("プロジェクト"), 1, 4)
        meta_layout.addWidget(self.project_edit, 1, 5, 1, 3)
        tag_label = QLabel("タグ")
        tag_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        meta_layout.addWidget(tag_label, 2, 0)
        meta_layout.addWidget(self.tags_editor, 2, 1, 1, 4)
        meta_layout.addWidget(self.preset_combo, 2, 5, 1, 2, Qt.AlignTop)
        meta_layout.addWidget(self.add_preset_button, 2, 7, 1, 1, Qt.AlignTop)
        form_root.addWidget(meta_group)

        prompt_group = CollapsibleGroupBox("プロンプト", "section_prompt_collapsed")
        self.collapsible_sections.append(prompt_group)
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("ここにメインプロンプトを入力")
        self.prompt_edit.setMinimumHeight(190)
        prompt_layout.addWidget(self.prompt_edit)
        form_root.addWidget(prompt_group)

        negative_group = CollapsibleGroupBox("ネガティブ / 補助プロンプト", "section_negative_collapsed")
        self.collapsible_sections.append(negative_group)
        negative_layout = QVBoxLayout(negative_group)
        self.negative_edit = QTextEdit()
        self.negative_edit.setPlaceholderText("ネガティブプロンプトや補助プロンプト。不要なら空でOK")
        self.negative_edit.setMinimumHeight(90)
        negative_layout.addWidget(self.negative_edit)
        form_root.addWidget(negative_group)

        desc_group = CollapsibleGroupBox("説明 / メモ", "section_description_collapsed")
        self.collapsible_sections.append(desc_group)
        desc_layout = QVBoxLayout(desc_group)
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("使いどころ、成功/失敗メモ、修正方針など")
        self.description_edit.setMinimumHeight(110)
        desc_layout.addWidget(self.description_edit)
        form_root.addWidget(desc_group)

        image_group = CollapsibleGroupBox("画像", "section_images_collapsed")
        self.collapsible_sections.append(image_group)
        image_layout = QVBoxLayout(image_group)
        img_btn_row = QHBoxLayout()
        self.add_images_button = QPushButton("画像を追加")
        self.rename_image_button = QPushButton("ファイル名変更")
        self.remove_image_button = QPushButton("選択画像を削除")
        self.cover_image_button = QPushButton("カバーにする")
        self.open_image_button = QPushButton("画像を開く")
        img_btn_row.addWidget(self.add_images_button)
        img_btn_row.addWidget(self.rename_image_button)
        img_btn_row.addWidget(self.remove_image_button)
        img_btn_row.addWidget(self.cover_image_button)
        img_btn_row.addWidget(self.open_image_button)
        img_btn_row.addStretch(1)
        image_layout.addLayout(img_btn_row)
        self.image_list = ImageListWidget(self)
        image_layout.addWidget(self.image_list)
        self.drop_hint_label = QLabel("画像ファイルをここへドラッグ＆ドロップで追加できます。")
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
        new_action = QAction("新規", self)
        new_action.setShortcut(QKeySequence.New)
        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        quit_action = QAction("終了", self)
        quit_action.setShortcut(QKeySequence.Quit)
        new_action.triggered.connect(self.new_prompt)
        save_action.triggered.connect(self.save_current_prompt)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(new_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("編集")
        copy_prompt_action = QAction("プロンプトをコピー", self)
        copy_prompt_action.setShortcut(QKeySequence.Copy)
        copy_prompt_action.triggered.connect(self.copy_prompt)
        duplicate_action = QAction("複製", self)
        duplicate_action.triggered.connect(self.duplicate_prompt)
        tag_manage_action = QAction("タグ管理", self)
        tag_manage_action.triggered.connect(self.open_tag_manager)
        edit_menu.addAction(copy_prompt_action)
        edit_menu.addAction(duplicate_action)
        edit_menu.addSeparator()
        edit_menu.addAction(tag_manage_action)

    def connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self.refresh_prompt_list)
        self.prompt_list.currentItemChanged.connect(self.on_prompt_selected)
        self.clear_tags_button.clicked.connect(self.clear_tag_filters)
        self.only_favorite_checkbox.stateChanged.connect(self.refresh_prompt_list)
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        for section in self.collapsible_sections:
            section.collapsedChanged.connect(self.on_section_collapsed_changed)

        self.new_button.clicked.connect(self.new_prompt)
        self.save_button.clicked.connect(self.save_current_prompt)
        self.duplicate_button.clicked.connect(self.duplicate_prompt)
        self.delete_button.clicked.connect(self.delete_current_prompt)
        self.copy_prompt_button.clicked.connect(self.copy_prompt)
        self.copy_full_button.clicked.connect(self.copy_full_prompt)
        self.open_assets_button.clicked.connect(self.open_current_image_folder)
        self.manage_tags_button.clicked.connect(self.open_tag_manager)
        self.add_preset_button.clicked.connect(self.add_selected_preset)

        self.add_images_button.clicked.connect(self.choose_images)
        self.rename_image_button.clicked.connect(self.rename_selected_image)
        self.remove_image_button.clicked.connect(self.remove_selected_image)
        self.cover_image_button.clicked.connect(self.set_selected_image_as_cover)
        self.open_image_button.clicked.connect(self.open_selected_image)
        self.image_list.itemDoubleClicked.connect(lambda _item: self.open_selected_image())

        for widget in [
            self.title_edit,
            self.engine_edit,
            self.model_edit,
            self.project_edit,
        ]:
            widget.textChanged.connect(self.mark_dirty)
        self.tags_editor.tagsChanged.connect(self.mark_dirty)
        self.favorite_check.stateChanged.connect(self.mark_dirty)
        self.rating_combo.currentIndexChanged.connect(self.mark_dirty)
        self.prompt_edit.textChanged.connect(self.mark_dirty)
        self.negative_edit.textChanged.connect(self.mark_dirty)
        self.description_edit.textChanged.connect(self.mark_dirty)

    def apply_font_size(self, size: int, save: bool = True) -> None:
        size = max(8, min(28, int(size)))
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
        for section in self.collapsible_sections:
            collapsed = self.db.get_setting(section.state_key, "0") == "1"
            section.set_collapsed(collapsed, emit_signal=False)

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

            tags_label = " / ".join(row.tags[:5])
            fav = "★ " if row.favorite else ""
            rating = "★" * row.rating if row.rating else ""
            lines = [f"{fav}{row.title or '(無題)'}"]
            sub = "  ".join(part for part in [row.project, row.engine, rating] if part)
            if sub:
                lines.append(sub)
            if tags_label:
                lines.append(tags_label)
            item = QListWidgetItem("\n".join(lines))
            item.setData(Qt.UserRole, row.id)
            item.setToolTip(f"更新: {row.updated_at}\nタグ: {', '.join(row.tags)}")
            icon = icon_from_path(row.cover_thumb, QSize(96, 72))
            if not icon.isNull():
                item.setIcon(icon)
            self.prompt_list.addItem(item)
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
        self.refresh_prompt_list()

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
        self.loading = True
        self.current_prompt_id = None
        self.title_edit.clear()
        self.engine_edit.clear()
        self.model_edit.clear()
        self.project_edit.clear()
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
        self.engine_edit.setText(str(row["engine"]))
        self.model_edit.setText(str(row["model"]))
        self.project_edit.setText(str(row["project"]))
        self.tags_editor.set_tags(self.db.list_prompt_tags(prompt_id))
        self.favorite_check.setChecked(bool(row["favorite"]))
        rating = max(0, min(5, int(row["rating"])))
        self.rating_combo.setCurrentIndex(rating)
        self.prompt_edit.setPlainText(str(row["prompt"]))
        self.negative_edit.setPlainText(str(row["negative_prompt"]))
        self.description_edit.setPlainText(str(row["description"]))
        self.refresh_images()
        self.loading = False
        self.dirty = False
        self.statusBar().showMessage(f"読み込み: {row['title']}")

    def gather_current_data(self) -> dict:
        return {
            "title": self.title_edit.text().strip() or "(無題)",
            "prompt": self.prompt_edit.toPlainText(),
            "negative_prompt": self.negative_edit.toPlainText(),
            "description": self.description_edit.toPlainText(),
            "engine": self.engine_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "project": self.project_edit.text().strip(),
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
        self.dirty = False
        self.refresh_tags()
        self.reload_preset_combo()
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
        self.statusBar().showMessage("複製しました。画像はコピーせず、プロンプト情報だけ複製しています。")

    def delete_current_prompt(self) -> None:
        if self.current_prompt_id is None:
            return
        title = self.title_edit.text().strip() or "(無題)"
        result = QMessageBox.question(
            self,
            "削除確認",
            f"「{title}」を削除しますか？\nDB上の登録を削除し、assets内の画像ファイルはWindowsのゴミ箱へ移動します。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        deleted_id = self.current_prompt_id
        image_rows = self.db.list_images(deleted_id)
        prompt_asset_dir = self.images_dir / f"prompt_{deleted_id:06d}"
        recycle_targets: list[Path] = []
        if prompt_asset_dir.exists():
            recycle_targets.append(prompt_asset_dir)
        for row in image_rows:
            file_path = Path(str(row["file_path"]))
            thumb_path = Path(str(row["thumbnail_path"] or ""))
            if file_path.exists() and not (prompt_asset_dir.exists() and is_relative_to_path(file_path, prompt_asset_dir)):
                recycle_targets.append(file_path)
            if thumb_path.exists():
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
            self.statusBar().showMessage(f"削除しました。画像ファイルをゴミ箱へ移動: {moved} 件")

    def copy_prompt(self) -> None:
        text = self.prompt_edit.toPlainText()
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("プロンプトをコピーしました")

    def copy_full_prompt(self) -> None:
        parts = []
        title = self.title_edit.text().strip()
        if title:
            parts.append(f"# {title}")
        prompt = self.prompt_edit.toPlainText().strip()
        if prompt:
            parts.append(prompt)
        negative = self.negative_edit.toPlainText().strip()
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
            "画像を選択",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*.*)",
        )
        if files:
            self.add_images_from_paths([Path(f) for f in files])

    def add_images_from_paths(self, paths: Iterable[Path]) -> None:
        paths = [Path(p) for p in paths if Path(p).suffix.lower() in SUPPORTED_IMAGE_EXTS and Path(p).exists()]
        if not paths:
            return
        if not self.ensure_current_prompt_saved_for_images():
            return
        assert self.current_prompt_id is not None
        added = 0
        prompt_asset_dir = self.images_dir / f"prompt_{self.current_prompt_id:06d}"
        prompt_asset_dir.mkdir(parents=True, exist_ok=True)
        for src in paths:
            try:
                dest = unique_path(prompt_asset_dir / safe_filename(src.name))
                if src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
                image_id = self.db.add_image(self.current_prompt_id, str(dest), "")
                thumb_path = self.create_thumbnail(dest, image_id)
                if thumb_path:
                    self.db.update_image_thumbnail(image_id, str(thumb_path))
                added += 1
            except Exception as exc:
                QMessageBox.warning(self, "画像追加エラー", f"画像を追加できませんでした。\n{src}\n\n{exc}")
        if added:
            self.refresh_images()
            self.refresh_prompt_list()
            self.statusBar().showMessage(f"画像を {added} 件追加しました")

    def create_thumbnail(self, src: Path, image_id: int) -> Optional[Path]:
        pix = QPixmap(str(src))
        if pix.isNull():
            return None
        thumb = pix.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_path = self.thumbs_dir / f"thumb_{image_id:08d}.png"
        if thumb.save(str(thumb_path), "PNG"):
            return thumb_path
        return None

    def refresh_images(self) -> None:
        self.image_list.clear()
        if self.current_prompt_id is None:
            return
        for row in self.db.list_images(self.current_prompt_id):
            image_id = int(row["id"])
            file_path = str(row["file_path"])
            thumb_path = str(row["thumbnail_path"] or file_path)
            cover = bool(row["is_cover"])
            stem = Path(file_path).stem
            label = f"★ {stem}" if cover else stem
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, image_id)
            item.setToolTip(file_path)
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

    def rename_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        old_path = Path(str(row["file_path"]))
        if not old_path.exists():
            QMessageBox.warning(self, "ファイル名変更エラー", "画像ファイルが見つかりません。")
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
            self.statusBar().showMessage(f"画像ファイル名を変更しました: {new_path.name}")
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
            "画像削除確認",
            "選択画像の登録を削除しますか？\n画像ファイルはWindowsのゴミ箱へ移動します。",
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
        self.db.delete_image(image_id)
        if not self.db.list_images(prompt_id):
            prompt_asset_dir = self.images_dir / f"prompt_{prompt_id:06d}"
            if prompt_asset_dir.exists():
                recycle_targets.append(prompt_asset_dir)
        moved, errors = move_paths_to_recycle_bin(recycle_targets)
        self.refresh_images()
        self.refresh_prompt_list()
        if errors:
            QMessageBox.warning(self, "画像削除警告", "登録は削除しましたが、一部ファイルをゴミ箱へ移動できませんでした。\n\n" + "\n".join(errors[:5]))
            self.statusBar().showMessage(f"画像登録を削除しました。一部ファイル移動失敗: {len(errors)} 件")
        else:
            self.statusBar().showMessage(f"画像を削除しました。ゴミ箱へ移動: {moved} 件")

    def set_selected_image_as_cover(self) -> None:
        if self.current_prompt_id is None:
            return
        image_id = self.selected_image_id()
        if image_id is None:
            return
        self.db.set_cover_image(self.current_prompt_id, image_id)
        self.refresh_images()
        self.refresh_prompt_list()
        self.statusBar().showMessage("カバー画像を変更しました")

    def open_selected_image(self) -> None:
        image_id = self.selected_image_id()
        if image_id is None:
            return
        row = self.db.get_image(image_id)
        if not row:
            return
        open_path(Path(str(row["file_path"])))

    def open_current_image_folder(self) -> None:
        if self.current_prompt_id is None:
            open_path(self.assets_dir)
            return
        folder = self.images_dir / f"prompt_{self.current_prompt_id:06d}"
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt naming
        if has_image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt naming
        if has_image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt naming
        paths = image_paths_from_mime(event.mimeData())
        if paths:
            if self.current_prompt_id is None:
                first = Path(paths[0])
                new_id = self.db.create_prompt(first.stem)
                self.current_prompt_id = new_id
                self.load_prompt(new_id)
            self.add_images_from_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if not self.maybe_save_dirty():
            event.ignore()
            return
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


def icon_from_path(path: str, size: QSize) -> QIcon:
    if not path:
        return QIcon()
    p = Path(path)
    if not p.exists():
        return QIcon()
    pix = QPixmap(str(p))
    if pix.isNull():
        return QIcon()
    pix = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QIcon(pix)


def has_image_urls(mime_data) -> bool:
    return bool(image_paths_from_mime(mime_data))


def image_paths_from_mime(mime_data) -> list[Path]:
    paths: list[Path] = []
    if not mime_data.hasUrls():
        return paths
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
            paths.append(path)
    return paths


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
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
