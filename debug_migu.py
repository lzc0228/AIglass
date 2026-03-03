import requests
import json

# 先搜索获取 copyrightId
search_url = "https://pd.musicapp.migu.cn/MIGUM3.0/v1.0/content/search_all.do?text=青花瓷&pageNo=1&pageSize=1&searchSwitch=%7Bsong%3A1%7D"
headers = {"User-Agent": "okhttp/3.10.0", "Referer": "http://music.migu.cn/"}

resp = requests.get(search_url, headers=headers, timeout=10)
data = resp.json()
song = data["songResultData"]["result"][0]
copyright_id = song["copyrightId"]
print(f"Copyright ID: {copyright_id}")

# 获取详情
detail_url = f"https://c.musicapp.migu.cn/MIGUM2.0/v1.0/content/resourceinfo.do?copyrightId={copyright_id}&resourceType=0"
resp2 = requests.get(detail_url, headers=headers, timeout=10)
detail = resp2.json()

print("\n详情API返回结构:")
print(json.dumps(detail, ensure_ascii=False, indent=2)[:3000])

print("\nresource字段:")
if "resource" in detail:
    print(json.dumps(detail["resource"], ensure_ascii=False, indent=2)[:2000])
else:
    print("没有resource字段")

# 尝试其他可能的字段
print("\n所有keys:", list(detail.keys()))
