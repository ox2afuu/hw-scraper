"""Content parsing module using lxml."""

import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path
from datetime import datetime
from lxml import html, etree

from hw_scraper.models import Course, CourseFile, FileType


class ContentParser:
    """Parser for extracting course content from HTML pages."""
    
    # Common file extensions for different types
    FILE_TYPE_EXTENSIONS = {
        FileType.LECTURE_VIDEO: ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
        FileType.LECTURE_SLIDE: ['.ppt', '.pptx', '.pdf', '.odp'],
        FileType.ASSIGNMENT: ['.docx', '.doc', '.pdf', '.txt', '.md'],
        FileType.RESOURCE: ['.zip', '.tar', '.gz', '.rar', '.7z'],
        FileType.READING: ['.pdf', '.epub', '.mobi', '.txt'],
        FileType.SYLLABUS: ['.pdf', '.docx', '.doc', '.html']
    }
    
    # Common URL patterns for course materials
    COURSE_PATTERNS = {
        'lecture': r'lecture|slides?|presentation|week\d+|module\d+',
        'assignment': r'assignment|homework|hw|problem|pset|quiz|exam',
        'resource': r'resource|material|download|file|document',
        'video': r'video|recording|stream|media',
        'syllabus': r'syllabus|schedule|calendar|outline'
    }
    
    def parse_course_page(self, html_content: str, base_url: str) -> Dict[str, Any]:
        """Parse course information from HTML page."""
        tree = html.fromstring(html_content)
        
        course_info = {
            'name': self._extract_course_name(tree),
            'instructor': self._extract_instructor(tree),
            'semester': self._extract_semester(tree),
            'description': self._extract_description(tree),
            'url': base_url
        }
        
        return course_info
    
    def _extract_course_name(self, tree: html.HtmlElement) -> str:
        """Extract course name from HTML tree."""
        # Try common selectors for course name
        selectors = [
            '//h1[@class="course-title"]/text()',
            '//h1[@class="course-name"]/text()',
            '//div[@class="course-header"]//h1/text()',
            '//title/text()',
            '//h1/text()',
            '//meta[@property="og:title"]/@content'
        ]
        
        for selector in selectors:
            result = tree.xpath(selector)
            if result:
                name = str(result[0]).strip()
                # Clean up the name
                name = re.sub(r'\s+', ' ', name)
                if name and len(name) < 200:  # Sanity check
                    return name
        
        return "Unknown Course"
    
    def _extract_instructor(self, tree: html.HtmlElement) -> Optional[str]:
        """Extract instructor name from HTML tree."""
        selectors = [
            '//span[@class="instructor"]/text()',
            '//div[@class="instructor-name"]/text()',
            '//*[contains(@class, "instructor")]//text()',
            '//*[contains(text(), "Instructor:")]/following-sibling::*/text()',
            '//*[contains(text(), "Professor:")]/following-sibling::*/text()'
        ]
        
        for selector in selectors:
            result = tree.xpath(selector)
            if result:
                instructor = ' '.join(str(r).strip() for r in result)
                if instructor and len(instructor) < 100:
                    return instructor
        
        return None
    
    def _extract_semester(self, tree: html.HtmlElement) -> Optional[str]:
        """Extract semester information from HTML tree."""
        selectors = [
            '//span[@class="semester"]/text()',
            '//div[@class="term"]/text()',
            '//*[contains(@class, "semester")]//text()',
            '//*[contains(@class, "term")]//text()',
            '//*[contains(text(), "Semester:")]/following-sibling::*/text()',
            '//*[contains(text(), "Term:")]/following-sibling::*/text()'
        ]
        
        for selector in selectors:
            result = tree.xpath(selector)
            if result:
                semester = str(result[0]).strip()
                if semester and len(semester) < 50:
                    return semester
        
        # Try to find semester in text using regex
        page_text = tree.text_content()
        semester_pattern = r'(Spring|Fall|Summer|Winter)\s+\d{4}'
        match = re.search(semester_pattern, page_text, re.IGNORECASE)
        if match:
            return match.group(0)
        
        return None
    
    def _extract_description(self, tree: html.HtmlElement) -> Optional[str]:
        """Extract course description from HTML tree."""
        selectors = [
            '//div[@class="course-description"]/text()',
            '//p[@class="description"]/text()',
            '//meta[@name="description"]/@content',
            '//meta[@property="og:description"]/@content',
            '//*[contains(@class, "description")]//text()'
        ]
        
        for selector in selectors:
            result = tree.xpath(selector)
            if result:
                description = ' '.join(str(r).strip() for r in result)
                if description and len(description) > 20:
                    return description[:500]  # Limit length
        
        return None
    
    def extract_course_files(self, html_content: str, base_url: str) -> List[CourseFile]:
        """Extract all downloadable files from course page."""
        tree = html.fromstring(html_content)
        files = []
        
        # Find all links
        links = tree.xpath('//a[@href]')
        
        for link in links:
            href = link.get('href')
            if not href:
                continue
            
            # Make URL absolute
            url = urljoin(base_url, href)
            
            # Check if it's a downloadable file
            if self._is_downloadable(url, link):
                file = self._create_course_file(url, link, tree)
                if file:
                    files.append(file)
        
        # Also look for embedded media
        media_files = self._extract_media_files(tree, base_url)
        files.extend(media_files)
        
        return files
    
    def _is_downloadable(self, url: str, link_element: html.HtmlElement) -> bool:
        """Check if URL points to a downloadable file."""
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check file extension
        known_extensions = [
            '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
            '.zip', '.rar', '.tar', '.gz', '.7z',
            '.mp4', '.avi', '.mov', '.wmv', '.webm',
            '.mp3', '.wav', '.ogg',
            '.txt', '.md', '.csv', '.json', '.xml',
            '.jpg', '.jpeg', '.png', '.gif', '.svg'
        ]
        
        for ext in known_extensions:
            if path.endswith(ext):
                return True
        
        # Check link text and attributes
        link_text = (link_element.text_content() or '').lower()
        download_attr = link_element.get('download')
        
        if download_attr is not None:
            return True
        
        # Check for download indicators in text
        download_keywords = ['download', 'pdf', 'slides', 'homework', 'assignment', 'lecture']
        for keyword in download_keywords:
            if keyword in link_text:
                return True
        
        # Check URL patterns
        if any(pattern in path for pattern in ['/download/', '/files/', '/documents/', '/media/']):
            return True
        
        return False
    
    def _create_course_file(self, url: str, link_element: html.HtmlElement, tree: html.HtmlElement) -> Optional[CourseFile]:
        """Create CourseFile object from link element."""
        try:
            # Extract file name
            filename = self._extract_filename(url, link_element)
            if not filename:
                return None
            
            # Detect file type
            file_type = self.detect_file_type(url, filename, link_element)
            
            # Extract additional metadata
            description = link_element.text_content() or link_element.get('title', '')
            
            # Try to extract date
            date = self._extract_date(link_element, tree)
            
            return CourseFile(
                name=filename,
                url=url,
                type=file_type,
                description=description.strip() if description else None,
                date=date
            )
        except Exception:
            return None
    
    def _extract_filename(self, url: str, link_element: Optional[html.HtmlElement] = None) -> str:
        """Extract filename from URL or link element."""
        # Try to get from download attribute
        if link_element is not None:
            download_attr = link_element.get('download')
            if download_attr:
                return download_attr
        
        # Extract from URL path
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        if '/' in path:
            filename = path.split('/')[-1]
        else:
            filename = path
        
        # Clean up filename
        if filename and '.' in filename:
            return filename
        
        # Generate filename from link text if available
        if link_element is not None:
            link_text = link_element.text_content()
            if link_text:
                # Sanitize for filename
                filename = re.sub(r'[^\w\s-]', '', link_text.strip())
                filename = re.sub(r'[-\s]+', '-', filename)
                return filename[:100]  # Limit length
        
        return f"file_{hash(url) % 10000}"
    
    def detect_file_type(self, url: str, filename: Optional[str] = None, 
                        link_element: Optional[html.HtmlElement] = None) -> FileType:
        """Detect file type from URL, filename, and context."""
        # Combine URL and filename for checking
        check_string = (url + (filename or '')).lower()
        
        # Check by extension
        for file_type, extensions in self.FILE_TYPE_EXTENSIONS.items():
            for ext in extensions:
                if check_string.endswith(ext):
                    return file_type
        
        # Check by URL patterns
        for pattern_type, pattern in self.COURSE_PATTERNS.items():
            if re.search(pattern, check_string, re.IGNORECASE):
                if pattern_type == 'lecture':
                    return FileType.LECTURE_SLIDE
                elif pattern_type == 'assignment':
                    return FileType.ASSIGNMENT
                elif pattern_type == 'video':
                    return FileType.LECTURE_VIDEO
                elif pattern_type == 'syllabus':
                    return FileType.SYLLABUS
                elif pattern_type == 'resource':
                    return FileType.RESOURCE
        
        # Check link context if available
        if link_element is not None:
            context = (link_element.text_content() or '').lower()
            if 'video' in context or 'recording' in context:
                return FileType.LECTURE_VIDEO
            elif 'slide' in context or 'presentation' in context:
                return FileType.LECTURE_SLIDE
            elif 'assignment' in context or 'homework' in context:
                return FileType.ASSIGNMENT
            elif 'syllabus' in context:
                return FileType.SYLLABUS
            elif 'reading' in context:
                return FileType.READING
        
        return FileType.OTHER
    
    def _extract_date(self, element: html.HtmlElement, tree: html.HtmlElement) -> Optional[datetime]:
        """Try to extract date from element context."""
        # Look for date patterns near the element
        parent = element.getparent()
        if parent is not None:
            text = parent.text_content()
            
            # Common date patterns
            date_patterns = [
                r'\d{1,2}/\d{1,2}/\d{4}',
                r'\d{4}-\d{2}-\d{2}',
                r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',
                r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        # Try to parse the date
                        date_str = match.group(0)
                        # Simple parsing (would need more robust solution for production)
                        return None  # Placeholder for date parsing
                    except:
                        pass
        
        return None
    
    def _extract_media_files(self, tree: html.HtmlElement, base_url: str) -> List[CourseFile]:
        """Extract embedded media files (video, audio) from HTML."""
        files = []
        
        # Look for video elements
        videos = tree.xpath('//video[@src] | //video/source[@src]')
        for video in videos:
            src = video.get('src')
            if src:
                url = urljoin(base_url, src)
                filename = self._extract_filename(url)
                files.append(CourseFile(
                    name=filename,
                    url=url,
                    type=FileType.LECTURE_VIDEO,
                    description="Embedded video"
                ))
        
        # Look for audio elements
        audios = tree.xpath('//audio[@src] | //audio/source[@src]')
        for audio in audios:
            src = audio.get('src')
            if src:
                url = urljoin(base_url, src)
                filename = self._extract_filename(url)
                files.append(CourseFile(
                    name=filename,
                    url=url,
                    type=FileType.RESOURCE,
                    description="Embedded audio"
                ))
        
        # Look for iframe embeds (e.g., YouTube)
        iframes = tree.xpath('//iframe[@src]')
        for iframe in iframes:
            src = iframe.get('src')
            if src and any(domain in src for domain in ['youtube.com', 'vimeo.com', 'dailymotion.com']):
                files.append(CourseFile(
                    name=f"video_embed_{hash(src) % 10000}",
                    url=src,
                    type=FileType.LECTURE_VIDEO,
                    description="Embedded video (external)"
                ))
        
        return files
    
    def parse_course_catalog(self, html_content: str, base_url: str) -> List[Course]:
        """Parse course catalog to extract list of courses."""
        tree = html.fromstring(html_content)
        courses = []
        
        # Common patterns for course listings
        course_selectors = [
            '//div[@class="course-item"]',
            '//li[@class="course"]',
            '//tr[@class="course-row"]',
            '//article[@class="course"]',
            '//*[contains(@class, "course-card")]',
            '//*[contains(@class, "course-listing")]'
        ]
        
        for selector in course_selectors:
            items = tree.xpath(selector)
            if items:
                for item in items:
                    course = self._extract_course_from_element(item, base_url)
                    if course:
                        courses.append(course)
                break
        
        # If no structured courses found, try to find course links
        if not courses:
            links = tree.xpath('//a[contains(@href, "course") or contains(@href, "class")]')
            for link in links:
                href = link.get('href')
                if href:
                    url = urljoin(base_url, href)
                    name = link.text_content() or "Unknown Course"
                    course_id = self._extract_course_id(url, name)
                    
                    courses.append(Course(
                        id=course_id,
                        name=name.strip(),
                        url=url
                    ))
        
        return courses
    
    def _extract_course_from_element(self, element: html.HtmlElement, base_url: str) -> Optional[Course]:
        """Extract course information from HTML element."""
        try:
            # Find course link
            link = element.xpath('.//a[@href]')
            if not link:
                return None
            
            href = link[0].get('href')
            url = urljoin(base_url, href)
            
            # Extract course name
            name = link[0].text_content() or element.text_content()
            name = ' '.join(name.split())  # Clean whitespace
            
            # Extract course ID
            course_id = self._extract_course_id(url, name)
            
            # Try to extract additional info
            instructor = None
            semester = None
            
            # Look for instructor
            instructor_elem = element.xpath('.//*[contains(@class, "instructor")]')
            if instructor_elem:
                instructor = instructor_elem[0].text_content().strip()
            
            # Look for semester
            semester_elem = element.xpath('.//*[contains(@class, "term") or contains(@class, "semester")]')
            if semester_elem:
                semester = semester_elem[0].text_content().strip()
            
            return Course(
                id=course_id,
                name=name,
                url=url,
                instructor=instructor,
                semester=semester
            )
        except Exception:
            return None
    
    def _extract_course_id(self, url: str, name: str) -> str:
        """Extract or generate course ID."""
        # Try to extract from URL
        url_parts = urlparse(url).path.split('/')
        for part in url_parts:
            if part and (part[0].isdigit() or '-' in part):
                return part
        
        # Try to extract from name (e.g., "CS101: Introduction to Programming")
        match = re.search(r'^([A-Z]{2,4}\s?\d{3,4})', name)
        if match:
            return match.group(1).replace(' ', '')
        
        # Generate from name
        return re.sub(r'[^\w]', '_', name)[:50]