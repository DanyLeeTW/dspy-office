# DSPy Agent 系統架構分析報告

> **專案名稱**: DSPy Agent - 聲明式 AI 代理框架
> **分析日期**: 2026-04-03
> **代碼規模**: 2,305 行純 Python (5 個模組文件)
> **技術棧**: Python 3.x + DSPy 2.5+ + 標準庫

---

## 1. 儀表板

| 維度 | 現況評分 (1-10) | 關鍵證據 (File) | 潛在風險 |
|:---|:---:|:---|:---|
| 模組解耦 | **9** | `signatures/__init__.py:1-226` 獨立簽名層 | Signatures 與 Modules 緊密耦合 |
| 測試友好度 | **8** | `utils/__init__.py:175-244` 內置評估指標 | 缺乏單元測試文件 |
| 性能瓶頸 | **7** | `modules/__init__.py:261-278` Session 文件 I/O | 同步文件操作阻塞 |
| 可擴展性 | **10** | `tools/__init__.py:41-121` 插件式註冊表 | DSPy 框架版本依賴 |
| DSPy 符合度 | **9** | 全面使用 Signature/Module/ReAct | 部分舊代碼風格殘留 |

---

## 2. 系統上下文圖 (C4 Model - Level 1)

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#38bdf8',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'defaultLinkColor': '#38bdf8',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
flowchart TB
    subgraph External["🌐 外部系統"]
        LLM[("DSPy LM<br/>OpenAI/DeepSeek")]
        MSG[("Messaging Platform<br/>企業微信")]
        MEM_DB[("LanceDB<br/>向量數據庫")]
        FS[("File System<br/>Sessions/Memory")]
    end

    subgraph DSPyAgent["🤖 DSPy Agent System"]
        subgraph Entry["📥 入口層"]
            XW[["dspy_xiaowang.py<br/>HTTP Server + 回調處理"]]
        end

        subgraph Core["⚙️ 核心層"]
            SIG[["signatures/<br/>15 個 DSPy Signatures"]]
            MOD[["modules/<br/>5 個 DSPy Modules"]]
        end

        subgraph Support["🔧 支持層"]
            TOOLS[["tools/<br/>26 個工具函數"]]
            UTILS[["utils/<br/>優化 + 指標"]]
        end
    end

    MSG -->|"Webhook"| XW
    XW -->|"調用"| MOD
    MOD -->|"使用"| SIG
    MOD -->|"執行"| TOOLS
    MOD -->|"檢索"| MEM_DB
    MOD -->|"LLM調用"| LLM
    XW -->|"持久化"| FS

    style LLM fill:#8b5cf6,color:#f8fafc
    style MOD fill:#38bdf8,color:#0f172a
    style SIG fill:#10b981,color:#0f172a
    style TOOLS fill:#f59e0b,color:#0f172a
```

---

## 3. 模組依賴矩陣

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'defaultLinkColor': '#64748b',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
flowchart LR
    subgraph DSPy["📦 DSPy Agent"]
        direction TB
        INIT["__init__.py<br/>45 行"]
        SIG["signatures/<br/>226 行"]
        MOD["modules/<br/>605 行"]
        TOOLS["tools/<br/>1007 行"]
        UTILS["utils/<br/>422 行"]
    end

    subgraph External["🔗 外部依賴"]
        DSPY_LIB[("dspy<br/>框架")]
        LEGACY[("舊模組<br/>memory/scheduler/messaging")]
    end

    INIT -->|"導出"| SIG
    INIT -->|"導出"| MOD
    INIT -->|"導出"| TOOLS
    INIT -->|"導出"| UTILS

    MOD -->|"from ..signatures import"| SIG
    MOD -->|"import tools"| TOOLS
    UTILS -->|"from .modules import"| MOD
    TOOLS -->|"import messaging/scheduler"| LEGACY

    MOD -->|"import dspy"| DSPY_LIB
    SIG -->|"import dspy"| DSPY_LIB

    style SIG fill:#10b981,color:#0f172a
    style MOD fill:#38bdf8,color:#0f172a
    style TOOLS fill:#f59e0b,color:#0f172a
    style DSPY_LIB fill:#8b5cf6,color:#f8fafc
```

---

## 4. 核心業務流時序圖

### 4.1 DSPy Agent 消息處理流程

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'actorBkg': '#1e293b',
    'actorTextColor': '#f8fafc',
    'actorBorder': '#38bdf8',
    'signalColor': '#38bdf8',
    'signalTextColor': '#f8fafc',
    'labelTextColor': '#f8fafc',
    'noteBkgColor': '#334155',
    'noteTextColor': '#f8fafc',
    'activationBkgColor': '#38bdf8',
    'activationBorderColor': '#38bdf8',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
sequenceDiagram
    autonumber
    participant User as 👤 用戶
    participant XW as 🚪 dspy_xiaowang
    participant SM as 📁 SessionManager
    participant CA as 🧠 CompleteAgent
    participant MM as 💾 MemoryModule
    participant RE as 🔄 ReAct
    participant Tools as 🔧 Tools

    User->>XW: 發送消息
    XW->>XW: debounce_message()
    XW->>SM: load(session_key)
    SM-->>XW: 歷史消息
    XW->>CA: forward(user_request, history)
    
    CA->>MM: forward(query)
    MM->>MM: retrieval(query)
    MM-->>CA: memory_context
    
    CA->>RE: forward(user_request, memory_context)
    
    loop Tool Use (max_iters=20)
        RE->>RE: 生成 thought
        alt 需要工具
            RE->>Tools: execute(tool_name, args)
            Tools-->>RE: 工具結果
        else 無需工具
            RE-->>CA: response
        end
    end
    
    CA-->>XW: Prediction(response, trajectory)
    XW->>SM: save(session_key, messages)
    XW-->>User: 回覆消息
```

### 4.2 DSPy Signature 定義流程

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'actorBkg': '#1e293b',
    'actorTextColor': '#f8fafc',
    'actorBorder': '#38bdf8',
    'signalColor': '#10b981',
    'signalTextColor': '#f8fafc',
    'labelTextColor': '#f8fafc',
    'noteBkgColor': '#334155',
    'noteTextColor': '#f8fafc',
    'activationBkgColor': '#10b981',
    'activationBorderColor': '#10b981',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
sequenceDiagram
    autonumber
    participant Dev as 👨‍💻 開發者
    participant SIG as 📝 Signature類
    participant DSPy as 🔮 DSPy框架
    participant LLM as ☁️ LLM

    Dev->>SIG: class MySig(dspy.Signature)
    Note over SIG: class MySig(dspy.Signature):<br/>    """任務描述"""<br/>    input: str = dspy.InputField()<br/>    output: str = dspy.OutputField()

    SIG->>DSPy: 註冊 Signature
    DSPy->>DSPy: 解析 InputField/OutputField
    
    Dev->>DSPy: module = dspy.Predict(MySig)
    DSPy->>DSPy: 綁定 Signature 到 Module
    
    Dev->>DSPy: result = module(input="...")
    DSPy->>LLM: 構建 prompt + 調用
    LLM-->>DSPy: 生成輸出
    DSPy->>DSPy: 解析為 Prediction 對象
    DSPy-->>Dev: result.output
```

---

## 5. DSPy 架構模式分析

### 5.1 文件行數統計

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
xychart-beta
    title "DSPy Agent 模組代碼行數分佈"
    x-axis ["tools", "modules", "utils", "signatures", "__init__"]
    y-axis "行數" 0 --> 1100
    bar [1007, 605, 422, 226, 45]
```

| 文件 | 行數 | 職責 | DSPy 組件 |
|:---|:---:|:---|:---|
| `tools/__init__.py` | 1007 | 26 個工具函數 + 註冊表 | DSPy Tools |
| `modules/__init__.py` | 605 | 5 個 DSPy Modules | DSPy Module |
| `utils/__init__.py` | 422 | Teleprompter + 評估指標 | DSPy Optimizer |
| `signatures/__init__.py` | 226 | 15 個 Signatures | DSPy Signature |
| `__init__.py` | 45 | Package 入口 | - |

### 5.2 DSPy 模式符合度

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'defaultLinkColor': '#64748b',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
flowchart LR
    subgraph Patterns["🎯 DSPy 核心模式"]
        P1["Signature<br/>聲明式輸入輸出"]
        P2["Module<br/>可組合邏輯單元"]
        P3["ReAct<br/>工具調用循環"]
        P4["ChainOfThought<br/>推理增強"]
        P5["Teleprompter<br/>自動優化"]
    end

    subgraph Implementation["✅ 實現狀態"]
        I1["✅ 15 個 Signatures<br/>signatures/__init__.py"]
        I2["✅ 5 個 Modules<br/>modules/__init__.py"]
        I3["✅ dspy.ReAct<br/>modules/__init__.py:212-225"]
        I4["✅ ChainOfThought<br/>modules/__init__.py:173"]
        I5["✅ MIPROv2<br/>utils/__init__.py:79-152"]
    end

    P1 --> I1
    P2 --> I2
    P3 --> I3
    P4 --> I4
    P5 --> I5

    style P1 fill:#10b981,color:#0f172a
    style P2 fill:#38bdf8,color:#0f172a
    style P3 fill:#8b5cf6,color:#f8fafc
    style P4 fill:#f59e0b,color:#0f172a
    style P5 fill:#ec4899,color:#f8fafc
```

---

## 6. 設計模式審計

### 6.1 DSPy 原生模式

| 模式 | 實現位置 | 符合度 | 評價 |
|:---|:---|:---:|:---|
| **Signature 模式** | `signatures/__init__.py:17-220` | ✅ 優秀 | 類繼承 + 類型提示規範 |
| **Module 模式** | `modules/__init__.py:181-278` | ✅ 優秀 | dspy.Module 子類化 |
| **ReAct 模式** | `modules/__init__.py:212-225` | ✅ 優秀 | 直接使用 dspy.ReAct |
| **Registry 模式** | `tools/__init__.py:41-121` | ✅ 優秀 | 裝飾器註冊工具 |
| **Teleprompter 模式** | `utils/__init__.py:79-152` | ✅ 優秀 | MIPROv2 封裝 |

### 6.2 與原版架構對比

| 特性 | 原版 (llm.py) | DSPy 版 | 改進 |
|:---|:---|:---|:---|
| LLM 調用 | urllib 手動 | dspy.LM 抽象 | ✅ 統一接口 |
| 工具循環 | while 手動 | dspy.ReAct | ✅ 自動化 |
| Prompt 管理 | 字符串拼接 | Signature 聲明 | ✅ 結構化 |
| 錯誤處理 | try/except | DSPy 內置 | ✅ 更健壯 |
| 優化支持 | 無 | Teleprompter | ✅ 自動優化 |

---

## 7. 數據流分析

### 7.1 DSPy 數據管道

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#38bdf8',
    'lineColor': '#64748b',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'mainBkg': '#0f172a',
    'nodeBorder': '#38bdf8',
    'clusterBkg': '#1e293b',
    'clusterBorder': '#334155',
    'titleColor': '#f8fafc',
    'edgeLabelBackground': '#1e293b',
    'defaultLinkColor': '#64748b',
    'fontFamily': 'Outfit, Inter, system-ui'
  }
}}%%
flowchart LR
    subgraph Input["📥 輸入"]
        REQ["user_request<br/>str"]
        HIST["conversation_history<br/>str"]
        MEM["memory_context<br/>str"]
    end

    subgraph DSPyPipeline["⚙️ DSPy 管道"]
        direction TB
        SIG["Signature<br/>輸入輸出定義"]
        MOD["Module<br/>邏輯封裝"]
        LM["LM<br/>語言模型"]
    end

    subgraph Output["📤 輸出"]
        RESP["response<br/>str"]
        TRAJ["trajectory<br/>List[Step]"]
    end

    REQ --> SIG
    HIST --> SIG
    MEM --> SIG
    SIG --> MOD
    MOD --> LM
    LM --> MOD
    MOD --> RESP
    MOD --> TRAJ

    style SIG fill:#10b981,color:#0f172a
    style MOD fill:#38bdf8,color:#0f172a
    style LM fill:#8b5cf6,color:#f8fafc
```

### 7.2 Session 管理

**SessionManager 類** (`modules/__init__.py:50-111`)

| 方法 | 職責 | 線程安全 |
|:---|:---|:---:|
| `load()` | 從 JSON 文件加載會話 | ✅ |
| `save()` | 保存會話到文件 | ✅ |
| `_strip_images()` | 清理圖片數據 | - |
| `_compress_evicted()` | 壓縮舊消息 | 異步 |

---

## 8. P0 風險標記

### 8.1 安全風險

| 風險 | 位置 | 描述 | 建議修復 |
|:---|:---|:---|:---|
| **命令注入** | `tools/__init__.py:129-154` | exec 工具直接執行 shell | 添加命令白名單 |
| **代碼注入** | `tools/__init__.py:627-645` | create_tool 動態執行 | AST 檢查 |
| **依賴注入** | `dspy_xiaowang.py:88-90` | registry 屬性動態設置 | 封裝為配置類 |

### 8.2 性能風險

| 風險 | 位置 | 描述 | 影響 |
|:---|:---|:---|:---|
| **同步文件 I/O** | `modules/__init__.py:74-81` | Session 加載同步阻塞 | 請求延遲 |
| **無緩存** | `modules/__init__.py:229-246` | Memory 無查詢緩存 | 重複檢索 |
| **大 Session** | `modules/__init__.py:49` | MAX_MESSAGES=40 硬編碼 | 內存膨脹 |

---

## 9. DSPy 最佳實踐符合度

### 9.1 Signature 設計

```python
# ✅ 正確實現 (signatures/__init__.py:17-34)
class AgentSignature(dspy.Signature):
    """任務描述作為 docstring"""
    user_request: str = dspy.InputField(desc="描述")
    response: str = dspy.OutputField(desc="描述")
```

**評估**:
- ✅ 使用類繼承 dspy.Signature
- ✅ 類型提示清晰
- ✅ desc 參數提供語義描述
- ✅ docstring 作為任務說明

### 9.2 Module 設計

```python
# ✅ 正確實現 (modules/__init__.py:181-196)
class Agent(dspy.Module):
    def __init__(self, use_chain_of_thought: bool = True):
        super().__init__()
        self.predict = dspy.ChainOfThought(AgentSignature)
    
    def forward(self, user_request: str, ...) -> dspy.Prediction:
        return self.predict(user_request=user_request, ...)
```

**評估**:
- ✅ 繼承 dspy.Module
- ✅ __init__ 中定義子模組
- ✅ forward 實現邏輯
- ✅ 返回 dspy.Prediction

### 9.3 ReAct 使用

```python
# ✅ 正確實現 (modules/__init__.py:212-225)
self.react = dspy.ReAct(
    ToolAgentSignature,
    tools=self.tools,
    max_iters=self.max_iters
)
```

**評估**:
- ✅ 使用 DSPy 內置 ReAct
- ✅ tools 作為函數列表傳入
- ✅ max_iters 控制循環

---

## 10. 改進建議

### 10.1 短期改進 (1 周)

1. **添加單元測試**
   ```python
   # tests/test_signatures.py
   def test_agent_signature_fields():
       sig = AgentSignature
       assert 'user_request' in sig.input_fields
       assert 'response' in sig.output_fields
   ```

2. **封裝配置**
   ```python
   # 替換 dspy_xiaowang.py:88-90
   class AgentConfig:
       def __init__(self, config: dict):
           self.workspace = config.get('workspace', '.')
           self.owner_id = next(iter(config.get('owner_ids', [])), '')
   ```

3. **添加緩存**
   ```python
   # modules/__init__.py MemoryModule
   from functools import lru_cache
   @lru_cache(maxsize=100)
   def _cached_retrieve(self, query: str) -> str:
       ...
   ```

### 10.2 中期改進 (1 月)

1. **異步支持**
   ```python
   class AsyncAgent(dspy.Module):
       async def aforward(self, ...):
           # 使用 asyncio
   ```

2. **可觀測性**
   ```python
   # 添加 DSPy 內置追蹤
   dspy.configure(lm=lm, trace=True)
   ```

3. **優化管道**
   ```python
   # 創建訓練數據生成器
   def generate_training_data(sessions_dir: str) -> List[dspy.Example]:
       ...
   ```

---

## 11. 審計檢查清單

- [x] **Check 1**: 已分析 `dspy_agent/` 全部 5 個 Python 文件
- [x] **Check 2**: 改進建議包含具體代碼範例
- [x] **Check 3**: Mermaid 語法使用雙引號轉義，符合規範
- [x] **Check 4**: Mermaid 樣式使用 Modern Dark 主題 + 高對比色彩

---

## 12. 總結

### DSPy Agent 架構評估

| 維度 | 評分 | 說明 |
|:---|:---:|:---|
| **DSPy 符合度** | 9/10 | 全面採用 Signature/Module/ReAct 模式 |
| **代碼質量** | 8/10 | 結構清晰，類型提示完整 |
| **可維護性** | 9/10 | 模組化設計，職責分離 |
| **可測試性** | 7/10 | 缺乏測試文件 |
| **可擴展性** | 10/10 | 插件式工具註冊 |

### 與原版對比

| 指標 | 原版 | DSPy 版 | 變化 |
|:---|:---:|:---:|:---:|
| 代碼行數 | 3,500 | 2,305 | -34% |
| 文件數 | 8 | 5 | -37.5% |
| 模組化 | 良好 | 優秀 | ↑ |
| 可優化 | 無 | Teleprompter | ✅ |

---

**報告生成**: Claude Code Agent
**架構類型**: DSPy Framework
**版本**: 2.0.0
**日期**: 2026-04-03
