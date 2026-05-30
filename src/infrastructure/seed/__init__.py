"""Seeder programático (SPEC-006 / ADR-0008).

Substitui o `db/seed.sql` aplicado no init do Postgres. Gera, por persona do
registry, dados determinísticos e realistas via SQLAlchemy, com upsert idempotente.
"""

from src.infrastructure.seed.seeder import SeedReport, seed_personas

__all__ = ["SeedReport", "seed_personas"]
