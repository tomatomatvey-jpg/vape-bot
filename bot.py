import asyncio
import json
import os
from dotenv import load_dotenv
load_dotenv()
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========================
# ⚙️ НАСТРОЙКИ (читаются из переменных окружения Railway)
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
COURIER_GROUP_ID = int(os.getenv("COURIER_GROUP_ID", "0"))
PAYMENT_DETAILS = os.getenv("PAYMENT_DETAILS", "Реквизиты не настроены")
PRODUCTS_FILE = "products.json"
# ========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Работа с каталогом ---
def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

# --- Корзины пользователей (хранятся в памяти) ---
user_carts: dict = {}

def get_cart(user_id):
    return user_carts.get(user_id, [])

def add_to_cart(user_id, product):
    user_carts.setdefault(user_id, []).append(product)

def clear_cart(user_id):
    user_carts[user_id] = []

# ========================
# 📋 СОСТОЯНИЯ (FSM)
# ========================
class OrderState(StatesGroup):
    address = State()
    delivery_time = State()
    payment = State()

class AdminState(StatesGroup):
    add_name = State()
    add_description = State()
    add_price = State()

# ========================
# ⌨️ КЛАВИАТУРЫ
# ========================
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Каталог товаров", callback_data="catalog")],
        [InlineKeyboardButton(text="🛒 Моя корзина", callback_data="cart")],
    ])

def admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="❌ Удалить товар", callback_data="admin_remove")],
        [InlineKeyboardButton(text="📋 Весь ассортимент", callback_data="admin_list")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])

def catalog_kb(products):
    buttons = []
    for i, p in enumerate(products):
        buttons.append([InlineKeyboardButton(
            text=f"{'🟢' if p.get('in_stock', True) else '🔴'} {p['name']} — {p['price']} руб.",
            callback_data=f"product_{i}"
        )])
    buttons.append([InlineKeyboardButton(text="🛒 Корзина", callback_data="cart")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def product_kb(idx, in_stock=True):
    buttons = []
    if in_stock:
        buttons.append([InlineKeyboardButton(text="➕ В корзину", callback_data=f"add_{idx}")])
    else:
        buttons.append([InlineKeyboardButton(text="❌ Нет в наличии", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад к каталогу", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="🛍 Продолжить покупки", callback_data="catalog")],
    ])

def payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data="paid")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order")],
    ])

# ========================
# 🏠 ОСНОВНЫЕ КОМАНДЫ
# ========================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        f"Добро пожаловать в наш вейп-шоп 🌬\n"
        f"Здесь ты можешь выбрать товар и оформить доставку прямо в Telegram.\n\n"
        f"Выбери действие 👇",
        reply_markup=main_menu_kb()
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    await message.answer("👨‍💼 Панель администратора:", reply_markup=admin_menu_kb())

@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Главное меню:", reply_markup=main_menu_kb())

# ========================
# 🏠 ГЛАВНОЕ МЕНЮ
# ========================
@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 Главное меню:", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer("Этот товар недоступен.", show_alert=True)

# ========================
# 🛍 КАТАЛОГ
# ========================
@dp.callback_query(F.data == "catalog")
async def cb_catalog(callback: CallbackQuery):
    products = load_products()
    if not products:
        await callback.message.edit_text(
            "😔 Каталог пока пуст. Загляните позже!",
            reply_markup=main_menu_kb()
        )
        return
    await callback.message.edit_text("🛍 Выберите товар:", reply_markup=catalog_kb(products))

@dp.callback_query(F.data.startswith("product_"))
async def cb_product_detail(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    products = load_products()
    if idx >= len(products):
        await callback.answer("❌ Товар не найден.")
        return
    p = products[idx]
    in_stock = p.get("in_stock", True)
    stock_label = "✅ В наличии" if in_stock else "❌ Нет в наличии"
    text = (
        f"📦 *{p['name']}*\n\n"
        f"{p.get('description', 'Описание отсутствует')}\n\n"
        f"💰 Цена: *{p['price']} руб.*\n"
        f"{stock_label}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=product_kb(idx, in_stock))

@dp.callback_query(F.data.startswith("add_"))
async def cb_add_to_cart(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    products = load_products()
    if idx >= len(products):
        await callback.answer("❌ Товар не найден.")
        return
    p = products[idx]
    if not p.get("in_stock", True):
        await callback.answer("❌ Товара нет в наличии!", show_alert=True)
        return
    add_to_cart(callback.from_user.id, p)
    await callback.answer(f"✅ {p['name']} добавлен в корзину!")

# ========================
# 🛒 КОРЗИНА
# ========================
@dp.callback_query(F.data == "cart")
async def cb_cart(callback: CallbackQuery):
    cart = get_cart(callback.from_user.id)
    if not cart:
        await callback.message.edit_text("🛒 Ваша корзина пуста.", reply_markup=main_menu_kb())
        return
    total = sum(item["price"] for item in cart)
    items_text = "\n".join([f"• {item['name']} — {item['price']} руб." for item in cart])
    text = f"🛒 *Ваша корзина:*\n\n{items_text}\n\n💰 *Итого: {total} руб.*"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=cart_kb())

@dp.callback_query(F.data == "clear_cart")
async def cb_clear_cart(callback: CallbackQuery):
    clear_cart(callback.from_user.id)
    await callback.message.edit_text("🗑 Корзина очищена.", reply_markup=main_menu_kb())

# ========================
# 📦 ОФОРМЛЕНИЕ ЗАКАЗА
# ========================
@dp.callback_query(F.data == "checkout")
async def cb_checkout(callback: CallbackQuery, state: FSMContext):
    cart = get_cart(callback.from_user.id)
    if not cart:
        await callback.answer("❌ Корзина пуста!", show_alert=True)
        return
    await state.set_state(OrderState.address)
    await callback.message.edit_text(
        "📍 *Оформление заказа — шаг 1/3*\n\n"
        "Введите адрес доставки:\n"
        "_(улица, дом, квартира, подъезд)_",
        parse_mode="Markdown"
    )

@dp.message(OrderState.address)
async def order_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(OrderState.delivery_time)
    await message.answer(
        "⏰ *Оформление заказа — шаг 2/3*\n\n"
        "Укажите удобное время доставки:\n"
        "_(например: сегодня 18:00–20:00)_",
        parse_mode="Markdown"
    )

@dp.message(OrderState.delivery_time)
async def order_delivery_time(message: Message, state: FSMContext):
    await state.update_data(delivery_time=message.text)
    cart = get_cart(message.from_user.id)
    total = sum(item["price"] for item in cart)
    items_text = "\n".join([f"• {item['name']} — {item['price']} руб." for item in cart])
    await state.set_state(OrderState.payment)
    await message.answer(
        f"💳 *Оформление заказа — шаг 3/3*\n\n"
        f"*Ваш заказ:*\n{items_text}\n\n"
        f"💰 *К оплате: {total} руб.*\n\n"
        f"Переведите сумму по реквизитам:\n"
        f"`{PAYMENT_DETAILS}`\n\n"
        f"После перевода нажмите кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=payment_kb()
    )

@dp.callback_query(F.data == "paid")
async def cb_paid(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = get_cart(callback.from_user.id)
    total = sum(item["price"] for item in cart)
    items_text = "\n".join([f"• {item['name']} — {item['price']} руб." for item in cart])
    user = callback.from_user
    username = f"@{user.username}" if user.username else f"[{user.full_name}](tg://user?id={user.id})"

    # Сообщение в группу курьеров
    courier_msg = (
        f"🛵 *НОВЫЙ ЗАКАЗ*\n\n"
        f"👤 Клиент: {user.full_name} ({username})\n"
        f"📍 Адрес: {data.get('address', '—')}\n"
        f"⏰ Время: {data.get('delivery_time', '—')}\n\n"
        f"🛍 *Состав заказа:*\n{items_text}\n\n"
        f"💰 Сумма: *{total} руб.*\n"
        f"✅ Оплата подтверждена клиентом"
    )

    try:
        await bot.send_message(COURIER_GROUP_ID, courier_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки в группу курьеров: {e}")

    await state.clear()
    clear_cart(callback.from_user.id)

    await callback.message.edit_text(
        "🎉 *Спасибо за заказ!*\n\n"
        "Ваш заказ принят и передан курьеру.\n"
        "Ожидайте доставку в указанное время! 🚀",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "cancel_order")
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Заказ отменён.", reply_markup=main_menu_kb())

# ========================
# 👨‍💼 АДМИН-ПАНЕЛЬ
# ========================
@dp.callback_query(F.data == "admin_list")
async def cb_admin_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    products = load_products()
    if not products:
        await callback.message.edit_text("Каталог пуст.", reply_markup=admin_menu_kb())
        return
    text = "📋 *Текущий ассортимент:*\n\n"
    for i, p in enumerate(products, 1):
        stock = "✅" if p.get("in_stock", True) else "❌"
        text += f"{i}. {stock} {p['name']} — {p['price']} руб.\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_menu_kb())

# --- Добавление товара ---
@dp.callback_query(F.data == "admin_add")
async def cb_admin_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminState.add_name)
    await callback.message.edit_text("➕ *Добавление товара*\n\nВведите название товара:", parse_mode="Markdown")

@dp.message(AdminState.add_name)
async def admin_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdminState.add_description)
    await message.answer("📝 Введите описание товара:")

@dp.message(AdminState.add_description)
async def admin_add_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AdminState.add_price)
    await message.answer("💰 Введите цену в рублях (только цифры):")

@dp.message(AdminState.add_price)
async def admin_add_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену (целое положительное число):")
        return
    data = await state.get_data()
    products = load_products()
    products.append({
        "name": data["name"],
        "description": data["description"],
        "price": price,
        "in_stock": True
    })
    save_products(products)
    await state.clear()
    await message.answer(
        f"✅ Товар *{data['name']}* успешно добавлен в каталог!",
        parse_mode="Markdown",
        reply_markup=admin_menu_kb()
    )

# --- Удаление товара ---
@dp.callback_query(F.data == "admin_remove")
async def cb_admin_remove(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    products = load_products()
    if not products:
        await callback.message.edit_text("Каталог пуст.", reply_markup=admin_menu_kb())
        return
    buttons = [
        [InlineKeyboardButton(text=f"❌ {p['name']} ({p['price']} руб.)", callback_data=f"remove_{i}")]
        for i, p in enumerate(products)
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text(
        "Выберите товар для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("remove_"))
async def cb_remove_product(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    idx = int(callback.data.split("_")[1])
    products = load_products()
    if idx >= len(products):
        await callback.answer("❌ Товар не найден.")
        return
    removed = products.pop(idx)
    save_products(products)
    await callback.answer(f"✅ «{removed['name']}» удалён из каталога!")
    await callback.message.edit_text("👨‍💼 Панель администратора:", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery):
    await callback.message.edit_text("👨‍💼 Панель администратора:", reply_markup=admin_menu_kb())

# ========================
# 🚀 ЗАПУСК
# ========================
async def main():
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
