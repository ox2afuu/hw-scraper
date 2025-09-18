"""Enhanced CLI with crawler/scraper split functionality."""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from hw_scraper.config import Config, load_config
from hw_scraper.auth import AuthManager
from hw_scraper.scraper import Scraper
from hw_scraper.crawler import BFSCrawler, DFSCrawler, RobotsParser, SitemapParser
from hw_scraper.scraper import HTMLScraper, JSDetector, XPathExtractor

console = Console()


def add_crawl_command(subparsers):
    """Add crawl command to parser."""
    crawl_parser = subparsers.add_parser(
        'crawl',
        help='Crawl website to discover URLs'
    )
    crawl_parser.add_argument(
        '-u', '--url',
        type=str,
        required=True,
        help='Starting URL for crawling'
    )
    crawl_parser.add_argument(
        '--algorithm',
        choices=['bfs', 'dfs'],
        default='bfs',
        help='Crawling algorithm (default: bfs)'
    )
    crawl_parser.add_argument(
        '--max-depth',
        type=int,
        default=3,
        help='Maximum crawl depth (default: 3, -1 for unlimited)'
    )
    crawl_parser.add_argument(
        '--max-urls',
        type=int,
        default=100,
        help='Maximum URLs to crawl (default: 100, -1 for unlimited)'
    )
    crawl_parser.add_argument(
        '--domains',
        type=str,
        nargs='+',
        help='Allowed domains to crawl (default: same domain)'
    )
    crawl_parser.add_argument(
        '--respect-robots',
        action='store_true',
        default=True,
        help='Respect robots.txt (default: True)'
    )
    crawl_parser.add_argument(
        '--no-robots',
        action='store_true',
        help='Ignore robots.txt'
    )
    crawl_parser.add_argument(
        '--use-sitemap',
        action='store_true',
        default=True,
        help='Use sitemap for URL discovery (default: True)'
    )
    crawl_parser.add_argument(
        '--output',
        type=str,
        help='Save discovered URLs to file (JSON format)'
    )
    crawl_parser.add_argument(
        '--filter',
        type=str,
        help='Regex pattern to filter URLs'
    )


def add_analyze_command(subparsers):
    """Add analyze command to parser."""
    analyze_parser = subparsers.add_parser(
        'analyze',
        help='Analyze website for JavaScript and structure'
    )
    analyze_parser.add_argument(
        '-u', '--url',
        type=str,
        required=True,
        help='URL to analyze'
    )
    analyze_parser.add_argument(
        '--check-js',
        action='store_true',
        help='Check for JavaScript rendering requirements'
    )
    analyze_parser.add_argument(
        '--extract-xpath',
        type=str,
        nargs='+',
        help='XPath expressions to extract'
    )
    analyze_parser.add_argument(
        '--extract-tables',
        action='store_true',
        help='Extract all tables from page'
    )
    analyze_parser.add_argument(
        '--extract-forms',
        action='store_true',
        help='Extract form information'
    )
    analyze_parser.add_argument(
        '--extract-links',
        action='store_true',
        help='Extract all links'
    )
    analyze_parser.add_argument(
        '--output',
        type=str,
        help='Save analysis results to file (JSON format)'
    )


def add_robots_command(subparsers):
    """Add robots command to parser."""
    robots_parser = subparsers.add_parser(
        'robots',
        help='Check robots.txt for a website'
    )
    robots_parser.add_argument(
        '-u', '--url',
        type=str,
        required=True,
        help='Website URL'
    )
    robots_parser.add_argument(
        '--check-url',
        type=str,
        help='Check if specific URL is allowed'
    )
    robots_parser.add_argument(
        '--user-agent',
        type=str,
        default='*',
        help='User agent to check (default: *)'
    )
    robots_parser.add_argument(
        '--show-sitemaps',
        action='store_true',
        help='Show sitemap URLs from robots.txt'
    )
    robots_parser.add_argument(
        '--show-delay',
        action='store_true',
        help='Show crawl delay'
    )


def add_sitemap_command(subparsers):
    """Add sitemap command to parser."""
    sitemap_parser = subparsers.add_parser(
        'sitemap',
        help='Parse sitemap for a website'
    )
    sitemap_parser.add_argument(
        '-u', '--url',
        type=str,
        help='Sitemap URL (will auto-detect if not provided)'
    )
    sitemap_parser.add_argument(
        '--website',
        type=str,
        help='Website URL to find sitemaps'
    )
    sitemap_parser.add_argument(
        '--output',
        type=str,
        help='Save URLs to file'
    )
    sitemap_parser.add_argument(
        '--format',
        choices=['json', 'csv', 'txt'],
        default='json',
        help='Output format (default: json)'
    )


def handle_crawl(args) -> int:
    """Handle the crawl command."""
    config = load_config(args.config if hasattr(args, 'config') else None)

    console.print(f"[cyan]Starting crawl from {args.url}...[/cyan]")

    # Parse allowed domains
    from urllib.parse import urlparse
    parsed_url = urlparse(args.url)
    allowed_domains = args.domains if args.domains else [parsed_url.netloc]

    # Create crawler
    if args.algorithm == 'bfs':
        crawler = BFSCrawler(
            config=config,
            respect_robots=not args.no_robots,
            max_depth=args.max_depth,
            max_urls=args.max_urls,
            allowed_domains=allowed_domains
        )
    else:
        crawler = DFSCrawler(
            config=config,
            respect_robots=not args.no_robots,
            max_depth=args.max_depth,
            max_urls=args.max_urls,
            allowed_domains=allowed_domains
        )

    console.print(f"[yellow]Algorithm: {args.algorithm.upper()}[/yellow]")
    console.print(f"[yellow]Max depth: {args.max_depth}[/yellow]")
    console.print(f"[yellow]Max URLs: {args.max_urls}[/yellow]")
    console.print(f"[yellow]Allowed domains: {', '.join(allowed_domains)}[/yellow]")

    # Perform crawl
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[green]Crawling...", total=None)

        result = crawler.crawl(args.url, use_sitemap=args.use_sitemap)

        progress.update(task, completed=True)

    # Display results
    console.print(f"\n[bold]Crawl Results:[/bold]")
    console.print(f"  URLs discovered: [cyan]{len(result.discovered_urls)}[/cyan]")
    console.print(f"  URLs visited: [green]{len(result.visited_urls)}[/green]")
    console.print(f"  URLs failed: [red]{len(result.failed_urls)}[/red]")
    console.print(f"  Max depth reached: {result.max_depth_reached}")
    console.print(f"  Duration: {result.duration:.2f} seconds")
    console.print(f"  Success rate: {result.success_rate:.1%}")

    # Apply filter if provided
    urls = result.discovered_urls
    if args.filter:
        import re
        pattern = re.compile(args.filter)
        urls = {url for url in urls if pattern.search(url)}
        console.print(f"\n[yellow]Filtered to {len(urls)} URLs matching pattern[/yellow]")

    # Save results if requested
    if args.output:
        output_data = {
            'start_url': args.url,
            'algorithm': args.algorithm,
            'discovered_urls': list(urls),
            'visited_urls': list(result.visited_urls),
            'failed_urls': result.failed_urls,
            'statistics': {
                'total_discovered': len(result.discovered_urls),
                'total_visited': len(result.visited_urls),
                'total_failed': len(result.failed_urls),
                'max_depth': result.max_depth_reached,
                'duration': result.duration,
                'success_rate': result.success_rate
            }
        }

        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        console.print(f"\n[green]✓[/green] Results saved to {args.output}")

    return 0


def handle_analyze(args) -> int:
    """Handle the analyze command."""
    config = load_config(args.config if hasattr(args, 'config') else None)

    console.print(f"[cyan]Analyzing {args.url}...[/cyan]")

    scraper = HTMLScraper(config)
    results = {'url': args.url}

    # Check JavaScript if requested
    if args.check_js:
        detector = JSDetector()

        try:
            response = scraper.session.get(args.url)
            response.raise_for_status()

            js_analysis = detector.detect_javascript(response.text)
            js_data = detector.extract_js_data(response.text)

            results['javascript'] = {
                **js_analysis,
                'extracted_data': js_data
            }

            console.print("\n[bold]JavaScript Analysis:[/bold]")
            console.print(f"  Uses JavaScript: {'Yes' if js_analysis['uses_javascript'] else 'No'}")
            console.print(f"  Requires JS rendering: {'Yes' if js_analysis['requires_js_rendering'] else 'No'}")
            console.print(f"  Frameworks detected: {', '.join(js_analysis['frameworks']) or 'None'}")
            console.print(f"  Dynamic content score: {js_analysis['dynamic_content_score']}/100")

        except Exception as e:
            console.print(f"[red]JavaScript analysis failed: {e}[/red]")

    # Extract with XPath
    if args.extract_xpath:
        extractor = XPathExtractor()

        try:
            response = scraper.session.get(args.url)
            response.raise_for_status()

            xpath_results = {}
            for xpath in args.extract_xpath:
                result = extractor.extract(response.text, xpath, 'all')
                xpath_results[xpath] = result

            results['xpath_extraction'] = xpath_results

            console.print("\n[bold]XPath Extraction:[/bold]")
            for xpath, data in xpath_results.items():
                console.print(f"  {xpath}: {len(data)} result(s)")

        except Exception as e:
            console.print(f"[red]XPath extraction failed: {e}[/red]")

    # Extract tables
    if args.extract_tables:
        tables = scraper.extract_tables(args.url)
        results['tables'] = tables
        console.print(f"\n[bold]Tables:[/bold] Found {len(tables)} table(s)")

    # Extract forms
    if args.extract_forms:
        extractor = XPathExtractor()
        try:
            response = scraper.session.get(args.url)
            forms = extractor.extract_forms(response.text)
            results['forms'] = forms
            console.print(f"\n[bold]Forms:[/bold] Found {len(forms)} form(s)")
        except Exception as e:
            console.print(f"[red]Form extraction failed: {e}[/red]")

    # Extract links
    if args.extract_links:
        extractor = XPathExtractor()
        try:
            response = scraper.session.get(args.url)
            links = extractor.extract_links(response.text, base_url=args.url)
            results['links'] = links
            console.print(f"\n[bold]Links:[/bold] Found {len(links)} link(s)")
        except Exception as e:
            console.print(f"[red]Link extraction failed: {e}[/red]")

    # Save results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        console.print(f"\n[green]✓[/green] Analysis saved to {args.output}")

    return 0


def handle_robots(args) -> int:
    """Handle the robots command."""
    parser = RobotsParser()

    console.print(f"[cyan]Checking robots.txt for {args.url}...[/cyan]")

    rp = parser.fetch_robots(args.url, args.user_agent)

    if rp is None:
        console.print("[yellow]No robots.txt found (all URLs allowed)[/yellow]")
    else:
        console.print("[green]✓[/green] robots.txt found")

        if args.check_url:
            allowed = parser.can_fetch(args.check_url, args.user_agent)
            status = "[green]ALLOWED[/green]" if allowed else "[red]DISALLOWED[/red]"
            console.print(f"\nURL: {args.check_url}")
            console.print(f"Status: {status}")

        if args.show_sitemaps:
            sitemaps = parser.get_sitemaps(args.url)
            console.print(f"\n[bold]Sitemaps:[/bold]")
            for sitemap in sitemaps:
                console.print(f"  - {sitemap}")

        if args.show_delay:
            delay = parser.get_crawl_delay(args.url)
            console.print(f"\n[bold]Crawl delay:[/bold] {delay} seconds")

        # Show allowed/disallowed paths
        allowed_paths = parser.get_allowed_paths(args.url, args.user_agent)
        disallowed_paths = parser.get_disallowed_paths(args.url, args.user_agent)

        if allowed_paths:
            console.print(f"\n[bold]Explicitly allowed paths:[/bold]")
            for path in allowed_paths:
                console.print(f"  + {path}")

        if disallowed_paths:
            console.print(f"\n[bold]Disallowed paths:[/bold]")
            for path in disallowed_paths:
                console.print(f"  - {path}")

    return 0


def handle_sitemap(args) -> int:
    """Handle the sitemap command."""
    parser = SitemapParser()

    urls = set()

    if args.url:
        console.print(f"[cyan]Parsing sitemap: {args.url}...[/cyan]")
        urls = parser.parse_sitemap(args.url)
    elif args.website:
        console.print(f"[cyan]Finding sitemaps for: {args.website}...[/cyan]")
        sitemaps = parser.find_sitemaps(args.website)

        console.print(f"Found {len(sitemaps)} sitemap(s)")
        for sitemap_url in sitemaps:
            console.print(f"  - {sitemap_url}")
            sitemap_urls = parser.parse_sitemap(sitemap_url)
            urls.update(sitemap_urls)
    else:
        console.print("[red]Error: Provide either --url or --website[/red]")
        return 1

    console.print(f"\n[bold]Total URLs found:[/bold] {len(urls)}")

    # Save results
    if args.output:
        urls_list = list(urls)

        if args.format == 'json':
            with open(args.output, 'w') as f:
                json.dump(urls_list, f, indent=2)
        elif args.format == 'csv':
            import csv
            with open(args.output, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['URL'])
                for url in urls_list:
                    writer.writerow([url])
        else:  # txt
            with open(args.output, 'w') as f:
                f.write('\n'.join(urls_list))

        console.print(f"[green]✓[/green] URLs saved to {args.output}")

    return 0


def create_enhanced_parser() -> argparse.ArgumentParser:
    """Create enhanced argument parser."""
    parser = argparse.ArgumentParser(
        prog='hw-scraper',
        description='Enhanced web scraper with crawling and analysis capabilities'
    )

    parser.add_argument('--version', action='version', version='%(prog)s 0.2.0')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Add new commands
    add_crawl_command(subparsers)
    add_analyze_command(subparsers)
    add_robots_command(subparsers)
    add_sitemap_command(subparsers)

    return parser


def main_enhanced():
    """Enhanced main entry point."""
    parser = create_enhanced_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == 'crawl':
            return handle_crawl(args)
        elif args.command == 'analyze':
            return handle_analyze(args)
        elif args.command == 'robots':
            return handle_robots(args)
        elif args.command == 'sitemap':
            return handle_sitemap(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        if hasattr(args, 'verbose') and args.verbose:
            console.print_exception()
        return 1


if __name__ == "__main__":
    sys.exit(main_enhanced())