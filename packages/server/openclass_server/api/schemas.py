from typing import Any

from openclass_core.models import Model, Observation, OntologyClass, OntologyVersion
from pydantic import Field, model_validator


class CreateClassifier(Model):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    classes: tuple[OntologyClass, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_ontology(self) -> "CreateClassifier":
        from uuid import uuid4

        OntologyVersion(
            classifier_id=uuid4(), version_number=1, classes=self.classes, created_by="local"
        )
        return self


class ClassifyRequest(Model):
    observation: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_observation(self) -> "ClassifyRequest":
        Observation(content=self.observation, metadata=self.metadata)
        return self
