import json
import os
import re
import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"
TARGET_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}


def send_discord(title, link, price, notice_type="新品上架"):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return

    color = 3066993 if notice_type == "現貨補貨" else 15844367

    embed = {
        "title": f"【Funbox 官網 - {notice_type}】{title}",
        "url": link,
        "color": color,
        "fields": [
            {"name": "狀態", "value": "🔥 現貨可購買！", "inline": True},
            {"name": "售價", "value": price or "請見頁面", "inline": True},
        ],
        "footer": {"text": "Funbox 戰鬥陀螺雷達"},
    }

    payload = {
        "username": "Funbox 戰鬥陀螺雷達",
        "embeds": [embed],
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"成功發送通知：{title} ({notice_type})")
    except Exception as e:
        print(f"發送 Discord 失敗: {e}")


def load_known_products():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {url: False for url in data}
            return data
    except Exception:
        return {}


def save_known_products(products_dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(products_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"寫入快取失敗: {e}")


def check_funbox(known_products, current_round):
    print(f"正在請求目標分類: {TARGET_URL}")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"網頁請求失敗: {e}")
        return

    soup = BeautifulSoup(html, "html.parser")
    found_items = []

    # 1. 檢查是否有 Next.js 的 __NEXT_DATA__
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            data = json.loads(next_data.string)
            print("成功找到 __NEXT_DATA__，正在解析商品...")
            # 遍歷尋找商品清單
            # 通常在 props -> pageProps 內
            page_props = data.get("props", {}).get("pageProps", {})
            products = page_props.get("products") or page_props.get("category", {}).get("products", [])
            for p in products:
                title = p.get("title") or p.get("name")
                handle = p.get("handle") or p.get("_id") or p.get("id")
                price = p.get("price")
                link = f"https://shop.funbox.com.tw/products/{handle}"
                found_items.append((title, link, str(price)))
        except Exception as err:
            print(f"解析 __NEXT_DATA__ 失敗: {err}")

    # 2. 正則比對網頁原始碼中所有 /products/ 連結
    if not found_items:
        print("未在 Next.js 中解析到商品，執行全頁正則掃描...")
        # 尋找所有形如 /products/xxxx 的路徑
        links = set(re.findall(r'href=["\'](/products/[^"\'\?#]+)["\']', html))
        print(f"全頁抓到的 /products/ 路徑數: {len(links)}")
        for l in links:
            found_items.append(("戰鬥陀螺商品", f"https://shop.funbox.com.tw{l}", "詳見官網"))

    # 3. 處理比對與通知
    print(f"本次掃描到有效項目數: {len(found_items)}")
    for title, link, price in found_items:
        current_round[link] = True
        print(f"處理項目: {title} -> {link}")

        if link not in known_products:
            send_discord(title, link, price, notice_type="新品上架")
        else:
            if not known_products.get(link, False):
                send_discord(title, link, price, notice_type="現貨補貨")

    # 4. 若依然為 0，印出頁面中的 script 標籤概況供診斷
    if not found_items:
        scripts = [s.get("id") or s.get("src") or "inline" for s in soup.find_all("script")]
        print("未抓到資料，頁面包含的 Scripts 標籤概況（前 10 個）:")
        print(scripts[:10])


def main():
    known_products = load_known_products()
    current_round = {}

    check_funbox(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("檢查流程結束。")


if __name__ == "__main__":
    main()
