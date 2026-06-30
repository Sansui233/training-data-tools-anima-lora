from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dataset_sources import collect_caption_files, collect_training_images, find_caption_for_image
from image_naming import original_stem


DOUBAO_API_KEY = ""
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seed-2-1-turbo-260628"
DEFAULT_TRIGGER = ""
DEFAULT_PROMPT = """Anima 风景 LoRA Caption 标注指南（无画质词 / 无触发词版）
一、Tag 排序权重规则
Anima 对前置标签的识别权重更高，标注需按「核心到次要、整体到局部」的顺序排列，权重从高到低依次为：
场景总类 + 核心地貌（最首位，决定画面大类归属）
核心标志性地物（构成风景主体的大元素）
光影、天气与氛围色调（决定画面整体观感）
构图、镜头与视角（画面结构与呈现形式）
次要点缀元素（概括表述）（非核心细碎元素）
人物及从属元素（放末尾）（弱化权重，避免抢占风景特征）
二、标注分级细则
（一）需详细精准标注的内容
场景与地貌分类
总体一个词描述风景类别。例子：如画面为开阔自然风景时，可前置 landscape，城市 city , 室内 indoor, 森林 forest, 海边 sea，户外 outdoor，建筑 building, 废墟 ruins，植物主体 plant, 小景、特写类局部风景无需强制添加。
风景类别可细化描述具体是什么，比如什么 jungle, 哪类的 sea/lake/ocean.
地貌需精准细分，禁用模糊表述：山脉区分 mountain range / snow capped peaks / cliff / plateau；水体区分 lake / ocean / waterfall / river / swamp；森林区分 pine forest / cherry blossom grove / bamboo forest 等。
核心标志性地物
占据画面较大面积、构成风景核心特征的元素必须拆分标注：
人文建筑：ancient stone temple, wooden pavilion, torii gate, mountain village
特色植被：giant banyan trees, autumn maple forest, bioluminescent mushrooms
特殊地貌：crystal clear alpine lake, tiered waterfall, karst rock formations
光影与环境氛围
明确标注时段、光照质感、天气、雾气等整体环境属性：
光照：golden hour sunlight, backlight, soft diffused light, moonlight
天气雾气：morning fog, drizzling rain, volumetric clouds, misty valley
色调倾向：warm orange tone, cool blue palette, muted pastel color
构图与镜头信息
明确画面视角与画幅，保证生成构图稳定：
wide shot, panoramic view, low angle, high angle, depth of field, foreground blur, distant focus
（二）需简略概括标注的内容（不拆分、不细化）
零散点缀物件需简略概括标注
占比小、随机出现、非风景核心特征的细碎元素，统一用概括性标签，不逐个枚举单一个体：
- 比如画面中的人物，人群就是 crowd, 1girl, 2boys 等。风景 LoRA 中人物仅为点缀，仅保留最低限度信息，禁止细化外貌：
  - 仅标注：数量 + 大致姿态 + 空间尺度，如 1girl, standing, small silhouette, far distance
禁止标注：
  - 发色、发型、服饰、表情、五官、角色名称、动作细节
  - 微观纹理细节
  - 地面纹路、墙面斑驳、叶片纹理等局部细碎质感，不单独拆标签，随主体元素一并概括即可。
三、标注禁忌
不添加任何画质类标签（如 masterpiece / best quality 等）
不添加自定义触发词，所有标签均为画面客观描述
不添加主观感受词（如 beautiful / amazing 等）
不添加渲染引擎、后期参数类标签（如 unreal engine / 8k 等）
四、标注示例
示例 1：雪山森林开阔风景
landscape, mountain range, snow capped peaks, dense pine forest, valley mist, golden hour backlight, panoramic wide shot, soft depth of field, scattered fallen leaves, distant tiny birds
示例 2：湖畔晨雾风景（含远处人影）
landscape, calm alpine lake, forest shoreline, thick morning fog, pale dawn sky, diffused ambient light, wide shot, 1boy, standing far distance, small silhouette
示例 3：山林古寺秋景
landscape, mountain forest, ancient stone temple, stone stairs, torii gate, autumn maple trees, soft overcast light, mid shot, depth of field, scattered fallen maple leaves
示例 4：海边悬崖日落
landscape, seaside cliff, crashing ocean waves, rocky shore, cloudy sunset sky, warm orange tone, high angle shot, distant seagulls

请根据输入图片生成最终 caption。
完全同义词需要重复使用，比如 tombstone gravestone 是同样的东西，则都输出。
你的 caption 长度应完全依照照片中的数量而定，不要完全按示例长度输出。
只输出一行 comma-separated English tags，不要输出解释、编号、Markdown 或中文。"""



def image_to_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_chat_payload(
    image_path: Path,
    model: str,
    prompt: str,
    temperature: float,
    image_url: str | None = None,
) -> dict[str, object]:
    image_url = image_url or image_to_data_url(image_path)
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "temperature": temperature,
        "reasoning_effort": "low",
    }


def call_doubao_chat_completion(
    payload: dict[str, object],
    api_key: str,
    base_url: str,
    timeout: int,
    retries: int,
    retry_delay: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    retryable_statuses = {429, 500, 502, 503, 504}
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in retryable_statuses and attempt < retries:
                time.sleep(retry_delay * (2 ** attempt))
                continue
            raise RuntimeError(f"Doubao API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(retry_delay * (2 ** attempt))
                continue
            raise RuntimeError(f"Doubao API request failed: {exc}") from exc
    raise RuntimeError("Doubao API request failed after retries")


def extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Doubao response does not contain choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("Doubao response choice is not an object")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("Doubao response choice does not contain a message")

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "\n".join(text_parts)
    raise ValueError("Doubao response message content is not text")


def normalize_tag_key(tag: str) -> str:
    return re.sub(r"\s+", "_", tag.strip().lower())


def split_tags(raw_caption: str) -> list[str]:
    cleaned = raw_caption.strip()
    cleaned = re.sub(r"^```(?:text|txt|csv)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = re.sub(r"^(?:tags?|caption)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    return [
        tag.strip().strip("\"'`")
        for tag in re.split(r"[,，\n;；]+", cleaned)
        if tag.strip().strip("\"'`")
    ]


def dedupe_tags(tags: list[str], trigger: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    initial_tags = [trigger, *tags] if trigger.strip() else tags
    for tag in initial_tags:
        key = normalize_tag_key(tag)
        if not key or key in seen:
            continue
        result.append(tag.strip())
        seen.add(key)

    return result


def tag_image_with_doubao(
    image_path: Path,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    prompt: str = DEFAULT_PROMPT,
    trigger: str = DEFAULT_TRIGGER,
    temperature: float = 0.1,
    timeout: int = 180,
    image_url: str | None = None,
    retries: int = 2,
    retry_delay: float = 5.0,
) -> tuple[list[str], dict[str, Any]]:
    payload = build_chat_payload(
        image_path=image_path,
        model=model,
        prompt=prompt,
        temperature=temperature,
        image_url=image_url,
    )
    response = call_doubao_chat_completion(
        payload=payload,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
    )
    raw_caption = extract_message_content(response)
    tags = dedupe_tags(split_tags(raw_caption), trigger)
    return tags, response


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def tag_folder_with_doubao(
    data_dir: Path,
    report_dir: Path,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    prompt: str = DEFAULT_PROMPT,
    trigger: str = DEFAULT_TRIGGER,
    temperature: float = 0.1,
    timeout: int = 180,
    force: bool = False,
    workers: int = 20,
    retries: int = 2,
    retry_delay: float = 5.0,
) -> dict[str, object]:
    data_dir = data_dir.resolve()
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    training_images = collect_training_images(data_dir)
    caption_files = collect_caption_files(data_dir)
    pending_bases: set[str] = set()
    images: list[tuple[Path, Path]] = []
    skipped: list[dict[str, object]] = []

    for image_path in training_images:
        image_base = original_stem(image_path)
        existing_caption = find_caption_for_image(image_path, caption_files)
        if not force and (existing_caption is not None or image_base in pending_bases):
            skipped.append(
                {
                    "image": str(image_path),
                    "caption": str(existing_caption or image_path.with_suffix(".txt")),
                    "caption_exists": existing_caption is not None,
                    "reason": (
                        "same basename caption exists"
                        if existing_caption is not None
                        else "same basename image is already queued"
                    ),
                }
            )
            continue

        images.append((image_path, image_path.with_suffix(".txt")))
        pending_bases.add(image_base)

    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    def tag_and_write(image_path: Path, caption_path: Path) -> dict[str, object]:
        tags, response = tag_image_with_doubao(
            image_path=image_path,
            api_key=api_key,
            model=model,
            base_url=base_url,
            prompt=prompt,
            trigger=trigger,
            temperature=temperature,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )
        caption_path.write_text(", ".join(tags) + "\n", encoding="utf-8")
        return {
            "image": str(image_path),
            "caption": str(caption_path),
            "tag_count": len(tags),
            "response_id": response.get("id"),
            "model": response.get("model"),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(tag_and_write, image_path, caption_path): (
                image_path,
                caption_path,
            )
            for image_path, caption_path in images
        }
        for index, future in enumerate(as_completed(futures), start=1):
            image_path, _caption_path = futures[future]
            try:
                result = future.result()
                successes.append(result)
                print(
                    f"[{index}/{len(images)}] tagged {image_path.name}: "
                    f"{result['tag_count']} tags"
                )
            except Exception as exc:
                failures.append(
                    {"image": str(image_path), "error": f"{type(exc).__name__}: {exc}"}
                )
                print(f"[{index}/{len(images)}] failed {image_path.name}: {exc}")

    write_jsonl(report_dir / "doubao_captions.jsonl", successes)
    write_jsonl(report_dir / "doubao_skipped.jsonl", skipped)
    write_jsonl(report_dir / "doubao_failures.jsonl", failures)

    summary = {
        "training_image_count": len(training_images),
        "image_count": len(images),
        "caption_count": len(successes),
        "skipped_count": len(skipped),
        "failed_count": len(failures),
        "data_dir": str(data_dir),
        "report_dir": str(report_dir),
        "base_url": base_url,
        "model": model,
        "trigger": trigger,
        "temperature": temperature,
        "force": force,
        "workers": workers,
        "retries": retries,
        "retry_delay": retry_delay,
    }
    (report_dir / "doubao_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Doubao captions for training images.")
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--target-dir", type=Path, default=Path("train/anima"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default=DOUBAO_API_KEY or os.getenv("ARK_API_KEY", ""))
    parser.add_argument("--trigger", default=DEFAULT_TRIGGER)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Doubao API key is empty. Fill DOUBAO_API_KEY in this script, "
            "pass --api-key, or set ARK_API_KEY."
        )
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.retries < 0:
        raise SystemExit("--retries must be at least 0")
    if args.retry_delay < 0:
        raise SystemExit("--retry-delay must be at least 0")

    target_dir = args.target_dir.resolve()
    data_dir = (args.data_dir or target_dir / "data").resolve()
    report_dir = (args.report_dir or target_dir / "reports").resolve()

    if args.image is not None:
        image_path = args.image.resolve()
        if not image_path.is_file():
            raise SystemExit(f"image does not exist: {image_path}")

        caption_files = collect_caption_files(image_path.parent)
        existing_caption = find_caption_for_image(image_path, caption_files)
        if existing_caption is not None and not args.force:
            print(
                json.dumps(
                    {
                        "image": str(image_path),
                        "caption": str(existing_caption),
                        "skipped": True,
                        "reason": "same basename caption exists",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        tags, response = tag_image_with_doubao(
            image_path=image_path,
            api_key=args.api_key,
            model=args.model,
            base_url=args.base_url,
            prompt=args.prompt,
            trigger=args.trigger,
            temperature=args.temperature,
            timeout=args.timeout,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
        caption_path = image_path.with_suffix(".txt")
        caption_path.write_text(", ".join(tags) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "image": str(image_path),
                    "caption": str(caption_path),
                    "tag_count": len(tags),
                    "response_id": response.get("id"),
                    "model": response.get("model"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        summary = tag_folder_with_doubao(
            data_dir=data_dir,
            report_dir=report_dir,
            api_key=args.api_key,
            model=args.model,
            base_url=args.base_url,
            prompt=args.prompt,
            trigger=args.trigger,
            temperature=args.temperature,
            timeout=args.timeout,
            force=args.force,
            workers=args.workers,
            retries=args.retries,
            retry_delay=args.retry_delay,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
