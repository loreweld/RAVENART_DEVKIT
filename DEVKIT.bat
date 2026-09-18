@echo off
chcp 65001 >nul
title DEVKIT - AI Gelistirme Destek Sistemi
cd /d "%~dp0"

set "PYCMD="
where py >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
    echo [HATA] Python bulunamadi. Lutfen Python 3.8+ yukleyin.
    pause
    exit /b 1
)

%PYCMD% gui.py

if errorlevel 1 (
    echo.
    echo [HATA] GUI baslatilamadi. Konsol modunu deneyin: %PYCMD% devkit.py help
    pause
)
