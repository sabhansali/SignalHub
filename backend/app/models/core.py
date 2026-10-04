import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


# SQLAlchemy's generic Uuid works with both PostgreSQL and SQLite.
UUIDType = Uuid(as_uuid=True)
JSONType = JSONB().with_variant(JSON(), "sqlite")


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    RESEARCHER = "RESEARCHER"
    SALES = "SALES"
    PRE_SALES = "PRE_SALES"
    VIEWER = "VIEWER"


class Tier(str, enum.Enum):
    TIER_1 = "TIER_1"
    PRIORITY = "PRIORITY"
    OTHER = "OTHER"


class SourceType(str, enum.Enum):
    COMPANY = "COMPANY"
    INVESTOR = "INVESTOR"
    PRESS_RELEASE = "PRESS_RELEASE"
    ANNUAL_REPORT = "ANNUAL_REPORT"
    CAREERS = "CAREERS"
    NEWS = "NEWS"
    JOBS = "JOBS"
    EVENT = "EVENT"
    PARTNER = "PARTNER"
    OTHER = "OTHER"


class ClaimType(str, enum.Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    RECOMMENDATION = "RECOMMENDATION"


class ClaimStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class SignalStrength(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVIEW = "REVIEW"
    DISMISSED = "DISMISSED"


class BriefType(str, enum.Enum):
    DETAILED = "DETAILED"
    SALES = "SALES"


class BriefStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class WorkflowStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class SignalType(str, enum.Enum):
    TECHNOLOGY = "TECHNOLOGY"
    HIRING = "HIRING"
    PARTNERSHIP = "PARTNERSHIP"
    INVESTMENT = "INVESTMENT"
    TRANSFORMATION = "TRANSFORMATION"
    ACQUISITION = "ACQUISITION"
    LEADERSHIP = "LEADERSHIP"
    EXPANSION = "EXPANSION"
    PRODUCT = "PRODUCT"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(250), unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120), index=True)
    market: Mapped[str | None] = mapped_column(String(120), index=True)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), default=Tier.OTHER, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    priority_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    priority_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ICPProfile(Base):
    __tablename__ = "icp_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(120), index=True)
    market: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    base_weight: Mapped[float] = mapped_column(Numeric(5, 2), default=1)
    criteria: Mapped[dict] = mapped_column(JSONType, default=dict)
    active: Mapped[bool] = mapped_column(default=True)


class AccountScore(Base):
    __tablename__ = "account_scores"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    industry_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    market_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    strategic_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    signal_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    technology_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    total_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), default=Tier.OTHER)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(250))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trust_level: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint("account_id", "url", name="uq_source_account_url"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(16), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[ClaimType] = mapped_column(Enum(ClaimType))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.DRAFT, index=True)
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(200))
    support_strength: Mapped[SignalStrength] = mapped_column(Enum(SignalStrength), default=SignalStrength.MEDIUM)
    quoted_text: Mapped[str | None] = mapped_column(Text)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    strength: Mapped[SignalStrength] = mapped_column(Enum(SignalStrength), default=SignalStrength.LOW)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.ACTIVE)


class SignalEvidence(Base):
    __tablename__ = "signal_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(200))
    support_strength: Mapped[SignalStrength] = mapped_column(Enum(SignalStrength), default=SignalStrength.MEDIUM)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    opportunity_area: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    recommended_conversation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.REVIEW)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"), nullable=True)


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    brief_type: Mapped[BriefType] = mapped_column(Enum(BriefType))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[BriefStatus] = mapped_column(Enum(BriefStatus), default=BriefStatus.DRAFT, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.IN_PROGRESS)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchRequest(Base):
    __tablename__ = "research_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_type: Mapped[str] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.QUEUED, index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_requests.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.QUEUED, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    run_type: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.IN_PROGRESS)
    summary: Mapped[str | None] = mapped_column(Text)


class DetectedChange(Base):
    __tablename__ = "detected_changes"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    change_type: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[SignalStrength] = mapped_column(Enum(SignalStrength), default=SignalStrength.LOW)
    evidence_ids: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HubSpotAccount(Base):
    __tablename__ = "hubspot_accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    hubspot_company_id: Mapped[str] = mapped_column(String(120), unique=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HubSpotActivity(Base):
    __tablename__ = "hubspot_activity"
    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(120))
    activity_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict)
