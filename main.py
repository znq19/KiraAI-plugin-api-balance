import aiohttp
from typing import List, Dict, Any

from core.plugin import BasePlugin, on, Priority
from core.provider import LLMRequest
from core.utils.tool_utils import BaseTool
from core.logging_manager import get_logger

logger = get_logger("api_balance", "cyan")


class ApiBalanceTool(BaseTool):
    name = "query_api_balance"
    description = "查询 API 余额，支持 DeepSeek、SiliconFlow、月之暗面(Kimi)、以及自定义 New API 站点"
    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": "deepseek, siliconflow, moonshot, 或 newapi（查询所有自定义站点）"
            }
        },
        "required": ["provider"]
    }

    def __init__(self, ctx, plugin):
        self.ctx = ctx
        self.plugin = plugin

    async def execute(self, event, provider: str, *args, **kwargs):
        provider = str(provider).lower()

        if provider == "deepseek":
            return await self.plugin.query_deepseek_balance()
        if provider == "siliconflow":
            return await self.plugin.query_siliconflow_balance()
        if provider == "moonshot":
            return await self.plugin.query_moonshot_balance()
        if provider == "newapi":
            return await self.plugin.query_newapi_balance()

        return f"不支持的供应商: {provider}，支持的供应商：deepseek, siliconflow, moonshot, newapi"


class ApiBalancePlugin(BasePlugin):
    def __init__(self, ctx, cfg: dict):
        super().__init__(ctx, cfg)

        # DeepSeek
        self.deepseek_base_url = ""
        self.deepseek_api_key = ""

        # SiliconFlow
        self.siliconflow_base_url = ""
        self.siliconflow_api_key = ""

        # 月之暗面 (Kimi)
        self.moonshot_base_url = ""
        self.moonshot_api_key = ""

        # 自定义 New API 站点列表（合并两种格式）
        self.newapi_sites: List[Dict[str, Any]] = []

    async def initialize(self):
        # DeepSeek
        deepseek_section = self.plugin_cfg.get("section_deepseek", {})
        self.deepseek_base_url = deepseek_section.get(
            "deepseek_base_url", "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_api_key = deepseek_section.get("deepseek_api_key", "")

        # SiliconFlow
        siliconflow_section = self.plugin_cfg.get("section_siliconflow", {})
        self.siliconflow_base_url = siliconflow_section.get(
            "siliconflow_base_url", "https://api.siliconflow.cn"
        ).rstrip("/")
        self.siliconflow_api_key = siliconflow_section.get("siliconflow_api_key", "")

        # 月之暗面 (Kimi)
        moonshot_section = self.plugin_cfg.get("section_moonshot", {})
        self.moonshot_base_url = moonshot_section.get(
            "moonshot_base_url", "https://api.moonshot.cn/v1"
        ).rstrip("/")
        self.moonshot_api_key = moonshot_section.get("moonshot_api_key", "")

        # === 合并所有 New API 站点配置 ===
        all_sites = []

        # 1. 从 JSON 格式读取
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

        # 2. 从简易文本格式读取
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

        if self.newapi_sites:
            logger.info(f"[api_balance] 已加载 {len(self.newapi_sites)} 个自定义 New API 站点")
            for site in self.newapi_sites:
                logger.debug(f"[api_balance]   - {site['name']}: {site['base_url']} (api_user={site.get('api_user', '未设置')}, conversion={site.get('quota_conversion', 500000)})")

    async def terminate(self):
        pass

    @on.llm_request(priority=Priority.HIGH)
    async def inject_tools(self, event, req: LLMRequest, *args, **kwargs):
        try:
            req.tool_set.add(ApiBalanceTool(ctx=self.ctx, plugin=self))
        except Exception as e:
            logger.error(f"[api_balance] tool register failed: {e}")

    # ========== DeepSeek ==========
    async def query_deepseek_balance(self):
        if not self.deepseek_api_key:
            return "未配置 DeepSeek API Key"

        try:
            async with aiohttp.ClientSession() as session:
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
            async with aiohttp.ClientSession() as session:
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
            async with aiohttp.ClientSession() as session:
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
        """尝试从 New API 返回数据中提取余额，支持多种字段路径"""
        if isinstance(data, dict):
            # 优先检查 data 嵌套
            if "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                for key in ["quota", "balance", "remaining", "total_balance", "points", "amount", "credit"]:
                    if key in inner:
                        val = inner[key]
                        if isinstance(val, (int, float)):
                            return float(val)
                if "balance_infos" in inner:
                    total = 0
                    for item in inner["balance_infos"]:
                        total += float(item.get("total_balance", 0))
                    return total
            # 顶层字段
            for key in ["quota", "balance", "remaining", "total_balance", "points", "amount", "credit"]:
                if key in data:
                    val = data[key]
                    if isinstance(val, (int, float)):
                        return float(val)
        return None

    async def query_newapi_balance(self) -> str:
        """查询所有自定义 New API 站点的余额"""
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
                async with aiohttp.ClientSession() as session:
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
                            results.append(f"✅ {name}: {yuan:.4f} 元 (quota: {balance}, 换算: {conversion})")
                        else:
                            results.append(f"⚠️ {name}: 无法解析余额，返回数据: {str(data)[:100]}")

            except aiohttp.ClientError as e:
                results.append(f"❌ {name}: 网络请求失败 - {e}")
            except Exception as e:
                results.append(f"❌ {name}: 查询异常 - {e}")

        if not results:
            return "所有 New API 站点查询均返回空结果"

        return "\n".join(results)
