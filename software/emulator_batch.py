import os
import sys
import json
import time
import subprocess
import shutil
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from emulator_core import parameters_known
from emulator_core import set_tty
from emulator_core import get_version_core
from determine_basal import get_version_determine_basal

# Detect if running in Termux environment
use_termux = os.environ.get('PREFIX', '').endswith('/data/data/com.termux/files/usr')

if sys.platform == "linux":
    bashrc = os.path.expanduser("~/.bashrc")
    line = "export PYTHONUTF8=1\n"

    with open(bashrc, "a") as f:
        f.write("\n" + line)

    print("PYTHONUTF8=1 added to ~/.bashrc")

DEBUG = True

if DEBUG:
    try:
        import debugpy
    except Exception as e:
        print(f"Debugpy is not installed!\n Install it with this command:\n pip install debugpy\n {e}")
        """"
            With Debian 13+
            source venv/bin/activate
            python -m pip install debugpy
        """
    HOST = "0.0.0.0"
    PORT = 5678
    debugpy.listen((HOST, PORT))
    print("Waiting for VS Code debugger (10s)...")

    for _ in range(100):  # 100 × 0.1s = 10s
        if debugpy.is_client_connected():
            print("Debugger attached")
            break
        time.sleep(0.1)
    else:
        print("No debugger attached, continuing normally")
    debugpy.wait_for_client()
    print("Debugger attached")

class DummyDroid:
    def dialogCreateAlert(self, title):
        print(f"\n=== {title} ===")

    def dialogSetMultiChoiceItems(self, items, default):
        print("Choices (multi):")
        for i, it in enumerate(items):
            mark = "*" if i in default else " "
            print(f" [{mark}] {i}: {it}")

    def dialogSetSingleChoiceItems(self, items, default):
        print("Choices:")
        for i, it in enumerate(items):
            mark = "*" if i == default else " "
            print(f" [{mark}] {i}: {it}")

    def dialogSetPositiveButtonText(self, text): pass
    def dialogSetNegativeButtonText(self, text): pass
    def dialogSetNeutralButtonText(self, text): pass
    def dialogShow(self): pass

    def dialogGetResponse(self):
        return type("R", (), {"result": {"which": "positive"}})()

    def dialogGetSelectedItems(self):
        return type("R", (), {"result": []})()

    def dialogDismiss(self): pass

    def ttsSpeak(self, text):
        print(f"[TTS] {text}")

class DummyDroid:
    def toast(self, msg):
        print(f"[ANDROID TOAST] {msg}")

    def dialogCreateAlert(self, *args, **kwargs):
        print("[ANDROID DIALOG]", args)

    def dialogShow(self):
        pass

try:
    import androidhelper
    droid = androidhelper.Android()
    ANDROID_UI = True
except ImportError:
    droid = DummyDroid()
    ANDROID_UI = False

def get_display_timezone():
    tz = os.environ.get("TZ") # Termux
    if tz:
        return ZoneInfo(tz)
    return datetime.now().astimezone().tzinfo

def speak(text):
    try:
        if IsAndroid and use_termux:
            subprocess.run(
                ["termux-tts-speak", text],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif droid:
            droid.ttsSpeak(text)
        else:
            raise RuntimeError("No TTS available")
    except Exception as e:
        print("[SAY]", text)
        print(f"[speak-fallback] {e}")

def get_version_batch(echo_msg):
    echo_msg['emulator_batch.py'] = '2025-12-28 16:30'      # pause in announcing carbs required
    #cho_msg['emulator_batch.py'] = '2025-05-27 14:00'      # fit table output for Qpython+; adapt VDF home
    #cho_msg['emulator_batch.py'] = '2025-04-09 03:18'      # Logdir geändert
    return echo_msg

def mydialog(title, buttons=None, items=None, multi=False, default_pick=None):
    """
    buttons: list[str]        e.g. ["OK", "Cancel", "Extra"]
    items:   list[str] | None
    multi:   bool             multi-choice dialog
    default_pick: list[int]   default selected items
    """

    buttons = buttons or []
    items = items or []
    default_pick = default_pick or []

    # ----------------------------
    # Android UI pad
    # ----------------------------
    if droid is not None and hasattr(droid, "dialogCreateAlert"):
        try:
            droid.dialogCreateAlert(title)

            if items:
                if multi:
                    droid.dialogSetMultiChoiceItems(items, default_pick)
                else:
                    droid.dialogSetSingleChoiceItems(items, default_pick[0] if default_pick else 0)

            if len(buttons) >= 1:
                droid.dialogSetPositiveButtonText(buttons[0])
            if len(buttons) >= 2:
                droid.dialogSetNegativeButtonText(buttons[1])
            if len(buttons) >= 3:
                droid.dialogSetNeutralButtonText(buttons[2])

            droid.dialogShow()

            res_btn = droid.dialogGetResponse().result or {}
            res_sel = droid.dialogGetSelectedItems().result or []

            pressed = {
                "positive": 0,
                "negative": 1,
                "neutral": 2
            }.get(res_btn.get("which"), -1)

            droid.dialogDismiss()  # Android 12+ vereist

            return pressed, res_sel

        except Exception as e:
            print("[ANDROID UI ERROR]", e)

        # ----------------------------
        # Fallback: CLI / Termux
        # ----------------------------
        print("\n" + title)
        print("-" * len(title))

        for i, item in enumerate(items):
            mark = "*" if i in default_pick else " "
            print(f"[{mark}] {i}: {item}")

        if items:
            if multi:
                inp = input("Select items (comma separated, empty = default)): ").strip()
                if inp:
                    try:
                        picks = [int(x) for x in inp.split(",")]
                    except ValueError:
                        picks = default_pick
                else:
                    picks = default_pick
            else:
                inp = input("Select item number (empty = default):").strip()
                picks = [int(inp)] if inp.isdigit() else default_pick
        else:
            picks = []

        if buttons:
            print("\nButtons:")
            for i, b in enumerate(buttons):
                print(f"{i}: {b}")
            inp = input("Select button (empty = 0):").strip()
            pressed = int(inp) if inp.isdigit() else 0
        else:
            pressed = -1

        return pressed, picks

# ======================================================
# CLI / TERMUX (no Android UI)
# ======================================================
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    if items:
        for i, it in enumerate(items):
            mark = "*" if i in default_pick else " "
            print(f" [{mark}] {i}: {it}")

    print(f"Buttons : {buttons}")
    print(f"Defaults: {default_pick}")
    print("(CLI mode → defaults are used automatically)")

    # behavioral equivalent:
    pressed_button = 0 if buttons else -1
    selected_items = default_pick if multi else [default_pick[0]]

    return pressed_button, selected_items


def dialog1(Title, btns, default_btn, items, default_item):
    while True:
        os.system('clear')
        print('List of '+Title+':')
        for item in items:
            if item == default_item:
                trail = ' (default)'
            else:
                trail = ''
            print(item + '-' + items[item], trail)
        #print('default:', items[default_item])
        print('\nWhen done, list of actions:')
        for btn in btns:
            if btn == default_btn:
                trail = ' (default)'
            else:
                trail = ''
            print(btn +'-' + btns[btn], trail)
        #print('default:', btns[default_btn] )
        my_opt = input('Enter key for option or action: ')
        if ord((my_opt+default_btn)[0])>96:      my_opt = chr(ord(my_opt)-32)
        if my_opt in items:
            return default_btn, my_opt, False
        elif my_opt in btns:
            return my_opt, default_item, True
        elif my_opt == '':
            return default_btn, default_item, True
        else:
            #print(binascii.b2a_uu(7))          # bell() ?
            pass


def waitNextLoop(loopInterval, arg, varName):
    DISPLAY_TZ = datetime.now().astimezone().tzinfo

    # ---- UTC calculation ----
    if arg == 'Z':
        waitSec = loopInterval + 5
    else:
        loophh = int(arg[0:2]) -100 # handle leading '0'
        loopmm = int(arg[3:5]) -100 # handle leading '0'
        loopss = int(arg[6:8]) -100 # handle leading '0'

        LoopSec = loophh * 3600 + loopmm * 60 + loopss

        now_utc = datetime.now(timezone.utc)
        nowSec = now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second

        if nowSec < LoopSec:
            delta = LoopSec - nowSec
        else:
            delta = (24 * 3600 - nowSec) + LoopSec

        waitSec = round(delta + loopInterval + 5, 0)
        if waitSec < 10:
            waitSec = 65

    # ---- Display in local time ----
    then_utc = datetime.now(timezone.utc) + timedelta(seconds=waitSec - 5)
    then_local = then_utc.astimezone(DISPLAY_TZ)

    print(
        f' Waiting {int(waitSec)} sec for next loop at '
        f'{then_local.strftime("%H:%M:%S %Z")};   Variant "{varName}"',
        end='\r'
    )

    return waitSec

def alarmHours(titel):
    ###########################################################################
    #   the alarm hours dialog
    ###########################################################################
    btns = ["Next", "Exit"]
    items = ["00","01","02","03","04","05","06","07","08","09","10","11","12","13","14","15","16","17","18","19","20","21","22","23"]
    pick  = [                             7,  8,  9,  10,  11,  12,  13,  14,  15,  16,  17,  18,  19,  20,  21,  22      ]
    while True:
        default_pick = pick
        pressed_button, selected_items_indexes = mydialog("Pick alarm hours for\n"+titel, btns, items, True, default_pick)
        pick = selected_items_indexes
        if   pressed_button ==-1:           sys.exit()                      # external BREAK
        #lif selected_items_indexes == []:  sys.exit()                      # all declined
        elif pressed_button == 0:           break                           # NEXT
        elif pressed_button == 1:           sys.exit()                      # EXIT
    return pick

def sync_android_logs(src: Path, dst: Path):
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.glob("*"):
            if f.is_file():
                shutil.copy2(f, dst / f.name)
    except PermissionError:
        # Android freezes → silently fails, mirror remains old
        pass

###############################################
###    start of main                        ###
###############################################

#how_to_print = 'GUI'
how_to_print = 'print'
#et_tty(runframe, lfd,  how_to_print)            # export print settings to main routine
set_tty(0,        0,    how_to_print)            # export print settings to main routine

global echo_msg
droid = None  # Initialize droid variable for type checking

# try whether we are on Android:
IsAndroid = False
# ANDROID_SOURCE 
vdf_dir = Path('/storage/emulated/0/Documents/aapsLogs')
TERMUX_MIRROR  = Path.home() / "external-1/Documenten/aapsLogs"
fn = None
test_file = 'AndroidAPS.log'


                    # AAPS version: 3.3+                        or AAPS 2.8.2                                                        or AAPS 3.0+
ANDROID_SOURCE = {'/storage/emulated/0/Documents/aapsLogs', '/storage/emulated/0/Android/data/info.nightscout.androidaps/files/', '/storage/emulated/0/AAPS/logs/info.nightscout.androidaps/'}

for ext in (ANDROID_SOURCE):
        if Path(ext).is_dir():
            IsAndroid = True
            vdf_dir = Path(ext)
            fn = vdf_dir / test_file
            print(f'Found: {Path(ext)}', fn)

if IsAndroid:
    
    # try sync first (may fail)
    # if vdf_dir.exists():
    #     sync_android_logs(vdf_dir, TERMUX_MIRROR)

    # # werk ALTIJD met mirror
    # if TERMUX_MIRROR.is_dir():
    #     vdf_dir = TERMUX_MIRROR
    #     fn = vdf_dir / test_file
    #     print("Using Android mirror:", fn)
    # else:
    #     raise RuntimeError("No accessible AAPS log folder found")
    
    speed = '150'
    pitch = '33'
    my_decimal = ','
    #ClearScreenCommand = 'clear'                                           # done in --core.py
    #fn = inh[0]
    myseek  = fn

    ###########################################################################
    #   the language dialog
    ###########################################################################
    btns  = {"N":"Next", "T":"Test", "E":"Exit"}
    items = {"1":"Dieses Smartphon spricht Deutsch", "2":"This smartphone speaks English"}
    #global language
    language = {"1":"de+f18", "2":"en+f18"}
    pick = "1"
    pressed_button = "N"
    while True:                                                             # how the lady speaks ...
        pressed_button, pick, done = dialog1('Languages', btns, pressed_button, items, pick)
        #pick = selected_items_indexes[0]
        if done and pressed_button == "N":     break                           # NEXT
        elif        pressed_button == "E":     sys.exit()                      # EXIT
        elif        pressed_button == "T":     speak(items[pick])     # TEST
        #elif        pressed_button == "T":     call(['espeak', '-v', language[pick], '-p',pitch, '-s', speed, items[pick]])     # TEST
        
    if   pick == "1":
        textLessSMB = 'Die neuen Einstellungen hätten weniger Bolus vorgeschlagen, nämlich um '
        textMoreSMB = 'Die neuen Einstellungen schlagen einen extra Bolus vor, nämlich '
        textUnit= ' Einheiten'
        both_ansage  = 'Prüf doch Mal die Lage.'
        carb_ansage0 = 'Du brauchst eventuell Kohlenhydrate,'
        both_ansage1 = 'und zwar zirca'
        carb_ansage2 = 'Gramm in den nächsten'
        carb_ansage3 = 'Minuten'
        Speak_items = ["Extra Kohlenhydrate", "Extra Bolus", "Zuviel Bolus"]
        Speak_Pick  = "Wähle Ansagen"
    elif pick == "2":
        textLessSMB = 'the new settings would have suggested less bolus by '
        textMoreSMB = 'the new settings suggest an extra bolus, namely '
        textUnit= ' units'
        both_ansage  = 'Houston, we may have a situation.'
        carb_ansage0 = 'You may need carbohydrates,'
        both_ansage1 = 'namely about'
        carb_ansage2 = 'grams during the next'
        carb_ansage3 = 'minutes'
        Speak_items = ["extra carbs", "extra bolus", "less bolus"]
        Speak_Pick  = "Pick Items"   

    languageID = pick


    ###########################################################################
    #   the  variant definition file dialog
    ###########################################################################
    # New Code per 01-02-2026 Dries
    btns  = {"N": "Next", "E": "Exit"}

    vdf_path = Path(vdf_dir)
    items = {}
    fcount = 1

    #print(vdf_path.exists())
    #print(list(vdf_path.iterdir()))
    try:
        for varFile in vdf_path.iterdir():
            if varFile.is_file() and varFile.suffix.lower() in ('.dat', '.vdf'):
                items[str(fcount)] = varFile.name
                fcount += 1
    except PermissionError:
        print(f'\nWARNING: no *.dat file or *.vdf file found in\n {vdf_path}')
        print("No permissions for the folder")
        if use_termux:
            print("Did you run 'termux-setup-storage'?")
        sys.exit(1)

    if not items:
        print(f'\nWARNING: no *.dat file or *.vdf file found in\n {vdf_path}')
        input('\npress ENTER')
        sys.exit()

    pick = "1"
    pressed_button = "N"

    while True:
        pressed_button, pick, done = dialog1('vdf-files', btns, pressed_button, items, pick)
        #pick = selected_items_indexes[0]
        if done and pressed_button == "N":         break                           # NEXT
        elif        pressed_button == "E":         sys.exit()                      # EXIT
        #lif        pressed_button == "S":         #t speak(items[pick])     # SHOW
    
    varFile = vdf_path / items[pick]

    ###########################################################################
    #   the config file  dialog
    ###########################################################################
    btns  = {"N": "Next", "E": "Exit"}
    items = {}

    cfgF = list(Path(vdf_dir).glob('*.config')) # you can walk through it multiple times, if desired. And no more OS-dependent path logic. Dries

    if not cfgF:
        print('\nWARNING: config file is missing\nin logfile folder\nget config file and restart app')
        input('\npress ENTER')
        sys.exit()

    for idx, cfgFile in enumerate(cfgF, start=1):
        items[str(idx)] = cfgFile.name

    pick = "1"
    pressed_button = "N"

    while True:
        pressed_button, pick, done = dialog1(
            'config-files', btns, pressed_button, items, pick
        )

        if done and pressed_button == "N":  # NEXT
            break
        elif pressed_button == "E":
            sys.exit()                      # EXIT
        #lif        pressed_button == "S":         #t speak(items[pick])     # SHOW

    #fnam= varLabel + '.dat'
    cfg = open(str(vdf_dir) + os.sep + items[pick], 'r')
    next_row= 'extraCarbs'
    for zeile in cfg:
        key = zeile[:1]
        #print (next_row, key, zeile)
        if key == '[' :
            List = []
            wo = zeile.find(']')
            eleList = zeile[1:wo].split(',')    
            if '' not in eleList :              # otherwise empty for no alarms at all
                for i in range(len(eleList)):
                    List.append(eval(eleList[i]))
        else:
            wo = zeile.find('}')
            zeile = zeile[:wo+1]
            
        if next_row == 'extraCarbs':
            pickExtraCarbs = List
            next_row = 'extraBolus'
        elif next_row == 'extraBolus':
            pickMoreSMB = List
            next_row = 'lessBolus'
        elif next_row == 'lessBolus':
            pickLessSMB = List
            next_row = 'outputs'
        elif next_row == 'outputs':
            arg2 = 'Android/' + my_decimal
            outputJson = json.loads(zeile)
            #print('vorher :', str(outputJson))
            total_width = 6                         # base time in hh:mmZ
            for ele in outputJson:
                width = outputJson[ele]
                if width>0:
                    arg2 += '/'+ele
                    total_width += width
            input('Total width of output table is '+str(total_width)+'\nPress Enter to continue')
            next_row = 'end'
    cfg.close()
        
        
    ###########################################################################
    #   the display items dialog
    ###########################################################################
    btns = ["Next", "Exit", "Test"]
    items = ["bg", "target", "iob", "cob", "range", "bestslope", "autosens", "acce_ISF", "bg_ISF", "pp_ISF", "delta_ISF", "dura_ISF", "ISFs", "insReq", "SMB", "basal"]
    width = [9,     6,        6,      6,      13,      13,             6,         6,        6,         6,         6,           6,       20,      13,      11,     12  ]
    pick  = [0,               2,                                       6,         7,        8,         9 ,                    10,       11,      12,      13,     14  ]
    # while not True: Code is not analyzed because condition is statically evaluated as false!
    while True: # That's why I removed the not. Please check if this is correct. Dries
        default_pick = pick
        pressed_button, selected_items_indexes = mydialog("Pick outputs", btns, items, True, default_pick)
        pick = selected_items_indexes
        if   pressed_button ==-1:           sys.exit()                      # external BREAK
        elif selected_items_indexes == []:  sys.exit()                      # all declined
        elif pressed_button == 0:           break                           # NEXT
        elif pressed_button == 1:           sys.exit()                      # EXIT
        elif pressed_button == 2:                                           # TEST
            cols: int = 9                                                   # always: time column
            for i in selected_items_indexes:
                cols += width[i]                                            # add selected column width
            speak(str(cols))                                       # tell the sum

    #arg2 = 'Android/.'+''.join(['/'+items[i] for i in selected_items_indexes])# the feature list what to plot
    #arg2+= '/.'                                                            # always decimal "." on Android
    varyHome= '/storage/emulated/0/Android/data/org.qpython.plus/scripts3/'      # command used to start this script
    #varyHome = os.path.dirname(varyHome) + '\\'
    m  = '='*66+'\nEcho of software versions used\n'+'-'*66
    m +='\n emulator home directory  ' + varyHome
    #global echo_msg
    echo_msg = {}
    echo_msg = get_version_batch(echo_msg)
    echo_msg = get_version_core(echo_msg)
    echo_msg = get_version_determine_basal(echo_msg)
    for ele in echo_msg:
        m += '\n dated: '+echo_msg[ele] + '       module name: '+ele
    m += '\n' + '='*66 + '\n'


    #print ('VDF file:', varFile)
    #print (str(arg2))
    #sys.exit()


    ###########################################################################
    #   no more dialogs; go ahead
    ###########################################################################            
    t_stoppLabel = '2099-00-00T00:00:00Z'           # defaults to end of centuary, i.e. open end
    t_startLabel = '2000-00-00T00:00:00Z'           # defaults to start of centuary, i.e. open start
else:                                               # we are not on Android
    #IsAndroid = False
    #Settings for development on Windows with SMB events:
    #test_dir  = 'L:\PID\ISF\Android/'
    #test_file = 'AndroidAPS._2020-07-13_00-00-00_.2.zip'
    #fn = test_dir + test_file
    #ClearScreenCommand = 'cls'                     # done in --core.py
    #maxItem = '144'    # shows all
    
    """"
    Comments from Dries:
        Unsafe sys.argv[n] May be null!
        String-append spaghetti could be much cleaner.
    """
    if len(sys.argv) < 3:
        print("Usage: script <logfiles> <options> <variant> [start] [stop] [bg]")
        sys.exit()

    # Platform independent
    varyHome = str(Path(sys.argv[0]).resolve().parent) + os.sep # command used to start this script. 
    #print (varyHome)

    m  = '='*66+'\nEcho of software versions used\n'+'-'*66
    m += '\n emulator home directory       ' + varyHome
    #global echo_msg
    echo_msg = {}
    echo_msg = get_version_batch(echo_msg)
    echo_msg = get_version_core(echo_msg)
    echo_msg = get_version_determine_basal(echo_msg)
    for ele in echo_msg:
        m += '\n dated: '+echo_msg[ele] + '       module name: '+ele
    m += '\n'+'-'*66+'\nEcho of execution parameters used\n'+'-'*66
    m += '\nLogfiles to scan      ' + sys.argv[1]
    m += '\nOutput options        ' + sys.argv[2]
    m_default = ''
    
    if '.' in sys.argv[2]:
        my_decimal = '.'
    elif ',' in sys.argv[2]:
        my_decimal = ','
    else:
        my_decimal = ','
        m_default = ' (default)'

    m += '\nDecimal symbol        ' + my_decimal + m_default
    myseek  = sys.argv[1] #+ '\\'
    arg2    = 'Windows/' + sys.argv[2]              # the feature list of what to plot
    varFile = sys.argv[3]                           # the variant label
    if len(sys.argv)>=5:
        t_startLabel = sys.argv[4]                  # first loop time to evaluate#
        m_default = ''
    else:
        t_startLabel = '2000-00-00T00:00:00Z'       # defaults to start of centuary, i.e. open start
        m_default = ' (default)'
    m += '\nStart of time window  ' + t_startLabel + m_default
    if len(sys.argv)>=6:
        t_stoppLabel = sys.argv[5]                  # last loop time to evaluate
        m_default = ''
    else:
        t_stoppLabel = '2099-00-00T00:00:00Z'       # defaults to end of centuary, i.e. open end
        m_default = ' (default)'
    m += '\nEnd of time window    ' + t_stoppLabel + m_default
    if len(sys.argv)==7:
        # load the emulated bg history from dialog database
        m += '\nBG_emul data table    t_'+ sys.argv[6]
    m += '\n' + '='*66 + '\n'

#print ('evaluate from '+t_startLabel+' up to '+t_stoppLabel)

wdhl = 'yes'
entries = {}
lastTime = '0'
pauseCarbsReqEnds = datetime(1970, 1, 1, 0, 0, 0)

while wdhl[0]=='y':                                                                 # use CANCEL to stop/exit
    # All command line arguments known, go for main process
    loopInterval, thisTime, extraSMB, CarbReqGram, CarbReqTime, lastCOB, fn_first, pauseCarbsReqEnds = parameters_known(myseek, arg2, varFile, t_startLabel, t_stoppLabel, entries, m, my_decimal, pauseCarbsReqEnds)
    if thisTime == 'SYNTAX':        break                                           # problem in VDF file
    if thisTime == 'UTF8':          break                                           # PATHONUTF8 nor defined or incorrect
    #print('returned vary_ISF_batch:', CarbReqGram, ' minutes:',  CarbReqTime)
    if IsAndroid:
        thisHour = datetime.now()
        thisStr  = format(thisHour, '%H')
        if thisStr[0] == '0':       thisStr = thisStr[1]                            # could not EVAL('01', only '1')
        thisInt  = eval(thisStr)
        valGram = eval(CarbReqGram+'+0')
        val_lastCOB = eval(str(lastCOB)+'+0')
        #print("Zeitslot:", thisInt, str(pickExtraCarbs))
        #print("extra carbs", str(thisInt in pickExtraCarbs), valGram, str(lastCOB))
        if (thisInt in pickExtraCarbs or -1 in pickExtraCarbs) and valGram != 0 and valGram - val_lastCOB > 6:  # only report if min 0,5 BE missing
            AlarmTime = CarbReqTime
            valTime = eval(AlarmTime)
            #valGram = eval(AlarmGram)
            signif  = valTime / valGram
            if signif<5 and thisTime>lastTime and thisHour>=pauseCarbsReqEnds:      # above threshold of significance
                #pint(both_ansage, carb_ansage0)
                speak(both_ansage)
                speak(carb_ansage0)
                speak(both_ansage1 + str(valGram) + carb_ansage2 + AlarmTime + carb_ansage3)
                #call(['espeak', '-v',language[languageID], '-p',pitch, '-s',speed, both_ansage])
                #call(['espeak', '-v',language[languageID], '-p',pitch, '-s',speed, carb_ansage0])
                #call(['espeak', '-v',language[languageID], '-p',pitch, '-s',speed, both_ansage1 + str(valGram) + carb_ansage2 + AlarmTime + carb_ansage3])
        #print("extra bolus", str(thisInt in pickMoreSMB), str(extraSMB))
        if (thisInt in pickMoreSMB) and extraSMB>0 and thisTime>lastTime:
            speak(textMoreSMB+str(extraSMB)+textUnit)
            #call(['espeak', '-v',language[languageID], '-p',pitch, '-s',speed, textMoreSMB+str(extraSMB)+textUnit])    # wake up user, also during sleep?
        #print("less  bolus", str(thisInt in pickLessSMB), str(extraSMB))
        if (thisInt in pickLessSMB) and extraSMB<0 and thisTime>lastTime:
            speak(textLessSMB+str(extraSMB)+textUnit)
            #call(['espeak', '-v',language[languageID], '-p',pitch, '-s',speed, textLessSMB+str(extraSMB)+textUnit])    # wake up user, also during sleep?
        howLong = waitNextLoop(loopInterval, thisTime, varFile.suffix)
        lastTime = thisTime        
        time.sleep(howLong)
    else:   break                                                                   # on Windows run only once

sys.exit()