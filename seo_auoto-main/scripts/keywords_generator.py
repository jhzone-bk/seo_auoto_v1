"""
全自动关键词生成器 - 汽车热词自动覆盖
============================================
将主流汽车车型与痛点场景组合，生成 SEO 关键词列表，
输出到根目录 keywords.txt 中，格式为 关键词,标题。
"""

import os

# ============================================================
# 车型列表（主流汽车车型）
# ============================================================
CAR_MODELS = [
    # 特斯拉
    "Tesla Model Y",
    "Tesla Model 3",
    # 比亚迪
    "比亚迪汉",
    "比亚迪宋PLUS",
    "比亚迪秦PLUS",
    "比亚迪海豹",
    "比亚迪唐",
    "比亚迪元PLUS",
    # 小米
    "小米SU7",
    # 理想
    "理想L6",
    "理想L7",
    "理想L8",
    "理想L9",
    # 问界
    "问界M7",
    "问界M9",
    "问界M5",
    # 极氪
    "极氪001",
    "极氪007",
    # 蔚来
    "蔚来ET5",
    "蔚来ES6",
    # 小鹏
    "小鹏P7",
    "小鹏G6",
    "小鹏G9",
    # 其他热门
    "长安深蓝SL03",
    "吉利银河L7",
    "领克08",
    "智己LS6",
    "阿维塔12",
    "岚图FREE",
    "坦克300",
    "哈弗H6",
    "大众ID.4",
    "宝马i3",
    "奔驰EQB",
]

# ============================================================
# 痛点场景 / 用户搜索意图
# ============================================================
PAIN_POINTS = [
    "必备配件",
    "常见故障",
    "保养指南",
    "购车攻略",
    "续航实测",
    "优缺点分析",
    "落地价",
    "使用体验",
    "对比评测",
    "改装方案",
    "贷款方案",
    "保险费用",
    "充电桩安装",
    "冬季续航",
    "高速续航",
    "二手保值率",
    "车主真实口碑",
    "提车注意事项",
    "智能驾驶体验",
    "车机系统评测",
]

# ============================================================
# 标题模板（用于生成 SEO 友好的标题）
# ============================================================
TITLE_TEMPLATES = [
    "{model} {pain_point}，2026年最新整理值得收藏",
    "{model} {pain_point}，看完这篇就够了",
    "{model} {pain_point}，老车主真实分享避坑指南",
    "{model} {pain_point}，新手必看不踩雷",
    "{model} {pain_point}，全方位深度解析",
    "{model} {pain_point}，一篇讲透不花冤枉钱",
    "{model} {pain_point}，2026最全攻略",
    "{model} {pain_point}，真实车主一年用车总结",
    "{model} {pain_point}，买前必读干货分享",
    "{model} {pain_point}，过来人的血泪经验",
]


def generate_keywords(models, pain_points, title_templates):
    """
    将车型与痛点场景组合，生成 关键词,标题 列表。

    参数:
        models: 车型名称列表
        pain_points: 痛点场景列表
        title_templates: 标题模板列表

    返回:
        list[tuple[str, str]]: (关键词, 标题) 元组列表
    """
    keywords = []
    for model in models:
        for pain_point in pain_points:
            # 关键词 = 车型 + 痛点
            keyword = f"{model} {pain_point}"

            # 循环使用标题模板，避免全部相同
            template_index = (len(keywords)) % len(title_templates)
            title = title_templates[template_index].format(
                model=model, pain_point=pain_point
            )

            keywords.append((keyword, title))
    return keywords


def save_keywords(keywords, output_path):
    """
    将关键词列表保存到文件，每行格式: 关键词,标题

    参数:
        keywords: (关键词, 标题) 元组列表
        output_path: 输出文件路径
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for keyword, title in keywords:
            f.write(f"{keyword},{title}\n")

    print(f"[OK] 已生成 {len(keywords)} 条关键词，保存至: {output_path}")


def main():
    """主入口：生成关键词并写入 keywords.txt"""
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 根目录（脚本目录的上一级）
    root_dir = os.path.dirname(script_dir)
    # 输出路径
    output_path = os.path.join(root_dir, "keywords.txt")

    print(f"[CAR] 车型数量: {len(CAR_MODELS)}")
    print(f"[TOOL] 痛点场景数量: {len(PAIN_POINTS)}")
    print(f"[INFO] 预计生成关键词: {len(CAR_MODELS) * len(PAIN_POINTS)} 条")

    # 生成关键词
    keywords = generate_keywords(CAR_MODELS, PAIN_POINTS, TITLE_TEMPLATES)

    # 保存到文件
    save_keywords(keywords, output_path)

    # 预览前 5 条
    print("\n[PREVIEW] 预览前 5 条:")
    for kw, title in keywords[:5]:
        print(f"   {kw} → {title}")


if __name__ == "__main__":
    main()