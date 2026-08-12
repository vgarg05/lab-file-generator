# Lab File Generator

An AI-powered SaaS-style web tool that automatically generates complete, college-formatted `.docx` lab experiment files — with **Aim, Software Used, Theory, Code, and terminal Output** — in a single click using Google Gemini.

---

## ✨ Features

- 🤖 **AI-Generated Content** — Gemini generates theory, clean source code, and software details automatically based on your experiment aim.
- 🖥️ **VS Code-Style Terminal Output** — Execution output is rendered as a realistic VS Code dark terminal screenshot (Consolas font, charcoal background) and embedded directly in the document.
- 📊 **Automatic Graph Embedding** — If the generated code produces a matplotlib chart (e.g., Linear Regression plots), the graph is automatically saved and inserted into the Output section of the Word document.
- 📝 **Formatted Word Document** — Output is a properly structured `.docx` with Times New Roman font, correct heading hierarchy, and A4 page layout — ready to print.
- 🔄 **Self-Healing Code** — If the generated code fails to run, Gemini automatically analyses the error and fixes the code — retrying up to 3 times.
- 📌 **Optional Additional Instructions** — You can give the AI extra guidance, e.g., *"Use recursion"*, *"Explain time complexity"*, or paste your own code snippets/functions for the AI to incorporate.
- 🌐 **Multi-Language Support** — Python, C, C++, Java, JavaScript, and Rust.

---

## 🛠️ Tech Stack

| Layer              | Technology                          |
|--------------------|-------------------------------------|
| LLM                | Gemini 2.0 Flash (Google)           |
| Code Execution     | Local Subprocess (`.venv` Python)   |
| Terminal Rendering | Playwright → HTML/CSS → PNG         |
| Document Builder   | `python-docx`                       |
| Backend            | FastAPI + Uvicorn                   |
| Frontend           | Vanilla HTML / CSS / JS             |

---

## ⚙️ Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 3. Install Playwright browser

```powershell
python -m playwright install chromium
```

### 4. Add your Gemini API key

Open `.env` and replace the placeholder:

```
GEMINI_API_KEY=your_actual_key_here
```

Get a free key at: https://aistudio.google.com/app/apikey

---

## ▶️ Run

From the project root (`lab file generator/`):

```powershell
uvicorn backend.main:app --reload
```

Then open your browser at: **http://127.0.0.1:8000**

---

## 📖 Usage

1. Enter the **Experiment Number** (e.g. `1`) — used as the document title header (`Experiment - 1`) and the downloaded filename (`Experiment_1.docx`).
2. Select the **Programming Language**.
3. Type your **Experiment Aim** (e.g. `Write a program to implement Bubble Sort`).
4. *(Optional)* Add **Additional Instructions** — e.g., *"Use recursion"*, *"Explain time complexity"*, or paste a code snippet for the AI to use.
5. Click **Generate Lab File**.
6. Wait ~15–25 seconds for the pipeline to complete.
7. Your `Experiment_N.docx` downloads automatically.

---

## 📄 Document Format

```
Experiment - N              → Times New Roman 16pt Bold, Centered

Aim:                        → TNR 16pt Bold + inline aim text (14pt)

Software Used:              → TNR 16pt Bold + inline software details (14pt)

Theory:                     → TNR 16pt Bold, Left
  <ai-generated paragraphs> → TNR 14pt

Code:                       → TNR 16pt Bold, Left
  <source code>             → TNR 14pt

Output:                     → TNR 16pt Bold, Left
  [VS Code terminal PNG]    → Rendered execution output screenshot
  [Plot image]              → (Only if code generates a matplotlib chart)
```

---

## 🗂️ Project Structure

```
lab file generator/
├── backend/
│   ├── __init__.py
│   ├── main.py          → FastAPI app & generation pipeline
│   ├── generator.py     → Gemini API (theory + code + software + fix)
│   ├── executor.py      → Local subprocess runner + plot capture
│   ├── renderer.py      → Playwright terminal PNG renderer
│   ├── assembler.py     → python-docx document builder
│   └── templates/
│       └── terminal.html → VS Code dark terminal HTML template
├── frontend/
│   ├── index.html       → SaaS dashboard UI
│   ├── style.css        → Dashboard styles & animations
│   └── app.js           → Form handler & download logic
├── requirements.txt
├── .env                 → Add your GEMINI_API_KEY here
└── README.md
```

---

## 📌 Notes

- **Supported languages:** Python, C, C++, Java, JavaScript, Rust
- Java code is auto-forced to use `public class Main` so the compiler can resolve the entry point.
- Code is executed **locally** inside your `.venv` virtual environment — so packages like `numpy`, `torch`, `matplotlib`, and `sklearn` work out of the box if installed.
- If generated code produces a `plot.png` (via `plt.savefig`), it is automatically embedded in the Word document under the Output section.
- The `.docx` is built entirely in-memory — no temporary files are written to disk.
