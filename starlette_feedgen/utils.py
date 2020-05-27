import datetime
import email
import re
from asyncio.coroutines import iscoroutinefunction
from email.utils import formatdate
from typing import Any, Callable, Union
from urllib.parse import quote, urlparse
from xml.sax.saxutils import XMLGenerator

from starlette.concurrency import run_in_threadpool


class UnserializableContentError(ValueError):
    pass


class SimplerXMLGenerator(XMLGenerator):
    def addQuickElement(self, name: str, contents: str = None, attrs: dict = None) -> None:
        """Convenience method for adding an element with no children"""
        if attrs is None:
            attrs = {}
        self.startElement(name, attrs)
        if contents is not None:
            self.characters(contents)
        self.endElement(name)

    def characters(self, content: str) -> None:
        if content and re.search(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", content):
            # Fail loudly when content has control chars (unsupported in XML 1.0)
            # See http://www.w3.org/International/questions/qa-controls
            raise UnserializableContentError("Control characters are not supported in XML 1.0")
        XMLGenerator.characters(self, content)


def iri_to_uri(iri: str) -> str:
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
    #     reserved    = gen-delims / sub-delims
    #     gen-delims  = ":" / "/" / "?" / "#" / "[" / "]" / "@"
    #     sub-delims  = "!" / "$" / "&" / "'" / "(" / ")"
    #                   / "*" / "+" / "," / ";" / "="
    #     unreserved  = ALPHA / DIGIT / "-" / "." / "_" / "~"
    # Of the unreserved characters, urllib.parse.quote() already considers all
    # but the ~ safe.
    # The % character is also added to the list of safe characters here, as the
    # end of section 3.1 of RFC 3987 specifically mentions that % must not be
    # converted.
    if iri is None:
        return iri
    return quote(iri, safe="/#%[]=:;$&()+,!?*@'~")


def http_date(epoch_seconds: float = None) -> str:
    """
    Format the time to match the RFC1123 date format as specified by HTTP
    RFC7231 section 7.1.1.1.
    `epoch_seconds` is a floating point number expressed in seconds since the
    epoch, in UTC - such as that outputted by time.time(). If set to None, it
    defaults to the current time.
    Output a string in the format 'Wdy, DD Mon YYYY HH:MM:SS GMT'.
    """
    return formatdate(epoch_seconds, usegmt=True)


def rfc2822_date(date: Union[datetime.datetime, str]) -> str:
    if not isinstance(date, datetime.datetime):
        date = datetime.datetime.combine(date, datetime.time())
    return email.utils.format_datetime(date)


def rfc3339_date(date: Union[datetime.datetime, str]) -> str:
    if not isinstance(date, datetime.datetime):
        date = datetime.datetime.combine(date, datetime.time())
    return date.isoformat() + ("Z" if date.utcoffset() is None else "")


def get_tag_uri(url: str, date: datetime) -> str:
    """
    Create a TagURI.

    See:
    https://web.archive.org/web/20110514113830/http://diveintomark.org/archives/2004/05/28/howto-atom-id
    """
    bits = urlparse(url)
    d = ""
    if date is not None:
        date_str = date.strftime("%Y-%m-%d")
        d = f",{date_str}"
    return f"tag:{bits.hostname}{d}:{bits.path}/{bits.fragment}"


def add_domain(domain: str, url: str, secure: bool = False) -> str:
    if not domain:
        return url
    protocol = "https" if secure else "http"
    if url.startswith("//"):
        # Support network-path reference - RSS requires a protocol
        url = "%s:%s" % (protocol, url)
    elif not url.startswith(("http://", "https://", "mailto:")):
        url = iri_to_uri("%s://%s%s" % (protocol, domain, url))
    return url


async def run_async_or_thread(handler: Callable, *args: Any, **kwargs: Any) -> Any:
    if iscoroutinefunction(handler):
        return await handler(*args, **kwargs)
    return await run_in_threadpool(handler, *args, **kwargs)
