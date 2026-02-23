# CAPTCHA Solving Strategy

## Method: Image Matching (Find X offset)

### Step 1: Extract Images
```python
bg_img = page.locator("img.DfwepB").get_attribute("src")  # base64
piece_img = page.locator("#puzzleImgComponent").get_attribute("src")  # base64
```

### Step 2: Find Target X Position
Option A: **Template Matching (OpenCV)**
```python
import cv2
result = cv2.matchTemplate(bg_gray, piece_gray, cv2.TM_CCOEFF_NORMED)
_, _, _, max_loc = cv2.minMaxLoc(result)
target_x = max_loc[0]
```

Option B: **2Captcha API**
```python
# Send bg + piece images, get X offset
result = solver.coordinates(bg_img, imginstructions=piece_img)
```

### Step 3: Drag Slider
```python
slider = page.locator("#sliderContainer")
box = slider.bounding_box()

# Humanize: slow drag with random speed
page.mouse.move(box["x"] + 20, box["y"] + 20)
page.mouse.down()

# Move in small steps (not instant)
for step in generate_human_path(target_x):
    page.mouse.move(box["x"] + step, box["y"] + 20)
    await asyncio.sleep(random.uniform(0.01, 0.03))

page.mouse.up()
```

## Key Points
1. **Target Y** sudah diketahui dari `#puzzleContainer` style (`translateY`)
2. Hanya perlu cari **Target X** via image matching
3. Drag harus **human-like** (tidak instan, ada variasi speed)
4. Track width = 280px, jadi X offset max ~240px (280 - 40 slider width)

## Error Handling
- Jika gagal: click `.XAny99` untuk refresh CAPTCHA
- Retry max 3x sebelum fallback ke manual
