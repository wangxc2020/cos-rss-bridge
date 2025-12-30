from main import extract_metadata
import requests

urls = [
    ("Karpathy", "https://karpathy.bearblog.dev/feed/"),
    ("Sam Altman", "https://blog.samaltman.com/rss"),
    ("AI Explained", "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw"),
    ("Jiqizhixin", "https://www.jiqizhixin.com/rss")
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}

for name, url in urls:
    print(f"Testing {name}...")
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Failed: {resp.status_code}")
            continue
        items, latest = extract_metadata(resp.content, name)
        print(f"Latest: {latest}, Count: {len(items)}")
        if items:
            print(f"  Sample: {items[0]['title']} ({items[0]['date']})")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 20)
