import os
import requests
import time
import json
import re
import feedparser
from datetime import datetime, timezone, timedelta
import email.utils
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

# === ⚙️ 配置区域 ===
MAX_ITEMS = 5  # 每个源最多抓取最新的 N 条

# === 🔗 优质源列表 ===
RSS_URLS = [
    # --- 核心巨头 ---
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml"},
    {"name": "DeepMind", "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "HuggingFace", "url": "https://huggingface.co/blog/feed.xml"},
    
    # --- 借道源 (解决反爬/无RSS问题) ---
    {"name": "Anthropic(TC)", "url": "https://techcrunch.com/tag/anthropic/feed/"},
    {"name": "Meta AI(Eng)", "url": "https://engineering.fb.com/category/ai/feed/"},
    
    # --- 社区与产品 ---
    {"name": "ProductHunt", "url": "https://www.producthunt.com/feed?category=artificial-intelligence"},
    {"name": "GitHub Py", "url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml"},
    {"name": "TheVerge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    
    # --- 国内源 ---
    {"name": "QbitAI", "url": "https://www.qbitai.com/feed"},
    {"name": "PyTorch", "url": "https://pytorch.org/blog/feed.xml"},
]

# === 🛠️ 工具函数 ===

def clean_html(raw_html):
    """去除描述中的 HTML 标签，只留纯文本"""
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html)
    return text.replace('\n', ' ').strip()[:300] # 截断一下，省Token

def parse_date(date_obj_or_str):
    """万能日期清洗：统一返回 YYYY-MM-DD HH:MM"""
    if not date_obj_or_str: return "N/A"
    
    # 如果已经是 struct_time (feedparser 解析结果)
    if isinstance(date_obj_or_str, time.struct_time):
        return time.strftime('%Y-%m-%d %H:%M', date_obj_or_str)

    date_str = str(date_obj_or_str)
    dt = None
    try:
        # 1. 尝试 RFC 822 (RSS)
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed: dt = parsed
    except:
        pass
        
    if not dt:
        try:
            # 2. 尝试 ISO 8601 (Atom)
            clean_iso = date_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_iso)
        except:
            pass
            
    if dt:
        return dt.strftime('%Y-%m-%d %H:%M')
    return date_str  # 解析失败返回原样

def extract_metadata(xml_content, source_name):
    """解析 RSS/Atom 内容 (使用 feedparser)"""
    try:
        # feedparser 最好直接处理 bytes，以便它自己处理编码
        feed = feedparser.parse(xml_content)
        
        parsed_items = []
        dates = []
        
        for item in feed.entries[:MAX_ITEMS]:
            # 1. 提取 Title
            title = item.get('title', 'No Title')

            # 2. 提取 Link
            link = item.get('link', 'N/A')

            # 3. 提取 Date
            # feedparser 通常会提供 parsed 后的 struct_time
            raw_date = item.get('published_parsed') or item.get('updated_parsed')
            
            # 如果解析失败，尝试获取原始字符串
            if not raw_date:
                raw_date = item.get('published') or item.get('updated') or item.get('date')

            clean_date = parse_date(raw_date)
            if clean_date != "N/A": dates.append(clean_date)

            # 4. 提取 Description
            # 优先找 summary / description
            desc = item.get('summary') or item.get('description') or ""
            
            # 如果没有，尝试找 content (通常是 list)
            if not desc and 'content' in item:
                # content 是一个 list，里面可能有 html 或 text
                for c in item.content:
                    if c.get('value'):
                        desc = c.get('value')
                        break
            
            clean_desc = clean_html(desc)

            # 5. 存入结果
            parsed_items.append({
                "source": source_name,
                "title": title,
                "url": link,
                "date": clean_date,
                "desc": clean_desc
            })
            
        latest = max(dates) if dates else "N/A"
        return parsed_items, latest
        
    except Exception as e:
        print(f"解析错误: {e}")
        return [], "Error"

# === 🚀 主逻辑 ===
def run_etl_pipeline():
    all_news_json = []  # 存放所有清洗好的新闻
    report_lines = []   # 存放给管理员看的报告

    # 控制台打印表头
    print(f"{'Source Name':<20} | {'Status':<5} | {'Count':<5} | {'Latest Date'}")
    print("-" * 80)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }

    for src in RSS_URLS:
        name = src['name']
        url = src['url']
        
        status = "🔴"
        count = 0
        latest_date = "---"
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                # 解析数据
                # 传入 resp.content (bytes) 给 feedparser
                items, latest_date = extract_metadata(resp.content, name)
                count = len(items)
                
                if count > 0:
                    status = "✅"
                    all_news_json.extend(items) # 加入总列表
                else:
                    status = "⚠️"
            else:
                status = "❌"
                latest_date = f"HTTP {resp.status_code}"
                
        except Exception as e:
            status = "❌"
            latest_date = "Conn Err"

        # 打印并记录日志
        print(f"{name:<20} | {status} | {count:<5} | {latest_date}")
        report_lines.append(f"{status} [{name}] Items:{count} | Latest:{latest_date}")
        time.sleep(1)

    return all_news_json, "\n".join(report_lines)

def upload_to_cos(filename, content):
    if not content: return
    try:
        config = CosConfig(Region=os.environ['COS_REGION'], SecretId=os.environ['TENCENT_SECRET_ID'], SecretKey=os.environ['TENCENT_SECRET_KEY'])
        client = CosS3Client(config)
        client.put_object(
            Bucket=os.environ['COS_BUCKET'], Body=content.encode('utf-8'), Key=filename,
            StorageClass='STANDARD', ContentType='application/json; charset=utf-8' # 注意这里是 json
        )
        print(f"🎉 Uploaded: {filename}")
    except Exception as e:
        print(f"❌ Upload Failed {filename}: {e}")

if __name__ == "__main__":
    # 1. 抓取与清洗
    clean_data, report_txt = run_etl_pipeline()
    
    # 2. 上传 JSON 数据 (给 Coze 机器读)
    # json.dumps 处理非 ASCII 字符，保持中文可读
    if clean_data:
        json_str = json.dumps(clean_data, ensure_ascii=False, indent=2)
        upload_to_cos('RSS/news.json', json_str)
    
    # 3. 上传 报告文件 (给 管理员 读)
    if report_txt:
        upload_to_cos('RSS/rss_report.txt', report_txt)
