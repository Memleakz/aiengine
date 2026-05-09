import re
import urllib.parse
import urllib.request


async def web_search(query: str) -> str:
    """Perform a web search using DuckDuckGo Lite and return snippet results."""
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({'q': query}).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent/1.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch():
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode("utf-8", errors="ignore")

        html = await loop.run_in_executor(None, _fetch)

        # Simple regex extraction for DuckDuckGo Lite results
        # DDG Lite uses class="result-snippet" for descriptions
        snippets = re.findall(r'<td class=\'result-snippet\'[^>]*>(.*?)</td>', html, flags=re.IGNORECASE | re.DOTALL)

        if not snippets:
            return "No results found or search was blocked. Try using web_fetch directly on known URLs."

        results = []
        for s in snippets[:5]:  # Top 5 results
            # Clean up HTML tags
            clean_text = re.sub(r'<[^>]+>', '', s).strip()
            if clean_text:
                results.append(clean_text)

        return "\n\n".join([f"{i+1}. {r}" for i, r in enumerate(results)])

    except Exception as e:
        return f"Error performing web search: {e}"
