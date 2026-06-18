"""
广告中台 (Ads Manager) — 策略模式实现
=====================================
基于 config.json 的插拔式广告架构，支持：
  - BaseAdStrategy 抽象基类
  - JDStrategy / TaobaoStrategy / LeadStrategy 三种变现策略
  - 熔断保护（失败自动切换 fallback）
  - 优先级排序 + 最多 3 个广告位
  - data-ad-source 数据埋点
"""

import os
import json
import time
import requests
from abc import ABC, abstractmethod


# ============================================================
# 配置加载
# ============================================================
def _load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(os.path.dirname(script_dir), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ============================================================
# 抽象基类: BaseAdStrategy
# ============================================================
class BaseAdStrategy(ABC):
    """所有广告策略的基类"""

    def __init__(self, name, config):
        self.name = name
        self.enabled = config.get("enabled", False)
        self.priority = config.get("priority", 99)
        self.api_config = config.get("api", {})
        self.fallback_html = config.get("fallback", {}).get("html", "")
        self._last_failure = 0          # 上次失败时间戳
        self._circuit_open = False      # 熔断器状态
        self._circuit_timeout = 60      # 熔断恢复时间（秒）

    def is_available(self):
        """检查策略是否可用（启用 + 未熔断）"""
        if not self.enabled:
            return False
        if self._circuit_open:
            # 熔断恢复检查
            if time.time() - self._last_failure > self._circuit_timeout:
                self._circuit_open = False
            else:
                return False
        return True

    def _trip_circuit(self):
        """触发熔断"""
        self._last_failure = time.time()
        self._circuit_open = True

    def _build_tracking_attr(self):
        """生成 data-ad-source 埋点属性"""
        return f' data-ad-source="{self.name}"'

    @abstractmethod
    def get_link(self, keyword):
        """
        获取广告链接（子类实现）。

        返回: (success: bool, url: str) 或 (False, None)
        """
        pass

    @abstractmethod
    def get_html(self, keyword):
        """
        获取广告 HTML 片段。

        返回: str — 完整的广告 HTML，失败时返回 fallback HTML
        """
        pass


# ============================================================
# 京东策略
# ============================================================
class JDStrategy(BaseAdStrategy):
    """京东联盟商品推广"""

    def __init__(self, config):
        import random
        super().__init__("jd", config)
        # direct_links 在策略配置顶层，不在 api 子对象内（支持链接池轮换）
        links = config.get("direct_links", [])
        if not links:
            # 兼容旧版 direct_link 单链接
            single = config.get("direct_link", "")
            links = [single] if single else []
        self.direct_links = links
        self._random = random

    def _pick_link(self):
        """从链接池中随机选一个，避免所有文章都用同一个链接"""
        if self.direct_links:
            return self._random.choice(self.direct_links)
        return ""

    def get_link(self, keyword):
        """调用京东 API 获取推广链接，无 API 配置时使用 direct_links 池"""
        base_url = self.api_config.get("base_url", "")
        app_key = self.api_config.get("app_key", "")
        if not app_key or not base_url:
            # 没有 API 配置 → 从链接池随机选
            link = self._pick_link()
            if link:
                return (True, link)
            return (False, None)

        try:
            # 京东联盟 API 调用（简化实现）
            params = {
                "method": "jd.union.open.goods.query",
                "app_key": app_key,
                "keyword": keyword,
            }
            resp = requests.get(base_url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # 提取第一个商品链接
                goods_list = (
                    data.get("jd_union_open_goods_query_response", {})
                    .get("result", {})
                    .get("data", [])
                )
                if goods_list:
                    url = goods_list[0].get("materialUrl", "")
                    if url:
                        return (True, url)
            # API 失败 → 降级到链接池
            link = self._pick_link()
            if link:
                return (True, link)
            return (False, None)
        except Exception:
            # 异常 → 降级到链接池
            link = self._pick_link()
            if link:
                return (True, link)
            return (False, None)

    def get_html(self, keyword):
        """获取京东广告 HTML，调用 API 失败则使用 direct_links 池"""
        try:
            success, link = self.get_link(keyword)
        except Exception:
            self._trip_circuit()
            success, link = False, None

        tracking = self._build_tracking_attr()

        if success and link:
            return (
                '<div class="ad-inject ad-jd" style="margin:20px 0;padding:16px;'
                'border:1px solid #e0e0e0;border-radius:8px;background:#fafafa;"'
                f'{tracking}>'
                '<strong style="font-size:16px;color:#c00;">[广告] 京东正品推荐</strong>'
                f'<p style="margin:8px 0 0 0;">京东自营正品保障，急速送达，'
                f'<a href="{link}" rel="nofollow sponsored"{tracking}>去京东选购 &raquo;</a></p>'
                '</div>'
            )

        # API 和 direct_link 都不可用，使用 fallback（不触发熔断，这只是无数据不是异常）
        return self.fallback_html.replace(
            'data-ad-source="jd"',
            f'data-ad-source="jd" data-ad-fallback="true"',
        )


# ============================================================
# 淘宝策略
# ============================================================
class TaobaoStrategy(BaseAdStrategy):
    """淘宝联盟商品推广"""

    def __init__(self, config):
        super().__init__("taobao", config)

    def get_link(self, keyword):
        """调用淘宝联盟 API 获取推广链接"""
        app_key = self.api_config.get("app_key", "")
        if not app_key:
            return (False, None)

        try:
            params = {
                "method": "taobao.tbk.item.get",
                "app_key": app_key,
                "q": keyword,
            }
            resp = requests.get(
                self.api_config.get("base_url", ""),
                params=params,
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = (
                    data.get("tbk_item_get_response", {})
                    .get("results", {})
                    .get("n_tbk_item", [])
                )
                if items:
                    url = items[0].get("click_url", "")
                    if url:
                        return (True, url)
            return (False, None)
        except Exception:
            return (False, None)

    def get_html(self, keyword):
        """获取淘宝广告 HTML，调用 API 失败则使用 fallback"""
        try:
            success, link = self.get_link(keyword)
        except Exception:
            self._trip_circuit()
            success, link = False, None

        tracking = self._build_tracking_attr()

        if success and link:
            return (
                '<div class="ad-inject ad-taobao" style="margin:20px 0;padding:16px;'
                'border:1px solid #e0e0e0;border-radius:8px;background:#fafafa;"'
                f'{tracking}>'
                '<strong style="font-size:16px;color:#f60;">[广告] 淘宝好物推荐</strong>'
                f'<p style="margin:8px 0 0 0;">海量汽车用品，天天特价，'
                f'<a href="{link}" rel="nofollow sponsored"{tracking}>去淘宝逛逛 &raquo;</a></p>'
                '</div>'
            )

        # API 未返回有效链接，使用 fallback（不触发熔断）
        return self.fallback_html.replace(
            'data-ad-source="taobao"',
            f'data-ad-source="taobao" data-ad-fallback="true"',
        )


# ============================================================
# 汽车线索策略（最高利润）
# ============================================================
class LeadStrategy(BaseAdStrategy):
    """汽车线索转化：试驾/保养预约表单"""

    def __init__(self, config):
        super().__init__("lead_generation", config)

    def get_link(self, keyword):
        """调用线索收集 API"""
        base_url = self.api_config.get("base_url", "")
        token = self.api_config.get("token", "")
        if not base_url:
            return (False, None)

        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            params = {"keyword": keyword}
            resp = requests.get(base_url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                link = data.get("form_url", "") or data.get("url", "")
                if link:
                    return (True, link)
            return (False, None)
        except Exception:
            return (False, None)

    def get_html(self, keyword):
        """获取线索转化表单 HTML，调用 API 失败则使用 fallback"""
        try:
            success, link = self.get_link(keyword)
        except Exception:
            self._trip_circuit()
            success, link = False, None

        tracking = self._build_tracking_attr()

        if success and link:
            return (
                '<div class="ad-inject ad-lead" style="margin:20px 0;padding:20px;'
                'border:2px solid #1976d2;border-radius:12px;'
                'background:linear-gradient(135deg, #f5f7fa 0%, #e8edf5 100%);"'
                f'{tracking}>'
                '<strong style="font-size:16px;color:#1976d2;">[推荐] 免费获取底价</strong>'
                '<p style="margin:8px 0 0 0;">多家4S店真实报价一键对比，底价买车不被坑，'
                f'<a href="{link}" rel="nofollow sponsored"{tracking}>立即获取底价 &raquo;</a></p>'
                '</div>'
            )

        # API 未返回有效链接，使用 fallback（不触发熔断）
        return self.fallback_html.replace(
            'data-ad-source="lead_generation"',
            f'data-ad-source="lead_generation" data-ad-fallback="true"',
        )


# ============================================================
# 广告中台 (AdsManager)
# ============================================================
class AdsManager:
    """
    广告中台：统一管理所有策略，对外提供 get_all_ads()。
    支持：
      - 按 config.json 动态加载策略
      - 优先级排序 + 最多 3 个广告位
      - 熔断保护（自动切换策略填补空位）
      - data-ad-source 数据埋点
    """

    STRATEGY_REGISTRY = {
        "jd": JDStrategy,
        "taobao": TaobaoStrategy,
        "lead_generation": LeadStrategy,
    }

    def __init__(self, config_path=None):
        self.config = _load_config() if config_path is None else self._load_file(config_path)
        self.global_settings = self.config.get("global_settings", {})
        self.max_ads = self.global_settings.get("max_ads_per_article", 3)
        self.auto_switch = self.global_settings.get("auto_switch_on_failure", True)
        self.active_strategies = self._init_strategies()

        # 精准匹配映射表
        self.keyword_ad_mapping = self.config.get("keyword_ad_mapping", {})
        # 通用广告池配置
        self.default_ad_config = self.config.get("default_ad", {})
        self._default_ad_index = 0  # 轮询索引用

    def _load_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _init_strategies(self):
        """根据 config.json 初始化激活的策略列表，按 priority 排序"""
        strategies_config = self.config.get("strategies", {})
        loaded = []

        for name, strat_cfg in strategies_config.items():
            if not strat_cfg.get("enabled", False):
                continue
            cls = self.STRATEGY_REGISTRY.get(name)
            if cls is None:
                print(f"  [ADS] 未知策略类型: {name}，已跳过")
                continue
            instance = cls(strat_cfg)
            loaded.append(instance)

        # 按 priority 升序排列
        loaded.sort(key=lambda s: s.priority)
        print(f"  [ADS] 已加载 {len(loaded)} 条策略: {[s.name for s in loaded]}")
        return loaded

    def _match_keyword_ads(self, keyword):
        """
        关键词精准匹配：substring 匹配 keyword_ad_mapping 中的关键词。

        参数:
            keyword: 当前文章关键词（如 "宝马机油保养"）

        返回:
            list[str]: 匹配到的精准广告 HTML 列表（按 config 中定义顺序）
        """
        if not keyword or not self.keyword_ad_mapping:
            return []

        matched = []
        keyword_lower = keyword.lower()

        for match_key, ad_data in self.keyword_ad_mapping.items():
            # substring 匹配：关键词包含 match_key 即命中
            if match_key.lower() in keyword_lower:
                html = ad_data.get("html", "")
                if html:
                    matched.append(html)

        return matched

    def _get_default_ad(self):
        """
        从通用广告池中轮询取出一条广告，绝不重复连续取同一商品。

        返回:
            str: 一条通用广告 HTML
        """
        pool = self.default_ad_config.get("pool", [])
        if not pool:
            return None

        ad = pool[self._default_ad_index % len(pool)]
        self._default_ad_index += 1
        return ad

    def get_all_ads(self, keyword):
        """
        获取广告 HTML 列表，百分百保证不返回空列表。

        流程:
            1. 精准匹配 (keyword_ad_mapping) → 优先占据第1个广告位
            2. 策略广告 (JD/淘宝/线索) → 填充剩余广告位
            3. 通用广告池 (default_ad.pool) → 轮询兜底
            4. 硬编码兜底 → 绝对不返回空列表

        参数:
            keyword: 当前文章关键词

        返回:
            list[str]: 广告 HTML 片段列表（最多 max_ads 个，最少 1 个）
        """
        ads = []

        # ================================================
        # 第1步：精准匹配
        # ================================================
        precision_ads = self._match_keyword_ads(keyword)
        for pad in precision_ads:
            if len(ads) >= self.max_ads:
                break
            ads.append(pad)

        # ================================================
        # 第2步：策略广告
        # ================================================
        for strategy in self.active_strategies:
            if len(ads) >= self.max_ads:
                break

            if not strategy.is_available():
                continue

            try:
                ad_html = strategy.get_html(keyword)
                if ad_html and ad_html not in ads:
                    ads.append(ad_html)
            except Exception as e:
                print(f"  [ADS] {strategy.name} 异常: {e}")
                strategy._trip_circuit()

        # ================================================
        # 第3步：策略 fallback 兜底（填充剩余位）
        # ================================================
        if len(ads) < self.max_ads:
            for strategy in self.active_strategies:
                if len(ads) >= self.max_ads:
                    break
                if strategy.fallback_html and strategy.fallback_html not in ads:
                    ads.append(strategy.fallback_html)

        # ================================================
        # 第4步：通用广告池轮询兜底
        # ================================================
        pool = self.default_ad_config.get("pool", [])
        while len(ads) < self.max_ads and pool:
            default_ad = self._get_default_ad()
            if default_ad is None:
                break
            if default_ad not in ads:
                ads.append(default_ad)
            # 防止死循环：池中所有广告都已添加
            if len(ads) >= len(pool) and all(a in ads for a in pool):
                break

        # ================================================
        # 第5步：硬编码最终兜底（绝不返回空列表）
        # ================================================
        if not ads:
            ads.append(
                '<div class="ad-inject ad-hard-fallback" data-ad-source="hard_fallback" '
                'style="margin:20px 0;padding:16px;border:1px solid #e0e0e0;border-radius:8px;background:#fafafa;">'
                '<strong style="font-size:16px;color:#333;">[广告] 汽车用品精选</strong>'
                '<p style="margin:8px 0 0 0;">车载充电器、手机支架、清洁养护一站式购齐，'
                '<a href="https://u.jd.com/V60yYfp" rel="nofollow sponsored" data-ad-source="hard_fallback">立即选购 &raquo;</a></p>'
                '</div>'
            )

        return ads[:self.max_ads]

    def _has_spare_strategies(self):
        """检查是否有其他可用策略可以填补"""
        available = sum(1 for s in self.active_strategies if s.is_available())
        return available >= 1

    def inject_into_html(self, html_content, keyword):
        """
        将广告注入到 HTML 内容的指定位置。

        使用 config 中配置的插入位置（默认 after_p2, after_p4, after_p6），
        即第 2/4/6 个 </p> 之后，模拟首屏→中屏→文末的广告分布。
        """
        import re

        ads = self.get_all_ads(keyword)
        if not ads:
            return html_content

        # 找到所有 </p> 的位置
        p_matches = list(re.finditer(r"</p>", html_content))
        if len(p_matches) < 2:
            # 不足 2 个段落，在末尾追加所有广告
            return html_content + "\n" + "\n".join(ads)

        # 插入位置映射：第 2/4/6 个 </p>（0-indexed: 1, 3, 5）
        insert_offsets = [1, 3, 5]  # 对应 after_p2, after_p4, after_p6

        # 更稳健的做法：从后往前一次性插入
        insertions = []
        for i, ad_html in enumerate(ads):
            if i >= len(insert_offsets):
                break
            p_index = insert_offsets[i]
            if p_index < len(p_matches):
                insertions.append((p_matches[p_index].end(), ad_html))
            else:
                insertions.append((len(html_content), ad_html))

        # 按位置从大到小排序，从后往前插入
        insertions.sort(key=lambda x: x[0], reverse=True)
        result = html_content
        for pos, ad_html in insertions:
            if pos >= len(result):
                result += "\n" + ad_html
            else:
                result = result[:pos] + "\n" + ad_html + result[pos:]

        return result


# ============================================================
# 便捷工厂函数
# ============================================================
def create_ads_manager():
    """创建 AdsManager 实例，自动加载 config.json"""
    return AdsManager()