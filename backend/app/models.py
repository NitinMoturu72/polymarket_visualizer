from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id_encrypted: Mapped[str]
    secret_key_encrypted: Mapped[str]
    created_at: Mapped[str]
    updated_at: Mapped[str]

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    opened_at: Mapped[str | None] 
    closed_at: Mapped[str | None] 
    status: Mapped[str]
    market_title: Mapped[str | None]
    market_slug: Mapped[str]
    outcome: Mapped[str | None]
    outcome_side: Mapped[str | None]
    side_label: Mapped[str | None]
    qty: Mapped[str]
    entry_price: Mapped[str | None]
    exit_price: Mapped[str | None]
    commission: Mapped[str]
    realized_pnl: Mapped[str]
    note: Mapped[str | None]
    synced_at: Mapped[str]

class Withdrawal(Base):
    __tablename__ = "withdrawals"

    transaction_id: Mapped[str] = mapped_column(primary_key=True)
    external_id: Mapped[str | None]
    amount: Mapped[str]
    currency: Mapped[str | None]
    status: Mapped[str | None]
    created_at: Mapped[str | None]
    updated_at: Mapped[str | None]
    description: Mapped[str | None]
    failure_reason: Mapped[str | None]
    failure_code: Mapped[str | None]
    synced_at: Mapped[str]

class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[str]
    started_at: Mapped[str]
    finished_at: Mapped[str | None]
    status: Mapped[str]
    activities_fetched: Mapped[int | None]
    rows_written: Mapped[int | None]
    error_message: Mapped[str | None]
    triggered_by: Mapped[str]