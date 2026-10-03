"""Shared adapter contract and normalized transfer objects."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawArtifact:
    content: bytes
    canonical_url: str
    source_item_id: str
    content_type: str = "application/octet-stream"
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class ParsedDocument:
    records: list[dict[str, Any]]
    evidence: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SourceAdapter(ABC):
    source_code: str

    def discover(self):
        return []

    def fetch(self, item):
        raise NotImplementedError("fetch is provided by the governed HTTP/file collector")

    @abstractmethod
    def parse(self, raw: RawArtifact) -> ParsedDocument:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, parsed: ParsedDocument):
        raise NotImplementedError

    @abstractmethod
    def extract_rules(self, parsed: ParsedDocument):
        raise NotImplementedError

    def extract_evidence(self, parsed: ParsedDocument):
        return parsed.evidence

    @abstractmethod
    def validate(self, record) -> ValidationResult:
        raise NotImplementedError
