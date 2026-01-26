#!/usr/bin/env python3
"""测试咪咕音乐下载"""
import requests
import json
from urllib.parse import urlparse, unquote

def test_migu_download():
    # 步骤1: 搜索获取 copyrightId
    search_url = "https://pd.musicapp.migu.cn/MIGUM3.0/v1.0/content/search_all.do?text=青花瓷&pageNo=1&pageSize=1&searchSwitch=%7Bsong%3A1%7D"
    headers = {
        "User-Agent": "okhttp/3.10.0",
        "Referer": "http://music.migu.cn/"
    }

    print("步骤1: 搜索歌曲...")
    resp = requests.get(search_url, headers=headers, timeout=10)
    data = resp.json()

    songs = data.get("songResultData", {}).get("result", [])
    if not songs:
        print("未找到歌曲")
        return

    song = songs[0]
    copyright_id = song.get("copyrightId")
    song_name = song.get("name")
    singer = song.get("singers", [{}])[0].get("name", "")

    print(f"找到歌曲: {singer} - {song_name}")
    print(f"Copyright ID: {copyright_id}")

    # 步骤2: 获取详情获取 audioUrl
    detail_url = f"https://c.musicapp.migu.cn/MIGUM2.0/v1.0/content/resourceinfo.do?copyrightId={copyright_id}&resourceType=0"

    print("\n步骤2: 获取音频URL...")
    resp2 = requests.get(detail_url, headers=headers, timeout=10)
    detail = resp2.json()

    print(f"响应keys: {list(detail.keys())}")
    resource = detail.get("resource", [])
    print(f"resource类型: {type(resource)}, 长度: {len(resource) if resource else 0}")

    if resource:
        print(f"resource[0] keys: {list(resource[0].keys())}")
        audio_url = resource[0].get("audioUrl")
        print(f"\naudioUrl: {audio_url}")

        if audio_url:
            # 步骤3: 构造下载URL
            parsed = urlparse(audio_url)
            pathname = unquote(parsed.path)

            download_url = f"https://freetyst.nf.migu.cn{pathname}".replace(
                "彩铃/6_mp3-128kbps",
                "标清高清/MP3_320_16_Stero"
            )
            print(f"\n下载URL: {download_url}")

            # 步骤4: 获取文件大小
            print("\n步骤3: 测试下载...")
            try:
                head_resp = requests.head(download_url, headers=headers, timeout=10)
                size = int(head_resp.headers.get("Content-Length", 0))
                print(f"文件大小: {size / 1024 / 1024:.2f} MB")

                # 尝试下载前100字节
                range_resp = requests.get(download_url, headers={"Range": "bytes=0-99"}, timeout=10)
                print(f"下载测试: 成功获取 {len(range_resp.content)} 字节")
                print(f"Content-Type: {range_resp.headers.get('Content-Type')}")

                # 步骤5: 下载完整文件
                print("\n步骤4: 开始下载...")
                full_resp = requests.get(download_url, headers=headers, timeout=30, stream=True)
                total_size = int(full_resp.headers.get("Content-Length", 0))

                filename = f"{singer} - {song_name}.mp3"
                downloaded = 0

                with open(filename, "wb") as f:
                    for chunk in full_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            percent = (downloaded / total_size) * 100 if total_size else 0
                            print(f"\r下载进度: {percent:.1f}%", end="")

                print(f"\n下载完成: {filename}")
                import os
                file_size = os.path.getsize(filename)
                print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")

            except Exception as e:
                print(f"\n下载失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("未获取到audioUrl")
    else:
        print("resource为空")
        print(f"完整响应: {json.dumps(detail, ensure_ascii=False, indent=2)[:1000]}")

if __name__ == "__main__":
    test_migu_download()
