from core.mt5_compat import mt5, MT5_AVAILABLE


def check_demo_account():

    account_info = mt5.account_info()

    if account_info is None:

        print("❌ Failed To Read Account Info")
        return False

    # فحص نوع الحساب
    trade_mode = account_info.trade_mode

    # 0 = Demo
    # غير ذلك = Live غالبًا
    if trade_mode != 0:

        print("🚫 LIVE ACCOUNT DETECTED")
        print("🛑 BOT STOPPED FOR SAFETY")

        return False

    print("✅ Demo Account Confirmed")

    return True