"""Errores de dominio comunes. Los adaptadores traducen sus excepciones técnicas a estas."""

from __future__ import annotations


class DomainError(Exception):
    """Base de los errores de negocio de la flota."""


class InvalidMessageError(DomainError):
    """Mensaje mal formado: reintentarlo no sirve (→ DROP / 4xx)."""


class TransientDependencyError(DomainError):
    """Una dependencia (gateway, sidecar, broker) falló de forma transitoria (→ RETRY / 503)."""


class PublishRejectedError(TransientDependencyError):
    """El broker rechazó la publicación (p. ej. stream lleno con `discard=new`)."""
