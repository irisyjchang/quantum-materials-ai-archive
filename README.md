# Quantum Materials Lab — AI Archival System

An AI-assisted archival system to organize research data from Dropbox, paper growth records, and files shared through Slack. Some sources overlap, so part of the project will be identifying duplicates and connecting related records. The goal is to make the data easier to search, sort, and use.

The broader vision includes AI-assisted extraction and comparison of model outputs, with discrepancies flagged for human review. The **MVP** is a Python/FastAPI + SQLite web application for importing **human-verified JSON**, searching, filtering, source references, and CSV export. Extraction and human verification happen outside the archive interface. No AI API integration or automatic PDF/photo conversion is included in the MVP.

We’ll start with a small pilot to test different AI models and prompts before expanding to the full dataset.

- **[Start with the pilot](pilot/README.md)**
- **[Design document and MVP scope](docs/design-document.md)** — proposed architecture, import workflow, data model, acceptance criteria, and decisions for lab review.
- **[Questions for the research team](researcher-questions/README.md)**
- [View the first ChatGPT result](pilot/runs/chatgpt/pdf-to-json/run01/output.json)
- [See its prompt](pilot/runs/chatgpt/pdf-to-json/run01/pdf-to-json-v1.text)
- [Project board](https://github.com/users/irisyjchang/projects/2)

The current result is **unvalidated**.
