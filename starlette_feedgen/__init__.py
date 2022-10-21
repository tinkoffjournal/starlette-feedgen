"""
Asynchronous RSS/Atom feeds generation for Starlette,
adapted from Django syndication feed framework
"""

from .feed import FeedEndpoint

__all__ = ('FeedEndpoint',)
__version__ = '0.1.4'
