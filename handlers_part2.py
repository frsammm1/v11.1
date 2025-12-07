"""
🚀 HANDLERS PART 2 - v11.0
Comparison & Processing Functions
"""

import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import DOWNLOAD_DIR, QUALITY_SETTINGS
from comparator import compare_link_lists
from utils import sanitize_filename, is_youtube_url, is_unsupported_platform
from video_processor import get_video_info, generate_thumbnail_with_text, validate_video_file, convert_video_quality
from downloader import download_video, download_file
from uploader import upload_video, upload_photo, upload_document, send_failed_link, send_to_destination

logger = logging.getLogger(__name__)


async def perform_comparison(
    client: Client, message: Message, status: Message,
    user_id: int, old_items: list, new_items: list,
    new_file_path: str, compare_data: dict
):
    """
    🔍 PERFORM SMART COMPARISON
    Core comparison logic
    """
    try:
        # Run comparison
        new_links, stats = compare_link_lists(old_items, new_items)
        
        # Count by type
        type_counts = {}
        for item in new_links:
            ftype = item['type']
            type_counts[ftype] = type_counts.get(ftype, 0) + 1
        
        # Update user data
        from handlers import user_data, get_destination_channel
        
        user_data[user_id].update({
            'items': new_links,  # Only NEW links!
            'file_path': new_file_path,
            'step': 'select_range',
            'mode': 'compare',
            'comparison_stats': stats
        })
        
        # Check destination
        destination = await get_destination_channel(user_id)
        dest_info = ""
        if destination:
            dest_info = f"\n🎯 Destination: {destination[1] or destination[0]}\n"
        
        # Results
        if len(new_links) == 0:
            await status.edit_text(
                f"🟢 **COMPARISON COMPLETE**\n\n"
                f"📊 **Statistics:**\n"
                f"📄 Old File: {stats['total_old']} links\n"
                f"📄 New File: {stats['total_new']} links\n"
                f"✅ Common: {stats['common']} links\n"
                f"🗑️ Removed: {stats['old_only']} links\n\n"
                f"🎉 **No new links found!**\n"
                f"All links in new file already exist in old file.\n\n"
                f"💡 Nothing to download!"
            )
            
            # Cleanup
            cleanup_compare_data(user_id, compare_data)
            return
        
        # Build keyboard
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Select Range", callback_data="select_range")],
            [InlineKeyboardButton("⬇️ Download All NEW", callback_data="download_all")]
        ])
        
        type_info = "\n".join([
            f"{'🎬' if t == 'video' else '🖼️' if t == 'image' else '📄'} {t.title()}s: {c}" 
            for t, c in type_counts.items()
        ])
        
        await status.edit_text(
            f"🟢 **COMPARISON COMPLETE!**\n\n"
            f"📊 **Statistics:**\n"
            f"📄 Old: {stats['total_old']} links\n"
            f"📄 New: {stats['total_new']} links\n"
            f"✅ Common: {stats['common']}\n"
            f"🆕 **NEW LINKS: {stats['new_only']}** ⭐\n"
            f"🗑️ Removed: {stats['old_only']}\n\n"
            f"🎯 **NEW LINKS DETECTED:**\n"
            f"{type_info}\n"
            f"📦 Total NEW: {len(new_links)}{dest_info}\n\n"
            f"🚀 Ready to download NEW links only!",
            reply_markup=kb
        )
        
        # Cleanup old file
        old_file_path = compare_data.get('old_file_path')
        if old_file_path and os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
            except:
                pass
        
    except Exception as e:
        logger.error(f"Comparison error: {e}", exc_info=True)
        await status.edit_text(
            f"❌ **Comparison Failed**\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Please try again or contact support."
        )
        cleanup_compare_data(user_id, compare_data)


def cleanup_compare_data(user_id: int, compare_data: dict):
    """Cleanup comparison temporary data"""
    try:
        old_file_path = compare_data.get('old_file_path')
        if old_file_path and os.path.exists(old_file_path):
            os.remove(old_file_path)
    except:
        pass
    
    from handlers import user_data
    if user_id in user_data and 'compare_data' in user_data[user_id]:
        del user_data[user_id]['compare_data']


def setup_processing_handlers(app: Client):
    """Setup remaining handlers (range, quality, etc.)"""
    from handlers import user_data, active_downloads, download_progress
    
    @app.on_callback_query(filters.regex(r"^(select_range|download_all)$"))
    async def range_select(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id
        action = callback.data
        
        if user_id not in user_data:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        items = user_data[user_id]['items']
        current_mode = user_data[user_id].get('mode', 'original')
        mode_emoji = "🔵" if current_mode == "original" else "🟢"
        
        if action == "download_all":
            user_data[user_id]['range'] = (1, len(items))
            user_data[user_id]['step'] = 'ask_caption'
            
            await callback.message.edit_text(
                f"{mode_emoji} **{current_mode.upper()} MODE**\n\n"
                f"✏️ **Custom Caption (Optional)**\n\n"
                f"📦 Processing {len(items)} items\n\n"
                f"Do you want to add custom text to captions?\n\n"
                f"**Options:**\n"
                f"• Send your custom text (will be added to each caption)\n"
                f"• Send `/skip` to skip this step\n\n"
                f"Example: 'Downloaded by @MyBot'\n"
                f"This will be added after default caption."
            )
        else:
            user_data[user_id]['step'] = 'range_input'
            await callback.message.edit_text(
                f"{mode_emoji} **{current_mode.upper()} MODE**\n\n"
                f"📊 **Range Selection**\n\n"
                f"Total: {len(items)} items\n\n"
                f"📝 Send range:\n"
                f"• `1-50` → Items 1 to 50\n"
                f"• `10-20` → Items 10 to 20\n"
                f"• `5` → Only item 5\n\n"
                f"⏳ Waiting..."
            )
    
    
    @app.on_message(filters.text & filters.private)
    async def handle_text_input(client: Client, message: Message):
        user_id = message.from_user.id
        text = message.text.strip()
        
        if user_id not in user_data:
            # Check if it's a channel link/ID
            if text.startswith('t.me/') or text.startswith('-') or text.isdigit():
                from utils import extract_channel_id, save_destination_channel
                channel_id = extract_channel_id(text)
                if channel_id:
                    await save_destination_channel(user_id, channel_id, text)
                    await message.reply_text(
                        f"✅ **Destination Set!**\n\n"
                        f"🆔 ID: `{channel_id}`\n"
                        f"Use /clear to remove it."
                    )
            return
        
        step = user_data[user_id].get('step', '')
        items = user_data[user_id]['items']
        
        # Handle range input
        if step == 'range_input':
            try:
                if '-' in text:
                    start, end = map(int, text.split('-'))
                else:
                    start = end = int(text)
                
                if start < 1 or end > len(items) or start > end:
                    await message.reply_text(
                        f"❌ Invalid! Valid: 1-{len(items)}"
                    )
                    return
                
                user_data[user_id]['range'] = (start, end)
                user_data[user_id]['step'] = 'ask_caption'
                
                count = end - start + 1
                await message.reply_text(
                    f"✅ **Range: {start}-{end}** ({count} items)\n\n"
                    f"✏️ **Custom Caption (Optional)**\n\n"
                    f"Send custom text or `/skip` to continue."
                )
                
            except:
                await message.reply_text("❌ Invalid format! Use: `1-10` or `5`")
        
        # Handle custom caption
        elif step == 'ask_caption':
            if text.lower() == '/skip':
                user_data[user_id]['custom_caption'] = ""
                user_data[user_id]['step'] = 'ask_watermark'
                
                await message.reply_text(
                    f"✏️ **Text Watermark (Optional)**\n\n"
                    f"Add text overlay on video thumbnails?\n\n"
                    f"**Options:**\n"
                    f"• Send your watermark text\n"
                    f"• Send `/skip` to skip\n\n"
                    f"Example: '@MyChannel' or 'My Brand'\n"
                    f"Text will appear on thumbnails."
                )
            else:
                user_data[user_id]['custom_caption'] = text
                user_data[user_id]['step'] = 'ask_watermark'
                
                await message.reply_text(
                    f"✅ **Caption Saved!**\n\n"
                    f"Preview: `{text[:50]}...`\n\n"
                    f"✏️ **Text Watermark (Optional)**\n\n"
                    f"Add watermark on thumbnails?\n"
                    f"Send text or `/skip`"
                )
        
        # Handle watermark text
        elif step == 'ask_watermark':
            if text.lower() == '/skip':
                user_data[user_id]['watermark_text'] = ""
            else:
                user_data[user_id]['watermark_text'] = text
            
            user_data[user_id]['step'] = 'select_quality'
            
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("360p", callback_data="q_360p"),
                    InlineKeyboardButton("480p", callback_data="q_480p")
                ],
                [
                    InlineKeyboardButton("720p ⭐", callback_data="q_720p"),
                    InlineKeyboardButton("1080p 🔥", callback_data="q_1080p")
                ]
            ])
            
            start, end = user_data[user_id]['range']
            caption_preview = user_data[user_id].get('custom_caption', 'None')
            watermark_preview = user_data[user_id].get('watermark_text', 'None')
            current_mode = user_data[user_id].get('mode', 'original')
            mode_emoji = "🔵" if current_mode == "original" else "🟢"
            
            await message.reply_text(
                f"{mode_emoji} **FINAL CONFIGURATION**\n\n"
                f"📊 Range: {start}-{end}\n"
                f"✏️ Caption: {caption_preview[:30]}...\n"
                f"🎨 Watermark: {watermark_preview[:20]}...\n\n"
                f"🎬 **Select Video Quality:**",
                reply_markup=kb
            )
    
    
    @app.on_callback_query(filters.regex(r"^q_"))
    async def quality_cb(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id
        quality = callback.data.split("_")[1]
        
        if user_id not in user_data or 'range' not in user_data[user_id]:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        items = user_data[user_id]['items']
        file_path = user_data[user_id]['file_path']
        start, end = user_data[user_id]['range']
        custom_caption = user_data[user_id].get('custom_caption', '')
        watermark_text = user_data[user_id].get('watermark_text', '')
        current_mode = user_data[user_id].get('mode', 'original')
        
        selected_items = items[start-1:end]
        active_downloads[user_id] = True
        
        # Get destination
        from utils import get_destination_channel
        destination = await get_destination_channel(user_id)
        dest_id = destination[0] if destination else callback.message.chat.id
        dest_name = destination[1] if destination and destination[1] else "This Chat"
        
        stop_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⛔ Stop All", callback_data="stop")
        ]])
        
        mode_emoji = "🔵" if current_mode == "original" else "🟢"
        mode_text = "ORIGINAL" if current_mode == "original" else "COMPARE (NEW ONLY)"
        
        await callback.message.edit_text(
            f"{mode_emoji} **{mode_text} MODE**\n\n"
            f"🚀 **HYDROGEN BOMB ACTIVATED!**\n\n"
            f"⚡ Quality: {quality}\n"
            f"📊 Range: {start}-{end} ({len(selected_items)} items)\n"
            f"🎯 Destination: {dest_name}\n"
            f"✏️ Custom Caption: {'✅' if custom_caption else '❌'}\n"
            f"🎨 Watermark: {'✅' if watermark_text else '❌'}\n\n"
            f"💪 Processing at maximum speed...",
            reply_markup=stop_kb
        )
        
        # Process batch
        from handlers_part2 import process_batch
        await process_batch(
            client, callback.message, selected_items, 
            quality, start, end, user_id, dest_id,
            custom_caption, watermark_text
        )
        
        # Cleanup
        from handlers_part2 import cleanup_user_data
        cleanup_user_data(user_id, file_path)
    
    
    @app.on_callback_query(filters.regex("^stop$"))
    async def stop_cb(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id
        active_downloads[user_id] = False
        await callback.answer("⛔ Stopping...", show_alert=True)
    
    
    @app.on_message(filters.command("cancel"))
    async def cancel_cmd(client: Client, message: Message):
        user_id = message.from_user.id
        active_downloads[user_id] = False
        await message.reply_text("⛔ All downloads cancelled!")


# Processing functions (same as v10.0 but available here)
async def process_batch(
    client: Client,
    message: Message,
    items: list,
    quality: str,
    start: int,
    end: int,
    user_id: int,
    destination_id: int,
    custom_caption: str = "",
    watermark_text: str = ""
):
    """Process batch - SAME AS v10.0"""
    from handlers import active_downloads, download_progress
    
    success = 0
    failed = 0
    skipped = 0
    
    for idx, item in enumerate(items, start):
        if not active_downloads.get(user_id, False):
            await message.reply_text("⛔ Stopped by user!")
            break
        
        prog = await message.reply_text(
            f"📦 **Item {idx}/{end}**\n"
            f"📝 {item['title'][:50]}...\n"
            f"🚀 Processing..."
        )
        
        try:
            base_caption = f"{idx}. {item['title']}"
            if custom_caption:
                base_caption += f"\n\n{custom_caption}"
            
            if is_youtube_url(item['url']) or is_unsupported_platform(item['url']):
                platform = "YouTube" if is_youtube_url(item['url']) else "Social Media"
                await prog.edit_text(f"🎬 {platform} detected! Sending link...")
                
                await send_failed_link(
                    client, destination_id, item['title'],
                    item['url'], idx, 
                    f"{platform} link - Open manually",
                    item['type']
                )
                skipped += 1
                await prog.delete()
                continue
            
            if item['type'] == 'video':
                result = await process_video(
                    client, message, item, quality,
                    base_caption, idx, prog, user_id,
                    destination_id, watermark_text
                )
            elif item['type'] == 'image':
                result = await process_image(
                    client, message, item, base_caption,
                    idx, prog, user_id, destination_id
                )
            elif item['type'] == 'document':
                result = await process_document(
                    client, message, item, base_caption,
                    idx, prog, user_id, destination_id
                )
            else:
                result = False
            
            if result == 'FAILED':
                await send_failed_link(
                    client, destination_id, item['title'],
                    item['url'], idx, 
                    "Processing failed - Check link manually",
                    item['type']
                )
                failed += 1
            elif result:
                success += 1
            else:
                failed += 1
        
        except Exception as e:
            logger.error(f"Item {idx} error: {e}", exc_info=True)
            try:
                await prog.delete()
                await send_failed_link(
                    client, destination_id, item['title'],
                    item['url'], idx, f"Error: {str(e)[:50]}",
                    item['type']
                )
            except:
                pass
            failed += 1
        
        await asyncio.sleep(0.3)
    
    await message.reply_text(
        f"✅ **BATCH COMPLETE!**\n\n"
        f"✔️ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"⏭️ Skipped: {skipped}\n"
        f"📊 Total: {len(items)}\n"
        f"📍 Range: {start}-{end}\n\n"
        f"🚀 HYDROGEN BOMB v11.0 delivered!"
    )


async def process_video(
    client: Client, message: Message, item: dict,
    quality: str, caption: str, idx: int,
    prog: Message, user_id: int, dest_id: int,
    watermark: str = ""
) -> bool:
    """Process video - SAME AS v10.0"""
    from handlers import active_downloads, download_progress
    
    try:
        safe = sanitize_filename(item['title'])
        fname = f"{safe}_{idx}.mp4"
        
        vpath = await download_video(
            item['url'], quality, fname, prog,
            user_id, active_downloads, download_progress
        )
        
        if vpath == 'UNSUPPORTED':
            return 'FAILED'
        
        if not vpath or not validate_video_file(vpath):
            return 'FAILED'
        
        await prog.edit_text("🎬 Analyzing...")
        video_info = get_video_info(vpath)
        
        quality_height = QUALITY_SETTINGS[quality]['height']
        if video_info['height'] != quality_height:
            await prog.edit_text(f"⚙️ Converting to {quality}...")
            conv_path = str(DOWNLOAD_DIR / f"conv_{fname}")
            
            success = await convert_video_quality(vpath, conv_path, quality)
            
            if success:
                os.remove(vpath)
                vpath = conv_path
                video_info = get_video_info(vpath)
        
        thumb_path = str(DOWNLOAD_DIR / f"thumb_{user_id}_{idx}.jpg")
        has_thumb = generate_thumbnail_with_text(
            vpath, thumb_path, watermark, video_info['duration']
        )
        
        await prog.edit_text("📤 Uploading...")
        upload_success = await send_to_destination(
            client, dest_id, vpath, caption, 'video',
            prog, thumb_path if has_thumb else None,
            video_info['duration'], video_info['width'], video_info['height']
        )
        
        try:
            os.remove(vpath)
            if has_thumb and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except:
            pass
        
        await prog.delete()
        return upload_success
        
    except Exception as e:
        logger.error(f"Video error: {e}")
        return False


async def process_image(
    client: Client, message: Message, item: dict,
    caption: str, idx: int, prog: Message,
    user_id: int, dest_id: int
) -> bool:
    """Process image - SAME AS v10.0"""
    from handlers import active_downloads
    
    try:
        safe = sanitize_filename(item['title'])
        ext = os.path.splitext(item['url'])[1] or '.jpg'
        fname = f"{safe}_{idx}{ext}"
        
        ipath = await download_file(
            item['url'], fname, prog, user_id, active_downloads
        )
        
        if not ipath:
            return 'FAILED'
        
        await prog.edit_text("📤 Uploading...")
        success = await send_to_destination(
            client, dest_id, ipath, caption, 'image', prog
        )
        
        try:
            os.remove(ipath)
        except:
            pass
        
        await prog.delete()
        return success
        
    except Exception as e:
        logger.error(f"Image error: {e}")
        return False


async def process_document(
    client: Client, message: Message, item: dict,
    caption: str, idx: int, prog: Message,
    user_id: int, dest_id: int
) -> bool:
    """Process document - SAME AS v10.0"""
    from handlers import active_downloads
    
    try:
        safe = sanitize_filename(item['title'])
        ext = os.path.splitext(item['url'])[1] or '.pdf'
        fname = f"{safe}_{idx}{ext}"
        
        dpath = await download_file(
            item['url'], fname, prog, user_id, active_downloads
        )
        
        if not dpath:
            return 'FAILED'
        
        await prog.edit_text("📤 Uploading...")
        success = await send_to_destination(
            client, dest_id, dpath, caption, 'document', prog
        )
        
        try:
            os.remove(dpath)
        except:
            pass
        
        await prog.delete()
        return success
        
    except Exception as e:
        logger.error(f"Document error: {e}")
        return False


def cleanup_user_data(user_id: int, file_path: str):
    """Cleanup - SAME AS v10.0"""
    from handlers import user_data, active_downloads, download_progress
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
    
    for pattern in [f"temp_{user_id}_*", f"thumb_{user_id}_*", f"*_part*", f"conv_*"]:
        for tf in DOWNLOAD_DIR.glob(pattern):
            try:
                os.remove(tf)
            except:
                pass
    
    if user_id in user_data:
        del user_data[user_id]
    if user_id in active_downloads:
        del active_downloads[user_id]
    if user_id in download_progress:
        del download_progress[user_id]
