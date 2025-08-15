"""
Main CLI interface for Claude.ai share URL scraper.
"""

import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .scraper import ClaudeShareScraper
from .parser import ConversationParser
from .cache import CacheManager
from .utils import is_valid_claude_share_url, extract_share_id


console = Console()


@click.group()
@click.version_option()
def cli():
    """Claude.ai share URL scraper - Download and parse conversations into markdown."""
    pass


@cli.command()
@click.argument('url')
@click.option('--cache-dir', '-c', default='cache', 
              help='Cache directory path (default: cache)')
@click.option('--rate-limit', '-r', default='1.0,3.0',
              help='Rate limit range in seconds: min,max (default: 1.0,3.0)')
@click.option('--timeout', '-t', default=30,
              help='Request timeout in seconds (default: 30)')
@click.option('--max-retries', default=3,
              help='Maximum retry attempts (default: 3)')
@click.option('--force', '-f', is_flag=True,
              help='Force re-download even if cached')
@click.option('--no-markdown', is_flag=True,
              help='Skip markdown generation (download HTML only)')
def scrape(url: str, cache_dir: str, rate_limit: str, timeout: int, 
           max_retries: int, force: bool, no_markdown: bool):
    """Scrape a single Claude.ai share URL."""
    
    # Validate URL
    if not is_valid_claude_share_url(url):
        console.print(f"[red]Error: Invalid Claude.ai share URL: {url}[/red]")
        sys.exit(1)
    
    # Parse rate limit
    try:
        min_delay, max_delay = map(float, rate_limit.split(','))
    except ValueError:
        console.print("[red]Error: Invalid rate limit format. Use: min,max[/red]")
        sys.exit(1)
    
    share_id = extract_share_id(url)
    console.print(f"Processing share ID: {share_id}")
    
    # Initialize components
    cache_manager = CacheManager(cache_dir)
    
    # Check if already cached
    if not force and cache_manager.conversation_exists(share_id):
        console.print("[green]Conversation already cached![/green]")
        conv_path = cache_manager.get_conversation_path(share_id)
        console.print(f"Location: {conv_path}")
        return
    
    # Scrape the conversation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # Download HTML
        task = progress.add_task("Downloading conversation...", total=None)
        
        scraper = ClaudeShareScraper(
            rate_limit_delay=(min_delay, max_delay),
            timeout=timeout,
            max_retries=max_retries
        )
        
        # Use advanced method that tries all bypass techniques
        result = scraper.fetch_conversation_advanced(url)
        
        scraper.close()
        
        if not result['success']:
            progress.remove_task(task)
            console.print(f"[red]Failed to download: {result['error']}[/red]")
            sys.exit(1)
        
        progress.update(task, description="Parsing HTML content...")
        
        # Parse HTML
        parser = ConversationParser()
        parsed_data = parser.parse_html(result['html_content'], url)
        
        if not parsed_data['success']:
            progress.remove_task(task)
            console.print(f"[red]Failed to parse: {parsed_data['error']}[/red]")
            sys.exit(1)
        
        progress.update(task, description="Saving to cache...")
        
        # Create cache entry
        metadata = parsed_data['metadata']
        conversation_date = None
        if metadata.get('date'):
            from datetime import datetime
            try:
                conversation_date = datetime.fromisoformat(metadata['date'].replace('Z', '+00:00'))
            except:
                pass
        
        conv_dir = cache_manager.create_conversation_entry(
            share_id=share_id,
            title=metadata['title'],
            url=url,
            conversation_date=conversation_date
        )
        
        # Save HTML
        cache_manager.save_raw_html(share_id, result['html_content'])
        
        # Save metadata
        cache_manager.save_metadata(share_id, metadata)
        
        # Generate and save markdown
        if not no_markdown:
            progress.update(task, description="Generating markdown...")
            markdown_content = parser.generate_markdown(parsed_data)
            cache_manager.save_markdown(share_id, markdown_content)
        
        progress.remove_task(task)
    
    console.print("[green]Successfully scraped conversation![/green]")
    console.print(f"Saved to: {conv_dir}")
    console.print(f"Title: {metadata['title']}")
    console.print(f"Messages: {len(parsed_data['messages'])}")


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--cache-dir', '-c', default='cache',
              help='Cache directory path (default: cache)')
@click.option('--rate-limit', '-r', default='1.0,3.0',
              help='Rate limit range in seconds: min,max (default: 1.0,3.0)')
@click.option('--timeout', '-t', default=30,
              help='Request timeout in seconds (default: 30)')
@click.option('--max-retries', default=3,
              help='Maximum retry attempts (default: 3)')
@click.option('--force', '-f', is_flag=True,
              help='Force re-download even if cached')
@click.option('--continue-on-error', is_flag=True,
              help='Continue processing other URLs if one fails')
def batch(file_path: str, cache_dir: str, rate_limit: str, timeout: int,
          max_retries: int, force: bool, continue_on_error: bool):
    """Scrape multiple URLs from a text file (one URL per line)."""
    
    # Parse rate limit
    try:
        min_delay, max_delay = map(float, rate_limit.split(','))
    except ValueError:
        console.print("[red]Error: Invalid rate limit format. Use: min,max[/red]")
        sys.exit(1)
    
    # Read URLs from file
    try:
        with open(file_path, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        sys.exit(1)
    
    # Filter valid URLs
    valid_urls = []
    for url in urls:
        if is_valid_claude_share_url(url):
            valid_urls.append(url)
        else:
            console.print(f"[yellow]Skipping invalid URL: {url}[/yellow]")
    
    if not valid_urls:
        console.print("[red]No valid Claude.ai share URLs found[/red]")
        sys.exit(1)
    
    console.print(f"Processing {len(valid_urls)} URLs...")
    
    # Initialize components
    cache_manager = CacheManager(cache_dir)
    scraper = ClaudeShareScraper(
        rate_limit_delay=(min_delay, max_delay),
        timeout=timeout,
        max_retries=max_retries
    )
    parser = ConversationParser()
    
    success_count = 0
    error_count = 0
    
    # Process URLs
    with Progress(console=console) as progress:
        task = progress.add_task("Processing URLs...", total=len(valid_urls))
        
        for i, url in enumerate(valid_urls):
            share_id = extract_share_id(url)
            progress.update(task, description=f"Processing {i+1}/{len(valid_urls)}: {share_id[:8]}...")
            
            try:
                # Check if already cached
                if not force and cache_manager.conversation_exists(share_id):
                    console.print(f"Skipping cached: {share_id[:8]}")
                    success_count += 1
                    continue
                
                # Scrape conversation using advanced method with all bypass techniques
                result = scraper.fetch_conversation_advanced(url)
                
                if not result['success']:
                    console.print(f"[red]Failed {share_id[:8]}: {result['error']}[/red]")
                    if not continue_on_error:
                        break
                    error_count += 1
                    continue
                
                # Parse HTML
                parsed_data = parser.parse_html(result['html_content'], url)
                
                if not parsed_data['success']:
                    console.print(f"[red]Parse error {share_id[:8]}: {parsed_data['error']}[/red]")
                    if not continue_on_error:
                        break
                    error_count += 1
                    continue
                
                # Save to cache
                metadata = parsed_data['metadata']
                conversation_date = None
                if metadata.get('date'):
                    from datetime import datetime
                    try:
                        conversation_date = datetime.fromisoformat(metadata['date'].replace('Z', '+00:00'))
                    except:
                        pass
                
                conv_dir = cache_manager.create_conversation_entry(
                    share_id=share_id,
                    title=metadata['title'],
                    url=url,
                    conversation_date=conversation_date
                )
                
                cache_manager.save_raw_html(share_id, result['html_content'])
                cache_manager.save_metadata(share_id, metadata)
                
                markdown_content = parser.generate_markdown(parsed_data)
                cache_manager.save_markdown(share_id, markdown_content)
                
                console.print(f"[green]Saved: {metadata['title'][:50]}...[/green]")
                success_count += 1
                
            except Exception as e:
                console.print(f"[red]Unexpected error {share_id[:8]}: {e}[/red]")
                if not continue_on_error:
                    break
                error_count += 1
            
            progress.advance(task)
    
    scraper.close()
    
    console.print(f"\nResults: {success_count} successful, {error_count} failed")


@cli.command()
@click.option('--cache-dir', '-c', default='cache',
              help='Cache directory path (default: cache)')
def list_cache(cache_dir: str):
    """List all cached conversations."""
    
    cache_manager = CacheManager(cache_dir)
    conversations = cache_manager.get_cached_conversations()
    
    if not conversations:
        console.print("[yellow]No cached conversations found[/yellow]")
        return
    
    table = Table(title="Cached Conversations")
    table.add_column("Share ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("Date", style="blue")
    table.add_column("Messages", justify="right", style="magenta")
    table.add_column("Directory", style="yellow")
    
    for conv in conversations:
        title = conv['title'][:50] + "..." if len(conv['title']) > 50 else conv['title']
        date_str = conv['date'][:10] if conv['date'] else 'Unknown'
        
        table.add_row(
            conv['share_id'][:8],
            title,
            date_str,
            str(conv.get('message_count', '?')),
            conv['directory']
        )
    
    console.print(table)


@cli.command()
@click.option('--cache-dir', '-c', default='cache',
              help='Cache directory path (default: cache)')
def stats(cache_dir: str):
    """Show cache statistics."""
    
    cache_manager = CacheManager(cache_dir)
    stats_data = cache_manager.get_cache_stats()
    
    console.print("[bold]Cache Statistics[/bold]")
    console.print(f"Total conversations: {stats_data['total_conversations']}")
    console.print(f"Total size: {stats_data['total_size_mb']} MB")
    console.print(f"Cache directory: {stats_data['cache_directory']}")
    console.print(f"Last updated: {stats_data.get('last_updated', 'Unknown')}")
    
    console.print("\nFile counts:")
    for file_type, count in stats_data['file_counts'].items():
        console.print(f"  {file_type}: {count}")


@cli.command()
@click.option('--cache-dir', '-c', default='cache',
              help='Cache directory path (default: cache)')
@click.option('--yes', '-y', is_flag=True,
              help='Skip confirmation prompt')
def cleanup(cache_dir: str, yes: bool):
    """Clean up empty cache directories."""
    
    if not yes:
        if not click.confirm("This will remove empty cache directories. Continue?"):
            return
    
    cache_manager = CacheManager(cache_dir)
    cleaned = cache_manager.cleanup_empty_directories()
    
    if cleaned > 0:
        console.print(f"[green]Cleaned up {cleaned} empty directories[/green]")
    else:
        console.print("[blue]No empty directories found[/blue]")


@cli.command()
@click.argument('url')
def debug(url: str):
    """Debug cloudscraper functionality."""
    import cloudscraper
    import time
    
    console.print(f"Testing cloudscraper with: {url}")
    
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'darwin', 'desktop': True}
        )
        
        console.print("Visiting main page...")
        main_response = scraper.get('https://claude.ai/')
        console.print(f"Main page status: {main_response.status_code}")
        
        time.sleep(2)
        
        console.print("Visiting share URL...")
        response = scraper.get(url)
        console.print(f"Share URL status: {response.status_code}")
        
        if response.status_code == 200:
            console.print(f"[green]Success! Content length: {len(response.text)}[/green]")
        else:
            console.print(f"[red]Failed with status {response.status_code}[/red]")
            console.print(f"Response preview: {response.text[:200]}")
            
    except Exception as e:
        console.print(f"[red]Exception: {e}[/red]")


@cli.command()
@click.argument('url')
def debug_browser(url: str):
    """Debug browser-based scraping functionality."""
    from .scraper import ClaudeShareScraper
    
    console.print(f"Testing browser scraper with: {url}")
    console.print("Note: First run may take longer as ChromeDriver downloads...")
    
    try:
        scraper = ClaudeShareScraper()
        result = scraper.fetch_conversation_with_browser(url)
        scraper.close()
        
        if result['success']:
            console.print(f"[green]Success! Content length: {len(result['html_content'])}[/green]")
            # Quick check if we have actual conversation content
            if 'message' in result['html_content'].lower():
                console.print("[green]✓ Found message content in HTML[/green]")
            else:
                console.print("[yellow]⚠ No message content found - may still be loading page[/yellow]")
        else:
            console.print(f"[red]Failed: {result['error']}[/red]")
            
    except Exception as e:
        console.print(f"[red]Exception: {e}[/red]")


@cli.command()
@click.argument('url')
def debug_seleniumbase(url: str):
    """Debug SeleniumBase UC Mode functionality."""
    from .scraper import ClaudeShareScraper
    
    console.print(f"Testing SeleniumBase UC Mode with: {url}")
    console.print("Note: This will open a visible browser window...")
    
    try:
        scraper = ClaudeShareScraper()
        result = scraper.fetch_conversation_with_seleniumbase_uc(url)
        scraper.close()
        
        if result['success']:
            console.print(f"[green]Success! Content length: {len(result['html_content'])}[/green]")
            # Quick check for conversation content
            content_lower = result['html_content'].lower()
            if 'message' in content_lower or 'conversation' in content_lower:
                console.print("[green]✓ Found conversation content in HTML[/green]")
            else:
                console.print("[yellow]⚠ No conversation content found[/yellow]")
        else:
            console.print(f"[red]Failed: {result['error']}[/red]")
            
    except Exception as e:
        console.print(f"[red]Exception: {e}[/red]")


@cli.command()
@click.argument('url')
def debug_undetected(url: str):
    """Debug undetected-chromedriver functionality."""
    from .scraper import ClaudeShareScraper
    
    console.print(f"Testing undetected-chromedriver with: {url}")
    console.print("Note: This will open a visible browser window...")
    
    try:
        scraper = ClaudeShareScraper()
        result = scraper.fetch_conversation_with_undetected_chrome(url)
        scraper.close()
        
        if result['success']:
            console.print(f"[green]Success! Content length: {len(result['html_content'])}[/green]")
            # Quick check for conversation content
            content_lower = result['html_content'].lower()
            if 'message' in content_lower or 'conversation' in content_lower:
                console.print("[green]✓ Found conversation content in HTML[/green]")
            else:
                console.print("[yellow]⚠ No conversation content found[/yellow]")
        else:
            console.print(f"[red]Failed: {result['error']}[/red]")
            
    except Exception as e:
        console.print(f"[red]Exception: {e}[/red]")


@cli.command()
@click.argument('url')
def debug_all_methods(url: str):
    """Test all bypass methods sequentially for comparison."""
    from .scraper import ClaudeShareScraper
    
    console.print(f"Testing all bypass methods with: {url}")
    console.print("This will try each method and show results...\n")
    
    scraper = ClaudeShareScraper()
    
    methods = [
        ("Cloudscraper", scraper.fetch_conversation),
        ("Standard Browser", scraper.fetch_conversation_with_browser),
        ("Undetected ChromeDriver", scraper.fetch_conversation_with_undetected_chrome),
        ("SeleniumBase UC Mode", scraper.fetch_conversation_with_seleniumbase_uc)
    ]
    
    results = []
    
    for method_name, method_func in methods:
        console.print(f"Testing {method_name}...")
        
        try:
            result = method_func(url)
            
            if result['success']:
                content_len = len(result['html_content'])
                has_conversation = 'message' in result['html_content'].lower()
                status = f"✅ Success - {content_len} chars, conversation: {has_conversation}"
            else:
                status = f"❌ Failed - {result['error']}"
                
        except Exception as e:
            status = f"💥 Crashed - {str(e)}"
        
        results.append((method_name, status))
        console.print(f"   {status}\n")
    
    scraper.close()
    
    # Summary
    console.print("[bold]Summary:[/bold]")
    for method_name, status in results:
        console.print(f"  {method_name}: {status}")


if __name__ == "__main__":
    cli()