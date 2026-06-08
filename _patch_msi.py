# -*- coding: utf-8 -*-
"""
MSI 后处理脚本 — 中文化
在 cx_Freeze bdist_msi 生成 MSI 后运行，覆写已有表数据。
使用 msilib Modify API（非原始 SQL）确保兼容性。
"""
import msilib
import sys
import os


def _update_field(db, table, primary_keys, column, new_value):
    """使用 msilib Modify API 更新表中某行的某个字段。
    
    primary_keys: list of (col_name, key_value) pairs
    """
    cols = [pk[0] for pk in primary_keys]
    vals = [pk[1] for pk in primary_keys]
    
    where_clause = ' AND '.join(f"`{c}` = '{v.replace(chr(39), chr(39)+chr(39))}'" for c, v in primary_keys)
    sql = f"SELECT * FROM `{table}` WHERE {where_clause}"
    view = db.OpenView(sql)
    # Execute with a parameter record
    rec_params = msilib.CreateRecord(len(cols))
    for i, v in enumerate(vals):
        rec_params.SetString(i + 1, v)
    view.Execute(rec_params)
    
    rec = view.Fetch()
    if rec is None:
        view.Close()
        return False
    
    # Find the column index
    # We need to figure out which column number this is.
    # Let's get column names from the view.
    col_info = view.GetColumnInfo(msilib.MSICOLINFO_NAMES)
    rec_cols = msilib.CreateRecord(col_info.GetFieldCount())
    # Actually, we can just use the column name to find the index
    # The SELECT * returns columns in schema order.
    # For Control table: Dialog_, Control, Type, X, Y, Width, Height, Attributes, Property, Text, Control_Next, Help
    # For Property table: Property, Value
    
    # Simpler approach: use specific SELECT to get just the targeted column
    view.Close()
    
    # Re-open with a targeted SELECT
    sql2 = f"SELECT `{column}` FROM `{table}` WHERE {where_clause}"
    view2 = db.OpenView(sql2)
    view2.Execute(rec_params)
    
    rec2 = view2.Fetch()
    if rec2 is None:
        view2.Close()
        return False
    
    rec2.SetString(1, new_value)
    view2.Modify(msilib.MSIMODIFY_REPLACE, rec2)
    view2.Close()
    return True


def _update_property(db, prop_name, new_value):
    """更新 Property 表"""
    view = db.OpenView(f"SELECT Value FROM Property WHERE Property = '{prop_name}'")
    view.Execute(None)
    rec = view.Fetch()
    if rec:
        rec.SetString(1, new_value)
        view.Modify(msilib.MSIMODIFY_REPLACE, rec)
        print(f'  Property.{prop_name} := {new_value}')
    view.Close()


def _update_control_text(db, dialog, control, new_text):
    """更新 Control 表的 Text 字段"""
    sql = f"SELECT Text FROM Control WHERE Dialog_ = '{dialog}' AND Control = '{control}'"
    view = db.OpenView(sql)
    view.Execute(None)
    rec = view.Fetch()
    if rec:
        rec.SetString(1, new_text)
        view.Modify(msilib.MSIMODIFY_REPLACE, rec)
    view.Close()


def patch_msi(msi_path):
    db = msilib.OpenDatabase(msi_path, msilib.MSIDBOPEN_DIRECT)

    # 1. ProductLanguage: 1033 → 2052
    _update_property(db, 'ProductLanguage', '2052')

    # 2. 覆写 Control 文本
    control_overrides = {
        # ExitDialog
        ('ExitDialog', 'Description'):    '点击"完成"按钮退出安装程序。',
        ('ExitDialog', 'Title'):          '{\\VerdanaBold10}完成 [ProductName] 安装向导',
        ('ExitDialog', 'LaunchOnFinish'): '安装完成后运行程序(&L)',

        # PrepareDlg
        ('PrepareDlg', 'Description'):    '请稍候，安装程序正在准备引导您完成安装。',

        # SelectDirectoryDlg
        ('SelectDirectoryDlg', 'Description'): '请选择 [ProductName] 的安装文件夹。',
        ('SelectDirectoryDlg', 'Title'):        '{\\DlgFontBold8}选择安装位置',

        # ProgressDlg
        ('ProgressDlg', 'Title'):         '{\\DlgFontBold8}[Progress1] [ProductName]',
        ('ProgressDlg', 'Text'):          '请稍候，安装程序正在[Progress2] [ProductName]。',
        ('ProgressDlg', 'ActionText'):    '准备中...',
        ('ProgressDlg', 'StatusLabel'):   '状态:',

        # CancelDlg
        ('CancelDlg', 'Text'):            '确定要取消 [ProductName] 安装吗？',

        # FilesInUse
        ('FilesInUse', 'Description'):    '部分需要更新的文件正在使用中。',
        ('FilesInUse', 'Text'):           '以下应用程序正在使用需要由此安装程序更新的文件。建议关闭这些应用程序。',
        ('FilesInUse', 'Title'):          '{\\DlgFontBold8}文件正在使用',

        # MaintenanceTypeDlg
        ('MaintenanceTypeDlg', 'Title'):     '{\\DlgFontBold8}更改、修复或删除安装',
        ('MaintenanceTypeDlg', 'BodyText'):  '选择是要修复还是删除 [ProductName]。',

        # WaitForCostingDlg
        ('WaitForCostingDlg', 'Text'):    '请稍候，安装程序正在计算磁盘空间需求...',

        # UserExit
        ('UserExit', 'Title'):            '{\\VerdanaBold10}[ProductName] 安装已中断',
        ('UserExit', 'Description1'):     '[ProductName] 安装已中断。系统未被修改。要稍后安装此程序，请重新运行安装程序。',
        ('UserExit', 'Description2'):     '点击"完成"按钮退出安装程序。',

        # FatalError
        ('FatalError', 'Title'):          '{\\VerdanaBold10}[ProductName] 安装程序提前结束',
        ('FatalError', 'Description1'):   '[ProductName] 安装因错误提前结束。系统未被修改。',
        ('FatalError', 'Description2'):   '点击"完成"按钮退出安装程序。',
    }

    for (dialog, control), text in control_overrides.items():
        _update_control_text(db, dialog, control, text)

    # 3. 补充 UIText
    existing_keys = set()
    view = db.OpenView("SELECT `Key` FROM UIText")
    view.Execute(None)
    while True:
        rec = view.Fetch()
        if not rec:
            break
        existing_keys.add(rec.GetString(1))
    view.Close()

    extra_uitext = {
        'AbsentPath':           '文件夹 [2] 不存在或无法访问。是否继续？',
        'SelParentCostNegNeg':  '由于磁盘空间不足，无法将此功能安装到所选位置。请释放额外的磁盘空间或选择其他位置。',
        'VolumeCostAvailable':  '可用磁盘空间',
        'VolumeCostDifference': '所需磁盘空间',
        'VolumeCostRequired':   '所需磁盘空间',
        'VolumeCostSize':       '磁盘空间',
        'VolumeCostVolume':     '磁盘',
    }

    for key, text in extra_uitext.items():
        if key not in existing_keys:
            v = db.OpenView("SELECT * FROM `UIText`")
            rec = msilib.CreateRecord(2)
            rec.SetString(1, key)
            rec.SetString(2, text)
            v.Modify(msilib.MSIMODIFY_INSERT, rec)
            v.Close()

    db.Commit()
    db.Close()
    print(f'  OK MSI patch applied: {msi_path}')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'dist',
            'StickyNote-1.5.5-win64.msi'
        )
    if os.path.exists(target):
        patch_msi(target)
    else:
        print(f'  ! MSI not found: {target}')
        sys.exit(1)
