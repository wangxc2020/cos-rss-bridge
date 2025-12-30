import os
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

# === ✅ 2025年12月 终极修正版 URL 列表 ===
RSS_URLS = [
    # --- 1. 极其稳定的官方源 ---
    "https://openai.com/news/rss.xml",                # OpenAI (稳)
    "https://deepmind.google/blog/rss.xml",           # DeepMind (稳)
    "https://huggingface.co/blog/feed.xml",           # HuggingFace (稳)
    "https://www.producthunt.com/feed?category=artificial-intelligence", # Product Hunt (稳)
    "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml",   # GitHub热榜 (稳)
    
    # --- 2. 修正后的源 ---
    
    # PyTorch: 修正 URL 路径
    "https://pytorch.org/blog/feed.xml",
    
    # Meta AI: 官网反爬太严(400)，改用 Meta 工程博客 AI 分类 (WordPress架构，非常稳)
    "https://engineering.fb.com/category/ai/feed/",
    
    # Stability AI: 修正参数
    "https://stability.ai/news?format=rss",

    # --- 3. "借刀杀人"源 (专门解决无RSS/停更问题) ---
    
    # Anthropic: 官网无RSS，社区源停更。改用 TechCrunch 的 Anthropic 专属标签
    # 只要 Anthropic 发新闻，TechCrunch 肯定第一时间报。
    "https://techcrunch.com/tag/anthropic/feed/",
    
    # 补充: The Verge AI (替代反爬严重的 Ben Evans)
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    
    # --- 4. 国内源 (作为数据保底) ---
    "https://www.qbitai.com/feed"
]

# === XML 解析与清洗工具 ===
def analyze_xml(xml_text):
    try:
        # 预处理：有些源 xml 声明编码可能有误，强行忽略错误解码
        root = ET.fromstring(xml_text)
        items = root.findall('.//item')
        if not items: items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        if not items: items = root.findall('.//entry')
            
        count = len(items)
        latest_date = "N/A"
        
        # 找最新日期 (前3条)
        for item in items[:3]:
            # 优先找 pubDate (RSS)
            node = item.find('pubDate')
            # 其次找 published (Atom)
            if node is None: node = item.find('{http://www.w3.org/2005/Atom}published')
            # 再次找 updated
            if node is None: node = item.find('{http://www.w3.org/2005/Atom}updated')
            # 再次找 dc:date
            if node is None: node = item.find('{http://purl.org/dc/elements/1.1/}date')
            
            if node is not None and node.text:
                # 截断日期字符串，太长了没法看
                latest_date = node.text[:25]
                break
                
        return count, latest_date
    except Exception:
        return 0, "Parse Error"

def fetch_and_report():
    combined_data = ""
    report_lines = []
    
    print(f"{'RSS 源 (Short URL)':<40} | {'St':<2} | {'Num':<3} | {'Latest Date'}")
    print("-" * 85)
    
    report_lines.append(f"更新时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    report_lines.append("-" * 60)
    
    # 伪装头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://google.com'
    }

    for url in RSS_URLS:
        status_icon = "🔴"
        count = 0
        latest = "---"
        # 简化 URL 显示
        short_url = url.replace("https://", "").replace("www.", "").replace("techcrunch.com/tag/", "TC/").replace("feed/", "")[:38]

        try:
            resp = requests.get(url, headers=headers, timeout=25)
            
            # 兼容：有些服务器返回 403 但其实给了内容（罕见），主要看 200
            if resp.status_code == 200 and len(resp.text) > 500:
                status_icon = "✅"
                count, latest = analyze_xml(resp.text)
                
                # 只有解析出条目的才算真正成功
                if count > 0:
                    combined_data += f"\n\n<<<<SOURCE_START:{url}>>>>\n"
                    combined_data += resp.text
                    combined_data += f"\n<<<<SOURCE_END>>>>\n"
                else:
                    status_icon = "⚠️"
                    latest = "Xml Empty"
            else:
                status_icon = "❌"
                latest = f"HTTP {resp.status_code}"

        except Exception as e:
            status_icon = "❌"
            latest = "Err"

        print(f"{short_url:<40} | {status_icon} | {count:<3} | {latest}")
        
        report_lines.append(f"{status_icon} {short_url}")
        report_lines.append(f"   Items: {count} | Last: {latest}")
        
        time.sleep(2)

    return combined_data, "\n".join(report_lines)

def upload_to_cos(filename, content):
    if not content: return
    secret_id = os.environ['TENCENT_SECRET_ID']
    secret_key = os.environ['TENCENT_SECRET_KEY']
    region = os.environ['COS_REGION']
    bucket = os.environ['COS_BUCKET']
    
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)
    
    try:
        client.put_object(
            Bucket=bucket, Body=content.encode('utf-8'), Key=filename,
            StorageClass='STANDARD', ContentType='text/plain; charset=utf-8'
        )
        print(f"🎉 Upload Success: {filename}")
    except Exception as e:
        print(f"❌ Upload Failed {filename}: {e}")

if __name__ == "__main__":
    full_data, report_text = fetch_and_report()
    if len(full_data) > 500:
        upload_to_cos('RSS/rss_mirror.txt', full_data)
        upload_to_cos('RSS/rss_report.txt', report_text)
    else:
        print("⚠️ 数据量严重不足，跳过上传。")
