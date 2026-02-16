# Project: Business Automation Suite

## Project Overview
This project contains automation scripts for business workflows including:
- Invoice processing from email attachments
- Customer data synchronization between systems
- Automated report generation and distribution
- API integrations with third-party services

## Architecture
- **Backend**: Python 3.9+ with FastAPI
- **Database**: PostgreSQL 14+
- **Queue**: Redis for async task processing
- **Storage**: AWS S3 for document archival
- **Notifications**: Slack webhooks

## Key Directories
- `/src/` - Main application code
  - `/extractors/` - Data extraction modules
  - `/transformers/` - Data transformation logic
  - `/loaders/` - Database and API loaders
  - `/workflows/` - Complete workflow orchestrators
- `/config/` - Configuration files (YAML)
- `/scripts/` - Executable automation scripts
- `/tests/` - Test suites (pytest)
- `/logs/` - Application logs

## Dependencies
- Core: pandas, requests, python-dotenv
- Database: psycopg2-binary, sqlalchemy
- PDF Processing: PyPDF2, pdfplumber
- Email: imaplib (built-in)
- Testing: pytest, pytest-mock, pytest-cov

## Coding Standards
- Use type hints for all function signatures
- Document all functions with docstrings (Google style)
- Follow PEP 8 style guide
- Write unit tests for all business logic
- Use dataclasses for data structures
- Implement proper error handling with specific exceptions
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)

## Common Commands
```bash
# Setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Testing
pytest tests/ -v
pytest tests/ --cov=src

# Run workflows
python scripts/run_invoice_pipeline.py
python scripts/run_customer_sync.py

# Linting
flake8 src/
black src/ --check
mypy src/
```

## Environment Variables
Required in `.env` file:
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `IMAP_HOST`
- `SLACK_WEBHOOK_URL`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

## Testing Notes
- Mock external API calls in tests
- Use fixtures in `tests/conftest.py`
- Integration tests require Docker Compose for PostgreSQL
- Run `docker-compose up -d` before integration tests
```

---

## Core Concepts

### 1. Agentic Coding

Claude Code operates autonomously to:
- **Read and understand** your entire codebase structure
- **Plan multi-step solutions** before writing any code
- **Edit multiple files** simultaneously across your project
- **Execute commands** and verify results
- **Handle git workflows** (branches, commits, PRs)

**Example Interaction:**
```
You: Create a complete ETL pipeline that extracts data from MongoDB, 
     transforms it with pandas, and loads it into Snowflake. Include 
     error handling, logging, and unit tests.

Claude Code: [Plans the solution]
├── Analyzes existing codebase structure
├── Identifies required dependencies
├── Plans file structure and class hierarchy
└── Proposes implementation strategy

[Then executes autonomously]
├── Creates src/extractors/mongodb_extractor.py
├── Creates src/transformers/data_transformer.py
├── Creates src/loaders/snowflake_loader.py
├── Creates src/pipeline.py (orchestrator)
├── Creates tests/test_pipeline.py
├── Updates requirements.txt
└── Runs tests to verify
```

### 2. Context Awareness

Claude Code maintains comprehensive context through:

**CLAUDE.md Files**
- Project-level documentation read at session start
- Defines coding standards, architecture, and common patterns
- Provides context about dependencies and workflows

**Conversation History**
- Maintains full context across your session
- Remembers previous decisions and implementations
- Can reference earlier parts of the conversation

**Codebase Understanding**
- Analyzes file relationships and dependencies
- Understands import structures and module organization
- Recognizes design patterns in use

### 3. Checkpointing System

Claude Code automatically saves code state before changes:

- **Automatic snapshots**: Created before each modification
- **Quick rewind**: Press `Esc` twice to undo
- **Selective restore**: Restore code, conversation, or both
- **Command access**: Use `/rewind` command for manual control

**Example Usage:**
```
You: Refactor the entire authentication system to use JWT tokens

[Claude makes extensive changes across 10 files]

You: Actually, I want to keep session-based auth. Let's rewind.

[Press Esc twice or type /rewind]

[Code restored to pre-refactor state]
```

### 4. Subagents & Advanced Features

**Subagents**
Delegate specialized tasks to separate Claude instances:
```
You: Build a payment processing system. Use one subagent for the backend 
     API and another for the frontend checkout form.

Claude Code:
├── Main agent: Coordinates overall architecture
├── Subagent 1: Implements FastAPI payment endpoints
└── Subagent 2: Creates React checkout component