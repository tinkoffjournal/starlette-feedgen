# Starlette FeedGen
RSS/Atom feeds generation for [Starlette](https://www.starlette.io/),
adapted from [Django syndication feed framework](https://docs.djangoproject.com/en/stable/ref/contrib/syndication/).

## Installation
```sh
pip install starlette_feedgen
```

## Usage

```python
from typing import NamedTuple
from starlette.applications import Starlette
from starlette_feedgen import FeedEndpoint

class FeedItem(NamedTuple):
    title = 'Hello'
    description = 'There'
    link = 'http://example.com/article'

app = Starlette()

@app.route('/feed')
class Feed(FeedEndpoint):
    title = 'Example RSS Feed'
    description = 'With example item'
    link = 'http://example.com'

    async def get_items(self):
        yield FeedItem()
```

Example RSS Output:

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>Example RSS Feed</title>
        <link>http://example.com</link>
        <description>With example item</description>
        <atom:link rel="self" href="/feed"></atom:link>
        <lastBuildDate>Wed, 27 May 2020 13:38:55 +0000</lastBuildDate>
        <item>
            <title>Hello</title>
            <link>http://example.com/article</link>
            <description>There</description>
            <guid>http://example.com/article</guid>
        </item>
    </channel>
</rss>
```
