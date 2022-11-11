import datetime
import email
import re
from email.utils import formatdate
from typing import Any
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape, quoteattr

from aiofiles.threadpool.text import AsyncTextIOWrapper


class UnserializableContentError(ValueError):
    pass


class AsyncXMLGenerator:
    """
    Asynchronous content handler.
    Allows asynchronously generating xml document using aiofiles.tempfile as an outfile.
    Adapted from xml.sax.saxutils.XMLGenerator.
    """

    def __init__(
        self,
        out: AsyncTextIOWrapper,
        encoding: str = 'iso-8859-1',
        short_empty_elements: bool = False,
    ):
        self._locator = None
        self._write = out.write
        self._flush = out.flush
        self._ns_contexts: list = [{}]  # contains uri -> prefix dicts
        self._current_context = self._ns_contexts[-1]
        self._undeclared_ns_maps: list = []
        self._encoding = encoding
        self._short_empty_elements = short_empty_elements
        self._pending_start_element = False

    async def _finish_pending_start_element(self) -> None:
        """
        Finish pending start element.
        """
        if self._pending_start_element:
            await self._write('>')
            self._pending_start_element = False

    # ContentHandler methods
    async def startDocument(self) -> None:
        """
        Start xml document.
        """
        await self._write(f'<?xml version="1.0" encoding="{self._encoding}"?>\n')

    async def endDocument(self) -> None:
        """
        Flush outfile.
        """
        await self._flush()

    async def startElement(self, name: str, attrs: dict) -> None:
        """
        Start xml element with attributes.
        """
        await self._finish_pending_start_element()
        await self._write('<' + name)
        for (name, value) in attrs.items():
            await self._write(f' {name}={quoteattr(value)}')
        if self._short_empty_elements:
            self._pending_start_element = True
        else:
            await self._write('>')

    async def endElement(self, name: str) -> None:
        """
        End xml element.
        """
        if self._pending_start_element:
            await self._write('/>')
            self._pending_start_element = False
        else:
            await self._write(f'</{name}>')

    async def characters(self, content: Any) -> None:
        """
        Escape &, <, and > in a string of content.
        """
        if content:
            await self._finish_pending_start_element()
            if isinstance(content, bytes):
                content = content.decode(self._encoding)
            await self._write(escape(content))


class SimplerXMLGenerator(AsyncXMLGenerator):
    async def addQuickElement(
        self, name: str, contents: Any = None, attrs: dict | None = None
    ) -> None:
        """
        Convenience method for adding an element with no children.
        """
        if attrs is None:
            attrs = {}
        await self.startElement(name, attrs)
        if contents is not None:
            await self.characters(contents)
        await self.endElement(name)

    async def characters(self, content: str) -> None:
        """
        Raise exception of content has control chars.
        """
        if content and re.search(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', content):
            # Fail loudly when content has control chars (unsupported in XML 1.0)
            # See http://www.w3.org/International/questions/qa-controls
            raise UnserializableContentError(
                'Control characters are not supported in XML 1.0'
            )
        await super().characters(content)


def iri_to_uri(iri: str | None) -> str | None:
    """
    Convert an Internationalized Resource Identifier (IRI) portion to a URI
    portion that is suitable for inclusion in a URL.

    This is the algorithm from section 3.1 of RFC 3987, slightly simplified
    since the input is assumed to be a string rather than an arbitrary byte
    stream.

    Take an IRI (string or UTF-8 bytes, e.g. '/I ♥ Django/' or
    b'/I \xe2\x99\xa5 Django/') and return a string containing the encoded
    result with ASCII chars only (e.g. '/I%20%E2%99%A5%20Django/').
    """
    # The list of safe characters here is constructed from the "reserved" and
    # "unreserved" characters specified in sections 2.2 and 2.3 of RFC 3986:
    #     reserved    = gen-delims / sub-delims   noqa: E800
    #     gen-delims  = ":" / "/" / "?" / "#" / "[" / "]" / "@"
    #     sub-delims  = "!" / "$" / "&" / "'" / "(" / ")"
    #                   / "*" / "+" / "," / ";" / "="
    #     unreserved  = ALPHA / DIGIT / "-" / "." / "_" / "~"   noqa: E800
    # Of the unreserved characters, urllib.parse.quote() already considers all
    # but the ~ safe.
    # The % character is also added to the list of safe characters here, as the
    # end of section 3.1 of RFC 3987 specifically mentions that % must not be
    # converted.
    if iri is None:
        return iri
    return quote(iri, safe="/#%[]=:;$&()+,!?*@'~")


def http_date(epoch_seconds: float | None = None) -> str:
    """
    Format the time to match the RFC1123 date format as specified by HTTP
    RFC7231 section 7.1.1.1.
    `epoch_seconds` is a floating point number expressed in seconds since the
    epoch, in UTC - such as that outputted by time.time(). If set to None, it
    defaults to the current time.
    Output a string in the format 'Wdy, DD Mon YYYY HH:MM:SS GMT'.
    """
    return formatdate(epoch_seconds, usegmt=True)


def rfc2822_date(date_time: datetime.datetime) -> str:
    """
    Format date and time to match the RFC2822 date format.
    """
    return email.utils.format_datetime(date_time)


def rfc3339_date(date_time: datetime.datetime) -> str:
    """
    Format date and time to match the RFC3339 date format.
    """
    return date_time.isoformat() + ('Z' if date_time.utcoffset() is None else '')


def get_tag_uri(url: str, date: datetime.datetime) -> str:
    """
    Create a TagURI.

    See:
    https://web.archive.org/web/20110514113830/http://diveintomark.org/archives/2004/05/28/howto-atom-id
    """
    bits = urlparse(url)
    d = ''
    if date is not None:
        date_str = date.strftime('%Y-%m-%d')
        d = f',{date_str}'
    return f'tag:{bits.hostname}{d}:{bits.path}/{bits.fragment}'


def add_domain(domain: str | None, url: str, secure: bool = False) -> str:
    """
    Add domain to the given url.
    """
    if not domain:
        return url
    protocol = 'https' if secure else 'http'
    if url.startswith('//'):
        # Support network-path reference - RSS requires a protocol
        url = f'{protocol}:{url}'
    elif not url.startswith(('http://', 'https://', 'mailto:')):
        url = iri_to_uri(f'{protocol}://{domain}{url}') or ''
    return url


def to_str(s: Any) -> str | None:
    """
    Convert object to string.
    """
    return str(s) if s is not None else s
