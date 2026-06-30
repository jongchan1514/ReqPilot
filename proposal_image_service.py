from __future__ import annotations

from pathlib import Path
from typing import Any


PALETTE = {
    'bg': '#f8fafc',
    'ink': '#0f172a',
    'muted': '#64748b',
    'line': '#dbe3ef',
    'card': '#ffffff',
    'primary': '#2563eb',
    'primary_dark': '#1e40af',
    'accent': '#0f766e',
    'soft_blue': '#eff6ff',
    'soft_green': '#ecfdf5',
    'soft_slate': '#f1f5f9',
}


class ProposalImageDependencyError(RuntimeError):
    pass


Image = None
ImageDraw = None
ImageFont = None


def _ensure_pillow():
    global Image, ImageDraw, ImageFont
    if Image is not None and ImageDraw is not None and ImageFont is not None:
        return
    try:
        from PIL import Image as _Image
        from PIL import ImageDraw as _ImageDraw
        from PIL import ImageFont as _ImageFont
    except ModuleNotFoundError as exc:
        raise ProposalImageDependencyError(
            "제안 이미지 생성을 사용하려면 Pillow가 필요합니다. "
            "req-manager 환경에서 `python -m pip install Pillow==10.4.0`을 실행하세요."
        ) from exc

    Image = _Image
    ImageDraw = _ImageDraw
    ImageFont = _ImageFont


def _font(size: int, bold: bool = False):
    _ensure_pillow()
    candidates = [
        r'C:\Windows\Fonts\malgunbd.ttf' if bold else r'C:\Windows\Fonts\malgun.ttf',
        r'C:\Windows\Fonts\malgun.ttf',
        r'C:\Windows\Fonts\arial.ttf',
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int,
               max_lines: int | None = None) -> list[str]:
    text = ' '.join(str(text or '').replace('\r', ' ').split())
    if not text:
        return []

    lines: list[str] = []
    current = ''
    tokens = text.split(' ')
    for token in tokens:
        candidate = token if not current else f'{current} {token}'
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ''
            if max_lines and len(lines) >= max_lines:
                return _ellipsis_last(draw, lines, font, max_width)

        if _text_width(draw, token, font) <= max_width:
            current = token
            continue

        piece = ''
        for ch in token:
            candidate = piece + ch
            if _text_width(draw, candidate, font) <= max_width:
                piece = candidate
            else:
                if piece:
                    lines.append(piece)
                    if max_lines and len(lines) >= max_lines:
                        return _ellipsis_last(draw, lines, font, max_width)
                piece = ch
        current = piece

    if current:
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        return _ellipsis_last(draw, lines, font, max_width)
    return lines


def _ellipsis_last(draw: ImageDraw.ImageDraw, lines: list[str], font, max_width: int) -> list[str]:
    if not lines:
        return lines
    last = lines[-1]
    while last and _text_width(draw, last + '...', font) > max_width:
        last = last[:-1]
    lines[-1] = (last or '').rstrip() + '...'
    return lines


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font,
                  fill: str, max_width: int, line_gap: int = 8,
                  max_lines: int | None = None) -> int:
    x, y = xy
    lines = _wrap_text(draw, text, font, max_width, max_lines=max_lines)
    if not lines:
        return y
    line_h = font.size + line_gap
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
             fill: str, outline: str = PALETTE['line'], radius: int = 18,
             width: int = 1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _chip(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, fill: str,
          fg: str = '#ffffff') -> tuple[int, int]:
    font = _font(26, bold=True)
    w = _text_width(draw, text, font) + 34
    h = 46
    draw.rounded_rectangle((x, y, x + w, y + h), radius=23, fill=fill)
    draw.text((x + 17, y + 8), text, font=font, fill=fg)
    return w, h


def _normalize_content(content: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any]:
    req_id = requirement.get('req_id') or 'REQ'
    req_name = requirement.get('req_name') or '요구사항'
    sections = content.get('sections') if isinstance(content.get('sections'), list) else []
    while len(sections) < 4:
        sections.append({'heading': '제안 포인트', 'body': '요구사항 충족을 위한 실행 가능한 방안을 제시합니다.'})
    return {
        'title': content.get('title') or f'{req_id} {req_name}',
        'subtitle': content.get('subtitle') or '요구사항 충족을 위한 제안 장표 초안',
        'proposal_summary': content.get('proposal_summary') or requirement.get('detail') or req_name,
        'sections': sections[:4],
        'checklist': (content.get('checklist') or [])[:4],
        'keywords': (content.get('keywords') or [])[:4],
    }


def render_requirement_proposal_image(content: dict[str, Any], requirement: dict[str, Any],
                                      orientation: str, template_type: str,
                                      tone: str, output_path: str):
    _ensure_pillow()
    data = _normalize_content(content, requirement)
    if orientation == 'portrait':
        _render_portrait(data, requirement, template_type, tone, output_path)
    else:
        _render_landscape(data, requirement, template_type, tone, output_path)


def _draw_header(draw: ImageDraw.ImageDraw, data: dict[str, Any], requirement: dict[str, Any],
                 width: int, margin: int):
    req_id = requirement.get('req_id') or 'REQ'
    title_font = _font(48, bold=True)
    subtitle_font = _font(25)
    _chip(draw, req_id, margin, margin, PALETTE['primary'])
    _draw_wrapped(draw, data['title'], (margin, margin + 62), title_font,
                  PALETTE['ink'], width - margin * 2, max_lines=2)
    _draw_wrapped(draw, data['subtitle'], (margin, margin + 176), subtitle_font,
                  PALETTE['muted'], width - margin * 2, max_lines=1)


def _draw_summary(draw: ImageDraw.ImageDraw, data: dict[str, Any], box: tuple[int, int, int, int]):
    x1, y1, x2, y2 = box
    _rounded(draw, box, PALETTE['soft_blue'], '#bfdbfe', radius=20)
    draw.text((x1 + 28, y1 + 24), '제안 요약', font=_font(28, bold=True), fill=PALETTE['primary_dark'])
    _draw_wrapped(draw, data['proposal_summary'], (x1 + 28, y1 + 68), _font(25),
                  PALETTE['ink'], x2 - x1 - 56, max_lines=3)


def _draw_section_card(draw: ImageDraw.ImageDraw, item: dict[str, Any],
                       box: tuple[int, int, int, int], accent: str):
    x1, y1, x2, y2 = box
    _rounded(draw, box, PALETTE['card'], PALETTE['line'], radius=18)
    draw.rounded_rectangle((x1 + 20, y1 + 20, x1 + 70, y1 + 70), radius=14, fill=accent)
    draw.text((x1 + 34, y1 + 27), '✓', font=_font(30, bold=True), fill='#ffffff')
    draw.text((x1 + 88, y1 + 24), str(item.get('heading') or '제안 포인트'),
              font=_font(28, bold=True), fill=PALETTE['ink'])
    _draw_wrapped(draw, str(item.get('body') or ''), (x1 + 24, y1 + 90), _font(24),
                  PALETTE['muted'], x2 - x1 - 48, line_gap=9, max_lines=5)


def _draw_checklist(draw: ImageDraw.ImageDraw, checklist: list[str],
                    box: tuple[int, int, int, int]):
    x1, y1, x2, y2 = box
    _rounded(draw, box, PALETTE['soft_green'], '#bbf7d0', radius=18)
    draw.text((x1 + 24, y1 + 20), '충족 포인트', font=_font(27, bold=True), fill='#166534')
    if (y2 - y1) < 150:
        item_w = (x2 - x1 - 220) // 4
        x = x1 + 185
        for item in checklist[:4]:
            draw.ellipse((x, y1 + 35, x + 14, y1 + 49), fill=PALETTE['accent'])
            _draw_wrapped(draw, item, (x + 24, y1 + 26), _font(20), PALETTE['ink'],
                          item_w - 24, line_gap=4, max_lines=2)
            x += item_w
        return
    y = y1 + 65
    for item in checklist[:4]:
        draw.ellipse((x1 + 26, y + 8, x1 + 40, y + 22), fill=PALETTE['accent'])
        _draw_wrapped(draw, item, (x1 + 52, y), _font(23), PALETTE['ink'],
                      x2 - x1 - 76, line_gap=6, max_lines=2)
        y += 55


def _draw_keywords(draw: ImageDraw.ImageDraw, keywords: list[str], x: int, y: int):
    cursor = x
    for keyword in keywords:
        w, _ = _chip(draw, str(keyword), cursor, y, PALETTE['soft_slate'], PALETTE['primary_dark'])
        cursor += w + 12


def _render_landscape(data: dict[str, Any], requirement: dict[str, Any],
                      template_type: str, tone: str, output_path: str):
    width, height = 1600, 900
    margin = 70
    img = Image.new('RGB', (width, height), PALETTE['bg'])
    draw = ImageDraw.Draw(img)

    _draw_header(draw, data, requirement, width, margin)
    _draw_keywords(draw, data['keywords'], margin, 285)
    _draw_summary(draw, data, (margin, 350, width - margin, 485))

    gap = 26
    card_w = (width - margin * 2 - gap * 2) // 3
    card_h = 218
    y = 515
    accents = [PALETTE['primary'], '#7c3aed', '#0891b2']
    for i, item in enumerate(data['sections'][:3]):
        x = margin + i * (card_w + gap)
        _draw_section_card(draw, item, (x, y, x + card_w, y + card_h), accents[i])

    _draw_checklist(draw, data['checklist'], (margin, 758, width - margin, 845))
    draw.text((margin, height - 35), 'ReqPilot · 요구사항 기반 제안 이미지',
              font=_font(20), fill=PALETTE['muted'])
    img.save(output_path, 'PNG')


def _render_portrait(data: dict[str, Any], requirement: dict[str, Any],
                     template_type: str, tone: str, output_path: str):
    width, height = 1240, 1754
    margin = 72
    img = Image.new('RGB', (width, height), PALETTE['bg'])
    draw = ImageDraw.Draw(img)

    _draw_header(draw, data, requirement, width, margin)
    _draw_keywords(draw, data['keywords'], margin, 310)
    _draw_summary(draw, data, (margin, 380, width - margin, 555))

    y = 590
    accents = [PALETTE['primary'], '#7c3aed', '#0891b2', '#ea580c']
    for i, item in enumerate(data['sections']):
        _draw_section_card(draw, item, (margin, y, width - margin, y + 210), accents[i])
        y += 235

    _draw_checklist(draw, data['checklist'], (margin, y + 10, width - margin, y + 270))
    draw.text((margin, height - 42), 'ReqPilot · 요구사항 기반 제안 이미지',
              font=_font(22), fill=PALETTE['muted'])
    img.save(output_path, 'PNG')
