"""
generator.py — Gemini API integration.
Handles theory generation, code generation, and code fixing.
"""

import os
import json
import re

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

# Model for structured JSON output (theory + code together)
_json_model = genai.GenerativeModel(
    model_name="gemini-3.1-flash-lite",
    generation_config=genai.types.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.3,
    ),
)

# Plain model for code fixing (no JSON mode needed)
_plain_model = genai.GenerativeModel(
    model_name="gemini-3.1-flash-lite",
    generation_config=genai.types.GenerationConfig(
        temperature=0.2,
    ),
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if the model wraps output despite being told not to."""
    text = text.strip()
    # Remove leading fence with optional language tag
    text = re.sub(r"^```[a-zA-Z+#]*\n?", "", text)
    # Remove trailing fence
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_theory_and_code(aim: str, language: str, instructions: str = "") -> dict:
    """
    Call Gemini to produce both theory and source code for the experiment.

    Returns:
        dict with keys "theory" (str), "code" (str), and "software" (str)
    """
    java_note = (
        'IMPORTANT: Since the language is Java, the public class MUST be named "Main" '
        "so the file can be saved as Main.java and executed correctly."
        if language == "Java"
        else ""
    )

    instructions_note = ""
    if instructions.strip():
        instructions_note = (
            "\nIMPORTANT CUSTOM REQUIREMENTS:\n"
            "You MUST adapt the generated code or theory according to these guidelines:\n"
            f"- {instructions.strip()}\n"
        )

    prompt = f"""You are an assistant generating content for a college lab experiment document.

Experiment Aim : {aim}
Programming Language : {language}

Return a JSON object with exactly three keys:

1. "theory"
   - 3 to 5 paragraphs of concise, textbook-style academic theory.
   - Explain the core concepts, algorithm steps (if applicable), and real-world relevance.
   - Tone: formal, undergraduate computer science lab manual.
   - Plain text only — no markdown, no bullet points, no headings.

2. "code"
   - Complete, self-contained, working {language} source code that fulfils "{aim}".
   - The program must produce visible output when executed.
   - All print/output statements must output text that is flush to the left (do not put leading spaces, tabs, or indents inside print strings like "  Value: " unless explicitly formatting an aligned data table).
   - If the program generates any plots, charts, or figures (e.g., using matplotlib or seaborn), you MUST write 'import matplotlib; matplotlib.use("Agg")' BEFORE importing pyplot, and save the figure as 'plot.png' using 'plt.savefig("plot.png", bbox_inches="tight")' instead of using 'plt.show()'.
   - Raw source code only — no markdown code fences, no explanations.
   {java_note}

3. "software"
   - A short, concise comma-separated string listing the software and tools used/required (e.g. compiler, interpreter, IDE, libraries, OS) according to the aim (e.g. "Python 3.8+, PyTorch, NumPy, VS Code", or "GCC Compiler, VS Code, Windows 10/11").

{instructions_note}
Return ONLY the JSON object, nothing else."""

    response = _json_model.generate_content(prompt)
    data = json.loads(response.text)

    return {
        "theory": data.get("theory", "").strip(),
        "code": _strip_code_fences(data.get("code", "")),
        "software": data.get("software", "VS Code, Windows 10/11").strip(),
    }


def fix_code(code: str, error: str, aim: str, language: str) -> str:
    """
    Ask Gemini to fix code that produced a compile / runtime error.

    Returns:
        Fixed source code as a plain string.
    """
    java_note = (
        'IMPORTANT: The public class MUST be named "Main".'
        if language == "Java"
        else ""
    )

    prompt = f"""The following {language} code produced an error when executed. Fix it so it runs correctly.

Original Aim: {aim}

--- Code ---
{code}

--- Error ---
{error}

{java_note}
Return ONLY the corrected {language} source code. No markdown code fences, no explanations."""

    response = _plain_model.generate_content(prompt)
    return _strip_code_fences(response.text)
