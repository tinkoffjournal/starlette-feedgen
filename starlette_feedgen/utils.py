import datetime
import email
import re
from email.utils import formatdate
from typing import Any, Callable, Union
from urllib.parse import quote, urlparse
from xml.sax.saxutils import quoteattr, escape


class UnserializableContentError(ValueError):
    pass


class AsyncXMLGenerator:
    def __init__(self, out, encoding="iso-8859-1", short_empty_elements=False):
        self._locator = None
        self._write = out.write
        self._flush = out.flush
        self._ns_contexts = [{}]  # contains uri -> prefix dicts
        self._current_context = self._ns_contexts[-1]
        self._undeclared_ns_maps = []
        self._encoding = encoding
        self._short_empty_elements = short_empty_elements
        self._pending_start_element = False

    def _qname(self, name):
        """Builds a qualified name from a (ns_url, localname) pair"""
        if name[0]:
            # Per http://www.w3.org/XML/1998/namespace, The 'xml' prefix is
            # bound by definition to http://www.w3.org/XML/1998/namespace.  It
            # does not need to be declared and will not usually be found in
            # self._current_context.
            if 'http://www.w3.org/XML/1998/namespace' == name[0]:
                return 'xml:' + name[1]
            # The name is in a non-empty namespace
            prefix = self._current_context[name[0]]
            if prefix:
                # If it is not the default namespace, prepend the prefix
                return prefix + ":" + name[1]
        # Return the unqualified name
        return name[1]

    async def _finish_pending_start_element(self):
        if self._pending_start_element:
            await self._write('>')
            self._pending_start_element = False

    # ContentHandler methods

    async def startDocument(self):
        await self._write('<?xml version="1.0" encoding="%s"?>\n' %
                    self._encoding)

    async def endDocument(self):
        await self._flush()

    def startPrefixMapping(self, prefix, uri):
        self._ns_contexts.append(self._current_context.copy())
        self._current_context[uri] = prefix
        self._undeclared_ns_maps.append((prefix, uri))

    def endPrefixMapping(self):
        self._current_context = self._ns_contexts[-1]
        del self._ns_contexts[-1]

    async def startElement(self, name, attrs):
        await self._finish_pending_start_element()
        await self._write('<' + name)
        for (name, value) in attrs.items():
            await self._write(' %s=%s' % (name, quoteattr(value)))
        if self._short_empty_elements:
            self._pending_start_element = True
        else:
            await self._write(">")

    async def endElement(self, name):
        if self._pending_start_element:
            await self._write('/>')
            self._pending_start_element = False
        else:
            await self._write('</%s>' % name)

    async def startElementNS(self, name, attrs):
        await self._finish_pending_start_element()
        await self._write('<' + self._qname(name))

        for prefix, uri in self._undeclared_ns_maps:
            if prefix:
                await self._write(' xmlns:%s="%s"' % (prefix, uri))
            else:
                await self._write(' xmlns="%s"' % uri)
        self._undeclared_ns_maps = []

        for (name, value) in attrs.items():
            await self._write(' %s=%s' % (self._qname(name), quoteattr(value)))
        if self._short_empty_elements:
            self._pending_start_element = True
        else:
            await self._write(">")

    async def endElementNS(self, name):
        if self._pending_start_element:
            await self._write('/>')
            self._pending_start_element = False
        else:
            await self._write('</%s>' % self._qname(name))

    async def characters(self, content):
        if content:
            await self._finish_pending_start_element()
            if not isinstance(content, str):
                content = str(content, self._encoding)
            await self._write(escape(content))

    async def ignorableWhitespace(self, content):
        if content:
            await self._finish_pending_start_element()
            if not isinstance(content, str):
                content = str(content, self._encoding)
            await self._write(content)

    async def processingInstruction(self, target, data):
        await self._finish_pending_start_element()
        await self._write('<?%s %s?>' % (target, data))


class SimplerXMLGenerator(AsyncXMLGenerator):
    async def addQuickElement(self, name: str, contents: str = None, attrs: dict = None) -> None:
        """Convenience method for adding an element with no children"""
        if attrs is None:
            attrs = {}
        await self.startElement(name, attrs)
        if contents is not None:
            await self.characters(contents)
        await self.endElement(name)

    async def characters(self, content: str) -> None:
        if content and re.search(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", content):
            # Fail loudly when content has control chars (unsupported in XML 1.0)
            # See http://www.w3.org/International/questions/qa-controls
            raise UnserializableContentError("Control characters are not supported in XML 1.0")
        await super().characters(content)


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
