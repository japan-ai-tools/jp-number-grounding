"""JP Number Grounding: check that numbers, amounts, dates and times in an AI-written Japanese summary appear in its source."""
from .ground import check, extract, normalize, parse_number

__version__ = "0.1.0"
__all__ = ["check", "extract", "normalize", "parse_number", "__version__"]
