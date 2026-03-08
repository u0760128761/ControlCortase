path = r"d:\Личное\progs\cortarse\ControlCortase\raspberry_pi\motor_server.py"
content = open(path, 'r', encoding='utf-8').read()

idx = content.find('_nmcli_run')
if idx == -1:
    print("ERROR: _nmcli_run not found in file!")
else:
    snippet = content[idx:idx+200]
    print("=== Current _nmcli_run snippet ===")
    print(snippet)
    print()
    if "['sudo', 'nmcli']" in content:
        print("STATUS: sudo IS present — fix already applied")
    elif "['nmcli']" in content:
        print("STATUS: sudo NOT present — fix needs to be applied")
    else:
        print("STATUS: cannot determine cmd pattern")
