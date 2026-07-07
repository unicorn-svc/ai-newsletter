#!/usr/bin/env python3
"""
Newsletter Generator

데이터(JSON) + 템플릿(Jinja2) -> 뉴스레터 HTML 생성.

[UI / 데이터 분리 구조]
  - UI       : templates/newsletter.html   (HTML 골격 + CSS. 스타일은 여기만 수정)
  - 데이터    : data/<날짜>.json             (발행분별 기사 데이터. 기사 추가는 여기만 수정)
  - 빌드 로직 : 이 파일                       (그룹핑 / 통계 / 날짜 포맷 + 렌더링)
  - 출력      : newsletters/YYYYMMDD_HHMM.html  (published_at 으로 파일명 자동 결정)

사용법:
    python generate_newsletter.py data/20260611_0630.json
    python generate_newsletter.py data/20260611_0630.json --send      # 생성 후 메일 발송
    python generate_newsletter.py data/20260611_0630.json -o out.html # 출력 경로 지정

데이터 JSON 형식 (UI 정보 없음 — 순수 데이터):
    {
      "published_at": "2026-06-11T06:30",
      "sources": ["AI Times", "지디넷", "전자신문"],
      "articles": [
        {"category": "genai", "title": "...", "url": "https://...",
         "summary": "...", "source": "전자신문", "time": "06/10 07:28"}
      ]
    }
  - articles 는 평면 배열. category 별 그룹핑/정렬/카운트는 렌더러가 자동 수행.
  - 통계(기사/소스/카테고리 수)도 자동 계산 — 손으로 세지 않음.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "newsletters"

# ── 카테고리 레지스트리 : (id, 이모지, 라벨) ─────────────────────────
# 표시 순서 = 이 목록의 순서. 기사가 있는 카테고리만 렌더(빈 카테고리 자동 생략).
# 색상은 templates/newsletter.html 의 .badge-/.border-/.title- CSS 가 같은 id 로 정의.
# 카테고리 추가/이름변경: 아래 항목 수정 + 템플릿 CSS 에 동일 id 클래스 추가.
CATEGORIES = [
    ("genai",    "✨", "생성AI"),
    ("biz",      "💼", "AI기업/비즈니스"),
    ("tech",     "🔬", "AI연구/기술"),
    ("service",  "⚡", "AI활용/서비스"),
    ("policy",   "📋", "AI정책/규제"),
    ("chip",     "🔧", "AI반도체"),
    ("security", "🔒", "AI보안"),
    ("robot",    "🤖", "로봇/자율주행"),
]

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def format_dates(published_at: str) -> dict:
    """ISO 문자열 -> 화면용 날짜 문자열들."""
    dt = datetime.fromisoformat(published_at)
    date_label = f"{dt.year}년 {dt.month}월 {dt.day}일"
    weekday = WEEKDAYS_KO[dt.weekday()]
    ampm = "오전" if dt.hour < 12 else "오후"
    hour12 = dt.hour % 12 or 12
    time_label = f"{ampm} {hour12}:{dt.minute:02d}"
    return {
        "dt": dt,
        "date_label": date_label,                              # 2026년 6월 11일
        "meta_label": f"{date_label} ({weekday}) {time_label}",  # ...(목) 오전 6:30
        "footer_label": f"{date_label} {time_label}",           # ...오전 6:30
    }


def build_context(data: dict) -> dict:
    """순수 데이터 dict -> 템플릿 렌더 컨텍스트(그룹핑/통계/날짜 포맷 완료)."""
    articles = data.get("articles", [])
    known_ids = {cid for cid, _, _ in CATEGORIES}

    grouped: dict[str, list] = {}
    for art in articles:
        cid = art.get("category")
        if cid not in known_ids:
            raise ValueError(
                f"알 수 없는 카테고리 '{cid}'. 허용값: {sorted(known_ids)} "
                f"(기사: {str(art.get('title', '?'))[:40]})"
            )
        grouped.setdefault(cid, []).append(art)

    # 레지스트리 순서대로, 기사가 있는 카테고리만
    categories = [
        {"id": cid, "emoji": emoji, "label": label, "articles": grouped[cid]}
        for cid, emoji, label in CATEGORIES
        if grouped.get(cid)
    ]

    sources = data.get("sources", [])
    dates = format_dates(data["published_at"])

    return {
        "date_label": dates["date_label"],
        "meta_label": dates["meta_label"],
        "footer_label": dates["footer_label"],
        "sources_label": " · ".join(sources),
        "total_articles": len(articles),
        "source_count": len(sources),
        "category_count": len(categories),
        "categories": categories,
        "filename_stem": f"{dates['dt']:%Y%m%d_%H%M}",
    }


def render_html(ctx: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("newsletter.html").render(**ctx)


def build_text(ctx: dict) -> str:
    """HTML 비지원 메일 클라이언트용 평문 본문."""
    lines = [f"AI 뉴스레터 | {ctx['footer_label']}", ""]
    for cat in ctx["categories"]:
        lines.append(f"[{cat['emoji']} {cat['label']}] {len(cat['articles'])}개")
        for a in cat["articles"]:
            lines.append(f"- {a['title']}")
            lines.append(f"  {a['url']}")
        lines.append("")
    lines.append(ctx["sources_label"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="데이터 JSON + 템플릿 -> 뉴스레터 HTML 생성")
    parser.add_argument("data", help="데이터 JSON 경로 (예: data/20260611_0630.json)")
    parser.add_argument("-o", "--output", help="출력 HTML 경로 (기본: newsletters/YYYYMMDD_HHMM.html)")
    parser.add_argument("--send", action="store_true", help="생성 후 email_sender 로 발송")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"오류: 데이터 파일을 찾을 수 없음: {data_path}", file=sys.stderr)
        return 1

    data = json.loads(data_path.read_text(encoding="utf-8"))
    ctx = build_context(data)
    html = render_html(ctx)

    out = Path(args.output) if args.output else OUTPUT_DIR / f"{ctx['filename_stem']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(
        f"생성 완료: {out}  "
        f"({ctx['total_articles']}기사 · {ctx['source_count']}소스 · {ctx['category_count']}카테고리)"
    )

    if args.send:
        from email_sender import get_recipients, send_email

        recipients = get_recipients()
        if not recipients:
            print("오류: RECIPIENTS 환경 변수가 비어 있음.", file=sys.stderr)
            return 1
        subject = f"AI 뉴스레터 | {ctx['footer_label']}"
        text = build_text(ctx)
        print(f"발송 대상 {len(recipients)}명: {', '.join(recipients)}")
        ok = all(send_email(to, subject, text, html) for to in recipients)
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
