"""NameMachine Verification Engine v2.

This package is introduced incrementally so the legacy availability API can keep
serving production while providers move to evidence-based verification.
"""

from .diagnostics import provider_diagnostics
from .models import Evidence, VerificationVerdict

__all__ = ["Evidence", "VerificationVerdict", "provider_diagnostics"]
