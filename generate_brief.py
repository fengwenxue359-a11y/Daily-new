#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日国外播客学习简报生成器（云端版）
- 抓取国外知名播客 RSS，解析最新剧集
- 若配置了 LLM_API_KEY（OpenAI 兼容接口，如 DeepSeek / 智谱 / OpenAI），调用大模型生成中文学习简报
- 未配置 API Key 时，自动降级为「最新剧集速览」简报（仍然可用）
- 输出 briefs/daily-learning-YYYY-MM-DD.html 并更新 index.html（着陆页）

部署：GitHub Actions 每天 UTC 00:00（北京时间 08:00）自动运行并提交到仓库，
     配合 GitHub Pages 即可实现手机随时访问，全程无需本地电脑开机。
"""
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
TODAY = datetime.now(BJT).strftime("%Y-%m-%d")

# ============ 配置：想增删播客改这里 ============
# feed 留空时，脚本会通过 Apple iTunes Search API 自动解析该节目的 RSS 地址
SHOWS = [
    {"name": "Huberman Lab", "category": "个人成长", "feed": "https://feeds.megaphone.fm/hubermanlab"},
    {"name": "The Tim Ferriss Show", "category": "个人成长", "feed": "https://rss.art19.com/tim-ferriss-show"},
    {"name": "The Diary Of A CEO", "category": "个人成长", "feed": ""},
    {"name": "My First Million", "category": "赚钱商业", "feed": ""},
    {"name": "The Prof G Pod", "category": "赚钱商业", "feed": ""},
    {"name": "All-In Podcast", "category": "科技投资", "feed": ""},
    {"name": "Acquired", "category": "科技投资", "feed": ""},
]
MAX_EPISODES_PER_SHOW = 3  # 每档节目取最近几集
EPISODE_DAYS = 10          # 只纳入 N 天内发布的剧集

# ============ LLM 配置（可选，OpenAI 兼容接口）============
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GrowDailyBot/1.0)",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def resolve_feed(show_name):
    """通过 Apple iTunes Search API 解析节目 RSS 地址"""
    api = ("https://itunes.apple.com/search?term={}&media=podcast&limit=1"
           .format(urllib.request.quote(show_name)))
    try:
        data = json.loads(http_get(api))
        results = data.get("results", [])
        return results[0].get("feedUrl", "") if results else ""
    except Exception as e:
        print(f"[warn] iTunes 查询失败 {show_name}: {e}")
        return ""


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").replace("&amp;", "&") \
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"') \
        .replace("&#39;", "'").replace("&nbsp;", " ")


def parse_feed(feed_url, days=EPISODE_DAYS):
    """解析 RSS，返回最近的剧集列表"""
    eps = []
    try:
        root = ET.fromstring(http_get(feed_url))
        cutoff = datetime.now(BJT).timestamp() - days * 86400
        for item in root.iter("item"):
            title = strip_html(item.findtext("title", "")).strip()
            pub = item.findtext("pubDate", "")
            desc = strip_html(item.findtext("description", "")).strip()[:600]
            link = (item.findtext("link", "") or "").strip()
            dt = None
            if pub:
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
                    try:
                        dt = datetime.strptime(pub.strip(), fmt).astimezone(BJT)
                        break
                    except ValueError:
                        continue
            ts = dt.timestamp() if dt else 0
            if ts and ts < cutoff:
                continue
            eps.append({"title": title, "date": dt.strftime("%Y-%m-%d") if dt else "",
                        "desc": desc, "link": link})
            if len(eps) >= MAX_EPISODES_PER_SHOW:
                break
    except Exception as e:
        print(f"[warn] RSS 解析失败 {feed_url}: {e}")
    return eps


def collect_episodes():
    """收集所有节目的最新剧集"""
    shows = []
    for show in SHOWS:
        feed = show["feed"] or resolve_feed(show["name"])
        print(f"[info] {show['name']} -> {feed or '未找到 RSS'}")
        eps = parse_feed(feed) if feed else []
        if eps:
            shows.append({**show, "episodes": eps})
    return shows


def build_llm_context(shows):
    lines = []
    for s in shows:
        lines.append(f"## {s['name']}（{s['category']}）")
        for e in s["episodes"]:
            lines.append(f"- [{e['date']}] {e['title']}：{e['desc']}")
    return "\n".join(lines)


def call_llm(context):
    """调用 OpenAI 兼容接口生成中文简报正文（返回 markdown）"""
    prompt = f"""你是一名中文学习简报编辑。下面是从国外知名播客 RSS 抓取到的最新剧集信息。
请挑选 3-6 条最有价值的内容（优先个人成长、赚钱商业方向，优先最近几天发布的），写一份中文学习简报。

要求：
- 直接输出 HTML 片段（不要 <!DOCTYPE>/<html>/<head>/<body>），每条内容用 <div class="card"> 包裹
- 每条包含：分类 tag、节目名、中文标题、4-6 条核心观点要点(<ul><li>)、行动启发、原文链接
- 风格：简体中文、专有名词保留英文、务实可执行、不夸大不编造（没提到的细节不要虚构）
- 不要输出 markdown 代码块标记，直接输出 HTML

播客数据：
{context}"""
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {LLM_API_KEY}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return re.sub(r"^```(html)?\s*|\s*```$", "", content.strip())


PAGE_CSS = """
  :root { --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --muted:#6b7280; --line:#e5e8ee;
          --accent:#2f6fed; --accent-soft:#eaf1ff; --green:#0f9d76; --green-soft:#e6f7f1;
          --amber:#c77700; --amber-soft:#fff4e0; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         background:var(--bg); color:var(--ink); line-height:1.7; }
  .wrap { max-width:820px; margin:0 auto; padding:32px 20px 80px; }
  .header { background:linear-gradient(135deg,#2f6fed,#6b4ef5); color:#fff;
            border-radius:16px; padding:28px 30px; margin-bottom:24px; }
  .header h1 { font-size:23px; margin-bottom:6px; }
  .header p { opacity:.92; font-size:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:20px 24px; margin-bottom:16px; }
  .card h2 { font-size:16.5px; margin:4px 0 10px; }
  .card ul { padding-left:20px; margin:10px 0; font-size:14.5px; }
  .card li { margin-bottom:6px; }
  .tag { display:inline-block; font-size:11.5px; padding:2px 10px; border-radius:20px;
         margin-right:6px; margin-bottom:8px; font-weight:600; }
  .tag.growth { background:var(--green-soft); color:var(--green); }
  .tag.money  { background:var(--amber-soft); color:var(--amber); }
  .tag.tech   { background:var(--accent-soft); color:var(--accent); }
  .action { background:var(--green-soft); border-radius:10px; padding:10px 14px;
            font-size:13.5px; margin-top:10px; }
  .action b { color:var(--green); }
  .meta { color:var(--muted); font-size:13px; }
  a { color:var(--accent); text-decoration:none; }
  .footer { text-align:center; color:var(--muted); font-size:12.5px; margin-top:26px; }
  .empty { color:var(--muted); text-align:center; padding:40px 0; }
"""


def render_page(title, subtitle, body_html):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>📖 每日国外播客学习简报</h1>
    <p>{html.escape(subtitle)}</p >
  </div>
  {body_html}
  <p class="footer">GrowDaily · 由云端定时任务自动生成 · 学习改变来自行动，而非收藏</p >
</div>
</body>
</html>"""


def render_landing(brief_files):
    """着陆页：最新简报 + 历史归档"""
    links = "\n".join(
        f'<div class="card"><a href=" "file"]}">📖 {f["label"]}</a ></div>'
        for f in brief_files)
    body = f'<h2 style="font-size:18px;margin-bottom:14px">简报归档（按日期）</h2>{links or "<div class=\'empty\'>暂无简报</div>"}'
    return render_page("GrowDaily · 学习简报", "每天早上 8 点自动更新 · 点开阅读当天简报", body)


def main():
    shows = collect_episodes()
    if not shows:
        print("[error] 没有抓到任何剧集")
        return 1

    print(f"[info] 共 {len(shows)} 档节目有更新")
    if LLM_API_KEY:
        print("[info] 检测到 LLM_API_KEY，调用大模型生成简报...")
        body_html = call_llm(build_llm_context(shows))
    else:
        print("[info] 未配置 LLM_API_KEY，生成剧集速览简报")
        cards = []
        for s in shows:
            cat = {"个人成长": "growth", "赚钱商业": "money"}.get(s["category"], "tech")
            items = "".join(
                f'<li>[{e["date"]}] <a href="{e["link"] or "#"}" target="_blank">{html.escape(e["title"])}</a >'
                f'<br><span style="color:#6b7280;font-size:13px">{html.escape(e["desc"][:200])}</span></li>'
                for e in s["episodes"])
            cards.append(f'<div class="card"><span class="tag {cat}">{s["category"]}</span>'
                         f'<h2>{html.escape(s["name"])} · 最新剧集</h2><ul>{items}</ul></div>')
        tip = ('<div class="card" style="background:#eaf1ff;border-color:transparent">'
               '<b>提示：</b>当前为「剧集速览」模式。在 GitHub 仓库 Settings → Secrets 中配置 '
               'LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（OpenAI 兼容接口）后，'
               '下次运行将自动生成含核心观点与行动启发的完整中文简报。</div>')
        body_html = "\n".join(cards) + tip

    os.makedirs("briefs", exist_ok=True)
    fname = f"daily-learning-{TODAY}.html"
    subtitle = f"{TODAY} · 北京时间 08:00 自动生成 · 精选全球知名播客一手内容"
    with open(f"briefs/{fname}", "w", encoding="utf-8") as f:
        f.write(render_page(f"每日学习简报 · {TODAY}", subtitle, body_html))

    # 着陆页：列出 briefs 目录下所有简报（新→旧）
    briefs = sorted(
        ({"file": f"briefs/{f}", "label": f.replace("daily-learning-", "").replace(".html", "")}
         for f in os.listdir("briefs") if f.endswith(".html")),
        key=lambda x: x["label"], reverse=True)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_landing(briefs))

    print(f"[done] 已生成 briefs/{fname} 和 index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
