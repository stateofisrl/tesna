"""
Generate PWA icons for the Tesla Investment Platform
"""
from PIL import Image, ImageDraw, ImageFont
import os

# Create images directory if it doesn't exist
os.makedirs('static/images', exist_ok=True)

# Icon sizes needed
sizes = [72, 96, 128, 144, 152, 180, 192, 384, 512]

# Tesla brand color (dark gray)
background_color = (31, 41, 55)  # Tailwind gray-800
text_color = (255, 255, 255)  # White

for size in sizes:
    # Create a new image with background
    img = Image.new('RGB', (size, size), background_color)
    draw = ImageDraw.Draw(img)
    
    # Draw a simple "T" for Tesla
    # Calculate font size based on icon size
    font_size = int(size * 0.6)
    
    try:
        # Try to use a system font
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        # Fallback to default font
        font = ImageFont.load_default()
    
    # Draw the "T" letter centered
    text = "T"
    
    # Get text bounding box for centering
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]
    
    draw.text((x, y), text, fill=text_color, font=font)
    
    # Add a subtle border
    border_width = max(1, size // 50)
    draw.rectangle(
        [(border_width, border_width), (size - border_width, size - border_width)],
        outline=(59, 130, 246),  # Tailwind blue-500
        width=border_width
    )
    
    # Save the icon
    filename = f'static/images/icon-{size}x{size}.png'
    img.save(filename, 'PNG')
    print(f'✅ Created {filename}')

print('\n✅ All PWA icons generated successfully!')
