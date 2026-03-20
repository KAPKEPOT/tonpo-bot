# fx/bot/keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Optional


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Get yes/no confirmation keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data='confirm_yes'),
            InlineKeyboardButton("❌ No", callback_data='confirm_no')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_risk_keyboard() -> InlineKeyboardMarkup:
    """Get risk selection keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("0.5% (Conservative)", callback_data='risk_0.5'),
            InlineKeyboardButton("1% (Moderate)", callback_data='risk_1.0')
        ],
        [
            InlineKeyboardButton("2% (Aggressive)", callback_data='risk_2.0'),
            InlineKeyboardButton("Custom", callback_data='risk_custom')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_plans_keyboard() -> InlineKeyboardMarkup:
    """Get subscription plans keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("Free", callback_data='plan_free'),
            InlineKeyboardButton("Basic $9.99", callback_data='plan_basic')
        ],
        [
            InlineKeyboardButton("Pro $29.99", callback_data='plan_pro'),
            InlineKeyboardButton("Enterprise $99.99", callback_data='plan_enterprise')
        ],
        [InlineKeyboardButton("Compare Plans", callback_data='plan_compare')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_upgrade_keyboard(plan_tier: str) -> InlineKeyboardMarkup:
    """Get upgrade confirmation keyboard for a specific plan"""
    keyboard = [
        [
            InlineKeyboardButton(
                "💰 Pay with USDT (ERC-20)",
                callback_data=f'pay_usdt_{plan_tier}'
            )
        ],
        [
            InlineKeyboardButton(
                "₿ Pay with BTC",
                callback_data=f'pay_btc_{plan_tier}'
            )
        ],
        [
            InlineKeyboardButton("📅 Monthly", callback_data=f'period_monthly_{plan_tier}'),
            InlineKeyboardButton("📅 Yearly (save 17%)", callback_data=f'period_yearly_{plan_tier}')
        ],
        [
            InlineKeyboardButton("🔙 Back to Plans", callback_data='plan_compare')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
  
def get_payment_pending_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    """Get keyboard shown while waiting for payment"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Check Status", callback_data=f'pay_check_{payment_id}')
        ],
        [
            InlineKeyboardButton("❌ Cancel Payment", callback_data=f'pay_cancel_{payment_id}')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)      
def get_trade_confirmation_keyboard(trade_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Get trade confirmation keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Execute", callback_data='trade_execute'),
            InlineKeyboardButton("📊 Adjust Risk", callback_data='trade_adjust')
        ],
        [
            InlineKeyboardButton("✏️ Modify", callback_data='trade_modify'),
            InlineKeyboardButton("❌ Cancel", callback_data='trade_cancel')
        ]
    ]
    
    # Add multiple TPs info if applicable
    if len(trade_data.get('signal', {}).get('take_profits', [])) > 1:
        keyboard.insert(0, [
            InlineKeyboardButton("🎯 Multiple TPs", callback_data='trade_info')
        ])
    
    return InlineKeyboardMarkup(keyboard)


def get_execution_keyboard() -> InlineKeyboardMarkup:
    """Get execution decision keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Execute Now", callback_data='trade_execute'),
            InlineKeyboardButton("❌ Cancel", callback_data='trade_cancel')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Get main settings keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("⚖️ Risk", callback_data='settings_risk'),
            InlineKeyboardButton("🔔 Notifications", callback_data='settings_notifications')
        ],
        [
            InlineKeyboardButton("📊 Symbols", callback_data='settings_symbols'),
            InlineKeyboardButton("🔌 Connection", callback_data='settings_connection')
        ],
        [
            InlineKeyboardButton("🔑 API", callback_data='settings_api'),
            InlineKeyboardButton("❌ Close", callback_data='settings_close')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_risk_settings_keyboard(user) -> InlineKeyboardMarkup:
    """Get risk settings keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(
                f"Default Risk ({user.default_risk_factor*100:.1f}%)",
                callback_data='risk_default'
            )
        ],
        [
            InlineKeyboardButton(
                f"Max Size ({user.max_position_size})",
                callback_data='risk_max_size'
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data='risk_back')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_notification_settings_keyboard(settings) -> InlineKeyboardMarkup:
    """Get notification settings keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(
                f"Trade: {'✅' if settings.notify_on_trade else '❌'}",
                callback_data='notify_trade'
            )
        ],
        [
            InlineKeyboardButton(
                f"Error: {'✅' if settings.notify_on_error else '❌'}",
                callback_data='notify_error'
            )
        ],
        [
            InlineKeyboardButton(
                f"Daily Report: {'✅' if settings.notify_daily_report else '❌'}",
                callback_data='notify_daily'
            )
        ],
        [
            InlineKeyboardButton(
                f"Report Time ({settings.notification_hour}:00)",
                callback_data='notify_hour'
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data='notify_back')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_symbol_settings_keyboard(user) -> InlineKeyboardMarkup:
    """Get symbol settings keyboard"""
    keyboard = [
        [InlineKeyboardButton("➕ Allow Symbol", callback_data='symbol_add')],
        [InlineKeyboardButton("➖ Block Symbol", callback_data='symbol_remove')],
        [InlineKeyboardButton("🔄 Clear All", callback_data='symbol_clear')],
        [InlineKeyboardButton("🔙 Back", callback_data='symbol_back')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_connection_settings_keyboard() -> InlineKeyboardMarkup:
    """Get connection settings keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔄 Test Connection", callback_data='conn_test')],
        [InlineKeyboardButton("✏️ Update Credentials", callback_data='conn_update')],
        [InlineKeyboardButton("🔙 Back", callback_data='conn_back')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_api_settings_keyboard(settings) -> InlineKeyboardMarkup:
    """Get API settings keyboard"""
    keyboard = []
    
    if settings.api_enabled and settings.api_key:
        keyboard.append([InlineKeyboardButton("🔄 Regenerate Key", callback_data='api_generate')])
        keyboard.append([InlineKeyboardButton("❌ Revoke Key", callback_data='api_revoke')])
    else:
        keyboard.append([InlineKeyboardButton("🔑 Generate API Key", callback_data='api_generate')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='api_back')])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Get admin main keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("👥 Users", callback_data='admin_users'),
            InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data='admin_stats'),
            InlineKeyboardButton("⚠️ Alerts", callback_data='admin_alerts')
        ],
        [InlineKeyboardButton("❌ Close", callback_data='admin_close')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_user_keyboard(users: List) -> InlineKeyboardMarkup:
    """Get admin user selection keyboard"""
    keyboard = []
    
    for user in users[:5]:  # Show first 5
        username = user.telegram_username or str(user.telegram_id)
        keyboard.append([
            InlineKeyboardButton(
                f"@{username} - {user.subscription_tier}",
                callback_data=f'user_select_{user.telegram_id}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='user_back')])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_user_actions_keyboard(user) -> InlineKeyboardMarkup:
    """Get admin user actions keyboard"""
    keyboard = []
    
    if user.is_banned:
        keyboard.append([InlineKeyboardButton("🔓 Unban User", callback_data=f'user_unban_{user.telegram_id}')])
    else:
        keyboard.append([InlineKeyboardButton("🔒 Ban User", callback_data=f'user_ban_{user.telegram_id}')])
    
    # Add admin promotion if not already admin
    if user.telegram_id not in settings.ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("👑 Make Admin", callback_data=f'user_make_admin_{user.telegram_id}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='user_back')])
    
    return InlineKeyboardMarkup(keyboard)


def get_pagination_keyboard(page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    """Get pagination keyboard"""
    keyboard = []
    row = []
    
    if page > 1:
        row.append(InlineKeyboardButton("◀️ Prev", callback_data=f'{prefix}_page_{page-1}'))
    
    row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data='noop'))
    
    if page < total_pages:
        row.append(InlineKeyboardButton("Next ▶️", callback_data=f'{prefix}_page_{page+1}'))
    
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f'{prefix}_back')])
    
    return InlineKeyboardMarkup(keyboard)