from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import every model before create_all.
from app.models.user import User
from app.models.auth import AuthChallenge, UserSession
from app.models.client import Client
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import PaymentAttempt, Transaction

from app.core.config import settings
from app.core.database import Base, engine

from app.api import auth, invoices, payments, reports, clients, relayer

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PayFlow API",
    description="Cross-chain invoicing with USDC settlement on NEAR",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(clients.router, prefix="/api")
app.include_router(relayer.router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": "PayFlow",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}