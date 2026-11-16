from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.envelope import ArtifactReference
from app.storage.interaction_errors import InteractionNotFound
from app.storage.orm import ArtifactReferenceRow, InteractionRow


class ArtifactReferenceConflict(Exception):
    def __init__(self, tenant_id: str, interaction_id: str, artifact_id: str) -> None:
        super().__init__(
            f"Artifact reference {artifact_id!r} was already registered with different metadata"
        )
        self.tenant_id = tenant_id
        self.interaction_id = interaction_id
        self.artifact_id = artifact_id


class ArtifactReferenceRepository:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def register(
        self,
        tenant_id: str,
        interaction_id: str,
        reference: ArtifactReference,
    ) -> bool:
        try:
            with self._session_factory.begin() as session:
                self._require_interaction(session, tenant_id, interaction_id)
                existing = self._find(
                    session, tenant_id, interaction_id, reference.artifact_id
                )
                if existing is not None:
                    if not self._matches(existing, reference):
                        raise ArtifactReferenceConflict(
                            tenant_id, interaction_id, reference.artifact_id
                        )
                    return False

                session.add(
                    ArtifactReferenceRow(
                        tenant_id=tenant_id,
                        interaction_id=interaction_id,
                        artifact_id=reference.artifact_id,
                        artifact_type=reference.artifact_type,
                        uri=reference.uri,
                        media_type=reference.media_type,
                        sha256=reference.sha256,
                        created_at=datetime.now(timezone.utc),
                    )
                )
                return True
        except IntegrityError:
            with self._session_factory() as session:
                existing = self._find(
                    session, tenant_id, interaction_id, reference.artifact_id
                )
                if existing is None:
                    raise
                if not self._matches(existing, reference):
                    raise ArtifactReferenceConflict(
                        tenant_id, interaction_id, reference.artifact_id
                    )
                return False

    @staticmethod
    def _require_interaction(
        session: Session, tenant_id: str, interaction_id: str
    ) -> None:
        exists = session.scalar(
            select(InteractionRow.id).where(
                InteractionRow.tenant_id == tenant_id,
                InteractionRow.interaction_id == interaction_id,
            )
        )
        if exists is None:
            raise InteractionNotFound(tenant_id, interaction_id)

    @staticmethod
    def _find(
        session: Session, tenant_id: str, interaction_id: str, artifact_id: str
    ) -> ArtifactReferenceRow | None:
        return session.scalar(
            select(ArtifactReferenceRow).where(
                ArtifactReferenceRow.tenant_id == tenant_id,
                ArtifactReferenceRow.interaction_id == interaction_id,
                ArtifactReferenceRow.artifact_id == artifact_id,
            )
        )

    @staticmethod
    def _matches(
        row: ArtifactReferenceRow, reference: ArtifactReference
    ) -> bool:
        return (
            row.artifact_type == reference.artifact_type
            and row.uri == reference.uri
            and row.media_type == reference.media_type
            and row.sha256 == reference.sha256
        )
