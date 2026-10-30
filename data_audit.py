#!/usr/bin/env python3
"""
FER3ON Phase 0.5: Data Audit
فحص جودة البيانات المجمعة قبل ربط resolvers
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent


def _ledger_path(setting_name, fallback):
    try:
        from core import settings
        return ROOT / str(getattr(settings, setting_name, fallback))
    except Exception:
        return ROOT / fallback

def audit_rejected_shadow():
    """فحص REJECTED_SHADOW للتحقق من تلوث البيانات"""
    rejected_file = _ledger_path('SHADOW_COUNTERFACTUAL_LOG_PATH',
                                 'data/analytics/shadow_counterfactual/rejected_shadow_2026-09-01-clean.jsonl')
    
    if not rejected_file.exists():
        print('❌ ملف REJECTED_SHADOW غير موجود')
        return
    
    with open(rejected_file, 'r') as f:
        lines = f.readlines()
    
    print(f'📊 REJECTED_SHADOW: {len(lines)} سجل')
    
    # عينة الـ 50 الأخيرة
    sample = []
    for line in lines[-50:]:
        try:
            sample.append(json.loads(line))
        except Exception as e:
            print(f'  ⚠️ خطأ parsing: {e}')
    
    print(f'✓ عينة صالحة: {len(sample)}/50')
    
    # إحصائيات
    statuses = defaultdict(int)
    reject_reasons = defaultdict(int)
    signals = defaultdict(int)
    invalid_records = 0
    gate_stages = defaultdict(int)
    
    for item in sample:
        status = item.get('status', 'UNKNOWN')
        statuses[status] += 1
        reason = item.get('reject_reason', 'NONE')
        reject_reasons[reason] += 1
        signal = item.get('direction', item.get('signal', 'UNKNOWN'))
        signals[signal] += 1
        gate_stages[item.get('gate_stage', item.get('gate', 'UNKNOWN'))] += 1
        if float(item.get('entry_price', 0) or 0) <= 0:
            invalid_records += 1
    
    print(f'\n  الحالات: {dict(statuses)}')
    print(f'  أسباب الرفض: {dict(reject_reasons)}')
    print(f'  مراحل البوابة: {dict(gate_stages)}')
    print(f'  سجلات غير قابلة للحل (entry_price<=0): {invalid_records}')
    print(f'  الإشارات: {dict(signals)}')
    
    # عينة مثال
    if sample:
        for i, ex in enumerate(sample[:3]):
            print(f'\n  مثال #{i+1}:')
            print(f'    Signal: {ex.get("direction", ex.get("signal"))}')
            print(f'    Reason: {ex.get("reject_reason")}')
            print(f'    Quality: {ex.get("quality_score")}')
            print(f'    Outcome: {ex.get("outcome", ex.get("status"))}')
            print(f'    Timestamp: {ex.get("signal_time", ex.get("timestamp"))}')

def audit_decision_ledger():
    """فحص Decision Ledger للتحقق من الانحراف SELL/BUY"""
    ledger_file = _ledger_path('DECISION_LEDGER_LOG_PATH',
                               'data/analytics/decision_ledger/decisions.jsonl')
    
    if not ledger_file.exists():
        print('\n❌ ملف DECISION_LEDGER غير موجود')
        return
    
    with open(ledger_file, 'r') as f:
        ledger_lines = f.readlines()
    
    print(f'\n📊 DECISION_LEDGER: {len(ledger_lines)} سجل')
    
    # إحصائيات الاتجاه
    buy_count = 0
    sell_count = 0
    buy_approved = 0
    sell_approved = 0
    
    for line in ledger_lines:
        try:
            item = json.loads(line)
            signal = str(item.get('direction', item.get('signal', ''))).upper()
            verdict = str(item.get('decision', item.get('verdict', ''))).upper()
            
            if signal == 'BUY':
                buy_count += 1
                if 'APPROVE' in verdict or verdict == 'EXECUTE_FULL':
                    buy_approved += 1
            elif signal == 'SELL':
                sell_count += 1
                if 'APPROVE' in verdict or verdict == 'EXECUTE_FULL':
                    sell_approved += 1
        except:
            pass
    
    total = buy_count + sell_count
    print(f'  BUY: {buy_count} ({100*buy_count/total:.1f}%) | SELL: {sell_count} ({100*sell_count/total:.1f}%)')
    print(f'  النسبة SELL/BUY: {sell_count/max(buy_count,1):.2f}:1')
    print(f'  BUY المقبولة: {buy_approved}/{buy_count} ({100*buy_approved/max(buy_count,1):.1f}%)')
    print(f'  SELL المقبولة: {sell_approved}/{sell_count} ({100*sell_approved/max(sell_count,1):.1f}%)')

def audit_exit_actions():
    """فحص EXIT_ACTIONS"""
    exit_file = _ledger_path('PHASE3_EXIT_MANAGER_LOG_PATH',
                             'data/analytics/exit_manager/exit_actions.jsonl')
    
    if not exit_file.exists():
        print('\n❌ EXIT_ACTIONS ملف معدوم')
        return
    
    with open(exit_file, 'r') as f:
        exit_lines = f.readlines()
    
    print(f'\n📊 EXIT_ACTIONS: {len(exit_lines)} سجل')

def audit_entry_plans():
    """فحص ENTRY_PLANS"""
    entry_file = _ledger_path('PHASE2_ENTRY_CONTROLLER_LOG_PATH',
                              'data/analytics/entry_controller/entry_plans.jsonl')
    
    if not entry_file.exists():
        print('\n❌ ENTRY_PLANS ملف معدوم')
        return
    
    with open(entry_file, 'r') as f:
        entry_lines = f.readlines()
    
    print(f'\n📊 ENTRY_PLANS: {len(entry_lines)} سجل')
    
    # إحصائيات الحالة (عينة آخر 100)
    states = defaultdict(int)
    for line in entry_lines[-100:]:
        try:
            item = json.loads(line)
            state = item.get('status', item.get('state', 'UNKNOWN'))
            states[state] += 1
        except:
            pass
    
    print(f'  حالات (عينة آخر 100): {dict(states)}')

def main():
    print('=' * 70)
    print('🔍 DATA AUDIT: فحص جودة البيانات المجمعة')
    print('=' * 70)
    
    audit_rejected_shadow()
    audit_decision_ledger()
    audit_exit_actions()
    audit_entry_plans()
    
    print('\n' + '=' * 70)
    print('✅ انتهى الفحص')
    print('=' * 70)

if __name__ == '__main__':
    main()
