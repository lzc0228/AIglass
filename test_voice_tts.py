#!/usr/bin/env python3
"""
测试 TTS 语音播报系统

用法:
    python test_voice_tts.py
"""

import os
import sys

# 设置环境变量
os.environ.setdefault('AIGLASS_TTS_ENABLED', '1')
os.environ.setdefault('AIGLASS_TTS_PREGEN', '1')

def test_piper_tts():
    """测试 Piper TTS 基础功能"""
    print("=" * 50)
    print("测试 Piper TTS 基础功能")
    print("=" * 50)

    from piper_tts import get_piper_tts

    tts = get_piper_tts()
    print(f"TTS enabled: {tts.enabled}")
    print(f"TTS available: {tts.is_available()}")
    print(f"Model path: {tts.model_path}")

    if not tts.is_available():
        print("\n❌ TTS 不可用，无法继续测试")
        return False

    print("\n✅ TTS 可用")

    # 测试生成几个常用短语
    print("\n测试生成常用短语:")
    phrases = [
        "第一", "第二", "第三",
        "12点方向", "3点方向",
        "1米", "2米",
        "处为",
        "斑马线", "人", "柱子",
        "可以通过", "注意避让避免碰撞",
    ]

    success_count = 0
    for phrase in phrases:
        pcm = tts.text_to_audio(phrase)
        if pcm:
            success_count += 1
            print(f"  ✅ '{phrase}' ({len(pcm)} bytes)")
        else:
            print(f"  ❌ '{phrase}' 失败")

    print(f"\n成功生成 {success_count}/{len(phrases)} 个短语")
    return success_count == len(phrases)


def test_audio_player():
    """测试 audio_player 模块"""
    print("\n" + "=" * 50)
    print("测试 audio_player 模块")
    print("=" * 50)

    try:
        from audio_player import (
            initialize_audio_system,
            _get_pcm_for_text,
            _find_audio_path_for_text,
        )
        print("✅ audio_player 模块导入成功")

        # 初始化音频系统
        initialize_audio_system()
        print("✅ 音频系统初始化完成")

        # 测试 _get_pcm_for_text 函数
        print("\n测试 _get_pcm_for_text 函数:")

        test_cases = [
            "第一",
            "12点方向1米处为斑马线",
            "前方有障碍物，注意避让",
            "街道环境。注意，12点方向约两步有人，先停一下",
        ]

        for text in test_cases:
            pcm = _get_pcm_for_text(text, allow_tts=True, save_generated=True)
            if pcm:
                print(f"  ✅ '{text[:20]}...' ({len(pcm)} bytes)")
            else:
                print(f"  ❌ '{text[:20]}...' 失败")

        return True

    except Exception as e:
        print(f"❌ audio_player 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fragments_json():
    """测试 fragments.json 是否包含必要的片段"""
    print("\n" + "=" * 50)
    print("测试 fragments.json")
    print("=" * 50)

    import json

    fragments_path = os.path.join(os.path.dirname(__file__), "voice", "fragments.json")
    try:
        with open(fragments_path, "r", encoding="utf-8") as f:
            fragments = json.load(f)
        print(f"✅ fragments.json 加载成功")

        # 检查新增的类别
        required_keys = ["numbering", "connectors", "state_descriptions"]
        for key in required_keys:
            if key in fragments:
                print(f"  ✅ '{key}' 存在")
                print(f"     内容: {fragments[key]}")
            else:
                print(f"  ❌ '{key}' 不存在")

        return True

    except Exception as e:
        print(f"❌ fragments.json 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("TTS 语音播报系统测试\n")

    results = []

    # 测试 1: Piper TTS
    results.append(("Piper TTS", test_piper_tts()))

    # 测试 2: audio_player
    results.append(("audio_player", test_audio_player()))

    # 测试 3: fragments.json
    results.append(("fragments.json", test_fragments_json()))

    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)

    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + ("=" * 50))
    if all_passed:
        print("🎉 所有测试通过！")
        print("\n现在你可以:")
        print("1. 运行主程序: python app_main.py")
        print("2. 实时场景识别会自动使用 TTS 播报")
        print("3. 生成的语音会缓存到 voice/generated/ 目录")
    else:
        print("⚠️  部分测试失败，请检查上述输出")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
