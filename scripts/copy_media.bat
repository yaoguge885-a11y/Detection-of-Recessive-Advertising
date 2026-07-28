@echo off
chcp 65001 >nul
echo ============================================================
echo Media 文件合并 - 使用 robocopy
echo ============================================================

set "BASE=d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs"
set "DEST=%BASE%\merged_20260728\media"

echo.
echo [1/4] wechat_20260728_100314 ...
robocopy "%BASE%\wechat_20260728_100314\media" "%DEST%" /E /XC /XN /XO /NJH /NJS /NDL /NP

echo.
echo [2/4] wechat_20260728_012504 ...
robocopy "%BASE%\wechat_20260728_012504\media" "%DEST%" /E /XC /XN /XO /NJH /NJS /NDL /NP

echo.
echo [3/4] bilibili_20260728_130630 ...
robocopy "%BASE%\bilibili_20260728_130630\media" "%DEST%" /E /XC /XN /XO /NJH /NJS /NDL /NP

echo.
echo [4/4] bilibili_20260727_162733 ...
robocopy "%BASE%\bilibili_20260727_162733\media" "%DEST%" /E /XC /XN /XO /NJH /NJS /NDL /NP

echo.
echo ============================================================
echo Media 合并完成!
echo ============================================================
