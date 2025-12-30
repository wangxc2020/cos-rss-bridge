from main import extract_metadata
import requests

urls = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("HuggingFace", "https://huggingface.co/blog/feed.xml"),
    ("DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Anthropic(TC)", "https://techcrunch.com/tag/anthropic/feed/")
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

for name, url in urls:
    print(f"Testing {name}...")
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        items, latest = extract_metadata(resp.content, name)
        print(f"Latest: {latest}")
        for item in items[:2]:
            print(f"  [{item['date']}] {item['title']} (Desc len: {len(item['desc'])})")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 20)
