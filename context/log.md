# 对话记录总结（环境与项目梳理）

日期：2026-01-21  
仓库：`/data0/home/scli/Codes/OpenAIglasses_for_Navigation-main`

## 1) 本轮目标

1. 先理清项目结构与关键入口。
2. 依据 `tasks/` 文档中的“可开工/可运行”要求，对项目做必要更新（偏工程可落地、避免大重构）。
3. 把运行环境（conda 虚拟环境 + .env + 模型文件）先“跑通”到可启动状态。

## 2) 项目结构梳理（关键模块/入口）

- 主入口：`app_main.py`
  - FastAPI 服务 + WebSocket 路由
  - 负责：视频/音频接入、前端 UI 推送、ASR 回调、状态机调度、各工作流装配
  - 主要 WS 端点：`/ws_ui`、`/ws_audio`、`/ws/camera`、`/ws/viewer`、`/ws`、`/ws/cmd`
- 全局统领/状态机：`navigation_master.py`
  - 状态常量：`IDLE/CHAT/BLINDPATH_NAV/SEEKING_CROSSWALK/WAIT_TRAFFIC_LIGHT/CROSSING/SEEKING_NEXT_BLINDPATH/RECOVERY/TRAFFIC_LIGHT_DETECTION/ITEM_SEARCH`
  - `process_frame()`：根据状态调用盲道/过马路等工作流，并输出引导文本（由上层统一播报/广播）
- 三大业务工作流：
  - `workflow_blindpath.py`：盲道导航（分割、跟随、避障、光流稳定等）
  - `workflow_crossstreet.py`：过马路（斑马线检测/对齐/通行流程）
  - `yolomedia.py`：找物品（YOLOE 文本提示 + 手部检测 + 跟踪/引导）
- 语音/音频链路：
  - `asr_core.py`：DashScope Paraformer 实时 ASR 回调，热词中断、节流/复位
  - `audio_stream.py`：音频流分发（`/stream.wav` 等）
  - `audio_player.py`：统一音频播放接口（避免到处 print/播放），支持 voice 映射与预加载
- 多模态对话：
  - `omni_client.py`：DashScope OpenAI-compatible 的 Qwen-Omni 流式输出（text/audio）
  - `qwen_extractor.py`：中文物品名 -> 英文检测类名（本地映射优先、可回退到 Qwen Turbo）

## 3) 读取到的任务/约束（来自 `tasks/执行文档.md` 等）

- 不做大规模重构：优先“局部可回滚的小改动”。
- 不破坏现有状态机：新增状态要有退出路径、默认回到 `CHAT`。
- 所有新输出走统一播报接口（避免到处 print）。
- 调试需可复现：给出“输入→状态→输出”的路径。

## 4) 本轮关键决策（为什么这么改）

1. **可运行性优先**：先把“密钥/路径/依赖/环境”这些阻塞项处理掉，让项目能在不同机器上启动。
2. **最小改动原则**：不重排工程结构、不重写状态机；仅修复明显不一致（硬编码 Key、绝对路径、语法错误、资源路径不匹配）。
3. **跨环境可移植**：把所有模型/资源默认路径改为“仓库内相对路径”，同时保留环境变量覆盖。
4. **权限问题绕开**：Ultralytics 默认写 `~/.config/Ultralytics/settings.json` 在当前环境会报权限错误，因此统一把配置写到仓库内 `.ultralytics/`。

## 4.1) 关键假设（本轮默认成立的前提）

1. **运行环境**：优先使用用户指定的 conda 环境 `openai_glasses`（Python 3.9），且该环境具备本项目依赖（已做 import 验证）。
2. **模型权重**：默认权重都在仓库 `model/` 下；若用户自定义路径，可用 `.env` 里的 `*_MODEL` 环境变量覆盖。
3. **外部服务**：ASR/Qwen 相关功能需要 DashScope 可用的 `DASHSCOPE_API_KEY`，且运行机器能访问 DashScope 兼容端点（网络可达）。
4. **权限限制**：当前环境对 `~/.config` 等目录写入可能受限，因此将 Ultralytics 配置落到仓库目录以规避。

## 5) 已实施的改动（代码/配置）

### 5.1 配置文件

- 新增 `/.env.example`：提供环境变量模板（不含真实 key）。
- 生成并更新 `/.env`：填入默认模型/音频目录配置，但 **`DASHSCOPE_API_KEY` 仍为占位符**（需要用户补全）。
- 新增 `/.gitignore`：忽略 `.env` 与 `.ultralytics/`（避免把本地密钥/运行时配置提交到 git）。

### 5.2 移除硬编码密钥（DashScope）

目的：避免代码内写死 key、对齐 `tasks/执行文档.md` 的“用 `.env`/环境变量”方式。

- `app_main.py`：`API_KEY` 改为只读 `DASHSCOPE_API_KEY`，缺失则直接报错提示。
- `omni_client.py`：同上。
- `qwen_extractor.py`：创建 OpenAI client 时从 `DASHSCOPE_API_KEY` 读取，缺失则抛错。
- `qwenturbo_template.py`：示例脚本改为从环境变量读取（默认 `sk-xxx` 占位）。

### 5.3 修复绝对路径（/home/lsc 等）

目的：保证仓库在任意路径部署都能跑。

- `app_main.py`：`BLIND_PATH_MODEL`、`OBSTACLE_MODEL` 默认改为 `./model/...`（支持环境变量覆盖）。
- `trafficlight_detection.py`：`TRAFFIC_LIGHT_MODEL` 默认改为 `./model/trafficlight.pt`。
- `yolomedia.py`：`ITEM_SEARCH_MODEL`、`HAND_LANDMARKER_TASK` 默认改为 `./model/...`。
- `yoloe_backend.py`：`YOLOE_MODEL_PATH` 默认改为 `./model/yoloe-11l-seg.pt`，并支持 `AIGLASS_DEVICE`/无 CUDA 回退 CPU。
- `audio_player.py`：音频目录默认改为 `./music`；并把 `AUDIO_MAP` 指向仓库中真实存在的 `converted_*.wav` 文件，避免大小写/文件名不匹配。

### 5.4 修复一个会阻塞启动的语法错误

- `app_main.py`：`start_ai_with_text_custom()` 中 `global night_detector` 声明位置不正确导致 `SyntaxError`，已修复（统一在函数顶部声明）。

### 5.5 Ultralytics 权限问题修复

现象：在 conda 环境导入 `ultralytics` 时，尝试写 `~/.config/Ultralytics/settings.json`，报 `Permission denied`。

处理：
- 在以下文件中设置 `YOLO_CONFIG_DIR=<repo>/.ultralytics` 并确保目录可创建：
  - `app_main.py`
  - `obstacle_detector_client.py`
  - `models.py`
  - `trafficlight_detection.py`
  - `yoloe_backend.py`
  - `yolomedia.py`
- 并在 `.gitignore` 忽略 `.ultralytics/`。

备注：这能避免在受限环境下写用户目录失败，且不影响模型推理逻辑。

### 5.6 `yolomedia.py` 的本地音频依赖处理

目的：避免在无音频设备/服务端环境下因 `pygame.mixer.init()` 直接崩溃。

- `pygame` 改为可选导入；且仅在 `AIGLASS_ENABLE_LOCAL_AUDIO=1` 时尝试初始化。
- 默认流程仍走 `audio_player.play_audio_threadsafe()` 的统一播放链路。

### 5.7 文档对齐

- `README.md`：修正 clone/cd 示例（不再写 `rebuild1002`），并移除“改代码写 API_KEY”的做法，改为复制 `.env.example`。

## 6) 环境现状（Conda）

用户指定 conda 环境：

- 环境名：`openai_glasses`
- 路径：`/data0/home/scli/conda/envs/openai_glasses`
- Python：3.9.25

验证结果（在该环境内）：

- 关键依赖可 import：`fastapi`、`uvicorn`、`cv2`、`torch`、`ultralytics`、`mediapipe`、`dashscope`、`openai`、`python-dotenv` 等均 OK。
- Ultralytics 的默认写配置路径会触发权限错误（已通过 `YOLO_CONFIG_DIR` 绕开）。

额外发现：

- `conda env list` 在当前运行环境下会报 `PermissionError`/`KeyError`（疑似 conda 插件在探测 CUDA 虚拟包时触发 IPC/信号量权限问题），因此**不建议依赖 conda CLI 列表命令**；直接用环境路径激活/调用更稳。

## 7) 模型文件检查结果（model/ 是否齐全）

已检查 `model/` 必需权重均存在：

- `yolo-seg.pt`（盲道/斑马线分割）
- `yoloe-11l-seg.pt`（开放词汇检测/分割）
- `shoppingbest5.pt`（物品识别）
- `trafficlight.pt`（红绿灯检测）
- `hand_landmarker.task`（MediaPipe 手部）

结论：模型侧目前不阻塞启动。

## 8) 未解决问题 / 风险点

1. **DashScope Key 未配置**：`/.env` 中 `DASHSCOPE_API_KEY` 仍是占位符，需要用户填入真实 key 才能使用 ASR/Qwen。
2. **网络连通性未知**：DashScope 调用需要外网/对应域名可达；当前未实际跑通 ASR/Omni 请求链路。
3. **conda 命令异常**：`conda env list` 报错未修复（但不影响直接使用指定 env 路径跑程序）。
4. **`models.py` 可能存在历史遗留依赖**：文件里引用 `app.cloud.*`（仓库里不一定存在），当前看起来可能未被主流程使用；建议后续确认是否死代码/需清理（本轮遵循“避免大重构”，未动它的结构性问题）。
5. **音频设备与系统依赖**：`pyaudio`/`pygame` 在不同机器上可能依赖系统库（portaudio 等）；当前环境 import OK，但实际播放/采集仍需运行时验证。

## 9) 下一步行动（建议按顺序）

1. **填好 `.env`**
   - 编辑 `/.env`：把 `DASHSCOPE_API_KEY=your_api_key_here` 替换为真实 key。
2. **进入 conda 环境并启动**
   - 推荐（正常激活）：
     - `source /data0/home/scli/miniconda3/etc/profile.d/conda.sh`
     - `conda activate /data0/home/scli/conda/envs/openai_glasses`
     - `cd /data0/home/scli/Codes/OpenAIglasses_for_Navigation-main`
     - `python app_main.py`
   - 备选（不依赖 conda activate，直接用 env python）：
     - `/data0/home/scli/conda/envs/openai_glasses/bin/python app_main.py`
3. **基础验证**
   - 浏览器打开 `http://localhost:8081`，确认前端页面/WS 能连接。
4. **设备联调（如有 ESP32）**
   - 摄像头：连 `/ws/camera`，浏览器订阅 `/ws/viewer`
   - 音频：连 `/ws_audio`
5. **语音指令回归**
   - “开始导航/盲道导航”
   - “开始过马路/帮我过马路”
   - “检测红绿灯/看红绿灯”
   - “帮我找一下XXX”

---

# 追加记录：全量对照 tasks/ 的实现要求

日期：2026-01-21（同日追加）

## A) 用户在本次对话中的新增/强化需求

1. **环境优先**：先把 `.env` “填好”，并确认 `model/` 权重齐全，确保能在指定 conda 环境里稳定启动。
2. **必须激活 conda 虚拟环境**：
   - 环境：`openai_glasses`
   - 路径：`/data0/home/scli/conda/envs/openai_glasses`
3. **全面对照 `tasks/` 并实现全部内容**：不仅是“跑通工程”，还要把 `tasks/` 文档中提到的功能与模块逐项落地实现。
4. **持续记录**：要求把本次对话的重要内容继续追加到 `context/log.md`，包含决策、假设、未解决问题、下一步行动（要求详细）。

## B) 面向 “实现 tasks/ 全量内容” 的当前判断（阶段划分）

> 说明：`tasks/` 内包含两类内容：  
> - **工程可验收功能项**（能在产品里直接用/可演示）  
> - **论文/研究式的 WP 模块设计**（更偏架构与算法模块，需要定义“最小可用实现”的验收口径）

为避免偏离 `tasks/执行文档.md` 的“避免大重构”原则，阶段建议（尚未执行）：

1. **P0：补齐缺失的可验收功能**（在现有状态机/WS/播报框架内增量实现）
2. **P1：按 `tasks/项目综合文档.md` 落地 WP 模块的“最小可用实现”**（先实现接口/数据流/可观测输出，再迭代算法质量）
3. **P2：整合输出与调度**（统一 JSON/去重/优先级调度/稳定模板），但保持对现有工作流侵入最小

## C) 本阶段的关键决策（新增）

1. **运行方式决策**：优先用指定 conda 环境的 Python 解释器运行与验证：
   - 直接运行：`/data0/home/scli/conda/envs/openai_glasses/bin/python app_main.py`
   - 或激活后运行（若 conda CLI 可用）：`conda activate /data0/home/scli/conda/envs/openai_glasses`
   - 理由：当前环境 `conda env list` 等命令存在异常，直接用解释器路径更稳定。
2. **“实现 tasks/” 的落地口径决策（默认口径）**：
   - 对功能类条目：以“可运行 + 可通过指令触发 + 有 UI 文本 + 有语音播报 + 有退出/回退路径”为验收。
   - 对 WP/研究类条目：先实现“模块接口 + 数据结构 + 端到端串联 + 可观测输出（日志/JSON）”，再做性能/效果迭代。
3. **实现策略决策**：严格遵守 `tasks/执行文档.md` 约束：
   - 不大重构、不破坏状态机；所有新增状态必须有退出路径且可回到 `CHAT`。
   - UI 文本统一走 `ui_broadcast_final()`，并用 `[AI]` / `[导航]` 前缀区分。
   - 语音统一走 `audio_player.play_voice_text()` / `play_audio_threadsafe()`，避免散落的 `print`/直接播放。

## D) 假设（新增/强化）

1. **用户会提供可用的 `DASHSCOPE_API_KEY`**：否则 ASR/Qwen 相关条目无法端到端验收（目前 `.env` 仍是占位符）。
2. **运行机器具备摄像头/音频设备或替代输入**：部分功能（如人脸、关灯提醒、盲道/过街）高度依赖实时视频流。
3. **不新增需要联网安装的大依赖**：默认在现有 conda env 依赖范围内实现；如必须新增依赖，需要用户确认并允许联网/安装。
4. **模型文件以仓库 `model/` 为准**：后续如要升级/替换权重，优先通过环境变量覆盖路径而非改代码。

## E) 未解决问题（新增）

1. **“全面实现 tasks/项目综合文档.md” 的验收定义**：
   - WP1/WP2/WP3/WP4 的描述包含研究性指标与模块设计，需要确认：
     - 是否要求达到论文级指标/还是仅实现模块与数据流？
     - 是否需要离线数据集评估脚本/可视化报告？
2. **两项功能缺口（来自仓库现状文档 `功能实现状态文档.md`）**：
   - 识别朋友/人脸分析：目前未发现完整可用实现（需新增本地人脸登记与识别流程）。
   - 灯光关闭提醒：目前未发现完整可用实现（需新增亮度/灯源检测与提醒策略）。
3. **输出与调度一致性**：
   - 目前部分模块仍可能绕过统一的“输出/播报调度”直接播报；需要对照 `tasks/执行文档.md` 进一步收口。
4. **网络与外部服务可用性**：
   - DashScope/Omni 的实际调用链路尚未在本机端到端验证（需要真实 key + 网络可达）。

## F) 下一步行动（新增，面向“实现 tasks/ 全量”）

1. **逐条拆解 `tasks/执行文档.md` 与 `tasks/项目综合文档.md`**  
   - 产出：可执行 checklist（每条对应代码入口/触发方式/验收方式/输出示例）。
2. **先补齐缺失的两项功能（P0）**
   - 人脸/朋友识别：新增“登记→识别→询问/播报”闭环；本地存储人脸库；指令入口对齐现有 ASR/命令系统。
   - 关灯提醒：新增亮度检测与稳定策略（阈值 + 滞回 + 置信度）；提供“检查灯/提醒关灯”等指令入口，并可选自动触发。
3. **落地 WP 模块的最小实现（P1）**
   - 输出生成模块：把检测结果转换为结构化信息（方向/距离/关系/规避建议），再经模板生成 `[导航]` 文本。
   - JSON 流优化/去重：跨工作流合并输出，避免重复播报，保证“重要信息优先”。
   - 场景推断+权重：用轻量规则或权重表对检测结果重排，提升信息密度与相关性。
   - IMU 闭环：利用已有 IMU/yaw 信息抑制重复转向提示，提升稳定性。
4. **验证**
   - 用 conda 环境跑 `python app_main.py`，完成“启动→WS 连接→基本指令触发”回归。
   - 更新 `功能实现状态文档.md`：把每一条 tasks 的实现状态与入口写清楚（便于验收）。

---

# 追加记录：本轮实现进展（功能补齐 + WP 最小实现落地）

日期：2026-01-21（实现完成后追加）

## 1) 已完成事项（对照 tasks/ 与 12 条用户需求）

### 1.1 缺失功能补齐（P0 功能清单）

- ✅ **识别朋友/人脸分析**：新增本地人脸库与识别闭环
  - 新增文件：`face_friend_recognition.py`
  - 指令入口（`app_main.py:start_ai_with_text_custom()`）：
    - 识别：`这是谁` / `谁在我面前`
    - 录入：`这是张三` / `这是张三，男，30岁`
    - 管理：`朋友列表` / `我认识谁` / `忘记张三`
  - 数据落盘：`context/faces/`（已加入 `.gitignore`，避免提交隐私数据）
- ✅ **灯光关闭提醒**：新增启发式检测与提醒闭环
  - 新增文件：`light_reminder.py`
  - 指令入口：
    - 一次性检查：`灯关了吗` / `检查灯有没有关`
    - 常驻提醒：`提醒我关灯` / `开启关灯提醒` / `关闭关灯提醒`
  - 策略：仅在 `CHAT/IDLE`（非导航）时执行常驻提醒，避免打断导航播报；带冷却时间防刷屏

### 1.2 WP1/WP2/WP3/WP4（最小可用实现）

- ✅ **输出生成模块（WP1）**：从检测结果生成 Top-3 关键物体的结构化中间表示与自然语言提示
  - 新增文件：`semantic_output.py`
  - 输出字段：`clock_dir`、`distance_m`、`relations`、`avoidance_action`、`urgency`
  - 动态/稳定自适应：动态场景更短、稳定场景更完整
- ✅ **JSON Stream Optimizer（WP2）**：
  - 同类 IoU 去冗余（避免重复框/覆盖）
  - 基于签名的去重复播报（节流）
- ✅ **场景推断 + 权重表（WP3）**：
  - 新增权重表：`context/weights/task_navigation.txt`、`context/weights/scene_street.txt`、`context/weights/scene_indoor.txt`
  - 用户偏好：`context/user_prefs.json`
  - 支持指令：`重新加载语义权重`
- ✅ **IMU 闭环稳定（WP4）**：
  - 在 `app_main.py` 抽取 `latest_yaw_deg/latest_yaw_rate_dps` 快照
  - 语义输出在转头/转身时抑制冗余播报（除非紧急项），并输出 `jump_count` 指标

## 2) 关键决策（实现期新增）

1. **人脸识别离线优先**：使用 OpenCV Haar + LBPH 实现“可运行、可录入、可识别”的本地闭环；性别/年龄采用“录入时提供的元数据”，避免不可靠猜测误导用户。
2. **关灯提醒先做启发式**：采用“局部高亮 + 整体亮度 + 滞回 + 冷却”的轻量方案，先满足“可用/可演示/可调参”，后续再考虑专用灯具检测模型。
3. **WP 模块先把数据流跑通**：语义输出先完成结构化 JSON + 生成文本 + 去冗余 + 权重可配置 + IMU 抑制跳变，为后续算法/论文指标迭代留接口。
4. **回放/评估优先可观测性**：新增 JSONL 事件记录器 `event_logger.py`，把 UI final 与语义输出 payload 记录到 `recordings/events_*.jsonl`（`recordings/` 已加入 `.gitignore`）。

## 3) 假设（实现期新增/强化）

1. 当前 conda 环境的 OpenCV 包含 `cv2.face`（已验证），因此 LBPH 可用。
2. 摄像头画面可获取到清晰人脸与室内灯光；否则对应功能会提示“暂无画面/请对准镜头”。
3. 语义输出的距离为启发式估计（基于 bbox 面积），只用于“可执行提示”的粗略参考。

## 4) 未解决问题 / 后续优化点

1. **更高质量的性别/年龄**：如需自动推断，可引入专用模型或在非安全关键场景下可选调用多模态云模型（需额外依赖/网络与验收口径确认）。
2. **更强的场景推断**：当前 scene inference 为轻量规则，后续可用更完整的 prompt 列表与空间分布特征做鲁棒分类。
3. **全局语音调度统一**：目前语义输出/关灯/人脸等新增内容已走统一 UI+TTS，但部分历史工作流仍存在“内部直接播报”的路径，后续可逐步与 `voice_scheduler.py` 收口（需谨慎避免影响稳定性）。

## 5) 下一步行动（建议）

1. 在 conda 环境启动并实测新指令（人脸录入/识别、关灯提醒、场景探索），确认 UI 与语音都正常。
2. 根据实际场景调参：
   - `AIGLASS_FACE_MATCH_THRESHOLD`
   - `AIGLASS_LIGHT_*` 阈值
   - `AIGLASS_SEM_*`（周期、去重、转头阈值）
3. 结合真实用户/场景，迭代 `context/weights/*.txt` 与 `context/user_prefs.json`，产出可对标 WorldScribe 的示例样例集。

---

# 最终补充：本次对话“交付物”与今日日志总览

日期：2026-01-21（对话结束前补充）

## 1) 本次对话交付物（最终清单）

### 1.1 新增/更新的核心功能

1. **朋友/人脸识别（本地离线）**
   - 新增：`face_friend_recognition.py`
   - 入口：`app_main.py:start_ai_with_text_custom()`
   - 数据目录：`context/faces/`（包含 `db.json`、`images/*.png`、`lbph.yml`；已 `gitignore`）
   - 主要指令：
     - 识别：`这是谁` / `谁在我面前`
     - 录入：`这是张三` / `这是张三，男，30岁`
     - 列表：`朋友列表` / `我认识谁`
     - 删除：`忘记张三` / `删除张三`

2. **灯光关闭提醒（启发式）**
   - 新增：`light_reminder.py`
   - 入口：`app_main.py:start_ai_with_text_custom()` + 摄像头帧循环常驻检测（仅启用时）
   - 主要指令：
     - 一次性检查：`灯关了吗` / `检查灯有没有关`
     - 常驻提醒：`提醒我关灯` / `开启关灯提醒`
     - 关闭：`关闭关灯提醒` / `停止关灯提醒`
   - 约束：常驻提醒只在 `CHAT/IDLE` 下运行，避免打断导航播报；提醒带冷却时间防刷屏

3. **场景探索 / 语义输出（WP1/WP2/WP3/WP4 最小可用）**
   - 新增：`semantic_output.py`
   - 支持：Top-3 筛选、方向（钟点）、距离（启发式）、关系、规避动作、动态/稳定自适应模板
   - 去冗余（WP2）：IoU 去重 + 输出签名去重节流
   - 场景推断/权重表（WP3）：`context/weights/*.txt` + `context/user_prefs.json`
   - IMU 闭环抑制（WP4）：转头/转身（yaw_rate 超阈值）时抑制冗余播报（除非紧急项）
   - 主要指令：
     - 一次性：`描述周围` / `周围有什么` / `场景探索`
     - 常驻：`开启场景探索` / `关闭场景探索`
     - 调参热加载：`重新加载语义权重`

4. **事件记录（用于回放/评估/复现）**
   - 新增：`event_logger.py`
   - 行为：UI final 与语义输出 payload 会写入 `recordings/events_*.jsonl`（默认开启，可通过环境变量关闭）
   - 目的：满足 `tasks/执行文档.md` 的“可复现：输入→状态→输出”要求，并为论文/评估提供数据

### 1.2 配置与文档同步

- 更新 `/.env.example`：补充人脸/关灯/语义输出/事件记录相关环境变量示例
- 更新 `README.md`：补充新语音指令与可选环境变量说明
- 更新 `功能实现状态文档.md`：12/12 功能已实现，并把 #8/#12 从“未实现”改为“已实现”（同时保留“可选升级建议”）
- 更新 `/.gitignore`：
  - 忽略 `.env`、`.ultralytics/`、`context/faces/`、`recordings/`、`__pycache__/`、`*.pyc`

## 2) 今日日志总览（2026-01-21，log.md 全部内容的“汇总版”）

> 目标：把今天 log.md 里所有记录再压缩成“一份总览”，便于快速回顾。

### 2.1 今日完成的阶段目标

1. **工程可运行性打底（先跑通再扩展）**
   - 统一使用 conda 环境 `openai_glasses`（路径固定）作为运行基线
   - `.env/.env.example` 对齐：不再硬编码 DashScope key；全部从 `DASHSCOPE_API_KEY` 读取
   - 模型路径与资源路径去绝对路径：默认使用仓库内 `model/`、`music/` 等相对路径，并支持 env 覆盖
   - 修复 Ultralytics 写配置权限问题：统一改写入仓库内 `.ultralytics/`
   - 修复会阻塞启动的语法错误（`app_main.py` 的 `global` 使用）
   - 音频资源映射对齐实际文件名，避免启动后播报找不到音频文件

2. **对照 tasks/ 要求，补齐缺失功能并落地 WP 最小实现**
   - 缺失功能（#8/#12）已补齐：人脸/朋友识别 + 关灯提醒
   - WP1–WP4 最小实现落地：语义输出骨架 + 去冗余 + 权重表 + IMU 抑制冗余播报
   - 增加事件记录：形成可回放/可评估的数据闭环

### 2.2 今日关键决策（综合）

1. **最小改动原则**：不做大规模重构，不破坏现有状态机与主循环；新增功能以“模块 + 指令入口 + 可回滚”方式接入。
2. **离线优先**：
   - 人脸识别采用 OpenCV Haar + LBPH 实现闭环（不依赖联网安装大模型）。
   - 关灯提醒先用启发式规则跑通闭环（可演示、可调参），后续再考虑更强模型。
3. **输出规范统一**：
   - UI 输出统一走 `ui_broadcast_final()`，并区分 `[AI]` 与 `[导航]`。
   - 语音输出统一走 `play_voice_text()`（保持一致的播报路径）。
4. **可复现优先**：新增 JSONL 事件日志，作为后续评估与 bug 复现依据。

### 2.3 今日关键假设（综合）

1. conda 环境 `openai_glasses` 的依赖已齐全（含 `cv2.face`）。
2. 运行时能获取到摄像头画面；否则与视觉相关的功能会降级提示“暂无画面/请对准镜头”。
3. DashScope 相关能力（ASR/Omni）依赖真实 `DASHSCOPE_API_KEY` 与网络可达性；本地功能（人脸/关灯/语义输出）不依赖该 key。

### 2.4 今日仍未完全解决的问题（综合）

1. **外部服务端到端验证**：DashScope 调用链路仍需用户填入真实 key 并实际运行验证（网络/区域/鉴权）。
2. **关灯提醒与场景推断的鲁棒性**：目前为启发式 + 权重表方案；真实环境可能误判，需要基于数据回放调参/迭代。
3. **历史模块的“统一语音调度”收口**：已有模块有少量历史路径可能仍存在直接播报/独立节流逻辑；后续如要完全统一到 `VoiceScheduler` 需谨慎渐进，避免引入不稳定。

### 2.5 下一步行动（综合建议）

1. **在 conda 环境实际运行回归**（真实摄像头/麦克风/ESP32 联调优先）：
   - 验证人脸录入→识别闭环
   - 验证关灯一次性检查与常驻提醒
   - 验证场景探索一次性与常驻输出（并查看 `recordings/events_*.jsonl` 是否写入）
2. **基于回放数据调参**：
   - 人脸阈值：`AIGLASS_FACE_MATCH_THRESHOLD`
   - 关灯阈值：`AIGLASS_LIGHT_*`
   - 语义输出：`AIGLASS_SEM_*`（周期/去重/转头阈值）
3. **准备论文/演示材料**：
   - 用事件日志抽取“动态/稳定场景对比样例”
   - 逐步完善 scene inference 规则与权重表，形成可解释的“重排逻辑”叙述

## 3) 追加：tasks 逐行实现程度对照文档

日期：2026-01-21（补充）

- 已生成 `tasks/实现程度对照文档.md`：逐行对照 `tasks/执行文档.md` 与 `tasks/项目综合文档.md`，每行标注 `DONE/PARTIAL/TODO/INFO` 并给出证据/备注。
- 用途：便于验收与查缺补漏（尤其是 WP1–WP4 与“需要数据/硬件/实验”的条目）。

## 14) 本轮对话总结（2026-01-21）

- **决策**：
  1. 继续沿用“增量可回滚”策略，不重构主状态机，只在 `app_main.py` 的统一播报/播报接口里接入新指令，人脸、关灯与语义输出全部走 `ui_broadcast_final` + `play_voice_text`；同时用事件日志留记录，方便复现。  
  2. 盲道红绿灯处理优先用 `workflow_blindpath` 内的 YOLO 输出，并在 `_parse_yolo_results` 里把 class 名映射为 `red/green/yellow`，只在解析失败或不确定时退到已有的 HSV 检测，避免 HSV 误判影响主流程。  
  3. 为 `tasks/实现程度对照文档.md` 保持一份“高层汇总”用于快速了解 DONE/PARTIAL/TODO，同步将刚刚的代码更新写入对应条目，确保文档与实现同步。

- **假设**：
  1. 本地 `openai_glasses` environment 仍可访问 DashScope API（仅需补 `DASHSCOPE_API_KEY`），也具备 `cv2.face` 与 `torch` 等依赖。  
  2. 模型文件（`model/` 目录）与语音/资源路径在仓库内，不会因绝对路径而失败，且 `YOLO` 模型可在任意 GPU/CPU 上加载。  
  3. 彩色/语义提示的距离估计、角度估计均为启发式（面积分数、中心位置），足够用作“可执行提示”描述。

- **未解决的问题**：
  1. DashScope ASR/Qwen 仍需用户填入真实 `DASHSCOPE_API_KEY` 并完成网络访问才能验证 end-to-end；本轮未实测。  
  2. `_parse_yolo_results` 逻辑尚未在真实红绿灯测试集中跑通，需确认 color map 是否覆盖常见 class 且不会误判；同时观察 HSV fallback 触发频率。  
  3. tasks 文档中归类为 TODO 的用户研究、问卷、算法对比等项依旧依赖真实数据/实验室测试，代码层面无法自动解决。  
  4. 语义输出与场景推断的“全流程去冗余”尚未统一覆盖所有 workflow（需按 WP2/3/4 继续扩展）。

- **下一步行动**：
  1. 在 `openai_glasses` 环境里跑一次完整的 `python app_main.py`（最好连上摄像头/ESP32），验证人脸识别、关灯提醒与 semantic exploration 的语音/UI回路，并检查 `recordings/events_*.jsonl` 内容是否合理。  
  2. 用真实红绿灯帧跑 `workflow_blindpath.detect_traffic_light`，观察 `_parse_yolo_results` 的日志与返回色彩，必要时扩充 `YOLO_TRAFFIC_LIGHT_COLOR_MAP` 并调整 `logger` 级别。  
  3. 复查汇总文档（`tasks/实现程度对照文档汇总.md`）里的 TODO，按照依赖（数据/硬件/网络）顺序安排下一轮工作（对照 `tasks/执行文档.md`、`tasks/项目综合文档.md` 的 PARTIAL 项）。

---

## 15) 本轮对话补充：Git 分支准备与上传前清理（2026-01-26）

> 目标：检查 GitHub 远端配置，创建并整理 `dev` 分支；把“上传前准备”全部做完（用户自行 push）。

### 15.1 关键发现

1. 远端仓库：`origin=https://github.com/lzc0228/AIglass.git`（HTTPS）。
2. 网络连通性 OK（可访问 github.com），但 `git ls-remote` 返回 **401**，并触发 askpass 等待交互式输入（导致命令超时）。结论：**需要 GitHub 认证**（PAT 或 SSH）。
3. 仓库中存在不应推送的运行时/缓存产物：
   - `recordings/`（音视频录制文件，体积较大）
   - `__pycache__/`（`.pyc`）
   - `.specstory/`、`music_downloads/`、`*.out` 等调试/下载产物
4. `.env` 在本地存在但已被 `.gitignore` 忽略；`.env.example` 使用占位符，不含真实 key。

### 15.2 本轮完成的上传前准备（已落地到本地 `dev`）

1. **创建分支**：从 `main` 创建并切换到 `dev`。
2. **配置提交身份**：设置本地 `git config user.name/user.email`，避免 commit 阶段缺失身份导致失败。
3. **清理忽略规则**：更新 `.gitignore`，新增忽略：
   - `.specstory/`、`music_downloads/`、`compile.zip`、`musicn-1.5.0.tar.gz`
   - `recordings/`、`context/faces/`、`__pycache__/`、`*.pyc`
   - `*.out`、`*.log`、`debug_output.txt`、`output.txt`
4. **提交内容**：
   - `79f7985`：`dev: sync features and docs`（本轮实现与文档同步的主提交）
   - `d452a4a`：`chore: stop tracking runtime artifacts`（将历史误纳入 git 的 `recordings/` 与 `__pycache__/` 从版本控制中移除；本地文件保留）
5. **最终状态**：`dev` 分支工作区干净（`git status` 无未提交变更）。

### 15.3 决策

1. 按用户要求：我不直接 push；只把 `dev` 分支与提交准备完整。
2. 保持 `origin` 为 HTTPS 不自动改动；由用户选择继续 HTTPS（PAT）或改 SSH。

### 15.4 假设

1. 用户对 `lzc0228/AIglass` 拥有 push 权限。
2. 用户将使用 GitHub 的 Personal Access Token（PAT）或 SSH key 完成认证。
3. 目标远端分支名为 `dev`（与本地一致）。

### 15.5 未解决问题

1. 远端认证未完成：HTTPS 方式会 401，需要 PAT/SSH 才能执行 `push/ls-remote`。
2. 未确认远端是否已存在 `dev` 分支（因认证卡住无法查询）。

### 15.6 下一步行动（用户侧）

1. 推送分支：`git push -u origin dev`
2. 若提示 401/需要密码：
   - HTTPS：Username 填 GitHub 用户名；Password 填 PAT（classic token，至少 `repo` 权限）
   - 或改 SSH：`git remote set-url origin git@github.com:lzc0228/AIglass.git` 后再 `git push -u origin dev`
3. 推送后建议：在 GitHub 开 PR（`dev` → `main`），并在 PR 描述中引用关键提交号 `79f7985` / `d452a4a` 作为变更依据。
