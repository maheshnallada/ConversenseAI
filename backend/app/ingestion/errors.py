class IdempotencyConflict(Exception):
    """The same interaction identity was submitted with a different payload."""

    def __init__(self, tenant_id: str, interaction_id: str) -> None:
        self.tenant_id = tenant_id
        self.interaction_id = interaction_id
        super().__init__(
            f"Interaction {tenant_id}/{interaction_id} already exists with a different payload"
        )
