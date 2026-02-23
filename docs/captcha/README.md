# Shopee CAPTCHA Documentation

> Last updated: Jan 2025

## Files

| File | Content |
|------|---------|
| [selectors.md](selectors.md) | CSS selectors for CAPTCHA elements |
| [html-sample.html](html-sample.html) | HTML structure reference |
| [solving-strategy.md](solving-strategy.md) | Algorithm & approach |
| [interface.md](interface.md) | CaptchaSolver class contract |

## Quick Reference

**Type**: Slider Puzzle (drag piece to match hole)

**Key Selectors**:
- Background: `img.DfwepB`
- Puzzle: `#puzzleImgComponent`
- Slider: `#sliderContainer`

**Solving**: Find X offset via template matching or 2Captcha, then drag slider.
