# Quantum Materials Lab — AI Archival System

An AI-assisted archival system to organize research data from Dropbox, paper growth records, and files shared through Slack. Some sources overlap, so part of the project will be identifying duplicates and connecting related records. The goal is to make the data easier to search, sort, and use.

The planned system will use AI to extract crystal-growth data into structured JSON, compare outputs across models, and flag discrepancies for human review. A web interface will support photo and file uploads across devices, with a Python/FastAPI backend and SQLite database for searchable storage, filtering, and CSV export.

We’ll start with a small pilot to test different AI models and prompts before expanding to the full dataset.

- **[Design document](DESIGN.md)**
- **[Start with the pilot](pilot/README.md)**
- [View the first ChatGPT result](pilot/runs/chatgpt/pdf-to-json/run01/output.json)
- [See its prompt](pilot/runs/chatgpt/pdf-to-json/run01/pdf-to-json-v1.text)
- [Project board](https://github.com/users/irisyjchang/projects/2)

The current result is **unvalidated**.
