from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


START_MARKER = "<!-- BRIXEL_DEVLOG_ENTRIES_START -->"
END_MARKER = "<!-- BRIXEL_DEVLOG_ENTRIES_END -->"


@dataclass
class DevEntry:
    source_path: Path
    title: str
    date: datetime
    summary: str
    image: str
    project: str
    entry_type: str
    body: str


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def parse_frontmatter_value(value: str) -> str:
    value = value.strip()

    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        value = value[1:-1]

    return value.strip()


def parse_markdown_file(path: Path) -> DevEntry:
    raw = path.read_text(encoding="utf-8-sig")

    if not raw.startswith("---"):
        raise ValueError(f"{path.name} is missing front matter block.")

    parts = raw.split("---", 2)

    if len(parts) < 3:
        raise ValueError(f"{path.name} has invalid front matter.")

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    metadata: dict[str, str] = {}

    for line in frontmatter_text.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        metadata[key.strip()] = parse_frontmatter_value(value)

    required_fields = ["title", "date", "summary", "image"]

    for field in required_fields:
        if not metadata.get(field):
            raise ValueError(f"{path.name} is missing required field: {field}")

    date_value = metadata["date"]

    try:
        date_obj = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date_obj = datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(
                f"{path.name} has invalid date: {date_value}. "
                "Use YYYY-MM-DD."
            ) from error

    return DevEntry(
        source_path=path,
        title=metadata["title"],
        date=date_obj,
        summary=metadata["summary"],
        image=metadata["image"],
        project=metadata.get("project", "Brixel House"),
        entry_type=metadata.get("entryType", "Dev Diary"),
        body=body,
    )


def format_display_date(date_obj: datetime) -> str:
    if sys.platform == "win32":
        return date_obj.strftime("%B %#d, %Y")

    return date_obj.strftime("%B %-d, %Y")


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)

    # Bold: **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    # Italic: *text*
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)

    # Markdown links: [text](https://example.com)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )

    # Plain URLs
    escaped = re.sub(
        r"(?<!href=\")(?<!\">)(https?://[^\s<]+)",
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )

    return escaped


def markdown_body_to_html(body: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    output: list[str] = []

    for block in blocks:
        lines = block.splitlines()
        first_line = lines[0].strip()

        if first_line.startswith("### "):
            output.append(f"        <h4>{inline_markdown_to_html(first_line[4:].strip())}</h4>")
            continue

        if first_line.startswith("## "):
            output.append(f"        <h4>{inline_markdown_to_html(first_line[3:].strip())}</h4>")
            continue

        if all(line.strip().startswith("- ") for line in lines):
            output.append("        <ul>")
            for line in lines:
                item = line.strip()[2:].strip()
                output.append(f"          <li>{inline_markdown_to_html(item)}</li>")
            output.append("        </ul>")
            continue

        paragraph = " ".join(line.strip() for line in lines)
        output.append(f"        <p>{inline_markdown_to_html(paragraph)}</p>")

    return "\n".join(output)


def render_entry(entry: DevEntry) -> str:
    entry_id = f"{entry.date.strftime('%Y-%m-%d')}-{slugify(entry.title)}"

    title = html.escape(entry.title)
    summary = html.escape(entry.summary)
    project = html.escape(entry.project)
    entry_type = html.escape(entry.entry_type)
    display_date = format_display_date(entry.date)
    image = html.escape(entry.image)
    image_alt = html.escape(f"{entry.title} dev diary image")
    body_html = markdown_body_to_html(entry.body)

    return f"""        <article class="dev-entry-card" id="{entry_id}">
          <div class="dev-entry-media">
            <img
              src="{image}"
              alt="{image_alt}"
            >
          </div>

          <div class="dev-entry-copy">
            <p class="status-pill">{entry_type}</p>
            <p class="dev-entry-date">{display_date} · {project}</p>

            <h3>{title}</h3>

            <p class="dev-entry-summary">
              {summary}
            </p>

{body_html}
          </div>
        </article>"""


def load_entries(posts_dir: Path) -> list[DevEntry]:
    if not posts_dir.exists():
        raise FileNotFoundError(f"Posts folder not found: {posts_dir}")

    markdown_files = sorted(posts_dir.glob("*.md"))

    if not markdown_files:
        raise FileNotFoundError(f"No .md files found in: {posts_dir}")

    entries = []

    for path in markdown_files:
        entries.append(parse_markdown_file(path))

    entries.sort(key=lambda entry: entry.date, reverse=True)
    return entries


def replace_between_markers(page_html: str, generated_html: str) -> str:
    start_index = page_html.find(START_MARKER)
    end_index = page_html.find(END_MARKER)

    if start_index == -1:
        raise ValueError(f"Missing start marker: {START_MARKER}")

    if end_index == -1:
        raise ValueError(f"Missing end marker: {END_MARKER}")

    if end_index < start_index:
        raise ValueError("End marker appears before start marker.")

    before = page_html[: start_index + len(START_MARKER)]
    after = page_html[end_index:]

    return f"{before}\n{generated_html}\n        {after}"


def run_command(command: str, cwd: Path) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
    )

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.stderr.strip():
        print(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}")


def build(repo_dir: Path, push: bool) -> None:
    posts_dir = repo_dir / "_posts"
    devdiary_path = repo_dir / "devdiary.html"

    if not devdiary_path.exists():
        raise FileNotFoundError(f"devdiary.html not found: {devdiary_path}")

    entries = load_entries(posts_dir)
    rendered_entries = "\n\n".join(render_entry(entry) for entry in entries)

    original_html = devdiary_path.read_text(encoding="utf-8")
    updated_html = replace_between_markers(original_html, rendered_entries)

    backup_path = devdiary_path.with_suffix(".html.bak")
    shutil.copy2(devdiary_path, backup_path)

    devdiary_path.write_text(updated_html, encoding="utf-8")

    print(f"Built {len(entries)} dev diary entr{'y' if len(entries) == 1 else 'ies'}.")
    print(f"Updated: {devdiary_path}")
    print(f"Backup:  {backup_path}")

    if push:
        run_command("git status --short", repo_dir)
        run_command("git add devdiary.html _posts assets/blog css/style.css index.html frontmatter.json", repo_dir)
        run_command('git commit -m "Update Brixel House dev diary"', repo_dir)
        run_command("git push", repo_dir)
        print("Committed and pushed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Brixel House Dev Diary entries.")
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the brixelhouse-site repo. Defaults to current folder.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Commit and push after successful build.",
    )

    args = parser.parse_args()

    repo_dir = Path(args.repo).resolve()

    try:
        build(repo_dir, args.push)
        return 0
    except Exception as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())