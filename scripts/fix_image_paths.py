#!/usr/bin/env python3
"""Fix image paths in markdown posts to use {{ site.baseurl }}"""

import re
import sys
from pathlib import Path


def fix_image_paths(content):
    """Replace markdown image syntax and HTML img tags with baseurl"""

    # Pattern 1: Markdown image syntax ![alt](/assets/images/file.ext)
    # Replace with: <img src="{{ site.baseurl }}/assets/images/file.ext" alt="alt">
    markdown_pattern = r"!\[([^\]]*)\]\((/assets/images/[^\)]+)\)"

    def markdown_replacer(match):
        alt_text = match.group(1)
        img_path = match.group(2)
        return f'<img src="{{{{ site.baseurl }}}}{img_path}" alt="{alt_text}">'

    content = re.sub(markdown_pattern, markdown_replacer, content)

    # Pattern 2: HTML img tags with /assets/images/ that don't already have baseurl
    # Replace: <img src="/assets/images/file.ext" ...>
    # With: <img src="{{ site.baseurl }}/assets/images/file.ext" ...>
    html_pattern = r'(<img\s+[^>]*src=")(/assets/images/[^"]+)(")'

    def html_replacer(match):
        if "{{ site.baseurl }}" in match.group(0):
            return match.group(0)  # Already has baseurl, skip
        prefix = match.group(1)
        img_path = match.group(2)
        suffix = match.group(3)
        return f"{prefix}{{{{ site.baseurl }}}}{img_path}{suffix}"

    content = re.sub(html_pattern, html_replacer, content)

    return content


def main():
    posts_dir = Path("_posts")

    if not posts_dir.exists():
        print(f"Error: {posts_dir} directory not found")
        sys.exit(1)

    updated_count = 0
    total_images = 0

    for md_file in sorted(posts_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            original_content = content

            # Count images before
            image_count = len(re.findall(r"/assets/images/", content))
            if image_count == 0:
                continue

            # Fix image paths
            content = fix_image_paths(content)

            # Check if anything changed
            if content != original_content:
                md_file.write_text(content, encoding="utf-8")
                updated_count += 1
                total_images += image_count
                print(f"✓ Updated {md_file.name} ({image_count} images)")

        except Exception as e:
            print(f"✗ Error processing {md_file.name}: {e}")

    print(
        f"\nSummary: Updated {updated_count} files with {total_images} total image references"
    )


if __name__ == "__main__":
    main()
