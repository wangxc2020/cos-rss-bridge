import os
import requests
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client

# === 配置区域 ===
# 填入你需要抓取的“被墙”的 RSS 列表
RSS_URLS = [
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://www.anthropic.com/rss.xml",
    "https://hnrss.org/newest?q=AI+OR+GPT+points=100"
]

def fetch_and_merge():
    combined_data = ""
    print("开始抓取 RSS...")
    
    for url in RSS_URLS:
        try:
            # GitHub Action 在国外，无需代理
            print(f"正在抓取: {url}")
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=20)
            
            # 简单拼接：加上分隔符，方便 Coze 识别
            combined_data += f"\n\n<<<<SOURCE_START:{url}>>>>\n"
            combined_data += resp.text
            combined_data += f"\n<<<<SOURCE_END>>>>\n"
        except Exception as e:
            print(f"❌ 抓取失败 {url}: {e}")
            
    return combined_data

def upload_to_cos(content):
    secret_id = os.environ['TENCENT_SECRET_ID']
    secret_key = os.environ['TENCENT_SECRET_KEY']
    region = os.environ['COS_REGION']
    bucket = os.environ['COS_BUCKET']
    
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)
    
    # 上传文件名为 rss_mirror.txt
    response = client.put_object(
        Bucket=bucket,
        Body=content.encode('utf-8'),
        Key='rss_mirror.txt',
        StorageClass='STANDARD',
        ContentType='text/plain; charset=utf-8'
    )
    print(f"✅ 上传成功! ETag: {response['ETag']}")

if __name__ == "__main__":
    data = fetch_and_merge()
    if len(data) > 100:
        upload_to_cos(data)
    else:
        print("⚠️ 数据为空，跳过上传")
