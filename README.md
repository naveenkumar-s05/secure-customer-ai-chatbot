# Secure Customer AI Chatbot

A secure, AI-powered customer chatbot that answers invoice questions using customer-specific data and supports invoice creation through a review-and-confirm workflow.

## Overview

The **Secure Customer AI Chatbot** lets authenticated customers interact with their invoice information using natural-language messages. Instead of manually searching through invoice records, a customer can ask the assistant questions such as:

- “Show me my invoices.”
- “Which invoices are unpaid?”
- “Prepare a new invoice for me.”

The backend authenticates customers using OTP verification, stores customer and conversation data in PostgreSQL, and uses retrieval-augmented generation (RAG) to find relevant invoice records. When a customer requests a new invoice, the assistant prepares a preview. The invoice is saved only after the customer confirms the proposal.

## Features

- **OTP-based authentication:** Verify a customer's mobile number and issue a bearer access token.
- **Protected API endpoints:** Use authentication to identify the customer making a request.
- **Conversation management:** Create conversations, list them, send messages, and retrieve chat history.
- **Customer-specific invoice retrieval:** Search invoice information relevant to the authenticated customer.
- **AI-powered responses:** Use a local language model to formulate responses based on retrieved records.
- **Invoice preview and confirmation:** Review a proposed invoice before confirming its creation.
- **Persistent storage:** Store customer accounts, invoices, conversations, and messages in PostgreSQL.
- **Vector search:** Use Qdrant to support retrieval of indexed invoice records.
- **API documentation:** Explore and test endpoints through FastAPI Swagger UI.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend application logic |
| FastAPI | REST API framework |
| Uvicorn | Local ASGI server |
| PostgreSQL | Relational database |
| SQLAlchemy | Database access and ORM |
| Alembic | Database migrations |
| Qdrant | Vector storage and retrieval |
| Ollama | Local language model and embedding runtime |
| Swagger UI | Interactive API testing |

## Architecture

```text
Customer
   |
   v
FastAPI API
   |
   +--> OTP Authentication --> Bearer Access Token
   |
   +--> Conversation API
            |
            v
       AI Assistant
            |
            +--> Invoice question --> Customer-scoped retrieval
            |                           |
            |                           v
            |                     Qdrant / Invoice data
            |
            +--> Invoice request --> Proposal preview
                                        |
                                        v
                                  Customer confirmation
                                        |
                                        v
                                  PostgreSQL + indexing
```

PostgreSQL is the primary store for customer and invoice records. Qdrant supports retrieval over indexed invoice data. The application uses the authenticated customer's identity to scope access to customer-specific information.

## Project Structure

```text
secure-customer-chatbot/
├── app/
│   ├── assistant.py
│   ├── auth.py
│   ├── config.py
│   ├── conversations.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── rag.py
│   └── schemas.py
├── alembic/
│   └── versions/
├── alembic.ini
├── index_invoices.py
├── seed_data.py
├── test_rag.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Prerequisites

Install or prepare the following before running the project:

- Python compatible with the dependencies in `requirements.txt`
- PostgreSQL
- Ollama
- Git

The application also requires the chat model and embedding model configured in the project. For this project, the intended local models include Qwen for chat and `nomic-embed-text` for embeddings.

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/secure-customer-ai-chatbot.git
cd secure-customer-ai-chatbot
```

Replace `YOUR-USERNAME` with your GitHub username and use the repository URL you created.

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root. Add the variables required by the application, using the names expected by `app/config.py`.

Example placeholders:

```env
DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<database_name>
SECRET_KEY=replace-with-a-secure-secret
```

Add any model or Ollama configuration variables required by your local setup.

**Do not commit `.env` or real credentials to GitHub.** Keep secrets in your local environment.

### 5. Prepare the PostgreSQL database

Create the PostgreSQL database specified in your `DATABASE_URL`. Then apply the project's Alembic migrations:

```powershell
alembic upgrade head
```

If the project requires sample customer and invoice data, run the seed script:

```powershell
python seed_data.py
```

Use the seed script according to its intended behavior; avoid running it repeatedly if it inserts duplicate test records.

### 6. Prepare the local AI models

Start Ollama and ensure the chat and embedding models configured by the project are available. For example, if these are the models used in your configuration:

```powershell
ollama pull qwen2.5
ollama pull nomic-embed-text
```

If your `app/config.py` specifies different model names, use those names instead.

### 7. Index invoice records

After the database has been populated, run the invoice-indexing script:

```powershell
python index_invoices.py
```

This prepares invoice records for retrieval through Qdrant.

**Important:** The project's Qdrant storage is local. Avoid running the indexing script while another application process is using the same local Qdrant data directory. Stop the API server before running indexing or direct Qdrant maintenance commands.

### 8. Start the FastAPI server

```powershell
uvicorn app.main:app
```

Open the interactive API documentation in your browser:

- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Use the Swagger interface to test authentication, conversation, message, invoice retrieval, and invoice confirmation endpoints.

## Typical Usage Flow

1. Request an OTP using the authentication endpoint.
2. Verify the OTP and obtain a bearer access token.
3. Authorize Swagger requests using the token.
4. Create a conversation.
5. Send a natural-language invoice question.
6. Review the assistant's answer, which is based on retrieved invoice information.
7. For invoice creation, review the proposed invoice and explicitly confirm it before it is saved.

## Testing

The project includes `test_rag.py` for testing retrieval behavior. Run it according to the test script's setup requirements:

```powershell
python test_rag.py
```

The API can also be tested through Swagger UI. Demonstrated project workflows include OTP authentication, authenticated customer identification, conversation operations, invoice retrieval, invoice proposal and confirmation, and database verification.

For a more complete test suite, add tests for invalid or expired OTPs, missing or invalid access tokens, unauthorized conversation access, cross-customer invoice access, invalid invoice fields, and duplicate invoice handling.

## Security Notes

- Never commit `.env`, access tokens, OTPs, database passwords, or API secrets.
- Keep customer data access enforced by backend authentication and ownership checks.
- Do not rely on the language model alone to enforce authorization.
- Treat local database and Qdrant files as development data; do not publish real customer information.
- Use fresh credentials if a token or secret is accidentally exposed.

## Future Improvements

- Build a dedicated customer-facing frontend.
- Expand automated API and security tests.
- Add structured logging and monitoring.
- Improve deployment configuration and production secret management.
- Add clearer recovery and re-indexing workflows for invoice data.

## Author

**Naveen Kumar S**

Internship project: Secure Customer AI Chatbot
