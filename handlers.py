"""
🚀 HANDLERS - HYDROGEN BOMB v11.0
DUAL MODE SYSTEM: Original + Compare
"""

import os
import asyncio
import aiofiles
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_DIR, QUALITY_SETTINGS, BOT_MODES
from utils import (
    parse_content, sanitize_filename, is_youtube_url, 
    is_unsupported_platform, extract_channel_id,
    save_destination_channel, get_destination_channel, 
    clear_destination_channel
)
from video_processor import (
    get_video_info, generate_thumbnail_with_text, 
    validate_video_file, convert_video_quality
)
from downloader import download_video, download_file
from uploader import (
    upload_video, upload_photo, upload_document, 
    send_failed_link, send_to_destination
)
from comparator import compare_link_lists, SmartComparator

logger = logging.getLogger(__name__)

# Global state
user_data = {}
active_downloads = {}
download_progress = {}


def setup_handlers(app: Client):
    """Setup all bot handlers with v11.0 DUAL MODE"""
    
    @app.on_message(filters.command("start"))
    async def start_cmd(client: Client, message: Message):
        await message.reply_text(
            "🚀 **M3U8 Downloader Bot - HYDROGEN BOMB Edition v11.0**\n\n"
            "⚡ **REVOLUTIONARY DUAL MODE:**\n"
            "🔵 **Original Mode** - Process all links\n"
            "🟢 **Compare Mode** - Process only NEW links\n\n"
            "🔥 **ALL v10.0 FEATURES:**\n"
            "⚡ 6-7x Faster Downloads\n"
            "📦 Smart 2GB+ File Handling\n"
            "🎯 Destination Channel Support\n"
            "✏️ Custom Caption Feature\n"
            "🎨 Text Watermark on Thumbnails\n"
            "⚙️ Advanced Quality Control\n"
            "❌ Universal Failed Link Handler\n"
            "💪 Dynamic Worker Management\n\n"
            "🆕 **NEW IN v11.0:**\n"
            "🔍 Smart Link Comparison\n"
            "📊 Accurate Difference Detection\n"
            "🎯 Zero Misses Guaranteed\n"
            "📈 Detailed Comparison Stats\n\n"
            "📝 **How to Use:**\n\n"
            "**ORIGINAL MODE:**\n"
            "1. Send TXT/HTML file\n"
            "2. Follow steps → Download!\n\n"
            "**COMPARE MODE:**\n"
            "1. Send OLD TXT file\n"
            "2. Send NEW TXT file\n"
            "3. Bot finds differences\n"
            "4. Downloads only NEW links!\n\n"
            "🔧 **Commands:**\n"
            "/start - Show this message\n"
            "/cancel - Stop downloads\n"
            "/destination - Set destination\n"
            "/clear - Clear destination\n"
            "/mode - Switch modes\n\n"
            "🚀 **HYDROGEN BOMB v11.0 - DUAL MODE POWER!**"
        )
    
    
    @app.on_message(filters.command("mode"))
    async def mode_cmd(client: Client, message: Message):
        """Switch between Original and Compare modes"""
        user_id = message.from_user.id
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔵 Original Mode", callback_data="mode_original")],
            [InlineKeyboardButton("🟢 Compare Mode", callback_data="mode_compare")]
        ])
        
        current_mode = user_data.get(user_id, {}).get('mode', 'original')
        
        await message.reply_text(
            f"🎯 **SELECT MODE**\n\n"
            f"Current: **{BOT_MODES.get(current_mode, 'Original')}**\n\n"
            f"**🔵 Original Mode:**\n"
            f"• Send single TXT file\n"
            f"• Process all links\n"
            f"• Best for fresh batches\n\n"
            f"**🟢 Compare Mode:**\n"
            f"• Send OLD + NEW TXT files\n"
            f"• Process only NEW links\n"
            f"• Perfect for updates\n"
            f"• Zero misses guaranteed!\n\n"
            f"Choose your mode:",
            reply_markup=kb
        )
    
    
    @app.on_callback_query(filters.regex(r"^mode_"))
    async def mode_switch(client: Client, callback: CallbackQuery):
        """Handle mode switching"""
        user_id = callback.from_user.id
        mode = callback.data.split("_")[1]
        
        if user_id not in user_data:
            user_data[user_id] = {}
        
        user_data[user_id]['mode'] = mode
        
        mode_emoji = "🔵" if mode == "original" else "🟢"
        mode_name = BOT_MODES.get(mode, "Unknown")
        
        await callback.message.edit_text(
            f"{mode_emoji} **MODE SELECTED**\n\n"
            f"✅ {mode_name}\n\n"
            f"Now send your TXT file(s) to start!"
        )
    
    
    @app.on_message(filters.command("destination"))
    async def destination_cmd(client: Client, message: Message):
        await message.reply_text(
            "🎯 **Set Destination Channel/Group**\n\n"
            "Send me ONE of these:\n\n"
            "1️⃣ **Forward any message** from your channel\n"
            "2️⃣ **Send channel link** (e.g., t.me/yourchannel)\n"
            "3️⃣ **Send channel ID** (e.g., -1001234567890)\n\n"
            "💡 Make sure I'm admin in that channel!"
        )
    
    
    @app.on_message(filters.command("clear"))
    async def clear_cmd(client: Client, message: Message):
        user_id = message.from_user.id
        await clear_destination_channel(user_id)
        await message.reply_text("✅ Destination channel cleared!")
    
    
    @app.on_message(filters.forwarded)
    async def handle_forward(client: Client, message: Message):
        """Handle forwarded messages to set destination"""
        user_id = message.from_user.id
        
        if message.forward_from_chat:
            channel_id = message.forward_from_chat.id
            channel_name = message.forward_from_chat.title or "Unknown"
            
            await save_destination_channel(user_id, channel_id, channel_name)
            
            await message.reply_text(
                f"✅ **Destination Set!**\n\n"
                f"📢 Channel: {channel_name}\n"
                f"🆔 ID: `{channel_id}`\n\n"
                f"All files will be sent here now!"
            )
    
    
    @app.on_message(filters.document)
    async def handle_doc(client: Client, message: Message):
        """
        🎯 SMART DOCUMENT HANDLER
        Detects mode and routes accordingly
        """
        user_id = message.from_user.id
        file_name = message.document.file_name
        
        if not (file_name.endswith('.txt') or file_name.endswith('.html')):
            await message.reply_text("❌ Please send TXT or HTML file only!")
            return
        
        # Initialize user data if needed
        if user_id not in user_data:
            user_data[user_id] = {'mode': 'original'}
        
        current_mode = user_data[user_id].get('mode', 'original')
        
        status = await message.reply_text("📥 Processing your file...")
        
        try:
            file_path = await message.download(file_name=f"{DOWNLOAD_DIR}/{user_id}_{file_name}")
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            items = parse_content(content)
            
            if not items:
                await status.edit_text("❌ No supported links found in file!")
                os.remove(file_path)
                return
            
            # ROUTE BASED ON MODE
            if current_mode == 'compare':
                await handle_compare_mode_file(
                    client, message, status, user_id, 
                    file_path, items, file_name
                )
            else:
                await handle_original_mode_file(
                    client, message, status, user_id, 
                    file_path, items
                )
            
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            await status.edit_text(f"❌ Error: {str(e)[:100]}")
    
    
    async def handle_original_mode_file(
        client: Client, message: Message, status: Message,
        user_id: int, file_path: str, items: list
    ):
        """
        🔵 ORIGINAL MODE HANDLER
        Same as v10.0 - process all links
        """
        # Count by type
        type_counts = {}
        for item in items:
            ftype = item['type']
            type_counts[ftype] = type_counts.get(ftype, 0) + 1
        
        user_data[user_id].update({
            'items': items, 
            'file_path': file_path,
            'step': 'select_range',
            'mode': 'original'
        })
        
        # Check destination
        destination = await get_destination_channel(user_id)
        dest_info = ""
        if destination:
            dest_info = f"\n🎯 Destination: {destination[1] or destination[0]}\n"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Select Range", callback_data="select_range")],
            [InlineKeyboardButton("⬇️ Download All", callback_data="download_all")]
        ])
        
        type_info = "\n".join([
            f"{'🎬' if t == 'video' else '🖼️' if t == 'image' else '📄'} {t.title()}s: {c}" 
            for t, c in type_counts.items()
        ])
        
        await status.edit_text(
            f"🔵 **ORIGINAL MODE**\n\n"
            f"✅ Content Detected!\n\n"
            f"{type_info}\n"
            f"📦 Total: {len(items)}{dest_info}\n\n"
            f"🚀 Choose your action:",
            reply_markup=kb
        )
    
    
    async def handle_compare_mode_file(
        client: Client, message: Message, status: Message,
        user_id: int, file_path: str, items: list, file_name: str
    ):
        """
        🟢 COMPARE MODE HANDLER
        New in v11.0 - smart comparison
        """
        compare_data = user_data[user_id].get('compare_data', {})
        
        # Check if this is OLD or NEW file
        if 'old_items' not in compare_data:
            # This is the OLD file
            compare_data['old_items'] = items
            compare_data['old_file_path'] = file_path
            compare_data['old_file_name'] = file_name
            
            user_data[user_id]['compare_data'] = compare_data
            
            await status.edit_text(
                f"🟢 **COMPARE MODE - Step 1/2**\n\n"
                f"✅ **OLD FILE RECEIVED**\n\n"
                f"📄 File: {file_name}\n"
                f"📦 Links: {len(items)}\n\n"
                f"📥 **Now send the NEW file**\n"
                f"(The updated version with new links)\n\n"
                f"⏳ Waiting for NEW file..."
            )
            
        else:
            # This is the NEW file
            old_items = compare_data['old_items']
            old_file_name = compare_data.get('old_file_name', 'old.txt')
            
            await status.edit_text(
                f"🟢 **COMPARE MODE - Step 2/2**\n\n"
                f"✅ **NEW FILE RECEIVED**\n\n"
                f"📄 Old: {old_file_name} ({len(old_items)} links)\n"
                f"📄 New: {file_name} ({len(items)} links)\n\n"
                f"🔍 **Analyzing differences...**\n"
                f"⏳ Please wait..."
            )
            
            # PERFORM COMPARISON
            await perform_comparison(
                client, message, status, user_id,
                old_items, items, file_path, compare_data
            )
    
    # Continue with rest of handlers...
    # (Part 2 will have the remaining handlers)
