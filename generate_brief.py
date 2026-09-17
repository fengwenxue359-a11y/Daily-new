import feedparser
from deep_translator import GoogleTranslator, MyMemoryTranslator
import json
import os
import datetime
import time

# ================= 你的资讯源 =================
RSS_FEEDS = [
    {"name": "Huberman Lab (YouTube)", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2D2CMWXMOVWx7giW1n3LIg"},
    {"name": "华尔街日报 - 科技", "url": "https://feeds.a.dj.com/rss/RSSWSJD.xml"},
    {"name": "经济学人 - 国际", "url": "https://www.economist.com/the-world-this-week/rss.xml"},
    {"name": "Nature 最新研究", "url": "https://www.nature.com/nature.rss"},
    {"name": "BBC 国际新闻", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"}
]

def translate_text(text):
    if not text: return ""
    # 优先使用 Google 翻译
    try:
        time.sleep(1) # 延时1秒，避免请求过快被封
        return GoogleTranslator(source='en', target='zh-CN').translate(text[:1000])
    except Exception as e:
        print(f"Google翻译失败，尝试备用引擎: {e}")
        # 如果 Google 失败，尝试备用引擎 MyMemory
        try:
            time.sleep(1)
            return MyMemoryTranslator(source='en', target='zh-CN').translate(text[:1000])
        except Exception as e2:
            print(f"备用翻译也失败: {e2}")
            return text # 全部失败，返回英文

def generate_daily_brief():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    brief_items = []
    for feed_info in RSS_FEEDS:
        feed = feedparser.parse(feed_info['url'])
        for entry in feed.entries[:4]:
            title_en = entry.title
            desc_en = entry.get('summary', '')[:600]
            item = {
                "source": feed_info["name"],
                "title_en": title_en,
                "title_cn": translate_text(title_en),
                "desc_en": desc_en,
                "desc_cn": translate_text(desc_en),
                "link": entry.link
            }
            brief_items.append(item)

    data = {"date": today_str, "items": brief_items}
    os.makedirs("briefs/archive", exist_ok=True)
    
    with open("briefs/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(f"briefs/archive/{today_str}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    archive_dir = "briefs/archive"
    history = sorted([f.replace('.json', '') for f in os.listdir(archive_dir) if f.endswith('.json')], reverse=True)
    with open("briefs/history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

    print(f"成功生成简报，共 {len(brief_items)} 条。")

if __name__ == "__main__":
    generate_daily_brief()
