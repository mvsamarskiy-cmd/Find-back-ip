"""Optional no-key verification providers.

Providers in this package must fail closed: if a dependency, endpoint, or response
cannot be trusted, they return UNKNOWN evidence rather than invent availability.
"""
