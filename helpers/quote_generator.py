import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pilmoji import Pilmoji
import textwrap
from datetime import datetime

class QuoteGenerator:
    def __init__(self):
        self.width = 600
        self.height = 600
        self.bg_color = (54, 57, 63)
        self.text_color = (220, 221, 222)
        self.author_color = (255, 255, 255)
        self.timestamp_color = (163, 166, 170)
        self.avatar_size = 256
        self.padding = 40
        self.message_bg_color = (64, 68, 75)
        self.border_radius = 12
        
    async def download_avatar(self, avatar_url):
        """Download avatar image from URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as response:
                    if response.status == 200:
                        avatar_data = await response.read()
                        return Image.open(io.BytesIO(avatar_data))
        except Exception as e:
            print(f"Error downloading avatar: {e}")
        return None
    
    def create_circular_avatar(self, avatar_img):
        """Convert avatar to circular shape"""
        if not avatar_img:
            return None
            
        if avatar_img.mode != 'RGBA':
            avatar_img = avatar_img.convert('RGBA')
            
        avatar_img = avatar_img.resize((self.avatar_size, self.avatar_size), Image.Resampling.LANCZOS)
        
        circular_img = Image.new('RGBA', (self.avatar_size, self.avatar_size), (0, 0, 0, 0))
        
        mask = Image.new('L', (self.avatar_size, self.avatar_size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, self.avatar_size, self.avatar_size), fill=255)
        
        circular_img.paste(avatar_img, (0, 0))
        circular_img.putalpha(mask)
        
        return circular_img
    
    def create_discord_background(self):
        """Create a Discord-style background"""
        bg = Image.new('RGB', (self.width, self.height), self.bg_color)
        return bg
    
    def draw_rounded_rectangle(self, draw, bbox, radius, fill_color):
        """Draw a rounded rectangle"""
        x1, y1, x2, y2 = bbox
        
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill_color)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill_color)
        
        draw.pieslice([x1, y1, x1 + 2*radius, y1 + 2*radius], 180, 270, fill=fill_color)
        draw.pieslice([x2 - 2*radius, y1, x2, y1 + 2*radius], 270, 360, fill=fill_color)
        draw.pieslice([x1, y2 - 2*radius, x1 + 2*radius, y2], 90, 180, fill=fill_color)
        draw.pieslice([x2 - 2*radius, y2 - 2*radius, x2, y2], 0, 90, fill=fill_color)

    def get_font(self, size, bold=False):
        """Get font with best Unicode support available"""
        unicode_fonts = [
            "/System/Library/Fonts/Arial Unicode MS.ttf",  # Best Unicode coverage
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SF-Pro-Display-Bold.otf" if bold else "/System/Library/Fonts/SF-Pro-Display-Regular.otf",
            "/System/Library/Fonts/SF-Pro-Text-Bold.otf" if bold else "/System/Library/Fonts/SF-Pro-Text-Regular.otf",
            "/System/Library/Fonts/PingFang.ttc",  # Good for CJK
            "/System/Library/Fonts/Hiragino Sans GB.ttc",  # Good for CJK
            
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            
            "/Windows/Fonts/Arial Unicode MS.ttf",
            "/Windows/Fonts/arialbd.ttf" if bold else "/Windows/Fonts/arial.ttf",
            "/Windows/Fonts/seguiemj.ttf",  # Segoe UI Emoji
            "/Windows/Fonts/msgothic.ttc",  # Good for Japanese
        ]
        
        for font_path in unicode_fonts:
            try:
                font = ImageFont.truetype(font_path, size)
                try:
                    test_bbox = font.getbbox("あ")
                    if test_bbox[2] > test_bbox[0]:
                        return font
                except:
                    pass
                return font
            except:
                continue
        
        return ImageFont.load_default()
    
    def wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width"""
        if not text.strip():
            return ["[No message content]"]
            
        words = text.split()
        processed_words = []
        for word in words:
            if len(word) > 40:
                processed_words.extend([word[i:i+40] for i in range(0, len(word), 40)])
            else:
                processed_words.append(word)
        
        final_lines = []
        current_line_words = []
        
        for word in processed_words:
            test_line = " ".join(current_line_words + [word])
            bbox = font.getbbox(test_line)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line_words.append(word)
            else:
                if current_line_words:
                    final_lines.append(" ".join(current_line_words))
                current_line_words = [word]
                
                bbox = font.getbbox(word)
                if bbox[2] - bbox[0] > max_width:
                    for i in range(0, len(word), 20):
                        chunk = word[i:i+20]
                        final_lines.append(chunk)
                    current_line_words = []
        
        if current_line_words:
            final_lines.append(" ".join(current_line_words))
        
        return final_lines[:10]
    
    def safe_text_render(self, img, position, text, font, color):
        """Safely render text with emoji support using Pilmoji"""
        try:
            with Pilmoji(img) as pilmoji:
                pilmoji.text(position, text, font=font, fill=color)
        except Exception as e:
            try:
                draw = ImageDraw.Draw(img)
                draw.text(position, text, font=font, fill=color)
            except Exception as e2:
                try:
                    draw = ImageDraw.Draw(img)
                    ascii_text = ''.join(char if ord(char) < 128 else '?' for char in text)
                    draw.text(position, ascii_text, font=font, fill=color)
                except Exception as e3:
                    draw = ImageDraw.Draw(img)
                    draw.text(position, "[Unable to render text]", font=font, fill=color)
    
    async def generate_quote_image(self, author_name, author_avatar_url, message_content, timestamp=None):
        """Generate a square Discord-style quote image with centered avatar and text below"""
        try:
            
            avatar_img = await self.download_avatar(author_avatar_url)
            
            img = self.create_discord_background()
            draw = ImageDraw.Draw(img)
            
            circular_avatar = self.create_circular_avatar(avatar_img)
            
            author_font = self.get_font(28, bold=True)
            message_font = self.get_font(22)
            timestamp_font = self.get_font(18)
            
            img = img.convert('RGBA')
            
            avatar_x = (self.width - self.avatar_size) // 2
            avatar_y = self.padding
            
            if circular_avatar:
                img.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)
            else:
                draw = ImageDraw.Draw(img)
                draw.ellipse([avatar_x, avatar_y, avatar_x + self.avatar_size, avatar_y + self.avatar_size], 
                           fill=(99, 102, 107))
                initials = "".join([word[0].upper() for word in author_name.split()[:2]])
                initial_font = self.get_font(36, bold=True)
                bbox = initial_font.getbbox(initials)
                initial_width = bbox[2] - bbox[0]
                initial_height = bbox[3] - bbox[1]
                initial_x = avatar_x + (self.avatar_size - initial_width) // 2
                initial_y = avatar_y + (self.avatar_size - initial_height) // 2
                self.safe_text_render(img, (initial_x, initial_y), initials, initial_font, self.author_color)
            
            author_y = avatar_y + self.avatar_size + 20
            author_bbox = author_font.getbbox(author_name)
            author_width = author_bbox[2] - author_bbox[0]
            author_x = (self.width - author_width) // 2
            
            draw = ImageDraw.Draw(img)
            self.safe_text_render(img, (author_x, author_y), author_name, author_font, self.author_color)
            
            timestamp_y = author_y + 35
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = timestamp
                    time_str = dt.strftime("%m/%d/%Y")
                    
                    timestamp_bbox = timestamp_font.getbbox(time_str)
                    timestamp_width = timestamp_bbox[2] - timestamp_bbox[0]
                    timestamp_x = (self.width - timestamp_width) // 2
                    
                    self.safe_text_render(img, (timestamp_x, timestamp_y), time_str, timestamp_font, self.timestamp_color)
                    timestamp_y += 30
                except:
                    pass

            message_start_y = timestamp_y + 20
            text_width = self.width - (self.padding * 2)

            wrapped_lines = self.wrap_text(message_content, message_font, text_width - 40)

            line_height = 28
            message_height = len(wrapped_lines) * line_height + 30

            available_height = self.height - message_start_y - self.padding
            if message_height > available_height:
                max_lines = max(1, (available_height - 30) // line_height)
                wrapped_lines = wrapped_lines[:max_lines]
                message_height = len(wrapped_lines) * line_height + 30
            
            msg_bg_x1 = self.padding
            msg_bg_y1 = message_start_y
            msg_bg_x2 = self.width - self.padding
            msg_bg_y2 = message_start_y + message_height
            
            self.draw_rounded_rectangle(draw, (msg_bg_x1, msg_bg_y1, msg_bg_x2, msg_bg_y2), 
                                      self.border_radius, self.message_bg_color)
            
            text_start_x = self.padding + 20
            message_content_y = message_start_y + 15

            for i, line in enumerate(wrapped_lines):
                y_pos = message_content_y + (i * line_height)
                if y_pos + line_height > msg_bg_y2 - 15:
                    if i < len(wrapped_lines) - 1:
                        self.safe_text_render(img, (text_start_x, y_pos), "...", message_font, self.text_color)
                    break
                
                line_bbox = message_font.getbbox(line)
                line_width = line_bbox[2] - line_bbox[0]
                line_x = (self.width - line_width) // 2
                
                self.safe_text_render(img, (line_x, y_pos), line, message_font, self.text_color)
            
            final_img = Image.new('RGB', (self.width, self.height), self.bg_color)
            final_img.paste(img, (0, 0), img if img.mode == 'RGBA' else None)
            
            output = io.BytesIO()
            final_img.save(output, format='PNG', quality=95)
            output.seek(0)
            
            return output
            
        except Exception as e:
            print(f"Error generating quote image: {e}")
            import traceback
            traceback.print_exc()
            return None

quote_generator = QuoteGenerator()
