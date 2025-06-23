# Document Analyzer

A modern web application for managing documents, creating prompts, and running batch analysis jobs.

## Features

- Upload and manage documents (supports .txt, .pdf, .doc, .docx)
- Create and manage analysis prompts
- Schedule overnight batch runs for document-prompt combinations
- View and provide feedback on analysis results
- Modern, responsive UI built with NiceGUI

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app/main.py
```

The application will be available at http://localhost:8080

## Usage

### Documents Tab
- Upload single or multiple documents
- Supported formats: .txt, .pdf, .doc, .docx
- View uploaded documents

### Prompts Tab
- Create new analysis prompts
- View and manage existing prompts
- Each prompt can be used across multiple batch runs

### Batch Runs Tab
- Schedule new batch runs
- Select documents and prompts for analysis
- Set execution time for overnight processing
- View status of scheduled and completed runs

### Results Tab
- View analysis results
- Filter results by batch run
- Provide feedback on analysis results

## Project Structure

```
doc_analyzer/
├── app/
│   ├── main.py           # Main application and UI components
│   ├── models.py         # Database models
│   └── batch_processor.py # Background task processor
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Database

The application uses SQLite as the database backend. The database file will be created automatically at first run as `doc_analyzer.db` in the root directory.
