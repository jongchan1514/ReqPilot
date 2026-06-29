# ReqPilot

ReqPilot is a local Flask application for managing RFP requirements, proposal documents, traceability matrices, work logs, todos, and AI-assisted search.

## Features

- Upload RFP PDFs and extract requirements, table of contents, and business information with Gemini.
- Manage requirements and TOC mappings.
- View traceability matrices by TOC or by requirement.
- Analyze proposal coverage against RFP documents or stored requirements.
- Keep todos and work logs.
- Sync local vector chunks for RAG-based assistant answers.

## Setup

Create an environment with Conda:

```powershell
conda env create -f environment.yml
conda activate req-manager
```

Or install with pip:

```powershell
pip install -r requirements.txt
```

Create a local `.env` file:

```powershell
copy .env.example .env
```

Then fill in `GEMINI_API_KEY` and change `SECRET_KEY`.

Run the app:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Local Data

The following paths are intentionally ignored by Git because they can contain secrets, private documents, generated files, or local-only runtime data:

- `.env`
- `instance/`
- `uploads/`
- `logs/`
- `__pycache__/`
- `start_server.vbs`
