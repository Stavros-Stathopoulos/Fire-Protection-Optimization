"""Domain layer: core entities and problem assembly."""

from .entities import FireRegion, FireStation, IncidentDistrict
from .problem import FireProtectionProblem

__all__ = ["FireRegion", "FireStation", "IncidentDistrict", "FireProtectionProblem"]
