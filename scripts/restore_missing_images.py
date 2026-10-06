#!/usr/bin/env python3
"""Insert Mailchimp campaign images that conversion dropped from markdown posts."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

POSTS_DIR = Path("_posts")
HTML_DIR = POSTS_DIR / "campaigns_content"
CUTOFF = "2025-04-01"

MANUAL_HTML_TO_MD = {
    "14166727_sagevoice-update-8-19.html": "2024-08-19-keeping-humans-in-the-loop.md",
}

SKIP_SRC = re.compile(
    r"(facebook|twitter|instagram|linkedin|pinterest|whatsapp|tiktok|"
    r"list-manage|mailchimp\.com/images|cdn-images\.mailchimp|"
    r"forwardtoafriend|archive-icon|social-block|mceLogo)",
    re.I,
)
SKIP_PREV = re.compile(
    r"view this email in your browser|unsubscribe|update your preferences",
    re.I,
)
IMG_RE = re.compile(
    r"<img\b[^>]*>",
    re.I,
)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*(['"])(.*?)\2""", re.I | re.S)
FILENAME_RE = re.compile(r"/([^/]+\.(?:jpg|jpeg|png|gif|webp))", re.I)
YOUTUBE_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)", re.I)

QUOTE_TRANS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u2014": "-",
        "\u2013": "-",
    }
)


def attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(3) for m in ATTR_RE.finditer(tag)}


def slug_from_html(stem: str) -> str:
    stem = re.sub(r"^\d+_?-?", "", stem)
    stem = re.sub(r"[_-]+$", "", stem)
    return re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-")


def md_stem_clean(name: str) -> str:
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name.lower())
    name = re.sub(r"^(sagevoice-)?(update-)?", "", name)
    return name


def match_md(html_file: Path) -> Path | None:
    if html_file.name in MANUAL_HTML_TO_MD:
        return POSTS_DIR / MANUAL_HTML_TO_MD[html_file.name]

    descriptive = md_stem_clean(slug_from_html(html_file.stem))
    if not descriptive or descriptive in {"untitled", "copy-01"}:
        return None

    best = None
    best_score = 0
    for md in POSTS_DIR.glob("*.md"):
        mdc = md_stem_clean(md.stem)
        score = 0
        if descriptive in mdc or mdc in descriptive:
            score = min(len(descriptive), len(mdc))
        words = [w for w in descriptive.split("-") if len(w) > 2]
        if words:
            matches = sum(1 for w in words if w in mdc)
            if matches >= max(2, len(words) * 0.6):
                score = max(score, matches * 10)
        if score > best_score:
            best_score = score
            best = md
    return best if best_score else None


def preceding_text(html: str, img_start: int) -> str:
    window = html[max(0, img_start - 12000) : img_start]
    # Drop scripts/styles in the window
    window = re.sub(r"<(script|style)\b.*?</\1>", " ", window, flags=re.I | re.S)
    text = BeautifulSoup(window, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\*\|[A-Z_:]+\|\*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if SKIP_PREV.search(text[-200:] if text else ""):
        return ""
    return text[-180:]


def in_header_or_footer(html: str, img_start: int) -> bool:
    window = html[max(0, img_start - 2500) : img_start]
    if "mceSectionFooter" in window and "mceSectionBody" not in window[-800:]:
        return True
    if "mceSectionHeader" in window and "mceSectionBody" not in window[-800:]:
        return True
    return False


def youtube_parent(html: str, img_start: int) -> bool:
    window = html[max(0, img_start - 1500) : img_start]
    last_a = window.rfind("<a")
    if last_a == -1:
        return False
    chunk = window[last_a:]
    return bool(YOUTUBE_RE.search(chunk))


def content_images(html: str) -> list[dict]:
    images = []
    seen = set()
    for match in IMG_RE.finditer(html):
        tag = match.group(0)
        a = attrs(tag)
        classes = {c.lower() for c in a.get("class", "").split()}
        if "mcelogo" in classes:
            continue
        src = a.get("src", "")
        if not src or SKIP_SRC.search(src):
            continue
        if in_header_or_footer(html, match.start()):
            continue
        if youtube_parent(html, match.start()):
            continue
        filename_match = FILENAME_RE.search(src)
        filename = (
            unquote(filename_match.group(1))
            if filename_match
            else Path(urlparse(src).path).name
        )
        if not filename or filename.lower().startswith("default_image"):
            continue
        if filename in seen:
            continue
        prev = preceding_text(html, match.start())
        if SKIP_PREV.search(prev):
            continue
        seen.add(filename)
        images.append(
            {
                "filename": filename,
                "alt": a.get("alt") or filename,
                "prev": prev,
            }
        )
    return images


def snippet_candidates(prev: str) -> list[str]:
    prev = prev.translate(QUOTE_TRANS).strip()
    prev = re.sub(r"\s+", " ", prev)
    if not prev:
        return []
    candidates = []
    words = prev.split()
    for n in (18, 12, 8, 5):
        if len(words) >= n:
            candidates.append(" ".join(words[-n:]))
    if len(prev) >= 25:
        candidates.append(prev[-80:])
    # de-dupe preserving order
    out = []
    for c in candidates:
        if c not in out:
            out.append(c)
    return out


def find_paragraph_end(md: str, snippet: str) -> int | None:
    snippet = snippet.translate(QUOTE_TRANS)
    words = [w for w in re.split(r"\s+", snippet) if w]
    if len(words) < 3:
        return None
    pattern = r"[\s\u00a0]+".join(re.escape(w) for w in words)
    matches = list(re.finditer(pattern, md, flags=re.I))
    if not matches:
        md_norm = md.translate(QUOTE_TRANS)
        pattern_norm = r"\s+".join(re.escape(w) for w in words)
        matches = list(re.finditer(pattern_norm, md_norm, flags=re.I))
        if not matches:
            return None
        # Approximate: use normalized match end as a search hint in original text
        end_word = words[-1]
        idx = md.lower().rfind(end_word.lower())
        if idx == -1:
            return None
        end = idx + len(end_word)
    else:
        end = matches[-1].end()
    para_end = md.find("\n\n", end)
    return len(md) if para_end == -1 else para_end


def img_tag(filename: str, alt: str) -> str:
    alt = alt.replace('"', "&quot;")
    return (
        f'<img src="{{{{ site.baseurl }}}}/assets/images/{filename}" alt="{alt}">'
    )


def restore_post(md_path: Path, images: list[dict]) -> tuple[int, list[str]]:
    md = md_path.read_text(encoding="utf-8")
    present = set(re.findall(r"/assets/images/([^\"')\s>]+)", md))
    missing = [img for img in images if img["filename"] not in present]
    if not missing:
        return 0, []

    insertions: dict[int, list[str]] = defaultdict(list)
    unmatched = []
    for img in missing:
        pos = None
        for snippet in snippet_candidates(img["prev"]):
            pos = find_paragraph_end(md, snippet)
            if pos is not None:
                break
        if pos is None:
            # Fallback: stock-image heading
            m = re.search(
                r"(?im)^.*stock image.*$",
                md,
            )
            if m:
                pos = find_paragraph_end(md, m.group(0).strip()) or m.end()
            else:
                unmatched.append(img["filename"])
                continue
        insertions[pos].append(img_tag(img["filename"], img["alt"]))

    for pos in sorted(insertions, reverse=True):
        block = "\n\n" + "\n\n".join(insertions[pos])
        md = md[:pos] + block + md[pos:]

    md_path.write_text(md, encoding="utf-8")
    inserted = sum(len(v) for v in insertions.values())
    return inserted, unmatched


def main() -> None:
    html_files = sorted(HTML_DIR.glob("*.html"))
    print(f"Scanning {len(html_files)} campaign HTML files")
    total_inserted = 0
    for html_file in html_files:
        md_path = match_md(html_file)
        if not md_path or not md_path.exists():
            continue
        date = md_path.name[:10]
        if date >= CUTOFF:
            continue
        html = html_file.read_text(encoding="utf-8", errors="ignore")
        images = content_images(html)
        if not images:
            continue
        inserted, unmatched = restore_post(md_path, images)
        if inserted or unmatched:
            print(f"{md_path.name}: inserted {inserted}, unmatched {unmatched}")
            total_inserted += inserted
    print(f"\nDone. Inserted {total_inserted} images.")


if __name__ == "__main__":
    main()
