import os
import json
import requests
import time  # 👈 导入时间模块，用于做延时控制
import re    # 👈 正则匹配，用于广告插入定位

# 广告中台接入（策略模式，替代旧 AD_CONFIG）
from ads_manager import create_ads_manager


def rewrite_article(raw_keyword, raw_title):
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("OPENAI_MODEL", "agnes-2.0-flash")
    
    # 规范化 URL 拼装
    if not base_url.endswith("/chat/completions"):
        base_url = base_url.rstrip("/") + "/chat/completions"
        
    prompt = f"""你是一个顶级SEO专家。请针对关键词「{raw_keyword}」和原始标题「{raw_title}」进行结构化二创。

输出格式必须是标准的 JSON，不要包含任何 markdown 语法标记（如 ```json ）。

字段要求如下：
{{
    "keyword": "高度优化的长尾关键词",
    "title": "吸引点击且包含关键词的 H1 标题",
    "meta_description": "150字以内的网页描述，用于提高搜索展现率",
    "html_content": "带有 <h2> <h3> <p> 标签的文章正文，内容要原创、通顺，字数在1000字以上"
}}"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    response = requests.post(base_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"\n❌ API 请求失败！HTTP 状态码为: {response.status_code}")
        print(f"当前请求使用的模型为: {model_name}")
        try:
            print(f"❌ 接口报错详情: {response.text}")
        except Exception:
            pass
        raise Exception(f"HTTP {response.status_code}")
        
    res_json = response.json()
    return res_json['choices'][0]['message']['content']


def load_already_generated(filepath):
    """
    读取已生成的关键词列表，返回 set 集合用于快速 O(1) 去重。
    如果文件不存在则创建空文件并返回空集合。
    """
    if not os.path.exists(filepath):
        open(filepath, "w", encoding="utf-8").close()
        return set()

    with open(filepath, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_as_generated(filepath, keyword):
    """将已成功处理的关键词追加写入 already_generated.txt"""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(keyword + "\n")


def load_progress(filepath):
    """读取进度文件，返回已处理行数（整数），不存在则返回 0"""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return int(content) if content.isdigit() else 0


def save_progress(filepath, count):
    """将当前已处理行数写入进度文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(str(count))


def fetch_car_hotspots(keywords_file, max_new=5):
    """
    热点自动补给：抓取汽车类资讯站最新标题，以 append 模式追加到 keywords.txt。
    使用多个备用源，若主源失败则自动切换。
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    new_keywords = []

    # 源 1: 懂车帝 / 今日头条汽车 RSS 聚合
    sources = [
        {
            "name": "toutiao-auto",
            "url": "https://www.toutiao.com/api/pc/feed/?category=news_auto",
            "parser": "json",
        },
        {
            "name": "autohome-news",
            "url": "https://www.autohome.com.cn/all/",
            "parser": "html",
        },
    ]

    for src in sources:
        if len(new_keywords) >= max_new:
            break
        try:
            print(f"  [FETCH] 尝试抓取: {src['name']} ...")
            resp = requests.get(src["url"], headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"  [FETCH] {src['name']} 返回 {resp.status_code}，跳过")
                continue

            if src["parser"] == "json":
                data = resp.json()
                items = data.get("data", [])
                for item in items:
                    title = (
                        item.get("title")
                        or item.get("abstract")
                        or ""
                    )
                    if title and len(title) > 5 and "汽车" not in title[:2]:
                        # 去重 + 截断
                        clean_title = title.strip()[:50]
                        if clean_title not in new_keywords:
                            new_keywords.append(clean_title)
                        if len(new_keywords) >= max_new:
                            break
            else:
                # HTML 解析：提取 <title> / <meta> / <h2> 等
                titles = re.findall(
                    r'<a[^>]*href="[^"]*"[^>]*>([^<]{8,60})</a>',
                    resp.text,
                )
                for t in titles:
                    t = t.strip()
                    if t and "汽车" in t:
                        t = re.sub(r"<[^>]+>", "", t)[:50]
                        if t not in new_keywords:
                            new_keywords.append(t)
                        if len(new_keywords) >= max_new:
                            break
        except Exception as e:
            print(f"  [FETCH] {src['name']} 异常: {e}")
            continue

    # 如果抓取失败，使用内置备用热点词库
    if not new_keywords:
        print("  [FETCH] 在线抓取均失败，使用内置备用热点词库")
        fallback_hotspots = [
            "2026年6月汽车销量排行榜,最新销量数据深度解读",
            "新能源车购置税减免政策延续,2026年买车能省多少钱",
            "小米SU7 Ultra发布,零百加速2秒级售价曝光",
            "比亚迪第800万辆新能源车下线,全球市场布局加速",
            "特斯拉FSD入华最新进展,自动驾驶法规解读",
            "理想L6交付破10万,家庭SUV市场格局重塑",
            "问界M9连续三个月销量冠军,华为智驾体验报告",
            "小鹏MONA首款车型亮相,10万级纯电轿车新选择",
        ]
        new_keywords = fallback_hotspots[:max_new]

    # 以 append 模式追加到 keywords.txt（去重）
    existing = set()
    if os.path.exists(keywords_file):
        with open(keywords_file, "r", encoding="utf-8") as f:
            existing = set(line.strip() for line in f if line.strip())

    added_count = 0
    with open(keywords_file, "a", encoding="utf-8") as f:
        for kw_line in new_keywords:
            if kw_line not in existing:
                f.write(kw_line + "\n")
                existing.add(kw_line)
                added_count += 1

    print(f"  [FETCH] 热点补给完成: 新增 {added_count} 条，共 {len(existing)} 条")
    return added_count


if __name__ == "__main__":
    # 定义路径（脚本目录 → 根目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    keywords_file = os.path.join(root_dir, "keywords.txt")
    already_generated_file = os.path.join(root_dir, "already_generated.txt")
    progress_file = os.path.join(root_dir, "processed_progress.txt")
    BATCH_SIZE = 5  # 每批处理 5 条后保存进度

    # 初始化广告中台（策略模式：JD / 淘宝 / 线索，按 config.json 配置）
    print("=" * 50)
    print("[ADS] 初始化广告中台...")
    ads_mgr = create_ads_manager()

    # ================================================================
    # 模块 A: 热点自动补给（追加最新汽车资讯到 keywords.txt）
    # ================================================================
    print("[HOTSPOT] 开始热点自动补给...")
    fetch_car_hotspots(keywords_file, max_new=5)

    # ================================================================
    # 模块 B: 进度管理 — 读取已处理行数，实现增量续跑
    # ================================================================
    start_index = load_progress(progress_file)
    if start_index > 0:
        print(f"[PROGRESS] 从第 {start_index} 行继续（已跳过前 {start_index} 行）")

    # 加载已生成关键词（去重集合）
    already_generated = load_already_generated(already_generated_file)
    if already_generated:
        print(f"[DEDUP] 已加载 {len(already_generated)} 条已生成记录，将自动跳过")

    # 读取并解析 keywords.txt 所有行
    all_lines = []
    if os.path.exists(keywords_file):
        print(f"[READ] 正在读取词库文件: {keywords_file}")
        with open(keywords_file, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                all_lines.append(raw)
    else:
        print(f"[WARN] 未找到 {keywords_file}，将使用默认测试关键词运行。")
        all_lines = ["3C数码选购,2026年最值得买的几款高性价比手机推荐"]

    # 空转保护：全部跑完则直接退出
    if start_index >= len(all_lines):
        print(f"[DONE] 所有 {len(all_lines)} 行已处理完毕，无需继续。")
        exit(0)

    # 解析为 tasks，跳过前 start_index 行
    tasks = []
    for raw in all_lines[start_index:]:
        if "," in raw:
            parts = raw.split(",", 1)
            tasks.append({"keyword": parts[0].strip(), "title": parts[1].strip()})

    # 过滤已生成关键词（二次去重保护）
    original_count = len(tasks)
    tasks = [t for t in tasks if t["keyword"] not in already_generated]
    skipped = original_count - len(tasks)
    if skipped > 0:
        print(f"[SKIP] 跳过 {skipped} 条已处理关键词，剩余 {len(tasks)} 条待处理")

    os.makedirs("output_data", exist_ok=True)
    print(f"[START] 本次任务共需生成 {len(tasks)} 篇 SEO 文章...")
    print("-" * 50)

    # ================================================================
    # 模块 C: 主循环 — 批量 AI 二创 + 广告注入 + 进度保存
    # ================================================================
    total_processed = start_index  # 累计已处理行数（含已跳过的）

    for index, task in enumerate(tasks, 1):
        print(f"\n[{index}/{len(tasks)}] 正在处理: {task['keyword']}")
        try:
            result_raw = rewrite_article(task["keyword"], task["title"])

            # 清洗 markdown 标记
            if "```json" in result_raw:
                result_raw = result_raw.split("```json")[1].split("```")[0].strip()
            elif "```" in result_raw:
                result_raw = result_raw.split("```")[1].split("```")[0].strip()

            # 校验 JSON 格式
            data = json.loads(result_raw.strip())

            # 广告自动注入（策略模式中台：多联盟 + 熔断 + 埋点）
            if "html_content" in data:
                original_html = data["html_content"]
                data["html_content"] = ads_mgr.inject_into_html(
                    original_html, task["keyword"]
                )
                if data["html_content"] != original_html:
                    print("  [AD] 广告中台已注入（含 data-ad-source 埋点）")

            # 写入 JSON 文件
            filename = f"output_data/{task['keyword']}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"  [OK] 成功生成 JSON 文件: {filename}")

            # 标记去重
            mark_as_generated(already_generated_file, task["keyword"])

        except Exception as e:
            print(f"  [FAIL] 处理失败 {task['keyword']}: {e}")
            if 'result_raw' in locals():
                print(f"  [RAW] 原始返回截取: {str(result_raw)[:200]}")

        # 增量进度保存：每处理完 BATCH_SIZE 条，写入进度文件并退出
        total_processed = start_index + index
        if index % BATCH_SIZE == 0:
            save_progress(progress_file, total_processed)
            print(f"  [PROGRESS] 已保存进度: {total_processed}/{len(all_lines)} 行")
            if index < len(tasks):
                print(f"  [BATCH] 本批次 {BATCH_SIZE} 条已完成，退出等待下次调度...")
                exit(0)

        # 休眠 5 秒，防止触发 API 频率限制
        if index < len(tasks):
            print("  [WAIT] 歇息 5 秒，防止被 API 中转站限流屏蔽...")
            time.sleep(5)

    # 最终保存进度（处理不足 BATCH_SIZE 的尾部）
    save_progress(progress_file, total_processed)
    print(f"  [DONE] 所有待处理任务已完成，进度: {total_processed}/{len(all_lines)} 行")
    print(f"\n[DONE] 全部完成！最终进度: {total_processed}/{len(all_lines)} 行")
