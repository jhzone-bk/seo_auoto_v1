import os
import json
import requests
import time  # 👈 导入时间模块，用于做延时控制
import re    # 👈 正则匹配，用于广告插入定位

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


def inject_ads(html_content, keyword):
    """
    根据关键词自动注入广告代码。
    广告插入位置：文章第 2 个 </p> 标签之后。

    匹配规则:
      - 关键词含「行车记录仪」→ 插入行车记录仪广告
      - 关键词含「保养」       → 插入保养产品广告
      - 无匹配                   → 返回原文不变
    """
    # 广告素材库
    AD_DASHCAM = (
        '<div class="ad-inject ad-dashcam" style="margin:20px 0;padding:16px;'
        'border:1px solid #e0e0e0;border-radius:8px;background:#fafafa;">'
        '<strong style="font-size:16px;color:#d32f2f;">[广告] 行车记录仪推荐</strong>'
        '<p style="margin:8px 0 0 0;">2026年热销4K超清行车记录仪，前后双录、夜视增强、'
        '停车监控，<a href="#" rel="nofollow sponsored">点击查看详情 &raquo;</a></p>'
        '</div>'
    )

    AD_MAINTENANCE = (
        '<div class="ad-inject ad-maintenance" style="margin:20px 0;padding:16px;'
        'border:1px solid #e0e0e0;border-radius:8px;background:#fafafa;">'
        '<strong style="font-size:16px;color:#1976d2;">[广告] 汽车保养优选</strong>'
        '<p style="margin:8px 0 0 0;">全合成机油买二送一、三滤套装限时特惠，'
        '正品保障假一赔十，<a href="#" rel="nofollow sponsored">立即抢购 &raquo;</a></p>'
        '</div>'
    )

    # 根据关键词选择广告
    keyword_lower = keyword.lower()
    if "行车记录仪" in keyword_lower:
        ad_html = AD_DASHCAM
    elif "保养" in keyword_lower:
        ad_html = AD_MAINTENANCE
    else:
        # 无匹配广告，原文返回
        return html_content

    # 定位第 2 个 </p> 标签之后的位置
    matches = list(re.finditer(r"</p>", html_content))
    if len(matches) < 2:
        # 如果 </p> 不足 2 个，在末尾追加
        return html_content + "\n" + ad_html

    # 在第 2 个 </p> 之后插入（即 match.end() 位置）
    insert_pos = matches[1].end()
    return html_content[:insert_pos] + "\n" + ad_html + html_content[insert_pos:]


if __name__ == "__main__":
    # 定义路径（脚本目录 → 根目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    keywords_file = os.path.join(root_dir, "keywords.txt")
    already_generated_file = os.path.join(root_dir, "already_generated.txt")

    # 加载已生成关键词（去重集合）
    already_generated = load_already_generated(already_generated_file)
    if already_generated:
        print(f"[DEDUP] 已加载 {len(already_generated)} 条已生成记录，将自动跳过")

    tasks = []

    # 1. 读取并解析关键词文件
    if os.path.exists(keywords_file):
        print(f"[READ] 正在读取词库文件: {keywords_file}")
        with open(keywords_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): # 略过空行或注释行
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    tasks.append({"keyword": parts[0].strip(), "title": parts[1].strip()})
    else:
        # 兼容备用方案
        print(f"[WARN] 未找到 {keywords_file}，将使用默认测试关键词运行。")
        tasks = [{"keyword": "3C数码选购", "title": "2026年最值得买的几款高性价比手机推荐"}]

    # 2. 过滤已生成的关键词，防止重复浪费 API
    original_count = len(tasks)
    tasks = [t for t in tasks if t["keyword"] not in already_generated]
    skipped = original_count - len(tasks)
    if skipped > 0:
        print(f"[SKIP] 跳过 {skipped} 条已处理关键词，剩余 {len(tasks)} 条待处理")

    os.makedirs("output_data", exist_ok=True)
    print(f"[START] 本次任务共需生成 {len(tasks)} 篇 SEO 文章...")
    
    # 2. 循环批量执行 AI 二创
    for index, task in enumerate(tasks, 1):
        print(f"\n🔄 [{index}/{len(tasks)}] 正在处理: {task['keyword']}")
        try:
            result_raw = rewrite_article(task["keyword"], task["title"])
            
            # 清洗 markdown 标记
            if "```json" in result_raw:
                result_raw = result_raw.split("```json")[1].split("```")[0].strip()
            elif "```" in result_raw:
                result_raw = result_raw.split("```")[1].split("```")[0].strip()
                
            # 校验 JSON 格式
            data = json.loads(result_raw.strip())

            # 广告自动注入：在写文件前对 html_content 插入广告
            if "html_content" in data:
                original_html = data["html_content"]
                data["html_content"] = inject_ads(original_html, task["keyword"])
                if data["html_content"] != original_html:
                    print("[AD] 广告已注入")

            # 将文件名用 keyword 命名
            filename = f"output_data/{task['keyword']}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"[OK] 成功生成 JSON 文件: {filename}")
            # 处理成功后，将关键词写入去重记录
            mark_as_generated(already_generated_file, task["keyword"])
        except Exception as e:
            print(f"❌ 处理失败 {task['keyword']}: {e}")
            if 'result_raw' in locals():
                print(f"📝 原始返回截取: {str(result_raw)[:200]}")
        
        # 👈 在每次生成完后（最后一篇除外），休眠 5 秒，防止触发 API 频率限制断连
        if index < len(tasks):
            print("⏳ 歇息 5 秒，防止被 API 中转站限流屏蔽...")
            time.sleep(5)
