"""Built-in schema lint rules."""

from strawberry.schema_registry.rules.federation_key_required import (
    FederationKeyRequiredOnEntities,
)

__all__ = [
    "FederationKeyRequiredOnEntities",
]
