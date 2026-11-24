#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notifier.py - โมดูลสำหรับส่งข้อความสรุปผลการซิงค์ผ่าน Telegram Bot API และ LINE Messaging API
"""

import json
import logging
import os
import sys

import requests

from app_paths import get_app_dir

LOG_FILE = os.path.join(get_app_dir(), "sync.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)


def log_info(msg):
    logging.info(msg)
    if sys.stdout is not None:
        print(msg)


def log_error(msg):
    logging.error(msg)
    if sys.stderr is not None:
        print(msg, file=sys.stderr)


def send_telegram_message(bot_token, chat_id, text):
    """
    ส่งข้อความผ่าน Telegram Bot API
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        log_info(f"[Telegram] ส่งข้อความสำเร็จไปยัง chat_id={chat_id}")
        return True, "ส่งผ่าน Telegram สำเร็จ"
    except requests.exceptions.RequestException as e:
        safe_error = str(e).replace(bot_token, "<redacted>") if bot_token else str(e)
        err_msg = f"[Telegram] ส่งข้อความล้มเหลว: {safe_error}"
        log_error(err_msg)
        return False, err_msg


def send_line_message(channel_token, user_id, text):
    """
    ส่งข้อความผ่าน LINE Messaging API (Push Message)
    """
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {channel_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        log_info(f"[LINE] ส่งข้อความสำเร็จไปยัง user_id={user_id}")
        return True, "ส่งผ่าน LINE สำเร็จ"
    except requests.exceptions.RequestException as e:
        err_msg = f"[LINE] ส่งข้อความล้มเหลว: {str(e)}"
        log_error(err_msg)
        return False, err_msg


def send_notification(config, message, is_auto=False):
    """
    ส่งแจ้งเตือนตามการตั้งค่าใน config
    - is_auto=True: ตรวจสอบค่า notify_on_auto ในตาราง schedule
    """
    notif_cfg = config.get("notification", {})
    schedule_cfg = config.get("schedule", {})

    # ถ้าเป็นโหมดอัตโนมัติ ให้เช็กว่าเปิดใช้งานแจ้งเตือนหรือไม่
    if is_auto and not schedule_cfg.get("notify_on_auto", False):
        log_info("[Notifier] ข้ามการแจ้งเตือนอัตโนมัติ (notify_on_auto = false)")
        return

    results = []

    # Telegram
    if notif_cfg.get("telegram_enabled", False):
        token = notif_cfg.get("telegram_bot_token", "").strip()
        chat_id = notif_cfg.get("telegram_chat_id", "").strip()
        if token and chat_id:
            success, msg = send_telegram_message(token, chat_id, message)
            results.append(msg)
        else:
            log_error("[Notifier] Telegram เปิดใช้งานแต่ยังไม่ได้กรอก Bot Token หรือ Chat ID")

    # LINE
    if notif_cfg.get("line_enabled", False):
        token = notif_cfg.get("line_channel_token", "").strip()
        user_id = notif_cfg.get("line_user_id", "").strip()
        if token and user_id:
            success, msg = send_line_message(token, user_id, message)
            results.append(msg)
        else:
            log_error("[Notifier] LINE เปิดใช้งานแต่ยังไม่ได้กรอก Channel Token หรือ User ID")

    if results:
        log_info(f"[Notifier] สรุปการส่งแจ้งเตือน: {' | '.join(results)}")
    else:
        log_info("[Notifier] ไม่มีช่องทางแจ้งเตือนใดถูกเปิดใช้งานหรือกรอกข้อมูลไม่ครบ")