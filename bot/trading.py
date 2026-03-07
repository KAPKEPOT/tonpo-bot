# fx/bot/trading.py
import asyncio
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, CallbackContext, MessageHandler, CallbackQueryHandler, filters
from sqlalchemy.orm import Session

from database.repositories import UserRepository
from services.trade_executor import TradeExecutor
from services.mt5_manager import MT5ConnectionManager
from services.risk_service import RiskService
from services.subscription import SubscriptionService
from bot.keyboards import get_trade_confirmation_keyboard
from utils.formatters import format_trade_calculation, format_positions, format_balance

logger = logging.getLogger(__name__)

# Conversation states
(ENTER_TRADE, CONFIRM_TRADE, ADJUST_RISK, EXECUTING) = range(4)

TRADING_STATES = {
    ENTER_TRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, TradingHandler.receive_trade)],
    CONFIRM_TRADE: [CallbackQueryHandler(TradingHandler.confirm_trade, pattern='^trade_')],
    ADJUST_RISK: [MessageHandler(filters.TEXT, TradingHandler.adjust_risk)],
    EXECUTING: [],  # No input while executing
}


class TradingHandler:
    """
    Handles trading conversations
    """
    
    def __init__(self, db_session: Session, bot):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.trade_executor = TradeExecutor(db_session, bot)
        self.mt5_manager = MT5ConnectionManager(db_session)
        self.risk_service = RiskService()
        self.sub_service = SubscriptionService(db_session)
        
        # Track active trades for rate limiting
        self.active_trades = {}
    
    def start_trade(self, update: Update, context: CallbackContext) -> int:
        """Start the trade placement flow"""
        user_id = update.effective_user.id
        
        # Check if user is registered
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user or not user.is_verified:
            update.message.reply_text(
                "❌ You need to register first!\n\nUse /register to connect your MT5 account."
            )
            return ConversationHandler.END
        
        # Check if already in a trade
        if user_id in self.active_trades:
            update.message.reply_text(
                "⚠️ You already have a trade in progress. Please wait or use /cancel."
            )
            return ConversationHandler.END
        
        # Check daily limit
        can_trade, limit_info = self.sub_service.check_trade_limit(user_id)
        if not can_trade:
            update.message.reply_text(
                f"❌ *Daily trade limit reached*\n\n"
                f"You've used {limit_info['current']}/{limit_info['limit']} trades today.\n"
                f"Limit resets at midnight UTC.\n\n"
                f"Upgrade with /upgrade for higher limits.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        context.user_data['action'] = 'trade'
        context.user_data['trade_start'] = asyncio.get_event_loop().time()
        
        update.message.reply_text(
            "📝 *Enter your trade signal*\n\n"
            "Use this format:\n"
            "```\n"
            "BUY/SELL [LIMIT/STOP] SYMBOL\n"
            "Entry PRICE or NOW\n"
            "SL PRICE\n"
            "TP1 PRICE\n"
            "TP2 PRICE (optional)\n"
            "```\n\n"
            "Example:\n"
            "```\n"
            "BUY GBPUSD\n"
            "Entry NOW\n"
            "SL 1.25000\n"
            "TP 1.26000\n"
            "```",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ENTER_TRADE
    
    def start_calculate(self, update: Update, context: CallbackContext) -> int:
        """Start the calculation flow (no execution)"""
        user_id = update.effective_user.id
        
        # Check if user is registered
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user or not user.is_verified:
            update.message.reply_text(
                "❌ You need to register first!\n\nUse /register to connect your MT5 account."
            )
            return ConversationHandler.END
        
        context.user_data['action'] = 'calculate'
        
        update.message.reply_text(
            "📊 *Enter trade to calculate*\n\n"
            "Use the same format as /trade, but I won't execute it.\n\n"
            "```\n"
            "BUY/SELL [LIMIT/STOP] SYMBOL\n"
            "Entry PRICE or NOW\n"
            "SL PRICE\n"
            "TP1 PRICE\n"
            "TP2 PRICE (optional)\n"
            "```",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ENTER_TRADE
    
    def receive_trade(self, update: Update, context: CallbackContext) -> int:
        """Receive and parse trade signal"""
        user_id = update.effective_user.id
        signal_text = update.message.text
        
        # Store signal for later use
        context.user_data['signal_text'] = signal_text
        
        # Show processing message
        processing_msg = update.message.reply_text("🔄 Processing your signal...")
        context.user_data['processing_msg_id'] = processing_msg.message_id
        
        # Parse and calculate based on action
        if context.user_data['action'] == 'trade':
            return self._process_trade(update, context)
        else:
            return self._process_calculation(update, context)
    
    async def _process_trade(self, update: Update, context: CallbackContext) -> int:
        """Process a trade signal for execution"""
        user_id = update.effective_user.id
        signal_text = context.user_data['signal_text']
        
        # Mark as active
        self.active_trades[user_id] = context.user_data.get('trade_start')
        
        try:
            # Calculate trade first
            result = await self.trade_executor.calculate_only(user_id, signal_text)
            
            if not result['success']:
                await self._edit_message(
                    update, context,
                    f"❌ *Invalid signal*\n\nError: {result['error']}\n\nPlease try again or /cancel",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ENTER_TRADE
            
            # Store calculation result
            context.user_data['calculation'] = result
            
            # Check if multiple TPs are allowed
            if len(result['signal']['take_profits']) > 1:
                has_feature = self.sub_service.check_feature_access(user_id, 'multiple_tps')
                if not has_feature:
                    # Show upgrade prompt
                    await self._edit_message(
                        update, context,
                        "⚠️ *Multiple Take Profits*\n\n"
                        "Your current plan doesn't support multiple TP levels.\n"
                        "Only the first TP will be used.\n\n"
                        "Upgrade with /upgrade to enable this feature.",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_trade_confirmation_keyboard(result)
                    )
                    return CONFIRM_TRADE
            
            # Show confirmation
            formatted = format_trade_calculation(result)
            await self._edit_message(
                update, context,
                formatted,
                parse_mode=ParseMode.HTML,
                reply_markup=get_trade_confirmation_keyboard(result)
            )
            
            return CONFIRM_TRADE
            
        except Exception as e:
            logger.error(f"Trade processing error: {e}")
            await self._edit_message(
                update, context,
                f"❌ Error processing trade: {str(e)[:100]}\n\nPlease try again or /cancel"
            )
            return ENTER_TRADE
        finally:
            # Remove from active
            self.active_trades.pop(user_id, None)
    
    async def _process_calculation(self, update: Update, context: CallbackContext) -> int:
        """Process a calculation request"""
        user_id = update.effective_user.id
        signal_text = context.user_data['signal_text']
        
        try:
            result = await self.trade_executor.calculate_only(user_id, signal_text)
            
            if not result['success']:
                await self._edit_message(
                    update, context,
                    f"❌ *Invalid signal*\n\nError: {result['error']}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END
            
            # Format and send result
            formatted = format_trade_calculation(result, show_confirmation=False)
            await self._edit_message(
                update, context,
                formatted,
                parse_mode=ParseMode.HTML
            )
            
            # Ask if they want to execute
            from bot.keyboards import get_execution_keyboard
            
            await context.bot.send_message(
                chat_id=user_id,
                text="Would you like to execute this trade?",
                reply_markup=get_execution_keyboard()
            )
            
            context.user_data['calculation'] = result
            return CONFIRM_TRADE
            
        except Exception as e:
            logger.error(f"Calculation error: {e}")
            await self._edit_message(
                update, context,
                f"❌ Error calculating: {str(e)[:100]}"
            )
            return ConversationHandler.END
    
    def confirm_trade(self, update: Update, context: CallbackContext) -> int:
        """Handle trade confirmation"""
        query = update.callback_query
        query.answer()
        
        action = query.data.replace('trade_', '')
        
        if action == 'execute':
            # Execute the trade
            query.edit_message_text("🔄 Executing trade...")
            return self._execute_trade(update, context)
        
        elif action == 'adjust':
            # Adjust risk
            query.edit_message_text(
                "Enter new risk percentage (e.g., 1.5 for 1.5%):"
            )
            return ADJUST_RISK
        
        elif action == 'cancel':
            # Cancel
            query.edit_message_text("❌ Trade cancelled.")
            context.user_data.clear()
            return ConversationHandler.END
        
        elif action == 'modify':
            # Modify trade parameters
            query.edit_message_text(
                "Please re-enter your trade with modified parameters:"
            )
            return ENTER_TRADE
    
    async def _execute_trade(self, update: Update, context: CallbackContext) -> int:
        """Execute the confirmed trade"""
        user_id = update.effective_user.id
        calculation = context.user_data.get('calculation')
        
        if not calculation:
            await self._edit_message(
                update, context,
                "❌ Trade data lost. Please start over with /trade"
            )
            return ConversationHandler.END
        
        try:
            # Execute trade
            result = await self.trade_executor.execute_trade(
                user_id,
                context.user_data['signal_text'],
                context.user_data
            )
            
            if result['success']:
                # Success message
                success_text = (
                    "✅ *Trade Executed Successfully!*\n\n"
                    f"📊 Position Size: {result['calculated']['position_size']}\n"
                    f"💰 Risk: ${result['calculated']['potential_loss']:,.2f}\n"
                    f"🎯 Target: ${result['calculated']['potential_profit']:,.2f}\n"
                    f"📈 R:R Ratio: 1:{result['calculated']['risk_reward']:.2f}\n\n"
                )
                
                if 'orders' in result:
                    order_ids = [o.get('orderId', 'N/A') for o in result['orders']]
                    success_text += f"Order IDs: {', '.join(order_ids)}"
                
                await self._edit_message(
                    update, context,
                    success_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Failure message
                await self._edit_message(
                    update, context,
                    f"❌ *Trade Failed*\n\nError: {result.get('error', 'Unknown error')}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            await self._edit_message(
                update, context,
                f"❌ *Execution Error*\n\n{str(e)[:200]}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Clean up
        context.user_data.clear()
        return ConversationHandler.END
    
    def adjust_risk(self, update: Update, context: CallbackContext) -> int:
        """Adjust risk percentage"""
        try:
            risk = float(update.message.text)
            risk_factor = risk / 100
            
            if risk_factor < 0.001 or risk_factor > 0.1:
                raise ValueError
            
            # Update calculation with new risk
            calculation = context.user_data.get('calculation')
            if calculation:
                # Recalculate with new risk
                # This would need to call risk service again
                pass
            
            # Show updated calculation
            from bot.keyboards import get_trade_confirmation_keyboard
            
            update.message.reply_text(
                f"✅ Risk set to {risk:.1f}%\n\n"
                "Review updated calculation:",
                reply_markup=get_trade_confirmation_keyboard(calculation)
            )
            
            return CONFIRM_TRADE
            
        except ValueError:
            update.message.reply_text(
                "❌ Invalid percentage. Please enter a number between 0.1 and 10:"
            )
            return ADJUST_RISK
    
    async def handle_action(self, update: Update, context: CallbackContext) -> None:
        """Handle simple actions (balance, positions)"""
        user_id = update.effective_user.id
        action = context.user_data.get('action')
        
        try:
            connection = await self.mt5_manager.get_connection(user_id)
            
            if action == 'balance':
                account_info = await connection.get_account_information()
                formatted = format_balance(account_info)
                await update.message.reply_text(formatted, parse_mode=ParseMode.HTML)
            
            elif action == 'positions':
                positions = await connection.get_positions()
                if positions:
                    formatted = format_positions(positions)
                    await update.message.reply_text(formatted, parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_text("No open positions.")
            
        except Exception as e:
            logger.error(f"Action {action} failed: {e}")
            await update.message.reply_text(
                f"❌ Failed to get {action}: {str(e)[:100]}"
            )
        
        context.user_data.clear()
    
    async def _edit_message(self, update: Update, context: CallbackContext, 
                           text: str, **kwargs):
        """Edit the processing message or send new one"""
        msg_id = context.user_data.get('processing_msg_id')
        
        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_user.id,
                    message_id=msg_id,
                    text=text,
                    **kwargs
                )
            except:
                # If edit fails, send new message
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=text,
                    **kwargs
                )
        else:
            await update.message.reply_text(text, **kwargs)
    
    def cancel(self, update: Update, context: CallbackContext) -> int:
        """Cancel the current operation"""
        user_id = update.effective_user.id
        
        # Remove from active trades
        self.active_trades.pop(user_id, None)
        
        update.message.reply_text(
            "❌ Operation cancelled."
        )
        
        context.user_data.clear()
        return ConversationHandler.END