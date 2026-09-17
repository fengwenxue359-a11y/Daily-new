import feedparser
from deep_translator import GoogleTranslator
import json
import os
import datetime

# ================= 你的资讯源（可以自己在这里添加） =================
RSS_FEEDS = [
    {"name": "Huberman Lab (YouTube)", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2D2CMWXMOVWx7giW1n3LIg"},
    {"name": "华尔街日报 - 科技", "url": "https://feeds.a.dj.com/rss/RSSWSJD.xml"},
    {"name": "经济学人 - 国际", "url": "https://www.economist.com/the-world-this-week/rss.xml"},
    {"name": "Nature 最新研究", "url": "https://www.nature.com/nature.rss"},
    {"name": "BBC 国际新闻", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"}
]

def translate_text(text):
    if not text: return ""
    try:
        return GoogleTranslator(source='en', target='zh-CN').translate(text[:1500])
    except Exception as e:
        print(f"翻译失败: {e}")
        return text

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
