import os
import json
import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth
from deep_translator import GoogleTranslator
import html2text

POSTED_FILE = "posted.json"

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_posted(posted_set):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_set), f, ensure_ascii=False, indent=2)

def summarize_text(text, ratio=0.3):
    sentences = text.split(".")
    keep = max(1, int(len(sentences) * ratio))
    return ".".join(sentences[:keep]) + "."

def translate_text(text, target_lang="zh-TW"):
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception as e:
        print(f"翻譯失敗：{e}")
        return text

def fetch_uscis_news():
    base_url = "https://www.uscis.gov"
    listing_url = f"{base_url}/newsroom/news-releases"
    response = requests.get(listing_url)
    if response.status_code != 200:
        print(f"Failed to retrieve page, status code: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    news_links = soup.select('.views-row .field-content a[hreflang="en"]')

    news_items = []
    for link in news_links:
        title = link.get_text(strip=True)
        href = link['href']
        full_url = f"{base_url}{href}"

        # 抓取新聞內頁
        detail_resp = requests.get(full_url)
        if detail_resp.status_code == 200:
            detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
            body_div = detail_soup.find("div", class_="field--name-body")
            content_html = body_div.decode_contents() if body_div else ""
        else:
            content_html = ""

        # 轉為純文字
        text_maker = html2text.HTML2Text()
        text_maker.ignore_links = True
        text_maker.ignore_images = True
        plain_text = text_maker.handle(content_html)

        # 摘要 + 翻譯
        summary_en = summarize_text(plain_text)
        summary_zh = translate_text(summary_en)

        news_items.append({
            'title': title,
            'url': full_url,
            'content': summary_zh
        })

    return news_items

def post_to_wordpress(title, url, content, wp_site, wp_user, wp_password):
    post_data = {
        'title': title,
        'content': f'''
            <style>
                .uscis-article {{
                    font-family: "Arial", sans-serif;
                    font-size: 16px;
                    line-height: 1.8;
                    color: #333;
                    background-color: #f9f9f9;
                    padding: 16px;
                    border-radius: 6px;
                    border: 1px solid #ddd;
                }}
                .uscis-article a {{
                    color: #0073aa;
                    text-decoration: none;
                }}
                .uscis-article a:hover {{
                    text-decoration: underline;
                }}
                .uscis-note {{
                    color: #777;
                    font-size: 14px;
                    margin-top: 12px;
                }}
            </style>
            <div class="uscis-article">
                <p>{content}</p>
                <p class="uscis-note"><strong>新聞來源：</strong> 
                <a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a><br/>
                本文轉自美國移民局（USCIS）官方最新資訊，僅供參考。</p>
            </div>
        ''',
        'status': 'publish'
    }

    auth = HTTPBasicAuth(wp_user, wp_password)
    response = requests.post(f"{wp_site}/wp-json/wp/v2/posts", json=post_data, auth=auth)
    if response.status_code == 201:
        print(f"✅ 已發佈：{title}")
        return True
    else:
        print(f"❌ 發佈失敗：{title}，狀態碼：{response.status_code}，錯誤訊息：{response.text}")
        return False

if __name__ == "__main__":
    WP_SITE = os.getenv("WP_SITE_URL")
    WP_USER = os.getenv("WP_USERNAME")
    WP_PASSWORD = os.getenv("WP_APP_PASSWORD")

    if not all([WP_SITE, WP_USER, WP_PASSWORD]):
        print("請先設定環境變數 WP_SITE_URL, WP_USERNAME, WP_APP_PASSWORD")
        exit(1)

    posted = load_posted()
    news = fetch_uscis_news()

    for item in news:
        if item['url'] not in posted:
            success = post_to_wordpress(item['title'], item['url'], item['content'], WP_SITE, WP_USER, WP_PASSWORD)
            if success:
                posted.add(item['url'])

    save_posted(posted)
