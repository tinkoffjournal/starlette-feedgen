"""
Asynchronous RSS/Atom feeds generation for Starlette,
adapted from Django syndication feed framework
"""

from .feed import FeedEndpoint, FeedDoesNotExist

__all__ = ('FeedEndpoint','FeedDoesNotExist',)
__version__ = '0.1.4'
