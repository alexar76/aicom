import sys
import statistics
from PIL import Image

path = sys.argv[1]
img = Image.open(path).convert('L')
w, h = img.size
crop = img.crop((w // 5, h // 5, 4 * w // 5, 4 * h // 5))
pixels = list(crop.getdata())
mean = sum(pixels) / len(pixels)
std = statistics.pstdev(pixels)
if mean < 32 and std < 42:
    print(f'FAIL dark/flat mean={mean:.1f} std={std:.1f}')
    sys.exit(1)
print(f'ok mean={mean:.1f} std={std:.1f}')
