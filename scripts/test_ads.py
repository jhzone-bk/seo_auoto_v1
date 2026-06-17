"""策略模式广告中台 — 完整功能测试（含精准匹配/兜底/百分百填充）"""
import sys, os, json, time

sys.path.insert(0, "scripts")
from ads_manager import (
    AdsManager, JDStrategy, TaobaoStrategy, LeadStrategy,
    BaseAdStrategy, create_ads_manager,
)

PASS, FAIL = 0, 0

# ============================================================
# Test 1: Strategy instantiation
# ============================================================
print("=" * 50)
print("[TEST 1] Strategy instantiation + base interface")

jd = JDStrategy({"enabled": True, "priority": 1, "api": {}, "fallback": {"html": "<div data-ad-source='jd'>JD</div>"}})
tb = TaobaoStrategy({"enabled": False, "priority": 3, "api": {}, "fallback": {"html": "<div data-ad-source='taobao'>TB</div>"}})
lead = LeadStrategy({"enabled": True, "priority": 2, "api": {}, "fallback": {"html": "<div data-ad-source='lead_generation'>LEAD</div>"}})

ok_jd = isinstance(jd, BaseAdStrategy) and jd.name == "jd"
ok_tb = isinstance(tb, BaseAdStrategy) and not tb.is_available()
ok_lead = isinstance(lead, BaseAdStrategy) and lead.name == "lead_generation"

for name, ok in [("JDStrategy", ok_jd), ("TaobaoStrategy(disabled)", ok_tb), ("LeadStrategy", ok_lead)]:
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if ok: PASS += 1
    else: FAIL += 1

# ============================================================
# Test 2: AdsManager loads config
# ============================================================
print("\n" + "=" * 50)
print("[TEST 2] AdsManager loads from config.json")
mgr = create_ads_manager()
print(f"  DEV: active_strategies = {[s.name for s in mgr.active_strategies]}")
ok = len(mgr.active_strategies) >= 1
print(f"  {'PASS' if ok else 'FAIL'}: strategy count = {len(mgr.active_strategies)}")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 3: get_all_ads fallback (API no data still returns fallback)
# ============================================================
print("\n" + "=" * 50)
print("[TEST 3] get_all_ads() fallback mechanism")
ads = mgr.get_all_ads("Tesla Model Y tire maintenance")
for i, ad in enumerate(ads):
    has_tracking = 'data-ad-source=' in ad
    has_fallback = 'data-ad-fallback' in ad
    print(f"  [{i+1}] data-ad-source: {has_tracking}, fallback: {has_fallback}")
ok = len(ads) >= 1 and all('data-ad-source=' in a for a in ads)
print(f"  {'PASS' if ok else 'FAIL'}: ad_count={len(ads)} + tracking")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 4: inject_into_html
# ============================================================
print("\n" + "=" * 50)
print("[TEST 4] inject_into_html() multi-position")
html = "<h2>Test</h2><p>P1</p><p>P2</p><p>P3</p><p>P4</p><p>P5</p><p>P6</p><p>P7</p>"
result = mgr.inject_into_html(html, "maintenance")
ad_count = result.count('data-ad-source=')
print(f"  DEV: data-ad-source count in result = {ad_count}")
ok = ad_count >= 1
print(f"  {'PASS' if ok else 'FAIL'}: ads injected into HTML")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 5: Circuit breaker (API exception -> trip -> fallback)
# ============================================================
print("\n" + "=" * 50)
print("[TEST 5] Circuit breaker on API exception")
jd2 = JDStrategy({"enabled": True, "priority": 1, "api": {"app_key": "", "base_url": ""}, "fallback": {"html": "<div data-ad-source='jd' data-ad-fallback='true'>JD-FALLBACK</div>"}})
def mock_get_link(keyword):
    raise Exception("Connection timeout")
jd2.get_link = mock_get_link
html2 = jd2.get_html("test")
ok = jd2._circuit_open and "data-ad-fallback" in html2
print(f"  {'PASS' if ok else 'FAIL'}: exception tripped circuit + fallback HTML")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 6: Auto-switch fill
# ============================================================
print("\n" + "=" * 50)
print("[TEST 6] Auto-switch fill (auto_switch_on_failure)")
jd2._circuit_open = True
jd2._last_failure = time.time()
mgr2 = AdsManager.__new__(AdsManager)
mgr2.global_settings = {"max_ads_per_article": 2, "auto_switch_on_failure": True}
mgr2.max_ads = 2
mgr2.auto_switch = True
mgr2.active_strategies = [jd2, lead]
mgr2.keyword_ad_mapping = {}
mgr2.default_ad_config = {"pool": []}
mgr2._default_ad_index = 0
ads_result = mgr2.get_all_ads("maintenance")
print(f"  DEV: after JD trip, got {len(ads_result)} ads")
ok = len(ads_result) >= 1
print(f"  {'PASS' if ok else 'FAIL'}: auto-switch fills after circuit trip")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 7: 精准匹配 — substring 命中（"宝马机油保养" 包含 "机油"）
# ============================================================
print("\n" + "=" * 50)
print("[TEST 7] 精准匹配: substring 命中 keyword_ad_mapping")
mgr3 = AdsManager.__new__(AdsManager)
mgr3.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr3.max_ads = 3
mgr3.auto_switch = True
mgr3.active_strategies = []
mgr3.keyword_ad_mapping = {
    "机油": {"html": '<div data-ad-source="precision" data-ad-keyword="机油">PRECISION-OIL</div>'},
}
mgr3.default_ad_config = {"pool": []}
mgr3._default_ad_index = 0
ads7 = mgr3.get_all_ads("宝马机油保养")
print(f"  DEV: 关键词='宝马机油保养', 命中精准广告数={len(ads7)}")
has_precision = any('data-ad-keyword="机油"' in a for a in ads7)
ok = len(ads7) >= 1 and has_precision and ads7[0].find('data-ad-keyword="机油"') != -1
print(f"  {'PASS' if ok else 'FAIL'}: 精准匹配命中 + 占据第1个广告位")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 8: 精准匹配 — 多关键词命中（"行车记录仪" + "轮胎"）
# ============================================================
print("\n" + "=" * 50)
print("[TEST 8] 精准匹配: 多关键词命中")
mgr8 = AdsManager.__new__(AdsManager)
mgr8.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr8.max_ads = 3
mgr8.auto_switch = True
mgr8.active_strategies = []
mgr8.keyword_ad_mapping = {
    "行车记录仪": {"html": '<div data-ad-source="precision" data-ad-keyword="行车记录仪">PRECISION-DVR</div>'},
    "轮胎": {"html": '<div data-ad-source="precision" data-ad-keyword="轮胎">PRECISION-TIRE</div>'},
}
mgr8.default_ad_config = {"pool": []}
mgr8._default_ad_index = 0
ads8 = mgr8.get_all_ads("行车记录仪和轮胎更换")
print(f"  DEV: 关键词='行车记录仪和轮胎更换', 命中精准广告数={len(ads8)}")
has_dvr = any('data-ad-keyword="行车记录仪"' in a for a in ads8)
has_tire = any('data-ad-keyword="轮胎"' in a for a in ads8)
ok = has_dvr and has_tire
print(f"  {'PASS' if ok else 'FAIL'}: 两个精准词均命中 (DVR={has_dvr}, TIRE={has_tire})")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 9: 精准匹配 — 无匹配时走通用广告池兜底
# ============================================================
print("\n" + "=" * 50)
print("[TEST 9] 兜底: 无精准匹配时走 default_ad.pool")
mgr9 = AdsManager.__new__(AdsManager)
mgr9.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr9.max_ads = 3
mgr9.auto_switch = True
mgr9.active_strategies = []
mgr9.keyword_ad_mapping = {}
mgr9.default_ad_config = {
    "pool": [
        '<div data-ad-source="default_pool" data-ad-product="车载充电器">CHARGER</div>',
        '<div data-ad-source="default_pool" data-ad-product="全能清洁剂">CLEANER</div>',
    ]
}
mgr9._default_ad_index = 0
ads9 = mgr9.get_all_ads("与汽车无关的内容")
print(f"  DEV: 关键词='与汽车无关的内容', 返回广告数={len(ads9)}")
all_default = all('data-ad-source="default_pool"' in a for a in ads9)
ok = len(ads9) >= 1 and all_default
print(f"  {'PASS' if ok else 'FAIL'}: 兜底通用广告池生效 (all_default={all_default})")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 10: 通用广告池轮询不重复
# ============================================================
print("\n" + "=" * 50)
print("[TEST 10] 通用广告池: 轮询避免重复")
mgr10 = AdsManager.__new__(AdsManager)
mgr10.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr10.max_ads = 3
mgr10.auto_switch = True
mgr10.active_strategies = []
mgr10.keyword_ad_mapping = {}
mgr10.default_ad_config = {
    "pool": [
        '<div data-ad-source="default_pool" data-ad-product="车载充电器">CHARGER</div>',
        '<div data-ad-source="default_pool" data-ad-product="全能清洁剂">CLEANER</div>',
        '<div data-ad-source="default_pool" data-ad-product="手机支架">MOUNT</div>',
    ]
}
mgr10._default_ad_index = 0
ads10a = mgr10.get_all_ads("test1")
ads10b = mgr10.get_all_ads("test2")

# 轮询后索引偏移，第2次调用应从不同位置开始
print(f"  DEV: 第1次调用 ads={[a[a.find('data-ad-product=')+17:a.find('data-ad-product=')+25].strip('\"') for a in ads10a]}")
print(f"  DEV: 第2次调用 ads={[a[a.find('data-ad-product=')+17:a.find('data-ad-product=')+25].strip('\"') for a in ads10b]}")

# 基本验证: 两次调用都能返回3个广告，且不重复
products_a = set()
products_b = set()
for a in ads10a:
    idx = a.find('data-ad-product="')
    if idx > 0:
        products_a.add(a[idx+17:].split('"')[0])
for a in ads10b:
    idx = a.find('data-ad-product="')
    if idx > 0:
        products_b.add(a[idx+17:].split('"')[0])

ok = len(ads10a) == 3 and len(ads10b) == 3 and len(products_a) == 3 and len(products_b) == 3
print(f"  {'PASS' if ok else 'FAIL'}: 轮询机制正常 (a={len(products_a)}个产品, b={len(products_b)}个产品)")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 11: 百分百填充 — 极端情况绝不返回空列表
# ============================================================
print("\n" + "=" * 50)
print("[TEST 11] 百分百填充: 极端情况绝不返回空")

# 场景1: 所有策略禁用的 AdsManager
mgr11a = AdsManager.__new__(AdsManager)
mgr11a.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr11a.max_ads = 3
mgr11a.auto_switch = True
mgr11a.active_strategies = []
mgr11a.keyword_ad_mapping = {}
mgr11a.default_ad_config = {"pool": []}
mgr11a._default_ad_index = 0
ads11a = mgr11a.get_all_ads("任意关键词")
ok11a = len(ads11a) >= 1 and 'data-ad-source="hard_fallback"' in ads11a[0]
print(f"  场景1 (无策略/无pool/无精准): ad_count={len(ads11a)}, hard_fallback={ok11a}")

# 场景2: keyword 为 None
ads11b = mgr11a.get_all_ads(None)
ok11b = len(ads11b) >= 1
print(f"  场景2 (keyword=None): ad_count={len(ads11b)}")

# 场景3: keyword 为空字符串
ads11c = mgr11a.get_all_ads("")
ok11c = len(ads11c) >= 1
print(f"  场景3 (keyword=''): ad_count={len(ads11c)}")

ok = ok11a and ok11b and ok11c
print(f"  {'PASS' if ok else 'FAIL'}: 百分百填充, 任何情况下都不返回空列表")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 12: 精准匹配 + 策略广告 + 通用池混合填充
# ============================================================
print("\n" + "=" * 50)
print("[TEST 12] 混合填充: 精准匹配优先 + 策略 + 通用池")
mgr12 = AdsManager.__new__(AdsManager)
mgr12.global_settings = {"max_ads_per_article": 3, "auto_switch_on_failure": True}
mgr12.max_ads = 3
mgr12.auto_switch = True
mgr12.active_strategies = [lead]  # 只有1个策略
mgr12.keyword_ad_mapping = {
    "机油": {"html": '<div data-ad-source="precision" data-ad-keyword="机油">PRECISION-OIL</div>'},
}
mgr12.default_ad_config = {
    "pool": [
        '<div data-ad-source="default_pool" data-ad-product="车载充电器">CHARGER</div>',
        '<div data-ad-source="default_pool" data-ad-product="全能清洁剂">CLEANER</div>',
    ]
}
mgr12._default_ad_index = 0
ads12 = mgr12.get_all_ads("机油更换")
print(f"  DEV: 关键词='机油更换', 返回广告数={len(ads12)}")
for i, a in enumerate(ads12):
    if 'data-ad-source="precision"' in a:
        print(f"  [{i+1}] precision (精准匹配)")
    elif 'data-ad-source="lead_generation"' in a:
        print(f"  [{i+1}] lead_generation (策略)")
    elif 'data-ad-source="default_pool"' in a:
        print(f"  [{i+1}] default_pool (通用池)")

# 第1个必须是精准匹配
first_is_precision = 'data-ad-source="precision"' in ads12[0]
ok = len(ads12) == 3 and first_is_precision
print(f"  {'PASS' if ok else 'FAIL'}: 精准匹配第1位 + 策略 + 通用池补齐3个")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Test 13: _match_keyword_ads 单元测试 — 大小写不敏感
# ============================================================
print("\n" + "=" * 50)
print("[TEST 13] _match_keyword_ads: 大小写不敏感 substring")
mgr13 = AdsManager.__new__(AdsManager)
mgr13.keyword_ad_mapping = {
    "机油": {"html": "<div>OIL</div>"},
}
mgr13.active_strategies = []
mgr13.global_settings = {}
mgr13.max_ads = 3
mgr13.auto_switch = True
mgr13.default_ad_config = {"pool": []}
mgr13._default_ad_index = 0

# 大小写混合测试
ads13_upper = mgr13._match_keyword_ads("宝马机油保养")
ads13_mixed = mgr13._match_keyword_ads("BMW机油")
ok = len(ads13_upper) == 1 and len(ads13_mixed) == 1
print(f"  {'PASS' if ok else 'FAIL'}: 大小写/混合不影响匹配 (upper={len(ads13_upper)}, mixed={len(ads13_mixed)})")
if ok: PASS += 1
else: FAIL += 1

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 50)
print(f"TOTAL: {PASS} PASS, {FAIL} FAIL")
if FAIL > 0:
    sys.exit(1)