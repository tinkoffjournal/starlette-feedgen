import datetime
from collections.abc import Iterable
from typing import Any

from aiofiles.threadpool.text import AsyncTextIOWrapper

from .utils import (
    SimplerXMLGenerator,
    get_tag_uri,
    iri_to_uri,
    rfc2822_date,
    rfc3339_date,
    to_str,
)

utc = datetime.timezone.utc


class SyndicationFeed:
    """
    Base class for all syndication feeds. Subclasses should provide write().
    """

    content_type: str

    def __init__(
        self,
        title: str,
        link: str,
        description: str,
        language: str | None = None,
        author_email: str | None = None,
        author_name: str | None = None,
        author_link: str | None = None,
        subtitle: str | None = None,
        categories: Iterable | None = None,
        feed_url: str | None = None,
        feed_copyright: str | None = None,
        feed_guid: str | None = None,
        ttl: int | None = None,
        use_cached_items: bool | None = False,
        **kwargs: Any,
    ):
        self.feed: dict = {
            'title': to_str(title),
            'link': iri_to_uri(link),
            'description': to_str(description),
            'language': to_str(language),
            'author_email': to_str(author_email),
            'author_name': to_str(author_name),
            'author_link': iri_to_uri(author_link),
            'subtitle': to_str(subtitle),
            'categories': [str(c) for c in categories or []],
            'feed_url': iri_to_uri(feed_url),
            'feed_copyright': to_str(feed_copyright),
            'id': feed_guid or link,
            'ttl': to_str(ttl),
            **kwargs,
        }
        self.items: list = []
        self.use_cached_items = use_cached_items
        self.cached_items: list[str] = []

    def add_item(
        self,
        title: str,
        link: str,
        description: str,
        author_email: str | None = None,
        author_name: str | None = None,
        author_link: str | None = None,
        pubdate: datetime.datetime | None = None,
        comments: Any = None,
        unique_id: str | None = None,
        unique_id_is_permalink: bool | None = None,
        categories: Iterable | None = None,
        item_copyright: str | None = None,
        ttl: int | None = None,
        updateddate: datetime.datetime | None = None,
        enclosures: list | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Add an item to the feed. All args are expected to be strings except
        pubdate and updateddate, which are datetime.datetime objects, and
        enclosures, which is an iterable of instances of the Enclosure class.
        """
        self.items.append(
            {
                'title': to_str(title),
                'link': iri_to_uri(link),
                'description': to_str(description),
                'author_email': to_str(author_email),
                'author_name': to_str(author_name),
                'author_link': iri_to_uri(author_link),
                'pubdate': pubdate,
                'updateddate': updateddate,
                'comments': to_str(comments),
                'unique_id': to_str(unique_id),
                'unique_id_is_permalink': unique_id_is_permalink,
                'enclosures': enclosures or (),
                'categories': [str(c) for c in categories or []],
                'item_copyright': to_str(item_copyright),
                'ttl': to_str(ttl),
                **kwargs,
            }
        )

    def add_cached_items(self, cached_items: list[str]) -> None:
        """
        Add cached items to the feed.
        Cached items are supposed to be already rendered
        and therefore expected to be strings.
        """
        self.cached_items.extend(cached_items)

    def num_items(self) -> int:
        """
        Return the number of the items.
        """
        return len(self.items)

    def root_attributes(self) -> dict:
        """
        Return extra attributes to place on the root (i.e. feed/channel) element.
        Called from write().
        """
        return {}

    async def add_root_elements(self, handler: SimplerXMLGenerator) -> None:
        """
        Add elements in the root (i.e. feed/channel) element. Called
        from write().
        """
        pass

    def item_attributes(self, item: Any) -> dict:
        """
        Return extra attributes to place on each item (i.e. item/entry) element.
        """
        return {}

    async def add_item_elements(self, handler: SimplerXMLGenerator, item: Any) -> None:
        """
        Add elements on each item (i.e. item/entry) element.
        """
        pass

    async def write(self, outfile: AsyncTextIOWrapper, encoding: str) -> None:
        """
        Output the feed in the given encoding to outfile, which is a file-like
        object. Subclasses should override this.
        """
        raise NotImplementedError(
            'subclasses of SyndicationFeed must provide a write() method'
        )

    def latest_post_date(self) -> datetime.datetime:
        """
        Return the latest item's pubdate or updateddate. If no items
        have either of these attributes this return the current UTC date/time.
        """
        latest_date = None
        date_keys = ('updateddate', 'pubdate')

        for item in self.items:
            for date_key in date_keys:
                item_date = item.get(date_key)
                if item_date:  # noqa: SIM102
                    # right operand of "or" can be reached (mypy)
                    if latest_date is None or item_date > latest_date:  # type: ignore
                        latest_date = item_date
        # datetime.now(tz=utc) is slower, as documented in django.utils.timezone.now
        return latest_date or datetime.datetime.utcnow().replace(tzinfo=utc)


class Enclosure:
    """An RSS enclosure"""

    def __init__(self, url: str, length: str, mime_type: str):
        """All args are expected to be strings"""
        self.length, self.mime_type = length, mime_type
        self.url = iri_to_uri(url)


class RssFeed(SyndicationFeed):
    """
    RSS syndication feed. Base class for all RSS specifications.
    """

    _version = ''
    content_type = 'application/rss+xml; charset=utf-8'

    async def write(self, outfile: AsyncTextIOWrapper, encoding: str = 'utf-8') -> None:
        """
        Output the feed in the given encoding to outfile, which is a file-like object.
        """
        handler = SimplerXMLGenerator(outfile, encoding)
        await handler.startDocument()
        await handler.startElement('rss', self.rss_attributes())
        await handler.startElement('channel', self.root_attributes())
        await self.add_root_elements(handler)
        await self.write_items(handler)
        await self.endChannelElement(handler)
        await handler.endElement('rss')

    def rss_attributes(self) -> dict:
        """
        Return attributes to place on the top level <rss> element.
        """
        return {'version': self._version, 'xmlns:atom': 'http://www.w3.org/2005/Atom'}

    async def write_items(self, handler: SimplerXMLGenerator) -> None:
        """
        Output each item to outfile as <item> element. Called from write().
        """
        for item in self.items:
            await handler.startElement('item', self.item_attributes(item))
            await self.add_item_elements(handler, item)
            await handler.endElement('item')

    async def add_root_elements(self, handler: SimplerXMLGenerator) -> None:
        """
        Add elements to the root <channel> element. Called from write().
        """
        await handler.addQuickElement('title', self.feed['title'])
        await handler.addQuickElement('link', self.feed['link'])
        await handler.addQuickElement('description', self.feed['description'])
        if self.feed['feed_url'] is not None:
            await handler.addQuickElement(
                'atom:link', None, {'rel': 'self', 'href': self.feed['feed_url']}
            )
        if self.feed['language'] is not None:
            await handler.addQuickElement('language', self.feed['language'])
        for cat in self.feed['categories']:
            await handler.addQuickElement('category', cat)
        if self.feed['feed_copyright'] is not None:
            await handler.addQuickElement('copyright', self.feed['feed_copyright'])
        await handler.addQuickElement(
            'lastBuildDate', rfc2822_date(self.latest_post_date())
        )
        if self.feed['ttl'] is not None:
            await handler.addQuickElement('ttl', self.feed['ttl'])

    async def endChannelElement(self, handler: SimplerXMLGenerator) -> None:
        """
        End <channel> element.
        """
        await handler.endElement('channel')


class RssUserland091Feed(RssFeed):
    """
    RSS 0.91 specification of RSS syndication feed.
    """

    _version = '0.91'

    async def add_item_elements(self, handler: SimplerXMLGenerator, item: Any) -> None:
        """
        Add elements on each <item> element.
        """
        await handler.addQuickElement('title', item['title'])
        await handler.addQuickElement('link', item['link'])
        if item['description'] is not None:
            await handler.addQuickElement('description', item['description'])


class Rss201rev2Feed(RssFeed):
    """
    Rss 2.0 specification of RSS syndication feed.
    """

    # Spec: https://cyber.harvard.edu/rss/rss.html
    _version = '2.0'

    async def add_item_elements(self, handler: SimplerXMLGenerator, item: Any) -> None:
        """
        Add elements on each <item> element.
        """
        await handler.addQuickElement('title', item['title'])
        await handler.addQuickElement('link', item['link'])
        if item['description'] is not None:
            await handler.addQuickElement('description', item['description'])

        # Author information.
        if item['author_name'] and item['author_email']:
            await handler.addQuickElement(
                'author', '{} ({})'.format(item['author_email'], item['author_name'])
            )
        elif item['author_email']:
            await handler.addQuickElement('author', item['author_email'])
        elif item['author_name']:
            await handler.addQuickElement(
                'dc:creator',
                item['author_name'],
                {'xmlns:dc': 'http://purl.org/dc/elements/1.1/'},
            )

        if item['pubdate'] is not None:
            await handler.addQuickElement('pubDate', rfc2822_date(item['pubdate']))
        if item['comments'] is not None:
            await handler.addQuickElement('comments', item['comments'])
        if item['unique_id'] is not None:
            guid_attrs = {}
            if isinstance(item.get('unique_id_is_permalink'), bool):
                guid_attrs['isPermaLink'] = str(item['unique_id_is_permalink']).lower()
            await handler.addQuickElement('guid', item['unique_id'], guid_attrs)
        if item['ttl'] is not None:
            await handler.addQuickElement('ttl', item['ttl'])

        # Enclosure.
        if item['enclosures']:
            enclosures = list(item['enclosures'])
            if len(enclosures) > 1:
                raise ValueError(
                    'RSS feed items may only have one enclosure, see '
                    'http://www.rssboard.org/rss-profile#element-channel-item-enclosure'
                )
            enclosure = enclosures[0]
            await handler.addQuickElement(
                'enclosure',
                '',
                {
                    'url': enclosure.url,
                    'length': enclosure.length,
                    'type': enclosure.mime_type,
                },
            )

        # Categories.
        for cat in item['categories']:
            await handler.addQuickElement('category', cat)


class Atom1Feed(SyndicationFeed):
    """
    The Atom Syndication Format of feeds.
    """

    # Spec: https://tools.ietf.org/html/rfc4287
    content_type = 'application/atom+xml; charset=utf-8'
    ns = 'http://www.w3.org/2005/Atom'

    async def write(self, outfile: AsyncTextIOWrapper, encoding: str) -> None:
        """
        Output the feed in the given encoding to outfile, which is a file-like object.
        """
        handler = SimplerXMLGenerator(outfile, encoding)
        await handler.startDocument()
        await handler.startElement('feed', self.root_attributes())
        await self.add_root_elements(handler)
        await self.write_items(handler)
        await handler.endElement('feed')

    def root_attributes(self) -> dict:
        """
        Add elements to the root <feed> element. Called from write().
        """
        if self.feed['language'] is not None:
            return {'xmlns': self.ns, 'xml:lang': self.feed['language']}
        else:
            return {'xmlns': self.ns}

    async def add_root_elements(self, handler: SimplerXMLGenerator) -> None:
        """
        Add elements to the root <feed> element. Called from write().
        """
        await handler.addQuickElement('title', self.feed['title'])
        await handler.addQuickElement(
            'link', '', {'rel': 'alternate', 'href': self.feed['link']}
        )
        if self.feed['feed_url'] is not None:
            await handler.addQuickElement(
                'link', '', {'rel': 'self', 'href': self.feed['feed_url']}
            )
        await handler.addQuickElement('id', self.feed['id'])
        await handler.addQuickElement('updated', rfc3339_date(self.latest_post_date()))
        if self.feed['author_name'] is not None:
            await handler.startElement('author', {})
            await handler.addQuickElement('name', self.feed['author_name'])
            if self.feed['author_email'] is not None:
                await handler.addQuickElement('email', self.feed['author_email'])
            if self.feed['author_link'] is not None:
                await handler.addQuickElement('uri', self.feed['author_link'])
            await handler.endElement('author')
        if self.feed['subtitle'] is not None:
            await handler.addQuickElement('subtitle', self.feed['subtitle'])
        for cat in self.feed['categories']:
            await handler.addQuickElement('category', '', {'term': cat})
        if self.feed['feed_copyright'] is not None:
            await handler.addQuickElement('rights', self.feed['feed_copyright'])

    async def write_items(self, handler: SimplerXMLGenerator) -> None:
        """
        Output each item to outfile as <entry> element. Called from write().
        """
        for item in self.items:
            await handler.startElement('entry', self.item_attributes(item))
            await self.add_item_elements(handler, item)
            await handler.endElement('entry')

    async def add_item_elements(self, handler: SimplerXMLGenerator, item: Any) -> None:
        """
        Add elements on each <entry> element.
        """
        await handler.addQuickElement('title', item['title'])
        await handler.addQuickElement(
            'link', '', {'href': item['link'], 'rel': 'alternate'}
        )

        if item['pubdate'] is not None:
            await handler.addQuickElement('published', rfc3339_date(item['pubdate']))

        if item['updateddate'] is not None:
            await handler.addQuickElement('updated', rfc3339_date(item['updateddate']))

        # Author information.
        if item['author_name'] is not None:
            await handler.startElement('author', {})
            await handler.addQuickElement('name', item['author_name'])
            if item['author_email'] is not None:
                await handler.addQuickElement('email', item['author_email'])
            if item['author_link'] is not None:
                await handler.addQuickElement('uri', item['author_link'])
            await handler.endElement('author')

        # Unique ID.
        if item['unique_id'] is not None:
            unique_id = item['unique_id']
        else:
            unique_id = get_tag_uri(item['link'], item['pubdate'])
        await handler.addQuickElement('id', unique_id)

        # Summary.
        if item['description'] is not None:
            await handler.addQuickElement(
                'summary', item['description'], {'type': 'html'}
            )

        # Enclosures.
        for enclosure in item['enclosures']:
            await handler.addQuickElement(
                'link',
                '',
                {
                    'rel': 'enclosure',
                    'href': enclosure.url,
                    'length': enclosure.length,
                    'type': enclosure.mime_type,
                },
            )

        # Categories.
        for cat in item['categories']:
            await handler.addQuickElement('category', '', {'term': cat})

        # Rights.
        if item['item_copyright'] is not None:
            await handler.addQuickElement('rights', item['item_copyright'])


# This isolates the decision of what the system default is, so calling code can
# do "generator.DefaultFeed" instead of "generator.Rss201rev2Feed".
DefaultFeed = Rss201rev2Feed
