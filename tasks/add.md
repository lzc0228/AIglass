# 语音播报系统优化实施计划（更新版）

## 一、核心需求（重点）

### 1.1 全场景覆盖
尽可能覆盖视障用户可能遇到的所有常见场景，不仅限于医院/超市/商场：
- **交通场景**：街道、人行道、十字路口、斑马线、红绿灯、公交站、地铁站
- **建筑场景**：医院、超市、商场、办公楼、学校、银行、餐厅
- **室内场景**：电梯、楼梯、走廊、大厅、房间、卫生间
- **自然环境**：公园、广场、草坪、花坛、水池
- **特殊场景**：施工区域、地下通道、天桥、停车场

### 1.2 主动场景播报
**接收到实时图像后，系统必须主动识别并播报场景信息**：
- 不是被动等待用户询问
- 每次场景变化时主动播报
- 检测到危险时立即播报
- 定期（如3-5秒）更新环境描述

### 1.3 结构化语音输出（重点！！！）
**所有语音播报必须遵循统一的格式**：
```
[场景前缀] + [方向] + [距离] + [物体] + [危险等级] + [行动建议]
```

示例：
- "医院环境，左前方约3步有人，请注意"
- "注意，3点方向2米有汽车靠近，先停一下"
- "超市通道，右侧5米有货架，保持直行"

---

## 二、全场景分类体系

### 2.1 交通场景
| 场景 | 典型物体 | 播报重点 |
|------|----------|----------|
| 街道 | car/bus/truck/bicycle | 车辆方向和距离 |
| 人行道 | person/bench/pole | 行人和固定障碍 |
| 十字路口 | traffic light/crosswalk | 红绿灯状态 |
| 公交站 | bus stop/sign | 公交车信息 |
| 地铁站 | elevator/turnstile/ticket gate | 闸机和电梯位置 |

### 2.2 建筑场景
| 场景 | 典型物体 | 播报重点 |
|------|----------|----------|
| 医院 | doctor/nurse/wheelchair/bed | 医疗人员位置 |
| 超市 | shelf/cart/checkout | 货架和通道 |
| 商场 | escalator/elevator/mannequin | 扶梯和电梯 |
| 餐厅 | table/chair/counter | 座位和收银台 |
| 银行 | counter/atm/queue | 柜台和ATM |

### 2.3 室内场景
| 场景 | 典型物体 | 播报重点 |
|------|----------|----------|
| 电梯 | button/panel | 楼层和按钮 |
| 楼梯 | stair/handrail | 阶数和扶手 |
| 走廊 | door/sign | 房间和标识 |
| 卫生间 | sink/toilet/mirror | 设施位置 |

### 2.4 危险场景
| 场景 | 典型物体 | 播报策略 |
|------|----------|----------|
| 施工区域 | cone/barrier/fence | 立即警告 |
| 地下通道 | dark/stairs | 环境和照明 |
| 停车场 | car/pole | 车辆位置 |

---

## 三、结构化语音输出格式（核心）

### 3.1 输出数据结构
```python
{
    "schema_version": 2,
    "timestamp": 1234567890.123,
    "scene": "hospital",           # 场景类型
    "scene_confidence": 0.85,      # 场景置信度

    # 检测到的物体列表
    "objects": [
        {
            "id": 1,
            "name": "person",
            "name_zh": "人",

            # 方向信息（两种表示）
            "direction": {
                "clock": 11,           # 钟点方向 (1-12)
                "clock_zh": "左前方",   # 中文描述
                "lr": "left",          # 左中右 (left/center/right)
                "lr_zh": "左侧"
            },

            # 距离信息（两种表示）
            "distance": {
                "meters": 1.8,         # 米
                "steps": 3             # 步数
            },

            # 危险评估
            "urgency": "MEDIUM",       # HIGH/MEDIUM/LOW
            "is_moving": false,       # 是否移动
            "is_approaching": false,  # 是否靠近

            # 行动建议
            "action": "从右侧绕开",
            "action_type": "avoid"    # avoid/stop/continue
        }
    ],

    # 自然语言描述
    "text": "医院环境，左前方约3步有人，从右侧绕开",

    # 是否应该播报
    "should_speak": true,
    "priority": 50                   # 播报优先级
}
```

### 3.2 播报模板

#### 危险场景（HIGH优先级）
```
"紧急，{clock}点方向{distance}有{object}，先停下"
"注意，{direction}{distance}有{object}靠近"
"危险，前方{distance}有{object}"
```

#### 一般障碍（MEDIUM优先级）
```
"{scene}，{direction}{distance}有{object}，{action}"
"{clock}点方向{distance}有{object}，{action}"
"注意{direction}{distance}有{object}"
```

#### 安全环境（LOW优先级）
```
"{scene}，{direction}{distance}有{object}"
"前方{direction}{distance}是{object}"
```

---

## 四、主动播报机制（新增重点）

### 4.1 触发条件
系统在以下情况必须主动播报：

| 触发条件 | 播报策略 | 优先级 |
|----------|----------|--------|
| 场景发生变化 | 播报新场景类型 + 典型物体 | 中 |
| 检测到危险物体 | 立即播报危险信息 | 高 |
| 物体快速靠近 | 播报方向和避让建议 | 高 |
| 用户转向后 | 更新环境描述 | 中 |
| 定时更新（3-5秒） | 简要环境概述 | 低 |

### 4.2 播报频率控制
- **危险场景**：立即播报，不节流
- **场景切换**：切换后立即播报一次
- **环境更新**：每3-5秒更新一次
- **相同内容**：10秒内不重复播报

### 4.3 实现方式
在 `app_main.py` 的摄像头帧处理循环中：
```python
async def ws_camera_esp(websocket: WebSocket):
    last_scene = None
    last_announce_time = 0

    while True:
        # ... 接收图像 ...

        # 主动场景检测和播报
        current_time = time.time()

        # 1. 场景变化检测
        current_scene = detect_scene(frame)
        if current_scene != last_scene:
            announce_scene_change(current_scene)
            last_scene = current_scene

        # 2. 危险检测（立即播报）
        if has_hazard(frame):
            announce_hazard(frame)
            continue

        # 3. 定期环境更新
        if current_time - last_announce_time > 3.0:
            announce_environment(frame)
            last_announce_time = current_time
```

---

## 五、关键文件修改

### 5.1 新增文件
| 文件 | 说明 |
|------|------|
| `structured_voice.py` | 结构化语音核心模块 |
| `voice/fragments.json` | 语音片段映射 |
| `voice/templates.json` | 播报模板配置 |
| `context/weights/scene_*.txt` | 各场景权重文件（10+个） |

### 5.2 修改文件
| 文件 | 修改内容 |
|------|----------|
| `semantic_output.py` | 全场景识别、结构化输出、模板渲染 |
| `audio_player.py` | 结构化播放、延迟优化 |
| `piper_tts.py` | 预热、缓存 |
| `app_main.py` | **主动播报逻辑**（重点） |

---

## 六、语音片段清单（扩展）

### 方向片段（15个）
- 钟点：1点方向 ~ 12点方向
- 左中右：左侧、前方、右侧
- 组合：左前方、右前方等

### 距离片段（20个）
- 米：1米 ~ 10米
- 步：一步 ~ 十步
- 模糊：几米、几步、近距离、远距离

### 物体片段（50+个）
- 人物：人、医生、护士、小孩、老人
- 交通：汽车、公交车、自行车、电动车
- 固定：杆子、柱子、楼梯、电梯、门、窗
- 场所：货架、柜台、桌子、椅子

### 场景前缀（15个）
- 街道环境、医院环境、超市通道、商场内
- 电梯里、楼梯上、人行道、公交站
- 公园里、广场上、施工区域

### 行动建议（10个）
- 先停一下、从左侧绕开、从右侧绕开
- 保持直行、左转一点、右转一点
- 注意脚下、小心头顶

### 危险播报（8个）
- 紧急、危险、注意、警告
- 有障碍物、有车辆靠近、小心

---

## 七、实施步骤

### Phase 1: 结构化输出框架（最高优先级）
1. 创建 `structured_voice.py` 核心模块
2. 定义完整的结构化输出格式
3. 创建语音片段映射和模板

### Phase 2: 全场景识别（最高优先级）
1. 扩展 `semantic_output.py` 场景类型（10+场景）
2. 为每个场景创建权重文件
3. 实现场景变化检测

### Phase 3: 主动播报机制（最高优先级）
1. 修改 `app_main.py` 添加主动播报逻辑
2. 实现场景变化播报
3. 实现危险检测和立即播报
4. 实现定期环境更新

### Phase 4: 音频优化（高优先级）
1. TTS预热和缓存
2. 减少静音填充延迟
3. 支持序列播放

### Phase 5: 语料库扩展（中优先级）
1. 生成/录制语音片段
2. 更新映射文件
3. 预加载测试

---

## 八、验证方案

| 场景类型 | 检测物体 | 预期播报 |
|----------|----------|----------|
| 街道+车靠近 | car@3点@2米 | "注意，3点方向2米有汽车靠近，先停一下" |
| 医院+人员 | person@左前@3步 | "医院环境，左前方约3步有人" |
| 超市+货架 | shelf@右侧@5米 | "超市通道，右侧5米有货架" |
| 电梯 | elevator@正前@1米 | "前方1米是电梯" |
| 楼梯 | stairs@正前@2米 | "前方2米有楼梯，注意脚下" |
| 施工区域 | cone@3点@3米 | "危险，3点方向3米有施工区域，请注意" |
