"""TraceAtlas: company intelligence backed by evidence."""
from .core import run_batch
from .registry import research
from .models import VERSION as __version__
__all__ = ['run_batch', 'research', '__version__']
