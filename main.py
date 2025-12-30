import os
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

# === ✅ 经过人工清洗、修复后的完整源列表 ===
RSS_URLS = [
    # --- 1. 全球 AI 巨头 (Core) ---
    "https://openai.com/news/rss.xml",                # OpenAI 官方
    "https://deepmind.google/blog/rss.xml",           # Google DeepMind 官方
    "https://ai.meta.com/blog/rss.xml",               # Meta AI (Facebook) 官方
    # Anthropic 官网无 RSS，使用 GitHub 社区每天更新的静态镜像
    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    
    # --- 2. 开发者与开源社区 (Dev) ---
    "https://huggingface.co/blog/feed.xml",           # HuggingFace 博客
    "https://pytorch.org/feed.xml",                   # PyTorch 框架动态
    # GitHub Python 热榜 (静态镜像，极稳)
    "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml",
    
    # --- 3. 行业分析与趋势 (Insights) ---
    "https://lastweekin.ai/feed",                     # Last Week in AI (高质量汇总)
    "https://www.ben-evans.com/benedictevans?format=xml", # Benedict Evans (深度分析，已修正链接)
    
    # --- 4. 新产品发现 (Product) ---
    "https://www.producthunt.com/feed?category=artificial-intelligence", # Product Hunt AI榜
    
    # --- 5. 国内媒体 (在 GitHub 抓取是防止国内服务器波动，作为备份) ---
    "https://www.qbitai.com/feed"                     # 量子位 (已修正 feet -> feed)
]

# === 简单的 XML 元数据分析工具 ===
def analyze_xml(xml_text):
    try:
        root = ET.fromstring(xml_text)
        items = root.findall('.//item')
        if not items: items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        if not items: items = root.findall('.//entry')
            
        count = len(items)
        latest_date = "N/A"
        
        # 找最新日期
        for item in items[:3]:
            for tag in ['pubDate', 'published', 'updated', 'dc:date']:
                node = item.find(tag)
                if node is None: node = item.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
                if node is not None and node.text:
                    latest_date = node.text[:25]
                    break
            if latest_date != "N/A": break
        return count, latest_date
    except:
        return 0, "Parse Error"

def fetch_and_report():
    combined_data = ""
    report_lines = []
    
    # 打印控制台表头
    print(f"{'RSS 源 (Short URL)':<40} | {'St':<2} | {'Num':<3} | {'Latest Date'}")
    print("-" * 85)
    
    report_lines.append(f"更新时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    report_lines.append("-" * 60)
    
    # 强力浏览器伪装头 (解决 Product Hunt / Ben Evans 反爬)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://google.com'
    }

    for url in RSS_URLS:
        status_icon = "🔴"
        count = 0
        latest = "---"
        short_url = url.replace("https://", "").replace("www.", "").replace("raw.githubusercontent.com", "github_raw")[:38]

        try:
            # 30秒超时，防止大文件卡死
            resp = requests.get(url, headers=headers, timeout=30)
            
            if resp.status_code == 200 and len(resp.text) > 100:
                status_icon = "✅"
                count, latest = analyze_xml(resp.text)
                
                # 拼接数据 (打上标签，方便 Coze 识别来源)
                combined_data += f"\n\n<<<<SOURCE_START:{url}>>>>\n"
                combined_data += resp.text
                combined_data += f"\n<<<<SOURCE_END>>>>\n"
            else:
                status_icon = "⚠️"
                latest = f"HTTP {resp.status_code}"

        except Exception as e:
            status_icon = "❌"
            latest = "Err" # 简化报错显示

        # 打印进度
        print(f"{short_url:<40} | {status_icon} | {count:<3} | {latest}")
        
        # 写入报告
        report_lines.append(f"{status_icon} {short_url}")
        report_lines.append(f"   Items: {count} | Latest: {latest}")
        
        # 休息 2 秒，防封
        time.sleep(2)

    return combined_data, "\n".join(report_lines)

def upload_to_cos(filename, content):
    if not content: return
    
    # 从 GitHub Secrets 获取密钥
    secret_id = os.environ['TENCENT_SECRET_ID']
    secret_key = os.environ['TENCENT_SECRET_KEY']
    region = os.environ['COS_REGION']
    bucket = os.environ['COS_BUCKET']
    
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)
    
    try:
        client.put_object(
            Bucket=bucket,
            Body=content.encode('utf-8'),
            Key=filename,
            StorageClass='STANDARD',
            ContentType='text/plain; charset=utf-8'
        )
        print(f"🎉 Upload Success: {filename}")
    except Exception as e:
        print(f"❌ Upload Failed {filename}: {e}")

if __name__ == "__main__":
    # 1. 执行抓取
    full_data, report_text = fetch_and_report()
    
    # 2. 上传数据 (只要有数据就传)
    if len(full_data) > 500:
        upload_to_cos('rss_mirror.txt', full_data)
        upload_to_cos('rss_report.txt', report_text)
    else:
        print("⚠️ 数据量过少 (<500b)，放弃上传，请检查网络或源。")
