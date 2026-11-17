"""Install a user Startup entry, preserve prior source files, update display name."""
import datetime,shutil,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup=ROOT.parent/'backups'/('viona-network-'+stamp);backup.mkdir(parents=True)
for name in ('ui.html','index.html','mobile.html','assistant_tools.py'):
    p=ROOT/name
    shutil.copy2(p,backup/name)
    text=p.read_text(encoding='utf-8')
    if name=='assistant_tools.py':text=text.replace('한국어로 대화하는 NovaBrain입니다','한국어로 대화하는 VIONA입니다').replace('You are NovaBrain','You are VIONA')
    else:text=text.replace('NovaBrain','VIONA')
    p.write_text(text,encoding='utf-8')
startup=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/VIONA_Autostart.vbs'
if startup.exists():shutil.copy2(startup,backup/startup.name)
python=ROOT/'.venv/Scripts/pythonw.exe'
command=f'"{python}" "{ROOT / "autostart_viona.py"}" --open-browser'
vbs='CreateObject("WScript.Shell").Run "'+command.replace('"','""')+'", 0, False\r\n'
startup.write_text(vbs,encoding='utf-16')
print('Startup entry:',startup)
print('Source backup:',backup)
