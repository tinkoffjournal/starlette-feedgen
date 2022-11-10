from abc import ABC, abstractmethod
from asyncio.coroutines import iscoroutinefunction
from calendar import timegm
from collections.abc import AsyncGenerator, AsyncIterable, Iterable
from html import escape
from http import HTTPStatus
from typing import Any

import aiofiles
from starlette.endpoints import HTTPEndpoint
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import StreamingResponse

from .generator import DefaultFeed, Enclosure, SyndicationFeed
from .utils import add_domain, http_date


class FeedEndpoint(HTTPEndpoint, ABC):
    """
    Base endpoint class for feeds.
    Provides methods for filling feed generators with data.
    """

    feed_type: type[SyndicationFeed] = DefaultFeed
    language: str | None = None
    domain: str | None = None
    link: str = '/'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # default attributes for using cached items
        self.use_cached_items: bool = False
        self.cached_items: list = []

    @abstractmethod
    async def get_items(self) -> Iterable | AsyncIterable:
        """
        Return items the feed will be populated with.
        """
        ...

    async def get(self, request: Request) -> StreamingResponse:
        """
        Populate and return the feed.
        This method is the entry point for the route associated with the class.
        """
        try:
            obj = await self.get_object(request)
        except FeedDoesNotExist:
            raise HTTPException(
                int(HTTPStatus.NOT_FOUND), detail='Feed object does not exist'
            )
        headers = {}
        feed_generator = await self.get_feed(obj, request)
        if hasattr(self, 'item_pubdate') or hasattr(self, 'item_updateddate'):
            headers['Last-Modified'] = http_date(
                timegm(feed_generator.latest_post_date().utctimetuple())
            )

        async def iter_feed() -> AsyncGenerator[str, None]:
            """
            Feed async generator to be passed to StreamingResponse.
            """
            encoding = 'utf-8'
            async with aiofiles.tempfile.TemporaryFile(
                'w+', newline='\n', encoding=encoding
            ) as feed:
                await feed_generator.write(feed, encoding=encoding)
                await feed.seek(0)
                async for chunk in feed:
                    yield chunk

        return StreamingResponse(
            iter_feed(), media_type=feed_generator.content_type, headers=headers
        )

    async def get_object(self, request: Request, *args: Any, **kwargs: Any) -> Any:
        """
        Return a feed object.
        """
        ...

    def item_link(self, item: Any) -> str:
        """
        Return an item link.
        """
        return getattr(item, 'link', self.link)

    def item_title(self, item: Any) -> str:
        """
        Return an item title.
        """
        # Titles should be double escaped by default
        return getattr(item, 'title', None) or escape(str(item))

    def item_description(self, item: Any) -> str:
        """
        Return an item description.
        """
        return getattr(item, 'description', None) or str(item)

    async def item_enclosures(self, item: Any) -> Iterable[Enclosure]:
        """
        Return item's enclosure element that associates a media object
        such as an audio or video file with the item.
        """
        enc_url = await self._get_dynamic_attr('item_enclosure_url', item)
        if not enc_url:
            return []
        length: str = await self._get_dynamic_attr('item_enclosure_length', item)
        mime_type: str = await self._get_dynamic_attr('item_enclosure_mime_type', item)
        enc = Enclosure(url=str(enc_url), length=length, mime_type=mime_type)
        return [enc]

    async def _get_dynamic_attr(
        self, attname: str, obj: Any, default: Any = None
    ) -> Any:
        """
        Return a value of dynamic class attribute.
        It can be eiter regular attribute, method or coroutine.
        Method will be called, coroutine will be awaited.
        """
        attr = getattr(self, attname, default)
        if not callable(attr):
            return attr
        # Check co_argcount rather than try/excepting the function and
        # catching the TypeError, because something inside the function
        # may raise the TypeError. This technique is more accurate.
        try:
            code = attr.__code__
        except AttributeError:
            code = attr.__call__.__code__
        args: tuple = ()
        if code.co_argcount == 2:  # one argument is 'self'
            args = (obj,)

        if iscoroutinefunction(attr):
            result = await attr(*args)
        else:
            result = attr(*args)
        return result

    async def feed_extra_kwargs(self, obj: Any) -> dict[str, Any]:
        """
        Return an extra keyword arguments dictionary that is used when
        initializing the feed generator.
        """
        return {}

    async def item_extra_kwargs(self, item: Any) -> dict[str, Any]:
        """
        Return an extra keyword arguments dictionary that is used with
        the `add_item` call of the feed generator.
        """
        return {}

    async def get_feed(self, obj: Any, request: Request) -> SyndicationFeed:
        """
        Return a SyndicationFeed object, fully populated, for
        this feed. Raise FeedDoesNotExist for invalid parameters.
        """
        link = await self._get_dynamic_attr('link', obj)
        request_is_secure = request.url.is_secure
        link = add_domain(self.domain, link, request_is_secure)

        feed_url = await self._get_dynamic_attr('feed_url', obj)
        feed_extra_kwargs = await self.feed_extra_kwargs(obj)

        feed = self.feed_type(
            title=await self._get_dynamic_attr('title', obj),
            subtitle=await self._get_dynamic_attr('subtitle', obj),
            link=link,
            description=await self._get_dynamic_attr('description', obj),
            language=self.language,
            feed_url=add_domain(
                self.domain, feed_url or request.url.path, request_is_secure
            ),
            author_name=await self._get_dynamic_attr('author_name', obj),
            author_link=await self._get_dynamic_attr('author_link', obj),
            author_email=await self._get_dynamic_attr('author_email', obj),
            categories=await self._get_dynamic_attr('categories', obj),
            feed_copyright=await self._get_dynamic_attr('feed_copyright', obj),
            feed_guid=await self._get_dynamic_attr('feed_guid', obj),
            ttl=await self._get_dynamic_attr('ttl', obj),
            use_cached_items=self.use_cached_items,
            **feed_extra_kwargs,
        )

        if not self.use_cached_items:  # build the feed on the fly (default)
            items = await self.get_items()
            if isinstance(items, AsyncIterable):
                async for item in items:
                    await self._populate_feed(feed, item, request_is_secure)
            else:
                for item in items:
                    await self._populate_feed(feed, item, request_is_secure)
        else:  # add already rendered item feeds
            feed.add_cached_items(self.cached_items)
        return feed

    async def _populate_feed(
        self, feed: SyndicationFeed, item: Any, request_is_secure: bool = True
    ) -> None:
        """
        Populate a SyndicationFeed object with the item.
        """
        title = await self._get_dynamic_attr('item_title', item)
        description = await self._get_dynamic_attr('item_description', item)
        link = add_domain(
            self.domain,
            await self._get_dynamic_attr('item_link', item),
            request_is_secure,
        )
        enclosures = await self._get_dynamic_attr('item_enclosures', item)
        author_name = await self._get_dynamic_attr('item_author_name', item)
        if author_name is not None:
            author_email = await self._get_dynamic_attr('item_author_email', item)
            author_link = await self._get_dynamic_attr('item_author_link', item)
        else:
            author_email = author_link = None

        pubdate = await self._get_dynamic_attr('item_pubdate', item)
        updateddate = await self._get_dynamic_attr('item_updateddate', item)
        extra_kwargs = await self.item_extra_kwargs(item)
        feed.add_item(
            title=title,
            link=link,
            description=description,
            unique_id=await self._get_dynamic_attr('item_guid', item, link),
            unique_id_is_permalink=await self._get_dynamic_attr(
                'item_guid_is_permalink', item
            ),
            enclosures=enclosures,
            pubdate=pubdate,
            updateddate=updateddate,
            author_name=author_name,
            author_email=author_email,
            author_link=author_link,
            categories=await self._get_dynamic_attr('item_categories', item),
            item_copyright=await self._get_dynamic_attr('item_copyright', item),
            **extra_kwargs,
        )


class FeedDoesNotExist(Exception):
    ...
