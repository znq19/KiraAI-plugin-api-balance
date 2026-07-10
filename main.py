import aiohttp
from aiohttp.resolver import ThreadedResolver
from typing import List, Dict, Any, Optional
import re

from core.plugin import BasePlugin, on, Priority
from core.provider import LLMRequest
from core.utils.tool_utils import BaseTool
from core.logging_manager import get_logger
from core.chat.message_utils import KiraMessageEvent, KiraMessageBatchEvent
from core.chat import MessageChain
from core.chat.message_elements import Text

logger = get_logger("api_balance", "cyan")

# 平台名称与别名的映射表（所有名称统一转为小写进行匹配）
PLATFORM_ALIASES = {
    "deepseek": ["deepseek", "ds", "深度求索", "深度"],
    "siliconflow": ["siliconflow", "sf", "硅基流动", "硅基"],
    "moonshot": ["moonshot", "ms", "月之暗面", "暗面", "kimi"],
    "newapi": ["newapi", "新api", "api"],
}


def match_platform_by_alias(input_text: str, exact_match: bool = False) -> Optional[str]:
    """
    根据用户输入匹配平台，支持包含匹配和全字匹配
    返回: "deepseek" | "siliconflow" | "moonshot" | "newapi" | None
    """
    input_lower = input_text.lower().strip()
    if not input_lower:
        return None

    for platform, aliases in PLATFORM_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if exact_match:
                if input_lower == alias_lower:
                    return platform
            else:
                if input_lower in alias_lower:
                    return platform
    return None


class ApiBalanceTool(BaseTool):
    name = "query_api_balance"
    description = "查询 API 余额，支持 DeepSeek、SiliconFlow、月之暗面(Kimi)、以及自定义 New API 站点"
    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": "deepseek, siliconflow, moonshot, newapi, 或 NewAPI 站点名称（如 '小鸡'）"
            }
        },
        "required": ["provider"]
    }

    def __init__(self, ctx, plugin):
        self.ctx = ctx
        self.plugin = plugin

    async def execute(self, event, provider: str, *args, **kwargs):
        provider = provider.strip()
        if not provider:
            return "请指定要查询的平台"

        matched_platform = match_platform_by_alias(provider, exact_match=self.plugin.command_exact_match)
        if matched_platform:
            if matched_platform == "deepseek":
                return await self.plugin.query_deepseek_balance()
            elif matched_platform == "siliconflow":
                return await self.plugin.query_siliconflow_balance()
            elif matched_platform == "moonshot":
                return await self.plugin.query_moonshot_balance()
            elif matched_platform == "newapi":
                return await self.plugin.query_newapi_balance()

        site_result = await self.plugin.query_newapi_balance_by_name(provider)
        if site_result:
            return "\n".join(site_result) if isinstance(site_result, list) else site_result

        if self.plugin.command_exact_match:
            hint = "请输入完整的平台名称或站点名称"
        else:
            hint = "输入部分名称即可匹配（如 'ds' 匹配 'deepseek'）"
        return f"❌ 找不到匹配的供应商: {provider}\n支持：deepseek(ds)、siliconflow(sf)、moonshot(ms)、newapi，或你的 NewAPI 站点名称\n💡 {hint}"


class ApiBalancePlugin(BasePlugin):
    def __init__(self, ctx, cfg: dict):
        super().__init__(ctx, cfg)

        self.deepseek_base_url = ""
        self.deepseek_api_key = ""

        self.siliconflow_base_url = ""
        self.siliconflow_api_key = ""

        self.moonshot_base_url = ""
        self.moonshot_api_key = ""

        self.newapi_sites: List[Dict[str, Any]] = []

        self.enable_command = False
        self.command_words: List[str] = ["/余额", "/余额查询"]
        self.allowed_users: List[str] = []
        self.permission_denied_message = "❌ 权限不足：您没有查询余额的权限"
        self.command_success_template = "💳 {provider} 当前余额：{balance}"
        self.command_all_template = "💳 各平台余额如下：\n{results}"
        self.command_exact_match = False

        self.enable_tool = True

    def _get_session(self):
        connector = aiohttp.TCPConnector(
            resolver=ThreadedResolver(),
            ssl=False
        )
        return aiohttp.ClientSession(connector=connector)

    async def initialize(self):
        deepseek_section = self.plugin_cfg.get("section_deepseek", {})
        self.deepseek_base_url = deepseek_section.get(
            "deepseek_base_url", "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_api_key = deepseek_section.get("deepseek_api_key", "")

        siliconflow_section = self.plugin_cfg.get("section_siliconflow", {})
        self.siliconflow_base_url = siliconflow_section.get(
            "siliconflow_base_url", "https://api.siliconflow.cn"
        ).rstrip("/")
        self.siliconflow_api_key = siliconflow_section.get("siliconflow_api_key", "")

        moonshot_section = self.plugin_cfg.get("section_moonshot", {})
        self.moonshot_base_url = moonshot_section.get(
            "moonshot_base_url", "https://api.moonshot.cn/v1"
        ).rstrip("/")
        self.moonshot_api_key = moonshot_section.get("moonshot_api_key", "")

        all_sites = []

        newapi_section = self.plugin_cfg.get("section_newapi", {})
        json_sites = newapi_section.get("newapi_sites", [])
        if isinstance(json_sites, list):
            for site in json_sites:
                if isinstance(site, dict) and site.get("name") and site.get("base_url") and site.get("api_key"):
                    all_sites.append({
                        "name": site.get("name", "未命名站点"),
                        "base_url": site.get("base_url", "").rstrip("/"),
                        "api_key": site.get("api_key", ""),
                        "api_user": site.get("api_user", ""),
                        "quota_conversion": site.get("quota_conversion", 500000)
                    })

        simple_section = self.plugin_cfg.get("section_newapi_simple", {})
        simple_list = simple_section.get("newapi_sites_simple", [])
        if isinstance(simple_list, list):
            for line in simple_list:
                if not line or not line.strip():
                    continue
                parts = [p.strip() for p in line.split(";")]
                if len(parts) < 4:
                    logger.warning(f"[api_balance] 简易格式行格式错误（至少4个字段）: {line}")
                    continue
                name = parts[0]
                base_url = parts[1].rstrip("/")
                api_key = parts[2]
                api_user = parts[3]
                conversion = parts[4] if len(parts) >= 5 and parts[4].strip() else "500000"
                try:
                    conversion = float(conversion)
                except ValueError:
                    conversion = 500000
                all_sites.append({
                    "name": name,
                    "base_url": base_url,
                    "api_key": api_key,
                    "api_user": api_user,
                    "quota_conversion": conversion
                })

        self.newapi_sites = all_sites

        command_section = self.plugin_cfg.get("section_command", {})
        self.enable_command = command_section.get("enable_command", False)
        self.command_words = command_section.get("command_words", ["/余额", "/余额查询"])
        self.allowed_users = [str(uid).strip() for uid in command_section.get("allowed_users", []) if str(uid).strip()]
        self.permission_denied_message = command_section.get("permission_denied_message", "❌ 权限不足：您没有查询余额的权限")
        self.command_success_template = command_section.get("command_success_template", "💳 {provider} 当前余额：{balance}")
        self.command_all_template = command_section.get("command_all_template", "💳 各平台余额如下：\n{results}")
        self.command_exact_match = command_section.get("command_exact_match", False)

        tool_section = self.plugin_cfg.get("section_tool", {})
        self.enable_tool = tool_section.get("enable_tool", True)

        if self.newapi_sites:
            logger.info(f"[api_balance] 已加载 {len(self.newapi_sites)} 个自定义 New API 站点")
            for site in self.newapi_sites:
                logger.debug(f"[api_balance]   - {site['name']}: {site['base_url']} (api_user={site.get('api_user', '未设置')}, conversion={site.get('quota_conversion', 500000)})")

        logger.info(f"[api_balance] 自定义命令: {'启用' if self.enable_command else '禁用'}, 命令词: {self.command_words}, 工具调用: {'启用' if self.enable_tool else '禁用'}, 全字匹配: {'开启' if self.command_exact_match else '关闭'}")

    async def terminate(self):
        pass

    def _is_allowed(self, user_id: str) -> bool:
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    def _get_sid(self, event) -> str:
        if hasattr(event, "sid"):
            return event.sid
        if hasattr(event, "session") and hasattr(event.session, "sid"):
            return event.session.sid
        return "default"

    @on.llm_request(priority=Priority.HIGH)
    async def inject_tools(self, event, req: LLMRequest, *args, **kwargs):
        if not self.enable_tool:
            return
        try:
            req.tool_set.add(ApiBalanceTool(ctx=self.ctx, plugin=self))
        except Exception as e:
            logger.error(f"[api_balance] tool register failed: {e}")

    @on.im_message(priority=Priority.HIGH)
    async def handle_command(self, event: KiraMessageEvent):
        if not self.enable_command:
            return

        text = "".join(elem.text for elem in event.message.chain if isinstance(elem, Text))
        if not text:
            return

        text = text.strip()

        matched = False
        for cmd in self.command_words:
            if text == cmd or text.startswith(cmd + " "):
                matched = True
                break
        if not matched:
            return

        user_id = None
        if hasattr(event.message, "sender") and hasattr(event.message.sender, "user_id"):
            user_id = str(event.message.sender.user_id)
        else:
            logger.warning("[api_balance] 无法获取用户ID")
            return

        sid = self._get_sid(event)

        if not self._is_allowed(user_id):
            await self.ctx.message_processor.send_message_chain(
                session=sid,
                chain=MessageChain([Text(self.permission_denied_message)])
            )
            event.discard(force=True)
            event.stop()
            return

        parts = text.split(maxsplit=1)
        provider = parts[1].strip() if len(parts) > 1 else ""

        reply = await self._execute_command_query(provider)

        await self.ctx.message_processor.send_message_chain(
            session=sid,
            chain=MessageChain([Text(reply)])
        )
        event.discard(force=True)
        event.stop()

    async def _execute_command_query(self, provider: str) -> str:
        provider = provider.strip()
        if not provider:
            return await self._query_all_platforms()

        matched_platform = match_platform_by_alias(provider, exact_match=self.command_exact_match)
        if matched_platform:
            if matched_platform == "deepseek":
                result = await self.query_deepseek_balance()
                platform_display = "DeepSeek"
            elif matched_platform == "siliconflow":
                result = await self.query_siliconflow_balance()
                platform_display = "SiliconFlow"
            elif matched_platform == "moonshot":
                result = await self.query_moonshot_balance()
                platform_display = "月之暗面(Kimi)"
            elif matched_platform == "newapi":
                result = await self.query_newapi_balance()
                platform_display = "NewAPI"
            else:
                return "❌ 内部错误：未知平台"

            if "未配置" in result or "失败" in result or "无法解析" in result:
                return result

            balance_match = re.search(r'余额[：:]\s*([0-9.]+)', result)
            if balance_match:
                balance = balance_match.group(1)
                return self.command_success_template.format(provider=platform_display, balance=balance)
            else:
                return result

        site_results = await self.query_newapi_balance_by_name(provider)
        if site_results:
            return "\n".join(site_results)

        if self.command_exact_match:
            hint = "请输入完整的平台名称或站点名称"
        else:
            hint = "输入部分名称即可匹配（如 'ds' 匹配 'deepseek'）"
        return f"❌ 找不到匹配的供应商: {provider}\n支持：deepseek(ds)、siliconflow(sf)、moonshot(ms)、newapi，或你的 NewAPI 站点名称\n💡 {hint}"

    async def _query_all_platforms(self) -> str:
        results = []

        if self.deepseek_api_key:
            result = await self.query_deepseek_balance()
            if "未配置" not in result and "失败" not in result:
                balance_match = re.search(r'余额[：:]\s*([0-9.]+)', result)
                if balance_match:
                    results.append(f"DeepSeek：{balance_match.group(1)} 元")
                else:
                    results.append(f"DeepSeek：{result}")

        if self.siliconflow_api_key:
            result = await self.query_siliconflow_balance()
            if "未配置" not in result and "失败" not in result:
                balance_match = re.search(r'余额[：:]\s*([0-9.]+)', result)
                if balance_match:
                    results.append(f"SiliconFlow：{balance_match.group(1)} 元")
                else:
                    results.append(f"SiliconFlow：{result}")

        if self.moonshot_api_key:
            result = await self.query_moonshot_balance()
            if "未配置" not in result and "失败" not in result:
                balance_match = re.search(r'余额[：:]\s*([0-9.]+)', result)
                if balance_match:
                    results.append(f"月之暗面(Kimi)：{balance_match.group(1)} 元")
                else:
                    results.append(f"月之暗面(Kimi)：{result}")

        if self.newapi_sites:
            newapi_results = await self.query_newapi_balance()
            for line in newapi_results.split("\n"):
                if line.startswith("💳") or line.startswith("⚠️"):
                    name_match = re.search(r'💳\s*(.+?)：\s*([0-9.]+)', line)
                    if name_match:
                        results.append(f"{name_match.group(1)}：{name_match.group(2)} 元")
                    else:
                        results.append(line.replace("💳 ", ""))

        if not results:
            return "⚠️ 未配置任何有效的 API 余额查询平台"

        return self.command_all_template.format(results="\n".join(results))

    # ========== DeepSeek ==========
    async def query_deepseek_balance(self):
        if not self.deepseek_api_key:
            return "未配置 DeepSeek API Key"

        try:
            async with self._get_session() as session:
                async with session.get(
                    f"{self.deepseek_base_url}/user/balance",
                    headers={"Authorization": f"Bearer {self.deepseek_api_key}"}
                ) as resp:
                    data = await resp.json()

                    if "balance_infos" not in data:
                        return f"查询失败: {data}"

                    total = 0
                    for item in data["balance_infos"]:
                        total += float(item.get("total_balance", 0))

                    return f"DeepSeek 当前余额：{total:.2f} 元"

        except Exception as e:
            return f"DeepSeek 查询失败：{e}"

    # ========== SiliconFlow ==========
    async def query_siliconflow_balance(self):
        if not self.siliconflow_api_key:
            return "未配置 SiliconFlow API Key"

        try:
            async with self._get_session() as session:
                async with session.get(
                    f"{self.siliconflow_base_url}/v1/user/info",
                    headers={"Authorization": f"Bearer {self.siliconflow_api_key}"}
                ) as resp:
                    data = await resp.json()

                    balance = data.get("data", {}).get("balance")

                    if balance is None:
                        return f"查询失败: {data}"

                    return f"SiliconFlow 当前余额：{balance} 元"

        except Exception as e:
            return f"SiliconFlow 查询失败：{e}"

    # ========== 月之暗面 Kimi ==========
    async def query_moonshot_balance(self):
        if not self.moonshot_api_key:
            return "未配置月之暗面 API Key"

        try:
            async with self._get_session() as session:
                async with session.get(
                    f"{self.moonshot_base_url}/users/me/balance",
                    headers={"Authorization": f"Bearer {self.moonshot_api_key}"}
                ) as resp:
                    data = await resp.json()

                    balance = data.get("data", {}).get("available_balance")

                    if balance is None:
                        return f"查询失败: {data}"

                    return f"月之暗面 (Kimi) 当前余额：{balance} 元"

        except Exception as e:
            return f"月之暗面查询失败：{e}"

    # ========== New API 自定义站点 ==========
    @staticmethod
    def _try_extract_balance(data: dict) -> float | None:
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                for key in ["quota", "balance", "remaining", "total_balance", "points", "amount", "credit", "available"]:
                    if key in inner:
                        val = inner[key]
                        if isinstance(val, (int, float)):
                            return float(val)
                if "balance_infos" in inner:
                    total = 0
                    for item in inner["balance_infos"]:
                        total += float(item.get("total_balance", 0))
                    return total
            for key in ["quota", "balance", "remaining", "total_balance", "points", "amount", "credit", "available"]:
                if key in data:
                    val = data[key]
                    if isinstance(val, (int, float)):
                        return float(val)
        return None

    async def query_newapi_balance_by_name(self, site_name: str) -> Optional[List[str]]:
        if not self.newapi_sites:
            return None

        matched_sites = []
        site_name_lower = site_name.lower()

        for site in self.newapi_sites:
            site_display_name = site.get("name", "")
            site_name_lower_compare = site_display_name.lower()

            if self.command_exact_match:
                if site_name_lower == site_name_lower_compare:
                    matched_sites.append(site)
            else:
                if site_name_lower in site_name_lower_compare:
                    matched_sites.append(site)

        if not matched_sites:
            return None

        results = []
        for site in matched_sites:
            name = site.get("name", "未命名")
            base_url = site.get("base_url", "")
            api_key = site.get("api_key", "")
            api_user = site.get("api_user", "")
            conversion = site.get("quota_conversion", 500000)

            if not base_url or not api_key:
                results.append(f"⚠️ {name}: 配置不完整（缺少 base_url 或 api_key）")
                continue

            headers = {"Authorization": f"Bearer {api_key}"}
            if api_user:
                headers["New-Api-User"] = api_user

            try:
                async with self._get_session() as session:
                    async with session.get(
                        f"{base_url}/api/user/self",
                        headers=headers
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            results.append(f"❌ {name}: HTTP {resp.status} - {error_text[:100]}")
                            continue
                        data = await resp.json()

                        if isinstance(data, dict) and data.get("error"):
                            results.append(f"❌ {name}: {data.get('error', '未知错误')}")
                            continue

                        balance = self._try_extract_balance(data)
                        if balance is not None:
                            yuan = balance / conversion
                            results.append(f"💳 {name}: {yuan:.4f} 元 (quota: {balance}, 换算: {conversion})")
                        else:
                            results.append(f"⚠️ {name}: 无法解析余额，返回数据: {str(data)[:100]}")

            except aiohttp.ClientError as e:
                results.append(f"❌ {name}: 网络请求失败 - {e}")
            except Exception as e:
                results.append(f"❌ {name}: 查询异常 - {e}")

        return results

    async def query_newapi_balance(self) -> str:
        if not self.newapi_sites:
            return "未配置任何 New API 站点，请在插件设置中添加"

        results = []
        for site in self.newapi_sites:
            name = site.get("name", "未命名")
            base_url = site.get("base_url", "")
            api_key = site.get("api_key", "")
            api_user = site.get("api_user", "")
            conversion = site.get("quota_conversion", 500000)

            if not base_url or not api_key:
                results.append(f"⚠️ {name}: 配置不完整（缺少 base_url 或 api_key）")
                continue

            headers = {"Authorization": f"Bearer {api_key}"}
            if api_user:
                headers["New-Api-User"] = api_user

            try:
                async with self._get_session() as session:
                    async with session.get(
                        f"{base_url}/api/user/self",
                        headers=headers
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            results.append(f"❌ {name}: HTTP {resp.status} - {error_text[:100]}")
                            continue
                        data = await resp.json()

                        if isinstance(data, dict) and data.get("error"):
                            results.append(f"❌ {name}: {data.get('error', '未知错误')}")
                            continue

                        balance = self._try_extract_balance(data)
                        if balance is not None:
                            yuan = balance / conversion
                            results.append(f"💳 {name}: {yuan:.4f} 元 (quota: {balance}, 换算: {conversion})")
                        else:
                            results.append(f"⚠️ {name}: 无法解析余额，返回数据: {str(data)[:100]}")

            except aiohttp.ClientError as e:
                results.append(f"❌ {name}: 网络请求失败 - {e}")
            except Exception as e:
                results.append(f"❌ {name}: 查询异常 - {e}")

        if not results:
            return "所有 New API 站点查询均返回空结果"

        return "\n".join(results)
