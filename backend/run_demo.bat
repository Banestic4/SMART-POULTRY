@echo off
REM ===== SMART-Poultry demo launcher (edit the lines marked EDIT, save, double-click) =====
set SP_SMS_API_KEY=tlv_zJAH7VF6MJxxOizmvOz7dHWZBd7F95ftOBq4ovM60t8
REM EDIT: the base URL shown on your Termii dashboard / API docs page (starts with https://)
set SP_SMS_BASE_URL=https://v4.api.termii.com/
set SP_SMS_SENDER_ID=smart-poultry
set SP_SMS_RECIPIENTS=2348125012099
set SP_SMS_CHANNEL=generic
set SP_ADMIN_PASSWORD=Defence@2026
python app_ui.py
pause
