"""Genesis schema: relational identities, versioned JSON domain snapshots.

Snapshot internals can become normalized tables through future explicit migrations.
No provider-specific fields are required by this schema.
"""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ClassifierRow(Base):
    __tablename__ = "classifiers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class OntologyRow(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (UniqueConstraint("classifier_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ObservationRow(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "classification_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"))
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class UnknownRow(Base):
    __tablename__ = "unknown_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("classification_runs.id"), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventRow(Base):
    __tablename__ = "ontology_events"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
