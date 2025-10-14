from io import BytesIO
import math

import qrcode
from PIL import Image, ImageDraw, ImageFont


def generate_qr(data: str, box_size: int = 8, border: int = 2) -> Image.Image:
	qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=border)
	qr.add_data(data)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white")
	return img


def generate_passport_size_qr(data: str, size_mm: tuple = (45, 35), dpi: int = 300) -> Image.Image:
	"""Generate QR code in passport photo size (45x35mm by default)"""
	# Convert mm to pixels (1 inch = 25.4mm)
	size_pixels = (int(size_mm[0] * dpi / 25.4), int(size_mm[1] * dpi / 25.4))
	
	# Generate QR with appropriate box size for the target size
	qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=1)
	qr.add_data(data)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white")
	
	# Resize to exact passport photo size
	img = img.resize(size_pixels, Image.Resampling.LANCZOS)
	return img


def generate_batch_qr_codes(data: str, count: int, size_mm: tuple = (45, 35), dpi: int = 300) -> list[Image.Image]:
	"""Generate multiple QR codes of the same data"""
	return [generate_passport_size_qr(data, size_mm, dpi) for _ in range(count)]


def create_a4_print_layout(qr_images: list[Image.Image], qr_size_mm: tuple = (45, 35), 
                          margin_mm: int = 10, spacing_mm: int = 5, dpi: int = 300) -> Image.Image:
	"""Create A4 layout with QR codes arranged in grid for printing"""
	# A4 size in mm: 210 x 297
	a4_width_mm, a4_height_mm = 210, 297
	a4_width_px = int(a4_width_mm * dpi / 25.4)
	a4_height_px = int(a4_height_mm * dpi / 25.4)
	
	# Convert sizes to pixels
	qr_width_px = int(qr_size_mm[0] * dpi / 25.4)
	qr_height_px = int(qr_size_mm[1] * dpi / 25.4)
	margin_px = int(margin_mm * dpi / 25.4)
	spacing_px = int(spacing_mm * dpi / 25.4)
	
	# Calculate grid dimensions
	available_width = a4_width_px - 2 * margin_px
	available_height = a4_height_px - 2 * margin_px
	
	cols = max(1, (available_width + spacing_px) // (qr_width_px + spacing_px))
	rows = max(1, (available_height + spacing_px) // (qr_height_px + spacing_px))
	
	# Create A4 canvas
	canvas = Image.new('RGB', (a4_width_px, a4_height_px), 'white')
	draw = ImageDraw.Draw(canvas)
	
	# Try to load a font, fallback to default if not available
	try:
		font = ImageFont.truetype("arial.ttf", 12)
	except:
		try:
			font = ImageFont.load_default()
		except:
			font = None
	
	# Place QR codes in grid
	for i, qr_img in enumerate(qr_images):
		if i >= cols * rows:
			break
			
		row = i // cols
		col = i % cols
		
		# Calculate position
		x = margin_px + col * (qr_width_px + spacing_px)
		y = margin_px + row * (qr_height_px + spacing_px)
		
		# Paste QR code
		canvas.paste(qr_img, (x, y))
		
		# Add QR number label below each QR
		if font:
			label = f"QR #{i+1}"
			text_bbox = draw.textbbox((0, 0), label, font=font)
			text_width = text_bbox[2] - text_bbox[0]
			text_x = x + (qr_width_px - text_width) // 2
			text_y = y + qr_height_px + 2
			draw.text((text_x, text_y), label, fill='black', font=font)
	
	# Add header
	if font:
		header_text = f"QR Code Batch - {len(qr_images)} codes"
		header_bbox = draw.textbbox((0, 0), header_text, font=font)
		header_width = header_bbox[2] - header_bbox[0]
		header_x = (a4_width_px - header_width) // 2
		draw.text((header_x, 5), header_text, fill='black', font=font)
	
	return canvas


def image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
	buf = BytesIO()
	img.save(buf, format=fmt)
	return buf.getvalue()
