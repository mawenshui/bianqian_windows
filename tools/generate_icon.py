# -*- coding: utf-8 -*-
"""
生成桌面便签应用图标（icon.png + icon.ico）

生成一个经典的黄色便签图标，包含折角和图钉元素。
输出多种尺寸以适应不同场景：
- 256x256 PNG（用于 Qt 窗口/托盘图标）
- 包含多尺寸的 ICO 文件（用于 Windows 快捷方式/任务栏）
"""

import os
import sys
from PIL import Image, ImageDraw

def create_icon(size=256):
    """创建一个便签图标，返回 PIL Image 对象"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 便签主体颜色 — 温暖黄色
    note_color = (255, 235, 130, 255)
    note_shadow = (0, 0, 0, 40)
    note_border = (220, 200, 100, 255)
    pin_color = (200, 50, 50, 255)
    pin_shadow = (150, 30, 30, 80)
    fold_color = (230, 210, 100, 255)
    
    margin = int(size * 0.06)    # 外边距
    radius = int(size * 0.06)    # 圆角半径
    fold_size = int(size * 0.22) # 折角大小
    pin_size = int(size * 0.08)  # 图钉头大小
    
    # 便签主体矩形坐标
    x1, y1 = margin, margin
    x2, y2 = size - margin, size - margin
    
    # 阴影偏移
    shadow_offset = int(size * 0.025)
    
    # 绘制阴影（圆角矩形）
    sx1, sy1 = x1 + shadow_offset, y1 + shadow_offset
    sx2, sy2 = x2 + shadow_offset, y2 + shadow_offset
    draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=radius + shadow_offset, fill=note_shadow)
    
    # 绘制便签主体
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=note_color, outline=note_border, width=max(1, size // 80))
    
    # 绘制折角（右下角三角形）
    fx, fy = x2 - fold_size, y2
    draw.polygon([
        (x2 - fold_size, y2 - fold_size + (fold_size // 3)),  # 折痕起点
        (x2, y2 - fold_size),
        (x2, y2),
        (x2 - fold_size, y2),
    ], fill=fold_color, outline=note_border)
    
    # 在图钉区域上方留白（给图钉空间）
    pin_center_x = size // 2
    pin_center_y = margin + pin_size + margin // 2
    
    # 绘制图钉（红色圆形头部）
    draw.ellipse([
        pin_center_x - pin_size,
        pin_center_y - pin_size,
        pin_center_x + pin_size,
        pin_center_y + pin_size + pin_size // 4
    ], fill=pin_color)
    
    # 图钉高光
    highlight_size = pin_size // 2
    draw.ellipse([
        pin_center_x - highlight_size // 2,
        pin_center_y - highlight_size,
        pin_center_x + highlight_size // 2,
        pin_center_y - highlight_size // 2
    ], fill=(255, 180, 180, 180))
    
    # 图钉针（向下延伸的线）
    needle_width = max(1, size // 80)
    draw.line([
        (pin_center_x, pin_center_y + pin_size // 2),
        (pin_center_x, pin_center_y + pin_size + pin_size // 2)
    ], fill=pin_shadow, width=needle_width)

    # 便签上的横线（模拟书写线）
    line_spacing = int(size * 0.08)
    line_y_start = pin_center_y + pin_size + pin_size + margin
    line_margin_left = margin + int(size * 0.1)
    line_margin_right = x2 - int(size * 0.1)
    
    num_lines = 4
    for i in range(num_lines):
        ly = line_y_start + i * line_spacing
        if ly < y2 - fold_size - margin // 2:
            # 线的长度随折角变化（下方线更短）
            right_edge = line_margin_right
            if i >= num_lines - 2:
                right_edge = x2 - fold_size - margin // 2
            draw.line([(line_margin_left, ly), (right_edge, ly)], fill=(210, 195, 120, 120), width=1)
    
    # 正文模拟文字块
    text_margin_left = line_margin_left + int(size * 0.02)
    char_spacing = int(size * 0.04)
    char_width = int(size * 0.02)
    char_height = int(size * 0.012)
    text_color = (180, 170, 140, 160)
    
    for i in range(num_lines):
        ty = line_y_start + i * line_spacing - int(size * 0.02)
        if ty < y2 - fold_size - margin:
            # 每行不同长度的文字模拟
            chars_count = 8 - i * 1
            right_edge = text_margin_left + chars_count * char_spacing
            if right_edge > x2 - fold_size - margin // 2:
                right_edge = x2 - fold_size - margin // 2
            for j in range(chars_count):
                cx = text_margin_left + j * char_spacing
                if cx + char_width < right_edge:
                    draw.rounded_rectangle([cx, ty, cx + char_width, ty + char_height], radius=1, fill=text_color)
    
    return img


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 生成 256x256 的图标
    icon = create_icon(256)
    
    # 保存 PNG（Qt 使用）
    png_path = os.path.join(project_dir, 'icon.png')
    icon.save(png_path, 'PNG')
    print(f'✅ 已生成 PNG 图标: {png_path}')
    
    # 生成 ICO（Windows 使用，包含多种尺寸）
    sizes = [256, 128, 64, 48, 32, 16]
    icons = []
    for s in sizes:
        icons.append(create_icon(s))
    
    ico_path = os.path.join(project_dir, 'icon.ico')
    icons[0].save(ico_path, 'ICO', sizes=[(s, s) for s in sizes], append_images=icons[1:])
    print(f'✅ 已生成 ICO 图标: {ico_path} (含 {",".join(str(s) for s in sizes)} 尺寸)')
    
    print('\n图标生成完成！')


if __name__ == '__main__':
    main()
