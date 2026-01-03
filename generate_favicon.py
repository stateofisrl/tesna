"""
Generate favicon PNG files from existing icons for iOS compatibility
"""
from PIL import Image, ImageDraw, ImageFont
import os

# Ensure directories exist
os.makedirs('static/images', exist_ok=True)

# Tesla brand color (dark background with white logo outline)
background_color = (0, 0, 0)  # Black background for Tesla logo
logo_color = (255, 255, 255)  # White logo

# Create favicon sizes from scratch with Tesla "T" logo
def create_favicon(size, filename):
    img = Image.new('RGB', (size, size), background_color)
    draw = ImageDraw.Draw(img)
    
    # Draw simple Tesla "T" shape
    # Calculate proportions based on size
    margin = size // 8
    t_width = size - (2 * margin)
    t_height = size - (2 * margin)
    
    # Top bar of T (wider)
    top_bar_height = t_height // 5
    draw.rectangle(
        [(margin, margin), (margin + t_width, margin + top_bar_height)],
        fill=logo_color
    )
    
    # Vertical stem of T (centered)
    stem_width = t_width // 3
    stem_x = margin + (t_width - stem_width) // 2
    draw.rectangle(
        [(stem_x, margin), (stem_x + stem_width, margin + t_height)],
        fill=logo_color
    )
    
    img.save(filename, 'PNG')
    print(f'✅ Created {filename}')
    return img

# Generate standard favicon sizes
favicon_16 = create_favicon(16, 'static/favicon-16x16.png')
favicon_32 = create_favicon(32, 'static/favicon-32x32.png')
favicon_48 = create_favicon(48, 'static/favicon-48x48.png')

# Generate iOS/PWA icon sizes (reusing or creating)
create_favicon(180, 'static/images/icon-180x180.png')
create_favicon(192, 'static/images/icon-192x192.png')
create_favicon(512, 'static/images/icon-512x512.png')

# Create multi-resolution favicon.ico
print('\n✅ Creating favicon.ico with multiple resolutions...')
favicon_16.save(
    'static/favicon.ico',
    format='ICO',
    sizes=[(16, 16), (32, 32), (48, 48)]
)
print('✅ Created static/favicon.ico')

print('\n✅ All favicon files generated successfully!')
