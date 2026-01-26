import requests

resp = requests.get("https://pd.musicapp.migu.cn/MIGUM3.0/v1.0/content/search_all.do?text=青花瓷&pageNo=1&pageSize=1&searchSwitch=%7Bsong%3A1%7D",
    headers={"User-Agent": "okhttp/3.10.0"}, timeout=10)
data = resp.json()
song = data["songResultData"]["result"][0]
cid = song["copyrightId"]
name = song["singers"][0]["name"] + " - " + song["name"]
print(name, cid)

resp2 = requests.get(f"https://c.musicapp.migu.cn/MIGUM2.0/v1.0/content/resourceinfo.do?copyrightId={cid}&resourceType=0",
    headers={"User-Agent": "okhttp/3.10.0"}, timeout=10)
detail = resp2.json()
audio = detail["resource"][0]["audioUrl"]
print("audioUrl:", audio[:80])

from urllib.parse import urlparse, unquote
path = unquote(urlparse(audio).path)
dl_url = f"https://freetyst.nf.migu.cn{path}".replace("彩铃/6_mp3-128kbps", "标清高清/MP3_320_16_Stero")
print("下载URL:", dl_url[:80])

r = requests.head(dl_url, headers={"User-Agent": "okhttp/3.10.0"}, timeout=10)
size = int(r.headers["Content-Length"])
print(f"文件大小: {size/1024/1024:.2f} MB")

print("\n开始下载...")
r3 = requests.get(dl_url, headers={"User-Agent": "okhttp/3.10.0"}, timeout=30, stream=True)
with open(name + ".mp3", "wb") as f:
    for chunk in r3.iter_content(8192):
        f.write(chunk)
print("下载完成:", name + ".mp3")
