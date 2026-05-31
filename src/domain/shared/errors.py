"""Erros de dominio. A borda HTTP os traduz em status codes."""

from __future__ import annotations


class DomainError(Exception):
    """Base para violacoes de regra/invariante de dominio."""


class InvariantError(DomainError):
    """Valor invalido na construcao de um value object/entidade (-> 422)."""


class NotFoundError(DomainError):
    """Recurso de dominio inexistente (-> 404)."""


class ConflictError(DomainError):
    """Conflito de estado, ex.: violacao de unicidade (-> 409)."""
