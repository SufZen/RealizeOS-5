#!/bin/bash
# RealizeOS Desktop Launcher (macOS)
# Double-click this file in Finder to start RealizeOS
cd "$(dirname "$0")"
python3 start-realizeos.pyw &
disown
exit
