"""
HTML parser for Claude.ai share URLs to extract conversation content.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup, Tag, NavigableString

from .utils import extract_share_id, parse_iso_date, truncate_text


class ConversationParser:
    """Parser for Claude.ai share page HTML to extract conversation data."""
    
    def __init__(self):
        """Initialize the parser."""
        self.share_id = None
        self.title = None
        self.messages = []
        self.metadata = {}
    
    def parse_html(self, html_content: str, url: str) -> Dict[str, Any]:
        """
        Parse HTML content from Claude share page.
        
        Args:
            html_content: Raw HTML content
            url: Original share URL
            
        Returns:
            Dictionary containing parsed conversation data
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract share ID from URL
            self.share_id = extract_share_id(url)
            
            # Extract conversation metadata
            self.title = self._extract_title(soup)
            conversation_date = self._extract_date(soup)
            
            # Extract conversation messages
            self.messages = self._extract_messages(soup)
            
            # Build metadata
            self.metadata = {
                'share_id': self.share_id,
                'title': self.title,
                'url': url,
                'date': conversation_date.isoformat() if conversation_date else None,
                'message_count': len(self.messages),
                'parsed_at': datetime.now().isoformat()
            }
            
            return {
                'success': True,
                'metadata': self.metadata,
                'messages': self.messages,
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'metadata': {},
                'messages': [],
                'error': f"Parsing error: {str(e)}"
            }
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract conversation title from HTML."""
        # Try various title selectors
        title_selectors = [
            '.truncate',  # Claude's current UI stores title in div with truncate class
            'title',
            'h1',
            '[data-testid="chat-title"]',
            '.chat-title',
            '.conversation-title'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element and element.get_text().strip():
                title = element.get_text().strip()
                # Clean up title
                title = re.sub(r'\s*\|\s*Claude.*$', '', title)  # Remove "| Claude" suffix
                title = re.sub(r'\s+', ' ', title)  # Normalize whitespace
                if title and title != 'Claude':
                    return title
        
        return 'Untitled Conversation'
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract conversation date from HTML."""
        # Claude share pages don't reliably contain conversation date metadata
        # Most dates found in the HTML are from unrelated content or JavaScript
        # Return None to indicate no reliable date found
        return None
    
    def _extract_messages(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract conversation messages from HTML."""
        messages = []
        
        # Look for actual conversation structure in modern Claude UI
        # Search for the conversation container first
        conversation_container = None
        
        # Try to find the main conversation area
        conversation_selectors = [
            'main',
            '[role="main"]',
            '.conversation',
            '.chat-container',
            '#chat',
            '.messages-container'
        ]
        
        for selector in conversation_selectors:
            container = soup.select_one(selector)
            if container:
                conversation_container = container
                break
        
        if not conversation_container:
            conversation_container = soup
        
        # Look for message turn patterns in the conversation
        # Modern Claude UI likely has alternating message blocks
        message_elements = self._find_message_turns(conversation_container)
        
        # Parse each message turn
        for i, element in enumerate(message_elements):
            message = self._parse_message_element(element, i)
            if message and message['content'].strip():
                messages.append(message)
        
        return messages
        
    def _find_message_turns(self, container: BeautifulSoup) -> List[Tag]:
        """Find individual message turns in the conversation using Claude.ai's specific structure."""
        messages = []
        
        # Find user messages: look for containers with the user message testid, then find their parent containers
        user_containers = []
        for user_msg in container.find_all(attrs={'data-testid': 'user-message'}):
            # Find the parent container that has the rounded styling
            parent = user_msg
            for _ in range(10):  # Look up to find the styled container
                if parent.parent:
                    parent = parent.parent
                    classes = parent.get('class', [])
                    if classes and 'rounded-xl' in ' '.join(classes) and 'bg-bg-300' in ' '.join(classes):
                        user_containers.append(parent)
                        break
                else:
                    break
        
        # Find Claude responses: look for the streaming containers
        claude_containers = []
        for div in container.find_all('div', attrs={'data-is-streaming': 'false'}):
            claude_containers.append(div)
        
        # Combine and sort by document order
        all_containers = []
        
        for user_div in user_containers:
            all_containers.append(('user', user_div, self._get_simple_position(user_div)))
            
        for claude_div in claude_containers:
            all_containers.append(('claude', claude_div, self._get_simple_position(claude_div)))
        
        # Sort by position to maintain conversation order
        all_containers.sort(key=lambda x: x[2])
        
        # Return just the elements
        return [container[1] for container in all_containers]
    
    def _get_simple_position(self, element: Tag) -> int:
        """Get a simple position indicator for sorting based on document order."""
        # Find this element's position by counting preceding elements
        position = 0
        current = element
        
        # Count all elements that come before this one in document order
        while current:
            # Count preceding siblings
            for sibling in current.previous_siblings:
                if hasattr(sibling, 'name'):
                    position += 1
                    
            # Move up to parent
            current = current.parent
            if current:
                position += 1000  # Give significant weight to parent level
        
        return position
    
    def _calculate_content_richness(self, element: Tag, text: str) -> int:
        """Calculate how rich/meaningful the content in this element is."""
        score = 0
        
        # Check for code blocks (high value)
        if element.find('pre') or element.find('code'):
            score += 3
        
        # Check for structured content
        if element.find(['ul', 'ol', 'table']):
            score += 2
        
        # Check for substantial text
        if len(text) > 500:
            score += 2
        elif len(text) > 200:
            score += 1
        
        # Check for conversation patterns
        if any(pattern in text.lower() for pattern in [
            'what', 'how', 'why', 'can you', 'let me', 'here\'s', 'this is',
            'looking at', 'i think', 'the quest', 'fascinating', 'brilliant'
        ]):
            score += 1
        
        # Check for technical content
        if any(term in text.lower() for term in [
            'function', 'algorithm', 'model', 'system', 'code', 'language',
            'implementation', 'framework', 'api', 'data', 'analysis'
        ]):
            score += 1
        
        # Penalize very repetitive content
        lines = text.split('\n')
        unique_lines = set(line.strip() for line in lines if line.strip())
        if len(lines) > 5 and len(unique_lines) / len(lines) < 0.3:
            score -= 2
        
        return max(0, score)
    
    def _overlaps_with_selected(self, element: Tag, selected: List[Tag]) -> bool:
        """Check if element overlaps with any already selected elements."""
        for selected_element in selected:
            # Check if one contains the other
            if (element in selected_element.descendants or 
                selected_element in element.descendants):
                return True
        return False
    
    def _looks_like_message_content(self, element: Tag, text: str) -> bool:
        """Check if element looks like it contains message content."""
        # Look for indicators of message content
        message_indicators = [
            # Check for code blocks
            element.find('pre') is not None,
            element.find('code') is not None,
            # Check for question patterns
            '?' in text and len(text) > 30,
            # Check for substantial paragraphs
            len(text) > 100,
            # Check for numbered lists or bullets
            any(pattern in text for pattern in ['1.', '2.', '•', '-', '*']),
            # Check for common conversation starters
            any(starter in text.lower() for starter in [
                'what', 'how', 'why', 'when', 'where', 'can you', 'please',
                'i think', 'let me', 'here\'s', 'this is', 'looking at'
            ])
        ]
        
        return any(message_indicators)
    
    def _is_nested_in_message(self, element: Tag, message_list: List[Tag]) -> bool:
        """Check if element is nested inside an already identified message."""
        for message in message_list:
            if element in message.descendants:
                return True
        return False
    
    def _get_element_position(self, element: Tag) -> int:
        """Get the position of element in document order."""
        # Simple position calculation based on document order
        position = 0
        for el in element.parent.children if element.parent else []:
            if el == element:
                break
            if hasattr(el, 'name'):
                position += 1
        return position
    
    def _get_element_position_in_document(self, element: Tag) -> int:
        """Get the absolute position of element in the entire document."""
        # Walk up to find all elements before this one in document order
        position = 0
        current = element
        
        # Find the root of the document
        while current.parent:
            # Count preceding siblings
            for sibling in current.parent.children:
                if sibling == current:
                    break
                if hasattr(sibling, 'name'):
                    position += self._count_descendants(sibling)
            current = current.parent
        
        return position
    
    def _count_descendants(self, element: Tag) -> int:
        """Count all descendant elements."""
        if not hasattr(element, 'descendants'):
            return 1
        count = 1
        for desc in element.descendants:
            if hasattr(desc, 'name'):
                count += 1
        return count
    
    def _find_alternating_content(self, soup: BeautifulSoup) -> List[Tag]:
        """Find alternating conversation content when standard selectors fail."""
        # Look for patterns that suggest conversation structure
        content_blocks = []
        
        # Try to find main content area
        main_selectors = ['main', '.main-content', '#main', '.chat-container', '.conversation']
        main_element = None
        
        for selector in main_selectors:
            element = soup.select_one(selector)
            if element:
                main_element = element
                break
        
        if not main_element:
            main_element = soup
        
        # Look for div elements that might contain conversation content
        potential_messages = main_element.find_all('div')
        
        # Filter for elements that look like messages (have substantial text content)
        for div in potential_messages:
            text = div.get_text().strip()
            if len(text) > 20 and not self._is_ui_element(div):
                content_blocks.append(div)
        
        return content_blocks
    
    def _is_ui_element(self, element: Tag) -> bool:
        """Check if element is likely a UI element rather than message content."""
        # Check for common UI classes/attributes
        ui_indicators = [
            'button', 'nav', 'header', 'footer', 'sidebar', 'menu',
            'toolbar', 'tooltip', 'modal', 'popup', 'loading'
        ]
        
        class_str = ' '.join(element.get('class', [])).lower()
        id_str = (element.get('id') or '').lower()
        
        for indicator in ui_indicators:
            if indicator in class_str or indicator in id_str:
                return True
        
        # Check if element has form controls
        if element.find(['input', 'button', 'select', 'textarea']):
            return True
        
        return False
    
    def _parse_message_element(self, element: Tag, index: int) -> Optional[Dict[str, Any]]:
        """Parse individual message element."""
        if not element:
            return None
        
        # Determine message role (human vs assistant)
        role = self._determine_message_role(element, index)
        
        # Extract content
        content = self._extract_message_content(element)
        
        if not content.strip():
            return None
        
        return {
            'role': role,
            'content': content,
            'index': index,
            'timestamp': None  # Could be extracted if available
        }
    
    def _determine_message_role(self, element: Tag, index: int) -> str:
        """Determine if message is from human or assistant using Claude.ai specific structure."""
        # Check for specific Claude.ai data attributes
        user_message = element.find(attrs={'data-testid': 'user-message'})
        if user_message:
            return 'human'
            
        # Check for user avatar indicator (letter "D")
        if element.find('div', string='D'):
            return 'human'
        
        # Check for Claude response indicators by examining immediate children
        for child in element.children:
            if hasattr(child, 'get') and child.get('class'):
                child_classes = child.get('class', [])
                if 'font-claude-response' in child_classes:
                    return 'assistant'
        
        # Also check deeper for data-is-streaming  
        claude_response = element.find(attrs={'data-is-streaming': 'false'})
        if claude_response:
            return 'assistant'
        
        # Check class names for additional patterns
        class_str = ' '.join(element.get('class', [])).lower()
        if 'user-message' in class_str or 'human-message' in class_str:
            return 'human'
        if 'claude-message' in class_str or 'assistant-message' in class_str:
            return 'assistant'
        
        # Check for text patterns
        text = element.get_text().lower()
        if text.startswith(('human:', 'user:', 'me:')):
            return 'human'
        if text.startswith(('claude:', 'assistant:', 'ai:')):
            return 'assistant'
        
        # Default to alternating pattern (typically human starts)
        return 'human' if index % 2 == 0 else 'assistant'
    
    def _extract_message_content(self, element: Tag) -> str:
        """Extract and format message content as markdown."""
        # Check if this is a user message first
        user_message_element = element.find(attrs={'data-testid': 'user-message'})
        if user_message_element:
            # For user messages, extract the content directly from the user-message element
            return user_message_element.get_text(strip=True)
        
        # For Claude responses, separate thinking process from main response
        content_parts = []
        
        # Extract thinking process if present
        thinking_content = self._extract_thinking_process(element)
        if thinking_content:
            content_parts.append(f"**Thinking Process:**\n\n{thinking_content}")
        
        # Extract main response content
        main_content = self._extract_claude_main_response(element)
        if main_content:
            content_parts.append(main_content)
        
        return '\n\n'.join(content_parts).strip()
    
    def _extract_thinking_process(self, element: Tag) -> str:
        """Extract the thinking process content from the collapsible section."""
        # Find the font-claude-response container
        claude_response_div = None
        for child in element.children:
            if hasattr(child, 'get') and child.get('class'):
                if 'font-claude-response' in child.get('class', []):
                    claude_response_div = child
                    break
        
        if not claude_response_div:
            return ""
        
        # Look for the thinking process container - it has p-3, pt-0, pr-8 classes
        for div in claude_response_div.find_all('div'):
            classes = div.get('class', [])
            class_str = ' '.join(classes)
            
            if ('grid-cols-1' in class_str and 
                'p-3' in class_str and 
                'pt-0' in class_str and 
                'pr-8' in class_str):
                return self._extract_structured_content(div)
        
        return ""
    
    def _extract_claude_main_response(self, element: Tag) -> str:
        """Extract Claude's main response content, preserving order and structure."""
        # Find the font-claude-response container
        claude_response_div = None
        for child in element.children:
            if hasattr(child, 'get') and child.get('class'):
                if 'font-claude-response' in child.get('class', []):
                    claude_response_div = child
                    break
        
        if not claude_response_div:
            return ""
        
        # Look for the main response container - it has basic grid classes but NOT the padding classes
        for div in claude_response_div.find_all('div'):
            classes = div.get('class', [])
            class_str = ' '.join(classes)
            
            # Main response has grid-cols-1 and gap-2.5 but NOT p-3/pt-0/pr-8
            if ('grid-cols-1' in class_str and 
                'gap-2.5' in class_str and
                'p-3' not in class_str and
                'pt-0' not in class_str and
                'pr-8' not in class_str):
                return self._extract_structured_content(div)
        
        return ""
    
    def _extract_structured_content(self, container: Tag) -> str:
        """Extract content from a container while preserving structure and order."""
        content_parts = []
        
        # Process all child elements in document order
        for child in container.children:
            if hasattr(child, 'name'):
                formatted_content = self._format_html_element(child)
                if formatted_content and formatted_content.strip():
                    content_parts.append(formatted_content.strip())
        
        return '\n\n'.join(content_parts)
    
    def _extract_artifacts(self, element: Tag) -> List[str]:
        """Extract artifacts and structured content."""
        artifacts = []
        
        # Look for artifact containers or structured content
        artifact_selectors = [
            '.artifact',
            '.code-artifact', 
            '.document-artifact',
            '[data-artifact]',
            '.attachment'
        ]
        
        for selector in artifact_selectors:
            artifact_elements = element.select(selector)
            for artifact in artifact_elements:
                title = artifact.get('data-title') or artifact.get('title') or 'Artifact'
                content = artifact.get_text(strip=True)
                if content:
                    artifacts.append(f"**{title}:**\n\n{content}")
        
        return artifacts
    
    def _extract_code_blocks(self, element: Tag) -> List[str]:
        """Extract code blocks with proper formatting and Pygments highlighting."""
        code_blocks = []
        
        # Look for Claude's actual code block structure: <pre class="code-block__code"><code>
        code_pres = element.find_all('pre', class_='code-block__code')
        for code_pre in code_pres:
            code_elem = code_pre.find('code')
            if code_elem:
                # Extract clean code content without HTML styling
                code_content = self._extract_clean_code_content(code_elem)
                
                # Detect language from various sources
                language = self._detect_code_language(code_elem)
                
                # Apply Pygments highlighting if available
                if code_content.strip():
                    highlighted_code = self._apply_pygments_highlighting(code_content, language)
                    code_blocks.append(highlighted_code)
        
        # Fallback: Look for other code blocks
        if not code_blocks:
            fallback_selectors = ['pre code', 'code']
            for selector in fallback_selectors:
                code_elements = element.select(selector)
                for code_elem in code_elements:
                    # Skip if already processed above
                    if self._already_processed_code_block(code_elem, code_blocks):
                        continue
                        
                    # Skip inline code (short single-line code)
                    text = code_elem.get_text()
                    if len(text) < 20 or '\n' not in text:
                        continue
                        
                    code_content = self._extract_clean_code_content(code_elem)
                    language = self._detect_code_language(code_elem)
                    
                    if code_content.strip():
                        highlighted_code = self._apply_pygments_highlighting(code_content, language)
                        code_blocks.append(highlighted_code)
        
        return code_blocks
    
    def _is_language_indicator(self, element: Tag) -> bool:
        """Check if element is a language indicator div."""
        classes = element.get('class', [])
        class_str = ' '.join(classes)
        
        # Claude uses: class="text-text-500 font-small p-3.5 pb-0"
        return ('text-text-500' in class_str and 
                'font-small' in class_str and 
                'p-3.5' in class_str)
    
    def _extract_clean_code_content(self, code_elem: Tag) -> str:
        """Extract clean code content, removing HTML styling but preserving structure."""
        # Create a copy to avoid modifying original
        elem_copy = code_elem.__copy__()
        
        # Remove all span elements but keep their text content
        for span in elem_copy.find_all('span'):
            span.replace_with(span.get_text())
        
        # Get the text and clean it up
        code_text = elem_copy.get_text()
        
        # Clean up common artifacts
        lines = code_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove leading/trailing whitespace but preserve indentation structure
            cleaned_line = line.rstrip()
            cleaned_lines.append(cleaned_line)
        
        return '\n'.join(cleaned_lines)
    
    def _already_processed_code_block(self, code_elem: Tag, existing_blocks: List[str]) -> bool:
        """Check if this code block was already processed."""
        code_content = self._extract_clean_code_content(code_elem)
        code_snippet = code_content[:100]  # First 100 chars for comparison
        
        for block in existing_blocks:
            if code_snippet in block:
                return True
        return False
    
    def _apply_pygments_highlighting(self, code_content: str, language: str) -> str:
        """Apply Pygments syntax highlighting to code content."""
        try:
            from pygments import highlight
            from pygments.lexers import get_lexer_by_name, guess_lexer
            from pygments.formatters import get_formatter_by_name
            from pygments.util import ClassNotFound
            
            # Try to get lexer for the specified language
            lexer = None
            if language:
                try:
                    lexer = get_lexer_by_name(language, stripall=True)
                except ClassNotFound:
                    # Try common language mappings
                    language_mappings = {
                        'javascript': 'js',
                        'typescript': 'ts', 
                        'shell': 'bash',
                        'yaml': 'yml'
                    }
                    mapped_lang = language_mappings.get(language.lower(), language)
                    try:
                        lexer = get_lexer_by_name(mapped_lang, stripall=True)
                    except ClassNotFound:
                        pass
            
            # If no lexer found, try to guess from content
            if not lexer:
                try:
                    lexer = guess_lexer(code_content)
                    language = lexer.aliases[0] if lexer.aliases else 'text'
                except ClassNotFound:
                    language = 'text'
            
            # Format as markdown code block with language
            return f"```{language}\n{code_content}\n```"
            
        except ImportError:
            # Pygments not available, fall back to basic formatting
            language = language or ''
            return f"```{language}\n{code_content}\n```"
    
    def _detect_code_language(self, code_element: Tag) -> str:
        """Detect programming language from code element."""
        # Check element classes for language hints
        classes = code_element.get('class', [])
        for cls in classes:
            if isinstance(cls, str):
                # Common language class patterns
                if cls.startswith('language-'):
                    return cls.replace('language-', '')
                elif cls.startswith('lang-'):
                    return cls.replace('lang-', '')
                elif cls in ['python', 'javascript', 'java', 'cpp', 'csharp', 'go', 'rust', 'typescript']:
                    return cls
        
        # Check parent element classes
        parent = code_element.parent
        if parent:
            parent_classes = parent.get('class', [])
            for cls in parent_classes:
                if isinstance(cls, str) and cls.startswith('language-'):
                    return cls.replace('language-', '')
        
        # Try to detect from content patterns
        content = code_element.get_text()
        if content:
            content_lower = content.lower()
            if any(pattern in content_lower for pattern in ['def ', 'import ', 'python']):
                return 'python'
            elif any(pattern in content_lower for pattern in ['function', 'const ', 'let ', '=>']):
                return 'javascript'
            elif 'SELECT' in content.upper() and 'FROM' in content.upper():
                return 'sql'
            elif any(pattern in content for pattern in ['#include', 'std::', 'int main']):
                return 'cpp'
        
        return ''
    
    def _extract_tool_usage(self, element: Tag) -> List[str]:
        """Extract tool usage, web searches, and other special content."""
        tool_content = []
        
        # Look for web search results
        search_indicators = element.find_all(string=re.compile(r'web search|search results|fetched|favicon', re.I))
        if search_indicators:
            # This might contain web search results
            search_text = element.get_text()
            if any(indicator in search_text.lower() for indicator in ['web search', 'fetched', 'search results']):
                tool_content.append("**Web Search Results:**\n\n" + self._clean_search_results(search_text))
        
        # Look for other tool usage patterns
        tool_patterns = [
            (r'Failed to fetch', 'Network Request'),
            (r'Analyzing|Examined|Investigating', 'Analysis'),
            (r'Probed|Pondered', 'Thinking Process')
        ]
        
        text = element.get_text()
        for pattern, tool_type in tool_patterns:
            if re.search(pattern, text, re.I):
                relevant_text = self._extract_relevant_context(text, pattern)
                if relevant_text:
                    tool_content.append(f"**{tool_type}:**\n\n{relevant_text}")
        
        return tool_content
    
    def _clean_search_results(self, text: str) -> str:
        """Clean and format web search results."""
        # Remove excessive whitespace and format nicely
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    def _extract_relevant_context(self, text: str, pattern: str) -> str:
        """Extract relevant context around a pattern match."""
        # Find the line containing the pattern and surrounding context
        lines = text.split('\n')
        relevant_lines = []
        
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.I):
                # Include some context around the match
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                relevant_lines.extend(lines[start:end])
                break
        
        return '\n'.join(relevant_lines) if relevant_lines else text[:200]
    
    def _extract_text_content(self, element: Tag) -> str:
        """Extract main text content, filtering out code blocks and artifacts already processed."""
        # Clone the element to avoid modifying the original
        element_copy = element.__copy__()
        
        # Remove code blocks that we've already processed
        for code_block in element_copy.select('pre, .code-block'):
            code_block.decompose()
        
        # Remove any artifact containers
        for artifact in element_copy.select('.artifact, [data-artifact]'):
            artifact.decompose()
        
        # Process remaining child elements
        content = []
        for child in element_copy.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    content.append(text)
            elif isinstance(child, Tag):
                formatted = self._format_html_element(child)
                if formatted:
                    content.append(formatted)
        
        return '\n'.join(content).strip()
    
    def _format_html_element(self, element: Tag) -> str:
        """Format HTML element as markdown."""
        if not element or not element.name:
            return ""
        tag_name = element.name.lower()
        
        # Handle different HTML elements
        if tag_name == 'p':
            return element.get_text().strip()
        
        elif tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_name[1])
            return f"{'#' * level} {element.get_text().strip()}"
        
        elif tag_name == 'strong' or tag_name == 'b':
            return f"**{element.get_text().strip()}**"
        
        elif tag_name == 'em' or tag_name == 'i':
            return f"*{element.get_text().strip()}*"
        
        elif tag_name == 'code':
            return f"`{element.get_text()}`"
        
        elif tag_name == 'pre':
            code_element = element.find('code')
            if code_element:
                # Use the improved code extraction with Pygments
                code_content = self._extract_clean_code_content(code_element)
                language = self._detect_code_language(code_element)
                return self._apply_pygments_highlighting(code_content, language)
            else:
                code_content = element.get_text()
                return f"```\n{code_content}\n```"
        
        elif tag_name == 'a':
            href = element.get('href', '')
            text = element.get_text().strip()
            return f"[{text}]({href})" if href else text
        
        elif tag_name == 'ul':
            items = []
            for li in element.find_all('li'):
                items.append(f"- {li.get_text().strip()}")
            return '\n'.join(items)
        
        elif tag_name == 'ol':
            items = []
            for i, li in enumerate(element.find_all('li')):
                items.append(f"{i+1}. {li.get_text().strip()}")
            return '\n'.join(items)
        
        elif tag_name == 'blockquote':
            lines = element.get_text().strip().split('\n')
            return '\n'.join(f"> {line}" for line in lines)
        
        elif tag_name == 'table':
            return self._format_table(element)
        
        elif tag_name == 'div':
            # Check if div contains a code block
            code_pre = element.find('pre', class_='code-block__code')
            if code_pre:
                # This div contains a code block, format it properly
                return self._format_html_element(code_pre)
            else:
                # For regular div elements, just return the text content
                return element.get_text().strip()
        
        else:
            # For unknown elements, return text content
            return element.get_text().strip()
    
    def _format_table(self, table: Tag) -> str:
        """Format HTML table as markdown table."""
        rows = []
        
        # Get all rows
        for row in table.find_all('tr'):
            cells = []
            for cell in row.find_all(['td', 'th']):
                cells.append(cell.get_text().strip())
            
            if cells:
                rows.append('| ' + ' | '.join(cells) + ' |')
                
                # Add header separator after first row if it contains th elements
                if row.find('th') and len(rows) == 1:
                    separator = '| ' + ' | '.join(['---'] * len(cells)) + ' |'
                    rows.append(separator)
        
        return '\n'.join(rows)
    
    def generate_markdown(self, parsed_data: Dict[str, Any]) -> str:
        """
        Generate markdown content from parsed conversation data.
        
        Args:
            parsed_data: Dictionary from parse_html method
            
        Returns:
            Formatted markdown string
        """
        if not parsed_data['success']:
            return f"# Error\n\n{parsed_data['error']}"
        
        metadata = parsed_data['metadata']
        messages = parsed_data['messages']
        
        # Build markdown content
        markdown_parts = []
        
        # Title and metadata
        title = metadata.get('title', 'Untitled Conversation')
        markdown_parts.append(f"# {title}")
        markdown_parts.append("")
        
        # Metadata section
        markdown_parts.append("## Conversation Details")
        markdown_parts.append("")
        markdown_parts.append(f"- **URL**: {metadata.get('url', 'Unknown')}")
        markdown_parts.append(f"- **Share ID**: {metadata.get('share_id', 'Unknown')}")
        
        if metadata.get('date'):
            date_str = metadata['date']
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S UTC')
                markdown_parts.append(f"- **Date**: {formatted_date}")
            except:
                markdown_parts.append(f"- **Date**: {date_str}")
        
        markdown_parts.append(f"- **Messages**: {len(messages)}")
        markdown_parts.append(f"- **Parsed**: {metadata.get('parsed_at', 'Unknown')}")
        markdown_parts.append("")
        
        # Conversation content
        markdown_parts.append("## Conversation")
        markdown_parts.append("")
        
        for i, message in enumerate(messages):
            role = message['role']
            content = message['content']
            
            # Add role header
            role_display = "Human" if role == 'human' else "Claude"
            markdown_parts.append(f"# {role_display}")
            markdown_parts.append("")
            
            # Add content
            markdown_parts.append(content)
            markdown_parts.append("")
        
        return '\n'.join(markdown_parts)