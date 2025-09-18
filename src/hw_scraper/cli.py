"""Command-line interface for hw-scraper."""

import argparse
import sys
import json
import os
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from hw_scraper.config import Config, load_config
from hw_scraper.auth import AuthManager
from hw_scraper.scraper import Scraper
from hw_scraper.models import InputFormat, OutputFormat

console = Console()


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog='hw-scraper',
        description='Web scraper for course materials with anti-detection capabilities',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.1.0'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file (default: config.py in current dir)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Scrape command
    scrape_parser = subparsers.add_parser(
        'scrape',
        help='Scrape course materials from a URL'
    )
    scrape_parser.add_argument(
        '-u', '--url',
        type=str,
        help='URL to scrape'
    )
    scrape_parser.add_argument(
        '-i', '--input',
        type=str,
        help='Input file with URLs (JSON, XML, or CSV)'
    )
    scrape_parser.add_argument(
        '--stdin',
        action='store_true',
        help='Read URLs from stdin'
    )
    scrape_parser.add_argument(
        '-o', '--output',
        type=str,
        default='./downloads',
        help='Output directory for downloaded files (default: ./downloads)'
    )
    scrape_parser.add_argument(
        '--auth',
        choices=['env', 'keyring', 'cookies', 'prompt'],
        default='env',
        help='Authentication method (default: env)'
    )
    scrape_parser.add_argument(
        '--cookies',
        type=str,
        help='Path to cookies file (JSON or XML format)'
    )
    scrape_parser.add_argument(
        '--no-organize',
        action='store_true',
        help='Skip file organization by course/type'
    )
    scrape_parser.add_argument(
        '--impersonate',
        choices=['chrome', 'firefox', 'safari', 'edge'],
        default='chrome',
        help='Browser to impersonate (default: chrome)'
    )
    
    # Download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download files from a list of URLs'
    )
    download_parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input file with download links (JSON, XML, or CSV)'
    )
    download_parser.add_argument(
        '-o', '--output',
        type=str,
        default='./downloads',
        help='Output directory (default: ./downloads)'
    )
    download_parser.add_argument(
        '--parallel',
        type=int,
        default=3,
        help='Number of parallel downloads (default: 3)'
    )
    download_parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    # List command
    list_parser = subparsers.add_parser(
        'list',
        help='List available courses or content'
    )
    list_parser.add_argument(
        '-u', '--url',
        type=str,
        required=True,
        help='Course catalog URL'
    )
    list_parser.add_argument(
        '-f', '--format',
        choices=['table', 'json', 'csv'],
        default='table',
        help='Output format (default: table)'
    )
    list_parser.add_argument(
        '--auth',
        choices=['env', 'keyring', 'cookies', 'prompt'],
        default='env',
        help='Authentication method (default: env)'
    )
    
    # Config command
    config_parser = subparsers.add_parser(
        'config',
        help='Manage configuration settings'
    )
    config_subparsers = config_parser.add_subparsers(dest='config_action')
    
    # Config show
    config_show_parser = config_subparsers.add_parser(
        'show',
        help='Show current configuration'
    )
    
    # Config set
    config_set_parser = config_subparsers.add_parser(
        'set',
        help='Set configuration value'
    )
    config_set_parser.add_argument(
        'key',
        type=str,
        help='Configuration key (e.g., download.path)'
    )
    config_set_parser.add_argument(
        'value',
        type=str,
        help='Configuration value'
    )
    
    # Config init
    config_init_parser = config_subparsers.add_parser(
        'init',
        help='Initialize default configuration file'
    )
    config_init_parser.add_argument(
        '--path',
        type=str,
        default='./config.py',
        help='Path for configuration file (default: ./config.py)'
    )
    
    # Batch command for concurrent processing
    batch_parser = subparsers.add_parser(
        'batch',
        help='Process multiple courses concurrently'
    )
    batch_parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input file with course URLs (JSON, XML, CSV, or text)'
    )
    batch_parser.add_argument(
        '-o', '--output',
        type=str,
        default='./downloads',
        help='Output directory (default: ./downloads)'
    )
    batch_parser.add_argument(
        '-w', '--workers',
        type=int,
        default=3,
        help='Number of concurrent workers (default: 3)'
    )
    batch_parser.add_argument(
        '--worker-type',
        choices=['async', 'thread', 'process'],
        default='async',
        help='Type of workers to use (default: async)'
    )
    batch_parser.add_argument(
        '--no-checkpoint',
        action='store_true',
        help='Disable checkpointing for resume capability'
    )
    batch_parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress display'
    )
    batch_parser.add_argument(
        '--auth',
        choices=['env', 'keyring', 'cookies', 'prompt'],
        default='env',
        help='Authentication method (default: env)'
    )
    
    return parser


def handle_scrape(args) -> int:
    """Handle the scrape command."""
    config = load_config(args.config)
    
    # Determine input source
    urls = []
    
    if args.stdin:
        console.print("[cyan]Reading URLs from stdin...[/cyan]")
        for line in sys.stdin:
            line = line.strip()
            if line:
                urls.append(line)
    elif args.input:
        console.print(f"[cyan]Reading URLs from {args.input}...[/cyan]")
        urls = read_input_file(args.input)
    elif args.url:
        urls = [args.url]
    else:
        console.print("[red]Error: No input source specified. Use --url, --input, or --stdin[/red]")
        return 1
    
    if not urls:
        console.print("[yellow]Warning: No URLs to scrape[/yellow]")
        return 0
    
    # Set up authentication
    auth_manager = AuthManager(config)
    
    if args.auth == 'prompt':
        auth_manager.prompt_credentials()
    elif args.auth == 'cookies' and args.cookies:
        auth_manager.load_cookies(args.cookies)
    else:
        auth_manager.load_from_method(args.auth)
    
    # Initialize scraper
    scraper = Scraper(
        config=config,
        auth_manager=auth_manager,
        impersonate=args.impersonate
    )
    
    # Process URLs
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"[green]Scraping {len(urls)} URL(s)...", total=len(urls))
        
        for url in urls:
            console.print(f"\n[bold]Processing:[/bold] {url}")
            try:
                result = scraper.scrape_course(
                    url=url,
                    output_dir=args.output,
                    organize=not args.no_organize
                )
                console.print(f"[green]✓[/green] Successfully scraped: {result.course_name}")
                console.print(f"  Files downloaded: {result.files_count}")
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to scrape {url}: {str(e)}")
                if args.verbose:
                    console.print_exception()
            
            progress.update(task, advance=1)
    
    return 0


def handle_download(args) -> int:
    """Handle the download command."""
    config = load_config(args.config)
    
    # Read input file
    console.print(f"[cyan]Reading download links from {args.input}...[/cyan]")
    links = read_input_file(args.input)
    
    if not links:
        console.print("[yellow]Warning: No links to download[/yellow]")
        return 0
    
    from hw_scraper.downloader import DownloadManager
    
    downloader = DownloadManager(
        config=config,
        parallel=args.parallel,
        show_progress=not args.no_progress
    )
    
    console.print(f"[green]Downloading {len(links)} file(s) to {args.output}...[/green]")
    results = downloader.download_batch(links, args.output)
    
    # Summary
    successful = sum(1 for r in results if r.success)
    console.print(f"\n[bold]Download Summary:[/bold]")
    console.print(f"  Successful: [green]{successful}[/green]")
    console.print(f"  Failed: [red]{len(results) - successful}[/red]")
    
    return 0


def handle_list(args) -> int:
    """Handle the list command."""
    config = load_config(args.config)
    
    # Set up authentication
    auth_manager = AuthManager(config)
    auth_manager.load_from_method(args.auth)
    
    # Initialize scraper
    scraper = Scraper(config=config, auth_manager=auth_manager)
    
    console.print(f"[cyan]Fetching courses from {args.url}...[/cyan]")
    
    try:
        courses = scraper.list_courses(args.url)
        
        if args.format == 'table':
            table = Table(title="Available Courses")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("URL", style="blue")
            
            for course in courses:
                table.add_row(course.id, course.name, course.url)
            
            console.print(table)
        elif args.format == 'json':
            import json
            print(json.dumps([c.dict() for c in courses], indent=2))
        elif args.format == 'csv':
            import csv
            writer = csv.writer(sys.stdout)
            writer.writerow(['ID', 'Name', 'URL'])
            for course in courses:
                writer.writerow([course.id, course.name, course.url])
    except Exception as e:
        console.print(f"[red]Error fetching courses: {str(e)}[/red]")
        return 1
    
    return 0


def handle_config(args) -> int:
    """Handle the config command."""
    if args.config_action == 'init':
        from hw_scraper.config import create_default_config
        create_default_config(args.path)
        console.print(f"[green]✓[/green] Created configuration file at {args.path}")
        return 0
    
    config = load_config(args.config)
    
    if args.config_action == 'show':
        console.print("[bold]Current Configuration:[/bold]")
        for key, value in config.to_dict().items():
            if isinstance(value, dict):
                console.print(f"\n[cyan]{key}:[/cyan]")
                for k, v in value.items():
                    console.print(f"  {k}: {v}")
            else:
                console.print(f"{key}: {value}")
    elif args.config_action == 'set':
        # Parse key path (e.g., "download.path")
        keys = args.key.split('.')
        config_dict = config.to_dict()
        
        # Navigate to the correct level
        current = config_dict
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the value
        current[keys[-1]] = args.value
        
        # Save configuration
        config.update(config_dict)
        config.save()
        console.print(f"[green]✓[/green] Set {args.key} = {args.value}")
    
    return 0


def read_input_file(filepath: str) -> List[str]:
    """Read URLs from input file (JSON, XML, or CSV)."""
    path = Path(filepath)
    
    if not path.exists():
        console.print(f"[red]Error: Input file {filepath} not found[/red]")
        return []
    
    urls = []
    
    if path.suffix.lower() == '.json':
        with open(path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                urls = [item if isinstance(item, str) else item.get('url', '') for item in data]
            elif isinstance(data, dict) and 'urls' in data:
                urls = data['urls']
    elif path.suffix.lower() == '.xml':
        from lxml import etree
        tree = etree.parse(str(path))
        urls = tree.xpath('//url/text() | //link/text()')
    elif path.suffix.lower() == '.csv':
        import csv
        with open(path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    urls.append(row[0])
    else:
        # Try to read as plain text
        with open(path, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    
    return [url for url in urls if url]


def handle_batch(args) -> int:
    """Handle the batch command for concurrent processing."""
    import asyncio
    from hw_scraper.batch_processor import BatchProcessor
    from hw_scraper.models import WorkerConfig, WorkerType
    
    config = load_config(args.config)
    
    # Read URLs from input file
    console.print(f"[cyan]Reading URLs from {args.input}...[/cyan]")
    urls = read_input_file(args.input)
    
    if not urls:
        console.print("[yellow]Warning: No URLs to process[/yellow]")
        return 0
    
    console.print(f"[green]Found {len(urls)} URLs to process[/green]")
    
    # Set up authentication
    auth_manager = AuthManager(config)
    auth_manager.load_from_method(args.auth)
    
    # Configure workers
    worker_type_map = {
        'async': WorkerType.ASYNC,
        'thread': WorkerType.THREAD,
        'process': WorkerType.PROCESS
    }
    
    worker_config = WorkerConfig(
        max_workers=args.workers,
        worker_type=worker_type_map[args.worker_type],
        enable_checkpointing=not args.no_checkpoint
    )
    
    # Run batch processing
    async def run_batch():
        async with BatchProcessor(config, auth_manager, worker_config) as processor:
            result = await processor.process_courses(
                urls,
                output_dir=args.output,
                checkpoint=not args.no_checkpoint,
                progress=not args.no_progress
            )
            
            # Display summary
            console.print("\n[bold]Batch Processing Complete[/bold]")
            console.print(f"Total tasks: {result.total_tasks}")
            console.print(f"Completed: [green]{result.completed_tasks}[/green]")
            console.print(f"Failed: [red]{result.failed_tasks}[/red]")
            console.print(f"Success rate: {result.success_rate:.1%}")
            console.print(f"Files downloaded: {result.total_files_downloaded}")
            console.print(f"Duration: {result.duration:.1f} seconds")
            
            return result
    
    try:
        result = asyncio.run(run_batch())
        return 0 if result.failed_tasks == 0 else 1
    except Exception as e:
        console.print(f"[red]Batch processing failed: {str(e)}[/red]")
        if args.verbose:
            console.print_exception()
        return 1


def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'scrape':
            return handle_scrape(args)
        elif args.command == 'download':
            return handle_download(args)
        elif args.command == 'list':
            return handle_list(args)
        elif args.command == 'config':
            return handle_config(args)
        elif args.command == 'batch':
            return handle_batch(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        if hasattr(args, 'verbose') and args.verbose:
            console.print_exception()
        return 1


if __name__ == "__main__":
    sys.exit(main())