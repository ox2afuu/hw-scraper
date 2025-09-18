"""File organization module for sorting downloaded content."""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

from hw_scraper.config import Config
from hw_scraper.models import FileType


class FileOrganizer:
    """Organizes downloaded files into structured directories."""
    
    # Mapping of file types to directory names
    TYPE_DIRECTORIES = {
        FileType.LECTURE_VIDEO: 'lectures/videos',
        FileType.LECTURE_SLIDE: 'lectures/slides',
        FileType.ASSIGNMENT: 'assignments',
        FileType.RESOURCE: 'resources',
        FileType.READING: 'readings',
        FileType.SYLLABUS: '',  # Root of course directory
        FileType.OTHER: 'misc'
    }
    
    def __init__(self, config: Config):
        """Initialize file organizer."""
        self.config = config
        self.organization = config.organization
    
    def setup_course_directory(self, base_path: Path, course_name: str) -> Path:
        """Set up directory structure for a course."""
        # Sanitize course name for directory
        safe_name = self.sanitize_filename(course_name)
        course_path = base_path / safe_name
        
        # Create base directory
        course_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories if organizing by type
        if self.organization.by_type:
            subdirs = [
                self.organization.lectures_dir,
                f"{self.organization.lectures_dir}/{self.organization.videos_dir}",
                f"{self.organization.lectures_dir}/{self.organization.slides_dir}",
                self.organization.assignments_dir,
                self.organization.resources_dir,
                'readings',
                'misc'
            ]
            
            for subdir in subdirs:
                (course_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # Create README with course information
        self._create_course_readme(course_path, course_name)
        
        return course_path
    
    def organize_file(self, file_path: Path, file_type: FileType, course_name: str) -> Path:
        """Organize a downloaded file into appropriate directory."""
        if not file_path.exists():
            return file_path
        
        # Determine target directory
        target_dir = self._get_target_directory(file_path.parent, file_type, course_name)
        
        # Prepare filename
        filename = self._prepare_filename(file_path.name, file_type, course_name)
        
        # Move file to target location
        target_path = target_dir / filename
        
        # Handle duplicates
        target_path = self._handle_duplicate(target_path)
        
        # Move or copy file
        try:
            shutil.move(str(file_path), str(target_path))
        except Exception:
            # If move fails, try copy
            shutil.copy2(str(file_path), str(target_path))
            file_path.unlink()  # Delete original
        
        return target_path
    
    def _get_target_directory(self, base_path: Path, file_type: FileType, course_name: str) -> Path:
        """Determine target directory for file type."""
        if self.organization.flatten:
            return base_path
        
        target = base_path
        
        # Add course directory if organizing by course
        if self.organization.by_course:
            safe_course_name = self.sanitize_filename(course_name)
            target = target / safe_course_name
        
        # Add type directory if organizing by type
        if self.organization.by_type:
            type_dir = self.TYPE_DIRECTORIES.get(file_type, 'misc')
            if type_dir:
                target = target / type_dir
        
        # Ensure directory exists
        target.mkdir(parents=True, exist_ok=True)
        
        return target
    
    def _prepare_filename(self, original_name: str, file_type: FileType, course_name: str) -> str:
        """Prepare filename with optional modifications."""
        filename = original_name
        
        # Sanitize filename if configured
        if self.organization.sanitize_names:
            filename = self.sanitize_filename(filename, preserve_extension=True)
        
        # Add course prefix if configured
        if self.organization.add_course_prefix:
            prefix = self.sanitize_filename(course_name)[:20]  # Limit prefix length
            if not filename.startswith(prefix):
                filename = f"{prefix}_{filename}"
        
        # Add date prefix if configured
        if self.organization.preserve_dates:
            date_prefix = datetime.now().strftime('%Y%m%d')
            if not re.match(r'^\d{8}_', filename):
                filename = f"{date_prefix}_{filename}"
        
        return filename
    
    def _handle_duplicate(self, target_path: Path) -> Path:
        """Handle duplicate files by appending number."""
        if not target_path.exists():
            return target_path
        
        base = target_path.stem
        ext = target_path.suffix
        parent = target_path.parent
        
        counter = 1
        while True:
            new_path = parent / f"{base}_{counter}{ext}"
            if not new_path.exists():
                return new_path
            counter += 1
    
    def sanitize_filename(self, filename: str, preserve_extension: bool = False) -> str:
        """Sanitize filename for filesystem compatibility."""
        # Separate extension if preserving
        if preserve_extension and '.' in filename:
            name, ext = filename.rsplit('.', 1)
        else:
            name = filename
            ext = None
        
        # Remove or replace invalid characters
        # Windows: < > : " | ? * \ /
        # Unix: mainly / and null
        invalid_chars = '<>:"|?*\\/\0'
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        # Remove control characters
        name = ''.join(char for char in name if ord(char) >= 32)
        
        # Replace multiple spaces/underscores with single
        name = re.sub(r'[\s_]+', '_', name)
        
        # Remove leading/trailing dots and spaces
        name = name.strip('. ')
        
        # Limit length (255 chars typical limit, leave room for extension)
        max_length = 200 if ext else 250
        if len(name) > max_length:
            name = name[:max_length]
        
        # Ensure name is not empty
        if not name:
            name = 'unnamed'
        
        # Reattach extension if preserving
        if ext:
            return f"{name}.{ext}"
        
        return name
    
    def _create_course_readme(self, course_path: Path, course_name: str):
        """Create README file with course information."""
        readme_path = course_path / 'README.md'
        
        if readme_path.exists():
            return
        
        content = f"""# {course_name}

## Course Materials

This directory contains downloaded materials for {course_name}.

### Directory Structure

- `lectures/` - Lecture materials
  - `videos/` - Lecture recordings
  - `slides/` - Lecture slides and presentations
- `assignments/` - Homework and assignments
- `resources/` - Additional course resources
- `readings/` - Required and supplementary readings
- `misc/` - Other files

### Download Information

Downloaded on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Downloaded using: hw-scraper

---

*This README was automatically generated*
"""
        
        with open(readme_path, 'w') as f:
            f.write(content)
    
    def organize_batch(self, files: List[Dict[str, any]], base_path: Path) -> Dict[str, Path]:
        """Organize multiple files at once."""
        organized = {}
        
        for file_info in files:
            file_path = Path(file_info['path'])
            file_type = file_info.get('type', FileType.OTHER)
            course_name = file_info.get('course', 'Unknown')
            
            new_path = self.organize_file(file_path, file_type, course_name)
            organized[str(file_path)] = new_path
        
        return organized
    
    def create_index(self, base_path: Path) -> Path:
        """Create an index file of all organized content."""
        index_path = base_path / 'index.md'
        
        content = ["# Course Materials Index\n\n"]
        content.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Walk through directory structure
        for course_dir in sorted(base_path.iterdir()):
            if not course_dir.is_dir():
                continue
            
            content.append(f"## {course_dir.name}\n\n")
            
            # Count files by type
            file_counts = {}
            for root, dirs, files in os.walk(course_dir):
                for file in files:
                    if file.startswith('.'):
                        continue
                    ext = Path(file).suffix.lower()
                    file_counts[ext] = file_counts.get(ext, 0) + 1
            
            if file_counts:
                content.append("### File Statistics\n\n")
                for ext, count in sorted(file_counts.items()):
                    content.append(f"- {ext}: {count} files\n")
                content.append("\n")
            
            # List recent files
            recent_files = self._get_recent_files(course_dir, limit=5)
            if recent_files:
                content.append("### Recent Files\n\n")
                for file_path in recent_files:
                    rel_path = file_path.relative_to(course_dir)
                    content.append(f"- {rel_path}\n")
                content.append("\n")
        
        with open(index_path, 'w') as f:
            f.writelines(content)
        
        return index_path
    
    def _get_recent_files(self, directory: Path, limit: int = 5) -> List[Path]:
        """Get most recently modified files in directory."""
        files = []
        
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                if filename.startswith('.') or filename == 'README.md':
                    continue
                file_path = Path(root) / filename
                files.append(file_path)
        
        # Sort by modification time
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        return files[:limit]