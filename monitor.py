import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

# --- 基本設定區 ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# Funbox 官網戰鬥陀螺分類
FUNBOX_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade"

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def send_discord(title, link, price, source_name="Funbox 官網", notice_type="新品上架"):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return

    color = 3066993 if notice_type == "現貨補貨" else 15844367

    embed = {
        "title": f"【{source_name} - {notice_type}】{title}",
        "url": link,
        "color": color,
        "fields": [
            {"name": "狀態", "value": "🔥 現貨可購買！", "inline": True},
            {"name": "售價", "value": price or "請見頁面", "inline": True},
        ],
        "footer": {"text": f"{source_name} 自動監控通知"},
    }

    payload = {
        "username": "Funbox 戰鬥陀螺雷達",
        "embeds": [embed],
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"成功發送通知 [{source_name}]：{title} ({notice_type})")
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


def check_official(known_products, current_round):
    print("正在巡邏 Funbox 官網...")
    try:
        resp = requests.get(FUNBOX_URL, headers=COMMON_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"官網請求失敗: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 擴大搜尋所有連往商品頁的 a 標籤
    product_links = soup.find_all("a", href=re.compile(r"/(products|SalePage)/"))
    print(f"官網找到相關商品連結數: {len(product_links)}")

    found_links = set()
    for link_elem in product_links:
        raw_link = link_elem.get("href", "")
        if not raw_link:
            continue

        link = raw_link if raw_link.startswith("http") else f"https://shop.funbox.com.tw{raw_link}"
        link = link.split("?")[0]

        if link in found_links:
            continue
        found_links.add(link)

        # 向上尋找最接近的容器卡片以取得價格與標題
        card = link_elem.find_parent("li") or link_elem.find_parent("div") or link_elem
        text = card.get_text(separator=" ", strip=True)

        title = link_elem.get_text(strip=True) or card.get_text(strip=True)[:30]
        # 過濾純圖片或無文字情況
        if not title or len(title) < 2:
            continue

        price_match = re.search(r"NT\$\s*[\d,]+", text)
        price = price_match.group(0) if price_match else ""

        is_sold_out = any(k in text for k in ["售完", "補貨中", "缺貨", "售罄", "Sold Out"])
        has_stock = not is_sold_out

        print(f"發現商品: {title} | 現貨: {has_stock} | 連結: {link}")
        current_round[link] = has_stock

        if link not in known_products:
            if has_stock:
                send_discord(title, link, price, source_name="Funbox 官網", notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(title, link, price, source_name="Funbox 官網", notice_type="現貨補貨")


def main():
    known_products = load_known_products()
    current_round = {}

    check_official(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("全部監控檢查完成，資料庫已更新。")


if __name__ == "__main__":
    main()
