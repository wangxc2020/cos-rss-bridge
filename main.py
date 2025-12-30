import os
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

# === 配置: 每个源只保留最新的 N 条 ===
MAX_ITEMS_PER_SOURCE = 5

# === ✅ 修复后的源列表 ===
RSS_URLS = [
    # 1. 行业基石
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    
    # 2. 之前报错的源已修复
    # Meta Engineering (原路径404，改用主订阅源，包含AI内容)
    "https://engineering.fb.com/feed/", 
    
    # PyTorch (官方源)
    "https://pytorch.org/blog/feed.xml",
    
    # Stability AI (尝试修复 XML 解析问题)
    "https://stability.ai/news?format=rss",
    
    # 3. 稳定源
    "https://www.producthunt.com/feed?category=artificial-intelligence",
    "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml",
    
    # 4. 替代源
    # TechCrunch - Anthropic 标签
    "https://techcrunch.com/tag/anthropic/feed/",
    # The Verge - AI 标签
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    # 国内保底
    "https://www.qbitai.com/feed"
]

# === 核心：XML 瘦身函数 ===
def truncate_xml_content(xml_text, limit=MAX_ITEMS_PER_SOURCE):
    """
    解析 XML，强制只保留前 N 个 item/entry，然后重新生成字符串。
    极大幅度减少文件体积。
    """
    try:
        # 注册命名空间防止 tag 变成 ns0:item
        ET.register_namespace('', "http://www.w3.org/2005/Atom")
        
        # 这种方式是为了容错，有些 XML 声明可能有问题
        root = ET.fromstring(xml_text)
        
        # 1. 处理 RSS 2.0 (<channel> -> <item>)
        channel = root.find('channel')
        if channel is not None:
            items = channel.findall('item')
            # 如果数量超过限制，移除多余的
            if len(items) > limit:
                for item in items[limit:]:
                    channel.remove(item)
        
        # 2. 处理 Atom (<feed> -> <entry>)
        else:
            # Atom 根节点通常就是 feed
            entries = root.findall('{http://www.w3.org/2005/Atom}entry')
            if not entries:
                 entries = root.findall('entry') # 尝试无 namespace
            
            if len(entries) > limit:
                for entry in entries[limit:]:
                    root.remove(entry)
                    
        # 重新转回字符串
        return ET.tostring(root, encoding='unicode')
        
    except Exception as e:
        # 如果解析失败（太乱的格式），为了兜底，还是返回原文，但做字符串强行截断
        # 避免几 MB 的文件传上去
        return xml_text[:10000] 

# === 元数据分析工具 (用于报告) ===
def analyze_xml_simple(xml_text):
    try:
        root = ET.fromstring(xml_text)
        items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('.//entry')
        
        count = len(items)
        latest_date = "N/A"
        if items:
            item = items[0]
            for tag in ['pubDate', 'published', 'updated', 'dc:date']:
                node = item.find(tag)
                if node is None: node = item.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
                if node is not None and node.text:
                    latest_date = node.text[:25]
                    break
        return count, latest_date
    except:
        return 0, "Parse Err"

def fetch_and_report():
    combined_data = ""
    report_lines = []
    
    print(f"{'RSS 源 (Short URL)':<40} | {'Status':<6} | {'Raw Num':<7} | {'Action'}")
    print("-" * 90)
    
    report_lines.append(f"更新时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    report_lines.append(f"策略: 每个源仅保留最新的 {MAX_ITEMS_PER_SOURCE} 条")
    report_lines.append("-" * 60)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }

    for url in RSS_URLS:
        status_icon = "🔴"
        raw_count = 0
        action_msg = "Fail"
        short_url = url.replace("https://", "").replace("www.", "")[:38]

        try:
            resp = requests.get(url, headers=headers, timeout=25)
            
            if resp.status_code == 200 and len(resp.text) > 100:
                status_icon = "✅"
                
                # 1. 瘦身处理
                lean_xml = truncate_xml_content(resp.text, limit=MAX_ITEMS_PER_SOURCE)
                
                # 2. 统计原始数量 vs 瘦身数量
                raw_count, _ = analyze_xml_simple(resp.text)
                final_count, latest_date = analyze_xml_simple(lean_xml)
                
                action_msg = f"Cut {raw_count}->{final_count}"
                
                # 3. 只有真正有内容才加入 Combined
                if final_count > 0:
                    combined_data += f"\n\n<<<<SOURCE_START:{url}>>>>\n"
                    combined_data += lean_xml
                    combined_data += f"\n<<<<SOURCE_END>>>>\n"
            else:
                status_icon = "❌"
                action_msg = f"HTTP {resp.status_code}"

        except Exception as e:
            status_icon = "❌"
            action_msg = "Err"

        print(f"{short_url:<40} | {status_icon} | {raw_count:<7} | {action_msg}")
        report_lines.append(f"{status_icon} {short_url}")
        report_lines.append(f"   Items: {raw_count} -> {MAX_ITEMS_PER_SOURCE} | Last: {action_msg}")
        
        time.sleep(1)

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
    if len(full_data) > 200:
        upload_to_cos('RSS/rss_mirror.txt', full_data)
        upload_to_cos('RSS/rss_report.txt', report_text)
    else:
        print("⚠️ 数据量过少，跳过上传。")
