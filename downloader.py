import os
import ssl
import asyncio
import aiohttp
import aiofiles
import yt_dlp
import logging
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
from pyrogram.types import Message
from config import (
    DOWNLOAD_DIR, CHUNK_SIZE, CONCURRENT_FRAGMENTS, 
    MAX_RETRIES, FRAGMENT_RETRIES, CONNECTION_TIMEOUT,
    HTTP_CHUNK_SIZE, BUFFER_SIZE, DYNAMIC_WORKERS,
    MIN_WORKERS, MAX_WORKERS, WORKER_ADJUST_THRESHOLD,
    CONNECTION_POOL_SIZE, CONNECTION_POOL_PER_HOST, 
    DNS_CACHE_TTL, QUALITY_SETTINGS, SAFE_SPLIT_SIZE
)
from utils import format_size, format_time, create_progress_bar

logger = logging.getLogger(__name__)


class DynamicWorkerManager:
    """Dynamic worker adjustment for optimal speed"""
    
    def __init__(self):
        self.current_workers = CONCURRENT_FRAGMENTS
        self.last_speed = 0
        self.last_adjust = time.time()
        self.speed_history = []
    
    def adjust_workers(self, current_speed: float):
        """Adjust workers based on speed"""
        if not DYNAMIC_WORKERS:
            return self.current_workers
        
        now = time.time()
        if now - self.last_adjust < WORKER_ADJUST_THRESHOLD:
            return self.current_workers
        
        self.speed_history.append(current_speed)
        if len(self.speed_history) > 5:
            self.speed_history.pop(0)
        
        avg_speed = sum(self.speed_history) / len(self.speed_history)
        
        if avg_speed > self.last_speed * 1.2 and self.current_workers < MAX_WORKERS:
            self.current_workers = min(self.current_workers + 4, MAX_WORKERS)
            logger.info(f"📈 Workers → {self.current_workers}")
        elif avg_speed < self.last_speed * 0.8 and self.current_workers > MIN_WORKERS:
            self.current_workers = max(self.current_workers - 2, MIN_WORKERS)
            logger.info(f"📉 Workers → {self.current_workers}")
        
        self.last_speed = avg_speed
        self.last_adjust = now
        return self.current_workers


worker_manager = DynamicWorkerManager()


def is_direct_video_url(url: str) -> bool:
    """
    🎯 NEW v11.1 - Detect direct video URLs
    Returns True if URL is a direct video file (not streaming)
    """
    url_lower = url.lower()
    
    # Direct video extensions
    direct_video_extensions = [
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', 
        '.flv', '.webm', '.m4v', '.3gp', '.ogv',
        '.ts', '.mts', '.m2ts'
    ]
    
    # Check if URL ends with video extension
    for ext in direct_video_extensions:
        if ext in url_lower:
            return True
    
    # Exclude streaming formats
    streaming_formats = ['.m3u8', '.mpd', '/manifest.']
    for fmt in streaming_formats:
        if fmt in url_lower:
            return False
    
    return False


def is_streaming_url(url: str) -> bool:
    """Check if URL is streaming format (M3U8, MPD, etc.)"""
    url_lower = url.lower()
    streaming_formats = ['.m3u8', '.mpd', '/manifest.', 'master.m3u8']
    return any(fmt in url_lower for fmt in streaming_formats)


async def download_direct_video(
    url: str,
    output_path: str,
    progress_msg: Message,
    user_id: int,
    active_downloads: Dict[int, bool]
) -> Optional[str]:
    """
    🆕 v11.1 - Download direct video files (.mp4, .mkv, etc.)
    Fast direct download with progress tracking
    """
    try:
        logger.info(f"🎬 Direct video download: {url}")
        
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=CONNECTION_POOL_SIZE,
            limit_per_host=CONNECTION_POOL_PER_HOST,
            ttl_dns_cache=DNS_CACHE_TTL,
            force_close=False,
            enable_cleanup_closed=True,
            keepalive_timeout=300,
        )
        
        timeout = aiohttp.ClientTimeout(
            total=CONNECTION_TIMEOUT,
            connect=30,
            sock_read=60
        )
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': url.split('?')[0],
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} for direct video")
                    return None
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                last_update = 0
                update_threshold = 512 * 1024  # Update every 512KB
                
                async with aiofiles.open(output_path, 'wb', buffering=BUFFER_SIZE) as f:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        if not active_downloads.get(user_id, False):
                            if os.path.exists(output_path):
                                os.remove(output_path)
                            return None
                        
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        if downloaded - last_update >= update_threshold:
                            last_update = downloaded
                            try:
                                percent = (downloaded / total_size * 100) if total_size > 0 else 0
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = int((total_size - downloaded) / speed) if speed > 0 else 0
                                bar = create_progress_bar(percent)
                                
                                await progress_msg.edit_text(
                                    f"🎬 **DIRECT VIDEO DOWNLOAD**\n\n"
                                    f"{bar}\n\n"
                                    f"📦 {format_size(downloaded)} / {format_size(total_size)}\n"
                                    f"🚀 {format_size(int(speed))}/s\n"
                                    f"⏱️ {format_time(eta)}"
                                )
                            except:
                                pass
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 10240:
                    logger.info(f"✅ Direct video downloaded: {format_size(os.path.getsize(output_path))}")
                    return output_path
                
                return None
                
    except Exception as e:
        logger.error(f"Direct video download error: {e}", exc_info=True)
        return None


async def download_file(
    url: str, 
    filename: str, 
    progress_msg: Message, 
    user_id: int,
    active_downloads: Dict[int, bool]
) -> Optional[str]:
    """ULTRA-FAST file downloader - NO CHANGES (keep speed)"""
    filepath = DOWNLOAD_DIR / filename
    
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=CONNECTION_POOL_SIZE,
            limit_per_host=CONNECTION_POOL_PER_HOST,
            ttl_dns_cache=DNS_CACHE_TTL,
            force_close=False,
            enable_cleanup_closed=True,
            keepalive_timeout=300,
        )
        
        timeout = aiohttp.ClientTimeout(
            total=CONNECTION_TIMEOUT,
            connect=30,
            sock_read=60
        )
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status}")
                    return None
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                last_update = 0
                update_threshold = 256 * 1024
                
                async with aiofiles.open(filepath, 'wb', buffering=BUFFER_SIZE) as f:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        if not active_downloads.get(user_id, False):
                            if filepath.exists():
                                os.remove(filepath)
                            return None
                        
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        if downloaded - last_update >= update_threshold:
                            last_update = downloaded
                            try:
                                percent = (downloaded / total_size * 100) if total_size > 0 else 0
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = int((total_size - downloaded) / speed) if speed > 0 else 0
                                bar = create_progress_bar(percent)
                                
                                await progress_msg.edit_text(
                                    f"⚡ **DOWNLOADING**\n\n"
                                    f"{bar}\n\n"
                                    f"📦 {format_size(downloaded)} / {format_size(total_size)}\n"
                                    f"🚀 {format_size(int(speed))}/s\n"
                                    f"⏱️ {format_time(eta)}"
                                )
                            except:
                                pass
                
                if filepath.exists() and filepath.stat().st_size > 1024:
                    return str(filepath)
                return None
                
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


def download_video_sync(
    url: str, 
    quality: str, 
    output_path: str, 
    user_id: int,
    active_downloads: Dict[int, bool],
    download_progress: Dict[int, dict]
) -> bool:
    """
    🚀 v11.1 ENHANCED - Universal video downloader
    Supports: M3U8, MPD, MP4, MKV, and ALL video formats
    """
    try:
        def progress_hook(d):
            if not active_downloads.get(user_id, False):
                raise Exception("Cancelled")
            
            if d['status'] == 'downloading':
                try:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    speed = d.get('speed', 0) or 0
                    eta = d.get('eta', 0)
                    
                    if total > 0:
                        percent = (downloaded / total) * 100
                        workers = worker_manager.adjust_workers(speed)
                        
                        download_progress[user_id] = {
                            'percent': percent,
                            'downloaded': downloaded,
                            'total': total,
                            'speed': speed,
                            'eta': eta,
                            'workers': workers
                        }
                except:
                    pass
        
        quality_height = QUALITY_SETTINGS.get(quality, {}).get('height', 720)
        current_workers = worker_manager.current_workers
        
        # 🆕 v11.1 - Enhanced format selection for ALL video types
        # Supports: Streaming (M3U8, MPD) AND Direct videos (MP4, MKV, etc.)
        ydl_opts = {
            'format': (
                f'bestvideo[height<={quality_height}]+bestaudio/best[height<={quality_height}]/'
                f'best/bestvideo+bestaudio/bestvideo'
            ),
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            
            # SPEED SETTINGS - MAINTAINED
            'concurrent_fragment_downloads': current_workers,
            'retries': MAX_RETRIES,
            'fragment_retries': FRAGMENT_RETRIES,
            'skip_unavailable_fragments': True,
            'buffersize': BUFFER_SIZE,
            'http_chunk_size': HTTP_CHUNK_SIZE,
            
            # 🆕 v11.1 - Enhanced for direct videos
            'keepvideo': False,
            'writethumbnail': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            },
            
            'progress_hooks': [progress_hook],
            'extractor_retries': MAX_RETRIES,
            'socket_timeout': 60,
            'hls_prefer_native': True,
            
            # 🆕 v11.1 - Better handling for various sources
            'geo_bypass': True,
            'no_check_certificate': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if not active_downloads.get(user_id, False):
                return False
            
            logger.info(f"🚀 Downloading video: {url} at {quality}")
            ydl.download([url])
            logger.info(f"✅ Download complete")
            return True
            
    except Exception as e:
        error_msg = str(e).lower()
        if 'youtube' in error_msg or 'unsupported' in error_msg:
            download_progress[user_id] = {
                'error': 'unsupported',
                'url': url
            }
        logger.error(f"Download error: {e}")
        return False


async def fast_split_video(video_path: str, max_size_mb: int = SAFE_SPLIT_SIZE) -> List[str]:
    """
    ⚡ ULTRA-FAST split using ffmpeg -c copy
    Splits in SECONDS, not minutes!
    """
    try:
        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size_mb <= max_size_mb:
            logger.info(f"✅ File {file_size_mb:.1f}MB - No split needed")
            return [video_path]
        
        logger.info(f"🔪 Fast-splitting {file_size_mb:.1f}MB file...")
        start_time = time.time()
        
        # Get duration using ffprobe (fast)
        probe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        
        try:
            duration = float(result.stdout.strip())
        except:
            duration = 0
        
        if duration <= 0:
            logger.error("Could not get duration, returning original")
            return [video_path]
        
        logger.info(f"Duration: {duration:.1f}s")
        
        # Calculate optimal split
        max_size_bytes = max_size_mb * 1024 * 1024
        num_parts = int(file_size / max_size_bytes) + 1
        split_duration = duration / num_parts
        
        logger.info(f"Creating {num_parts} parts, {split_duration:.1f}s each")
        
        base_name = os.path.basename(video_path)
        name, ext = os.path.splitext(base_name)
        
        parts = []
        
        # Split using segment (MUCH FASTER!)
        for i in range(num_parts):
            start_pos = i * split_duration
            part_name = f"{name}_part{i+1:03d}_of_{num_parts:03d}{ext}"
            part_path = str(DOWNLOAD_DIR / part_name)
            
            # 🚀 KEY: Use -c copy for INSTANT split (no re-encode)
            split_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_pos),
                '-i', video_path,
                '-t', str(split_duration),
                '-c', 'copy',  # COPY = NO ENCODING = FAST!
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts',
                part_path
            ]
            
            result = subprocess.run(split_cmd, capture_output=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists(part_path):
                part_size = os.path.getsize(part_path) / (1024 * 1024)
                parts.append(part_path)
                logger.info(f"✅ Part {i+1}: {part_size:.1f}MB")
            else:
                logger.error(f"❌ Part {i+1} failed")
        
        elapsed = time.time() - start_time
        
        if parts:
            try:
                os.remove(video_path)
                logger.info(f"🗑️ Removed original")
            except:
                pass
            
            logger.info(f"⚡ Split completed in {elapsed:.1f}s! ({len(parts)} parts)")
            return parts
        else:
            logger.error("No parts created, returning original")
            return [video_path]
        
    except subprocess.TimeoutExpired:
        logger.error("Split timeout!")
        return [video_path]
    except Exception as e:
        logger.error(f"Split error: {e}", exc_info=True)
        return [video_path]


async def update_video_progress(
    progress_msg: Message, 
    user_id: int,
    download_progress: Dict[int, dict],
    active_downloads: Dict[int, bool]
):
    """Update video download progress"""
    last_percent = -1
    
    while active_downloads.get(user_id, False) and user_id in download_progress:
        try:
            prog = download_progress[user_id]
            
            if 'error' in prog:
                break
            
            percent = prog.get('percent', 0)
            
            if int(percent) - last_percent >= 2:
                last_percent = int(percent)
                
                downloaded = prog.get('downloaded', 0)
                total = prog.get('total', 0)
                speed = prog.get('speed', 0)
                eta = prog.get('eta', 0)
                workers = prog.get('workers', CONCURRENT_FRAGMENTS)
                
                bar = create_progress_bar(percent)
                
                await progress_msg.edit_text(
                    f"🎬 **VIDEO DOWNLOAD**\n\n"
                    f"{bar}\n\n"
                    f"📦 {format_size(downloaded)} / {format_size(total)}\n"
                    f"🚀 {format_size(int(speed))}/s\n"
                    f"⏱️ {format_time(int(eta))}\n"
                    f"💪 Workers: {workers}"
                )
                
        except:
            pass
        
        await asyncio.sleep(1)


async def download_video(
    url: str,
    quality: str,
    filename: str,
    progress_msg: Message,
    user_id: int,
    active_downloads: Dict[int, bool],
    download_progress: Dict[int, dict]
) -> Optional[str]:
    """
    🚀 v11.1 UNIVERSAL VIDEO DOWNLOADER
    
    Supports:
    - Streaming: M3U8, MPD, HLS, DASH
    - Direct: MP4, MKV, AVI, MOV, WEBM, FLV, WMV, etc.
    - All video formats!
    
    Flow:
    1. Detect video type (streaming vs direct)
    2. Use appropriate download method
    3. Check size → Split if needed
    4. Return path
    """
    temp_name = f"temp_{user_id}_{filename.replace('.mp4', '')}"
    output_path = str(DOWNLOAD_DIR / temp_name)
    
    try:
        download_progress[user_id] = {'percent': 0}
        
        # 🆕 v11.1 - Detect if direct video URL
        if is_direct_video_url(url):
            logger.info("🎬 Detected: DIRECT VIDEO")
            await progress_msg.edit_text("🎬 Downloading direct video...")
            
            # Try direct download first
            result = await download_direct_video(
                url, output_path + '.mp4', progress_msg, 
                user_id, active_downloads
            )
            
            if result and os.path.exists(result):
                final_path = Path(result)
                logger.info(f"✅ Direct video downloaded: {final_path}")
            else:
                # Fallback to yt-dlp for complex URLs
                logger.info("⚠️ Direct download failed, trying yt-dlp...")
                await progress_msg.edit_text("🚀 Starting enhanced download...")
                
                progress_task = asyncio.create_task(
                    update_video_progress(progress_msg, user_id, download_progress, active_downloads)
                )
                
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None,
                    download_video_sync,
                    url, quality, output_path, user_id, active_downloads, download_progress
                )
                
                if user_id in download_progress:
                    del download_progress[user_id]
                
                try:
                    progress_task.cancel()
                except:
                    pass
                
                if not success or not active_downloads.get(user_id, False):
                    return None
                
                # Find downloaded file
                possible_files = []
                for ext in ['.mp4', '.mkv', '.webm', '.ts']:
                    p = Path(output_path + ext)
                    if p.exists() and p.stat().st_size > 10240:
                        possible_files.append(p)
                
                for file in DOWNLOAD_DIR.glob(f"temp_{user_id}_*"):
                    if file.is_file() and file.stat().st_size > 10240:
                        possible_files.append(file)
                
                if not possible_files:
                    logger.error("No output file found")
                    return None
                
                final_path = max(possible_files, key=lambda p: p.stat().st_size)
        
        else:
            # Streaming video (M3U8, MPD, etc.) - use yt-dlp
            logger.info("📺 Detected: STREAMING VIDEO")
            await progress_msg.edit_text("🚀 Starting download...")
            
            progress_task = asyncio.create_task(
                update_video_progress(progress_msg, user_id, download_progress, active_downloads)
            )
            
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                download_video_sync,
                url, quality, output_path, user_id, active_downloads, download_progress
            )
            
            if user_id in download_progress and 'error' in download_progress[user_id]:
                del download_progress[user_id]
                try:
                    progress_task.cancel()
                except:
                    pass
                return 'UNSUPPORTED'
            
            if user_id in download_progress:
                del download_progress[user_id]
            
            try:
                progress_task.cancel()
            except:
                pass
            
            if not success or not active_downloads.get(user_id, False):
                return None
            
            # Find downloaded file
            possible_files = []
            for ext in ['.mp4', '.mkv', '.webm', '.ts']:
                p = Path(output_path + ext)
                if p.exists() and p.stat().st_size > 10240:
                    possible_files.append(p)
            
            for file in DOWNLOAD_DIR.glob(f"temp_{user_id}_*"):
                if file.is_file() and file.stat().st_size > 10240:
                    possible_files.append(file)
            
            if not possible_files:
                logger.error("No output file found")
                return None
            
            final_path = max(possible_files, key=lambda p: p.stat().st_size)
        
        # Rename to final filename
        final_output = DOWNLOAD_DIR / filename
        if final_path != final_output:
            os.rename(final_path, final_output)
        else:
            final_output = final_path
        
        # 🎯 SMART CHECK: Only split if actually > 1.9GB
        file_size_mb = final_output.stat().st_size / (1024 * 1024)
        
        if file_size_mb > SAFE_SPLIT_SIZE:
            logger.info(f"🔪 Large file detected: {file_size_mb:.1f}MB")
            await progress_msg.edit_text(
                f"🔪 **Splitting large file...**\n\n"
                f"Size: {file_size_mb:.1f}MB\n"
                f"⚡ Using fast split...\n\n"
                f"This takes only seconds!"
            )
            
            # FAST SPLIT (seconds, not minutes!)
            parts = await fast_split_video(str(final_output), SAFE_SPLIT_SIZE)
            
            if parts and len(parts) > 1:
                logger.info(f"✅ Split into {len(parts)} parts")
                await progress_msg.edit_text(f"✅ Split complete! ({len(parts)} parts)")
                return parts[0]
        else:
            logger.info(f"✅ File {file_size_mb:.1f}MB - No split needed")
        
        if final_output.exists() and final_output.stat().st_size > 10240:
            logger.info(f"✅ Video ready: {final_output}")
            return str(final_output)
        
        return None
        
    except Exception as e:
        logger.error(f"Video download error: {e}", exc_info=True)
        if user_id in download_progress:
            del download_progress[user_id]
        return None
