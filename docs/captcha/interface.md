# CaptchaSolver Interface Contract

## Required Interface

```python
class CaptchaSolver:
    @property
    def is_available(self) -> bool:
        """Return True if solver ready"""
        ...

    async def solve_shopee_slider(self, page: Page, attempt: int = 1) -> bool:
        """
        Solve Shopee slider CAPTCHA.

        Args:
            page: Playwright Page on verify URL
            attempt: Current attempt number (for logging)

        Returns:
            True if solved successfully, False otherwise
        """
        ...


def create_captcha_solver(
    api_key: str | None = None,
    enabled: bool = True
) -> CaptchaSolver | None:
    """
    Factory function.

    Returns None if disabled or no api_key.
    """
    ...
```

## Usage in Codebase

### extractors/base.py
```python
if self.captcha_solver and self.captcha_solver.is_available:
    solved = await self.captcha_solver.solve_shopee_slider(page, attempt=attempt + 1)
```

### core/scraper.py
```python
self.captcha_solver = create_captcha_solver()
```

## Environment Variables
```
CAPTCHA_API_KEY=xxx      # Primary
TWOCAPTCHA_API_KEY=xxx   # Fallback
```
