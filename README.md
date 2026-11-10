# Quantum Materials Lab — AI Archival System

An AI-assisted archival system to organize research data from Dropbox, paper growth records, and files shared through Slack. Some sources overlap, so part of the project will be identifying duplicates and connecting related records. The goal is to make the data easier to search, sort, and use.

The MVP uses one Codex skill, `stage-log-runs`, to check risk, extract the measurement table from existing growth log PDFs, and stage validated drafts in SQLite. A separate review app on the project operator’s laptop lets a lab-authorized reviewer inspect the source log, correct fields, and approve runs for search. The MVP workflow uses the operator’s ChatGPT subscription and requires no API key.

The pilot adds photo uploads and moves the app to a shared host so authorized reviewers can review and approve runs online from their own devices.

- **[MVP design](DESIGN.md)**
- **[Pilot design](pilot/DESIGN.md)**
- [Early extraction tests](pilot/README.md)
- [View the first ChatGPT result](pilot/runs/chatgpt/pdf-to-json/run01/output.json)
- [See its prompt](pilot/runs/chatgpt/pdf-to-json/run01/pdf-to-json-v1.text)
- [Project board](https://github.com/users/irisyjchang/projects/2)

The current result is **unvalidated**.
