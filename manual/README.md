# DEVKIT - Manual Tools

These are standalone tools that run a single analysis pass against an
arbitrary folder (not necessarily a registered project). Use them when you
want a quick one-off look without going through `devkit.py sync`.

Usage (from the DEVKIT home folder):

    python manual/scan.py <folder> [--ignore a,b,c]
    python manual/deps.py <folder> [--ignore a,b,c]
    python manual/techdebt.py <folder> [--ignore a,b,c]

Example:

    python manual/scan.py D:\some_project --ignore node_modules,dist

These tools are thin wrappers over the DEVKIT engine; they do not write any
files, they only print results.
