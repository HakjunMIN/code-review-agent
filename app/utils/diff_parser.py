import re
from typing import Dict, Set, Tuple, List


class DiffParser:
    """Parse git diffs to extract changed line information."""
    
    @staticmethod
    def parse_patch(patch: str) -> Dict[str, Set[int]]:
        """
        Parse a patch/diff to extract line numbers that were added or modified.
        
        Args:
            patch: Git patch/diff string
            
        Returns:
            Dictionary mapping side ('LEFT' or 'RIGHT') to set of line numbers
        """
        if not patch:
            return {'LEFT': set(), 'RIGHT': set()}
        
        left_lines: Set[int] = set()
        right_lines: Set[int] = set()
        
        current_right_line = 0
        current_left_line = 0
        
        for line in patch.split('\n'):
            # Parse hunk header: @@ -start,count +start,count @@
            if line.startswith('@@'):
                match = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    current_left_line = int(match.group(1))
                    current_right_line = int(match.group(2))
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                # Added line in new version (RIGHT side)
                right_lines.add(current_right_line)
                current_right_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Deleted line in old version (LEFT side)
                left_lines.add(current_left_line)
                current_left_line += 1
            elif line.startswith(' '):
                # Context line (unchanged)
                current_left_line += 1
                current_right_line += 1
        
        return {
            'LEFT': left_lines,
            'RIGHT': right_lines,
        }
    
    @staticmethod
    def get_changed_line_ranges(patch: str) -> List[Tuple[int, int]]:
        """
        Get ranges of changed lines in the new version (RIGHT side).
        
        Args:
            patch: Git patch/diff string
            
        Returns:
            List of (start_line, end_line) tuples representing changed ranges
        """
        changed_lines = DiffParser.parse_patch(patch).get('RIGHT', set())
        if not changed_lines:
            return []
        
        # Convert to sorted list and find continuous ranges
        sorted_lines = sorted(changed_lines)
        ranges: List[Tuple[int, int]] = []
        
        start = sorted_lines[0]
        end = sorted_lines[0]
        
        for line in sorted_lines[1:]:
            if line == end + 1:
                # Continuous range
                end = line
            else:
                # Gap found, save current range and start new one
                ranges.append((start, end))
                start = line
                end = line
        
        # Add the last range
        ranges.append((start, end))
        
        return ranges
    
    @staticmethod
    def is_valid_comment_line(patch: str, line: int, side: str = 'RIGHT') -> bool:
        """
        Check if a line number is valid for commenting in the diff.
        
        Args:
            patch: Git patch/diff string
            line: Line number to check
            side: 'LEFT' or 'RIGHT' (default: 'RIGHT')
            
        Returns:
            True if the line can be commented on
        """
        changed_lines = DiffParser.parse_patch(patch)
        return line in changed_lines.get(side, set())
    
    @staticmethod
    def find_nearest_valid_line(patch: str, line: int, max_distance: int = 5) -> int | None:
        """
        Find the nearest valid line for commenting if the given line is invalid.
        
        Args:
            patch: Git patch/diff string
            line: Target line number
            max_distance: Maximum distance to search
            
        Returns:
            Nearest valid line number, or None if not found
        """
        changed_lines = DiffParser.parse_patch(patch).get('RIGHT', set())
        if not changed_lines:
            return None
        
        if line in changed_lines:
            return line
        
        # Search nearby lines
        for distance in range(1, max_distance + 1):
            # Check above
            if line - distance in changed_lines:
                return line - distance
            # Check below
            if line + distance in changed_lines:
                return line + distance
        
        # Return the closest line in the diff
        sorted_lines = sorted(changed_lines)
        closest = min(sorted_lines, key=lambda x: abs(x - line))
        return closest if abs(closest - line) <= max_distance * 2 else None
