
from fastapi import FastAPI

from app.auth import router as auth_router
from app.conversations import router as conversations_router

app = FastAPI(title="Secure Customer AI Chatbot")

app.include_router(auth_router)
app.include_router(conversations_router)


@app.get("/")
def home():
    return {"message": "Secure Customer AI Chatbot API is running!"}


@app.get("/health")
def health():
    return {"status": "healthy"}
