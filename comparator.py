"""
🔍 SMART LINK COMPARATOR - v11.0
Ultra-accurate comparison engine
ZERO MISSES GUARANTEED!
"""

import logging
from typing import List, Dict, Tuple, Set
from urllib.parse import urlparse, parse_qs, unquote
import hashlib
import re

logger = logging.getLogger(__name__)


class SmartComparator:
    """
    🎯 ULTRA-ACCURATE Link Comparator
    
    Features:
    - Normalized URL comparison
    - Query parameter handling
    - URL encoding normalization
    - Fragment/anchor handling
    - Domain case-insensitive
    - Protocol normalization
    - Duplicate detection
    """
    
    def __init__(self):
        self.comparison_stats = {
            'total_old': 0,
            'total_new': 0,
            'common': 0,
            'new_only': 0,
            'old_only': 0
        }
    
    def normalize_url(self, url: str) -> str:
        """
        🔧 ADVANCED URL Normalization
        Ensures same URLs are detected even with minor differences
        """
        try:
            # Remove whitespace
            url = url.strip()
            
            # Decode URL encoding
            url = unquote(url)
            
            # Parse URL
            parsed = urlparse(url)
            
            # Normalize components
            scheme = parsed.scheme.lower() if parsed.scheme else 'https'
            netloc = parsed.netloc.lower()  # Case-insensitive domain
            path = parsed.path
            
            # Remove trailing slash from path (unless it's just "/")
            if len(path) > 1 and path.endswith('/'):
                path = path[:-1]
            
            # Sort query parameters for consistent comparison
            query = parsed.query
            if query:
                params = parse_qs(query, keep_blank_values=True)
                sorted_params = sorted(params.items())
                query = '&'.join(f"{k}={v[0]}" for k, v in sorted_params)
            
            # Ignore fragments (# anchors) for comparison
            # fragment = parsed.fragment
            
            # Reconstruct normalized URL
            normalized = f"{scheme}://{netloc}{path}"
            if query:
                normalized += f"?{query}"
            
            return normalized
            
        except Exception as e:
            logger.error(f"URL normalization error: {e}")
            return url.strip().lower()
    
    def generate_url_hash(self, url: str) -> str:
        """
        🔐 Generate unique hash for URL
        Even more robust comparison
        """
        normalized = self.normalize_url(url)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def extract_links_with_metadata(self, items: List[Dict]) -> Dict[str, Dict]:
        """
        📊 Extract links with full metadata
        Format: {hash: {url, title, type, index}}
        """
        link_map = {}
        
        for idx, item in enumerate(items):
            url = item['url']
            url_hash = self.generate_url_hash(url)
            normalized_url = self.normalize_url(url)
            
            link_map[url_hash] = {
                'url': url,  # Original URL
                'normalized_url': normalized_url,
                'title': item['title'],
                'type': item['type'],
                'index': idx + 1
            }
        
        return link_map
    
    def compare_files(
        self, 
        old_items: List[Dict], 
        new_items: List[Dict]
    ) -> Tuple[List[Dict], Dict]:
        """
        🎯 MAIN COMPARISON FUNCTION
        
        Returns:
        - List of NEW items (not in old file)
        - Detailed statistics dictionary
        """
        
        logger.info("=" * 70)
        logger.info("🔍 STARTING SMART COMPARISON")
        logger.info("=" * 70)
        
        # Extract with metadata
        old_links = self.extract_links_with_metadata(old_items)
        new_links = self.extract_links_with_metadata(new_items)
        
        old_hashes = set(old_links.keys())
        new_hashes = set(new_links.keys())
        
        # Find differences
        common_hashes = old_hashes & new_hashes
        new_only_hashes = new_hashes - old_hashes
        old_only_hashes = old_hashes - new_hashes
        
        # Build result list (NEW items only)
        new_items_result = []
        
        for url_hash in sorted(new_only_hashes):
            link_data = new_links[url_hash]
            new_items_result.append({
                'title': link_data['title'],
                'url': link_data['url'],
                'type': link_data['type'],
                'original_index': link_data['index']
            })
        
        # Update stats
        self.comparison_stats = {
            'total_old': len(old_items),
            'total_new': len(new_items),
            'common': len(common_hashes),
            'new_only': len(new_only_hashes),
            'old_only': len(old_only_hashes),
            'duplicate_in_old': len(old_items) - len(old_hashes),
            'duplicate_in_new': len(new_items) - len(new_hashes)
        }
        
        # Detailed logging
        logger.info(f"📊 OLD FILE: {self.comparison_stats['total_old']} items")
        logger.info(f"📊 NEW FILE: {self.comparison_stats['total_new']} items")
        logger.info(f"✅ COMMON: {self.comparison_stats['common']} links")
        logger.info(f"🆕 NEW ONLY: {self.comparison_stats['new_only']} links")
        logger.info(f"🗑️ REMOVED: {self.comparison_stats['old_only']} links")
        
        if self.comparison_stats['duplicate_in_old'] > 0:
            logger.warning(f"⚠️ Duplicates in OLD: {self.comparison_stats['duplicate_in_old']}")
        
        if self.comparison_stats['duplicate_in_new'] > 0:
            logger.warning(f"⚠️ Duplicates in NEW: {self.comparison_stats['duplicate_in_new']}")
        
        logger.info("=" * 70)
        
        return new_items_result, self.comparison_stats
    
    def get_comparison_summary(self) -> str:
        """
        📋 Generate human-readable comparison summary
        """
        stats = self.comparison_stats
        
        summary = (
            f"📊 **COMPARISON RESULTS**\n\n"
            f"📄 Old File: {stats['total_old']} items\n"
            f"📄 New File: {stats['total_new']} items\n\n"
            f"✅ Common Links: {stats['common']}\n"
            f"🆕 New Links: {stats['new_only']}\n"
            f"🗑️ Removed Links: {stats['old_only']}\n"
        )
        
        if stats['duplicate_in_old'] > 0:
            summary += f"\n⚠️ Duplicates in OLD: {stats['duplicate_in_old']}"
        
        if stats['duplicate_in_new'] > 0:
            summary += f"\n⚠️ Duplicates in NEW: {stats['duplicate_in_new']}"
        
        return summary
    
    def validate_comparison(
        self, 
        old_items: List[Dict], 
        new_items: List[Dict],
        result_items: List[Dict]
    ) -> bool:
        """
        ✅ VALIDATION CHECK
        Ensures comparison accuracy
        """
        try:
            # Check 1: Result size should be <= new file size
            if len(result_items) > len(new_items):
                logger.error("❌ Validation FAILED: Result > New file!")
                return False
            
            # Check 2: All result URLs should exist in new file
            new_urls = {self.normalize_url(item['url']) for item in new_items}
            result_urls = {self.normalize_url(item['url']) for item in result_items}
            
            if not result_urls.issubset(new_urls):
                logger.error("❌ Validation FAILED: Result contains URLs not in new file!")
                return False
            
            # Check 3: No result URLs should exist in old file
            old_urls = {self.normalize_url(item['url']) for item in old_items}
            common = result_urls & old_urls
            
            if common:
                logger.error(f"❌ Validation FAILED: {len(common)} URLs found in both old and result!")
                return False
            
            logger.info("✅ Validation PASSED: Comparison is accurate!")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False


# Helper function for quick comparison
def compare_link_lists(old_items: List[Dict], new_items: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    🚀 Quick comparison function
    
    Usage:
        new_links, stats = compare_link_lists(old_items, new_items)
    """
    comparator = SmartComparator()
    new_links, stats = comparator.compare_files(old_items, new_items)
    
    # Validate
    is_valid = comparator.validate_comparison(old_items, new_items, new_links)
    
    if not is_valid:
        logger.error("⚠️ COMPARISON VALIDATION FAILED!")
        logger.error("This is a critical error - please report!")
    
    return new_links, stats


# Test function
def test_comparator():
    """🧪 Test the comparator with sample data"""
    
    old_items = [
        {'title': 'Video 1', 'url': 'https://example.com/video1.m3u8', 'type': 'video'},
        {'title': 'Image 1', 'url': 'https://example.com/image1.jpg', 'type': 'image'},
        {'title': 'Doc 1', 'url': 'https://example.com/doc1.pdf', 'type': 'document'},
    ]
    
    new_items = [
        {'title': 'Video 1', 'url': 'https://example.com/video1.m3u8', 'type': 'video'},  # Same
        {'title': 'Video 1 Alt', 'url': 'HTTPS://EXAMPLE.COM/video1.m3u8/', 'type': 'video'},  # Same (normalized)
        {'title': 'Image 1', 'url': 'https://example.com/image1.jpg', 'type': 'image'},  # Same
        {'title': 'Image 2', 'url': 'https://example.com/image2.jpg', 'type': 'image'},  # NEW
        {'title': 'Video 2', 'url': 'https://example.com/video2.m3u8', 'type': 'video'},  # NEW
    ]
    
    new_links, stats = compare_link_lists(old_items, new_items)
    
    print("\n" + "=" * 70)
    print("🧪 COMPARATOR TEST RESULTS")
    print("=" * 70)
    print(f"Old items: {len(old_items)}")
    print(f"New items: {len(new_items)}")
    print(f"Detected NEW links: {len(new_links)}")
    print("\nNew links:")
    for item in new_links:
        print(f"  - {item['title']}: {item['url']}")
    print("\nStats:", stats)
    print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_comparator()
