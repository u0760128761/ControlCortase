"""Fix: change _nmcli_run to use 'sudo nmcli' so it has privileges to manage WiFi connections."""
path = r"d:\Личное\progs\cortarse\ControlCortase\raspberry_pi\motor_server.py"
content = open(path, 'r', encoding='utf-8').read()

old = "cmd = ['nmcli'] + list(args)"
new = "cmd = ['sudo', 'nmcli'] + list(args)"

if old not in content:
    print("ERROR: target not found. Looking for similar...")
    idx = content.find('_nmcli_run')
    print(repr(content[idx:idx+300]))
else:
    result = content.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(result)
    print("OK: _nmcli_run now uses 'sudo nmcli'")
    print("Occurrences replaced: 1")
