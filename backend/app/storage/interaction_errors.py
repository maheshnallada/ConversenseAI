class InteractionNotFound(Exception):
    def __init__(self, tenant_id: str, interaction_id: str) -> None:
        super().__init__(f"Interaction {interaction_id!r} not found for tenant")
        self.tenant_id = tenant_id
        self.interaction_id = interaction_id
