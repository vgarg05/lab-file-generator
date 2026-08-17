"""
generator.py — Gemini API integration.
Handles theory generation, code generation, and code fixing.
"""

import os
import json
import re
import time

import google.generativeai as genai
from dotenv import load_dotenv
from backend.logger import get_logger

logger = get_logger("labgen.generator")

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

# Model for structured JSON output (theory + code together)
_json_model = genai.GenerativeModel(
    model_name="gemini-3.1-flash",
    generation_config=genai.types.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.3,
    ),
)

# Plain model for code fixing (no JSON mode needed)
_plain_model = genai.GenerativeModel(
    model_name="gemini-3.1-flash",
    generation_config=genai.types.GenerationConfig(
        temperature=0.2,
    ),
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if the model wraps output despite being told not to."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z+#]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_theory_and_code(
    aim: str, language: str, code_instructions: str = "", theory_instructions: str = "",
    api_key: str | None = None,
) -> dict:
    """
    Generate the theory, code, and software used for the experiment using the structured prompts.
    """
    start_time = time.time()
    custom_key_str = " (using custom user API key)" if api_key else " (using system API key)"
    logger.info(f"Generating content for language='{language}', aim='{aim[:50]}...'{custom_key_str}")

    if api_key:
        import google.generativeai as _genai
        _genai.configure(api_key=api_key)
        json_model = _genai.GenerativeModel(
            model_name="gemini-3.1-flash",
            generation_config=_genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
    else:
        json_model = _json_model   # shared system-key model
    java_note = (
        'IMPORTANT: Since the language is Java, the public class MUST be named "Main" '
        "so the file can be saved as Main.java and executed correctly."
        if language == "Java"
        else ""
    )

    prompt = f"""You are an AI assistant that generates complete college laboratory experiment files.

The user provides three inputs:

### 1. Experiment Aim
This describes the main experiment or programming task that needs to be completed.

### 2. Theory Instructions
These instructions apply ONLY to the Theory section.
Use them to determine:
* Which concepts and definitions should be explained
* The depth and level of explanation
* Important formulas or equations
* Algorithms or principles that should be discussed theoretically
* Time and space complexity analysis
* Best-case, average-case, and worst-case analysis when relevant
* Examples, applications, advantages, disadvantages, or comparisons
* Any specific theoretical concepts requested by the user

Do NOT use theory instructions to modify the implementation unless they explicitly contain an implementation requirement.

### 3. Code Instructions
These instructions apply ONLY to the Program/Implementation section.
Use them to determine:
* Programming language (specified as: {language})
* Programming approach or algorithm
* Required functions
* Recursion vs. iteration
* Input and output format
* Variable/function naming requirements
* Comments or documentation requirements
* Specific code snippets or custom functions provided by the user
* Formatting requirements
* Constraints or edge cases
* Any other implementation-specific requirements

Do NOT use code instructions to unnecessarily modify the Theory section.

### Generation Rules
Based on the Experiment Aim, Theory Instructions, and Code Instructions:
1. Generate the experiment according to the user's requested aim.
2. Keep theoretical content and implementation content logically separate.
3. Follow all relevant instructions provided by the user.
4. If an instruction is not provided, use appropriate academic conventions.
5. Do not invent requirements that conflict with the user's instructions.
6. Ensure the generated theory is consistent with the generated code.
7. If complexity is requested in the Theory Instructions, provide complexity analysis for the actual algorithm implemented.
8. If the user provides code snippets, functions, equations, formatting rules, or other custom content, incorporate them where appropriate.
9. Prefer clear, concise, college-level explanations rather than unnecessarily advanced explanations.
10. Maintain consistent terminology between the Theory and Code sections.

### Output JSON Format Requirements
You MUST return a JSON object with exactly three keys:
1. "theory"
   - 3 to 5 paragraphs of concise, textbook-style academic theory following the "Theory Instructions".
   - Plain text only — no markdown, no bullet points, no headings, no asterisks, no hash symbols.
   - You MAY include mathematical formulas and equations using standard notation and Unicode symbols (e.g., Σ, μ, σ, ², ³, ≤, ≥, →, ∈, α, β, θ).
   - Write each formula or equation on its own separate line for clarity (e.g., "slope (m) = Σ(xi - x̄)(yi - ȳ) / Σ(xi - x̄)²").
   - If complexity analysis is requested, write it as: "Time Complexity: O(n²)" on its own line.
2. "code"
   - Complete, self-contained, working {language} source code following the "Code Instructions" that fulfills the requested aim.
   - The program must produce visible output when executed.
   - All print/output statements must output text that is flush to the left (do not put leading spaces, tabs, or indents inside print strings like "  Value: " unless explicitly formatting an aligned data table).
   - If the program generates any plots, charts, or figures (e.g., using matplotlib or seaborn), you MUST write 'import matplotlib; matplotlib.use("Agg")' BEFORE importing pyplot, and save the figure as 'plot.png' using 'plt.savefig("plot.png", bbox_inches="tight")' instead of using 'plt.show()'.
   - Raw source code only — no markdown code fences, no explanations.
   {java_note}
3. "software"
   - A short, concise comma-separated string listing the software and tools used/required (e.g. compiler, interpreter, IDE, libraries, OS) according to the aim (e.g. "Python 3.8+, PyTorch, NumPy, VS Code", or "GCC Compiler, VS Code, Windows 10/11").

### Input
Experiment Aim:
{aim}

Theory Instructions:
{theory_instructions if theory_instructions.strip() else "(None provided. Use default college level computer science conventions)"}

Code Instructions:
{code_instructions if code_instructions.strip() else "(None provided. Use default college level computer science conventions)"}

Generate the complete experiment while strictly respecting the separation between theoretical and implementation instructions, returning ONLY the JSON object, nothing else.
"""

    response = json_model.generate_content(prompt)
    data = json.loads(response.text)
    elapsed = time.time() - start_time
    logger.info(f"Gemini content generation completed in {elapsed:.2f}s")

    return {
        "theory": data.get("theory", "").strip(),
        "code": _strip_code_fences(data.get("code", "")),
        "software": data.get("software", "VS Code, Windows 10/11").strip(),
    }


def fix_code(code: str, error: str, aim: str, language: str) -> str:
    """
    Ask Gemini to fix code that produced a compile / runtime error.
    """
    logger.warning(f"Requesting Gemini auto-correct for {language} error: {error[:80]}...")
    start_time = time.time()
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
    fixed = _strip_code_fences(response.text)
    elapsed = time.time() - start_time
    logger.info(f"Gemini auto-correct completed in {elapsed:.2f}s")
    return fixed
