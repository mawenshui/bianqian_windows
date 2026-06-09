# -*- coding: utf-8 -*-
"""
MSI 后处理：
1. 补入 DesktopFolder 到 Directory 表（修复 Error 2727）
2. 中文化界面文本 + ProductLanguage
"""
import msilib
import sys

MSI_PATH = sys.argv[1] if len(sys.argv) > 1 else r'dist\StickyNote-1.6.1-win64.msi'

# ── 中文覆写表：{(Dialog_, Control): 新文本} ──
OVERRIDES = {
    # ExitDialog
    ('ExitDialog', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}桌面便签 安装完成',
    ('ExitDialog', 'Description'):              '桌面便签安装程序已成功完成。\r\n点击"完成"退出安装向导。',
    # PrepareDlg
    ('PrepareDlg', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}准备安装',
    ('PrepareDlg', 'Description'):              '安装程序已准备就绪，即将开始安装桌面便签。\r\n点击"安装"继续。',
    # SelectDirectoryDlg
    ('SelectDirectoryDlg', 'Title'):            '{\\VSI_MS_Sans_Serif13.0_0_0}选择安装位置',
    ('SelectDirectoryDlg', 'Description'):      '请选择桌面便签的安装文件夹。',
    # ProgressDlg
    ('ProgressDlg', 'Title'):                   '{\\VSI_MS_Sans_Serif13.0_0_0}正在安装',
    ('ProgressDlg', 'Text'):                    '安装程序正在安装桌面便签，请稍候...',
    ('ProgressDlg', 'Description'):             '请稍候，安装程序正在安装桌面便签。这可能需要几分钟时间。',
    # CancelDlg
    ('CancelDlg', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}取消安装',
    ('CancelDlg', 'Text'):                     '是否确定取消桌面便签的安装？',
    # FilesInUse
    ('FilesInUse', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}文件正在使用',
    ('FilesInUse', 'Description'):              '以下应用程序正在使用需要更新的文件。请关闭这些应用程序，然后点击"重试"继续。',
    # MaintenanceTypeDlg
    ('MaintenanceTypeDlg', 'Title'):            '{\\VSI_MS_Sans_Serif13.0_0_0}维护桌面便签',
    ('MaintenanceTypeDlg', 'Description'):      '选择要执行的操作。',
    # WaitForCostingDlg
    ('WaitForCostingDlg', 'Title'):             '{\\VSI_MS_Sans_Serif13.0_0_0}正在计算空间需求',
    ('WaitForCostingDlg', 'Description'):       '请稍候，安装程序正在计算磁盘空间需求。',
    # UserExit
    ('UserExit', 'Title'):                      '{\\VSI_MS_Sans_Serif13.0_0_0}安装已取消',
    ('UserExit', 'Description'):                '桌面便签安装程序已取消。\r\n点击"完成"退出安装向导。',
    # FatalError
    ('FatalError', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}安装失败',
    ('FatalError', 'Description'):              '桌面便签安装程序未能完成安装。\r\n点击"完成"退出安装向导。',
    # ResumeDlg / MaintenanceWelcomeDlg
    ('ResumeDlg', 'Title'):                     '{\\VSI_MS_Sans_Serif13.0_0_0}恢复安装',
    ('ResumeDlg', 'Description'):               '安装程序将恢复桌面便签的安装。',
    ('MaintenanceWelcomeDlg', 'Title'):         '{\\VSI_MS_Sans_Serif13.0_0_0}欢迎使用桌面便签维护程序',
    ('MaintenanceWelcomeDlg', 'Description'):   '选择要执行的操作：修复或删除桌面便签。',
    # WelcomeDlg
    ('WelcomeDlg', 'Title'):                    '{\\VSI_MS_Sans_Serif13.0_0_0}欢迎使用桌面便签安装向导',
    ('WelcomeDlg', 'Description'):              '此向导将引导您完成桌面便签的安装。\r\n\r\n建议在继续安装之前关闭所有其他应用程序。',
    # VerifyReadyDlg
    ('VerifyReadyDlg', 'Title'):                '{\\VSI_MS_Sans_Serif13.0_0_0}准备安装桌面便签',
    ('VerifyReadyDlg', 'Description'):          '安装程序已准备就绪。点击"安装"开始安装。',
}

# ── Property 覆写 ──
PROPERTY_OVERRIDES = {
    'ProductLanguage': '2052',
    # Manufacturer / ProductName 等也可以在这里覆写
    # 'Manufacturer': 'MaWenshui',
}


def _update_property(db, prop_name, new_value):
    """更新 Property 表"""
    view = db.OpenView(f"SELECT Value FROM Property WHERE Property = '{prop_name}'")
    view.Execute(None)
    rec = view.Fetch()
    if rec:
        rec.SetString(1, new_value)
        view.Modify(msilib.MSIMODIFY_REPLACE, rec)
        view.Close()
        print(f'  [OK] Property.{prop_name} = {new_value}')
    else:
        view.Close()
        # 插入新行
        view2 = db.OpenView("INSERT INTO Property (Property, Value) VALUES (?, ?)")
        rec2 = msilib.CreateRecord(2)
        rec2.SetString(1, prop_name)
        rec2.SetString(2, new_value)
        view2.Execute(rec2)
        view2.Close()
        print(f'  [OK] Property.{prop_name} = {new_value} (inserted)')


def _update_control_text(db, dialog, control, new_text):
    """更新 Control 表的 Text 列"""
    sql = f"SELECT Text FROM Control WHERE Dialog_ = '{dialog}' AND Control = '{control}'"
    view = db.OpenView(sql)
    view.Execute(None)
    rec = view.Fetch()
    if rec:
        rec.SetString(1, new_text)
        view.Modify(msilib.MSIMODIFY_REPLACE, rec)
        view.Close()
        print(f'  [OK] {dialog}.{control}')
    else:
        view.Close()
        print(f'  [SKIP] {dialog}.{control} (not found)')


def _ensure_desktop_folder(db):
    """确保 DesktopFolder 存在于 Directory 表中（修复 MSI Error 2727）"""
    view = db.OpenView("SELECT Directory FROM Directory WHERE Directory = 'DesktopFolder'")
    view.Execute(None)
    rec = view.Fetch()
    view.Close()
    if rec:
        print('  [OK] DesktopFolder already exists in Directory table')
        return
    # 插入 DesktopFolder 行：父目录为 TARGETDIR，DefaultDir 使用标准名称
    view = db.OpenView(
        "INSERT INTO Directory (Directory, Directory_Parent, DefaultDir) "
        "VALUES ('DesktopFolder', 'TARGETDIR', 'DESKTOP|Desktop')"
    )
    view.Execute(None)
    view.Close()
    print('  [OK] DesktopFolder inserted into Directory table')


def main():
    print(f'Patching: {MSI_PATH}')
    db = msilib.OpenDatabase(MSI_PATH, msilib.MSIDBOPEN_DIRECT)

    # 0. 补入 DesktopFolder（修复 Error 2727）
    print('\n--- Directory table fix ---')
    _ensure_desktop_folder(db)

    # 1. 覆写 Property
    print('\n--- Property overrides ---')
    for prop_name, new_value in PROPERTY_OVERRIDES.items():
        _update_property(db, prop_name, new_value)

    # 2. 覆写 Control 文本
    print('\n--- Control text overrides ---')
    for (dialog, control), new_text in OVERRIDES.items():
        _update_control_text(db, dialog, control, new_text)

    db.Commit()
    db.Close()
    print('\n✅ MSI patching complete.')


if __name__ == '__main__':
    main()
