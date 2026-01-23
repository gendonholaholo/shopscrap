"""Command-line interface for Shopee Scraper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from shopee_scraper import __version__
from shopee_scraper.utils.logging import setup_logging


app = typer.Typer(
    name="shopee-scraper",
    help="High-performance Shopee scraper using Camoufox anti-detect browser",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# =============================================================================
# Helper Functions
# =============================================================================


def run_async(coro):
    """Run async coroutine in sync context."""
    return asyncio.run(coro)


def display_products(products: list, limit: int = 10) -> None:
    """Display products in a table."""
    from shopee_scraper.models.output import ProductOutput

    table = Table(title=f"Products Found: {len(products)}")
    table.add_column("Item ID", style="cyan")
    table.add_column("Name", style="white", max_width=40)
    table.add_column("Price", style="green")
    table.add_column("Sold", style="yellow")
    table.add_column("Rating", style="magenta")

    for product in products[:limit]:
        # Handle both ProductOutput objects and dicts
        if isinstance(product, ProductOutput):
            item_id = product.id
            name = product.title[:40]
            price = product.price
            sold = product.soldCount
            rating = product.rating
        else:
            item_id = str(product.get("item_id", ""))
            name = product.get("name", "")[:40]
            price = product.get("price", 0)
            sold = product.get("sold", 0)
            rating = product.get("rating", 0)

        table.add_row(
            str(item_id),
            name,
            f"Rp{price:,.0f}",
            str(sold),
            f"{rating:.1f}",
        )

    console.print(table)
    if len(products) > limit:
        console.print(f"[dim]... and {len(products) - limit} more[/dim]")


def display_reviews(reviews: list[dict], limit: int = 5) -> None:
    """Display reviews."""
    console.print(f"\n[bold]Reviews Found: {len(reviews)}[/bold]\n")

    for review in reviews[:limit]:
        rating = review.get("rating", 0)
        stars = "★" * rating + "☆" * (5 - rating)
        author = review.get("author", {}).get("username", "Anonymous")
        comment = review.get("comment", "")[:100]

        console.print(f"[yellow]{stars}[/yellow] by [cyan]{author}[/cyan]")
        if comment:
            console.print(f"  {comment}")
        console.print()


# =============================================================================
# Commands
# =============================================================================


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold blue]shopee-scraper[/bold blue] v{__version__}")


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Search keyword"),
    pages: int = typer.Option(1, "--pages", "-p", help="Number of pages to scrape"),
    sort: str = typer.Option(
        "relevancy",
        "--sort",
        "-s",
        help="Sort by: relevancy, sales, price_asc, price_desc",
    ),
    output: str = typer.Option(
        "./data/output",
        "--output",
        "-o",
        help="Output directory",
    ),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run headless"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Search products by keyword."""

    async def _search():
        setup_logging(level="DEBUG" if verbose else "INFO")

        from shopee_scraper.core.scraper import ShopeeScraper

        console.print(f"[bold]Searching:[/bold] {keyword}")
        console.print(f"[dim]Pages: {pages}, Sort: {sort}[/dim]\n")

        async with ShopeeScraper(headless=headless, output_dir=output) as scraper:
            products = await scraper.search(
                keyword=keyword,
                max_pages=pages,
                sort_by=sort,
            )

            if products:
                display_products(products)
                console.print(f"\n[green]✓[/green] Saved to: {output}/")
            else:
                console.print("[yellow]No products found[/yellow]")

    run_async(_search())


@app.command()
def product(
    shop_id: int = typer.Argument(..., help="Shop ID"),
    item_id: int = typer.Argument(..., help="Item ID"),
    output: str = typer.Option(
        "./data/output", "--output", "-o", help="Output directory"
    ),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run headless"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Get product detail by shop_id and item_id."""

    async def _product():
        setup_logging(level="DEBUG" if verbose else "INFO")

        from shopee_scraper.core.scraper import ShopeeScraper
        from shopee_scraper.models.output import ProductOutput

        console.print(f"[bold]Getting product:[/bold] {shop_id}/{item_id}\n")

        async with ShopeeScraper(headless=headless, output_dir=output) as scraper:
            prod = await scraper.get_product(shop_id=shop_id, item_id=item_id)

            if prod:
                # Handle both ProductOutput and dict
                if isinstance(prod, ProductOutput):
                    console.print(f"[cyan]Name:[/cyan] {prod.title}")
                    console.print(f"[green]Price:[/green] Rp{prod.price:,}")
                    console.print(f"[yellow]Stock:[/yellow] {prod.stock}")
                    console.print(f"[magenta]Sold:[/magenta] {prod.soldCount}")
                    console.print(f"[blue]Rating:[/blue] {prod.rating:.1f}")
                else:
                    console.print(f"[cyan]Name:[/cyan] {prod.get('name', 'N/A')}")
                    console.print(
                        f"[green]Price:[/green] Rp{prod.get('price', 0):,.0f}"
                    )
                    console.print(f"[yellow]Stock:[/yellow] {prod.get('stock', 0)}")
                    console.print(f"[magenta]Sold:[/magenta] {prod.get('sold', 0)}")
                    console.print(f"[blue]Rating:[/blue] {prod.get('rating', 0):.1f}")
                console.print(f"\n[green]✓[/green] Saved to: {output}/")
            else:
                console.print("[red]Product not found[/red]")

    run_async(_product())


@app.command()
def reviews(
    shop_id: int = typer.Argument(..., help="Shop ID"),
    item_id: int = typer.Argument(..., help="Item ID"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum reviews"),
    output: str = typer.Option(
        "./data/output", "--output", "-o", help="Output directory"
    ),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run headless"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Get product reviews by shop_id and item_id."""

    async def _reviews():
        setup_logging(level="DEBUG" if verbose else "INFO")

        from shopee_scraper.core.scraper import ShopeeScraper

        console.print(f"[bold]Getting reviews:[/bold] {shop_id}/{item_id}\n")

        async with ShopeeScraper(headless=headless, output_dir=output) as scraper:
            revs = await scraper.get_reviews(
                shop_id=shop_id,
                item_id=item_id,
                max_reviews=limit,
            )

            if revs:
                display_reviews(revs)
                console.print(f"[green]✓[/green] Saved to: {output}/")
            else:
                console.print("[yellow]No reviews found[/yellow]")

    run_async(_reviews())


@app.command()
def login(
    username: str = typer.Option(..., "--username", "-u", help="Shopee username/email"),
    password: str = typer.Option(
        ..., "--password", "-p", help="Shopee password", hide_input=True
    ),
    session: str = typer.Option("default", "--session", "-s", help="Session name"),
    headless: bool = typer.Option(
        False, "--headless/--no-headless", help="Run headless"
    ),
    use_anticaptcha: bool = typer.Option(
        False, "--use-anticaptcha", help="Use 2Captcha for auto-solving CAPTCHA"
    ),
    twocaptcha_key: str = typer.Option(
        None, "--2captcha-key", envvar="TWOCAPTCHA_API_KEY", help="2Captcha API key"
    ),
) -> None:
    """Login to Shopee and save session."""

    async def _login():
        setup_logging(level="INFO")

        from shopee_scraper.core.scraper import ShopeeScraper

        console.print(f"[bold]Logging in as:[/bold] {username[:3]}***\n")

        if use_anticaptcha:
            if twocaptcha_key:
                console.print("[cyan]🤖 Auto-CAPTCHA enabled (2Captcha)[/cyan]\n")
            else:
                console.print(
                    "[yellow]⚠ --use-anticaptcha requires --2captcha-key or TWOCAPTCHA_API_KEY env[/yellow]\n"
                )
                return
        else:
            console.print("[dim]Note: You may need to solve CAPTCHA manually[/dim]\n")

        async with ShopeeScraper(
            headless=headless,
            use_anticaptcha=use_anticaptcha,
            twocaptcha_api_key=twocaptcha_key,
        ) as scraper:
            success = await scraper.login(
                username=username,
                password=password,
                session_name=session,
            )

            if success:
                console.print("[green]✓ Login successful![/green]")
                console.print(f"[dim]Session saved as: {session}[/dim]")
            else:
                console.print("[red]✗ Login failed[/red]")

    run_async(_login())


@app.command()
def scrape(
    keyword: str = typer.Argument(..., help="Search keyword"),
    pages: int = typer.Option(1, "--pages", "-p", help="Number of pages to scrape"),
    output: str = typer.Option(
        "./data/output", "--output", "-o", help="Output directory"
    ),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run headless"
    ),
    max_reviews: int = typer.Option(
        5, "--max-reviews", "-r", help="Max reviews per product (0 to skip)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Search and get full details for products (with reviews)."""

    async def _scrape():
        setup_logging(level="DEBUG" if verbose else "INFO")

        from shopee_scraper.core.scraper import ShopeeScraper

        console.print(f"[bold]Scraping:[/bold] {keyword}")
        console.print(
            f"[dim]Pages: {pages}, Max reviews per product: {max_reviews}[/dim]\n"
        )

        async with ShopeeScraper(headless=headless, output_dir=output) as scraper:
            # Search now automatically fetches full details and reviews
            products = await scraper.search(
                keyword=keyword,
                max_pages=pages,
                max_reviews=max_reviews,
                save=True,
            )

            if products:
                display_products(products)
                console.print(f"\n[green]✓[/green] Output saved to: {output}/")
            else:
                console.print("[yellow]No products found[/yellow]")

    run_async(_scrape())


@app.command()
def clear_session(
    session: str = typer.Option(
        "default", "--session", "-s", help="Session name to clear"
    ),
    all_sessions: bool = typer.Option(False, "--all", "-a", help="Clear all sessions"),
) -> None:
    """Clear saved login sessions."""
    from shopee_scraper.core.session import SessionManager

    session_mgr = SessionManager()

    if all_sessions:
        import shutil

        session_dir = Path("./data/sessions")
        if session_dir.exists():
            shutil.rmtree(session_dir)
            session_dir.mkdir(parents=True)
        console.print("[green]✓ All sessions cleared[/green]")
    else:
        session_mgr.clear_session(session)
        console.print(f"[green]✓ Session '{session}' cleared[/green]")


if __name__ == "__main__":
    app()
