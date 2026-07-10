# API余额查询插件 v2.6.0

查询 DeepSeek、SiliconFlow、Moonshot 以及自定义 New API 站点余额的 KiraAI 插件。

## 功能

- 查询 DeepSeek 账户余额
- 查询 SiliconFlow 账户余额
- 查询 Moonshot (Kimi) 账户余额
- 查询自定义 New API 站点余额（支持多个站点，JSON 或简易文本格式）
- 支持通过 **自定义命令** 触发（如 `/余额`、`余额`、`/mybalance` 等，可自定义）
- 支持通过 **LLM 工具调用** 触发（自然语言）
- **智能别名匹配**：支持简写，如 `ds` → DeepSeek、`sf` → SiliconFlow、`ms` → Moonshot
- **部分匹配**：输入部分文字即可匹配平台或站点（如 `鸡` 匹配 `小鸡`、`大鸡`）

## 使用方法

### 方式一：自定义命令（需在插件设置中开启）

在群聊或私聊中发送命令词即可查询余额：

```
/余额              # 查询所有已配置平台的余额
/余额 deepseek     # 查询 DeepSeek 余额（支持别名：ds、深度求索、深度）
/余额 siliconflow  # 查询 SiliconFlow 余额（支持别名：sf、硅基流动、硅基）
/余额 moonshot     # 查询月之暗面 (Kimi) 余额（支持别名：ms、kimi、暗面）
/余额 newapi       # 查询所有 NewAPI 站点余额（支持别名：新api、api）
/余额 小鸡          # 查询指定名称的 NewAPI 站点余额
/余额 鸡            # 匹配所有名称中包含“鸡”的站点（全字匹配关闭时）
```

> 💡 命令词支持自定义，可改为不带斜杠（如 `余额`、`查余额`），在插件设置 `command_words` 中配置即可。
> 💡 默认支持包含匹配（输入 `ds` 即可匹配 `deepseek`），如需要精确匹配可开启 `全字匹配`。

**示例回复：**

```
# 输入：/余额

💳 各平台余额如下：
DeepSeek：12.50 元
SiliconFlow：8.20 元
小鸡：3.45 元
浅忆：2.10 元
```

```
# 输入：/余额 ds

💳 DeepSeek 当前余额：12.50 元
```

```
# 输入：/余额 鸡

✅ 小鸡：3.4521 元 (quota: 1726050, 换算: 500000)
✅ 大鸡：1.2345 元 (quota: 617250, 换算: 500000)
```

### 方式二：自然语言（LLM 工具调用）

直接向 AI 发送指令，AI 会自动调用 `query_api_balance` 工具：

- "查询 DeepSeek 余额"
- "看看 SiliconFlow 还有多少钱"
- "帮我看看 Moonshot 余额"
- "查询所有 New API 站点的余额"
- "帮我查一下 API 余额"

## 配置说明

### 平台配置

#### DeepSeek

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `deepseek_base_url` | string | DeepSeek API 基础 URL |
| `deepseek_api_key` | sensitive | DeepSeek API Key |

#### SiliconFlow

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `siliconflow_base_url` | string | SiliconFlow API 基础 URL |
| `siliconflow_api_key` | sensitive | SiliconFlow API Key |

#### 月之暗面 (Kimi)

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `moonshot_base_url` | string | Moonshot API 基础 URL |
| `moonshot_api_key` | sensitive | Kimi API Key（从 platform.moonshot.cn 获取） |

#### 自定义 New API 站点

支持两种配置方式（可同时使用）：

**1. 简易文本格式（推荐）**

在 `section_newapi_simple` 中每行一个站点，格式：

```
名称;base_url;系统访问令牌;纯数字用户ID;换算比例(可选)
```

示例：
```
我的站点1;https://api.example.com;sk-xxxxxxxx;123456;500000
我的站点2;https://api2.example.com;sk-yyyyyyyy;789012
```

**2. JSON 格式**

在 `section_newapi` 中以 JSON 数组填写：

```json
[
  {
    "name": "站点名称",
    "base_url": "https://api.example.com",
    "api_key": "系统访问令牌",
    "api_user": "纯数字用户ID",
    "quota_conversion": 500000
  }
]
```

> ⚠️ **注意**：`api_key` 是系统访问令牌（在站点「个人设置 → 安全设置」中生成），**不是模型调用用的 API Key**。`api_user` 是纯数字用户 ID，在站点「个人中心」页面通常显示为 `ID: 12345`。`quota_conversion` 表示 `quota ÷ 该值 = 元`，默认 `500000`。

### 自定义命令控制

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_command` | switch | `false` | 开启后，用户可通过命令词直接查询余额 |
| `command_words` | list | `["/余额", "/余额查询"]` | 触发命令列表，支持不带斜杠（如 `余额`） |
| `allowed_users` | list | `[]` | 白名单 QQ 号，留空表示所有人可查 |
| `permission_denied_message` | string | `❌ 权限不足...` | 无权限时的提示 |
| `command_success_template` | string | `💳 {provider} 当前余额：{balance}` | 单平台查询成功模板，支持 `{provider}` `{balance}` |
| `command_all_template` | string | `💳 各平台余额如下：\n{results}` | 全部查询成功模板，支持 `{results}` |
| `command_exact_match` | switch | `false` | 开启全字匹配，关闭时支持部分匹配（如 `ds` → `deepseek`） |

### LLM 工具控制

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_tool` | switch | `true` | 开启后 LLM 可通过自然语言调用余额查询工具 |

## 注意事项

- New API 站点的 **系统访问令牌** 与 **模型调用 API Key** 是不同的，请勿混淆。
- **纯数字用户 ID** 可在站点的个人设置/账户信息页面找到（通常显示为 `ID: 12345`）。
- `quota_conversion` 换算比例需根据站点实际规则调整，可参考站点设置的 `quota_warning_threshold` 值。
- 自定义命令支持不带斜杠，如 `余额`、`查余额`，只需在 `command_words` 中添加即可。
- 平台别名支持：`ds` → DeepSeek、`sf` → SiliconFlow、`ms` → Moonshot、`kimi` → Moonshot。

## 作者

- 代码：ChuXia + znq19
- 上传助手：小染（被初夏抓来当苦力的(｀へ´)）

## 📝 更新日志

<details>
<summary><b>点击展开</b></summary>

### v2.6.0 (2026-07-11) — 自定义命令 + 智能别名匹配 + 网络稳定性优化 by znq19

**✨ 新增功能**
- **真正实现自定义命令控制**：用户可在群聊/私聊中通过 `/余额`、`余额` 等自定义命令直接查询余额，无需经过 LLM
- **智能别名匹配**：支持平台简写（`ds` → DeepSeek、`sf` → SiliconFlow、`ms` → Moonshot），输入部分文字即可匹配
- **NewAPI 站点名称匹配**：支持按站点名称单独查询，支持部分匹配（如 `鸡` 匹配 `小鸡`、`大鸡`）
- 支持命令词自定义（如 `/余额`、`余额`、`/mybalance` 等，完全由用户配置）
- 支持命令白名单权限控制，可指定哪些用户能使用命令
- 支持自定义成功/失败/权限不足的返回消息模板
- 新增全字匹配开关，关闭时支持部分匹配，开启后需完全匹配

**🔧 优化改进**
- 优化 `aiohttp` 网络请求稳定性，强制使用 `ThreadedResolver`
- 解决 Windows 环境下因 `aiodns` 导致的 DNS 解析失败问题（`Could not contact DNS servers`）
- 提升余额查询命令的响应速度

---

### v2.5.0 (2026-06-17) — New API 站点支持 by znq19

**✨ 新增功能**
- 支持自定义 New API 站点余额查询
- 支持 JSON 和简易文本两种配置格式
- 支持多个站点同时查询

---

### v1.0.0 ~ v2.0.0 — 基础平台支持 by ChuXia

**✨ 初始功能**
- 支持 DeepSeek 账户余额查询
- 支持 SiliconFlow (硅基流动) 账户余额查询
- 支持 Moonshot (月之暗面/Kimi) 账户余额查询

</details>
