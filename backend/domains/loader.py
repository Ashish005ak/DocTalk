from __future__ import annotations

import logging
from typing import Any

from backend.domains.models import DomainProfile

logger = logging.getLogger(__name__)


class DomainLoader:
    """Registry of domain profiles (built-in + runtime-registered)."""

    def __init__(self) -> None:
        self._profiles: dict[str, DomainProfile] = {}
        self._load_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_profile(self, domain_id: str) -> DomainProfile:
        """Return a profile by ID. Raises ``KeyError`` if not found."""
        profile = self._profiles.get(domain_id)
        if profile is None:
            raise KeyError(f"Domain profile '{domain_id}' not found. Available: {self.available_ids()}")
        return profile

    def list_profiles(self) -> list[DomainProfile]:
        """Return all registered profiles."""
        return list(self._profiles.values())

    def available_ids(self) -> list[str]:
        return list(self._profiles.keys())

    def register(self, profile: DomainProfile) -> None:
        """Register (or override) a profile at runtime."""
        self._profiles[profile.id] = profile
        logger.info("Registered domain profile: %s", profile.id)

    def load_custom(self, path: str) -> DomainProfile:
        """Load a custom profile from a JSON file and register it."""
        from backend.domains.custom import load_custom_profile

        logger.info("Loading custom domain profile from: %s", path)
        profile = load_custom_profile(path)
        self.register(profile)
        return profile

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_builtins(self) -> None:
        """Import and register the five built-in domain profiles."""
        from backend.domains.medical import PROFILE as medical
        from backend.domains.legal import PROFILE as legal
        from backend.domains.hr import PROFILE as hr
        from backend.domains.journalism import PROFILE as journalism
        from backend.domains.ux_research import PROFILE as ux_research
        from backend.domains.custom import get_generic_profile

        for profile in (medical, legal, hr, journalism, ux_research, get_generic_profile()):
            self._profiles[profile.id] = profile

        logger.info("Loaded %d built-in domain profile(s)", len(self._profiles))
