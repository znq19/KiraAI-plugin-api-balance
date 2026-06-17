import aiohttp

from core.plugin import BasePlugin, on, Priority
from core.provider import LLMRequest
from core.utils.tool_utils import BaseTool


class ApiBalanceTool(BaseTool):

    name = "query_api_balance"

    description = "查询 API 余额，支持 DeepSeek、SiliconFlow、月之暗面(Kimi)"

    parameters = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "description": "deepseek, siliconflow, moonshot"
            }
        },
        "required": ["provider"]
    }

    def __init__(self, ctx, plugin):
        self.ctx = ctx
        self.plugin = plugin

    async def execute(
        self,
        event,
        provider: str,
        *args,
        **kwargs
    ):
        provider = str(provider).lower()

        if provider == "deepseek":
            return await self.plugin.query_deepseek_balance()
        if provider == "siliconflow":
            return await self.plugin.query_siliconflow_balance()
        if provider == "moonshot":
            return await self.plugin.query_moonshot_balance()

        return f"不支持的供应商: {provider}，支持的供应商：deepseek, siliconflow, moonshot"


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

    async def initialize(self):

        # DeepSeek
        deepseek_section = self.plugin_cfg.get("section_deepseek", {})
        self.deepseek_base_url = deepseek_section.get(
            "deepseek_base_url",
            "https://api.deepseek.com"
        ).rstrip("/")
        self.deepseek_api_key = deepseek_section.get("deepseek_api_key", "")

        # SiliconFlow
        siliconflow_section = self.plugin_cfg.get("section_siliconflow", {})
        self.siliconflow_base_url = siliconflow_section.get(
            "siliconflow_base_url",
            "https://api.siliconflow.cn"
        ).rstrip("/")
        self.siliconflow_api_key = siliconflow_section.get("siliconflow_api_key", "")

        # 月之暗面 (Kimi)
        moonshot_section = self.plugin_cfg.get("section_moonshot", {})
        self.moonshot_base_url = moonshot_section.get(
            "moonshot_base_url",
            "https://api.moonshot.cn/v1"
        ).rstrip("/")
        self.moonshot_api_key = moonshot_section.get("moonshot_api_key", "")

    async def terminate(self):
        pass

    @on.llm_request(priority=Priority.HIGH)
    async def inject_tools(
        self,
        event,
        req: LLMRequest,
        *args,
        **kwargs
    ):

        try:
            req.tool_set.add(
                ApiBalanceTool(
                    ctx=self.ctx,
                    plugin=self
                )
            )

        except Exception as e:
            print(
                f"[api_balance] tool register failed: {e}"
            )

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

                    return f"DeepSeek当前余额：{total:.2f} 元"

        except Exception as e:
            return f"DeepSeek查询失败：{e}"

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

                    return f"SiliconFlow当前余额：{balance} 元"

        except Exception as e:
            return f"SiliconFlow查询失败：{e}"

    # ========== 月之暗面 Kimi ==========
    async def query_moonshot_balance(self):
        """查询月之暗面 Kimi 账户余额"""
    
        if not self.moonshot_api_key:
            return "未配置月之暗面 API Key"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.moonshot_base_url}/users/me/balance",
                    headers={"Authorization": f"Bearer {self.moonshot_api_key}"}
                ) as resp:
                    data = await resp.json()

                    # 月之暗面返回字段是 available_balance
                    balance = data.get("data", {}).get("available_balance")

                    if balance is None:
                        return f"查询失败: {data}"

                    return f"月之暗面 (Kimi) 当前余额：{balance} 元"

        except Exception as e:
            return f"月之暗面查询失败：{e}"
