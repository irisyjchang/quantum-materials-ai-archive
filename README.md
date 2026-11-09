# Quantum Materials Lab — AI Archival System

An AI-assisted archival system to organize research data from Dropbox, paper growth records, and files shared through Slack. Some sources overlap, so part of the project will be identifying duplicates and connecting related records. The goal is to make the data easier to search, sort, and use.

The MVP processes existing growth log PDFs from Google Drive and extracts data into JSON. A human reviewer approves every run before the app saves it to SQLite. Researchers can search approved runs and open downloaded source PDFs offline.

The pilot adds photo uploads and a shared review workflow so authorized reviewers can approve runs from different devices.

- **[MVP design](DESIGN.md)**
- **[Pilot design](pilot/DESIGN.md)**
- [Early extraction tests](pilot/README.md)
- [View the first ChatGPT result](pilot/runs/chatgpt/pdf-to-json/run01/output.json)
- [See its prompt](pilot/runs/chatgpt/pdf-to-json/run01/pdf-to-json-v1.text)
- [Project board](https://github.com/users/irisyjchang/projects/2)

The current result is **unvalidated**.
