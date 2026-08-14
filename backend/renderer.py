"""
renderer.py — Render terminal output as a PNG using Playwright.

Injects the real project path, run command, and stdout into the
terminal.html mockup, then screenshots it with headless Chromium.
"""

import sys
import textwrap
from pathlib import Path
from playwright.sync_api import sync_playwright

TEMPLATE_PATH = Path(__file__).parent / "templates" / "terminal.html"

# Derive project root (two levels up from this file: backend/ → project root)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Map language → the command that was actually run by executor.py
LANGUAGE_COMMAND: dict[str, str] = {
    "Python": "python main.py",
    "C": "gcc main.c -o main.exe && main.exe",
    "C++": "g++ main.cpp -o main.exe && main.exe",
    "Java": "javac Main.java && java Main",
    "JavaScript": "node main.js",
    "Rust": "rustc main.rs -o main.exe && main.exe",
}


def _escape_html(text: str) -> str:
    """Escape special HTML characters (pre-wrap handles newlines natively)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_terminal(output: str, language: str = "Python") -> bytes:
    """
    Render captured stdout into a terminal-style PNG.

    The terminal line displayed looks like:
        (.venv) PS C:\\Users\\vaibh\\Desktop\\lab file generator> python main.py

    Args:
        output:   Text to display (stdout from code execution).
        language: Programming language — used to pick the correct run command.

    Returns:
        PNG image bytes of the rendered terminal element.
    """
    command = LANGUAGE_COMMAND.get(language, f"run {language.lower()}")

    # Build the prompt path string:  (.venv) PS C:\path\to\project>
    prompt_path = f"(.venv) PS {PROJECT_ROOT}> "

    # Clean common leading whitespace and outer blank lines
    cleaned_output = textwrap.dedent(output).strip()

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template.replace("{{PROMPT_PATH}}", _escape_html(prompt_path))
        .replace("{{COMMAND}}", _escape_html(command))
        .replace("{{OUTPUT}}", _escape_html(cleaned_output))
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # device_scale_factor=2 forces 2x (Retina) pixel density,
        # producing a crisp high-resolution screenshot on all servers.
        context = browser.new_context(
            viewport={"width": 960, "height": 800},
            device_scale_factor=2,
        )
        page = context.new_page()
        page.set_content(html, wait_until="load")

        terminal = page.locator("#terminal")
        png_bytes = terminal.screenshot()

        browser.close()

    return png_bytes
