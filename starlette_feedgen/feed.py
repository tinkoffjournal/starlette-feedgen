from abc import ABC, abstractmethod
from calendar import timegm
from html import escape
from http import HTTPStatus
from io import BytesIO
from typing import Any, AsyncIterable, Dict, Iterable, Optional, Type

from starlette.endpoints import HTTPEndpoint
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import StreamingResponse

from .generator import DefaultFeed, Enclosure, SyndicationFeed
from .utils import add_domain, http_date, run_async_or_thread


class FeedEndpoint(HTTPEndpoint, ABC):
    feed_type: Type[SyndicationFeed] = DefaultFeed
    language: Optional[str] = None
    domain: Optional[str] = None
    link: str = "/"

    @abstractmethod
    def get_items(self) -> Iterable:
        ...

    async def get(self, request: Request) -> StreamingResponse:
        try:
            obj = await self.get_object(request)
        except FeedDoesNotExist:
            raise HTTPException(int(HTTPStatus.NOT_FOUND), detail="Feed object does not exist")
        headers = {}
        feed_generator = await self.get_feed(obj, request)
        if hasattr(self, "item_pubdate") or hasattr(self, "item_updateddate"):
            headers["Last-Modified"] = http_date(
                timegm(feed_generator.latest_post_date().utctimetuple())
            )
        feed = BytesIO()
        feed_generator.write(feed, encoding="utf-8")
        feed.seek(0)
        return StreamingResponse(feed, media_type=feed_generator.content_type, headers=headers)

    async def get_object(self, request: Request, *args: Any, **kwargs: Any) -> Any:
        ...

    def item_link(self, item: Any) -> str:
        return getattr(item, "link", self.link)

    def item_title(self, item: Any) -> str:
        # Titles should be double escaped by default
        return getattr(item, "title", None) or escape(str(item))

    def item_description(self, item: Any) -> str:
        return getattr(item, "description", None) or str(item)

    def item_enclosures(self, item: Any) -> Iterable[Enclosure]:
        enc_url = self._get_dynamic_attr("item_enclosure_url", item)
        if not enc_url:
            return []
        enc = Enclosure(
            url=str(enc_url),
            length=str(self._get_dynamic_attr("item_enclosure_length", item)),
            mime_type=str(self._get_dynamic_attr("item_enclosure_mime_type", item)),
        )
        return [enc]

    def _get_dynamic_attr(self, attname: str, obj: Any, default: Any = None) -> Any:
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
        args = ()
        if code.co_argcount == 2:  # one argument is 'self'
            args = (obj,)
        return attr(*args)

    def feed_extra_kwargs(self, obj: Any) -> Dict[str, Any]:
        """
        Return an extra keyword arguments dictionary that is used when
        initializing the feed generator.
        """
        return {}

    def item_extra_kwargs(self, item: Any) -> Dict[str, Any]:
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
        link = self._get_dynamic_attr("link", obj)
        request_is_secure = request.url.is_secure
        link = add_domain(self.domain, link, request_is_secure)

        feed = self.feed_type(
            title=self._get_dynamic_attr("title", obj),
            subtitle=self._get_dynamic_attr("subtitle", obj),
            link=link,
            description=self._get_dynamic_attr("description", obj),
            language=self.language,
            feed_url=add_domain(
                self.domain,
                self._get_dynamic_attr("feed_url", obj) or request.url.path,
                request_is_secure,
            ),
            author_name=self._get_dynamic_attr("author_name", obj),
            author_link=self._get_dynamic_attr("author_link", obj),
            author_email=self._get_dynamic_attr("author_email", obj),
            categories=self._get_dynamic_attr("categories", obj),
            feed_copyright=self._get_dynamic_attr("feed_copyright", obj),
            feed_guid=self._get_dynamic_attr("feed_guid", obj),
            ttl=self._get_dynamic_attr("ttl", obj),
            **self.feed_extra_kwargs(obj),
        )

        items = await run_async_or_thread(self.get_items)
        await self._process_items(feed, items, request_is_secure)
        return feed

    async def _process_items(
        self, feed: SyndicationFeed, items: Iterable[Any], request_is_secure: bool
    ) -> None:
        if isinstance(items, AsyncIterable):
            async for item in items:
                await self._populate_feed(feed, item, request_is_secure)
        else:
            for item in items:
                await self._populate_feed(feed, item, request_is_secure)

    async def _populate_feed(
        self, feed: SyndicationFeed, item: Any, request_is_secure: bool = True
    ) -> None:
        title = self._get_dynamic_attr("item_title", item)
        description = self._get_dynamic_attr("item_description", item)
        link = add_domain(
            self.domain, self._get_dynamic_attr("item_link", item), request_is_secure,
        )
        enclosures = self._get_dynamic_attr("item_enclosures", item)
        author_name = self._get_dynamic_attr("item_author_name", item)
        if author_name is not None:
            author_email = self._get_dynamic_attr("item_author_email", item)
            author_link = self._get_dynamic_attr("item_author_link", item)
        else:
            author_email = author_link = None

        pubdate = self._get_dynamic_attr("item_pubdate", item)
        updateddate = self._get_dynamic_attr("item_updateddate", item)
        extra_kwargs = await run_async_or_thread(self.item_extra_kwargs, item)
        feed.add_item(
            title=title,
            link=link,
            description=description,
            unique_id=self._get_dynamic_attr("item_guid", item, link),
            unique_id_is_permalink=self._get_dynamic_attr("item_guid_is_permalink", item),
            enclosures=enclosures,
            pubdate=pubdate,
            updateddate=updateddate,
            author_name=author_name,
            author_email=author_email,
            author_link=author_link,
            categories=self._get_dynamic_attr("item_categories", item),
            item_copyright=self._get_dynamic_attr("item_copyright", item),
            **extra_kwargs,
        )


class FeedDoesNotExist(Exception):
    ...
