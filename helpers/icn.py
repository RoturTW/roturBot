from PIL import Image, ImageDraw
import math

def draw(icon: str, width=40, height=40, scale=1.5):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    base_x = width / 2
    base_y = height / 2

    origin_x = base_x
    origin_y = base_y

    current_color = "#ffffff"
    line_width = 1

    def tx(x):
        return origin_x + x * scale

    def ty(y):
        return origin_y - y * scale

    def draw_line_with_caps(x1, y1, x2, y2, color, width):
        """Helper function to draw a line with rounded end caps"""
        sx1, sy1 = tx(x1), ty(y1)
        sx2, sy2 = tx(x2), ty(y2)
        
        lw = max(1, int(width * scale))
        w2 = width * scale / 2
        
        draw.line([sx1, sy1, sx2, sy2], fill=color, width=lw)
        draw.ellipse([sx1 - w2, sy1 - w2, sx1 + w2, sy1 + w2], fill=color)
        draw.ellipse([sx2 - w2, sy2 - w2, sx2 + w2, sy2 + w2], fill=color)

    commands = icon.split()
    px, py = 0, 0
    i = 0

    while i < len(commands):
        cmd = commands[i]
        i += 1

        if cmd == "w":
            line_width = float(commands[i])
            i += 1

        elif cmd == "c":
            current_color = commands[i]
            i += 1

        elif cmd == "move":
            dx = float(commands[i])
            dy = float(commands[i + 1])
            i += 2

            origin_x += dx * scale
            origin_y -= dy * scale

        elif cmd == "back":
            origin_x = base_x
            origin_y = base_y

        elif cmd == "scale":
            scale *= float(commands[i])
            i += 1

        elif cmd == "square":
            x, y, w, h = map(float, commands[i:i+4])
            i += 4

            corners = [
                (x - w, y + h),
                (x + w, y + h),
                (x + w, y - h),
                (x - w, y - h),
            ]
            
            lw = max(1, int(line_width * scale))
            w2 = line_width * scale / 2
            
            for j in range(4):
                x1, y1 = corners[j]
                x2, y2 = corners[(j + 1) % 4]
                
                sx1, sy1 = tx(x1), ty(y1)
                sx2, sy2 = tx(x2), ty(y2)
                
                draw.line([sx1, sy1, sx2, sy2], fill=current_color, width=lw)
                
                draw.ellipse(
                    [sx1 - w2, sy1 - w2, sx1 + w2, sy1 + w2],
                    fill=current_color
                )
            
            px, py = x, y

        elif cmd == "rect":
            x, y, w, h = map(float, commands[i:i+4])
            i += 4

            draw.rectangle(
                [
                    tx(x - w), ty(y + h),
                    tx(x + w), ty(y - h)
                ],
                fill=current_color
            )
            px, py = x, y

        elif cmd == "tri":
            x1, y1, x2, y2, x3, y3 = map(float, commands[i:i+6])
            i += 6

            points = [
                (tx(x1), ty(y1)),
                (tx(x2), ty(y2)),
                (tx(x3), ty(y3))
            ]
            draw.polygon(points, fill=current_color)
            
            draw_line_with_caps(x1, y1, x2, y2, current_color, line_width)
            draw_line_with_caps(x2, y2, x3, y3, current_color, line_width)
            draw_line_with_caps(x3, y3, x1, y1, current_color, line_width)
            
            px, py = x3, y3

        elif cmd == "dot":
            x, y = map(float, commands[i:i+2])
            i += 2

            r = (line_width * scale) / 2
            draw.ellipse(
                [
                    tx(x) - r, ty(y) - r,
                    tx(x) + r, ty(y) + r
                ],
                fill=current_color
            )
            px, py = x, y

        elif cmd == "line":
            x1, y1, x2, y2 = map(float, commands[i:i+4])
            i += 4

            draw_line_with_caps(x1, y1, x2, y2, current_color, line_width)
            px, py = x2, y2

        elif cmd == "cont":
            x, y = map(float, commands[i:i+2])
            i += 2

            draw_line_with_caps(px, py, x, y, current_color, line_width)
            px, py = x, y

        elif cmd == "cutcircle":
            x, y, r, direction, arclength = map(float, commands[i:i+5])
            i += 5

            dir_rad = (direction - 45) * math.pi / 18
            arc_rad = arclength * math.pi / 90

            start = dir_rad - arc_rad / 2
            end = dir_rad + arc_rad / 2

            lw = max(1, int(line_width * scale))
            w2 = line_width * scale / 2
            
            r2 = r + (line_width / 2)
            draw.arc(
                [
                    tx(x - r2), ty(y + r2),
                    tx(x + r2), ty(y - r2)
                ],
                start=math.degrees(start),
                end=math.degrees(end),
                fill=current_color,
                width=lw
            )
            
            start_x = x + r * math.cos(start)
            start_y = y + r * math.sin(start) * -1
            end_x = x + r * math.cos(end)
            end_y = y + r * math.sin(end) * -1
            
            sx1, sy1 = tx(start_x), ty(start_y)
            sx2, sy2 = tx(end_x), ty(end_y)
            
            draw.ellipse(
                [sx1 - w2, sy1 - w2, sx1 + w2, sy1 + w2],
                fill=current_color
            )
            draw.ellipse(
                [sx2 - w2, sy2 - w2, sx2 + w2, sy2 + w2],
                fill=current_color
            )
            
            px, py = x, y

        elif cmd == "ellipse":
            x, y, width, multiplier, direction = map(float, commands[i:i+5])
            i += 5

            rx = width
            ry = width * multiplier
            rot = (direction / 360) * 2 * math.pi

            steps = 64
            points = []

            for s in range(steps + 1):
                t = s / steps * 2 * math.pi
                px_local = rx * math.cos(t)
                py_local = ry * math.sin(t)

                pxr = px_local * math.cos(rot) - py_local * math.sin(rot)
                pyr = px_local * math.sin(rot) + py_local * math.cos(rot)

                points.append((tx(x + pxr), ty(y + pyr)))

            draw.line(
                points,
                fill=current_color,
                width=max(1, int(line_width * scale)),
                joint="curve"
            )
            px, py = x, y

        elif cmd == "curve":
            x1, y1, x2, y2, cx, cy = map(float, commands[i:i+6])
            i += 6

            steps = 32
            points = []

            for s in range(steps + 1):
                t = s / steps
                bx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t ** 2 * x2
                by = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t ** 2 * y2
                points.append((tx(bx), ty(by)))

            lw = max(1, int(line_width * scale))
            w2 = line_width * scale / 2
            
            draw.line(
                points,
                fill=current_color,
                width=lw
            )
            
            sx1, sy1 = tx(x1), ty(y1)
            sx2, sy2 = tx(x2), ty(y2)
            draw.ellipse(
                [sx1 - w2, sy1 - w2, sx1 + w2, sy1 + w2],
                fill=current_color
            )
            draw.ellipse(
                [sx2 - w2, sy2 - w2, sx2 + w2, sy2 + w2],
                fill=current_color
            )
            px, py = x2, y2

    return img
