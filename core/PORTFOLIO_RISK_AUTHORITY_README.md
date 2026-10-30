# Portfolio Risk Authority — FER3ON V3.5

## القاعدة الذهبية

الـ Authority السابق (`core/fer3on_decision_authority.py`) كان يقوم بدورين:
1. **Direction Authority** — يحدد BUY/SELL
2. **Risk Authority** — يدير المخاطر

هذا تسبب في **اختناق الفرص** ورفض صفقات دون سبب للمخاطرة.

## Authority الجديد (`core/portfolio_risk_authority.py`)

تحويله إلى **Portfolio Risk Authority** فقط:

| مسموح | ممنوع |
|---|---|
| Risk Control | رفض cross-strategy direction conflict |
| Lot Allocation | قرار الاتجاه BUY/SELL |
| Exposure Management | الحكم بين استراتيجيتين |
| Portfolio Limits | |
| Daily Loss Protection | |
| Drawdown Protection | |

## Architecture

```
Strategies
    ↓
Independent Evaluation
    ↓
Unified Decision
    ↓
Portfolio Risk Authority        (v3.5 - هذا الملف)
    ↓
Execution
```

## الاختلاف بين الاستراتيجيات → Portfolio Diversification لا Conflict

```
DAILY = BUY
SMC = SELL

هذا ليس Conflict.
هذا Portfolio Diversification.
```

Authority لا يحق له رفض صفقة لمجرد أن استراتيجية أخرى تختار الاتجاه المعاكس.

## Phase-1 Migration

`fer3on_decision_authority.py` لا يزال موجوداً كـ **legacy wrapper** لـ
`- نفس واجهة `decide_trade(...)`.

لكن منذ V3.5، يعتمد الـ runtime على `core/portfolio_risk_authority.py`
لجميع قرارات الرفض / Lot / Exposure. الـ legacy Authority لم يعد
يستخدم "Direction Authority" — إنه الآن thin wrapper.
