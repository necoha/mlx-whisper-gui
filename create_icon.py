#!/usr/bin/env python3
"""
Create an icon for the MLX Whisper GUI application
"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_app_icon():
    # Create a 1024x1024 icon (macOS standard)
    size = 1024
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Create a modern gradient background
    for y in range(size):
        # Gradient from blue to purple
        r = int(75 + (y / size) * 50)   # 75 -> 125
        g = int(120 + (y / size) * 30)  # 120 -> 150
        b = int(200 + (y / size) * 55)  # 200 -> 255
        color = (r, g, b, 255)
        draw.line([(0, y), (size, y)], fill=color)
    
    # Add rounded corners
    mask = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = size // 8
    mask_draw.rounded_rectangle(
        [0, 0, size, size], 
        radius=corner_radius, 
        fill=(255, 255, 255, 255)
    )
    
    # Apply mask
    img = Image.alpha_composite(
        Image.new('RGBA', img.size, (0, 0, 0, 0)),
        Image.alpha_composite(mask, img)
    )
    
    # Add microphone icon
    mic_color = (255, 255, 255, 220)
    center_x, center_y = size // 2, size // 2
    
    # Microphone body (capsule shape)
    mic_width = size // 6
    mic_height = size // 3
    mic_top = center_y - mic_height // 2
    mic_bottom = center_y + mic_height // 2
    
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [center_x - mic_width//2, mic_top, center_x + mic_width//2, mic_bottom],
        radius=mic_width//2,
        fill=mic_color
    )
    
    # Microphone stand
    stand_width = size // 20
    stand_height = size // 8
    draw.rectangle(
        [center_x - stand_width//2, mic_bottom, center_x + stand_width//2, mic_bottom + stand_height],
        fill=mic_color
    )
    
    # Base
    base_width = size // 4
    base_height = size // 30
    draw.rounded_rectangle(
        [center_x - base_width//2, mic_bottom + stand_height, 
         center_x + base_width//2, mic_bottom + stand_height + base_height],
        radius=base_height//2,
        fill=mic_color
    )
    
    # Sound waves
    wave_color = (255, 255, 255, 150)
    for i in range(3):
        radius = mic_width//2 + (i + 1) * size//12
        arc_width = size // 40
        # Left arc
        draw.arc(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            start=135, end=225, fill=wave_color, width=arc_width
        )
        # Right arc  
        draw.arc(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            start=315, end=45, fill=wave_color, width=arc_width
        )
    
    return img

def create_icns_file():
    """Create .icns file for macOS"""
    icon = create_app_icon()
    
    # Create iconset directory
    iconset_dir = "icon.iconset"
    os.makedirs(iconset_dir, exist_ok=True)
    
    # Define required icon sizes for macOS
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png")
    ]
    
    # Generate all required sizes
    for size, filename in sizes:
        resized_icon = icon.resize((size, size), Image.Resampling.LANCZOS)
        resized_icon.save(os.path.join(iconset_dir, filename))
    
    # Convert to .icns using iconutil
    os.system(f"iconutil -c icns {iconset_dir}")
    
    # Clean up iconset directory
    import shutil
    shutil.rmtree(iconset_dir)
    
    print("✅ Icon created: icon.icns")

if __name__ == "__main__":
    create_icns_file()