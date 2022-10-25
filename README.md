# Starlette FeedGen
Asynchronous RSS/Atom feeds generation for [Starlette](https://www.starlette.io/),
adapted from [Django syndication feed framework](https://docs.djangoproject.com/en/stable/ref/contrib/syndication/).

## Installation
```sh
pip install starlette-feedgen
```

## Usage

Here's a simple example of handling route `/feed` using `FeedEndpoint` class.

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

        async def item_generator():
            yield FeedItem()

        return item_generator()
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
        <lastBuildDate>Thu, 20 Oct 2022 12:46:17 +0000</lastBuildDate>
        <item>
            <title>Hello</title>
            <link>http://example.com/article</link>
            <description>There</description>
            <guid>http://example.com/article</guid>
        </item>
    </channel>
</rss>
```

Note that `FeedEndpoint` creates a feed generator object `Rss201rev2Feed` under the hood.
You can explicitly import a feed generator class and work with it, for example:

```python
import aiofiles
import asyncio
from starlette_feedgen.generator import Rss201rev2Feed

feed = Rss201rev2Feed(
    title='Poynter E-Media Tidbits',
    link='http://www.poynter.org/column.asp?id=31',
    description='A group Weblog by the sharpest minds in online media/journalism/publishing.',
    language='en',
)

feed.add_item(
    title='Hello',
    link='http://www.holovaty.com/test/',
    description='Testing.'
)


async def write_to_file():
    async with aiofiles.open('test.rss', 'w') as f:
        await feed.write(f, 'utf-8')

asyncio.run(write_to_file())
```

RSS Output:
```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"
	xmlns:atom="http://www.w3.org/2005/Atom">
	<channel>
		<title>Poynter E-Media Tidbits</title>
		<link>http://www.poynter.org/column.asp?id=31</link>
		<description>A group Weblog by the sharpest minds in online media/journalism/publishing.</description>
		<language>en</language>
		<lastBuildDate>Thu, 20 Oct 2022 13:24:50 +0000</lastBuildDate>
		<item>
			<title>Hello</title>
			<link>http://www.holovaty.com/test/</link>
			<description>Testing.</description>
		</item>
	</channel>
</rss>
```

For definitions of the different versions of RSS, see:
https://web.archive.org/web/20110718035220/http://diveintomark.org/archives/2004/02/04/incompatible-rss