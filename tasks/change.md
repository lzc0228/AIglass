# 物体识别增强与编号列表播报格式优化

## Context

根据用户需求和 docx 日志分析，当前系统存在以下问题：
1. **物体识别不全**：YOLOE 白名单仅 31 类，缺少斑马线、红绿灯、室内物品等关键物体
2. **播报内容简单**：只能播报"是否有障碍物"，无法播报具体物体类型
3. **播报格式不符**：用户期望使用编号列表格式（1️⃣12点钟方向1米处为斑马线，现在是绿灯可以通行）
4. **TTS 模型问题**：日志显示 "Piper-TTS 不可用，将仅使用预录音频"

## 实施方案

### Phase 1: 扩展 YOLOE 白名单类别

**文件**: `obstacle_detector_client.py`

将当前 31 类白名单扩展为约 60 类，新增类别包括：

| 类别组 | 新增类别 |
|--------|----------|
| 户外导航 | traffic light, crosswalk, stop sign, parking meter |
| 交通扩展 | taxi, train, police car, ambulance |
| 室内场景 | door, stairs, escalator, elevator, handrail, railing |
| 家居物品 | table, sofa, couch, bed, desk, tv, monitor, laptop |
| 个人物品 | backpack, handbag, suitcase, umbrella, cell phone |

### Phase 2: 添加编号列表播报格式

**文件**: `structured_voice.py`

新增 `render_text_with_numbering()` 方法，实现用户期望的格式：

```
格式：第一、{clock}点方向{distance}处为{name}，{state_description}
       第二、{clock}点方向{distance}处为{name}，{state_description}

示例：
第一、12点方向1米处为斑马线，现在是绿灯可以通行
第二、3点方向2米处有人，注意避让避免碰撞
第三、9点方向3米处为柱子，注意保持距离
```

### Phase 3: 更新中文映射表

**文件**: `semantic_output.py`

在 `NAME_ZH` 字典中添加新类别的中文映射。

### Phase 4: 修复 TTS 配置

确保 Piper TTS 模型路径正确配置。

## 关键文件

| 文件 | 修改内容 |
|------|----------|
| `obstacle_detector_client.py` | 扩展 `WHITELIST_CLASSES` 从 31 类到约 60 类 |
| `structured_voice.py` | 新增 `render_text_with_numbering()` 方法 |
| `semantic_output.py` | 更新 `NAME_ZH` 映射表 |
| `voice/fragments.json` | 添加新物体类别的映射 |

## 验证方案

1. 运行 `python app_main.py` 检查模型加载日志
2. 测试场景：输入包含斑马线/红绿灯的图像，验证能否识别
3. 验证播报格式是否符合用户期望
